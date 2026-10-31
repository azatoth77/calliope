// Bilancia la reazione (libreria dello Studio, 31/10, issue #297, parte 2; percorso): in ogni
// reazione manca un coefficiente stechiometrico. Prima la previsione (da 1 a 4), poi la verifica:
// gli atomi dell'elemento che conta, a sinistra e a destra, con il coefficiente scelto. Se è
// sbagliato un secondo tentativo con un aiuto, dopo il secondo errore la soluzione. Punti: 2 al
// primo tentativo, 1 al secondo. Logica pura: pagina, pulsanti e voce sono del motore di
// Calliope. I dati li controlla la prova di verità (prove/prova_studio_miniapp.py).
//
// Forma di DATI:
//   DATI.reazioni: elenco di { sinistra, destra, giusto }
//     sinistra, destra: elenchi di termini [coefficiente, formula]; il coefficiente è un numero
//       intero (1 compreso) oppure null per quello che manca (uno solo in tutta la reazione);
//       la formula è scritta con le cifre normali e senza parentesi («H2O», «CH4», «NaCl»)
//     giusto: il coefficiente mancante (da 1 a 4)
//   DATI.punti_primo, DATI.punti_secondo: i punti al primo e al secondo tentativo
// Gli atomi li conta la logica (atomi, conta): l'elemento che conta è il primo elemento della
// formula mancante che, dal suo lato, non compare in altri termini (elementoChiave).
"use strict";

const DATI = {
  reazioni: [
    { sinistra: [[2, "H2"], [null, "O2"]], destra: [[2, "H2O"]], giusto: 1 },
    { sinistra: [[1, "N2"], [null, "H2"]], destra: [[2, "NH3"]], giusto: 3 },
    { sinistra: [[1, "CH4"], [null, "O2"]], destra: [[1, "CO2"], [2, "H2O"]], giusto: 2 },
    { sinistra: [[null, "Na"], [1, "O2"]], destra: [[2, "Na2O"]], giusto: 4 },
  ],
  punti_primo: 2,
  punti_secondo: 1,
};

// Gli atomi di una formula senza parentesi: «CH4» → { C: 1, H: 4 }
function atomi(formula) {
  const out = {};
  const re = /([A-Z][a-z]?)(\d*)/g;
  let m, letto = "";
  while ((m = re.exec(formula)) !== null) {
    if (!m[0]) { re.lastIndex++; continue; }
    out[m[1]] = (out[m[1]] || 0) + (m[2] ? parseInt(m[2], 10) : 1);
    letto += m[0];
  }
  if (letto !== formula) throw new Error("formula non valida: " + formula);
  return out;
}

// Dove sta il termine mancante: { lato: "sinistra" | "destra", i }
function mancante(r) {
  for (const lato of ["sinistra", "destra"]) {
    const i = r[lato].findIndex((t) => t[0] === null);
    if (i >= 0) return { lato, i };
  }
  throw new Error("reazione senza coefficiente mancante");
}

// Gli atomi di un elemento su un lato, con il coefficiente mancante uguale a `c`
function conta(r, lato, elemento, c) {
  return r[lato].reduce((s, [k, f]) => s + (k === null ? c : k) * (atomi(f)[elemento] || 0), 0);
}

// L'elemento che conta: il primo della formula mancante che dal suo lato sta solo lì
function elementoChiave(r) {
  const { lato, i } = mancante(r);
  const f = r[lato][i][1];
  for (const el of Object.keys(atomi(f))) {
    if (r[lato].every(([, g], j) => j === i || !atomi(g)[el])) return el;
  }
  return Object.keys(atomi(f))[0];
}

// L'equazione scritta: il coefficiente 1 non si scrive, quello mancante è «?» (o `c`)
function equazione(r, c) {
  const termine = ([k, f]) => {
    const v = k === null ? (c === undefined ? "?" : c) : k;
    return v === 1 ? f : `${v} ${f}`;
  };
  return r.sinistra.map(termine).join(" + ") + " → " + r.destra.map(termine).join(" + ");
}

// La riga della verifica: «H: 4 a sinistra, 4 a destra»
function rigaConto(r, c) {
  const el = elementoChiave(r);
  return `${el}: ${conta(r, "sinistra", el, c)} a sinistra, ${conta(r, "destra", el, c)} a destra`;
}

// L'aiuto del secondo tentativo: quanti atomi dall'altra parte, quanti in ogni formula
// I pedici delle formule per lo schermo: «H2O» → «H₂O» (le cifre dopo una lettera o una parentesi)
const PEDICI = "₀₁₂₃₄₅₆₇₈₉";
function pedici(testo) {
  return String(testo).replace(/([A-Za-z)])(\d+)/g, (_, a, n) => a + n.split("").map((c) => PEDICI[+c]).join(""));
}

function aiuto(r) {
  const { lato, i } = mancante(r);
  const altro = lato === "sinistra" ? "destra" : "sinistra";
  const el = elementoChiave(r);
  const f = r[lato][i][1];
  const n = conta(r, altro, el, 0);
  return `Aiuto: a ${altro} ci sono ${n} atomi di ${el}, e ogni ${f} ne ha ${atomi(f)[el]}. Il coefficiente 1 non si scrive.`;
}

const N = DATI.reazioni.length;
const MASSIMO = N * DATI.punti_primo;

function chiudi(d) {
  return `Hai fatto ${d.punti} punti su ${MASSIMO}.`;
}

const GIOCO = {
  nuovaPartita() { return { passo: 0, tentativo: 1, scelto: null, stato: null, punti: 0 }; },
  attivi: {
    verifica: (d) => (d.stato === "riprova" ? { riprova: true, prossima: false, finito: true }
                                             : { riprova: false, prossima: true, finito: true }),
  },
  mosse: {
    domanda: {
      coeff(d, { valore }) {
        const r = DATI.reazioni[d.passo];
        const c = Number(valore);
        const giusto = c === r.giusto;
        let stato, punti = 0;
        if (giusto) {
          stato = "giusto";
          punti = d.tentativo === 1 ? DATI.punti_primo : DATI.punti_secondo;
        } else {
          stato = d.tentativo === 1 ? "riprova" : "soluzione";
        }
        return { dati: { ...d, scelto: c, stato, punti: d.punti + punti }, punti, fase: "verifica" };
      },
      finito: (d) => ({ dati: d, esito: chiudi(d), dopo: "fine" }),
    },
    verifica: {
      riprova: (d) => ({ dati: { ...d, tentativo: 2, scelto: null, stato: null }, fase: "domanda" }),
      prossima(d) {
        if (d.passo + 1 >= N) return { dati: d, esito: `Reazioni finite! ${chiudi(d)}`, dopo: "fine" };
        return { dati: { ...d, passo: d.passo + 1, tentativo: 1, scelto: null, stato: null },
                 fase: "domanda" };
      },
      finito: (d) => ({ dati: d, esito: chiudi(d), dopo: "fine" }),
    },
  },
  // Sullo schermo le formule coi pedici (H₂O); l'esito, che Calliope può dire, resta in testo
  // semplice (revisione della PR #366)
  vista: {
    domanda: (d) => {
      const r = DATI.reazioni[d.passo];
      return {
        titolo: `Reazione ${d.passo + 1} di ${N}`,
        sottotitolo: pedici(equazione(r)),
        testo: pedici("Quale coefficiente manca?" + (d.tentativo === 2 ? " " + aiuto(r) : "")),
      };
    },
    verifica: (d) => {
      const r = DATI.reazioni[d.passo];
      if (d.stato === "giusto") {
        return { titolo: "Giusto!", sottotitolo: pedici(equazione(r, r.giusto)),
                 testo: pedici(`Con ${r.giusto}: ${rigaConto(r, r.giusto)}. La reazione è bilanciata.`) };
      }
      if (d.stato === "riprova") {
        return { titolo: "Non torna", sottotitolo: pedici(equazione(r, d.scelto)),
                 testo: pedici(`Con ${d.scelto}: ${rigaConto(r, d.scelto)}. Riprova.`) };
      }
      return { titolo: "La soluzione", sottotitolo: pedici(equazione(r, r.giusto)),
               testo: pedici(`Con ${d.scelto}: ${rigaConto(r, d.scelto)}. Serve ${r.giusto}: ${rigaConto(r, r.giusto)}.`) };
    },
  },
};

if (typeof module !== "undefined") {
  module.exports = { GIOCO, DATI, atomi, conta, mancante, elementoChiave, equazione, rigaConto, aiuto, pedici };
}
