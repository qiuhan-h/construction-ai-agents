/* Service Worker — 缓存 Streamlit 静态资源（4: Streamlit 不支持离线 App Shell，
   仅缓存 manifest 和本文件，不拦截 Streamlit 动态请求。）
*/
const CACHE_NAME = 'caai-v1';
const PRECACHE_URLS = [
  './manifest.json',
  './service-worker.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Streamlit 动态请求直接放行，只缓存同源静态资源
  if (!event.request.url.startsWith(self.location.origin)) return;
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('_stcore')) return;
  if (event.request.url.includes('streamlit')) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return resp;
      });
    })
  );
});
