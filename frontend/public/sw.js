/* Recommendarr Service Worker — Push notification handler.
 * VAASSEN GmbH / Ray Vaassen
 *
 * Handles incoming push events, displays native notifications,
 * and routes notification click actions to the app.
 */

// ── Push Event ──────────────────────────────────────────────────

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "Recommendarr", body: event.data.text() };
  }

  const options = {
    body: payload.body || "",
    icon: payload.icon || "/icon-192.png",
    badge: payload.badge || "/icon-192.png",
    tag: payload.tag || "recommendarr-default",
    data: { url: payload.url || "/", ...(payload.data || {}) },
    vibrate: [100, 50, 100],
    actions: payload.actions || [],
  };

  event.waitUntil(
    self.registration.showNotification(payload.title || "Recommendarr", options)
  );
});

// ── Notification Click ──────────────────────────────────────────

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const url = event.notification.data?.url || "/";
  const action = event.action; // from notification actions buttons

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      // If app is already open, focus it and navigate
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin)) {
          client.focus();
          client.postMessage({
            type: "NOTIFICATION_CLICK",
            url,
            action,
            data: event.notification.data,
          });
          return;
        }
      }
      // Otherwise open new window
      return clients.openWindow(url);
    })
  );
});

// ── Install/Activate (minimal — no offline caching) ─────────────

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
