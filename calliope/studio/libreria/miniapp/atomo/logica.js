// Costruisci l'atomo (libreria dello Studio, 31/10, issue #297, parte 2; da esplorare): si
// aggiunge o si toglie un protone e si vede quale elemento diventa, con i neutroni del suo
// isotopo più comune e gli elettroni livello per livello (la regola 2, 8, 8, 2 dei primi venti
// elementi). Logica pura: pagina, pulsanti e voce sono del motore di Calliope. I dati li
// controlla la prova di verità (prove/prova_studio_miniapp.py).
"use strict";

// Z → [simbolo, nome, numero di massa dell'isotopo più comune]
const DATI = {
  elementi: [
    ["H", "Idrogeno", 1], ["He", "Elio", 4], ["Li", "Litio", 7], ["Be", "Berillio", 9],
    ["B", "Boro", 11], ["C", "Carbonio", 12], ["N", "Azoto", 14], ["O", "Ossigeno", 16],
    ["F", "Fluoro", 19], ["Ne", "Neon", 20], ["Na", "Sodio", 23], ["Mg", "Magnesio", 24],
    ["Al", "Alluminio", 27], ["Si", "Silicio", 28], ["P", "Fosforo", 31], ["S", "Zolfo", 32],
    ["Cl", "Cloro", 35], ["Ar", "Argon", 40], ["K", "Potassio", 39], ["Ca", "Calcio", 40],
  ],
  capienza: [2, 8, 8, 2],
};

function livelli(z) {
  const out = [];
  let resta = z;
  for (const cap of DATI.capienza) {
    if (resta <= 0) break;
    out.push(Math.min(cap, resta));
    resta -= cap;
  }
  return out;
}

const ORDINALI = ["primo", "secondo", "terzo", "quarto"];

function descrivi(z) {
  const [simbolo, nome, a] = DATI.elementi[z - 1];
  const lv = livelli(z);
  return {
    simbolo, nome, a, neutroni: a - z, livelli: lv,
    testo: `Nel nucleo ${z} ${z === 1 ? "protone" : "protoni"} e ${a - z} ${a - z === 1 ? "neutrone" : "neutroni"}. ` +
      `Intorno ${z} ${z === 1 ? "elettrone" : "elettroni"}: ` +
      lv.map((n, i) => `${n} nel ${ORDINALI[i]} livello`).join(", ") + ".",
  };
}

const GIOCO = {
  nuovaPartita() { return { z: 1, visti: [1] }; },
  attivi: {
    atomo: (d) => {
      const a = { finito: true };
      if (d.z < DATI.elementi.length) a.piu = true;
      if (d.z > 1) a.meno = true;
      return a;
    },
  },
  mosse: {
    atomo: {
      piu: (d) => ({ dati: { ...d, z: d.z + 1, visti: d.visti.includes(d.z + 1) ? d.visti : [...d.visti, d.z + 1] } }),
      meno: (d) => ({ dati: { ...d, z: d.z - 1, visti: d.visti.includes(d.z - 1) ? d.visti : [...d.visti, d.z - 1] } }),
      finito: (d) => ({ dati: d, punti: d.visti.length,
        esito: `Hai visto ${d.visti.length} ${d.visti.length === 1 ? "elemento" : "elementi"} diversi.`,
        dopo: "fine" }),
    },
  },
  vista: {
    atomo: (d) => {
      const x = descrivi(d.z);
      return { titolo: `${x.nome} (${x.simbolo})`, sottotitolo: `Z = ${d.z}, A = ${x.a}`, testo: x.testo };
    },
  },
};

if (typeof module !== "undefined") module.exports = { GIOCO, DATI, livelli, descrivi };
