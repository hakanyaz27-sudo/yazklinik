// YazKlinik Service Worker - DISABLED (eski SW abort sebebi)
// v4 2026-05-17: SW kendi kendini unregister + tum cache siler
// Boylece browser otomatik temizlik yapar
self.addEventListener("install", (evt) => {
  self.skipWaiting();
});

self.addEventListener("activate", (evt) => {
  evt.waitUntil((async () => {
    // Tum cache'i sil
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
    } catch(e) {}
    // Kendini unregister
    try {
      await self.registration.unregister();
    } catch(e) {}
    // Tum clientlara bildir
    try {
      const clients = await self.clients.matchAll();
      for(const c of clients) {
        c.postMessage({type: 'sw-disabled'});
      }
    } catch(e) {}
  })());
});

// Fetch event KESIN bypass - tum istekleri normal network'e birak
self.addEventListener("fetch", (evt) => {
  // Hicbir respondWith yapma - browser dogal davranisi
  return;
});
