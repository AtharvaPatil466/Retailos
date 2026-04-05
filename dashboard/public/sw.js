const CACHE_NAME = 'retailos-v2';
const OFFLINE_QUEUE_NAME = 'retailos-offline-queue';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192.svg',
  '/icon-512.svg',
];

// Install: cache the shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME && k !== OFFLINE_QUEUE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Offline Queue (IndexedDB) ────────────────────────────
// Queues POST/PUT/PATCH requests when offline, replays when back online

function openOfflineDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('retailos-offline', 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('queue')) {
        db.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function enqueueRequest(request) {
  const db = await openOfflineDB();
  const body = await request.text();
  const tx = db.transaction('queue', 'readwrite');
  tx.objectStore('queue').add({
    url: request.url,
    method: request.method,
    headers: Object.fromEntries(request.headers.entries()),
    body: body,
    timestamp: Date.now(),
  });
  return new Promise((resolve, reject) => {
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

async function replayQueue() {
  const db = await openOfflineDB();
  const tx = db.transaction('queue', 'readonly');
  const store = tx.objectStore('queue');
  const all = await new Promise((resolve) => {
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result);
  });

  const deleteTx = db.transaction('queue', 'readwrite');
  const deleteStore = deleteTx.objectStore('queue');

  for (const entry of all) {
    try {
      await fetch(entry.url, {
        method: entry.method,
        headers: entry.headers,
        body: entry.body || undefined,
      });
      deleteStore.delete(entry.id);
    } catch {
      // Still offline for this one, keep in queue
      break;
    }
  }
}

// ── Fetch Handler ────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Don't intercept WebSocket upgrades
  if (url.pathname.startsWith('/ws')) {
    return;
  }

  // API requests: network-first, queue writes if offline
  if (url.pathname.startsWith('/api')) {
    const isWrite = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(event.request.method);

    if (isWrite) {
      event.respondWith(
        fetch(event.request.clone()).catch(async () => {
          // Offline: queue the write and return a synthetic response
          await enqueueRequest(event.request.clone());
          return new Response(
            JSON.stringify({
              status: 'queued',
              message: 'You are offline. This action has been queued and will sync when you reconnect.',
            }),
            {
              status: 202,
              headers: { 'Content-Type': 'application/json' },
            }
          );
        })
      );
    } else {
      // GET requests: try network, fall back to cache
      event.respondWith(
        fetch(event.request)
          .then((response) => {
            if (response.ok) {
              const clone = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
            }
            return response;
          })
          .catch(() => caches.match(event.request).then((r) =>
            r || new Response(
              JSON.stringify({ status: 'offline', message: 'No cached data available' }),
              { status: 503, headers: { 'Content-Type': 'application/json' } }
            )
          ))
      );
    }
    return;
  }

  // Static assets: network-first with cache fallback
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

// ── Background Sync ──────────────────────────────────────
// Replay queued requests when connectivity returns

self.addEventListener('sync', (event) => {
  if (event.tag === 'replay-queue') {
    event.waitUntil(replayQueue());
  }
});

// Also replay on message from the app
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'REPLAY_QUEUE') {
    replayQueue().then(() => {
      event.source.postMessage({ type: 'QUEUE_REPLAYED' });
    });
  }
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
