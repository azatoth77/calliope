// Calliope · telefono: service worker solo per la cache della pagina (03/10/2026).
// Niente notifiche push (principio 9: niente servizi remoti). Prima la rete, così un
// aggiornamento di Calliope arriva subito; senza rete la pagina si apre dalla cache e dice
// che Calliope non risponde. I modelli li tiene la pagina (Cache Storage), l'audio e le
// schede non passano mai di qui.
"use strict";

const CACHE = "calliope-telefono-pagina-v6";
const PAGINA = [
  "/telefono/", "/telefono/telefono.js", "/telefono/voce.js", "/telefono/microfono.js",
  "/telefono/schermo-acceso.js",
  "/telefono/telefono.css", "/telefono/manifest.webmanifest", "/telefono/icona.svg",
  "/telefono/icona-180.png", "/telefono/icona-192.png", "/telefono/icona-512.png",
  "/schermo.js", "/schermo.css",
];

self.addEventListener("install", (ev) => {
  ev.waitUntil(caches.open(CACHE).then((c) => c.addAll(PAGINA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil(caches.keys()
    .then((k) => Promise.all(k.filter((n) => n.startsWith("calliope-telefono-pagina-") && n !== CACHE)
      .map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (ev) => {
  const u = new URL(ev.request.url);
  if (ev.request.method !== "GET" || u.origin !== location.origin) return;
  if (!PAGINA.includes(u.pathname)) return;      // API, modelli, eventi, WebSocket: diretti
  ev.respondWith(fetch(ev.request).then((r) => {
    if (r.ok) {
      const copia = r.clone();
      caches.open(CACHE).then((c) => c.put(u.pathname, copia));
    }
    return r;
  }).catch(() => caches.match(u.pathname)));
});
