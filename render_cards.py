"""poland-trip-weather · render_cards.py v0.1

Renders card.html (the morning card) to JPG for WhatsApp, from the same
data/latest.json the screen reads, after collect.py has written it.

Which days:
  auto (default) - today and tomorrow, Poland time, only inside the trip
                   (18-24/11/2026). Outside that window nothing is rendered,
                   so the repo does not grow with images nobody sends.
  all            - all 7 trip days (manual run, to check before the trip).

Writes data/cards/card-DD.jpg and data/cards/cards.json:
  {"rendered": ISO-UTC, "data_generated": ..., "days": {"18": {...}}}
The agent reads cards.json and sends a card only if it is fresh.

Browser: Google Chrome that is preinstalled on the GitHub runner
(channel="chrome"); locally falls back to Playwright's Chromium.
"""
import datetime as dt
import functools
import hashlib
import http.server
import json
import os
import sys
import threading
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "cards")
TRIP_DAYS = range(18, 25)
PL = ZoneInfo("Europe/Warsaw")
PORT = 8799


def days_to_render(mode, now_pl):
    if mode == "all":
        return list(TRIP_DAYS)
    out = []
    for add in (0, 1):
        d = (now_pl + dt.timedelta(days=add)).date()
        if d.year == 2026 and d.month == 11 and d.day in TRIP_DAYS:
            out.append(d.day)
    return out


def serve():
    h = functools.partial(http.server.SimpleHTTPRequestHandler,
                          directory=ROOT)
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def launch(p):
    try:
        return p.chromium.launch(channel="chrome")
    except Exception as e:
        print("chrome channel not available (%s), using chromium"
              % type(e).__name__)
        return p.chromium.launch()


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "auto").strip() or "auto"
    now_pl = dt.datetime.now(PL)
    days = days_to_render(mode, now_pl)
    print("mode=%s now_pl=%s days=%s" % (mode, now_pl.strftime(
        "%Y-%m-%d %H:%M"), days))
    if not days:
        return 0
    data = json.load(open(os.path.join(ROOT, "data", "latest.json"),
                          encoding="utf-8"))
    os.makedirs(OUT, exist_ok=True)
    idx_path = os.path.join(OUT, "cards.json")
    try:
        idx = json.load(open(idx_path, encoding="utf-8"))
    except Exception:
        idx = {"days": {}}
    srv = serve()
    bad = 0
    with sync_playwright() as p:
        b = launch(p)
        for day in days:
            pg = b.new_page(viewport={"width": 1080, "height": 1350})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://127.0.0.1:%d/card.html?day=%d" % (PORT, day))
            pg.wait_for_selector("body[data-ready]", timeout=15000)
            pg.evaluate("document.fonts.ready")
            ready = pg.evaluate("document.body.dataset.ready")
            if ready != "1" or errs:
                print("FAIL day=%d ready=%s errs=%s" % (day, ready, errs))
                bad += 1
                pg.close()
                continue
            path = os.path.join(OUT, "card-%02d.jpg" % day)
            pg.screenshot(path=path, type="jpeg", quality=88)
            pg.close()
            md5 = hashlib.md5(open(path, "rb").read()).hexdigest()[:8]
            idx["days"][str(day)] = {
                "file": "card-%02d.jpg" % day,
                "rendered": dt.datetime.now(dt.timezone.utc).isoformat(
                    timespec="seconds"),
                "data_generated": data.get("generated"),
                "md5": md5,
                "bytes": os.path.getsize(path)}
            print("ok day=%d %s %d bytes" % (day, md5, os.path.getsize(path)))
        b.close()
    srv.shutdown()
    idx["rendered"] = dt.datetime.now(dt.timezone.utc).isoformat(
        timespec="seconds")
    idx["data_generated"] = data.get("generated")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
