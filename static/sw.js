// YazKlinik Service Worker - offline-first cache + push notif
const CACHE = "yazklinik-v1-2026-05-17";
const APP_SHELL = [
  "/",
  "/dashboard",
  "/static/manifest.json",
  "/static/css/medical_theme.css",
];

self.addEventListener("install", (evt) => {
  evt.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(APP_SHELL).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (evt) => {
  evt.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (evt) => {
  const req = evt.request;
  if (req.method !== "GET") return;
  // Network-first for HTML, cache-first for assets
  if (req.headers.get("accept")?.includes("text/html")) {
    evt.respondWith(
      fetch(req).catch(() => caches.match(req).then((r) => r || caches.match("/")))
    );
  } else {
    evt.respondWith(
      caches.match(req).then((cached) => cached || fetch(req).then((resp) => {
        if (resp && resp.status === 200) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return resp;
      }))
    );
  }
});

self.addEventListener("push", (evt) => {
  const data = evt.data ? evt.data.json() : {};
  const title = data.title || "YazKlinik";
  const opts = {
    body: data.body || "",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    tag: data.tag || "default",
    data: data.url || "/",
  };
  evt.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener("notificationclick", (evt) => {
  evt.notification.close();
  evt.waitUntil(clients.openWindow(evt.notification.data || "/"));
});
