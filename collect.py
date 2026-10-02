#!/usr/bin/env python3
"""poland-trip-weather · collect.py v0.1.1

אוסף מזג אוויר למסע לפולין (18–24/11/2026). רץ ב-GitHub Actions, כותב
data/latest.json שהמסך (index.html) קורא. ספרייה סטנדרטית בלבד, בלי תלויות.

מקורות (כל אחד מבודד: כשל באחד לא מפיל את האחרים):
  met      MET Norway locationforecast 2.0 complete   (CC BY 4.0)
  models   Open-Meteo: ICON / ECMWF / GFS, יומי       (CC BY 4.0)
  metar    NOAA AviationWeather: EPWA, EPKK, EPLB     (מדידה בפועל)
  climate  Open-Meteo archive 2016–2025, 18–24/11     (ממוצע עונה, נשמר ב-data/climate.json
           ולא מורד שוב אם כבר קיים)

יחידות: טמפרטורה °C, גשם מ"מ, רוח ומשבים קמ"ש (יבשה). ימים לפי שעון פולין.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

VERSION = "0.1.1"
UA = "poland-trip-weather/0.1 github.com/ws4g8r267v-cyber/poland-trip-weather"
TZ_PL = ZoneInfo("Europe/Warsaw")
TIMEOUT = 40
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

TRIP_DAYS = ["2026-11-%02d" % d for d in range(18, 25)]
CLIMATE_YEARS = (2016, 2025)

SITES = {
    "warsaw":    {"lat": 52.2497, "lon": 20.9930, "station": "EPWA"},
    "treblinka": {"lat": 52.6313, "lon": 22.0522, "station": "EPWA"},
    "majdanek":  {"lat": 51.2206, "lon": 22.6033, "station": "EPLB"},
    "birkenau":  {"lat": 50.0343, "lon": 19.1784, "station": "EPKK"},
    "krakow":    {"lat": 50.0510, "lon": 19.9450, "station": "EPKK"},
}
STATIONS = ["EPWA", "EPKK", "EPLB"]
MODELS = {"icon": "icon_seamless", "ecmwf": "ecmwf_ifs025", "gfs": "gfs_seamless"}


def log(msg):
    print("[%s] %s" % (datetime.now(timezone.utc).strftime("%H:%M:%SZ"), msg),
          flush=True)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def r1(x):
    return None if x is None else round(float(x), 1)


# ---------- MET Norway ----------
def fetch_met():
    out, errors = {}, []
    for sid, s in SITES.items():
        try:
            url = ("https://api.met.no/weatherapi/locationforecast/2.0/complete?"
                   "lat=%.4f&lon=%.4f" % (s["lat"], s["lon"]))
            ts = get_json(url)["properties"]["timeseries"]
            days = {}
            for e in ts:
                t = datetime.fromisoformat(e["time"].replace("Z", "+00:00"))
                day = t.astimezone(TZ_PL).strftime("%Y-%m-%d")
                d = days.setdefault(day, {"temps": [], "mm": 0.0, "wind": [],
                                          "gust": [], "pop": []})
                inst = e["data"]["instant"]["details"]
                if "air_temperature" in inst:
                    d["temps"].append(inst["air_temperature"])
                if "wind_speed" in inst:
                    d["wind"].append(inst["wind_speed"] * 3.6)
                if "wind_speed_of_gust" in inst:
                    d["gust"].append(inst["wind_speed_of_gust"] * 3.6)
                n1 = e["data"].get("next_1_hours", {}).get("details", {})
                n6 = e["data"].get("next_6_hours", {}).get("details", {})
                if "precipitation_amount" in n1:
                    d["mm"] += n1["precipitation_amount"]
                elif "precipitation_amount" in n6:
                    d["mm"] += n6["precipitation_amount"]
                if "probability_of_precipitation" in n6:
                    d["pop"].append(n6["probability_of_precipitation"])
            out[sid] = {day: {
                "tmin": r1(min(d["temps"])) if d["temps"] else None,
                "tmax": r1(max(d["temps"])) if d["temps"] else None,
                "mm": r1(d["mm"]),
                "wind": round(max(d["wind"])) if d["wind"] else None,
                "gust": round(max(d["gust"])) if d["gust"] else None,
                "pop": round(max(d["pop"])) if d["pop"] else None,
                "n": len(d["temps"]),
            } for day, d in sorted(days.items())}
        except Exception as ex:  # רק סוג החריגה, בלי פרטים
            errors.append("%s:%s" % (sid, type(ex).__name__))
    return out, errors


# ---------- Open-Meteo: השוואת מודלים ----------
def fetch_models():
    out, errors = {}, []
    daily = ("temperature_2m_max,temperature_2m_min,precipitation_sum,"
             "wind_speed_10m_max,wind_gusts_10m_max")
    for sid, s in SITES.items():
        try:
            q = urllib.parse.urlencode({
                "latitude": s["lat"], "longitude": s["lon"], "daily": daily,
                "models": ",".join(MODELS.values()), "forecast_days": 16,
                "timezone": "Europe/Warsaw"})
            j = get_json("https://api.open-meteo.com/v1/forecast?" + q)
            dl = j["daily"]
            site = {}
            for key, m in MODELS.items():
                rows = {}
                for i, day in enumerate(dl["time"]):
                    def v(name):
                        col = dl.get("%s_%s" % (name, m))
                        return col[i] if col and i < len(col) else None
                    tmax = v("temperature_2m_max")
                    if tmax is None:
                        continue
                    rows[day] = {"tmax": r1(tmax),
                                 "tmin": r1(v("temperature_2m_min")),
                                 "mm": r1(v("precipitation_sum")),
                                 "wind": r1(v("wind_speed_10m_max")),
                                 "gust": r1(v("wind_gusts_10m_max"))}
                site[key] = rows
            out[sid] = site
        except Exception as ex:
            errors.append("%s:%s" % (sid, type(ex).__name__))
    return out, errors


# ---------- METAR ----------
def fetch_metar():
    out, errors = {}, []
    url = ("https://aviationweather.gov/api/data/metar?ids=%s&format=json"
           % ",".join(STATIONS))
    try:
        try:
            j = get_json(url)
        except Exception:
            time.sleep(8)            # ניסיון שני אחד; נכשל שוב → נרשם עם קוד ה-HTTP
            j = get_json(url)
        for ob in j:
            icao = ob.get("icaoId")
            if icao not in STATIONS:
                continue
            t = ob.get("obsTime")
            prev = out.get(icao)
            if prev and prev["obs"] >= (t or 0):
                continue
            kt = ob.get("wspd")
            gkt = ob.get("wgst")
            out[icao] = {
                "obs": t,
                "temp": ob.get("temp"),
                "wind": round(kt * 1.852) if isinstance(kt, (int, float)) else None,
                "gust": round(gkt * 1.852) if isinstance(gkt, (int, float)) else None,
                "wx": ob.get("wxString") or "",
                "raw": ob.get("rawOb", ""),
            }
        for icao in STATIONS:
            if icao not in out:
                errors.append("%s:missing" % icao)
    except Exception as ex:
        code = getattr(ex, "code", None)   # HTTPError → 403/429/5xx, כדי לדעת מה קרה
        errors.append("%s:%s" % (type(ex).__name__, code) if code else type(ex).__name__)
    return out, errors


# ---------- ממוצע עונה (פעם אחת) ----------
def climate(existing):
    if existing and existing.get("sites") and len(existing["sites"]) == len(SITES):
        return existing, []          # לא מורידים שוב מה שכבר נקרא
    out, errors = {}, []
    y0, y1 = CLIMATE_YEARS
    for sid, s in SITES.items():
        try:
            q = urllib.parse.urlencode({
                "latitude": s["lat"], "longitude": s["lon"],
                "start_date": "%d-11-18" % y0, "end_date": "%d-11-24" % y1,
                "daily": "temperature_2m_max,temperature_2m_min,"
                         "precipitation_sum,wind_speed_10m_max",
                "timezone": "Europe/Warsaw"})
            dl = get_json("https://archive-api.open-meteo.com/v1/archive?" + q)["daily"]
            hi, lo, mm, wd, wn = [], [], [], 0, []
            for i, day in enumerate(dl["time"]):
                if not ("11-18" <= day[5:] <= "11-24"):
                    continue
                if dl["temperature_2m_max"][i] is None:
                    continue
                hi.append(dl["temperature_2m_max"][i])
                lo.append(dl["temperature_2m_min"][i])
                p = dl["precipitation_sum"][i] or 0
                mm.append(p)
                wd += 1 if p >= 1 else 0
                if dl["wind_speed_10m_max"][i] is not None:
                    wn.append(dl["wind_speed_10m_max"][i])
            if not hi:
                raise ValueError("empty")
            out[sid] = {"tmax": r1(sum(hi) / len(hi)), "tmin": r1(sum(lo) / len(lo)),
                        "mm": r1(sum(mm) / len(mm)),
                        "wet": round(100 * wd / len(hi)),
                        "wind": round(sum(wn) / len(wn)) if wn else None,
                        "n": len(hi)}
        except Exception as ex:
            errors.append("%s:%s" % (sid, type(ex).__name__))
    if errors:
        return {"years": list(CLIMATE_YEARS), "sites": out}, errors
    return {"years": list(CLIMATE_YEARS), "sites": out,
            "built": datetime.now(timezone.utc).isoformat(timespec="seconds")}, []


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)           # כתיבה אטומית


def main():
    os.makedirs(DATA, exist_ok=True)
    t0 = time.time()
    sources = {}

    met, e = fetch_met();       sources["met"] = {"errors": e}
    log("met sites=%d errors=%s" % (len(met), e))
    models, e = fetch_models(); sources["models"] = {"errors": e}
    log("models sites=%d errors=%s" % (len(models), e))
    metar, e = fetch_metar();   sources["metar"] = {"errors": e}
    log("metar stations=%d errors=%s" % (len(metar), e))

    cpath = os.path.join(DATA, "climate.json")
    clim, e = climate(read_json(cpath))
    sources["climate"] = {"errors": e}
    if not e and clim.get("built"):
        write_json(cpath, clim)
    log("climate sites=%d errors=%s" % (len(clim.get("sites", {})), e))

    # אתר או תחנה שנכשלו שומרים את הנתון הקודם שלהם, מסומנים כישנים
    prev = read_json(os.path.join(DATA, "latest.json")) or {}
    for name, cur in (("met", met), ("models", models), ("metar", metar)):
        old = prev.get(name) or {}
        kept = sorted(k for k in old if k not in cur)
        for k in kept:
            cur[k] = old[k]
        if kept:
            sources[name]["kept_old"] = kept
            sources[name]["stale_since"] = prev.get("sources", {}).get(name, {}).get(
                "stale_since", prev.get("generated"))

    latest = {
        "version": VERSION,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trip_days": TRIP_DAYS,
        "met": met, "models": models, "metar": metar,
        "climate": clim.get("sites", {}), "climate_years": list(CLIMATE_YEARS),
        "sources": sources,
    }
    write_json(os.path.join(DATA, "latest.json"), latest)
    log("done in %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
