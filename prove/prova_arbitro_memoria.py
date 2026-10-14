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
"""

import contextlib
import io
import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from calliope import arbitro_memoria as am  # noqa: E402
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
verifica("DGX: embedding non caricato (keep_alive 0), gb 0 e gb_pieno dal catalogo",
         occ(c, "embedding").gb == 0 and occ(c, "embedding").caricato is False
         and occ(c, "embedding").gb_pieno > 0.6, occ(c, "embedding"))
verifica("DGX: processo di Calliope con Piper sulla GPU (3,0 + 1,5)",
         abs(occ(c, "calliope").gb - 4.5) < 0.01, occ(c, "calliope"))
atteso = round(16.45 + 3.48 + 5.62 + 2.1 + 4.5 + 51.38, 2)
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
cfg.stanza, cfg.stanza_lenta, cfg.stanza_lenta_stt_url = "ombra", True, "http://127.0.0.1:8004/v1"
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

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
