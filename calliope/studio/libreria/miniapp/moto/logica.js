// Moto rettilineo uniforme (libreria dello Studio, 31/10, issue #297, parte 2; percorso): un
// oggetto va a velocità costante per un certo tempo. Prima la previsione dello spazio percorso fra
// quattro risposte, poi la verifica con il conto s = v × t (e le conversioni km/h → m/s o minuti
// → secondi quando servono); se è sbagliata un secondo tentativo con un aiuto, dopo il secondo
// errore la soluzione. Punti: 2 al primo tentativo, 1 al secondo. Logica pura: pagina, pulsanti
// e voce sono del motore di Calliope. I dati li controlla la prova di verità
// (prove/prova_studio_miniapp.py).
//
// Forma di DATI:
//   DATI.passi: elenco di { cosa, v, unita_v, t, unita_t, opzioni, giusta, unita_s }
//     cosa: chi si muove («Una bici»); v: la velocità (numero) in unita_v («m/s», «cm/s»,
//     «km/h»); t: il tempo in unita_t («s», «min», «h»); opzioni: 4 numeri (le risposte A–D,
//     nell'unità unita_s: «m», «cm», «km»); giusta: l'indice (0–3) dell'opzione giusta
//   DATI.kmh_ms: 3.6 (da km/h a m/s si divide per 3,6); DATI.secondi: secondi in un'unità di tempo
//   DATI.punti_primo, DATI.punti_secondo: i punti al primo e al secondo tentativo
// Il conto lo fa la logica (risolvi): se la velocità è in km/h, il tempo non è in ore e lo spazio
// si chiede in metri, la velocità in m/s; poi il tempo nell'unità della velocità; s = v × t
// nell'unità di lunghezza della velocità, che deve essere unita_s.
"use strict";

const DATI = {
  passi: [
    { cosa: "Una bici", v: 5, unita_v: "m/s", t: 12, unita_t: "s",
      opzioni: [17, 60, 120, 600], giusta: 1, unita_s: "m" },
    { cosa: "Una tartaruga", v: 4, unita_v: "cm/s", t: 2, unita_t: "min",
      opzioni: [8, 48, 480, 4800], giusta: 2, unita_s: "cm" },
    { cosa: "Un treno", v: 108, unita_v: "km/h", t: 20, unita_t: "s",
      opzioni: [600, 2160, 60, 6000], giusta: 0, unita_s: "m" },
    { cosa: "Un'auto", v: 90, unita_v: "km/h", t: 30, unita_t: "min",
      opzioni: [2700, 3, 180, 45], giusta: 3, unita_s: "km" },
  ],
  kmh_ms: 3.6,
  secondi: { s: 1, min: 60, h: 3600 },
  punti_primo: 2,
  punti_secondo: 1,
};

const LETTERE = ["a", "b", "c", "d"];
const VELOCITA = { "m/s": ["m", "s"], "cm/s": ["cm", "s"], "km/h": ["km", "h"] };

function tondo(x) { return Math.round(x * 1e6) / 1e6; }
function numero(x) { return String(tondo(x)).replace(".", ","); }

// Il conto di un passo: { passi: [testi delle conversioni], v, uv, t, ut, s }
function risolvi(p) {
  const passi = [];
  let v = p.v, uv = p.unita_v, t = p.t, ut = p.unita_t;
  if (!VELOCITA[uv] || !(ut in DATI.secondi)) throw new Error("unità sconosciuta: " + uv + ", " + ut);
  if (uv === "km/h" && ut !== "h" && p.unita_s === "m") {
    const nuova = tondo(v / DATI.kmh_ms);
    passi.push(`${numero(v)} km/h = ${numero(v)} : ${numero(DATI.kmh_ms)} = ${numero(nuova)} m/s`);
    v = nuova; uv = "m/s";
  }
  const [lunghezza, tempo] = VELOCITA[uv];
  if (ut !== tempo) {
    const f = DATI.secondi[ut] / DATI.secondi[tempo];
    const nuovo = tondo(t * f);
    passi.push(f >= 1 ? `${numero(t)} ${ut} = ${numero(t)} × ${numero(f)} = ${numero(nuovo)} ${tempo}`
                      : `${numero(t)} ${ut} = ${numero(t)} : ${numero(1 / f)} = ${numero(nuovo)} ${tempo}`);
    t = nuovo; ut = tempo;
  }
  if (lunghezza !== p.unita_s) throw new Error(`lo spazio esce in ${lunghezza}, non in ${p.unita_s}`);
  return { passi, v, uv, t, ut, s: tondo(v * t) };
}

function conto(p) {
  const r = risolvi(p);
  return r.passi.concat([`s = ${numero(r.v)} ${r.uv} × ${numero(r.t)} ${r.ut} = ${numero(r.s)} ${p.unita_s}`]).join("; ") + ".";
}

function aiuto(p) {
  if (p.unita_v === "km/h" && p.unita_t !== "h" && p.unita_s === "m") {
    return `Aiuto: prima porta i km/h in m/s (dividi per ${numero(DATI.kmh_ms)}), poi s = v × t.`;
  }
  const tempo = VELOCITA[p.unita_v][1];
  if (p.unita_t !== tempo) {
    const [grande, piccola] = DATI.secondi[p.unita_t] > DATI.secondi[tempo] ? [p.unita_t, tempo] : [tempo, p.unita_t];
    const quante = numero(DATI.secondi[grande] / DATI.secondi[piccola]);
    return `Aiuto: prima porta il tempo in ${tempo} (1 ${grande} = ${quante} ${piccola}), poi s = v × t.`;
  }
  return "Aiuto: lo spazio è la velocità per il tempo, s = v × t.";
}

function scelte(p) {
  return p.opzioni.map((x, i) => `${LETTERE[i].toUpperCase()}) ${numero(x)} ${p.unita_s}`).join("   ");
}

const N = DATI.passi.length;
const MASSIMO = N * DATI.punti_primo;

function chiudi(d) { return `Hai fatto ${d.punti} punti su ${MASSIMO}.`; }

const GIOCO = {
  nuovaPartita() { return { passo: 0, tentativo: 1, scelta: null, stato: null, punti: 0 }; },
  attivi: {
    verifica: (d) => (d.stato === "riprova" ? { riprova: true, prossima: false, finito: true }
                                             : { riprova: false, prossima: true, finito: true }),
  },
  mosse: {
    domanda: {
      risposta(d, { valore }) {
        const p = DATI.passi[d.passo];
        const i = LETTERE.indexOf(String(valore));
        let stato, punti = 0;
        if (i === p.giusta) {
          stato = "giusto";
          punti = d.tentativo === 1 ? DATI.punti_primo : DATI.punti_secondo;
        } else {
          stato = d.tentativo === 1 ? "riprova" : "soluzione";
        }
        return { dati: { ...d, scelta: i, stato, punti: d.punti + punti }, punti, fase: "verifica" };
      },
      finito: (d) => ({ dati: d, esito: chiudi(d), dopo: "fine" }),
    },
    verifica: {
      riprova: (d) => ({ dati: { ...d, tentativo: 2, scelta: null, stato: null }, fase: "domanda" }),
      prossima(d) {
        if (d.passo + 1 >= N) return { dati: d, esito: `Percorso finito! ${chiudi(d)}`, dopo: "fine" };
        return { dati: { ...d, passo: d.passo + 1, tentativo: 1, scelta: null, stato: null },
                 fase: "domanda" };
      },
      finito: (d) => ({ dati: d, esito: chiudi(d), dopo: "fine" }),
    },
  },
  vista: {
    domanda: (d) => {
      const p = DATI.passi[d.passo];
      return {
        titolo: `Passo ${d.passo + 1} di ${N}`,
        sottotitolo: `${p.cosa} va a ${numero(p.v)} ${p.unita_v} costanti. Quanto spazio fa in ${numero(p.t)} ${p.unita_t}?`,
        testo: scelte(p) + (d.tentativo === 2 ? " " + aiuto(p) : ""),
      };
    },
    verifica: (d) => {
      const p = DATI.passi[d.passo];
      const detta = `${numero(p.opzioni[d.scelta])} ${p.unita_s}`;
      const giusta = `${LETTERE[p.giusta].toUpperCase()}) ${numero(p.opzioni[p.giusta])} ${p.unita_s}`;
      if (d.stato === "giusto") return { titolo: "Giusto!", sottotitolo: giusta, testo: conto(p) };
      if (d.stato === "riprova") return { titolo: "Non ancora", sottotitolo: `${detta} non torna.`, testo: aiuto(p) };
      return { titolo: "La soluzione", sottotitolo: `Non ${detta}, ma ${giusta}`, testo: conto(p) };
    },
  },
};

if (typeof module !== "undefined") module.exports = { GIOCO, DATI, risolvi, conto, aiuto };
