// Calliope · telefono: service worker solo per la cache della pagina (03/10/2026).
// Niente notifiche push (principio 9: niente servizi remoti). Prima la rete, così un
// aggiornamento di Calliope arriva subito; senza rete la pagina si apre dalla cache e dice
// che Calliope non risponde. I modelli li tiene la pagina (Cache Storage), l'audio e le
// schede non passano mai di qui.
"use strict";

// v39 (31/10, #298 parte 3): la condivisione dal telefono (share target, condividi.js)
const CACHE = "calliope-telefono-pagina-v39";
const PAGINA = [
  "/telefono/", "/telefono/telefono.js", "/telefono/voce.js", "/telefono/microfono.js",
  "/telefono/schermo-acceso.js",
  "/telefono/telefono.css", "/telefono/manifest.webmanifest", "/telefono/icona.svg",
  "/telefono/icona-180.png", "/telefono/icona-192.png", "/telefono/icona-512.png",
  "/schermo.js", "/schermo.css", "/sezioni.js", "/bordi.js", "/studio.js",
  "/libreria.js", "/studio_importa.js", "/telefono/condividi.js",
];

// La condivisione da un'altra app (31/10, #298 parte 3: share_target nel manifest, solo Android
// con la PWA installata). Il POST arriva qui e non al server: senza la sessione dello schermo il
// server non prende niente. I file restano sul telefono, in IndexedDB, finché la persona non
// sceglie la verifica nella pagina (condividi.js), che li manda con la stessa importazione di
// «Aggiungi materiali». Al più CONDIVISI_MAX file; una condivisione nuova sostituisce la vecchia
const CONDIVISI_DB = "calliope-condivisi";
const CONDIVISI_MAX = 10;

function condivisiDb() {
  return new Promise((ok, no) => {
    const r = indexedDB.open(CONDIVISI_DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore("file", { keyPath: "id", autoIncrement: true });
    r.onsuccess = () => ok(r.result);
    r.onerror = () => no(r.error);
  });
}

async function condividi(req) {
  let n = 0;
  try {
    const dati = await req.formData();
    const file = dati.getAll("file").filter((f) => f && typeof f === "object" && typeof f.size === "number")
      .slice(0, CONDIVISI_MAX);
    const db = await condivisiDb();
    await new Promise((ok, no) => {
      const t = db.transaction("file", "readwrite");
      const s = t.objectStore("file");
      s.clear();
      for (const f of file) {
        s.add({ nome: String(f.name || "file").slice(0, 120), tipo: String(f.type || "").slice(0, 100),
          dim: f.size, quando: Date.now(), blob: f });
      }
      t.oncomplete = ok;
      t.onerror = () => no(t.error);
    });
    db.close();
    n = file.length;
  } catch (e) { n = 0; }
  return Response.redirect("/telefono/?condividi=" + (n ? "1" : "vuoto") + "#/cose", 303);
}

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
  if (ev.request.method === "POST" && u.origin === location.origin && u.pathname === "/telefono/condividi") {
    ev.respondWith(condividi(ev.request));
    return;
  }
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
