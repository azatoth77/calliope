import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dei campi a modi di calliope/config.py (17/10, issue #83).

Caso vero del 15/10: `speaker_impronte_satellite: attiva` scritto a mano nel locale della DGX
(al femminile, come `fine_turno`) valeva «spento» senza avviso; `minori_pericolo_silenzio:
Avvisa` spegneva l'avviso ai tutori dopo il silenzio di un minore. Qui, dal file locale come
sulla DGX:
- per ogni campo a modi: il valore giusto, con le maiuscole e gli spazi, l'altro genere
  (accettato con l'avviso «ho letto …»), i valori sbagliati («acceso», «sì», un refuso) con
  l'avviso di load_config e il valore di serie;
- il «no» di YAML (false) vale il modo spento dove c'è; il «sì» (true) è rifiutato se ambiguo;
- `minori_pericolo_silenzio`: «Avvisa» vale «avvisa», un refuso resta «avvisa», e i Cancelli
  con una Config costruita a mano non spengono l'avviso per un refuso (solo «niente» lo spegne);
- il locale della DGX (i valori noti del 15–16/10) non cambia significato e non dà avvisi;
- un controllo che trova i campi nuovi: ogni campo testo di Config il cui commento elenca due o
  più valori tra «» o "" ha un validatore in VALIDATORI o sta in ECCEZIONI con il perché; e il
  commento di ogni campo a modi dice tutti i suoi valori.
"""

import contextlib
import io
import re
import tempfile
from dataclasses import fields
from pathlib import Path

from calliope.config import VALIDATORI, Config, _field_docs, load_config

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


tmp = Path(tempfile.mkdtemp())
(tmp / "calliope.yaml").write_text("", encoding="utf-8")
_prima_locale = os.environ.pop("CALLIOPE_CONFIG_LOCALE", None)
# Le variabili d'ambiente vincono sul file: qui non devono esserci
_prima_env = {k: os.environ.pop(k) for k in ("CALLIOPE_WAKE_MODE", "CALLIOPE_AUDIO_MODO")
              if k in os.environ}


def dal_locale(testo: str):
    """(cfg, log) con `testo` nel calliope.locale.yaml accanto a un calliope.yaml vuoto."""
    (tmp / "calliope.locale.yaml").write_text(testo, encoding="utf-8")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cfg = load_config(str(tmp / "calliope.yaml"))
    return cfg, out.getvalue()


def riga(campo, valore) -> str:
    return f"{campo}: {valore}\n"        # fuori sezione: load_config la accetta lo stesso


SERIE = Config()
# Dove il valore di serie non è il più stretto, un valore rifiutato vale il più stretto, come su
# main (revisione della PR #130): «amministratore» non deve aprire ai familiari
RIPIEGO = {"agenti_livello": "amministra", "agenti_livello_codice": "amministra",
           "ufficio_livello_fiscale": "amministra", "web_searxng_aggiorna": "manuale"}

# Per ogni campo a modi: (giusto, con maiuscole, altro genere → atteso o None, sbagliati)
CASI = {
    "speaker_impronte_satellite": ("ombra", " Ombra ", ("attiva", "attivo"), ["acceso", "sì", "atttivo"]),
    "minori_pericolo_silenzio": ("niente", "NIENTE", None, ["acceso", "sì", "avvisaa", "nessuno"]),
    "compagnia_enabled": ("ombra", "Ombra", ("attivo", "attiva"), ["accesa", "sì", "ombre"]),
    "compagnia_rivolta": ("attiva", "Attiva", ("spento", "spenta"), ["acceso", "sì", "rivolta"]),
    "compagnia_da_stanza": ("attiva", " Attiva ", ("attivo", "attiva"), ["acceso", "sì", "stanza"]),
    "stanza_lenta_prompt": ("si", "SI", None, ["acceso", "forse", "aut"]),
    "agenti_conferma": ("mai", "Mai", None, ["acceso", "sì", "costoso"]),
    # Il revisore a contesto pulito (20/10, #190)
    "agenti_revisore": ("attivo", "Attivo", ("attiva", "attivo"), ["acceso", "sì", "revisore"]),
    # Lo Studio (29/10, #280)
    "studio_modo": ("ombra", " Ombra ", ("attiva", "attivo"), ["acceso", "sì", "studio"]),
    # La padronanza (30/10, #245)
    "studio_padronanza": ("mostrata", " Mostrata ", None, ["accesa", "sì", "mostra"]),
    # Le carte generate (30/10, #246)
    "studio_carte_genera": ("attiva", " Attiva ", ("attivo", "attiva"), ["accesa", "sì", "genera"]),
    "studio_mappa_genera": ("attiva", " Attiva ", ("attivo", "attiva"), ["accesa", "sì", "genera"]),
    # La mappa libera e «Parliamone» (30/10, #328)
    "studio_mappa_libera": ("spenta", " Spenta ", ("spento", "spenta"), ["accesa", "sì", "libera"]),
    "studio_mappa_consigli": ("attiva", " Attiva ", ("attivo", "attiva"), ["accesa", "sì", "parla"]),
    "agenti_arbitro": ("mai", " MAI ", None, ["acceso", "talvolta"]),
    "agenti_sandbox_motore": ("processo", "Docker", None, ["acceso", "sì", "podman"]),
    "agenti_livello": ("amministra", "Amministra", None,
                       ["acceso", "ospite", "famigliare", "amministratore", "admin"]),
    "agenti_livello_codice": ("familiare", "Familiare", None, ["acceso", "admin"]),
    "ufficio_livello_fiscale": ("familiare", "FAMILIARE", None, ["acceso", "sì", "tutti"]),
    "wake_posizione": ("inizio", "Inizio", None, ["acceso", "sì", "ovunqe"]),
    "wake_mode": ("testo", "Testo", None, ["acceso", "sì", "testuale"]),
    "web_searxng_aggiorna": ("manuale", "Manuale", None, ["acceso", "sì", "automatica", "a mano"]),
    "stt_motore": ("server", "Server", None, ["acceso", "sì", "remoto"]),
    "vad_motore": ("onnx", "ONNX", None, ["acceso", "sì", "onnxruntime"]),
    "immagini_modello": ("no", "No ", None, ["acceso", "vision"]),
    "immagini_storia": ("descrizione", "Descrizione", None, ["acceso", "sì", "messaggi"]),
    "audio_modo": ("satellite", "Satellite", None, ["acceso", "sì", "satelite"]),
    "satellite_schermo": ("kiosk", "Kiosk", None, ["acceso", "sì", "intero"]),
    # quelli che avevano già un validatore, ora fatti dall'aiuto _modi
    "eventi": ("attivo", "Attivo", ("attiva", "attivo"), ["acceso", "sì"]),
    "frasi_varianti": ("spento", "SPENTO", ("spenta", "spento"), ["acceso", "sì"]),
    "dialogo_interprete": ("spento", " Spento ", ("spenta", "spento"), ["acceso", "attivo", "sì"]),
    "cortesia_voce_min": ("attiva", "Attiva", ("attivo", "attiva"), ["acceso", "sì"]),
    "stanza": ("ombra", "OMBRA", ("spento", "spenta"), ["attiva", "acceso", "sì"]),
    "stanza_guardia": ("attiva", "Attiva", ("attivo", "attiva"), ["accesa", "sì"]),
    "fine_turno": ("ombra", "Ombra", ("attivo", "attiva"), ["accesa", "sì"]),
    "ricerca_pertinenza": ("spenta", "Spenta", ("attivo", "attiva"), ["accesa", "sì"]),
    "system1_dopo_tool": ("ombra", "Ombra", ("attiva", "attivo"), ["acceso", "sì"]),
    # 22/10, issue #170: la dichiarazione dopo la prima frase
    "voce_azione_non_fatta": ("attivo", "Attivo", ("attiva", "attivo"), ["acceso", "sì"]),
    "stanza_lenta_blocchi": ("ombra", " Ombra", ("attiva", "attivo"), ["acceso", "sì"]),
    "arbitro_memoria": ("ombra", "Ombra", ("spenta", "spento"), ["attivo", "acceso", "sì"]),
    "stanza_lenta_ritrascrivi": ("no", "AUTO", None, ["acceso", "forse"]),
    "contesto_riassuntore": ("tagli", "Agente", ("spenta", "spento"), ["acceso", "sì"]),
    "tts_dispositivo": ("cuda", "CPU", None, ["gpu", "sì"]),
}

for campo, (giusto, maiusc, genere, sbagliati) in CASI.items():
    serie = RIPIEGO.get(campo, getattr(SERIE, campo))
    cfg, log = dal_locale(riga(campo, giusto))
    verifica(f"{campo}: «{giusto}» vale, senza avvisi",
             getattr(cfg, campo) == giusto and "non è valido" not in log
             and "ho letto" not in log, f"{getattr(cfg, campo)!r} {log.strip()[-160:]}")
    cfg, log = dal_locale(riga(campo, f"'{maiusc}'"))
    verifica(f"{campo}: «{maiusc}» vale «{maiusc.strip().lower()}»",
             getattr(cfg, campo) == maiusc.strip().lower() and "non è valido" not in log,
             f"{getattr(cfg, campo)!r}")
    if genere:
        scritto, atteso = genere
        cfg, log = dal_locale(riga(campo, scritto))
        verifica(f"{campo}: l'altro genere «{scritto}» vale «{atteso}» con l'avviso gentile",
                 getattr(cfg, campo) == atteso and f"ho letto «{atteso}»" in log
                 and campo in log and "non è valido" not in log,
                 f"{getattr(cfg, campo)!r} {log.strip()[-200:]}")
    for male in sbagliati:
        cfg, log = dal_locale(riga(campo, male))
        verifica(f"{campo}: «{male}» rifiutato con l'avviso, vale {serie!r}",
                 getattr(cfg, campo) == serie and f"«{campo}: " in log and "non è valido" in log,
                 f"{getattr(cfg, campo)!r} {log.strip()[-200:]}")

# Il caso vero del 15/10 e il caso dei minori, scritti come nel file locale della DGX
cfg, log = dal_locale("chi_parla:\n  speaker_impronte_satellite: attiva\n")
verifica("caso vero: «speaker_impronte_satellite: attiva» nella sezione vale «attivo», con "
         "l'avviso che nomina il file", cfg.speaker_impronte_satellite == "attivo"
         and "ho letto «attivo»" in log and "calliope.locale.yaml" in log, log.strip()[-200:])
cfg, log = dal_locale("minori:\n  minori_pericolo_silenzio: Avvisa\n")
verifica("minori: «Avvisa» vale «avvisa», senza avvisi", cfg.minori_pericolo_silenzio == "avvisa"
         and "non è valido" not in log, log.strip()[-200:])
cfg, log = dal_locale("minori:\n  minori_pericolo_silenzio: avviso\n")
verifica("minori: «avviso» vale «avvisa»", cfg.minori_pericolo_silenzio == "avvisa")
cfg, log = dal_locale("minori:\n  minori_pericolo_silenzio: no\n")
verifica("minori: il «no» di YAML è rifiutato, resta «avvisa» (la scelta prudente)",
         cfg.minori_pericolo_silenzio == "avvisa" and "non è valido" in log, log.strip()[-200:])

# Il «no» e il «sì» di YAML (false/true): prima erano un tipo sbagliato
for campo, atteso in (("eventi", "spento"), ("stanza", "spenta"), ("compagnia_rivolta", "spenta"),
                      ("speaker_impronte_satellite", "spento"), ("stanza_lenta_prompt", "no"),
                      ("immagini_modello", "no"), ("agenti_arbitro", "mai"),
                      ("satellite_schermo", "no"), ("stanza_lenta_blocchi", "spento"),
                      ("cortesia_voce_min", "spenta"), ("agenti_revisore", "spento"),
                      ("studio_modo", "spento"), ("studio_padronanza", "spenta"),
                      ("studio_carte_genera", "spenta"), ("studio_mappa_genera", "spenta"),
                      ("studio_mappa_libera", "spenta"), ("studio_mappa_consigli", "spenta")):
    cfg, log = dal_locale(riga(campo, "no"))
    verifica(f"{campo}: il «no» di YAML vale «{atteso}»", getattr(cfg, campo) == atteso
             and "non è" not in log, f"{getattr(cfg, campo)!r} {log.strip()[-160:]}")
# Il true non accende mai identità, permessi o sicurezza: impronte e «rivolta» restano
# com'erano (revisione della PR #130), con yes, on e true
for campo in ("eventi", "system1_dopo_tool", "stanza_guardia", "arbitro_memoria",
              "agenti_conferma", "wake_mode", "speaker_impronte_satellite", "compagnia_rivolta",
              "agenti_revisore", "studio_modo", "studio_padronanza", "studio_carte_genera",
              "studio_mappa_genera", "studio_mappa_libera", "studio_mappa_consigli"):
    for scritto in ("yes", "on", "true"):
        cfg, log = dal_locale(riga(campo, scritto))
        verifica(f"contrario: {campo}: il «{scritto}» di YAML (true) è ambiguo, rifiutato",
                 getattr(cfg, campo) == getattr(SERIE, campo) and "non è valido" in log,
                 f"{getattr(cfg, campo)!r}")
# Il false della compagnia non la spegne (su main era un tipo sbagliato: restava «attiva»)
cfg, log = dal_locale(riga("compagnia_enabled", "no"))
verifica("contrario: compagnia_enabled: no rifiutato, resta «attiva»",
         cfg.compagnia_enabled == "attiva" and "non è valido" in log, cfg.compagnia_enabled)
# I livelli: il true e il false non aprono
for campo in ("agenti_livello", "agenti_livello_codice", "ufficio_livello_fiscale"):
    cfg, log = dal_locale(riga(campo, "yes"))
    verifica(f"contrario: {campo}: true vale «amministra»", getattr(cfg, campo) == "amministra")
for campo, atteso in (("compagnia_enabled", "attiva"),
                      ("stanza_lenta_ritrascrivi", "si"), ("agenti_arbitro", "sempre")):
    cfg, log = dal_locale(riga(campo, "true"))
    verifica(f"{campo}: true vale «{atteso}» (come nel modulo che lo legge)",
             getattr(cfg, campo) == atteso, f"{getattr(cfg, campo)!r}")
cfg, log = dal_locale(riga("eventi", "") + riga("stanza", "[ombra]"))
verifica("contrario: vuoto e lista rifiutati, restano quelli di serie",
         (cfg.eventi, cfg.stanza) == (SERIE.eventi, SERIE.stanza) and log.count("non è valido") == 2,
         log.strip()[-200:])

# Il valore rifiutato nel locale lascia quello di calliope.yaml (il file prima), non uno a caso
(tmp / "calliope.yaml").write_text("chi_parla:\n  speaker_impronte_satellite: ombra\n",
                                   encoding="utf-8")
cfg, log = dal_locale("chi_parla:\n  speaker_impronte_satellite: acceso\n")
verifica("locale sbagliato: resta il valore del file prima, con l'avviso «tengo 'ombra'»",
         cfg.speaker_impronte_satellite == "ombra" and "tengo 'ombra'" in log, log.strip()[-200:])
(tmp / "calliope.yaml").write_text("", encoding="utf-8")

# Il locale della DGX (valori noti del 15–16/10): nessun significato cambiato, nessun avviso
DGX = ("llm:\n  llm_reti_spente: [domanda_insistita]\n  system1_dopo_tool: ombra\n"
       "chi_parla:\n  speaker_impronte_satellite: ombra\n"
       "conversazione_stanza:\n  stanza_lenta_blocchi: ombra\n"
       "conversazioni:\n  eventi: ombra\nregistro:\n  arbitro_memoria: ombra\n")
cfg, log = dal_locale(DGX)
verifica("locale della DGX: stessi modi, nessun avviso",
         (cfg.system1_dopo_tool, cfg.speaker_impronte_satellite, cfg.stanza_lenta_blocchi,
          cfg.eventi, cfg.arbitro_memoria) == ("ombra",) * 5
         and "domanda_insistita" in cfg.llm_reti_spente
         and "non è" not in log and "ho letto" not in log and "sconosciuta" not in log,
         log.strip()[-300:])

# I Cancelli con una Config costruita a mano (le prove, un domani un'altra strada): solo
# «niente» spegne l'avviso dopo il silenzio
from calliope import cancelli as K  # noqa: E402

for scritto, atteso in (("avvisa", True), ("Avvisa", True), ("avviso ", True), ("", True),
                        ("niente", False), (" Niente", False)):
    c = Config()
    c.minori_pericolo_silenzio = scritto
    k = K.Cancelli(c, log=lambda m: None)
    partiti = []
    k.materiale = lambda s: (None, None, None)
    k.avvisa = lambda *a, **kw: partiti.append(a) or "ok"
    seg = K.Segnale("p1", "Lia", "", ("pericolo",), False, None, 0.0)
    k.scaduto(seg)
    verifica(f"Cancelli: minori_pericolo_silenzio {scritto!r} → avviso {atteso}",
             bool(partiti) == atteso, str(partiti))

# Il controllo che trova i campi nuovi: un campo testo con due o più valori elencati nel
# commento ha un validatore, o sta qui con il perché
ECCEZIONI = {
    "llm_profilo": "nome di un profilo di PROFILI_LLM, controllato da apply_llm_profile",
    "llm_reasoning_effort": "valore passato com'è all'API OpenAI («none», «low»…; None = non inviare)",
    "stt_correzione_motore": "vuoto = quello della voce; il commento cita i backend, non modi",
    "stt_correzione_modello": "nome di un modello; il commento cita parole d'esempio",
    "giochi_giudice_modello": "nome di un modello; il commento cita altri campi",
}
docs = _field_docs()
tipi = {f.name: f.type for f in fields(Config)}
senza = []
for nome, (righe, _val) in docs.items():
    if tipi.get(nome) is not str and str(tipi.get(nome)) not in ("str | None", "str | bool"):
        continue
    testo = " ".join(righe)
    q = re.findall(r"«([^»]{1,20})»", testo) + re.findall(r'"([a-z_]{2,20})"', testo)
    q = [x for x in dict.fromkeys(q) if re.fullmatch(r"[a-zà-ù_]+", x)]
    if len(q) >= 2 and nome not in VALIDATORI and nome not in ECCEZIONI:
        senza.append((nome, q))
verifica("ogni campo a modi ha un validatore in VALIDATORI (o un'eccezione col perché)",
         not senza, str(senza))
verifica("eccezioni: solo campi che esistono, senza validatore",
         all(n in tipi and n not in VALIDATORI for n in ECCEZIONI))
mancano = {}
for nome, v in VALIDATORI.items():
    modi = getattr(v, "modi", None)
    if modi:
        testo = " ".join(docs[nome][0])
        m = [x for x in modi if not re.search(rf"\b{x}\b", testo)]
        if m:
            mancano[nome] = m
verifica("il commento di ogni campo a modi dice i suoi valori", not mancano, str(mancano))
verifica("i casi della prova coprono tutti i campi a modi",
         {n for n, v in VALIDATORI.items() if getattr(v, "modi", None)} <= set(CASI),
         str(sorted(n for n, v in VALIDATORI.items()
                    if getattr(v, "modi", None) and n not in CASI)))
verifica("predefiniti: ognuno tra i suoi modi",
         all(getattr(SERIE, n) in v.modi for n, v in VALIDATORI.items()
             if getattr(v, "modi", None)),
         str([n for n, v in VALIDATORI.items() if getattr(v, "modi", None)
              and getattr(SERIE, n) not in v.modi]))

if _prima_locale is not None:
    os.environ["CALLIOPE_CONFIG_LOCALE"] = _prima_locale
os.environ.update(_prima_env)
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
