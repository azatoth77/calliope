import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco del conto della memoria e delle classi delle attività (14/10/2026, passo 1
dell'arbitro della memoria: docs/ricerche/2026-10-14-arbitro-memoria.md, calliope/arbitro_memoria.py).

- la DGX di oggi (memoria unificata, 26B, e4b e llama-guard su Ollama, whisper.cpp, agente su vLLM
  a 0,4): classi giuste per ogni occupante, conto di Calliope e degli «altri», immagini e secondo
  Whisper a richiesta con la proposta in ombra;
- la politica: con poca memoria libera scarica prima lo sfondo (l'agente solo dal passo 4), il
  meno usato prima; **mai** il tempo reale né un modello che non è di Calliope, neanche per una
  richiesta enorme; memoria libera non letta → nessuna proposta;
- portatile con GPU dedicata (conta la parte sulla GPU di /api/ps), macchina senza GPU;
- `da_config`: guardiano spento senza minori né ospiti, rilevatore uguale alla voce, corsia lenta;
- sola lettura: `conto` e `testo` non chiamano programmi né la rete; `calliope stato --memoria`
  con `--inventario`, `--json`, file mancante → 1.

Passo 2 (15/10, calliope/arbitro_ombra.py):
- le misure vere della DGX nel conto (embedding 6,7 GB da caricato, whisper 2,6);
- `quiete(secondi)` unica: risposta, Whisper, VAD, segnale guasto (nel dubbio occupata);
- il confronto in ombra con guardia, corsia lenta, embedding e arbitro dell'agente: le loro
  decisioni non cambiano, le divergenze si contano per episodio nelle due direzioni;
- l'arbitro in ombra: `richiesta` è solo un append (niente conto né rete dal turno), la coda per
  precedenza a voce ferma, un caricamento alla volta, il vicino subito, la buttata oltre
  l'attesa massima, la proposta con la memoria vera, gli a richiesta ogni minuto (ci sta, solo
  scaricando, non possibile), mai il tempo reale;
- il registro `arbitro-AAAA-MM-GG.jsonl`, `storia`, il criterio (sette giorni, margine, tempo
  reale = 0 con l'avviso), `calliope stato --memoria --storia`; spento di serie, valore sbagliato
  rifiutato.
"""

import contextlib
import io
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from calliope import arbitro_memoria as am, modelli as cat  # noqa: E402
from calliope.config import Config  # noqa: E402

errori = 0
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {str(dettaglio)[:600]}" if not ok
                                                  and dettaglio else ""), flush=True)


def dgx(libera=22.5, extra_ollama=()):
    """La DGX del 14/10 (numeri di Dario: 119 GiB, ~21 GiB disponibili)."""
    return {
        "os": "linux", "arch": "aarch64", "sistema": "Ubuntu 24.04", "ram_gb": 128.45,
        "ram_libera_gb": libera,
        "gpu": {"nome": "NVIDIA GB10", "memoria_gb": 128.45, "libera_gb": libera,
                "unificata": True, "chiave": "GB10", "banda_gbs": 273},
        "motori": {
            "ollama": {"url": "http://127.0.0.1:11434", "versione": "0.35.0", "caricati": [
                {"nome": "gemma4:26b-a4b-it-qat", "gb": 16.1, "gb_gpu": 16.1,
                 "contesto": 28672, "in_parte_cpu": False},
                {"nome": "gemma4:e4b-it-qat", "gb": 3.13, "gb_gpu": 3.13, "contesto": 2048,
                 "in_parte_cpu": False},
                {"nome": "llama-guard3:8b", "gb": 5.27, "gb_gpu": 5.27, "contesto": 2048,
                 "in_parte_cpu": False}, *extra_ollama]},
            "vllm": [{"url": "http://127.0.0.1:8000/v1", "versione": "0.29.0",
                      "modelli": [{"id": "qwen3.6-35b"}], "gpu_memory_utilization": 0.4}],
            "whisper_server": {"locale": True, "attivo": True},
            "onnxruntime_cuda": True}}


def uso_dgx(**kw):
    u = am.Uso(voce="gemma4:26b-a4b-it-qat", guardiano="llama-guard3:8b",
               rilevatore="gemma4:e4b-it-qat", embedding="qwen3-embedding:0.6b",
               whisper="server", piper_gpu=True, agente="qwen3.6-35b", processo_gb=3.0)
    for k, v in kw.items():
        setattr(u, k, v)
    return u


def occ(c, ruolo):
    return next((o for o in c.occupanti if o.ruolo == ruolo), None)


# ─────────────────────────── 1. la DGX di oggi ───────────────────────────
c = am.conto(dgx(), uso_dgx())
cl = {o.ruolo: o.classe for o in c.occupanti}
verifica("DGX: voce, Whisper, guardiano, rilevatore e processo sono del tempo reale",
         all(cl.get(r) == am.TEMPO_REALE for r in ("voce", "whisper", "guardiano", "rilevatore",
                                                    "calliope")), cl)
verifica("DGX: agente ed embedding di sfondo, immagini e secondo Whisper a richiesta",
         cl.get("agente") == am.SFONDO and cl.get("embedding") == am.SFONDO
         and cl.get("immagini") == am.A_RICHIESTA and cl.get("whisper_lento") == am.A_RICHIESTA,
         cl)
ag = occ(c, "agente")
verifica("DGX: l'agente tiene gpu_memory_utilization × pool (0,4 × 128,45 = 51,38 GB)",
         abs(ag.gb - 51.38) < 0.01 and ag.dal_passo == 4 and "sonno" in ag.scarica, ag)
verifica("DGX: /api/ps più il buffer del piano (sottostima dichiarata)",
         abs(occ(c, "voce").gb - 16.45) < 0.01 and "sottostima" in occ(c, "voce").fonte,
         occ(c, "voce"))
verifica("DGX: embedding non caricato (keep_alive 0), gb 0 e gb_pieno dalla misura (6,7 GB)",
         occ(c, "embedding").gb == 0 and occ(c, "embedding").caricato is False
         and occ(c, "embedding").gb_pieno == 6.7 and "misura" in occ(c, "embedding").fonte,
         occ(c, "embedding"))
emb_car = {"nome": "qwen3-embedding:0.6b", "gb": 0.64, "gb_gpu": 0.0, "contesto": 32768,
           "in_parte_cpu": True}
ce6 = am.conto(dgx(extra_ollama=(emb_car,)), uso_dgx())
verifica("DGX: embedding caricato tiene la misura vera (6,7), non /api/ps (0,64 + buffer)",
         occ(ce6, "embedding").gb == 6.7 and occ(ce6, "embedding").caricato is True,
         occ(ce6, "embedding"))
verifica("DGX: whisper dei turni 2,6 GB (misura del 14/10)", occ(c, "whisper").gb == 2.6,
         occ(c, "whisper"))
verifica("DGX: processo di Calliope con Piper sulla GPU (3,0 + 1,5)",
         abs(occ(c, "calliope").gb - 4.5) < 0.01, occ(c, "calliope"))
atteso = round(16.45 + 3.48 + 5.62 + 2.6 + 4.5 + 51.38, 2)
verifica("DGX: conto di Calliope = somma degli occupanti caricati", abs(c.di_calliope_gb
                                                                        - atteso) < 0.02,
         (c.di_calliope_gb, atteso))
verifica("DGX: altri = usata − Calliope, margine 8 GB, caricabile = liberi − margine",
         abs(c.altri_gb - round(128.45 - 22.5 - c.di_calliope_gb, 2)) < 0.02
         and c.margine_gb == 8.0 and abs(c.spazio_gb - 14.5) < 0.01,
         (c.altri_gb, c.spazio_gb))
pr = {p.per: p for p in c.proposte}
verifica("DGX con 22,5 GB liberi: immagini (13 GB) e secondo Whisper ci stanno senza scaricare",
         pr["immagini"].ci_sta and not pr["immagini"].scaricherebbe
         and pr["whisper_lento"].ci_sta, pr)
verifica("DGX: per classe somma al conto di Calliope",
         abs(sum(v for k, v in c.per_classe().items() if k != "fuori") - c.di_calliope_gb)
         < 0.02, c.per_classe())

# ─────────────────────────── 2. la politica ───────────────────────────
poca = am.conto(dgx(libera=10.0), uso_dgx())
p = am.proposta(poca, 13.0, "immagini")
verifica("10 GB liberi: per le immagini scaricherebbe l'agente (sfondo), non il tempo reale",
         p.ci_sta and p.scaricherebbe == ["agente"] and p.liberati_gb > 11, p)
p3 = am.proposta(poca, 13.0, "immagini", passo=3)
verifica("al passo 3 l'agente non si tocca ancora: non ci sta, e dice quanto manca",
         not p3.ci_sta and p3.scaricherebbe == [] and abs(p3.mancano_gb - 11.0) < 0.01, p3)
enorme = am.proposta(poca, 500.0, "immagini")
tempo_reale = {o.ruolo for o in poca.occupanti if o.classe == am.TEMPO_REALE}
verifica("contrario: una richiesta enorme non scarica mai il tempo reale",
         not enorme.ci_sta and not (set(enorme.scaricherebbe) & tempo_reale)
         and "mai il tempo reale" in enorme.note, enorme)
estraneo = {"nome": "llama3.1:70b", "gb": 40.0, "gb_gpu": 40.0, "contesto": 8192,
            "in_parte_cpu": False}
ce = am.conto(dgx(libera=4.0, extra_ollama=(estraneo,)), uso_dgx())
pe = am.proposta(ce, 30.0, "immagini")
verifica("contrario: un modello che non è di Calliope si conta («fuori») ma non si scarica",
         occ(ce, "altro su Ollama").classe == "fuori" and "altro su Ollama" not in
         pe.scaricherebbe and any("non lo usa" in a for a in ce.avvisi)
         and ce.di_calliope_gb == c.di_calliope_gb, (pe, ce.avvisi))
# Il meno usato prima; senza ultimo uso: prima di tutti
x = am.Conto("finta", "unificata", 100, 5.0, "finta", 0.0, occupanti=[
    am.Occupante("a", "a", am.SFONDO, "ollama", gb=2, caricato=True, ultimo_uso_s=10),
    am.Occupante("b", "b", am.SFONDO, "ollama", gb=2, caricato=True, ultimo_uso_s=500),
    am.Occupante("c", "c", am.SFONDO, "ollama", gb=2, caricato=True, ultimo_uso_s=None),
    am.Occupante("v", "v", am.VICINO, "ollama", gb=2, caricato=True, ultimo_uso_s=9999),
    am.Occupante("r", "r", am.A_RICHIESTA, "servizio", gb=2, caricato=True, ultimo_uso_s=1),
    am.Occupante("t", "t", am.TEMPO_REALE, "ollama", gb=50, caricato=True, ultimo_uso_s=9e9)])
ordine = [o.ruolo for o in am.scaricabili(x)]
verifica("ordine: sfondo dal meno usato (senza uso per primo), poi a richiesta, poi vicino; "
         "mai il tempo reale", ordine == ["c", "b", "a", "r", "v"], ordine)
pp = am.proposta(x, 8.0, "z")
verifica("si ferma appena basta (3 GB mancanti → due scaricati)",
         pp.ci_sta and pp.scaricherebbe == ["c", "b"], pp)
verifica("chi si vuole caricare non è un candidato a scaricarsi",
         "r" not in [o.ruolo for o in am.scaricabili(x, per="r")])
nl = am.conto({**dgx(), "gpu": {**dgx()["gpu"], "libera_gb": None}}, uso_dgx())
verifica("memoria libera non letta: nessuna proposta che ci sta, avviso",
         all(not q.ci_sta for q in nl.proposte) and any("non si legge" in a
                                                        for a in nl.avvisi), nl.proposte)

# ─────────────────────────── 3. altre macchine ───────────────────────────
port = {"os": "windows", "arch": "x86_64", "ram_gb": 33.8, "ram_libera_gb": 6.5,
        "gpu": {"nome": "NVIDIA GeForce RTX 5070 Laptop GPU", "memoria_gb": 8.55,
                "libera_gb": 2.0, "unificata": False},
        "motori": {"ollama": {"caricati": [
            {"nome": "gemma4:e4b-it-qat", "gb": 4.6, "gb_gpu": 4.6, "contesto": 16384},
            {"nome": "qwen3-embedding:0.6b", "gb": 0.64, "gb_gpu": 0, "contesto": 512}]},
            "vllm": [], "whisper_server": None}}
cp = am.conto(port, am.Uso(voce="gemma4:e4b-it-qat", embedding="qwen3-embedding:0.6b",
                           whisper="locale", processo_gb=1.0))
verifica("portatile: GPU dedicata, margine 0,5, l'embedding sulla CPU non conta nella VRAM",
         cp.tipo == "dedicata" and cp.margine_gb == 0.5 and occ(cp, "embedding").gb == 0
         and occ(cp, "embedding").caricato is True
         and occ(cp, "whisper").caricato is True, [(o.ruolo, o.gb) for o in cp.occupanti])
verifica("portatile: immagini (13 GB) non ci stanno", not {q.per: q for q in cp.proposte}
         ["immagini"].ci_sta)
cpu = am.conto({"os": "linux", "arch": "x86_64", "ram_gb": 16.0, "ram_libera_gb": 9.0,
                "gpu": None, "motori": {}}, am.Uso(voce="gemma4:e2b-it-qat"))
verifica("solo CPU: tipo cpu, niente immagini, Ollama assente = non sondato",
         cpu.tipo == "cpu" and occ(cpu, "immagini") is None
         and occ(cpu, "voce").caricato is None, cpu.occupanti)

# ─────────────────────────── 4. da_config ───────────────────────────
cfg = Config()
cfg.minori_enabled, cfg.guardiano_ospiti = False, False
verifica("da_config: senza minori né ospiti col guardiano niente guardiano né rilevatore",
         am.da_config(cfg).guardiano == "" and am.da_config(cfg).rilevatore == "")
cfg = Config()
cfg.minori_enabled = True
cfg.guardiano_pericolo_modello = cfg.llm_model
verifica("da_config: rilevatore uguale alla voce → nessun modello in più",
         am.da_config(cfg).rilevatore == "" and am.da_config(cfg).guardiano)
cfg.stanza, cfg.stanza_lenta, cfg.stanza_lenta_stt_url = "ombra", True, "http://127.0.0.1:8005/v1"
u = am.da_config(cfg)
cl = am.conto(dgx(), u)
verifica("corsia lenta con un Whisper suo: secondo Whisper a richiesta, non sondato, niente "
         "proposta", u.stanza_lenta == "server" and occ(cl, "whisper_lento").caricato is None
         and "whisper_lento" not in {q.per for q in cl.proposte}, occ(cl, "whisper_lento"))

# ─────────────────────────── 5. sola lettura e terminale ───────────────────────────
vere = (subprocess.run, urllib.request.urlopen)


def vietato(*a, **k):
    raise AssertionError("chiamata esterna nel conto")


subprocess.run = urllib.request.urlopen = vietato
try:
    t = am.testo(am.conto(dgx(libera=10.0), uso_dgx()))
    ok_letto = True
except AssertionError as e:
    t, ok_letto = str(e), False
finally:
    subprocess.run, urllib.request.urlopen = vere
verifica("conto e testo non chiamano programmi né la rete", ok_letto, t)
verifica("testo: classi, proposta in ombra, niente si scarica",
         "Tempo reale:" in t and "Sfondo:" in t and "A richiesta:" in t
         and "in ombra" in t and "scaricherebbe agente" in t and "Niente si scarica" in t, t)
verifica("JSON del conto serializzabile, con i totali",
         json.loads(json.dumps(c.as_json()))["di_calliope_gb"] == c.di_calliope_gb)

TMP = Path(tempfile.mkdtemp(prefix="calliope-memoria-"))
f = TMP / "inv.json"
f.write_text(json.dumps({"inventario": dgx()}), encoding="utf-8")
from calliope import stato  # noqa: E402
prima = sorted(p.name for p in TMP.iterdir())
for argv, attesa in ((["--memoria", "--inventario", str(f)], "Cosa farebbe l'arbitro"),
                     (["--memoria", "--json", "--inventario", str(f)], '"memoria"')):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = stato.main(argv)
    verifica(f"calliope stato {' '.join(argv[:2])}: esce 0", rc == 0 and attesa in
             out.getvalue(), out.getvalue()[-400:])
js = json.loads(out.getvalue())
verifica("--json: inventario e memoria con le classi", js["memoria"]["per_classe"]["sfondo"] > 50)
out = io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
    rc = stato.main(["--memoria", "--inventario", str(TMP / "manca.json")])
verifica("--inventario mancante → 1", rc == 1, out.getvalue())
verifica("nessun file scritto", sorted(p.name for p in TMP.iterdir()) == prima)

# ─────────────────────────── 6. passo 2: una sola «voce ferma» ───────────────────────────
import copy  # noqa: E402
import datetime  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402

from calliope import arbitro_ombra as AO  # noqa: E402
from calliope.stanza.misure import Misure  # noqa: E402


class Orologio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


orl = Orologio()
q = am.Quiete(orologio=orl)
flag = {"risposta": False, "whisper": False}
q.segnali = [("risposta", lambda: flag["risposta"]), ("whisper", lambda: flag["whisper"])]
verifica("quiete: all'avvio la voce conta come appena occupata", not q(5) and q(0))
orl.t += 6
verifica("quiete(5) dopo 6 s senza niente, quiete(10) no", q(5) and not q(10))
flag["risposta"] = True
verifica("risposta in corso: occupata, col motivo", not q(0) and q.occupata() == "risposta")
flag["risposta"] = False
orl.t += 3
verifica("3 s dopo la risposta: quiete(2) sì, quiete(5) no", q(2) and not q(5))
flag["whisper"] = True
verifica("una frase che aspetta Whisper: occupata", q.occupata() == "whisper" and not q(0))
flag["whisper"] = False
q.voce_occupata()
orl.t += 30
verifica("VAD: chi parla tiene la voce occupata anche dopo 30 s", not q(0)
         and q.occupata() == "voce")
q.voce_libera()
orl.t += 4
verifica("VAD: 4 s dopo la fine del parlato quiete(3) sì, quiete(5) no", q(3) and not q(5))
q.segnali.append(("rotto", lambda: 1 / 0))
verifica("contrario: un segnale guasto vale occupata (come guardia e corsia lenta)",
         not q(0) and q.occupata() == "rotto")
q.segnali.pop()
verifica("la funzione del modulo usa la QUIETE del processo",
         am.quiete(0) == am.QUIETE(0) and isinstance(am.QUIETE, am.Quiete))
verifica("tempo_reale_toccato: trova un ruolo del tempo reale in una proposta (il controllo)",
         am.tempo_reale_toccato(c, am.Proposta("x", 1, True, 0, scaricherebbe=["voce", "agente"]))
         == ["voce"])

# ─────────────────────────── 7. l'arbitro in ombra ───────────────────────────
TMP2 = Path(tempfile.mkdtemp(prefix="calliope-arbitro-"))
cfg2 = Config()
cfg2.turn_log_dir = str(TMP2)
cfg2.arbitro_memoria = "ombra"
cfg2.llm_backend, cfg2.llm_model, cfg2.stt_motore = "ollama", "gemma4:26b-a4b-it-qat", "server"
cfg2.minori_enabled, cfg2.guardiano_enabled = True, True
cfg2.guardiano_modello, cfg2.guardiano_pericolo_modello = "llama-guard3:8b", "gemma4:e4b-it-qat"
cfg2.conversazioni_embedding = "qwen3-embedding:0.6b"
cfg2.agenti_enabled = True
cfg2.stanza_lenta_stt_url = ""
macchina_finta = {"libera": 22.5, "vllm": True, "caricati": None, "chiamate": 0}


def inv_finto():
    macchina_finta["chiamate"] += 1
    d = copy.deepcopy(dgx(libera=macchina_finta["libera"]))
    if not macchina_finta["vllm"]:
        d["motori"]["vllm"] = []
    return d


def libera_finta():
    macchina_finta["chiamate"] += 1
    return macchina_finta["libera"]


def caricati_finti():
    macchina_finta["chiamate"] += 1
    return macchina_finta["caricati"]


orl2 = Orologio()
q2 = am.Quiete(orologio=orl2)
mis = Misure(str(TMP2), 60, prefisso=AO.PREFISSO)
om = AO.Ombra(cfg2, q2, inventario=inv_finto, libera=libera_finta, caricati=caricati_finti,
              misure=mis, orologio=orl2, avvia=False, log=lambda m: None)


def righe(tipo):
    return [r for r in mis.memoria if r["tipo"] == tipo]


om._scrivi("avvio", modo=AO.OMBRA, **om._testa())
verifica("la riga d'avvio: memoria unificata, pool e margine", righe("avvio") and
         righe("avvio")[0]["memoria"] == "unificata" and righe("avvio")[0]["margine_gb"] == 8.0,
         mis.memoria[-1:])
q2.voce_occupata()
prima = macchina_finta["chiamate"]
om.richiesta("embedding", turni=16)
verifica("richiesta(): solo un append, niente conto né memoria letta (anche dal turno)",
         macchina_finta["chiamate"] == prima and len(om._richieste) == 1)
om.passo()
r0 = righe("richiesta")[-1]
verifica("embedding non caricato: chiederebbe 6,7 GB, ci sta senza scaricare, in coda perché "
         "qualcuno parla", r0["chi"] == "embedding" and r0["gb"] == 6.7 and r0["ci_sta"]
         and r0["scaricherebbe"] == [] and r0["partirebbe"] == "in_coda"
         and r0["occupata"] == "voce" and r0["libera_gb"] == 22.5 and r0["tempo_reale"] == []
         and r0["turni"] == 16, r0)
m0 = righe("minuto")[-1]
verifica("il primo giro scrive il minuto: memoria vera, margine, a richiesta che ci stanno",
         m0["libera_gb"] == 22.5 and m0["margine_gb"] == 8.0 and m0["tempo_reale"] == 0
         and m0["a_richiesta"]["whisper_lento"]["senza_scaricare"]
         and m0["a_richiesta"]["immagini"]["senza_scaricare"], m0)
q2.voce_libera()
orl2.t += 2
om.passo()
verifica("a voce ferma da 2 s non parte ancora (QUIETE_CARICO_S = 5)", not righe("partita"))
orl2.t += 4
om.passo()
p0 = righe("partita")
verifica("a voce ferma da 6 s la coda in ombra la fa partire, con l'attesa",
         len(p0) == 1 and p0[0]["chi"] == "embedding" and p0[0]["attesa_s"] >= 6, p0)
# Precedenza e un caricamento alla volta
cfg2.stanza_lenta_stt_url = "http://127.0.0.1:8005/v1"
orl2.t += 10
q2.voce_occupata()
om.richiesta("guardia", righe=3)
om.richiesta("corsia_lenta", segmenti=2)
om.passo()
rl = righe("richiesta")[-1]
verifica("corsia lenta col Whisper suo: a richiesta, 2,0 GB (large-v3 q5_0 di whisper-lento.sh, "
         "non i 3,6 della variante f16: issue #2)", rl["chi"] == "corsia_lenta"
         and rl["classe"] == am.A_RICHIESTA and rl["gb"] == 2.0
         and am.A_RICHIESTA_GB["whisper_lento"] == cat.WHISPER["cpp-lenta"].memoria_gb, rl)
q2.voce_libera()
orl2.t += 6
om.passo()
pp = [r["chi"] for r in righe("partita")]
verifica("precedenza: la corsia lenta (a richiesta) parte prima del guardiano (sfondo), e il "
         "guardiano aspetta il caricamento in corso", pp[-1] == "corsia_lenta"
         and "guardia" not in pp, pp)
orl2.t += 6
om.passo()
pp = [r["chi"] for r in righe("partita")]
verifica("finito il caricamento parte il guardiano", pp[-1] == "guardia", pp)
# Il vicino non aspetta; la buttata
q2.voce_occupata()
om.richiesta("embedding_ricerca")
om.richiesta("agente")
om.passo()
rv = [r for r in righe("richiesta") if r["chi"] == "embedding_ricerca"][-1]
verifica("la domanda di una ricerca (vicino) partirebbe subito anche a voce occupata",
         rv["classe"] == am.VICINO and rv["partirebbe"] == "subito", rv)
orl2.t += AO.ATTESA_MAX_S[am.SFONDO] + 5
om.passo()
bb = righe("buttata")
verifica("un lavoro di sfondo che aspetta oltre l'attesa massima si butta e si conta",
         bb and bb[-1]["chi"] == "agente" and om._coda == [], bb)
q2.voce_libera()
mb = righe("minuto")[-1]
verifica("il minuto conta le richieste per chi e le buttate",
         mb["richieste"].get("agente") == 1 and mb["buttate"] == 1, mb)
# Poca memoria: solo scaricando (l'agente, dal passo 4) e non possibile (senza vLLM). 9 GB:
# 9 − 8 di margine = 1 GB, meno dei 2,0 del secondo Whisper (con 10 ci starebbe giusto)
macchina_finta["libera"] = 9.0
orl2.t += 61
om._inv = None
om.passo()
m1 = righe("minuto")[-1]
verifica("9 GB liberi: secondo Whisper solo scaricando l'agente, immagini idem; mai il tempo "
         "reale", m1["a_richiesta"]["whisper_lento"]["ci_sta"]
         and m1["a_richiesta"]["whisper_lento"]["scaricherebbe"] == ["agente"]
         and m1["a_richiesta"]["immagini"]["scaricherebbe"] == ["agente"]
         and m1["tempo_reale"] == 0, m1)
macchina_finta["vllm"] = False
om._inv = None
orl2.t += 61
om.passo()
m2 = righe("minuto")[-1]
verifica("senza niente di sfondo da scaricare: immagini non possibili, quanto manca; tempo reale "
         "mai", not m2["a_richiesta"]["immagini"]["ci_sta"]
         and m2["a_richiesta"]["immagini"]["mancano_gb"] > 10 and m2["tempo_reale"] == 0, m2)
q2.voce_occupata()
om.richiesta("corsia_lenta")
om.passo()
rr = righe("richiesta")[-1]
verifica("richiesta del secondo Whisper con 9 GB liberi e niente da scaricare (9 − 8 = 1 < "
         "2,0): rifiuto in ombra, mai il tempo reale", rr["ci_sta"] is False
         and rr["mancano_gb"] >= 0.99 and rr["tempo_reale"] == []
         and rr["partirebbe"] == "rifiutata" and om._coda == [], rr)
q2.voce_libera()
macchina_finta.update(libera=22.5, vllm=True)
om._inv = None

# Il confronto con i quattro posti di oggi: decisioni uguali, divergenze contate
from calliope.stanza.guardia import Guardia  # noqa: E402
from calliope.stanza.lenta import Lenta  # noqa: E402
from calliope.conversazioni import ArchivioConversazioni  # noqa: E402
from calliope.agenti.arbitro import Arbitro  # noqa: E402

gocc = {"v": True}
cfg2.stanza_guardia_quiete_s = 5.0
g = Guardia(cfg2, types.SimpleNamespace(), None, occupato=[lambda: gocc["v"]], avvia=False,
            log=lambda m: None)
senza = g.libera()
g.ombra_quiete = om.confronta
orl2.t += 100                       # quiete() dice ferma da tanto, la guardia è occupata
con = g.libera()
d = om.divergenze().get("guardia") or {}
verifica("guardia: con l'ombra decide come prima (occupata), divergenza «solo per quiete»",
         senza is False and con is False and d.get("vecchia_no") == 1, d)
g.libera()
verifica("guardia: la stessa divergenza di fila è un episodio solo",
         om.divergenze()["guardia"]["vecchia_no"] == 1)
gocc["v"] = False
g._libera_da = time.monotonic() - 60
q2.voce_occupata()
verifica("guardia libera per la vecchia, voce occupata per quiete: decide libera, conta l'altra "
         "direzione", g.libera() is True and om.divergenze()["guardia"]["vecchia_si"] == 1)
q2.voce_libera()
le = Lenta(cfg2, types.SimpleNamespace(in_coda=lambda: 0, _comando={}), occupato=(),
           avvia=False, log=lambda m: None)
le._libera_da = time.monotonic() - 60
le.ombra_quiete = om.confronta
orl2.t += 100
verifica("corsia lenta: decide come prima, nessuna divergenza se anche quiete() è ferma",
         le.libera() is True and "corsia_lenta" in om.divergenze()
         and om.divergenze()["corsia_lenta"] == {"vecchia_si": 0, "vecchia_no": 0, "s": 0.0},
         om.divergenze())
arch = ArchivioConversazioni(":memory:", avvia=False, cfg=cfg2, sessione=False,
                             log=lambda m: None)
arch.inattivita_s = 600
arch.ultima_attivita = time.monotonic()
arch.ombra_quiete = om.confronta
orl2.t += 1000
verifica("embedding: inattiva() dice no come prima (attività da poco), quiete(600) sì: contata",
         arch.inattiva() is False and om.divergenze()["embedding"]["vecchia_no"] == 1)
eventi = []
arch.ombra_quiete = None
arch.su_carico = lambda chi, **k: eventi.append(chi)
verifica("spento: senza ombra inattiva() non chiama niente", arch.inattiva() is False
         and eventi == [])
arb = Arbitro(True, 3.0)
om.arbitro_agente = arb
arb.voce_occupata()
orl2.t += 100
om.passo()
verifica("arbitro dell'agente: occupato per lui, fermo per quiete → divergenza contata",
         om.divergenze()["agente"]["vecchia_no"] == 1, om.divergenze())
arb2 = Arbitro(True, 3.0, tenuta_max_s=0.0)
arb2.voce_occupata()
time.sleep(0.01)
turni_prima = arb2.turni
verifica("occupata_ora: oltre la tenuta massima dice libera senza toccare lo stato "
         "(in_pausa lo cambierebbe)", arb2.occupata_ora() is False and arb2._attiva
         and arb2.turni == turni_prima)
arb.voce_libera(ripresa_s=0)
time.sleep(0.01)
om.passo()
orl2.t += 61
om.passo()
mm = [r for r in righe("minuto") if r["divergenze"]]
verifica("il minuto porta le divergenze del minuto (guardia, embedding, agente)",
         mm and set(mm[-1]["divergenze"]) >= {"agente"}, mm[-1:] if mm else righe("minuto")[-1])
dv = righe("divergenza")
verifica("una riga per episodio, solo numeri (fonte, direzione, secondi)",
         dv and all(set(r) <= {"t", "tipo", "fonte", "direzione", "secondi"} for r in dv), dv[:3])

# Il registro su disco, la storia e il criterio
fatti = AO.leggi(str(TMP2))
st = AO.storia(fatti)
oggi = datetime.date.today().isoformat()
verifica("registro arbitro-AAAA-MM-GG.jsonl scritto e riletto",
         (TMP2 / f"arbitro-{oggi}.jsonl").exists() and oggi in st and st[oggi]["minuti"] >= 4,
         list(TMP2.iterdir()))
verifica("storia di oggi: libera minima 9 GB, immagini non possibili, rifiuti, partite, buttate",
         st[oggi]["libera_min_gb"] == 9.0 and st[oggi]["non_possibile"].get("immagini", 0) >= 1
         and st[oggi]["solo_scaricando"].get("whisper_lento", 0) >= 1 and st[oggi]["rifiuti"] >= 1
         and st[oggi]["partite"] >= 3 and st[oggi]["buttate"] == 1
         and st[oggi]["tempo_reale"] == 0, st[oggi])
verifica("criterio: un giorno solo non basta", not AO.criterio(st)["ok"]
         and "1 su 7" in AO.criterio(st)["motivi"][0], AO.criterio(st))


def giorno(n, libera=20.0, tr=0):
    d = (datetime.date(2026, 10, 1) + datetime.timedelta(days=n)).isoformat()
    return {"t": d + "T10:00:00.000", "tipo": "minuto", "libera_gb": libera, "margine_gb": 8.0,
            "a_richiesta": {"whisper_lento": {"ci_sta": True, "senza_scaricare": True},
                            "immagini": {"ci_sta": True, "senza_scaricare": False}},
            "tempo_reale": tr, "divergenze": {"guardia": {"vecchia_si": 1, "vecchia_no": 0,
                                                          "s": 2.0}},
            "richieste": {"embedding": 3}}


sette = AO.storia([giorno(i) for i in range(7)])
verifica("criterio: sette giorni sopra il margine e senza tempo reale → soddisfatto",
         AO.criterio(sette)["ok"] and "soddisfatto" in AO.testo_storia(sette))
sotto = AO.storia([giorno(i, libera=6.0 if i == 3 else 20.0) for i in range(7)])
verifica("criterio: un giorno sotto il margine → non ancora",
         not AO.criterio(sotto)["ok"] and "sotto il margine" in AO.criterio(sotto)["motivi"][0])
tr = AO.storia([giorno(i, tr=1 if i == 5 else 0) for i in range(7)])
t_tr = AO.testo_storia(tr)
verifica("contrario: «avrebbe scaricato il tempo reale» > 0 → avviso e criterio non soddisfatto",
         not AO.criterio(tr)["ok"] and "AVVISO" in t_tr and "deve essere 0" in t_tr, t_tr)
verifica("testo: solo scaricando e divergenze di quiete() per giorno",
         "solo scaricando: immagini 1 min" in t_tr and "quiete() diversa: guardia" in t_tr, t_tr)

# calliope stato --memoria --storia
out = io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
    rc = stato.memoria_main(cfg2, ["--memoria", "--storia"], False)
verifica("calliope stato --memoria --storia: esce 0, giorno e criterio", rc == 0
         and oggi in out.getvalue() and "Criterio per il passo 3" in out.getvalue(),
         out.getvalue()[-500:])
out = io.StringIO()
with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
    rc = stato.memoria_main(cfg2, ["--memoria", "--storia", "--json", "--giorni", "3"], True)
js = json.loads(out.getvalue())
verifica("--storia --json: modo, storia e criterio", rc == 0 and js["modo"] == "ombra"
         and oggi in js["storia"] and js["criterio"]["ok"] is False, js.get("criterio"))
out = io.StringIO()
with contextlib.redirect_stdout(out):
    rc = stato.memoria_main(cfg2, ["--memoria", "--storia", "--giorni", "x"], False)
verifica("--giorni non numerico → 1", rc == 1)

# Spento di serie, valori sbagliati
from calliope.config import VALIDATORI  # noqa: E402
verifica("arbitro_memoria spento di serie: nessun thread, nessuna ombra",
         Config().arbitro_memoria == "spento" and AO.load_ombra(Config()) is None)
try:
    VALIDATORI["arbitro_memoria"]("acceso")
    rifiutato = False
except ValueError:
    rifiutato = True
verifica("contrario: «acceso» non è un valore (spento | ombra)", rifiutato
         and VALIDATORI["arbitro_memoria"](" Ombra ") == "ombra")
verifica("contrario: un modo sconosciuto nel cfg vale spento",
         AO.modo(types.SimpleNamespace(arbitro_memoria="boh")) == AO.SPENTO)
om.chiudi()
arch.close()

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
