// Accendi i bit (libreria dello Studio, 31/10, issue #297, parte 2; da esplorare): otto bit da
// accendere e spegnere; la pagina mostra il numero binario di 8 cifre e la somma dei pesi dei bit
// accesi, che è il valore decimale («00101101 = 32 + 8 + 4 + 1 = 45»). Logica pura: pagina,
// pulsanti e voce sono del motore di Calliope. I dati li controlla la prova di verità
// (prove/prova_studio_miniapp.py).
//
// Forma di DATI:
//   { bit: 8,                                   // quanti bit ha il numero
//     pesi: [1, 2, 4, 8, 16, 32, 64, 128] }     // pesi[n] = 2^n, il peso del bit n (bit 0 a destra)
// Lo stato della partita: { acceso: [8 booleani, indice = n del bit], visti: [valori decimali] }.
"use strict";

const DATI = {
  bit: 8,
  pesi: [1, 2, 4, 8, 16, 32, 64, 128],
};

// Il valore decimale: la somma dei pesi dei bit accesi
function valore(acceso) {
  let v = 0;
  for (let n = 0; n < DATI.bit; n++) if (acceso[n]) v += DATI.pesi[n];
  return v;
}

// Le 8 cifre, dal bit più alto (a sinistra) al bit 0 (a destra)
function cifre(acceso) {
  let s = "";
  for (let n = DATI.bit - 1; n >= 0; n--) s += acceso[n] ? "1" : "0";
  return s;
}

// «00101101 = 32 + 8 + 4 + 1 = 45», dal peso più grande; «00000000 = 0» se è tutto spento
function somma(acceso) {
  const pesi = [];
  for (let n = DATI.bit - 1; n >= 0; n--) if (acceso[n]) pesi.push(DATI.pesi[n]);
  const v = valore(acceso);
  if (pesi.length === 0) return `${cifre(acceso)} = 0`;
  if (pesi.length === 1) return `${cifre(acceso)} = ${v}`;
  return `${cifre(acceso)} = ${pesi.join(" + ")} = ${v}`;
}

function conVisto(visti, v) { return visti.includes(v) ? visti : [...visti, v]; }

const GIOCO = {
  nuovaPartita() { return { acceso: Array(DATI.bit).fill(false), visti: [0] }; },
  attivi: {
    bit: (d) => {
      const a = { bit: true, finito: true };
      if (d.acceso.some(Boolean)) a.spegni = true;
      if (!d.acceso.every(Boolean)) a.accendi = true;
      return a;
    },
  },
  mosse: {
    bit: {
      bit: (d, { valore: n }) => {
        const acceso = d.acceso.map((x, i) => (i === n ? !x : x));
        return { dati: { ...d, acceso, visti: conVisto(d.visti, valore(acceso)) } };
      },
      accendi: (d) => {
        const acceso = Array(DATI.bit).fill(true);
        return { dati: { ...d, acceso, visti: conVisto(d.visti, valore(acceso)) } };
      },
      spegni: (d) => ({ dati: { ...d, acceso: Array(DATI.bit).fill(false) } }),
      finito: (d) => ({ dati: d, punti: d.visti.length,
        esito: `Hai formato ${d.visti.length} ${d.visti.length === 1 ? "numero" : "numeri"} diversi.`,
        dopo: "fine" }),
    },
  },
  vista: {
    bit: (d) => {
      const pesi = [], bits = [];
      for (let n = DATI.bit - 1; n >= 0; n--) {
        pesi.push(String(DATI.pesi[n]));
        bits.push(d.acceso[n] ? { testo: "1", colore: "giallo", comando: "bit", valore: n }
                              : { testo: "0", colore: "grigio", comando: "bit", valore: n });
      }
      return { titolo: "Accendi i bit", sottotitolo: "Sopra il peso di ogni bit", testo: somma(d.acceso),
               caselle: [pesi, bits] };
    },
  },
};

if (typeof module !== "undefined") module.exports = { GIOCO, DATI, valore, cifre, somma };
