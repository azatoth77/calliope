import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco delle installazioni (calliope/installa/, tools/stato.py; 01/10/2026).

Tutto con un server HTTP finto in locale (prove/http_finto.py) e file di pochi KB, in una
cartella temporanea: niente internet, niente /api/pull vero, niente biblioteca/, voices/ o
models/ veri. Verifica: catalogo e origini, ultima versione di Kiwix trovata in modo
deterministico, permessi (ospite, familiare, chi amministra senza voce), avvio senza
offerta rifiutato (anche nello stesso turno della proposta), prerequisiti (libreria
assente, spazio, file già presenti), checksum sbagliato, ripresa con Range, server che
ignora Range, annullo, avanzamento, attivazione e annuncio, aggiornamento e pulizia,
modello di Ollama, terminale, e il giro completo con Brain e l'azione in sospeso.
"""

import hashlib
import json
import tempfile
import time
from pathlib import Path

from calliope import capacita
from calliope.brain import Brain
from calliope.config import Config
from calliope.installa import Installazioni
from calliope.installa.catalogo import (DESCRIZIONI, FONTI, Azione, FileCat, catalogo,
                                        risolvi_zim, versioni_vecchie)
from calliope.installa.scarica import ErroreInstallazione, controlla_url, part_path
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from calliope.biblioteca_indice import percorso_indice, pronto, stato_indice
from prove.http_finto import FakeHTTP
from prove.zim_finto import VOCI, crea_zim, mini_wikipedia

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


TMP = Path(tempfile.mkdtemp(prefix="calliope-installa-"))
os.chdir(TMP)                      # voices/ e models/ relativi: qui, non quelli veri

srv = FakeHTTP().avvia()
ORIGINI = {"kiwix_mirror": srv.url + "/zim", "kiwix_main": srv.url + "/zim",
           "piper": srv.url + "/piper", "sherpa": srv.url + "/sherpa"}


def cfg_finta(**kw) -> Config:
    c = Config()
    for f in FONTI:
        if f.attr:
            setattr(c, f.attr, str(TMP / "biblioteca" / f"{f.prefisso}_2026-08.zim"))
    c.speaker_model = str(TMP / "models" / "speaker" / "campp.onnx")
    c.llm_native_url = srv.url
    c.llm_model = "modello-finto:1b"
    c.installa_margine_gb = 0.0
    c.installa_velocita_mb_s = 10.0
    c.biblioteca_indice_processi = 1          # file minuscoli: niente processi in più
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def dati(n: int, seme: str) -> bytes:
    return (seme.encode() * (n // len(seme) + 1))[:n]


# ── catalogo e origini ──
cat = catalogo(Config())
verifica("catalogo: tutte le azioni del tool", set(cat) == set(DESCRIZIONI),
         str(set(cat) ^ set(DESCRIZIONI)))
verifica("catalogo vero: solo https e host noti, mai 127.0.0.1",
         all(f.url.startswith("https://") for a in cat.values() for f in a.files)
         and not any("127.0.0.1" in a.hosts for a in cat.values()))
verifica("fonti italiane di Kiwix: 12, nopic dove esiste",
         len(FONTI) == 12 and {f.prefisso for f in FONTI} >= {
             "wikisource_it_all_nopic", "wikibooks_it_all_nopic", "wikiquote_it_all_nopic",
             "wikivoyage_it_all_nopic", "wikiversity_it_all_nopic",
             "wikipedia_it_medicine_nopic", "gutenberg_it_all", "wikipedia_it_all_maxi"})
verifica("nessuna versione di Kiwix scritta nel codice",
         not any(a.files for a in cat.values() if a.tipo == "kiwix"))
for url, hosts, ok in (("https://ftp.fau.de/kiwix/zim/x.zim", ("ftp.fau.de",), True),
                       ("http://ftp.fau.de/kiwix/zim/x.zim", ("ftp.fau.de",), False),
                       ("https://evil.example/x.zim", ("ftp.fau.de",), False),
                       ("http://127.0.0.1:1/x", ("127.0.0.1",), True),
                       ("http://localhost:1/x", ("127.0.0.1",), False)):
    try:
        controlla_url(url, hosts)
        got = True
    except ErroreInstallazione:
        got = False
    verifica(f"origine {url} → {'ammessa' if ok else 'rifiutata'}", got == ok)

# ── contenuti del sito finto ──
# Wikiquote: file ZIM veri, perché dal 01/10 la ricerca la usa (citazioni) e dopo il
# download se ne costruisce l'indice
QUOTE_OLD = crea_zim(VOCI[:2], uuid=b"q" * 16)
QUOTE_NEW = crea_zim(VOCI[:3], uuid=b"Q" * 16)
srv.zim("wikiquote", "wikiquote_it_all_nopic_2026-07.zim", QUOTE_OLD)
srv.zim("wikiquote", "wikiquote_it_all_nopic_2026-09.zim", QUOTE_NEW)
# Wikipedia ridotta: file ZIM veri (piccoli), perché dopo il download si costruisce l'indice
MINI_NEW = mini_wikipedia()
srv.zim("wikipedia", "wikipedia_it_all_mini_2026-10.zim", MINI_NEW)
srv.zim("wikipedia", "wikipedia_it_all_mini_2026-05.zim", dati(100, "old"))
srv.zim("wikipedia", "wikipedia_it_medicine_nopic_2026-07.zim", dati(2000, "med"))

cfg = cfg_finta()


class Prof:
    def __init__(self, name, admin=False):
        self.id, self.name, self.admin = name.lower() + "-id", name, admin


class Speakers:
    users = {"Dario": Prof("Dario", True), "Bianca": Prof("Bianca")}

    def get(self, n):
        return self.users.get(n)


class Spk:
    def __init__(self, name, level, how="voce"):
        self.current_speaker, self.current_level, self.identified_by = name, level, how


reg = build_registry()
annunci = []
inst = Installazioni(cfg, origini=ORIGINI, on_done=lambda: annunci.append(1), log=lambda m: None)
ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=Spk("Dario", "amministra"),
                  speaker=None, installazioni=inst, capacita=capacita.Registro())


def call(tool, args, turno, spk=None, level=None):
    ctx.turno = turno
    ctx.speaker_ctx = spk or Spk("Dario", "amministra")
    ctx.regole.clear()
    lv = level or ctx.speaker_ctx.current_level
    return json.loads(reg.call(tool, args, ctx, lv))


def aspetta():
    for _ in range(300):
        if not inst.occupato():
            return
        time.sleep(0.02)


# ── ultima versione: deterministica dall'indice ──
n_req = len(srv.richieste)
p = inst.piano("fonte_wikiquote")
verifica("ultima versione dall'indice di Kiwix (2026-09, non 2026-07)",
         p.ok and p.files and p.files[0].dest.endswith("wikiquote_it_all_nopic_2026-09.zim"),
         p.frase)
verifica("checksum dal .sha256 ufficiale e dimensione dal mirror",
         p.files[0].sha256 == hashlib.sha256(QUOTE_NEW).hexdigest()
         and p.files[0].size == len(QUOTE_NEW))
verifica("proposta chiara: nome, megabyte, spazio, tempo, internet, domanda",
         "Wikiquote, le citazioni" in p.frase and "megabyte" in p.frase
         and "liberi" in p.frase and "internet" in p.frase and p.frase.endswith("Procedo?")
         and "non ancora" not in p.frase
         # Wikiquote la ricerca la usa (citazioni, 01/10): dopo il download c'è l'indice
         and "Dopo preparo l'indice per la ricerca" in p.frase, p.frase)
p_med = inst.piano("fonte_wikimed")
verifica("fonte in più non ancora integrata (WikiMed): «le userò nelle ricerche»",
         "le userò nelle ricerche" in p_med.frase and "preparo l'indice" not in p_med.frase,
         p_med.frase)
cfg_spenta = cfg_finta(biblioteca_fonti_extra=[])
p_off = Installazioni(cfg_spenta, origini=ORIGINI).piano("fonte_wikiquote")
verifica("Wikiquote spenta in biblioteca_fonti_extra: la proposta dice come accenderla",
         "biblioteca_fonti_extra" in p_off.frase, p_off.frase)
verifica("la proposta non scarica il file (solo indice, .sha256, HEAD)",
         not any(m == "GET" and u.endswith(".zim") for m, u, _ in srv.richieste[n_req:]))
srv.zim("wikipedia", "wikipedia_it_all_mini_extra_2099-01.zim", b"x")   # nome quasi uguale
p = inst.piano("biblioteca_mini")
verifica("nomi quasi uguali non contano (mini_extra, en)", p.ok and
         p.files[0].dest.endswith("wikipedia_it_all_mini_2026-10.zim"), p.frase)

# ── permessi ──
r = call("installa_proponi", {"azione": "fonte_wikiquote"}, 1, Spk(None, "ospite"),
         level="familiare")
verifica("ospite: rifiutato", r["ok"] is False and "solo chi amministra" in r["risposta_finale"]
         and ctx.regole == ["installa_permesso"], r["risposta_finale"])
r = call("installa_proponi", {"azione": "fonte_wikiquote"}, 1, Spk("Bianca", "familiare"))
verifica("familiare: rifiutato, «chiedi a chi amministra»", r["ok"] is False
         and "chiedi a chi amministra" in r["risposta_finale"], r["risposta_finale"])
r = call("installa_proponi", {"azione": "fonte_wikiquote"}, 1,
         Spk("Dario", "amministra", how="breve"))
verifica("chi amministra ma frase troppo breve per la voce: la frase di sfida (04/10)",
         r["ok"] is False and "ripeti:" in r["risposta_finale"],
         r["risposta_finale"])
r = json.loads(reg.call("installa_avvia", {"azione": "fonte_wikiquote"}, ctx, "familiare"))
verifica("installa_avvia non ammesso ai familiari e rifiutato dal registro dei tool",
         r.get("ok") is False and "installa_avvia" not in
         {s["function"]["name"] for s in reg.schemas_for("familiare")})

# ── avvio senza offerta, stesso turno, turno dopo ──
r = call("installa_avvia", {"azione": "fonte_wikiquote"}, 5)
verifica("avvio senza offerta: rifiutato e segnato", r["ok"] is False
         and ctx.regole == ["installa_senza_offerta"] and not inst.occupato(), r["risposta_finale"])
r = call("installa_proponi", {"azione": "fonte_wikiquote"}, 6)
verifica("proposta di chi amministra: domanda e azione in sospeso", r["ok"] and
         r["in_sospeso"]["tool"] == "installa_avvia" and r["in_sospeso"]["domanda"] == "Procedo?"
         and r["risposta_finale"].endswith("?"), r["risposta_finale"])
r = call("installa_avvia", {"azione": "fonte_wikiquote"}, 6)
verifica("avvio nello stesso turno della proposta: rifiutato", r["ok"] is False
         and not inst.occupato())
call("installa_proponi", {"azione": "fonte_wikiquote"}, 7)
r = call("installa_avvia", {"azione": "fonte_wikimed"}, 8)
verifica("avvio di un'altra azione: rifiutato", r["ok"] is False and not inst.occupato())
call("installa_proponi", {"azione": "fonte_wikiquote"}, 9)
# Dal 04/10 la proposta vale 3 turni (calliope/conferme.py): quattro dopo non più
r = call("installa_avvia", {"azione": "fonte_wikiquote"}, 13)
verifica("avvio quattro turni dopo la proposta: rifiutato", r["ok"] is False)
call("installa_proponi", {"azione": "fonte_wikiquote"}, 14)
inst._offerte["dario-id"]["scade"] = time.monotonic() - 1
r = call("installa_avvia", {"azione": "fonte_wikiquote"}, 15)
verifica("offerta scaduta: rifiutato", r["ok"] is False)
inst._offerte["bianca-id"] = {"azione": "fonte_wikiquote", "turno": 15, "piano": None,
                             "scade": time.monotonic() + 60}
r = call("installa_avvia", {"azione": "fonte_wikiquote"}, 16)
verifica("offerta di un'altra persona: rifiutato", r["ok"] is False)

# Dal 03/10 (analisi di sicurezza S4) un «sì» breve non vale come chi amministra: in Calliope
# il livello è già «familiare» (main.py), e il tool ricontrolla la voce
call("installa_proponi", {"azione": "fonte_wikiquote"}, 18)
r = call("installa_avvia", {"azione": "fonte_wikiquote"}, 19, Spk("Dario", "amministra", "breve"))
# Dal 04/10: senza una conversazione sicura (qui nessuna) la frase di sfida
verifica("«sì» breve nel turno dopo: non parte, chiede la frase di sfida", r["ok"] is False
         and "ripeti:" in r["risposta_finale"] and not inst.occupato(),
         r["risposta_finale"])
call("installa_proponi", {"azione": "fonte_wikiquote"}, 20)
r = call("installa_avvia", {"azione": "fonte_wikiquote"}, 21)
verifica("«sì, procedi» con la voce nel turno dopo: parte in secondo piano", r["ok"] and
         "Ho cominciato a scaricare" in r["risposta_finale"], r["risposta_finale"])
aspetta()
dest = TMP / "biblioteca" / "wikiquote_it_all_nopic_2026-09.zim"
verifica("file scaricato, verificato e spostato", dest.read_bytes() == QUOTE_NEW
         and Path(str(dest) + ".verificato").is_file() and not part_path(dest).exists())
item = inst.done.get_nowait() if not inst.done.empty() else {}
verifica("fine nel registro: chi, cosa, quando, esito", item.get("chi") == "dario-id"
         and item.get("azione") == "fonte_wikiquote" and item.get("esito") == "ok"
         and item.get("inizio") and item.get("fine") and annunci == [1], str(item))
msg = inst.completa(item)
verifica("Wikiquote: scaricata, indicizzata, si usa subito (citazioni)",
         "si può già usare" in msg and pronto(dest), msg)
p = inst.piano("fonte_wikiquote")
verifica("già presente → niente da fare", p.codice == "gia_fatto" and "c'è già" in p.frase,
         p.frase)

# ── prerequisiti ──
capacita._SENZA.add("libzim")
r = call("installa_proponi", {"azione": "fonte_wikimed"}, 30)
verifica("biblioteca senza libzim (01/10: puro Python): la proposta si fa lo stesso",
         r["ok"] and "libzim" not in r["risposta_finale"]
         and not any(a.librerie for a in inst.catalogo.values() if a.capacita == "biblioteca"),
         r["risposta_finale"])
capacita._SENZA.discard("libzim")
inst._offerte.clear()
# Libreria che manca, per un'azione che ne ha una (la voce di Piper)
capacita._SENZA.add("piper")
n_req = len(srv.richieste)
r = call("installa_proponi", {"azione": "voce_paola"}, 30)
verifica("libreria assente: «non funzionerebbe», niente download né rete",
         r["ok"] is False and "non funzionerebbe" in r["risposta_finale"]
         and "pip install piper-tts" in r["risposta_finale"]
         and len(srv.richieste) == n_req, r["risposta_finale"])
capacita._SENZA.discard("piper")
inst.cfg.installa_margine_gb = 1e9
r = call("installa_proponi", {"azione": "fonte_wikimed"}, 31)
verifica("spazio insufficiente: niente offerta", r["ok"] is False
         and "liberato spazio" in r["risposta_finale"] and "dario-id" not in inst._offerte,
         r["risposta_finale"])
inst.cfg.installa_margine_gb = 0.0
r = call("installa_proponi", {"azione": "pulizia"}, 32)
verifica("pulizia senza file vecchi: niente da fare", r["ok"] is False
         and "Non ci sono file vecchi" in r["risposta_finale"])

# ── checksum sbagliato ──
srv.sha_sbagliato.add("/zim/wikipedia/wikipedia_it_medicine_nopic_2026-07.zim")
srv.zim("wikipedia", "wikipedia_it_medicine_nopic_2026-07.zim", dati(2000, "med"))
p = inst.piano("fonte_wikimed")
res = inst.esegui(p)
med = TMP / "biblioteca" / "wikipedia_it_medicine_nopic_2026-07.zim"
verifica("checksum sbagliato: errore, .part cancellato, niente file",
         res["esito"] == "errore" and res.get("codice") == "checksum" and not med.exists()
         and not part_path(med).exists(), str(res))

# ── ripresa con Range ──
srv.sha_sbagliato.clear()
srv.zim("wikipedia", "wikipedia_it_medicine_nopic_2026-07.zim", dati(2000, "med"))
srv.taglia["/zim/wikipedia/wikipedia_it_medicine_nopic_2026-07.zim"] = 1200
p = inst.piano("fonte_wikimed")
res = inst.esegui(p)
part = part_path(med)
verifica("connessione chiusa a metà: errore e .part conservato",
         res["esito"] == "errore" and part.exists() and part.stat().st_size == 1200,
         f"{res} {part.exists() and part.stat().st_size}")
p = inst.piano("fonte_wikimed")
verifica("la proposta conta solo il resto", p.byte == 800, str(p.byte))
n_req = len(srv.richieste)
res = inst.esegui(p)
ranges = [rg for m, u, rg in srv.richieste[n_req:] if m == "GET" and u.endswith("medicine_nopic_2026-07.zim")]
verifica("ripresa: chiede «bytes=1200-» e finisce con il checksum giusto",
         res["esito"] == "ok" and ranges == ["bytes=1200-"]
         and med.read_bytes() == dati(2000, "med"), f"{res} {ranges}")

# Server che ignora Range: si riparte da capo, il file è comunque giusto
srv.zim("wikiquote", "wikiquote_it_all_nopic_2026-07.zim", QUOTE_OLD)
fam_old = TMP / "biblioteca" / "x" / "wikiquote_it_all_nopic_2026-07.zim"
fc = FileCat(srv.url + "/zim/wikiquote/wikiquote_it_all_nopic_2026-07.zim", str(fam_old),
             len(QUOTE_OLD), hashlib.sha256(QUOTE_OLD).hexdigest())
fam_old.parent.mkdir(parents=True)
part_path(fam_old).write_bytes(QUOTE_OLD[:1000])
srv.ignora_range = True
from calliope.installa.scarica import scarica_file  # noqa: E402
import httpx  # noqa: E402
scarica_file(httpx.Client(), fc, ("127.0.0.1",))
srv.ignora_range = False
verifica("server che ignora Range: riparte da capo, file giusto", fam_old.read_bytes() == QUOTE_OLD)

# Reindirizzamento verso un host fuori dal catalogo: rifiutato
srv.rimanda["/sherpa/fuori.onnx"] = "http://localhost:9/fuori.onnx"
try:
    scarica_file(httpx.Client(), FileCat(srv.url + "/sherpa/fuori.onnx", str(TMP / "f.onnx"),
                                         10, None), ("127.0.0.1",))
    got = "scaricato"
except ErroreInstallazione as e:
    got = e.codice
verifica("rimando verso un host non ammesso: rifiutato", got == "origine_non_ammessa", got)

# ── annullo e avanzamento ──
SLOW = dati(400_000, "lento")
srv.zim("gutenberg", "gutenberg_it_all_2026-01.zim", SLOW)
srv.lento["/zim/gutenberg/gutenberg_it_all_2026-01.zim"] = 0.02
call("installa_proponi", {"azione": "fonte_gutenberg"}, 40)
r = call("installa_avvia", {"azione": "fonte_gutenberg"}, 41)
time.sleep(0.4)
r2 = call("installa_gestisci", {"azione": "stato"}, 42, Spk("Bianca", "familiare"))
verifica("a che punto è: percentuale e megabyte (anche a un familiare)",
         "per cento" in r2["risposta_finale"] and "Gutenberg" in r2["risposta_finale"],
         r2["risposta_finale"])
r3 = call("installa_gestisci", {"azione": "annulla"}, 43, Spk("Bianca", "familiare"))
verifica("annulla da un familiare: rifiutato", r3["ok"] is False and inst.occupato())
r3 = call("installa_gestisci", {"azione": "annulla"}, 44)
gut = TMP / "biblioteca" / "gutenberg_it_all_2026-01.zim"
item = inst.done.get(timeout=5)
verifica("annulla: fermo, .part resta per la ripresa, nessun annuncio",
         r3["ok"] and "riparto da lì" in r3["risposta_finale"] and not inst.occupato()
         and part_path(gut).exists() and not gut.exists() and item["esito"] == "annullato"
         and item["annuncia"] is False, r3["risposta_finale"])
srv.lento.clear()

# ── attivazione e annuncio: biblioteca, modello di chi parla ──
attivate = []
inst.attivatori["biblioteca"] = lambda: attivate.append("biblioteca") or True
r = call("installa_proponi", {"azione": "biblioteca_mini"}, 50)
verifica("Wikipedia ridotta: la proposta dice dell'indice dopo il download",
         "Dopo preparo l'indice per la ricerca, senza internet." in r["risposta_finale"],
         r["risposta_finale"])
call("installa_avvia", {"azione": "biblioteca_mini"}, 51)
for _ in range(1500):                      # download + indice in un processo a parte
    if not inst.occupato():
        break
    time.sleep(0.02)
item = inst.done.get(timeout=5)
msg = inst.completa(item)
mini_new = TMP / "biblioteca" / "wikipedia_it_all_mini_2026-10.zim"
verifica("biblioteca: scaricata, indice preparato, attivata senza riavvio, annuncio",
         attivate == ["biblioteca"] and "si può già usare" in msg and mini_new.exists()
         and pronto(mini_new), msg)
verifica("indice accanto: biblioteca/indici/<nome>.fts.sqlite, niente file temporanei",
         percorso_indice(mini_new) == TMP / "biblioteca" / "indici" /
         "wikipedia_it_all_mini_2026-10.fts.sqlite"
         and not list((TMP / "biblioteca" / "indici").glob("*.tmp")))
verifica("risolvi_zim: il file verificato più recente, con l'indice, vince su quello in "
         "configurazione", risolvi_zim(cfg.biblioteca_mini) == str(mini_new))
inst.attivatori["biblioteca"] = lambda: False
msg = inst.completa({**item})
verifica("attivazione non riuscita: «riavviami»", "riavvio" in msg, msg)

CAMPP = dati(5000, "cam")
srv.file("/sherpa/campp_finto.onnx", CAMPP)
inst.catalogo["modello_chi_parla"] = Azione(
    id="modello_chi_parla", titolo="il modello per riconoscere le voci", tipo="file",
    capacita="chi_parla", librerie=(), attivazione="riavvio", hosts=("127.0.0.1",),
    origine="dalle release di sherpa-onnx su GitHub",
    files=(FileCat(srv.url + "/sherpa/campp_finto.onnx", cfg.speaker_model, len(CAMPP),
                   hashlib.sha256(CAMPP).hexdigest()),))
r = call("installa_proponi", {"azione": "modello_chi_parla"}, 60)
verifica("modello di chi parla: la proposta dice del riavvio", "riavvio" in r["risposta_finale"],
         r["risposta_finale"])
call("installa_avvia", {"azione": "modello_chi_parla"}, 61)
aspetta()
msg = inst.completa(inst.done.get(timeout=5))
verifica("modello di chi parla: «riavviami quando vuoi»", "riavviami" in msg
         and Path(cfg.speaker_model).read_bytes() == CAMPP, msg)
p = inst.piano("modello_chi_parla")
verifica("file piccolo già presente: checksum rifatto, niente da fare", p.codice == "gia_fatto")
Path(cfg.speaker_model).write_bytes(dati(5000, "rovinato"))
p = inst.piano("modello_chi_parla")
verifica("file presente ma rovinato: da riscaricare", p.ok, p.frase)

# ── aggiornamento e pulizia ──
old_mini = TMP / "biblioteca" / "wikipedia_it_all_mini_2026-08.zim"
old_mini.write_bytes(b"vecchio")
srv.zim("wikipedia", "wikipedia_it_all_mini_2026-12.zim", mini_wikipedia())
p = inst.piano("biblioteca_aggiorna")
verifica("aggiornamento: solo le famiglie con una versione più nuova",
         p.ok and [Path(f.dest).name for f in p.files] == ["wikipedia_it_all_mini_2026-12.zim"],
         p.frase)
fasi = set()
res = inst.esegui(p, avanz=lambda fase, n, tot=None: fasi.add(fase))
mini_dic = TMP / "biblioteca" / "wikipedia_it_all_mini_2026-12.zim"
verifica("aggiornamento scaricato, verificato e indicizzato (fasi scarico, verifico, indice)",
         res["esito"] == "ok" and pronto(mini_dic) and {"scarico", "indice"} <= fasi
         and risolvi_zim(cfg.biblioteca_mini) == str(mini_dic), f"{res} {fasi}")

# Un aggiornamento il cui indice non si costruisce (file finto): resta in uso il vecchio
srv.zim("wikipedia", "wikipedia_it_all_mini_2027-01.zim", dati(3000, "rotto"))
p = inst.piano("biblioteca_aggiorna")
res = inst.esegui(p)
rotto = TMP / "biblioteca" / "wikipedia_it_all_mini_2027-01.zim"
verifica("indice non riuscito: errore detto, file verificato ma NON in uso",
         res["esito"] == "errore" and res.get("codice") == "indice"
         and "preparare l'indice" in res["frase"] and Path(str(rotto) + ".verificato").exists()
         and risolvi_zim(cfg.biblioteca_mini) == str(mini_dic), str(res))
p = inst.piano("biblioteca_aggiorna")
verifica("aggiornamento già scaricato, senza indice: si propone solo l'indice, niente download",
         p.ok and not p.files and p.indici == [rotto] and "entrano in uso solo con il loro "
         "indice" in p.frase and p.frase.endswith("Procedo?"), p.frase)
p = inst.piano("biblioteca_indice")
verifica("biblioteca_indice: propone l'indice della versione nuova in attesa",
         p.ok and p.indici == [rotto] and "senza internet" in p.frase, p.frase)
rotto.unlink()
Path(str(rotto) + ".verificato").unlink()
for k in [k for k in srv.files if "mini_2027-01" in k]:       # via anche dal sito finto
    srv.files.pop(k)

vecchi = [q.name for q in versioni_vecchie(cfg)]
verifica("file superati: 2026-08 e 2026-10 del mini", vecchi == [
    "wikipedia_it_all_mini_2026-08.zim", "wikipedia_it_all_mini_2026-10.zim"], str(vecchi))
indici = TMP / "biblioteca" / "indici"
orfano = indici / "wikipedia_it_all_mini_2025-01.fts.sqlite"
orfano.write_bytes(b"orfano")
tmp_vecchio = indici / "wikipedia_it_all_mini_2026-12.fts.sqlite.tmp"
tmp_vecchio.write_bytes(b"a meta")
os.utime(tmp_vecchio, (time.time() - 7200, time.time() - 7200))
tmp_nuovo = indici / "vikidia_it_all_nopic_2026-08.fts.sqlite.tmp"
tmp_nuovo.write_bytes(b"in corso")
r = call("installa_proponi", {"azione": "pulizia"}, 70)
verifica("pulizia: proposta con lo spazio liberato", r["ok"] and "Li cancello?"
         in r["risposta_finale"], r["risposta_finale"])
r = call("installa_avvia", {"azione": "pulizia"}, 71)
verifica("pulizia: fatta solo dopo il sì, il file nuovo resta",
         r["ok"] and not old_mini.exists() and not mini_new.exists()
         and Path(risolvi_zim(cfg.biblioteca_mini)).exists(), r["risposta_finale"])
verifica("pulizia: via anche gli indici dei file superati, gli orfani e i .tmp vecchi; "
         "restano l'indice in uso e un .tmp recente",
         not percorso_indice(mini_new).exists() and not orfano.exists()
         and not tmp_vecchio.exists() and tmp_nuovo.exists() and pronto(mini_dic),
         str(sorted(q.name for q in indici.iterdir())))
tmp_nuovo.unlink()

# ── indice che manca o è vecchio: capacità, proposta, costruzione a voce ──
from calliope import biblioteca_indice  # noqa: E402
cap = capacita.check_biblioteca(cfg)
verifica("capacità con l'indice pronto: niente «ricerca ridotta»",
         "ridotta" not in cap["motivo"] and cap["dettagli"]["indici"]["mini"] == "ok",
         str(cap))
percorso_indice(mini_dic).unlink()
cap = capacita.check_biblioteca(cfg)
verifica("indice mancante → attiva ma «ricerca ridotta», passo: prepara l'indice",
         cap["stato"] == "attiva" and "ricerca ridotta" in cap["motivo"]
         and "prepara l'indice della biblioteca" in cap["prossimo_passo"]
         and "--installa biblioteca_indice" in cap["prossimo_passo"], str(cap))
r = call("installa_proponi", {"azione": "biblioteca_mini"}, 72)
verifica("«scarica Wikipedia ridotta» con il file già presente ma senza indice → propone "
         "l'indice", r["ok"] and "c'è già, ma senza l'indice" in r["risposta_finale"]
         and "Preparo l'indice" in r["risposta_finale"], r["risposta_finale"])
inst._offerte.clear()
r = call("installa_proponi", {"azione": "biblioteca_indice"}, 73)
verifica("biblioteca_indice: proposta con tempo e spazio, senza internet",
         r["ok"] and "Preparo l'indice di ricerca per Wikipedia ridotta" in r["risposta_finale"]
         and "senza internet" in r["risposta_finale"]
         and r["risposta_finale"].endswith("Procedo?"), r["risposta_finale"])
while not inst.done.empty():          # la pulizia di prima (sincrona, solo nel registro)
    inst.done.get_nowait()
r = call("installa_avvia", {"azione": "biblioteca_indice"}, 74)
verifica("biblioteca_indice: «Ho cominciato a preparare l'indice»",
         r["ok"] and "preparare l'indice" in r["risposta_finale"], r["risposta_finale"])
for _ in range(1500):
    if not inst.occupato():
        break
    time.sleep(0.02)
item = inst.done.get(timeout=5)
attivate.clear()
inst.attivatori["biblioteca"] = lambda: attivate.append("biblioteca") or True
msg = inst.completa(item)
verifica("biblioteca_indice: costruito, biblioteca riattivata, «Ho finito di preparare»",
         pronto(mini_dic) and attivate == ["biblioteca"] and "Ho finito di preparare" in msg,
         msg)
p = inst.piano("biblioteca_indice")
verifica("biblioteca_indice: già pronto → niente da fare", p.codice == "gia_fatto"
         and "già pronto" in p.frase, p.frase)
# Versione vecchia dell'estrattore: l'indice non vale più
import sqlite3  # noqa: E402
con = sqlite3.connect(percorso_indice(mini_dic))
con.execute("UPDATE meta SET valore='0' WHERE chiave='versione'")
con.commit()
con.close()
p = inst.piano("biblioteca_indice")
verifica("indice di una versione vecchia → da rifare", p.ok and p.indici == [mini_dic]
         and stato_indice(mini_dic)[0] == "versione", p.frase)
res = inst.esegui(p)
verifica("indice rifatto", res["esito"] == "ok" and pronto(mini_dic), str(res))
p = inst.piano("biblioteca_aggiorna")
verifica("già all'ultima versione", p.codice == "gia_fatto" and "ultima versione" in p.frase,
         p.frase)

# ── modello di Ollama (finto) ──
while not inst.done.empty():          # la pulizia di prima (sincrona, solo nel registro)
    inst.done.get_nowait()
srv.ollama_modelli = []
r = call("installa_proponi", {"azione": "modello_llm"}, 80)
verifica("Ollama: proposta per il modello della configurazione", r["ok"]
         and "modello-finto:1b" in r["risposta_finale"], r["risposta_finale"])
call("installa_avvia", {"azione": "modello_llm"}, 81)
aspetta()
item = inst.done.get(timeout=5)
verifica("Ollama: /api/pull solo con il nome della configurazione",
         srv.pull_fatti == ["modello-finto:1b"] and item["esito"] == "ok", str(item))
srv.pull_errore = "file does not exist"
srv.ollama_modelli = []
call("installa_proponi", {"azione": "modello_llm"}, 82)
call("installa_avvia", {"azione": "modello_llm"}, 83)
aspetta()
item = inst.done.get(timeout=5)
msg = inst.completa(item)
verifica("Ollama: errore detto", item["esito"] == "errore" and "Non sono riuscita" in msg, msg)
srv.pull_errore = None
cfg_giu = cfg_finta(llm_native_url="http://127.0.0.1:9")
p = Installazioni(cfg_giu, origini=ORIGINI).piano("modello_llm")
verifica("Ollama giù: niente proposta", p.codice == "ollama_giu", p.frase)

# ── terminale: stesso codice, conferma da tastiera ──
from calliope.stato import installa as installa_terminale  # noqa: E402
srv.zim("wikivoyage", "wikivoyage_it_all_nopic_2026-09.zim", dati(1500, "viaggi"))
out = []
voy = TMP / "biblioteca" / "wikivoyage_it_all_nopic_2026-09.zim"
cfg.turn_log_dir = str(TMP / "registro")
rc = installa_terminale(cfg, "fonte_wikivoyage", inst=inst, input_fn=lambda _: "n",
                        out=out.append)
verifica("terminale: «n» → niente", rc == 0 and not voy.exists() and "non scarico" in out[-1])
rc = installa_terminale(cfg, "fonte_wikivoyage", inst=inst, input_fn=lambda _: "s",
                        out=out.append)
log = (TMP / "registro").glob("turni-*.jsonl")
righe = [json.loads(x) for f in log for x in f.read_text(encoding="utf-8").splitlines()]
verifica("terminale: «s» → scaricato, verificato e nel registro dei turni",
         rc == 0 and voy.exists() and righe and righe[-1]["installazione"]["esito"] == "ok"
         and righe[-1]["origine"] == "terminale", str(out[-1:]))
rc = installa_terminale(cfg, "azione_inventata", inst=inst, input_fn=lambda _: "s",
                        out=out.append)
verifica("terminale: azione fuori catalogo → rifiutata", rc == 1 and "catalogo" in out[-1])


# ── giro completo con Brain: proposta, «sì», avvio; e il modello che concatena ──
class Backend:
    def __init__(self, copione):
        self.copione = list(copione)

    def stream(self, messages, tools):
        self.visti = messages
        yield from self.copione.pop(0)


srv.zim("wikiversity", "wikiversity_it_all_nopic_2026-01.zim", dati(1000, "lez"))


def brain_con(copione):
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.tool_ctx = ctx
    b.backend = Backend(copione)
    ctx.speaker_ctx = Spk("Dario", "amministra")
    return b


c_prop = {"id": "c1", "name": "installa_proponi", "arguments": {"azione": "fonte_wikiversita"}}
c_avvia = {"id": "c2", "name": "installa_avvia", "arguments": {"azione": "fonte_wikiversita"}}
b = brain_con([[("calls", [c_prop])], [("calls", [c_avvia])]])
detto = "".join(b.stream_reply("Scarica Wikiversità", "amministra"))
verifica("Brain: la proposta chiude il turno con la domanda e l'azione in sospeso",
         detto.endswith("Procedo?") and b.has_pending(), detto)
ctx.speaker_ctx = Spk("Dario", "amministra")      # «sì, procedi»: la voce si riconosce
detto = "".join(b.stream_reply("Sì, procedi pure.", "amministra"))
aspetta()
verifica("Brain: «sì» → avvio nel turno dopo",
         "Ho cominciato" in detto and (TMP / "biblioteca" /
                                       "wikiversity_it_all_nopic_2026-01.zim").exists(), detto)
while not inst.done.empty():
    inst.done.get_nowait()
srv.zim("wikibooks", "wikibooks_it_all_nopic_2026-07.zim", dati(1000, "man"))
c_prop2 = {"id": "c1", "name": "installa_proponi", "arguments": {"azione": "fonte_wikibooks"}}
c_avvia2 = {"id": "c2", "name": "installa_avvia", "arguments": {"azione": "fonte_wikibooks"}}
b = brain_con([[("calls", [c_prop2, c_avvia2])], [("text", "Fatto.")]])
detto = "".join(b.stream_reply("Scarica Wikibooks", "amministra"))
aspetta()
verifica("Brain: proposta e avvio nella stessa risposta → l'avvio è rifiutato",
         not (TMP / "biblioteca" / "wikibooks_it_all_nopic_2026-07.zim").exists()
         and "installa_senza_offerta" in b.rules_fired(), f"{detto} {b.rules_fired()}")

srv.ferma()
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
