const CACHE = 'fishpal-v2';
const STATIC_URLS = ['/manifest.json', '/icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC_URLS)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(k => Promise.all(k.filter(x => x !== CACHE).map(x => caches.delete(x))))
  );
});

self.addEventListener('fetch', e => {
  const { origin, pathname } = new URL(e.request.url);
  if (origin !== self.location.origin || e.request.url.includes('/predict')) return;

  // HTML: network-first for fresh updates
  if (pathname === '/' || pathname === '') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }

  // Static assets: cache-first
  e.respondWith(
    caches.open(CACHE).then(c => c.match(e.request).then(r => r || fetch(e.request)))
  );
});
