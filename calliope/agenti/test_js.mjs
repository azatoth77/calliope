// I test JavaScript della sandbox (05/10/2026, calliope/agenti/sandbox.py, modo «test_js»):
// montato in sola lettura nel container di Node. Argomenti: i file .js della cartella. Prima
// la sintassi degli script (senza eseguirli: vm.Script), poi i test (*.test.js) con node:test
// nello stesso processo. L'ultima riga è il conto, dopo il segno ricevuto sullo stdin.
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { run } from "node:test";

const segno = (readFileSync(0, "utf8").split("\n")[0] || "").trim() || "ESITO";
const scrivi = process.stdout.write.bind(process.stdout);
const file = process.argv.slice(2);
const conto = { eseguiti: 0, falliti: 0, errori: 0, saltati: 0 };
for (const f of file.filter((x) => !x.endsWith(".test.js"))) {
  try {
    new vm.Script(readFileSync(f, "utf8"), { filename: f });
  } catch (e) {
    scrivi(`errore di sintassi in ${f}: ${e.message}\n`);
    conto.errori++;
  }
}
const prove = file.filter((x) => x.endsWith(".test.js"));
if (prove.length && !conto.errori) {
  const flusso = run({ files: prove, isolation: "none", concurrency: 1, timeout: 20000 });
  flusso.on("test:pass", (e) => {
    if (e.details && e.details.type === "suite") return;
    if (e.skip || e.todo) conto.saltati++; else conto.eseguiti++;
    scrivi(`ok ${e.name}\n`);
  });
  flusso.on("test:fail", (e) => {
    if (e.details && e.details.type === "suite") return;
    conto.eseguiti++;
    conto.falliti++;
    const err = e.details && e.details.error;
    const causa = err && (err.cause || err);
    scrivi(`FALLITO ${e.name}: ${String((causa && causa.message) || causa || "").slice(0, 600)}\n`);
  });
  flusso.on("test:diagnostic", () => {});
  await new Promise((ok) => { flusso.on("end", ok); flusso.on("close", ok); flusso.resume(); });
} else if (!prove.length) {
  scrivi("nessun file di test (*.test.js)\n");
}
// La prova di fumo della scheda (05/10, fumo_js.mjs): gli script del gioco con un DOM finto e
// trecento tocchi a caso. Solo se c'è un manifesto con la «scheda»
let scheda = null;
try { scheda = JSON.parse(readFileSync("manifesto.json", "utf8")).scheda || null; } catch (e) { /* nessuno */ }
if (scheda && Array.isArray(scheda.file) && !conto.errori) {
  const { fumo } = await import(new URL("./fumo_js.mjs", import.meta.url));
  const presenti = scheda.file.filter((f) => file.includes(f));
  conto.eseguiti++;
  const errori = presenti.length === scheda.file.length
    ? await fumo(presenti, { massimo: (scheda.giocatori || {}).max || 1 })
    : ["i file della scheda non ci sono tutti: " + scheda.file.join(", ")];
  if (errori.length) {
    conto.falliti++;
    scrivi("FALLITO prova di fumo del gioco (gli script di «scheda.file» caricati con un DOM "
      + "finto semplice e trecento tocchi a caso; se l'errore è di un metodo del DOM che il finto "
      + "non conosce, scrivilo in un modo più comune): " + errori.join(" | ") + "\n");
  } else {
    scrivi("ok prova di fumo del gioco\n");
  }
}
scrivi(`${segno} ${JSON.stringify(conto)}\n`);
process.exit(0);
