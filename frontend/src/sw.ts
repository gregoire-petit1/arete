/// <reference lib="webworker" />
import { clientsClaim } from 'workbox-core';
import { ExpirationPlugin } from 'workbox-expiration';
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { NetworkFirst } from 'workbox-strategies';

declare let self: ServiceWorkerGlobalScope;

// Same behaviour as the former generated worker (registerType: 'autoUpdate').
self.skipWaiting();
clientsClaim();

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// SPA navigation falls back to the app shell. API calls and the Strava OAuth
// callback must reach the server, never the cached shell.
registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html'), { denylist: [/^\/api\//] }));

registerRoute(
  ({ url }) => url.pathname.startsWith('/api/') && !url.pathname.startsWith('/api/agent/') && !url.pathname.startsWith('/api/garmin/exports'),
  new NetworkFirst({
    cacheName: 'api-cache',
    // Past 10 s offline-ish, serve the cached answer if any.
    networkTimeoutSeconds: 10,
    plugins: [new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 300 })],
  })
);

/** What the server sends (services/notifications.py). */
interface PushPayload {
  title: string;
  body: string;
  url: string;
}

function readPayload(event: PushEvent): PushPayload {
  try {
    const data = event.data?.json() as Partial<PushPayload> | undefined;
    return { title: data?.title ?? 'Arete', body: data?.body ?? '', url: data?.url ?? '/' };
  } catch {
    return { title: 'Arete', body: event.data?.text() ?? '', url: '/' };
  }
}

self.addEventListener('push', (event) => {
  const { title, body, url } = readPayload(event);
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      data: { url },
      icon: '/pwa-192x192.png',
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL((event.notification.data as { url?: string } | null)?.url ?? '/', self.location.origin);
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      const open = windows.find((w) => new URL(w.url).origin === target.origin);
      if (open) {
        await open.focus();
        if (new URL(open.url).pathname !== target.pathname) await open.navigate(target.href);
        return;
      }
      await self.clients.openWindow(target.href);
    })()
  );
});
