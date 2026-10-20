"use strict";
// Il tris per due come programma JavaScript (20/10/2026, issue #198, caso «tris-nudo» di
// prove/manuali/banco_temperatura.py): il riferimento giusto, senza la macchina a stati dei
// giochi né il contratto. Funzioni pure: lo stato è { caselle: [9 × null | "X" | "O"] }
const FILE = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8],
              [0, 4, 8], [2, 4, 6]];

function nuovaPartita() {
  return { caselle: Array(9).fill(null) };
}

function vincitore(stato) {
  const c = stato.caselle;
  for (const [a, b, d] of FILE) {
    if (c[a] && c[a] === c[b] && c[a] === c[d]) return c[a];
  }
  return null;
}

function pareggio(stato) {
  return !vincitore(stato) && stato.caselle.every((x) => x !== null);
}

function aChiTocca(stato) {
  if (vincitore(stato) || pareggio(stato)) return null;
  const messi = stato.caselle.filter((x) => x !== null).length;
  return messi % 2 === 0 ? "X" : "O";
}

function mossa(stato, casella) {
  const chi = aChiTocca(stato);
  if (!chi) throw new Error("la partita è finita");
  if (!Number.isInteger(casella) || casella < 1 || casella > 9) {
    throw new Error(`la casella ${casella} non c'è: da 1 a 9`);
  }
  if (stato.caselle[casella - 1] !== null) throw new Error(`la casella ${casella} è occupata`);
  const caselle = stato.caselle.slice();
  caselle[casella - 1] = chi;
  return { caselle };
}

function griglia(stato) {
  const c = stato.caselle.map((x, i) => x || String(i + 1));
  return [0, 3, 6].map((i) => c.slice(i, i + 3).join(" | ")).join("\n");
}

function main() {
  let s = nuovaPartita();
  for (const n of [5, 1, 9, 3, 2, 8, 7]) {
    if (!aChiTocca(s)) break;
    s = mossa(s, n);
  }
  console.log(griglia(s));
  const v = vincitore(s);
  console.log(v ? `Vince ${v}!` : pareggio(s) ? "Pareggio." : `Tocca a ${aChiTocca(s)}.`);
}

if (require.main === module) main();
module.exports = { nuovaPartita, mossa, vincitore, pareggio, aChiTocca };
