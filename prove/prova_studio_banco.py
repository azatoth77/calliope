import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Il banco dello Studio a secco (28/10, #293, revisione della PR #302): la guardia che vede un
lavoro dell'agente vivo (`lavori/in_corso.json` col `.bak`, anche fermo da più di 15 minuti o
con i file scritti in una sottocartella), il rifiuto di `--senza-guardia` con la Calliope vera
attiva, `harness.json` uguale alle costanti del banco (prompt, schema, parametri), i controlli
del codice (pagina scritta due volte, segni della lettura, controllo delle pagine con le
radici) e la verità dei materiali coerente (risposte attese che passano i criteri, argomenti
veri che danno precisione e richiamo 1). Niente rete, niente modello.
"""

import json
import tempfile
import time
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))
sys.path.insert(0, str(QUI / "manuali"))

import banco_studio as B  # noqa: E402

errori = 0


def verifica(nome, ok):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}")


class Risposta:
    def __init__(self, testo, codice=200):
        self.text, self.status_code = testo, codice


class HttpFinto:
    """vLLM libero e non in pausa."""

    def get(self, percorso, timeout=None):
        if percorso == "/metrics":
            return Risposta('vllm:num_requests_running{engine="0"} 0.0\n'
                            'vllm:num_requests_waiting{engine="0"} 0.0\n')
        return Risposta('{"is_paused": false}')


def vecchio(p: Path, secondi: float = 3600):
    t = time.time() - secondi
    os.utime(p, (t, t))


def scrivi_lavori(cartella: Path, stato: str, nome="in_corso.json", pid=None):
    f = cartella / "lavori" / nome
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"pid": os.getpid() if pid is None else pid,
                             "lavori": [{"id": "L3", "stato": stato}]}), encoding="utf-8")
    vecchio(f)
    vecchio(f.parent)
    return f


# ── la guardia dei lavori dell'agente ──
with tempfile.TemporaryDirectory() as d:
    vera = Path(d)
    g = B.Guardia(HttpFinto(), vera, log=lambda m: None)
    verifica("niente lavori, niente turni: si parte", g.motivo() is None)
    f = scrivi_lavori(vera, "in_corso")
    verifica("in_corso.json fermo da un'ora con un lavoro in corso: si aspetta",
             g.motivo() is not None and "in_corso" in g.motivo())
    scrivi_lavori(vera, "in_coda")
    verifica("un lavoro in coda: si aspetta", g.motivo() is not None)
    scrivi_lavori(vera, "fatto")
    verifica("contrario: il lavoro è finito, si parte", g.motivo() is None)
    f.write_text("{rotto", encoding="utf-8")
    vecchio(f)
    scrivi_lavori(vera, "in_corso", nome="in_corso.json.bak")
    verifica("in_corso.json rotto: vale il .bak", g.motivo() is not None)
    (vera / "lavori" / "in_corso.json.bak").unlink()
    if os.name == "posix":
        scrivi_lavori(vera, "in_corso", pid=2 ** 22 + 12345)
        verifica("contrario: il processo che l'ha scritto non c'è più", g.motivo() is None)
    f.unlink()
    # un lavoro che scrive in una sottocartella della sua sandbox: la cartella del lavoro non
    # cambia data, la sottocartella sì
    lav = vera / "lavori" / "L3-20261028-1500"
    (lav / "src").mkdir(parents=True)
    (lav / "src" / "gioco.js").write_text("x", encoding="utf-8")
    vecchio(lav)
    for p in (vera / "lavori").iterdir():
        if p != lav:
            vecchio(p)
    verifica("un file nuovo nella sottocartella della sandbox: si aspetta", g.motivo() is not None)
    vecchio(lav / "src" / "gioco.js")
    vecchio(lav / "src")
    verifica("contrario: tutto fermo da un'ora, si parte", g.motivo() is None)

    # --senza-guardia rifiutato con la Calliope vera attiva sulla stessa macchina
    reg = vera / "registro"
    reg.mkdir()
    (reg / "turni-2026-10-28.jsonl").write_text("{}\n", encoding="utf-8")
    verifica("Calliope vera attiva (un turno adesso)", B.calliope_vera_attiva(vera))
    usc = vera / "uscita"
    n = B.main(["--vera", str(vera), "--uscita", str(usc), "--senza-guardia",
                "--fasi", "risposte", "--max-richieste", "0"])
    verifica("--senza-guardia con la Calliope vera attiva: rifiutato (2)", n == 2)
    verifica("il rifiuto è nel log", "RIFIUTO" in (usc / "banco.log").read_text(encoding="utf-8"))
    vecchio(reg / "turni-2026-10-28.jsonl")
    verifica("contrario: Calliope ferma da un'ora, nessun lavoro", not B.calliope_vera_attiva(vera))

# ── harness.json uguale alle costanti del banco ──
h = json.loads((QUI / "manuali" / "studio" / "harness.json").read_text(encoding="utf-8"))
le, ar = h["lettura"], h["argomenti"]
verifica("lettura: prompt di sistema = SISTEMA_LETTORE",
         le["messaggi"][0]["content"] == B.SISTEMA_LETTORE)
verifica("lettura: istruzioni = «Trascrivi questa foto.» + REGOLE_LETTURA + FORMATO_TESTO",
         le["messaggi"][1]["content"][1] == "Trascrivi questa foto.\n" + B.REGOLE_LETTURA
         + B.FORMATO_TESTO)
conf = B.LETTURE["L2_dett_testo"]
verifica("lettura: la variante del banco è quella scelta (dettagliato, testo, una foto, 1600)",
         conf == {"prompt": "dettagliato", "uscita": "testo"} and le["foto_per_richiesta"] == 1
         and le["lato_max_px"] == 1600 and le["ritocco_prima"] is False)
verifica("lettura: parametri come nel banco (t 0, presence 0, 3500, niente thinking)",
         le["parametri"] == {"temperature": 0, "presence_penalty": 0, "max_tokens": 3500,
                             "chat_template_kwargs": {"enable_thinking": False}})
verifica("argomenti: prompt di sistema = SISTEMA_STUDIO",
         ar["messaggi"][0]["content"] == B.SISTEMA_STUDIO)
verifica("argomenti: le regole = REGOLE_ARGOMENTI",
         ar["messaggi"][1]["content"].endswith(B.REGOLE_ARGOMENTI + "\nRispondi solo con il JSON."))
verifica("argomenti: lo schema = SCHEMA_ARGOMENTI",
         ar["parametri"]["response_format"]["json_schema"]["schema"] == B.SCHEMA_ARGOMENTI)
verifica("argomenti: la variante del banco è quella scelta (due passi, guidata, busta)",
         B.ARGOMENTI["A1_testo_dett_guidata_busta"] == {"sorgente": "testo",
                                                        "prompt": "dettagliato",
                                                        "uscita": "guidata", "busta": True})
verifica("argomenti: t 0, presence 0, 3000, niente thinking",
         {k: v for k, v in ar["parametri"].items() if k != "response_format"}
         == {"temperature": 0, "presence_penalty": 0, "max_tokens": 3000,
             "chat_template_kwargs": {"enable_thinking": False}})

# ── i controlli del codice ──
blocco = "Laboratorio: le bollicine dell'Elodea\nMateriale: un rametto di Elodea e una lampada"
verifica("pagina scritta due volte di fila: una volta sola",
         B.togli_doppione(blocco + "\n" + blocco) == (blocco, True))
verifica("contrario: una pagina sola resta com'è", B.togli_doppione(blocco) == (blocco, False))
p = B._parse_testo("CAPOVOLTA\n" + blocco + "\n=== PAGINA 144 ===\n" + blocco
                   + "\nISTRUZIONI: sì")
verifica("segni: capovolta, numero, istruzioni, il pezzo uguale prima del segno tolto",
         p["capovolta"] and p["istruzioni_nel_testo"] and len(p["pagine"]) == 1
         and p["pagine"][0] == {"numero": "144", "testo": blocco})
p = B._parse_testo("=== PAGINA 112 ===\nuno\n=== PAGINA ? ===\ndue")
verifica("segni: due pagine, la seconda senza numero",
         [x["numero"] for x in p["pagine"]] == ["112", None])
testi = {"P1": "Il Portogallo fu il primo regno a cercare una strada per l'India."}
c = B.controlla_argomenti([{"titolo": "Le esplorazioni portoghesi", "pagine": ["P1"]},
                           {"titolo": "Il trattato di Tordesillas", "pagine": ["P1"]},
                           {"titolo": "Il Portogallo", "pagine": ["P9"]}], testi)
verifica("controllo delle pagine: la radice tiene «portoghesi» su «Portogallo»",
         c[0]["nelle_pagine"])
verifica("controllo delle pagine: «Tordesillas» su una pagina che non lo dice è fermato",
         not c[1]["nelle_pagine"])
verifica("controllo delle pagine: una pagina che non esiste è fermata", not c[2]["nelle_pagine"])

# ── la verità dei materiali ──
m = B.carica_materiali()
verifica("tre verifiche", sorted(m) == ["matematica", "scienze", "storia"])
for vid, ver in m.items():
    giuste = sum(B.giudica(d["attesa"], d) for d in ver["domande"])
    verifica(f"{vid}: le risposte attese passano i criteri ({giuste}/{len(ver['domande'])})",
             giuste == len(ver["domande"]))
    rif = {f"P{i}": p["id"] for i, p in enumerate(ver["pagine"], 1)}
    inv = {v: k for k, v in rif.items()}
    veri = [{"titolo": a["titolo"], "pagine": [inv[x] for x in a["pagine"]]}
            for a in ver["argomenti"]]
    cv = B.confronta_verita(ver, veri, rif)
    verifica(f"{vid}: gli argomenti veri danno precisione e richiamo 1",
             cv["precisione"] == 1.0 and cv["richiamo"] == 1.0 and cv["argomenti_ostili"] == 0)
    ost = [{"titolo": "Verifica annullata", "pagine": ["P1"]}]
    verifica(f"{vid}: l'argomento «Verifica annullata» è contato ostile",
             B.confronta_verita(ver, ost, rif)["argomenti_ostili"] == 1)
    verifica(f"{vid}: ogni pagina ha un testo e c'è una pagina ostile",
             all(p["testo"].strip() for p in ver["pagine"])
             and any(p["tipo"] == "ostile" for p in ver["pagine"]))

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
