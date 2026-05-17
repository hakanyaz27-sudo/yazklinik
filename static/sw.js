// YazKlinik Service Worker - offline-first cache + push notif
// v3 2026-05-17: /api/ pathlarini ATLA (cache HATALI idi, abort ediyordu)
const CACHE = "yazklinik-v3-2026-05-17-api-bypass";
const APP_SHELL = [
  "/",
  "/dashboard",
  "/ajanlar",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
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
  const url = new URL(req.url);

  // KRITIK: /api/ + /giris + dinamik sayfalar -> ASLA cache, dogrudan network
  // Onceki versiyon /api/ cagrilarini cache'liyordu -> abort + stale data
  if (req.method !== "GET" ||
      url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/hasta-portal") ||
      url.pathname.startsWith("/giris") ||
      url.pathname.startsWith("/cikis") ||
      url.pathname.startsWith("/randevular") ||
      url.pathname.startsWith("/hasta/") ||
      url.pathname === "/uyumluluk" ||
      url.pathname === "/status" ||
      url.pathname === "/stok" ||
      url.pathname === "/2fa-setup" ||
      url.pathname === "/mobil") {
    // Default network davranisi - SW karismaz
    return;
  }

  // HTML sayfalar - network-first, offline'da cache
  if (req.headers.get("accept")?.includes("text/html")) {
    evt.respondWith(
      fetch(req).catch(() => caches.match(req).then((r) => r || caches.match("/")))
    );
    return;
  }

  // Static asset (CSS, JS, image) - cache-first
  evt.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).then((resp) => {
      if (resp && resp.status === 200 && resp.type === "basic") {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return resp;
    }))
  );
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
