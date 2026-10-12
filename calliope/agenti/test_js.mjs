// I test JavaScript della sandbox (05/10/2026, calliope/agenti/sandbox.py, modo «test_js»):
// montato in sola lettura nel container di Node. Argomenti: i file .js della cartella. Prima
// la sintassi degli script (senza eseguirli: vm.Script), poi i test (*.test.js) con node:test
// nello stesso processo. L'ultima riga è il conto, dopo il segno ricevuto sullo stdin.
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { run } from "node:test";

const segno = (readFileSync(0, "utf8").split("\n")[0] || "").trim() || "ESITO";
const scrivi = process.stdout.write.bind(process.stdout);
// «--senza-fumo» (12/10 sera, riproduzione.py): solo i test dell'agente, senza la prova di fumo
const senzaFumo = process.argv[2] === "--senza-fumo";
const file = process.argv.slice(senzaFumo ? 3 : 2);
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
    // Dove (11/10): la prima riga dello stack in un file del lavoro, non in Node
    const dove = String((causa && causa.stack) || "").split("\n")
      .map((r) => r.match(/([^\s()\/\\]+\.js):(\d+)(?::\d+)?\)?\s*$/))
      .find((m) => m && file.some((f) => f.replace(/\\/g, "/").split("/").pop() === m[1]));
    // Il messaggio su una riga (le asserzioni di node:assert vanno a capo)
    const msg = String((causa && causa.message) || causa || "").replace(/\s+/g, " ").trim();
    scrivi(`FALLITO ${e.name}: ${msg.slice(0, 600)}` + (dove ? ` [in ${dove[1]}:${dove[2]}]` : "")
      + "\n");
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
if (scheda && Array.isArray(scheda.file) && !conto.errori && !senzaFumo) {
  const { fumo } = await import(new URL("./fumo_js.mjs", import.meta.url));
  const presenti = scheda.file.filter((f) => file.includes(f));
  conto.eseguiti++;
  const errori = presenti.length === scheda.file.length
    ? await fumo(presenti, { massimo: (scheda.giocatori || {}).max || 1,
                             comandi: (scheda.ascolta || {}).comandi || {},
                             giocatore: !!(scheda.ascolta || {}).giocatore })
    : ["i file della scheda non ci sono tutti: " + scheda.file.join(", ")];
  if (errori.length) {
    conto.falliti++;
    // Prima l'errore, poi come lavora la prova (11/10: l'agente credeva che nella prova
    // mancassero «calliope» o il contenitore, e che la prova fosse da cambiare)
    scrivi("FALLITO prova di fumo del gioco: " + errori.join(" | ") + " — la prova carica "
      + "gli script di «scheda.file» come nel riquadro (document finto con <div id=\"gioco\">, "
      + "l'oggetto calliope, timer finti), chiama quandoPronto e tocca a caso gli elementi con "
      + "un gestore (con «ascolta» manda anche comandi a voce a caso tra quelli attivi); correggi il punto indicato, non riscrivere il file. Se l'errore è di un "
      + "metodo del DOM che il finto non conosce, scrivilo in un modo più comune\n");
  } else {
    scrivi("ok prova di fumo del gioco\n");
  }
}
scrivi(`${segno} ${JSON.stringify(conto)}\n`);
process.exit(0);
