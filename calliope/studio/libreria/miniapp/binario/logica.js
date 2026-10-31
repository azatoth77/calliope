// Binario e decimale (libreria dello Studio, 31/10, issue #297, parte 2; quiz): prima qualche
// esempio passo passo (da decimale a binario con le divisioni per 2 e i resti letti dal basso,
// poi la verifica da binario a decimale con i pesi), poi sei domande a scelta fra tre risposte,
// metà da binario a decimale e metà da decimale a binario. Un punto per risposta giusta; l'esito
// dice giusto o sbagliato e perché (la somma dei pesi, e se si riconosce l'errore tipico: le cifre
// lette al contrario o un peso dimenticato). Logica pura: pagina, pulsanti e voce sono del motore
// di Calliope. I dati li controlla la prova di verità (prove/prova_studio_miniapp.py).
//
// Forma di DATI:
//   { esempi: [{ decimale: 13 }, …],          // i numeri degli esempi, in ordine (poi si ricomincia)
//     domande: [{ verso: "bd" | "db",          // "bd": da binario a decimale; "db": da decimale a binario
//                 numero,                      // il numero della domanda come si mostra: con "bd"
//                                              //   un testo di 0 e 1 ("1011"), con "db" un intero (13)
//                 opzioni: [3 testi],          // le risposte A, B, C: decimali con "bd", binari con "db"
//                 giusta: 0 | 1 | 2 }, …] }    // l'indice della risposta giusta
// Tutto ciò che si mostra (divisioni, resti, pesi, somme) è calcolato qui da questi numeri.
"use strict";

const DATI = {
  esempi: [{ decimale: 13 }, { decimale: 22 }, { decimale: 37 }, { decimale: 50 }],
  domande: [
    { verso: "bd", numero: "1011", opzioni: ["13", "11", "9"], giusta: 1 },
    { verso: "db", numero: 13, opzioni: ["1011", "1001", "1101"], giusta: 2 },
    { verso: "bd", numero: "10110", opzioni: ["22", "13", "18"], giusta: 0 },
    { verso: "db", numero: 19, opzioni: ["11001", "10011", "10001"], giusta: 1 },
    { verso: "bd", numero: "110010", opzioni: ["34", "19", "50"], giusta: 2 },
    { verso: "db", numero: 25, opzioni: ["11001", "10001", "10011"], giusta: 0 },
  ],
};

const LETTERE = ["a", "b", "c"];

// Le divisioni per 2 di d: [{ dividendo, quoziente, resto }] fino al quoziente 0
function divisioni(d) {
  const out = [];
  let q = d;
  while (q > 0) {
    out.push({ dividendo: q, quoziente: Math.floor(q / 2), resto: q % 2 });
    q = Math.floor(q / 2);
  }
  return out;
}

// Il binario di d: i resti letti dal basso (dall'ultima divisione alla prima)
function binario(d) {
  return d === 0 ? "0" : divisioni(d).map((x) => x.resto).reverse().join("");
}

// I pesi delle cifre 1 di un binario, dal più grande: "1101" → [8, 4, 1]
function pesiAccesi(b) {
  const out = [];
  for (let i = 0; i < b.length; i++) if (b[i] === "1") out.push(2 ** (b.length - 1 - i));
  return out;
}

// Il valore decimale di un binario: la somma dei pesi delle cifre 1
function decimale(b) { return pesiAccesi(b).reduce((s, p) => s + p, 0); }

// «1101 = 8 + 4 + 1 = 13»
function conPesi(b) {
  const p = pesiAccesi(b), v = decimale(b);
  return p.length > 1 ? `${b} = ${p.join(" + ")} = ${v}` : `${b} = ${v}`;
}

// I passi di un esempio: una divisione per passo, poi la lettura dei resti e la verifica
function passi(d) { return divisioni(d).length + 1; }

function rovescia(s) { return s.split("").reverse().join(""); }

// Il perché di una risposta sbagliata, se si riconosce l'errore tipico ("" se no)
function perche(q, scelta) {
  const giusta = q.opzioni[q.giusta];
  if (q.verso === "db") {
    if (scelta === rovescia(giusta)) return "Hai letto i resti dall'alto: vanno letti dal basso.";
    const manca = decimale(giusta) - decimale(scelta);
    if (pesiAccesi(giusta).includes(manca)) return `Manca il peso ${manca}.`;
    return "";
  }
  const b = String(q.numero), v = Number(scelta);
  if (rovescia(b) !== b && v === decimale(rovescia(b))) return "Hai letto le cifre al contrario.";
  const manca = decimale(b) - v;
  if (pesiAccesi(b).includes(manca)) return `Hai dimenticato il peso ${manca}.`;
  return "";
}

// La spiegazione della risposta giusta, con i pesi
function spiega(q) {
  return q.verso === "bd" ? conPesi(String(q.numero)) : conPesi(binario(q.numero));
}

const GIOCO = {
  nuovaPartita() { return { es: 0, passo: 0, visti: 1, q: 0 }; },
  attivi: {
    esempio: (d) => {
      const a = { altro: true, domande: true, finito: true };
      if (d.passo < passi(DATI.esempi[d.es].decimale) - 1) a.passo = true;
      return a;
    },
  },
  mosse: {
    esempio: {
      passo: (d) => ({ dati: { ...d, passo: d.passo + 1 } }),
      altro: (d) => ({ dati: { ...d, es: (d.es + 1) % DATI.esempi.length, passo: 0, visti: d.visti + 1 } }),
      domande: (d) => ({ dati: { ...d, q: 0 }, fase: "domanda" }),
      finito: (d) => ({ dati: d, esito: `Hai visto ${d.visti} ${d.visti === 1 ? "esempio" : "esempi"}.`, dopo: "fine" }),
    },
    domanda: {
      risposta: (d, { valore }) => {
        const q = DATI.domande[d.q];
        const i = LETTERE.indexOf(valore);
        const ok = i === q.giusta;
        const ultima = d.q + 1 >= DATI.domande.length;
        const esito = ok ? `Giusto! ${spiega(q)}.`
          : `Sbagliato: ${spiega(q)}. ${perche(q, q.opzioni[i])}`.trim();
        return { dati: { ...d, q: d.q + 1 }, punti: ok ? 1 : 0, esito, dopo: ultima ? "fine" : "domanda" };
      },
      finito: (d) => ({ dati: d, fase: "fine" }),
    },
  },
  vista: {
    esempio: (d) => {
      const n = DATI.esempi[d.es].decimale, div = divisioni(n), b = binario(n);
      if (d.passo < div.length) {
        const x = div[d.passo];
        const resti = div.slice(0, d.passo + 1).map((y) => y.resto).join(", ");
        return { titolo: `${n} in binario`, sottotitolo: `Divido per 2: passo ${d.passo + 1} di ${div.length}`,
                 testo: `${x.dividendo} : 2 = ${x.quoziente}, resto ${x.resto}. Resti finora: ${resti}.` };
      }
      return { titolo: `${n} in binario è ${b}`, sottotitolo: "I resti letti dal basso",
               testo: `Verifica con i pesi: ${conPesi(b)}.` };
    },
    domanda: (d) => {
      const q = DATI.domande[d.q];
      const titolo = q.verso === "bd" ? `Quanto vale ${q.numero} in decimale?` : `Come si scrive ${q.numero} in binario?`;
      return { titolo, sottotitolo: `Domanda ${d.q + 1} di ${DATI.domande.length}`,
               testo: q.opzioni.map((o, i) => `${LETTERE[i].toUpperCase()}: ${o}`).join("   ") };
    },
  },
};

if (typeof module !== "undefined") {
  module.exports = { GIOCO, DATI, divisioni, binario, pesiAccesi, decimale, conPesi, passi, perche };
}
