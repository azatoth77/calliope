"""
Prova a secco della valutazione (18/10/2026, issue #173, decisione 0032): con
`conserva_valutazione_fino: "AAAA-MM-GG"` fino a quel giorno compreso si conservano testo e audio di
tutte le conversazioni, ospiti compresi (calliope/conserva.py, turnlog.py, stanza/tenuta.py,
stanza/banco.py, conversazioni.py).

- configurazione: vuota di serie; la data con o senza virgolette (YAML la legge come data); una
  data scritta male rifiutata (resta spento);
- registro dei turni: un turno di un ospite e uno della zona grigia con le parole e il segno
  `conserva: {testo: true, motivo: valutazione, di_serie: …}`; una riga di altri senza segno;
- voce: l'audio dell'ospite in `voce/_valutazione/ospiti/`, della zona grigia e dell'adulto senza
  consenso sotto il suo id; quello di sempre (adulto col sì) resta nella sua cartella, senza segno;
  contrari sempre: frase di sfida, codice detto, scritto, frase ignorata, `conserva_voce: false`;
- contrari: interruttore vuoto, data passata (anche ieri), data scritta male → come oggi, niente
  dell'ospite su disco; la data di oggi vale (compresa);
- la scadenza: una riga nel log, una volta; i file restano, la rotazione li toglie dopo
  `turn_log_days`, e toglie la cartella di un profilo tolto (mai «ospiti» per questo);
- «dimentica» e `--svuota`: `svuota(persona)` toglie le sue frasi della valutazione, `svuota()`
  tutto; la revoca del consenso anche;
- la stanza, dal giro vero della corsia veloce e della lenta: il segmento di un ospite ha la riga
  nella tenuta (segnata, che la ricerca, i nomi e la guardia non vedono) e l'audio nel banco con
  `valutazione: true`, anche senza `stanza_audio_banco_giorni`; contrari: spenta, in pausa;
  «dimentica» del satellite, `--svuota` di una persona e di tutto;
- l'archivio delle conversazioni: l'ospite anche su disco (`ospite = 2`) che nessuna ricerca vede
  e che la pulizia dei non conservati lascia; contrario spento: niente su disco; `svuota`;
- la riga di `calliope stato`, dell'avvio e del cruscotto.

Nomi di fantasia. Tutto in una cartella temporanea. ~5–10 s.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # prova_stanza_lenta

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from calliope import conserva as C
from calliope.config import Config
from calliope.speaker_id import UserProfile
from calliope.turnlog import TurnLog

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    print(("OK  " if ok else "ERR ") + nome + ("" if ok else f"  → {dettaglio}"), flush=True)
    if not ok:
        errori += 1


class Registro:
    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((u for u in self.users.values() if u.id == pid), None)

    def save(self):
        pass


OGGI = datetime.date.today()
DOMANI = (OGGI + datetime.timedelta(days=1)).isoformat()
IERI = (OGGI - datetime.timedelta(days=1)).isoformat()
SR = 16000
AUDIO = (0.3 * np.sin(2 * np.pi * 220 * np.arange(SR) / SR)).astype(np.float32)
tmp = Path(tempfile.mkdtemp(prefix="calliope-valutazione-"))


def cfg_per(nome, fino="", **k):
    cfg = Config()
    cfg.turn_log_dir = str(tmp / nome / "registro")
    cfg.memory_db = str(tmp / nome / "memoria.db")
    cfg.turn_log_days = 60
    cfg.conserva_voce, cfg.conserva_voce_mb = True, 2000
    cfg.conserva_valutazione_fino = fino
    for a, v in k.items():
        setattr(cfg, a, v)
    return cfg


def nuova(nome, fino=""):
    amm = UserProfile(name="Primo", admin=True, id="p-amm")
    adu = UserProfile(name="Ginevra", id="p-adu")
    reg = Registro(amm, adu)
    cfg = cfg_per(nome, fino)
    log = []
    cons = C.Conservazione(cfg, reg, log=log.append)
    cons._ruotata_il = OGGI                        # niente rotazione in secondo piano
    tl = TurnLog(cfg.turn_log_dir, 60, conserva=cons)
    cons.turnlog = tl
    return cfg, reg, cons, tl, log


N = [0]


def turno(nome=None, modo="voce", livello="familiare", reg=None, **extra):
    N[0] += 1
    voce = None
    if nome:
        voce = {"nome": nome, "modo": modo, **extra.pop("voce", {})}
        p = reg.get(nome) if reg else None
        if p is not None:
            voce["id"] = p.id
    return {"inizio": f"{OGGI.isoformat()}T10:{N[0] // 60:02d}:{N[0] % 60:02d}.000",
            "livello": livello, "voce": voce, "testo": "il mio cane si chiama Fido",
            "esito": "risposta", "risposta": "Che bel nome.",
            "tool": [{"nome": "ricordo", "argomenti": {"testo": "Fido"}, "ok": True}], **extra}


def scrivi(cons, tl, rec, audio=AUDIO):
    cons.al_turno(rec, audio, SR)
    tl.write(rec)
    return rec


def righe(cfg):
    p = Path(cfg.turn_log_dir) / f"turni-{OGGI.isoformat()}.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() \
        else []


try:
    # ───────── configurazione ─────────
    import yaml
    from calliope.config import SEZIONI, _data_valida
    verifica("configurazione: vuota di serie (spento), nella sezione «registro»",
             Config().conserva_valutazione_fino == ""
             and "conserva_valutazione_fino" in SEZIONI["registro"])
    data_yaml = yaml.safe_load("x: 2026-11-30")["x"]
    verifica("configurazione: la data con e senza virgolette (YAML la legge come data)",
             _data_valida("2026-11-30") == "2026-11-30" and _data_valida(data_yaml) == "2026-11-30"
             and _data_valida("") == "" and _data_valida(None) == "")
    try:
        _data_valida("30/11/2026")
        rifiutata = False
    except ValueError:
        rifiutata = True
    verifica("configurazione, contrario: una data scritta male è rifiutata", rifiutata)
    from calliope.config import _apply_file
    tmp.mkdir(parents=True, exist_ok=True)
    risultati = []
    for testo in ("conserva_valutazione_fino: 2026-11-30\n",
                  "registro:\n  conserva_valutazione_fino: \"2026-11-30\"\n",
                  "conserva_valutazione_fino: 30/11/2026\n"):
        f = tmp / "locale.yaml"
        f.write_text(testo, encoding="utf-8")
        c = Config()
        _apply_file(c, str(f))
        risultati.append(c.conserva_valutazione_fino)
    verifica("configurazione: la riga del file locale, fuori sezione o in «registro»; scritta "
             "male resta spento", risultati == ["2026-11-30", "2026-11-30", ""], str(risultati))
    verifica("valutazione_attiva: oggi compreso, ieri no, vuoto e storta no",
             C.valutazione_attiva(SimpleNamespace(conserva_valutazione_fino=OGGI.isoformat()))
             and not C.valutazione_attiva(SimpleNamespace(conserva_valutazione_fino=IERI))
             and not C.valutazione_attiva(SimpleNamespace(conserva_valutazione_fino=""))
             and not C.valutazione_attiva(SimpleNamespace(conserva_valutazione_fino="presto")))

    # ───────── registro dei turni e voce, accesa ─────────
    cfg, reg, cons, tl, log = nuova("accesa", DOMANI)
    adu = reg.get("Ginevra")
    adu.voce_conservata = None                     # adulto senza consenso
    ospite = scrivi(cons, tl, turno(livello="ospite", caso="ospite"))
    grigia = scrivi(cons, tl, turno("Ginevra", modo="conversazione", reg=reg, caso="grigia"))
    senza = scrivi(cons, tl, turno("Ginevra", reg=reg, caso="senza_consenso"))
    amm = scrivi(cons, tl, turno("Primo", livello="amministra", reg=reg, caso="amm"))
    tl.write({"inizio": f"{OGGI.isoformat()}T11:00:00", "livello": "ospite",
              "testo": "foto.jpg", "voce": None, "caso": "altri_ospite"})
    r = {x["caso"]: x for x in righe(cfg)}
    verifica("turno di un ospite: il testo, la risposta e gli argomenti restano",
             r["ospite"]["testo"] == "il mio cane si chiama Fido"
             and r["ospite"]["risposta"] == "Che bel nome."
             and r["ospite"]["tool"][0].get("argomenti"), str(r["ospite"])[:300])
    verifica("…con il segno della valutazione e la regola di serie",
             r["ospite"].get("conserva") == {"testo": True, "motivo": "valutazione",
                                             "di_serie": "ospite"}
             and r["grigia"].get("conserva", {}).get("di_serie") == "voce_incerta",
             str(r["ospite"].get("conserva")))
    verifica("zona grigia: il testo resta", r["grigia"]["testo"] == "il mio cane si chiama Fido")
    verifica("una riga di altri senza segno, di un ospite: il testo resta",
             r["altri_ospite"]["testo"] == "foto.jpg", str(r["altri_ospite"]))
    verifica("la persona di casa: come di serie, senza segno",
             "conserva" not in r["amm"] and r["amm"]["testo"])
    vd = cons.voce_dir
    verifica("audio dell'ospite in voce/_valutazione/ospiti/, nello stesso formato",
             str(ospite.get("voce_file", "")).startswith("_valutazione/ospiti/")
             and (vd / ospite["voce_file"]).exists()
             and C.formato_wav((vd / ospite["voce_file"]).read_bytes()) == C.formato_wav(
                 C.wav_mulaw(AUDIO, SR)) and r["ospite"].get("voce_file") == ospite["voce_file"],
             str(ospite.get("voce_file")))
    verifica("audio della zona grigia e dell'adulto senza consenso sotto il suo id",
             str(grigia.get("voce_file", "")).startswith("_valutazione/p-adu/")
             and str(senza.get("voce_file", "")).startswith("_valutazione/p-adu/"),
             f"{grigia.get('voce_file')} {senza.get('voce_file')}")
    verifica("chi amministra: la voce dove sempre, senza segno",
             str(amm.get("voce_file", "")).startswith("p-amm/") and not amm.get("voce_valutazione"))
    prima = sum(1 for _ in vd.rglob("*.wav"))
    for nome, rec in (("frase di sfida", turno(livello="ospite", regole=["sfida_risposta"])),
                      ("codice detto", turno(livello="ospite", tool=[
                          {"nome": "schermo_gestisci", "argomenti": {"codice": "******"}}])),
                      ("scritto", turno(livello="ospite", canale="scritto")),
                      ("ignorata", turno(livello="ospite", esito="ignorato"))):
        cons.al_turno(rec, AUDIO, SR)
        verifica(f"voce, contrario anche in valutazione «{nome}»: non salvata",
                 not rec.get("voce_file"), str(rec)[:200])
    verifica("…nessun file in più", sum(1 for _ in vd.rglob("*.wav")) == prima)
    cfg.conserva_voce = False
    rec = turno(livello="ospite")
    cons.al_turno(rec, AUDIO, SR)
    verifica("voce, contrario: con conserva_voce: false niente audio, il testo sì",
             not rec.get("voce_file") and rec.get("conserva", {}).get("testo") is True)
    cfg.conserva_voce = True
    st = cons.stato()
    verifica("stato: la riga della valutazione e l'audio in più",
             st.get("valutazione", {}).get("attiva") is True
             and st["valutazione"]["voce_file"] == 3 and st["voce_persone"] == 1
             and "Valutazione: si conserva tutto fino al" in C.testo_stato(st),
             str(st.get("valutazione")))

    # ───────── la rotazione e la scadenza ─────────
    vecchio = vd / "_valutazione" / "ospiti" / (OGGI - datetime.timedelta(days=61)).isoformat()
    vecchio.mkdir(parents=True)
    (vecchio / "100000-000.wav").write_bytes(C.wav_mulaw(AUDIO, SR))
    tolto = vd / "_valutazione" / "p-tolto" / OGGI.isoformat()
    tolto.mkdir(parents=True)
    (tolto / "100000-000.wav").write_bytes(C.wav_mulaw(AUDIO, SR))
    cfg.conserva_valutazione_fino = IERI
    verifica("scadenza: non vale più, e lo dice il log una volta",
             not cons.valutazione() and not cons.valutazione()
             and sum("Valutazione finita" in m for m in log) == 1, str(log))
    rec = scrivi(cons, tl, turno(livello="ospite", caso="dopo"))
    verifica("dopo la scadenza: l'ospite senza parole né audio, come di serie",
             righe(cfg)[-1]["testo"] is None and not rec.get("voce_file"))
    out = cons.ruota(OGGI)
    verifica("rotazione: i file della valutazione restano (anche finita), via i giorni oltre "
             "turn_log_days e la cartella di un profilo tolto",
             (vd / ospite["voce_file"]).exists() and (vd / grigia["voce_file"]).exists()
             and not vecchio.exists() and not tolto.parent.exists()
             and (vd / amm["voce_file"]).exists(), str(out))
    # «dimentica», revoca e svuota
    n = cons.svuota("p-adu")["voce"]
    verifica("svuota --persona: via le sue frasi della valutazione",
             n >= 2 and not (vd / "_valutazione" / "p-adu").exists()
             and (vd / ospite["voce_file"]).exists(), str(n))
    cons.svuota()
    verifica("svuota di tutto: via anche quelle degli ospiti", not vd.exists()
             and not list(Path(cfg.turn_log_dir).glob("turni-*.jsonl")))

    # ───────── contrari: spenta, data passata ─────────
    for nome, fino in (("vuota", ""), ("passata", IERI), ("storta", "fine novembre")):
        cfg2, reg2, cons2, tl2, _ = nuova(nome, fino)
        o = scrivi(cons2, tl2, turno(livello="ospite", caso="o"))
        g = scrivi(cons2, tl2, turno("Ginevra", modo="conversazione", reg=reg2, caso="g"))
        rr = {x["caso"]: x for x in righe(cfg2)}
        verifica(f"contrario «{nome}»: niente dell'ospite né della zona grigia su disco",
                 rr["o"]["testo"] is None and rr["g"]["testo"] is None
                 and rr["o"]["conserva"] == {"testo": False, "motivo": "ospite"}
                 and not o.get("voce_file") and not g.get("voce_file")
                 and not (cons2.voce_dir / "_valutazione").exists(), str(rr["o"])[:200])
        if nome == "vuota":
            verifica("contrario «vuota»: lo stato non ha la riga della valutazione",
                     "valutazione" not in cons2.stato()
                     and "Valutazione" not in C.testo_stato(cons2.stato()))
    cfg3, reg3, cons3, tl3, _ = nuova("oggi", OGGI.isoformat())
    o = scrivi(cons3, tl3, turno(livello="ospite", caso="o"))
    verifica("la data di oggi vale (compresa)", righe(cfg3)[-1]["testo"]
             and str(o.get("voce_file", "")).startswith("_valutazione/ospiti/"))
    reg3.get("Ginevra").voce_conservata = True
    gg = scrivi(cons3, tl3, turno("Ginevra", modo="conversazione", reg=reg3))
    n = cons3.imposta_consenso(reg3.get("Ginevra"), False)
    verifica("revoca del consenso: via anche le sue frasi della valutazione",
             n >= 1 and not (cons3.voce_dir / gg["voce_file"]).exists())
    dopo = scrivi(cons3, tl3, turno("Ginevra", modo="conversazione", reg=reg3))
    dopo2 = scrivi(cons3, tl3, turno("Ginevra", reg=reg3))
    verifica("revoca: dopo il «no» la sua voce non si registra più nemmeno in valutazione "
             "(il testo sì)", not dopo.get("voce_file") and not dopo2.get("voce_file")
             and not (cons3.voce_dir / "_valutazione" / "p-adu").exists()
             and righe(cfg3)[-1]["testo"], f"{dopo.get('voce_file')} {dopo2.get('voce_file')}")
    reg3.get("Ginevra").voce_conservata = None
    mai = scrivi(cons3, tl3, turno("Ginevra", reg=reg3))
    verifica("…contrario: un consenso mai chiesto non ferma la valutazione",
             str(mai.get("voce_file", "")).startswith("_valutazione/p-adu/"))

    # ───────── la zona grigia di casa resta illeggibile (revisione della PR #178) ─────────
    from calliope.ciclo import Ciclo
    from calliope.conversazione import Conversazione as Conv0, turni as turni0
    from calliope.conversazioni import ArchivioConversazioni as Arch0
    for nome, fino in (("grigia_accesa", DOMANI), ("grigia_spenta", "")):
        cfg4, reg4, cons4, tl4, _ = nuova(nome, fino)
        rec = turno("Ginevra", modo="conversazione", reg=reg4)
        rec["testo"] = "la frase della zona grigia"
        finto = SimpleNamespace(s=SimpleNamespace(conserva=cons4), _meta_turno={})
        Ciclo._segna_conserva(finto, rec)                  # il giro vero del ciclo
        cons4.al_turno(rec)
        (tmp / nome).mkdir(parents=True, exist_ok=True)
        a4 = Arch0(tmp / nome / "conv.db", giorni=60, log=lambda m: None, avvia=False,
                   cfg=cfg4, conserva=cons4.conversazioni_su_disco)
        cv = Conv0("persona:p-adu")
        cv.owner, cv.last_turn_at = "p-adu", time.monotonic()
        ms = [{"role": "user", "content": "la frase della zona grigia",
               **({"_turno": finto._meta_turno} if finto._meta_turno else {})},
              {"role": "assistant", "content": "Va bene."}]
        cv.history += ms
        a4.archivia(cv, turni0(ms), "p-adu", "Ginevra", ospite=False)
        righe4 = a4.db.execute("SELECT c.ospite, t.domanda FROM turni t JOIN conversazioni c "
                               "ON c.id = t.conv").fetchall()
        verifica(f"zona grigia «{nome}»: il segno del ciclo c'è, chat() e cerca() non la danno, "
                 "l'archivio della persona non la ha",
                 finto._meta_turno.get("conserva") is False
                 and not a4.chat("p-adu") and not a4.cerca("zona grigia", "p-adu")["risultati"]
                 and (0, "la frase della zona grigia") not in righe4, f"{finto._meta_turno} {righe4}")
        if fino:
            verifica("zona grigia accesa: la copia della valutazione (ospite = 2) e il registro "
                     "dei turni con le parole; l'ombra degli eventi la tratta come anonima",
                     (2, "la frase della zona grigia") in righe4
                     and rec["conserva"]["motivo"] == "valutazione", str(righe4))
        a4.close()
    # L'ombra degli eventi con il registro su disco: le parole del turno della valutazione no
    from calliope.eventi.ombra import Ombra
    from calliope.eventi.registro import Disco, Registri

    def ombra_su_disco(nome, conserva):
        dpath = tmp / f"eventi-{nome}.db"
        dsk = Disco.file(str(dpath))
        rgs = Registri(dsk, log=lambda m: None)
        cvo = Conv0("persona:p-adu")
        cvo.history = [{"role": "user", "content": "la frase della zona grigia"},
                       {"role": "assistant", "content": "Il melograno è pronto."}]
        br = SimpleNamespace(conv=cvo, last_capito=None, last_sfida=False, redact=lambda x: x)
        cc = SimpleNamespace(brain=br, speaker=SimpleNamespace(played=[], interrupted=False),
                             corsia=SimpleNamespace(chiave="locale", nome="locale"),
                             speaker_ctx=None, rule=lambda n: None)
        om = Ombra(SimpleNamespace(eventi="ombra"), rgs, cc, log=lambda m: None)
        om.sente(("frase", {"testo": "Il melograno è pronto.", "atto": "risposta",
                            "autore": "esito", "canale": "voce"}))
        om.chiudi_turno({"esito": "risposta", "regole": [],
                         **({"conserva": conserva} if conserva else {})},
                        SimpleNamespace(text="la frase della zona grigia", scritto=None))
        rgs.scrivi()
        dsk.db.commit()
        byte = dpath.read_bytes() + (Path(str(dpath) + "-wal").read_bytes()
                                     if Path(str(dpath) + "-wal").exists() else b"")
        dsk.db.close()
        return b"melograno" in byte

    verifica("ombra degli eventi: le parole di un turno della valutazione mai sul disco del "
             "registro della persona (contrario: un turno di casa sì)",
             not ombra_su_disco("val", {"testo": True, "motivo": "valutazione",
                                        "di_serie": "voce_incerta"})
             and ombra_su_disco("casa", None))
    verifica("la riga dell'avvio e del cruscotto",
             C.testo_valutazione(cfg3).startswith("Valutazione: si conserva tutto fino al")
             and C.testo_valutazione(Config()) is None
             and "finita" in C.testo_valutazione(SimpleNamespace(conserva_valutazione_fino=IERI,
                                                                 turn_log_days=60)))
    from calliope.schermi.cruscotto import Cruscotto
    cr = Cruscotto.__new__(Cruscotto)
    cr.cfg = cfg3
    verifica("cruscotto: la valutazione accesa", cr._valutazione()["attiva"] is True
             and Cruscotto._valutazione(SimpleNamespace(cfg=Config())) is None)

    # ───────── l'archivio delle conversazioni ─────────
    from calliope.conversazione import Conversazione, turni as turni_conv
    from calliope.conversazioni import ArchivioConversazioni

    def archivio(nome, fino):
        cfg_a = cfg_per(nome, fino)
        (tmp / nome).mkdir(parents=True, exist_ok=True)
        c = C.Conservazione(cfg_a, Registro(UserProfile(name="Ginevra", id="p-adu")),
                            log=lambda m: None)
        return ArchivioConversazioni(tmp / nome / "conv.db", giorni=60, log=lambda m: None,
                                     avvia=False, cfg=cfg_a,
                                     conserva=c.conversazioni_su_disco), cfg_a

    def archivia(arch, chi, testo):
        conv = Conversazione(f"persona:{chi}" if chi else "ospite:studio")
        conv.owner, conv.last_turn_at = chi, time.monotonic()
        msgs = [{"role": "user", "content": testo}, {"role": "assistant", "content": "Va bene."}]
        conv.history += msgs
        arch.archivia(conv, turni_conv(msgs), chi, None, ospite=chi is None)
        return conv

    arch, cfg_a = archivio("arch_acceso", DOMANI)
    archivia(arch, None, "sono un ospite e il mio cane si chiama Fido")
    archivia(arch, "p-adu", "il mio libro preferito è il barone rampante")
    su_disco = arch.db.execute("SELECT persona, ospite FROM conversazioni").fetchall()
    verifica("archivio: l'ospite anche su disco, con ospite = 2", (None, 2) in su_disco
             and ("p-adu", 0) in su_disco and "Fido" in " ".join(
                 d for (d,) in arch.db.execute("SELECT domanda FROM turni")), str(su_disco))
    verifica("archivio: l'ospite resta nella sessione per la ricerca di chi amministra",
             arch.cerca("cane Fido", None, ospiti=True)["risultati"])
    rilegge = ArchivioConversazioni(tmp / "arch_acceso" / "conv.db", giorni=60,
                                    log=lambda m: None, avvia=False, cfg=cfg_a,
                                    conserva=lambda p: True)
    verifica("archivio: dopo un riavvio nessuna ricerca vede la copia della valutazione",
             not rilegge.cerca("cane Fido", None, ospiti=True)["risultati"]
             and not rilegge.cerca("cane Fido", "p-adu")["risultati"]
             and rilegge.cerca("barone rampante", "p-adu")["risultati"])
    rilegge.togli_non_conservate()
    verifica("archivio: la pulizia dei non conservati la lascia",
             (None, 2) in rilegge.db.execute("SELECT persona, ospite FROM conversazioni")
             .fetchall())
    rilegge.svuota()
    verifica("archivio: svuota la toglie", not rilegge.db.execute(
        "SELECT 1 FROM conversazioni").fetchall())
    rilegge.close()
    arch.close()
    arch, _ = archivio("arch_spento", "")
    archivia(arch, None, "sono un ospite e il mio cane si chiama Fido")
    verifica("archivio, contrario spento: niente dell'ospite su disco",
             not any(o for _p, o in arch.db.execute("SELECT persona, ospite FROM conversazioni")))
    arch.close()

    # ───────── la stanza: la corsia veloce, la lenta, la tenuta e il banco ─────────
    import prova_stanza_lenta as PL
    from calliope.stanza import banco as banco_mod
    from calliope.stanza.tenuta import Tenuta
    PL._patch_orologio()

    def stanza(nome, fino, **k):
        cfg_s = PL.cfg_base(registro=nome, conserva_valutazione_fino=fino, **k)
        b = banco_mod.Banco(cfg_s, log=lambda m: None)
        st, le = PL.nuova(cfg_s, banco=b)
        st.tenuta = Tenuta(PL.TMP / f"{nome}.db", registry=None, log=lambda m: None)
        st.tenuta.valutazione = lambda: C.valutazione_attiva(cfg_s)
        c = PL.Coll(30, "cucina")
        st._info[30] = {"nome": "cucina", "stanza": "cucina", "canale": "satellite"}
        s_o = PL.parla(st, c, 181, [(0.35, 2.0)], testi=("Buonasera a tutti.",) * 2)
        s_g = PL.parla(st, c, 183, [(0.12, 1.5)], testi=("Eh già.",) * 2)
        s_c = PL.parla(st, c, 185, [(0.1, 2.0)], testi=("Ciao Nicola.",) * 2)
        st.tenuta.attendi()
        le.giro(PL.tardi(cfg_s))
        st.tenuta.attendi()
        d = banco_mod.cartella(cfg_s)
        meta = {}
        for w in sorted(d.rglob("*.wav")) if d.exists() else ():
            m = json.loads(w.with_suffix(".json").read_text(encoding="utf-8"))
            meta[m["segmento"]] = m
        dischi = st.tenuta.db.execute("SELECT segmento, chi, sicurezza, persona, testo FROM "
                                      "righe").fetchall()
        return st, cfg_s, (s_o, s_g, s_c), meta, dischi

    st, cfg_s, (s_o, s_g, s_c), meta, dischi = stanza("st_accesa", DOMANI)
    seg_disco = {r[0]: r for r in dischi}
    verifica("stanza: il segmento dell'ospite ha la riga nella tenuta, segnata",
             s_o in seg_disco and seg_disco[s_o][2] == "valutazione"
             and seg_disco[s_o][4] == "Buonasera a tutti.", str(dischi))
    verifica("stanza: …e l'audio nel banco con «valutazione», senza stanza_audio_banco_giorni",
             s_o in meta and meta[s_o].get("valutazione") is True
             and not (banco_mod.cartella(cfg_s) / banco_mod.ACCESO).exists(), str(meta.keys()))
    verifica("stanza: la riga della persona di casa come di serie (sicurezza voce)",
             seg_disco.get(s_c, (None,) * 3)[2] == "voce" and seg_disco[s_c][3] == "p-carlo")
    verifica("stanza: anche l'audio di casa senza l'eccezione del banco, con la persona",
             s_c in meta and meta[s_c].get("valutazione") is True
             and meta[s_c]["persone"] == ["p-carlo"], str(meta.get(s_c)))
    trov = st.tenuta.cerca(radici=["buonasera"], recenti=True, sats=["30"])
    verifica("stanza: la ricerca non vede le righe della valutazione (solo quelle di sempre)",
             trov and all(r["sicurezza"] == "voce" for r in trov)
             and not any(r["testo"] == "Buonasera a tutti." for r in trov),
             str([(r["chi"], r["sicurezza"]) for r in trov]))
    verifica("stanza, contrario: in pausa il banco non salva niente nemmeno in valutazione",
             st.lenta.banco.salva(30, {}, {"segmento": 999}, b"\0\0" * SR, SR,
                                  {"chi": "ignoto", "sicurezza": "nessuna", "testo": "x"}, [],
                                  in_pausa=True) is None)
    verifica("stanza: i conteggi dicono le righe della valutazione",
             st.tenuta.conteggi().get("righe_valutazione") == 1, str(st.tenuta.conteggi()))
    n = banco_mod.svuota(cfg_s, "p-carlo")
    resto = {json.loads(j.read_text(encoding="utf-8")).get("segmento")
             for j in banco_mod.cartella(cfg_s).rglob("*.json")}
    verifica("stanza: --svuota --persona toglie i suoi segmenti, quello dell'ospite resta",
             n >= 1 and s_c not in resto and s_o in resto, f"{n} {resto}")
    st.tenuta.dimentica(30)
    verifica("stanza: «dimentica» del satellite toglie anche le righe della valutazione",
             not st.tenuta.db.execute("SELECT 1 FROM righe").fetchall())
    st.tenuta.chiudi()
    st.chiudi()

    # ───────── la frase di sfida e i codici fuori anche dalla stanza (PR #178) ─────────
    import types
    from calliope.ciclo import Ciclo

    def ciclo_finto(st, cfg_s, modo):
        f = SimpleNamespace()
        f.s = SimpleNamespace(stanza=st, registry=PL.Voci(), cfg=cfg_s)
        f.rec = {"voce": {"nome": "Carlo", "modo": modo}}
        f.speaker_ctx = SimpleNamespace(sfida=None, conoscente=None)
        f.listener = SimpleNamespace(started_at=time.monotonic() - 2.0,
                                     ended_at=time.monotonic() - 0.5)
        f._stanza_dove = lambda: (30, None)
        f.regole = []
        f.brain = SimpleNamespace(rules_fired=lambda: list(f.regole),
                                  redact=lambda x: x.replace("123456", "******")
                                  if isinstance(x, str) else x)
        f._ripulisci_per_registro = types.MethodType(Ciclo._ripulisci_per_registro, f)
        return f

    def nuovo_turno(testo, detto):
        return SimpleNamespace(text=testo, scritto=None, said=[detto], non_rivolta=False,
                               stanza_seq=None, stanza_esito_fatto=False)

    for nome, fino, modo in (("sf_grigia", DOMANI, "conversazione"), ("sf_casa", "", "voce")):
        cfg_s = PL.cfg_base(registro=nome, conserva_valutazione_fino=fino, stanza_contesto=True,
                            stanza_audio_banco_giorni=7)
        st, le = PL.nuova(cfg_s, banco=banco_mod.Banco(cfg_s, log=lambda m: None))
        st.tenuta = Tenuta(PL.TMP / f"{nome}.db", registry=None, log=lambda m: None)
        st.tenuta.valutazione = lambda c=cfg_s: C.valutazione_attiva(c)
        st._info[30] = {"nome": "cucina", "stanza": "cucina", "canale": "satellite"}
        f = ciclo_finto(st, cfg_s, modo)
        # 1. La richiesta: Calliope chiede la sfida
        t1 = nuovo_turno("cancella il documento", "Per conferma ripeti: girasole, treno.")
        Ciclo._stanza_turno(f, t1)
        f.regole = ["sfida_voce"]
        Ciclo._stanza_esito(f, t1, {**f.rec, "esito": "risposta", "testo": t1.text,
                                    "regole": ["sfida_voce"]})
        # 2. La risposta ripetuta, con la sfida in attesa
        f.speaker_ctx.sfida = SimpleNamespace(scaduta=lambda: False)
        f.regole = []
        t2 = nuovo_turno("girasole treno sette", "Fatto.")
        Ciclo._stanza_turno(f, t2)
        f.regole = ["sfida_risposta"]
        Ciclo._stanza_esito(f, t2, {**f.rec, "esito": "risposta",
                                    "testo": "(frase di conferma)",
                                    "regole": ["sfida_risposta"]})
        # 3. Un codice detto: il registro dei turni l'ha già tolto
        f.speaker_ctx.sfida = None
        f.regole = []
        t3 = nuovo_turno("il codice è 123456", "Abbinato.")
        Ciclo._stanza_turno(f, t3)
        Ciclo._stanza_esito(f, t3, {**f.rec, "esito": "risposta",
                                    "testo": "il codice è ******", "regole": []})
        st.tenuta.attendi()
        testi = [r[0] for r in st.tenuta.db.execute("SELECT testo FROM righe ORDER BY id")]
        tutto = " ".join(testi) + " " + " ".join(str(e.dati.get("testo"))
                                                 for e in st.registro(30).eventi())
        verifica(f"sfida «{nome}»: né le parole della sfida né il codice nella stanza, in "
                 "memoria e sul disco",
                 testi and "girasole" not in tutto and "123456" not in tutto
                 and "(frase di conferma)" in testi and "il codice è ******" in testi
                 and any("ripeti: …" in x for x in testi), str(testi))
        verifica(f"sfida «{nome}»: il banco salta il segmento nel tratto della sfida",
                 st.segreto_in(30, time.time() - 1.5, time.time() - 1.0)
                 and st.lenta.banco.salva(30, {}, {"segmento": 777, "inizio": time.time() - 1.5,
                                                   "fine": time.time() - 1.0},
                                          b"\0\0" * SR, SR,
                                          {"chi": "persona:p-carlo", "sicurezza": "voce",
                                           "testo": "x"}, [], segreto=True) is None
                 and st.lenta.banco.saltati.get("segreto") == 1)
        st.tenuta.chiudi()
        st.chiudi()

    # ───────── i conoscenti: --persona e «dimentica» (PR #178) ─────────
    cfg_k = PL.cfg_base(registro="conoscente", conserva_valutazione_fino=DOMANI)
    bk = banco_mod.Banco(cfg_k, log=lambda m: None)
    rk = {"chi": "conoscente:k1", "sicurezza": "voce", "testo": "Piacere, Marco.", "nome": "Marco"}
    for seg in (501, 502):
        bk.salva(30, {}, {"segmento": seg, "inizio": time.time() - 3600 + seg}, b"\0\0" * SR, SR,
                 rk, [])
    bk.salva_blocco(30, {}, {"blocco": 9, "inizio": time.time() - 3000}, [rk], "Piacere, Marco.",
                    ["Piacere, Marco."])
    metas = [json.loads(j.read_text(encoding="utf-8"))
             for j in banco_mod.cartella(cfg_k).rglob("*.json")]
    blocco = next((m for m in metas if m.get("tipo") == "blocco"), {})
    verifica("conoscente: segmenti e blocco con «conoscente:k1» e il segno della valutazione",
             all(m.get("persone") == ["conoscente:k1"] and m.get("valutazione") for m in metas)
             and blocco and len(metas) == 3, str(metas)[:300])
    verifica("conoscente: --persona con l'id nudo toglie i suoi segmenti",
             banco_mod.svuota(cfg_k, "k1") == 2)
    resto = list(banco_mod.cartella(cfg_k).rglob("*.json"))
    verifica("…e anche il blocco", not resto, str(resto))
    bk.salva(30, {}, {"segmento": 503, "inizio": time.time() - 500}, b"\0\0" * SR, SR, rk, [])
    ck = C.Conservazione(cfg_k, Registro(), log=lambda m: None)
    ck.conoscente = lambda pid: SimpleNamespace(id=pid, tipo="conoscente") if pid == "k1" else None
    r = ck.conoscente_tolto("k1")
    verifica("conoscente: «dimentica» (conoscente tolto) toglie il suo audio dal banco",
             r is not None and r.get("stanza_banco") == 1
             and not list(banco_mod.cartella(cfg_k).rglob("*.wav")), str(r))

    for nome, fino in (("st_spenta", ""), ("st_passata", IERI)):
        st, cfg_s, (s_o, s_g, _c), meta, dischi = stanza(nome, fino)
        verifica(f"stanza, contrario «{nome}»: niente dell'ospite su disco, né audio",
                 not meta and not any(r[0] == s_o for r in dischi)
                 and not any(r[2] == "valutazione" for r in dischi), f"{dischi} {list(meta)}")
        st.tenuta.chiudi()
        st.chiudi()
    shutil.rmtree(PL.TMP, ignore_errors=True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
