/* PFML's service worker (README, Reminders). It only shows notifications:
   no caching and no fetch handler, so pages and data always come from the
   network exactly as they would without it. account.js registers it when a
   member turns notifications on for this phone or browser. */

self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (ev) { ev.waitUntil(self.clients.claim()); });

// {title, body, url, tag} from send-reminders (supabase/functions/)
self.addEventListener("push", function (ev) {
  var msg = {};
  try { msg = ev.data ? ev.data.json() : {}; } catch (e) { msg = { body: ev.data ? ev.data.text() : "" }; }
  ev.waitUntil(self.registration.showNotification(msg.title || "PFML", {
    body: msg.body || "",
    icon: "icon-192.png",
    tag: msg.tag || undefined,
    data: { url: msg.url || "./" }
  }));
});

// A tap opens the page it's about, in the app if it's open; only ever on
// this site, whatever the message says.
self.addEventListener("notificationclick", function (ev) {
  ev.notification.close();
  var url = new URL((ev.notification.data && ev.notification.data.url) || "./", self.registration.scope);
  if (url.origin !== self.location.origin) url = new URL(self.registration.scope);
  ev.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    var open = list.filter(function (c) { return "focus" in c; })[0];
    if (!open) return self.clients.openWindow(url.href);
    return open.focus().then(function (c) { return c.navigate ? c.navigate(url.href) : c; })
      .catch(function () { return self.clients.openWindow(url.href); });
  }));
});
