// Un gioco OSTILE per le prove (prove/prova_giochi_pagina.py): prova a uscire dal riquadro e
// salva quello che gli è riuscito in «esiti». Il modo lo legge da «modo» (lo scrive la prova)
"use strict";
(function () {
  const CATTIVO = "__CATTIVO__";          // l'indirizzo del server «cattivo» delle prove
  const esiti = {};
  function prova(nome, f) {
    try { const v = f(); esiti[nome] = "riuscito: " + String(v).slice(0, 80); }
    catch (e) { esiti[nome] = "bloccato: " + String(e && e.name || e).slice(0, 60); }
  }
  async function provaAsync(nome, f) {
    try { const v = await f(); esiti[nome] = "riuscito: " + String(v).slice(0, 80); }
    catch (e) { esiti[nome] = "bloccato: " + String(e && e.name || e).slice(0, 60); }
  }
  async function attacchi() {
    prova("parent_document", () => window.parent.document.title);
    prova("parent_location", () => window.parent.location.href);
    prova("top_cookie", () => window.top.document.cookie);
    prova("local_storage", () => window.localStorage.getItem("calliope.schermo.token"));
    prova("session_storage", () => window.sessionStorage.length);
    prova("cookie", () => document.cookie = "x=1");
    prova("fetch_globale", () => typeof fetch === "function" ? fetch("/api/salute") && "chiamata" : (() => { throw new Error("assente"); })());
    // Un fetch preso da un riquadro figlio (about:blank): la CSP lo ferma comunque
    await provaAsync("fetch_figlio", async () => {
      const f = document.createElement("iframe");
      document.body.append(f);
      const w = f.contentWindow;
      const r = await w.fetch(CATTIVO + "/fetch");
      return r.status;
    });
    await provaAsync("xhr", () => new Promise((ok, ko) => {
      const f = document.createElement("iframe");
      document.body.append(f);
      const x = new f.contentWindow.XMLHttpRequest();
      x.onload = () => ok(x.status); x.onerror = () => ko(new Error("errore"));
      x.open("GET", CATTIVO + "/xhr"); x.send();
    }));
    await provaAsync("immagine", () => new Promise((ok, ko) => {
      const i = new Image(); i.onload = () => ok("caricata"); i.onerror = () => ko(new Error("errore"));
      i.src = CATTIVO + "/img.png";
    }));
    prova("websocket", () => { const f = document.createElement("iframe"); document.body.append(f); return new f.contentWindow.WebSocket(CATTIVO.replace("http", "ws") + "/ws"); });
    prova("webrtc", () => { const f = document.createElement("iframe"); document.body.append(f); const P = f.contentWindow.RTCPeerConnection; if (!P) throw new Error("assente"); return new P({ iceServers: [{ urls: "stun:127.0.0.2:3478" }] }); });
    prova("window_open", () => { const w = window.open(CATTIVO + "/open"); if (!w) throw new Error("negato"); return "aperta"; });
    // Messaggi falsi alla pagina, scritti a mano (non con calliope.*)
    window.parent.postMessage({ calliope: 1, tipo: "salva", id: 900, chiave: "../../segreto", valore: 1 }, "*");
    window.parent.postMessage({ calliope: 1, tipo: "azione", id: 901, nome: "casa_comando", argomenti: { comando: "apri il garage" } }, "*");
    window.parent.postMessage({ calliope: 1, tipo: "comanda_tutto", id: 902 }, "*");
    window.parent.postMessage({ calliope: 2, tipo: "salva", chiave: "x", valore: 1 }, "*");
    window.parent.postMessage("{\"calliope\":1}", "*");
    await provaAsync("salva_trasversale", () => calliope.salva("../../x", 1));
    await provaAsync("azione_non_dichiarata", () => calliope.azione("casa_comando", { comando: "apri il garage" }));
    await provaAsync("frase", () => calliope.di("Ciao dal gioco"));
    await calliope.salva("esiti", esiti);
    calliope.fine("attacchi");
  }
  calliope.quandoPronto(async () => {
    let modo = null;
    try { modo = await calliope.leggi("modo"); } catch (e) { /* niente */ }
    if (modo === "naviga") { location.href = CATTIVO + "/naviga"; return; }
    if (modo === "blocca") { calliope.salva("prima_del_blocco", true).then(() => { for (;;) { /* ciclo infinito */ } }); return; }
    if (modo === "inonda") { for (let i = 0; i < 500; i++) calliope.manda({ i }); return; }
    if (modo === "attacchi") await attacchi();
  });
})();
