/* poland-trip-weather · sw.js v1 — עבודה בלי רשת
   המסך והנתונים: קודם רשת (עד 6 שניות), ואם אין — העותק האחרון ששמור במכשיר.
   קבצים קבועים (אייקונים, מניפסט): מהמכשיר, ואם אין — מהרשת. */
const CACHE = "ptw-v1";
const SHELL = ["./", "index.html", "manifest.webmanifest",
               "icon-192.png", "icon-512.png", "apple-touch-icon.png"];
const TIMEOUT_MS = 6000;

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE)
    .then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k.startsWith("ptw-") && k !== CACHE)
                              .map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

function keyFor(req) {
  const u = new URL(req.url);
  if (req.mode === "navigate" || u.pathname.endsWith("/")) return new URL("index.html", self.registration.scope).href;
  return u.origin + u.pathname;          // בלי ?t=… כדי שיהיה עותק אחד לכל קובץ
}

function withTimeout(p, ms) {
  return new Promise((ok, bad) => {
    const t = setTimeout(() => bad(new Error("timeout")), ms);
    p.then(r => { clearTimeout(t); ok(r); }, x => { clearTimeout(t); bad(x); });
  });
}

async function networkFirst(req) {
  const key = keyFor(req), c = await caches.open(CACHE);
  try {
    const r = await withTimeout(fetch(req), TIMEOUT_MS);
    if (r && r.ok) c.put(key, r.clone()).catch(() => null);
    return r;
  } catch (x) {
    const hit = await c.match(key);
    if (hit) {                              // מסמנים למסך שזה עותק שמור, לא נתון חדש
      const h = new Headers(hit.headers); h.set("X-PTW-From-Cache", "1");
      return new Response(await hit.blob(), {status: hit.status, statusText: hit.statusText, headers: h});
    }
    throw x;
  }
}

async function cacheFirst(req) {
  const key = keyFor(req), c = await caches.open(CACHE);
  const hit = await c.match(key);
  if (hit) return hit;
  const r = await fetch(req);
  if (r && r.ok) c.put(key, r.clone()).catch(() => null);
  return r;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const u = new URL(req.url);
  if (u.origin !== self.location.origin) return;
  const p = u.pathname;
  if (req.mode === "navigate" || p.endsWith("/") || p.endsWith("/index.html")
      || p.endsWith("/data/latest.json") || p.endsWith("/data/cards.json")
      || p.includes("/data/cards/")) {
    e.respondWith(networkFirst(req));
  } else if (/\.(png|webmanifest|woff2)$/.test(p)) {
    e.respondWith(cacheFirst(req));
  }
});
