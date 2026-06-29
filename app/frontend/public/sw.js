const CACHE = 'logcore-v4'
const STATIC = ['/manifest.json', '/icon-192.png', '/icon-512.png']

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  )
})

// ── Push notifications ──────────────────────────────────────────────────────

self.addEventListener('push', e => {
  let data = { title: 'LogCore', body: '', url: '/' }
  try { data = { ...data, ...e.data.json() } } catch {}
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      data: { url: data.url },
    })
  )
})

self.addEventListener('notificationclick', e => {
  e.notification.close()
  const url = e.notification.data?.url || '/'
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(all => {
      const existing = all.find(c => new URL(c.url).pathname !== '/login')
      if (existing) { existing.focus(); return existing.navigate(url) }
      return clients.openWindow(url)
    })
  )
})

// ── Fetch handler ────────────────────────────────────────────────────────────

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url)

  // Network-first for API calls
  if (url.pathname.startsWith('/api')) {
    e.respondWith(
      fetch(e.request).catch(() => new Response(JSON.stringify({ error: 'offline' }), {
        headers: { 'Content-Type': 'application/json' }
      }))
    )
    return
  }

  // Network-first for HTML — always get the latest app shell, fall back to cache offline
  const isHtml = url.pathname === '/' || url.pathname === '/index.html' || !url.pathname.split('/').pop().includes('.')
  if (isHtml) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone()))
          return res
        })
        .catch(() => caches.match(e.request))
    )
    return
  }

  // Cache-first for static assets (JS/CSS are content-hashed, icons/manifest are pre-cached)
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached
      return fetch(e.request).then(res => {
        if (res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone()))
        return res
      })
    })
  )
})
