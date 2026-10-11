// Apri le porte (prove dei comandi a voce, 11/10): tre porte, una nasconde il premio
"use strict";
const PORTE = ["uno", "due", "tre"];

function nuovaPartita(premio) {
  return { aperte: [], premio: PORTE.includes(premio) ? premio : "tre", finita: false };
}

function apri(stato, porta) {
  if (stato.finita || !PORTE.includes(porta) || stato.aperte.includes(porta)) return stato;
  const aperte = stato.aperte.concat([porta]);
  return { ...stato, aperte, finita: porta === stato.premio };
}

// I comandi che valgono adesso: le porte ancora chiuse e «ricomincia»
function comandiAdesso(stato) {
  if (stato.finita) return ["ricomincia"];
  return PORTE.filter((p) => !stato.aperte.includes(p)).concat(["ricomincia"]);
}

if (typeof module !== "undefined") module.exports = { nuovaPartita, apri, comandiAdesso, PORTE };
