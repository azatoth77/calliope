// Tris: le regole, senza DOM (si provano con node:test in logica.test.js)
"use strict";

const LINEE = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6]];

function nuovaPartita() {
  return { celle: Array(9).fill(""), turno: "X", vincitore: "", finita: false };
}

function vincitore(celle) {
  for (const [a, b, c] of LINEE) {
    if (celle[a] && celle[a] === celle[b] && celle[a] === celle[c]) return celle[a];
  }
  return "";
}

function mossa(stato, i) {
  if (stato.finita || !Number.isInteger(i) || i < 0 || i > 8 || stato.celle[i]) return stato;
  const celle = stato.celle.slice();
  celle[i] = stato.turno;
  const v = vincitore(celle);
  const piena = celle.every((x) => x);
  return { celle, turno: stato.turno === "X" ? "O" : "X", vincitore: v,
           finita: !!v || piena };
}

// Il computer: vince se può, altrimenti blocca, altrimenti il centro, poi la prima libera
function mossaComputer(stato) {
  const libere = stato.celle.map((x, i) => (x ? -1 : i)).filter((i) => i >= 0);
  const io = stato.turno, tu = io === "X" ? "O" : "X";
  for (const segno of [io, tu]) {
    for (const i of libere) {
      const c = stato.celle.slice();
      c[i] = segno;
      if (vincitore(c) === segno) return i;
    }
  }
  if (libere.includes(4)) return 4;
  return libere.length ? libere[0] : -1;
}

if (typeof module !== "undefined") module.exports = { nuovaPartita, vincitore, mossa, mossaComputer };
