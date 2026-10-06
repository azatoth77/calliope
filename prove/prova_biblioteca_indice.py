import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dell'indice SQLite FTS5 della biblioteca (calliope/biblioteca_indice.py;
01/10/2026), su file ZIM minuscoli costruiti qui (prove/zim_finto.py).

Verifica: costruzione (in un processo e con più processi, stesso risultato), ricerca
full-text con le radici e gli alias dei redirect, parola tolta quando non trova nulla,
accenti, suggerimenti sui titoli con il prefisso, la biblioteca intera sopra l'indice e senza
(ricerca ridotta); validità dell'indice: mancante, a metà, versione o firma delle radici
diversa, uuid o dimensione dello ZIM diversi, file illeggibile; annullo (anche del processo
lanciato dall'installatore) senza file a metà; file che non è uno ZIM; riga di comando.
"""

import shutil
import sqlite3
import subprocess
import tempfile
import threading
from pathlib import Path

from calliope import biblioteca_indice as bi
from calliope.config import Config
from calliope.zim import ZimError
from prove.zim_finto import REDIRECT_VOCI, VOCI, crea_zim, mini_wikipedia

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


TMP = Path(tempfile.mkdtemp(prefix="calliope-indice-"))
RADICE = Path(__file__).resolve().parent.parent
zim = TMP / "wikipedia_it_all_mini_2026-08.zim"
zim.write_bytes(mini_wikipedia(uuid=b"A" * 16))
idx = bi.percorso_indice(zim)

verifica("indice mancante", bi.stato_indice(zim)[0] == "mancante" and bi.apri(zim) is None)
avanz = []
stats = bi.costruisci(zim, processi=1, avanz=lambda n, t: avanz.append((n, t)))
verifica("costruito: voci HTML, titoli e redirect contati, avanzamento fino in fondo",
         stats["voci"] == len(VOCI) and stats["titoli"] == len(VOCI) + len(REDIRECT_VOCI)
         and stats["redirect"] == len(REDIRECT_VOCI) and avanz[-1] == (len(VOCI), len(VOCI)),
         str(stats))
verifica("percorso: <cartella dello ZIM>/indici/<nome>.fts.sqlite, niente .tmp",
         idx == TMP / "indici" / "wikipedia_it_all_mini_2026-08.fts.sqlite" and idx.is_file()
         and not list((TMP / "indici").glob("*.tmp")))
verifica("indice valido", bi.stato_indice(zim) == ("ok", "") and bi.pronto(zim))

ind = bi.apri(zim)
from calliope.zim import ZimFile  # noqa: E402
z = ZimFile(zim)


def paths(rowids):
    return [z.dirent(r).path for r in rowids]


verifica("full-text con le radici: «scoperta» trova «scoperto»",
         paths(ind.fulltext(["scoperta", "penicillina"], 3)) == ["Penicillina"])
verifica("full-text in AND: se non trova nulla toglie la parola più corta",
         paths(ind.fulltext(["xyz", "penicillina"], 3)) == ["Penicillina"])
verifica("alias: il titolo di un redirect trova la voce di destinazione",
         paths(ind.fulltext(["sovrano", "ghiacci"], 3)) == ["Monte_Bianco"])
verifica("accenti: «citta» trova «Città di Castello»",
         paths(ind.fulltext(["citta", "castello"], 3)) == ["Città_di_Castello"])
verifica("vulcani/vulcano: stessa radice, più voci per bm25",
         set(paths(ind.fulltext(["vulcani"], 5))) == {"Vulcano", "Etna"})
verifica("niente risultati: lista vuota", ind.fulltext(["qwertyuiop"], 3) == [])
rows = ind.titoli("monte bia")
verifica("suggerimenti: l'ultima parola come prefisso",
         [z.dirent(r).path for r, _ in rows][:1] in (["Monte_Bianco"], ["Bianco"]), str(rows))
z.close()
ind.close()

# ── la biblioteca sopra l'indice, e senza ──
from calliope.biblioteca import Biblioteca  # noqa: E402
cfg = Config()
cfg.biblioteca_mini = str(zim)
cfg.biblioteca_completa = cfg.biblioteca_ragazzi = cfg.biblioteca_dizionario = None
bib = Biblioteca(cfg)
a = bib.archivi[0]
verifica("archivio con l'indice", a.indice is not None)
verifica("suggerimenti: prima il titolo identico («Po» prima di «Po (fiume)»)",
         a.suggest("po", 3)[:1] == ["Fiume_Po"], str(a.suggest("po", 3)))
p = bib.cerca("Quanto è alto il Monte Bianco?")
verifica("cerca: l'altezza del Monte Bianco", p and "4805" in p[0].testo
         and p[0].titolo == "Monte Bianco", str(p[:1]))
p = bib.cerca("Chi scoprì l'antibiotico dalla muffa?")
verifica("cerca: una voce trovata solo per parole (full-text)",
         any("Fleming" in x.testo for x in p), str([x.titolo for x in p]))
bib.close()
shutil.move(idx, TMP / "da_parte.sqlite")
bib = Biblioteca(cfg)
a = bib.archivi[0]
verifica("senza indice: si apre lo stesso, ricerca ridotta", a.indice is None
         and a.fulltext(["penicillina"], 3) == [])
verifica("senza indice: suggerimenti dal prefisso del titolo", a.suggest("monte", 3)
         == ["Monte_Bianco", "Bianco"], str(a.suggest("monte", 3)))
p = bib.cerca("Quanto è alto il Monte Bianco?")
verifica("senza indice: il titolo esatto basta per il Monte Bianco", p and "4805" in p[0].testo)
p = bib.cerca("Chi scoprì l'antibiotico dalla muffa?")
verifica("senza indice: la voce trovata solo per parole non c'è",
         not any("Fleming" in x.testo for x in p))
bib.close()
shutil.move(TMP / "da_parte.sqlite", idx)

# ── fonte in più a richiesta: Wikiquote per le citazioni (01/10) ──
from prove.zim_finto import pagina  # noqa: E402
wq = TMP / "wikiquote_it_all_nopic_2026-07.zim"
wq.write_bytes(crea_zim([("Albert_Einstein", "Albert Einstein", pagina(
    "Albert Einstein",
    "Albert Einstein (1879 – 1955), fisico tedesco naturalizzato statunitense.",
    "Albert Einstein, Come io vedo il mondo, traduzione di Mario Rossi, Newton Compton, 1975.",
    "Einstein era un genio della fisica e anche un buon violinista. (Niels Bohr)",
    "La fantasia è più importante della conoscenza, perché la conoscenza è limitata.",
    "Due cose sono infinite: l'universo e la stupidità umana, ma riguardo l'universo ho "
    "ancora dei dubbi."))]))
(TMP / (wq.name + ".verificato")).write_text("x", encoding="utf-8")
bib = Biblioteca(cfg)
verifica("Wikiquote senza indice: non si apre", not bib.citazioni and not bib.extra)
bib.close()
bi.costruisci(wq, processi=1)
bib = Biblioteca(cfg)
verifica("Wikiquote con l'indice: aperta, per le citazioni", bib.citazioni
         and bib.richieste("Dimmi una citazione di Einstein") == {"citazioni"}
         and bib.richieste("Quanto è alto il Monte Bianco?") == set())
p = bib.cerca("Dimmi una citazione di Albert Einstein")
verifica("«una citazione di Einstein»: una sua frase, non la fonte bibliografica né una "
         "frase su di lui", p and p[0].fonte == "Wikiquote" and "fantasia" in p[0].testo
         and not any("Newton Compton" in x.testo or "Bohr" in x.testo for x in p),
         str([(x.fonte, x.testo[:40]) for x in p]))
p = bib.cerca("Chi ha detto che l'universo e la stupidità umana sono infinite?")
verifica("«chi ha detto…»: la frase giusta, con l'autore nel titolo", p and p[0].fonte ==
         "Wikiquote" and "stupidità" in p[0].testo and p[0].titolo == "Albert Einstein",
         str([(x.fonte, x.titolo, x.testo[:40]) for x in p]))
p = bib.cerca("Quanto è alto il Monte Bianco?")
verifica("domanda normale: Wikiquote non c'entra", p and all(x.fonte != "Wikiquote" for x in p))
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
reg = build_registry(biblioteca=True, citazioni=True)
verifica("tool: con Wikiquote la descrizione nomina le citazioni",
         "citazioni" in reg.get("biblioteca_cerca").description
         and "citazioni" not in build_registry(biblioteca=True).get("biblioteca_cerca")
         .description)
bib.close()
cfg.biblioteca_fonti_extra = []
bib = Biblioteca(cfg)
verifica("Wikiquote spenta in biblioteca_fonti_extra: non si apre", not bib.extra)
bib.close()


# ── validità ──
def meta(sql):
    con = sqlite3.connect(idx)
    con.execute(sql)
    con.commit()
    con.close()


meta("DELETE FROM meta WHERE chiave='completo'")
verifica("senza «completo=1» → incompleto, non si apre", bi.stato_indice(zim)[0] == "incompleto"
         and bi.apri(zim) is None)
meta("INSERT INTO meta VALUES ('completo', '1')")
meta("UPDATE meta SET valore='0' WHERE chiave='versione'")
verifica("versione dell'estrattore diversa → versione", bi.stato_indice(zim)[0] == "versione")
meta(f"UPDATE meta SET valore='{bi.VERSIONE}' WHERE chiave='versione'")
meta("UPDATE meta SET valore='diversa' WHERE chiave='firma_radici'")
verifica("radici (biblioteca._stem) cambiate → versione", bi.stato_indice(zim)[0] == "versione")
meta(f"UPDATE meta SET valore='{bi.firma_radici()}' WHERE chiave='firma_radici'")
verifica("rimesso a posto → ok", bi.pronto(zim))
dati_ok = zim.read_bytes()
zim.write_bytes(mini_wikipedia(uuid=b"B" * 16))
verifica("stesso nome, ZIM diverso (uuid) → diverso, non si apre",
         bi.stato_indice(zim)[0] == "diverso" and bi.apri(zim) is None)
zim.write_bytes(dati_ok + b"\0")
verifica("dimensione dello ZIM diversa → diverso", bi.stato_indice(zim)[0] == "diverso")
zim.write_bytes(dati_ok)
salva = idx.read_bytes()
idx.write_bytes(b"non sono un database" * 50)
verifica("indice illeggibile → illeggibile", bi.stato_indice(zim)[0] == "illeggibile")
idx.write_bytes(salva)
verifica("ok di nuovo", bi.pronto(zim))

# ── annullo e errori: niente file a metà ──
altro = TMP / "vikidia_it_all_nopic_2026-09.zim"
altro.write_bytes(crea_zim(VOCI * 1, per_cluster=1))
stop = threading.Event()
stop.set()
try:
    bi.costruisci(altro, processi=1, cancel=stop)
    got = "costruito"
except bi.IndiceAnnullato:
    got = "annullato"
verifica("annullo: IndiceAnnullato, niente indice né .tmp", got == "annullato"
         and not bi.percorso_indice(altro).exists()
         and not list((TMP / "indici").glob("*.tmp")), got)
finto = TMP / "finto_2026-01.zim"
finto.write_bytes(b"non sono uno zim" * 100)
try:
    bi.costruisci(finto, processi=1)
    got = "costruito"
except ZimError as e:
    got = f"ZimError: {e}"
verifica("file che non è uno ZIM: ZimError, niente .tmp", got.startswith("ZimError")
         and not list((TMP / "indici").glob("*.tmp")), got)

# ── più processi: stesso indice ──
grande = TMP / "grande_2026-01.zim"
voci = [(f"Voce_{i}", f"Voce {i}", f"<html><body><p>Testo della voce numero {i} sul tema "
         f"{'alfa' if i % 2 else 'beta'} e su altro ancora.</p></body></html>")
        for i in range(40)]
grande.write_bytes(crea_zim(voci, per_cluster=3, compressioni=("zstd", "xz")))
s1 = bi.costruisci(grande, processi=1)
ind = bi.apri(grande)
r1 = sorted(ind.fulltext(["alfa"], 50))
ind.close()
# Con più processi da riga di comando: su Windows i processi figli («spawn») rieseguono il
# modulo principale, e questo script non è protetto da `if __name__ == "__main__"`
env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(RADICE))
r = subprocess.run([sys.executable, "-m", "calliope.biblioteca_indice", str(grande),
                    "--processi", "2", "--forza", "--avanzamento"], capture_output=True,
                   text=True, encoding="utf-8", env=env, cwd=TMP, timeout=120)
import json  # noqa: E402
s2 = next((json.loads(x[6:]) for x in r.stdout.splitlines() if x.startswith("FATTO ")),
          {"voci": None, "errore": r.stdout + r.stderr})
ind = bi.apri(grande)
r2 = sorted(ind.fulltext(["alfa"], 50))
ind.close()
verifica("con 2 processi: stesse voci e stessi risultati", s1["voci"] == s2["voci"] == 40
         and s2["processi"] == 2 and r1 == r2 and len(r1) == 20,
         f"{s1['voci']} {s2} {len(r1)} {len(r2)}")

# ── processo lanciato dall'installatore: avanzamento e annullo ──
from calliope.installa import Installazioni  # noqa: E402
from calliope.installa.scarica import Annullato  # noqa: E402
cfg.biblioteca_indice_processi = 1
inst = Installazioni(cfg, log=lambda m: None)
bi.percorso_indice(grande).unlink()
seen = []
inst._indice_processo(grande, threading.Event(), lambda n, t: seen.append((n, t)))
verifica("installatore: indice in un processo a parte, con l'avanzamento",
         bi.pronto(grande) and seen and seen[-1] == (40, 40), str(seen[-3:]))
bi.percorso_indice(grande).unlink()
stop = threading.Event()
stop.set()
try:
    inst._indice_processo(grande, stop, lambda n, t: None)
    got = "finito"
except Annullato:
    got = "annullato"
verifica("installatore: annullo → processo fermato, niente .tmp",
         got == "annullato" and not list((TMP / "indici").glob("*.tmp")), got)

# ── riga di comando ──
r = subprocess.run([sys.executable, "-m", "calliope.biblioteca_indice", str(zim), "--stato"],
                   capture_output=True, text=True, encoding="utf-8", env=env, cwd=TMP)
verifica("python -m calliope.biblioteca_indice <file> --stato", r.returncode == 0
         and f"{zim.name}: ok" in r.stdout, r.stdout + r.stderr)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
