// Network-first cache so the book still opens with no signal on the road.
const CACHE = "spiti-book-v1";

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(["./"])));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const network = fetch(e.request).then(res => {
    if (res.ok) {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, copy));
    }
    return res;
  });
  // Give a slow mountain connection a few seconds, then fall back to the cached copy.
  const timeout = new Promise(resolve => setTimeout(resolve, 4000));
  e.respondWith(
    Promise.race([network, timeout])
      .then(res => res || caches.match(e.request, { ignoreSearch: true }).then(hit => hit || network))
      .catch(() => caches.match(e.request, { ignoreSearch: true }).then(hit => hit || Response.error()))
  );
});
