// Retired. The whole site is now cached by ../sw.js; this removes the old book-only worker
// from phones that installed it, then reloads those pages so the new worker takes over.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil((async () => {
  await caches.delete("spiti-book-v1");
  await self.registration.unregister();
  for (const client of await self.clients.matchAll({ type: "window" })) client.navigate(client.url);
})()));
