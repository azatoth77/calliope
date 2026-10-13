// Le porte del castello (prove della macchina a stati, 13/10): tre porte più una per
// giocatore; dietro ognuna un mostro (punti) o niente. Si gioca a turno; finite le porte, la fine
"use strict";
const SORPRESE = [["un drago", 3], ["un fantasma", 2], ["un pipistrello", 1], ["una ragnatela", 0]];

const GIOCO = {
  nuovaPartita({ giocatori }) {
    const n = Math.min(6, 2 + giocatori);
    const dietro = [];
    for (let i = 0; i < n; i++) dietro.push(Math.floor(Math.random() * SORPRESE.length));
    return { porte: n, dietro, aperte: [] };
  },
  attivi: {
    turno: (d) => ({ porta: chiuse(d) }),
  },
  mosse: {
    turno: {
      porta(d, { valore }) {
        const [cosa, punti] = SORPRESE[d.dietro[valore - 1]];
        const aperte = d.aperte.concat([valore]);
        const finite = aperte.length === d.porte;
        return { dati: { ...d, aperte }, punti, esito: `Dietro la porta ${valore} c'è ${cosa}!`,
                 dopo: finite ? "fine" : "turno" };
      },
    },
  },
  vista: {
    turno: (d) => ({ titolo: "Quale porta apri?", testo: `Porte chiuse: ${chiuse(d).length}` }),
  },
};

function chiuse(d) {
  const out = [];
  for (let p = 1; p <= d.porte; p++) if (!d.aperte.includes(p)) out.push(p);
  return out;
}

if (typeof module !== "undefined") module.exports = { GIOCO, chiuse };
