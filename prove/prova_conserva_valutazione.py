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
