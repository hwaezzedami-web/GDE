// Bouchra service worker: offline start + push notifications.
// Pushes arrive without content; we read the waiting notifications from Firebase.
const SHELL = 'bouchra-shell-v1';
const AUTH = 'bouchra-auth';
const FILES = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith('bouchra-shell') && k !== SHELL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(fetch(req).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(SHELL).then(c => c.put(req, copy)); }
    return res;
  }).catch(() => caches.match(req).then(r => r || caches.match('./index.html'))));
});

async function readAuth() {
  const c = await caches.open(AUTH);
  const r = await c.match('./__auth');
  return r ? r.json() : null;
}

async function freshToken(a) {
  const r = await fetch(a.tokenBase + '?key=' + encodeURIComponent(a.key), {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'grant_type=refresh_token&refresh_token=' + encodeURIComponent(a.refresh)
  });
  if (!r.ok) throw new Error('token ' + r.status);
  const j = await r.json();
  if (j.refresh_token && j.refresh_token !== a.refresh) {
    a.refresh = j.refresh_token;
    const c = await caches.open(AUTH);
    await c.put('./__auth', new Response(JSON.stringify(a)));
  }
  return j.id_token;
}

const TAB_FOR = {shop: 'shop', coupon: 'coupons', dream: 'dreams'};

async function onPush(e) {
  let shown = 0;
  try {
    const a = await readAuth();
    if (a && a.refresh && a.cid) {
      const t = await freshToken(a);
      const base = a.db + '/couples/' + a.cid + '/inbox/' + a.uid;
      const r = await fetch(base + '.json?auth=' + encodeURIComponent(t) + (a.q || ''));
      const inbox = r.ok ? await r.json() : null;
      for (const [k, v] of Object.entries(inbox || {})) {
        if (!v) continue;
        await self.registration.showNotification(v.title || '💕 بشرى', {
          body: v.text || '', tag: k, icon: 'icon-192.png', badge: 'icon-192.png',
          data: {tab: TAB_FOR[v.kind] || 'chat'}
        });
        shown++;
        fetch(base + '/' + k + '.json?auth=' + encodeURIComponent(t) + (a.q || ''), {method: 'DELETE'}).catch(() => {});
      }
    }
  } catch (err) { /* fall through to a generic notification */ }
  if (!shown) {
    // Safari requires a visible notification for every push.
    await self.registration.showNotification('💕 بشرى', {body: 'لديكِ رسالة جديدة', icon: 'icon-192.png', data: {tab: 'chat'}});
  }
}

self.addEventListener('push', e => e.waitUntil(onPush(e)));

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const tab = (e.notification.data && e.notification.data.tab) || 'chat';
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
    for (const c of all) {
      c.postMessage({tab});
      if ('focus' in c) return c.focus();
    }
    return self.clients.openWindow('./#' + tab);
  })());
});
