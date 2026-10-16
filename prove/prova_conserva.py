import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della conservazione dei dati (12/10/2026, calliope/conserva.py, decisione 0028 T1;
dal 16/10 la decisione 0031: i minori di casa come gli adulti, issue #104).

- `decidi`, il solo posto: persona di casa riconosciuta sì, **minore compreso** (testo, eventi,
  conversazioni); ospite e zona grigia no (testo); nel dubbio tra un adulto e un minore il testo
  sì e la voce no; la voce solo sopra soglia, senza compagnia, con il consenso (chi amministra sì
  finché non dice no, gli altri adulti solo dopo il loro «sì», un minore solo col «sì» di un
  tutore), mai con `conserva_voce: false`;
- registro dei turni: le parole restano per adulti e minori (dal profilo o dalla fascia) e nel
  dubbio con un minore; ospiti e zona grigia senza parole (restano i numeri e quante parole);
- voce: μ-law che si rilegge (errore piccolo), un file per frase nella cartella della persona,
  permessi 600/700 fuori da Windows; mai per ospite, adulto senza consenso, minore senza il sì di
  un tutore, scritto, frase ignorata, compagnia, dubbio con un minore, frase di sfida, codice
  detto; il minore col sì del tutore sì;
- consenso: il «sì» salvato nel profilo (per un minore con il tutore che l'ha dato); la revoca
  cancella le registrazioni;
- rotazione: giorni vecchi, persone senza più il diritto, tetto di spazio; il minore col sì del
  tutore resta;
- il registro dei turni di prima ripulito una volta (segno nella cartella): le parole del minore
  restano, quelle dell'ospite no;
- svuotare: una persona (voce, parole nei turni, eventi) e tutto;
- eventi: i registri di adulti e minori su disco e ripresi dopo un riavvio; quelli degli ospiti
  no, e la rotazione li toglie; le parole di un turno incerto restano solo in memoria
  (`senza_parole`); `dati_del_turno` su disco con nomi e lunghezze;
- il tool `dati_conservati`: ospite, scritto, zona grigia rifiutati; domanda e «sì»; revoca; il
  minore che dà o revoca da solo il consenso rifiutato, il tutore che lo dà con la persona e il
  «sì», un adulto non tutore rifiutato; «svuota» solo per chi amministra, con la domanda;
- da terminale: `python -m calliope.conserva` (conteggi) e `--svuota --persona` (anche di un
  minore: turni, eventi, conversazioni, voce);
- l'archivio delle conversazioni (12/10 sera): su disco l'adulto e il minore, ospite e turno
  incerto no (l'ospite nella sessione in memoria), conversazione in corso salvata, rotazione delle
  righe di prima (il minore resta), tenuta di `turn_log_days`, svuota e conteggi.

Nomi di fantasia. Tutto in una cartella temporanea. ~1 s.
"""

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
from calliope.eventi.registro import Disco, Registri
from calliope.eventi.tipi import CAMPI_TESTO, TIPI, Evento, per_disco, senza_parole
from calliope.speaker_id import UserProfile
from calliope.tools.conserva import _dati_conservati, conserva_specs
from calliope.turnlog import TurnLog

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    print(("OK  " if ok else "ERR ") + nome + ("" if ok else f"  → {dettaglio}"))
    if not ok:
        errori += 1


class Registro:
    """I profili, come SpeakerRegistry, senza modelli."""

    def __init__(self, *profili):
        self.users = {p.name: p for p in profili}
        self.salvato = 0

    def get(self, nome):
        return self.users.get(nome)

    def by_id(self, pid):
        return next((u for u in self.users.values() if u.id == pid), None)

    def find(self, nome):
        return next((n for n in self.users if n.lower() == str(nome).lower()), None)

    def save(self):
        self.salvato += 1


def profili():
    oggi = datetime.date.today()
    amm = UserProfile(name="Primo", admin=True, id="p-amm")
    adulto = UserProfile(name="Ginevra", id="p-adu")
    minore = UserProfile(name="Leo", id="p-min",
                         nascita=f"{oggi.year - 10}-01-15", tutori=["p-amm"])
    return amm, adulto, minore


tmp = Path(tempfile.mkdtemp(prefix="calliope-conserva-"))
try:
    amm, adulto, minore = profili()
    reg = Registro(amm, adulto, minore)

    # ───────── decidi ─────────
    verifica("adulto dalla voce: testo sì", C.decidi(adulto, "testo", "voce").ok)
    verifica("adulto, frase breve: testo sì", C.decidi(adulto, "testo", "breve").ok)
    # Dal 16/10 (decisione 0031) il minore di casa come un adulto
    verifica("minore: testo, eventi e conversazioni sì (16/10, decisione 0031)",
             all(C.decidi(minore, c, "voce").ok for c in ("testo", "eventi", "conversazioni"))
             and C.decidi(minore, "testo", "voce").motivo == "minore")
    verifica("minore, contrario: la voce no senza il sì di un tutore",
             C.decidi(minore, "voce", "voce").motivo == "senza_consenso")
    minore.voce_conservata = True
    verifica("minore, contrario: un «sì» senza il tutore (il minore da solo) non vale",
             not C.decidi(minore, "voce", "voce") and not C.consenso_voce(minore))
    minore.voce_conservata_da = "p-amm"
    verifica("minore col «sì» di un tutore: voce sì", C.decidi(minore, "voce", "voce").ok)
    verifica("minore col «sì» del tutore, contrario: in compagnia o con una frase breve no",
             not C.decidi(minore, "voce", "voce", {"compagnia"})
             and not C.decidi(minore, "voce", "breve"))
    minore.voce_conservata = minore.voce_conservata_da = None
    # Il testo della stanza (14/10, decisione 0029 punto 5): con la tenuta accesa anche i minori
    # riconosciuti dalla voce (prove/prova_stanza_tenuta.py)
    verifica("la stanza sì anche per il minore con la voce, no nella zona grigia",
             C.decidi(minore, "stanza", "voce").ok
             and not C.decidi(minore, "stanza", "conversazione"))
    verifica("contrario: ospite, mai", not any(C.decidi(None, c, "voce") for c in C.COSE))
    verifica("dubbio con un minore (incerta, minore_vicino, minore_incerto): il testo sì",
             all(C.decidi(amm, "testo", "voce", {d}).ok for d in C.DUBBI_MINORE)
             and C.decidi(minore, "testo", "voce", {"incerta"}).ok)
    verifica("dubbio con un minore, contrario: la voce no",
             all(C.decidi(amm, "voce", "voce", {d}).motivo == "dubbio_minore"
                 for d in C.DUBBI_MINORE))
    verifica("proprietario incerto con un minore: il testo sì, la voce no",
             C.decidi(amm, "testo", "proprietario").ok
             and C.decidi(amm, "voce", "proprietario").motivo == "voce_incerta")
    verifica("contrario: zona grigia («conversazione») e nessun modo: testo no",
             not C.decidi(amm, "testo", "conversazione")
             and not C.decidi(minore, "testo", "conversazione")
             and not C.decidi(amm, "testo", None))
    verifica("chi amministra: voce sì senza averlo detto (scelta di partenza)",
             C.decidi(amm, "voce", "voce").ok)
    verifica("contrario: adulto senza consenso: voce no",
             C.decidi(adulto, "voce", "voce").motivo == "senza_consenso")
    adulto.voce_conservata = True
    verifica("adulto dopo il «sì»: voce sì", C.decidi(adulto, "voce", "voce").ok)
    verifica("contrario: voce con una frase breve (non certa): no",
             C.decidi(adulto, "voce", "breve").motivo == "voce_incerta")
    verifica("contrario: in compagnia: voce no, testo sì",
             not C.decidi(adulto, "voce", "voce", {"compagnia"})
             and C.decidi(adulto, "testo", "voce", {"compagnia"}).ok)
    verifica("contrario: conserva_voce false: voce no",
             C.decidi(adulto, "voce", "voce", cfg=SimpleNamespace(conserva_voce=False)).motivo
             == "spenta")
    amm.voce_conservata = False
    verifica("contrario: chi amministra che ha detto no: voce no",
             not C.decidi(amm, "voce", "voce"))
    amm.voce_conservata = None
    cresciuto = UserProfile(name="Ugo", id="p-ugo", voce_conservata=True,
                            voce_conservata_da="p-amm")
    verifica("contrario: un adulto col «sì» dato da un tutore quando era minore: voce no",
             C.decidi(cresciuto, "voce", "voce").motivo == "senza_consenso")
    cresciuto.voce_conservata_da = "p-ugo"
    verifica("…e col «sì» suo, sì", C.decidi(cresciuto, "voce", "voce").ok)
    verifica("minore per la sola fascia scritta a mano: minore",
             C.categoria(UserProfile(name="X", fascia="ragazzi")) == "minore")
    try:
        C.decidi(adulto, "foto")
        verifica("cosa sconosciuta: errore", False)
    except ValueError:
        verifica("cosa sconosciuta: errore", True)

    # ───────── registro dei turni ─────────
    cfg = Config()
    cfg.turn_log_dir = str(tmp / "registro")
    cfg.memory_db = str(tmp / "memoria.db")     # mai quella vera (svuota tutto, 12/10 sera)
    cfg.turn_log_days = 60
    cfg.conserva_voce, cfg.conserva_voce_mb = True, 2000
    cons = C.Conservazione(cfg, reg, log=lambda m: None)
    # La rotazione del giorno parte in secondo piano al primo salvataggio: qui la si chiama a
    # mano, quando serve (niente thread che corrono con la prova)
    cons._ruotata_il = datetime.date.today()
    log = TurnLog(cfg.turn_log_dir, 60, conserva=cons)
    cons.turnlog = log
    oggi = datetime.date.today().isoformat()

    def turno(nome, modo="voce", livello="familiare", testo="accendi la luce della cucina",
              **extra):
        voce = {"nome": nome, "modo": modo, **({"id": reg.get(nome).id} if reg.get(nome)
                                                else {}), **extra.pop("voce", {})}
        return {"inizio": f"{oggi}T10:00:0{len(extra) % 10}.000", "livello": livello,
                "voce": voce if nome else None, "testo": testo, "esito": "risposta",
                "risposta": "Fatto, luce accesa.",
                "tool": [{"nome": "casa_comando", "argomenti": {"comando": "accendi"},
                          "ok": True}], **extra}

    casi = {"adulto": turno("Ginevra"),
            "minore": turno("Leo"),
            "minore_fascia": turno("Ginevra", ascolto={"fascia": "ragazzi"}),
            "ospite": turno(None, livello="ospite"),
            "incerta": turno("Primo", livello="amministra",
                             voce={"incerta": ["Primo", "Leo"]}),
            "grigia": turno("Ginevra", modo="conversazione")}
    for k, r in casi.items():
        r["caso"] = k
        cons.al_turno(r)
        log.write(r)
    righe = {r["caso"]: r for r in (json.loads(x) for x in (
        Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(encoding="utf-8").splitlines())}
    for k in ("adulto", "minore", "minore_fascia", "incerta"):
        # Dal 16/10 (decisione 0031) il minore (dal profilo o dalla sola fascia nel turno) e il
        # dubbio tra un adulto e un minore tengono le parole come l'adulto
        r = righe[k]
        verifica(f"registro «{k}»: le parole, la risposta e gli argomenti restano",
                 r["testo"] == "accendi la luce della cucina"
                 and r["risposta"] == "Fatto, luce accesa." and r["tool"][0].get("argomenti")
                 and "conserva" not in r, str(r)[:300])
    for k in ("ospite", "grigia"):
        r = righe[k]
        verifica(f"registro, contrario «{k}»: niente parole, restano i numeri",
                 r["testo"] is None and r["risposta"] is None and r.get("testo_parole") == 5
                 and "argomenti" not in r["tool"][0] and r["tool"][0]["nome"] == "casa_comando",
                 str(r)[:300])
    verifica("il ciclo segna il motivo nel turno (letto dall'ombra degli eventi)",
             righe["grigia"]["conserva"] == {"testo": False, "motivo": "voce_incerta"}
             and righe["ospite"]["conserva"] == {"testo": False, "motivo": "ospite"}
             and "conserva" not in righe["adulto"] and "conserva" not in righe["minore"])
    # Righe scritte da altri (cassetto, schermi) senza il segno: decide la conservazione
    log.write({"inizio": f"{oggi}T11:00:00", "livello": "familiare", "testo": "foto.jpg",
               "voce": {"nome": "Leo", "modo": "schermo"}, "caso": "altri"})
    log.write({"inizio": f"{oggi}T11:00:01", "livello": "familiare", "testo": "foto.jpg",
               "voce": {"nome": None, "modo": "schermo"}, "caso": "altri_ospite"})
    ultime = [json.loads(x) for x in (Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
        encoding="utf-8").splitlines()][-2:]
    verifica("una riga di altri senza segno, di un minore → con le parole",
             ultime[0]["testo"] == "foto.jpg", str(ultime[0]))
    verifica("contrario: una riga di altri senza segno e senza nessuno → senza parole",
             ultime[1]["testo"] is None, str(ultime[1]))

    # ───────── voce ─────────
    sr = 16000
    tt = np.arange(sr * 2) / sr
    audio = (0.3 * np.sin(2 * np.pi * 220 * tt) + 0.05 * np.sin(2 * np.pi * 1300 * tt)).astype(
        np.float32)
    rec = turno("Ginevra")
    cons.al_turno(rec, audio, sr)
    f = rec.get("voce_file")
    verifica("voce dell'adulto con il sì: salvata nella sua cartella",
             bool(f) and f.startswith("p-adu/") and (cons.voce_dir / f).exists(), str(rec))
    if f:
        letto, sr2 = C.leggi_wav(cons.voce_dir / f)
        err = float(np.sqrt(np.mean((letto[:len(audio)] - audio) ** 2)))
        verifica("μ-law: si rilegge, 8 bit al campione, errore piccolo",
                 sr2 == sr and len(letto) == len(audio) and err < 0.01
                 and (cons.voce_dir / f).stat().st_size < len(audio) + 100, f"{err} {sr2}")
        if os.name == "posix":
            m = (cons.voce_dir / f).stat().st_mode & 0o777
            verifica("permessi del file 600", m == 0o600, oct(m))
        else:
            print("OK  permessi 600/700: solo su Linux (qui le ACL della cartella dell'utente)")
    rec = turno("Primo", livello="amministra")
    cons.al_turno(rec, audio, sr)
    verifica("chi amministra: voce salvata senza averlo detto", bool(rec.get("voce_file")))
    for nome, r in (("minore senza il sì di un tutore", turno("Leo")),
                    ("ospite", turno(None, livello="ospite")),
                    ("adulto senza consenso", turno("Ginevra")),
                    ("frase breve", turno("Primo", modo="breve")),
                    ("compagnia", turno("Primo", voce={"compagnia": {"voci": 2}})),
                    ("scritta", turno("Primo", modo="schermo", canale="scritto")),
                    ("ignorata", {**turno("Primo"), "esito": "ignorato"}),
                    ("incerta con un minore", turno("Primo", voce={"minore_vicino": "Leo"})),
                    ("frase di sfida", {**turno("Primo"), "regole": ["sfida_risposta"]}),
                    ("codice detto", {**turno("Primo"), "tool": [
                        {"nome": "schermo_gestisci", "argomenti": {"codice": "******"}}]})):
        if nome == "adulto senza consenso":
            adulto.voce_conservata = None
        cons.al_turno(r, audio, sr)
        verifica(f"voce, contrario «{nome}»: non salvata", not r.get("voce_file"), str(r)[:200])
        adulto.voce_conservata = True
    verifica("nessun file per il minore senza il sì del tutore",
             not (cons.voce_dir / "p-min").exists())
    # Il tutore ha detto sì (16/10, decisione 0031): la voce del minore si tiene
    cons.imposta_consenso(minore, True, da="p-amm")
    rec = turno("Leo")
    cons.al_turno(rec, audio, sr)
    verifica("voce del minore col «sì» del tutore: salvata nella sua cartella",
             bool(rec.get("voce_file")) and rec["voce_file"].startswith("p-min/")
             and minore.voce_conservata_da == "p-amm", str(rec)[:200])
    for nome, r in (("minore in un dubbio con un adulto",
                     turno("Leo", voce={"minore_incerto": "Leo"})),
                    ("minore in compagnia", turno("Leo", voce={"compagnia": {"voci": 2}}))):
        cons.al_turno(r, audio, sr)
        verifica(f"voce, contrario «{nome}»: non salvata, il testo sì",
                 not r.get("voce_file") and "conserva" not in r, str(r)[:200])
    # Dal ciclo: _scrivi_turno prende l'audio del turno di questo rec, poi il registro dei turni
    from calliope.ciclo import Ciclo
    finto = SimpleNamespace(s=SimpleNamespace(conserva=cons, cfg=cfg, turns=log), ombra=None,
                            _turno=SimpleNamespace(audio=audio, scritto=None))
    rec = turno("Primo", livello="amministra")
    Ciclo._scrivi_turno(finto, rec)
    scritta = [json.loads(x) for x in (Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
        encoding="utf-8").splitlines()][-1]
    verifica("ciclo: la voce del turno salvata e citata nel registro dei turni",
             bool(scritta.get("voce_file")) and (cons.voce_dir / scritta["voce_file"]).exists())
    finto._turno = SimpleNamespace(audio=audio, scritto={"testo": "x"})
    rec = turno("Primo", livello="amministra")
    Ciclo._scrivi_turno(finto, rec)
    verifica("ciclo, contrario: un turno scritto non ha audio", not rec.get("voce_file"))

    # ───────── consenso e revoca ─────────
    n = cons.registrazioni("p-adu")
    tolte = cons.imposta_consenso(adulto, False)
    verifica("revoca: scelta nel profilo salvata, registrazioni cancellate",
             adulto.voce_conservata is False and tolte == n == 1 and reg.salvato >= 1
             and cons.registrazioni("p-adu") == 0 and adulto.voce_conservata_il == oggi)
    d = UserProfile.from_dict(adulto.to_dict(), "x")
    verifica("il consenso resta nel profilo (speakers.json)", d.voce_conservata is False)
    verifica("profilo di prima senza il campo: «mai detto»",
             UserProfile.from_dict({"name": "Z"}, "x").voce_conservata is None)

    # ───────── rotazione ─────────
    vecchio = (datetime.date.today() - datetime.timedelta(days=70)).isoformat()
    C._scrivi_privato(cons.voce_dir / "p-amm" / vecchio / "100000-000.wav",
                      C.wav_mulaw(audio, sr))
    C._scrivi_privato(cons.voce_dir / "p-adu" / oggi / "100000-000.wav", C.wav_mulaw(audio, sr))
    C._scrivi_privato(cons.voce_dir / "p-sconosciuto" / oggi / "1.wav", C.wav_mulaw(audio, sr))
    r = cons.ruota()
    verifica("rotazione: via il giorno oltre i 60, la persona senza consenso e l'id sconosciuto",
             not (cons.voce_dir / "p-amm" / vecchio).exists()
             and not (cons.voce_dir / "p-adu").exists()
             and not (cons.voce_dir / "p-sconosciuto").exists()
             and (cons.voce_dir / "p-amm" / oggi).exists() and r["persone"] == 2, str(r))
    verifica("rotazione: il minore col «sì» del tutore resta",
             cons.registrazioni("p-min") == 1)
    minore.voce_conservata_da = None              # come se l'avesse detto lui: non vale
    r = cons.ruota()
    verifica("rotazione, contrario: il minore senza il «sì» di un tutore via",
             not (cons.voce_dir / "p-min").exists() and r["persone"] == 1, str(r))
    minore.voce_conservata = None
    ieri =(datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    for g in (ieri, oggi):
        for i in range(3):
            C._scrivi_privato(cons.voce_dir / "p-amm" / g / f"x{i}.wav", C.wav_mulaw(audio, sr))
    giorno_mb = C._mb(cons.voce_dir / "p-amm" / oggi)
    cons.mb = giorno_mb * 1.2
    r = cons.ruota()
    verifica("tetto di spazio: via i giorni più vecchi, resta l'ultimo",
             r["tetto"] == 1 and not (cons.voce_dir / "p-amm" / ieri).exists()
             and (cons.voce_dir / "p-amm" / oggi).exists(), str(r))
    cons.mb = 2000

    # ───────── registro di prima ripulito una volta ─────────
    vecchia = Path(cfg.turn_log_dir) / f"turni-{ieri}.jsonl"
    vecchia.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in (
        {"inizio": f"{ieri}T09:00:00", "livello": "familiare", "testo": "quanto fa sette per otto",
         "voce": {"nome": "Leo", "modo": "voce"}, "risposta": "Cinquantasei."},
        {"inizio": f"{ieri}T09:01:00", "livello": "amministra", "testo": "che ore sono",
         "voce": {"nome": "Primo", "modo": "voce"}, "risposta": "Sono le nove."},
        {"inizio": f"{ieri}T09:02:00", "livello": "ospite", "testo": "il mio cane si chiama Fido",
         "voce": None, "risposta": "Bel nome."})) + "\nrotta{\n",
        encoding="utf-8")
    r = cons.ripulisci_registro()
    righe = vecchia.read_text(encoding="utf-8").splitlines()
    # Dal 16/10 (decisione 0031) la pulizia all'avvio non toglie più le parole dei minori
    verifica("registro di prima: le parole del minore e dell'adulto restano, la riga rotta pure",
             json.loads(righe[0])["testo"] == "quanto fa sette per otto"
             and json.loads(righe[1])["testo"] == "che ore sono" and righe[3] == "rotta{",
             str(righe)[:300])
    verifica("registro di prima, contrario: le parole dell'ospite tolte",
             r and r["turni"] == 1 and json.loads(righe[2])["testo"] is None, f"{r} {righe[2]}")
    verifica("una volta sola: il segno nella cartella", cons.ripulisci_registro() is None
             and (Path(cfg.turn_log_dir) / C.SEGNO_RIPULITO).exists())

    # ───────── eventi ─────────
    db = tmp / "conversazioni.db"
    disco = Disco.file(db, log=lambda m: None)
    cons.eventi = disco
    regs = Registri(disco, log=lambda m: None, conserva=cons.registro_su_disco)
    for chiave in ("persona:p-adu", "persona:p-min", "ospite:studio", "persona:ignoto"):
        rg = regs.della_corsia(chiave)
        rg.apri("persona")
        rg.aggiungi("detto_persona", 1, testo="la frase di prova", canale="voce")
    regs.scrivi()
    chiavi = set(disco.chiavi())
    # Dal 16/10 (decisione 0031) anche il registro del minore va su disco
    verifica("eventi: su disco l'adulto e il minore; ospite e profilo ignoto in memoria",
             chiavi == {"persona:p-adu", "persona:p-min"}
             and regs.della_corsia("ospite:studio").eventi(), str(chiavi))
    # Righe di un ospite scritte da una versione di prima: la rotazione le toglie
    vecchie = Registri(disco, log=lambda m: None)            # senza conservazione, come prima
    v = vecchie.della_corsia("ospite:cucina")
    v.apri("persona")
    v.aggiungi("detto_persona", 1, testo="frase di un ospite", canale="voce")
    vecchie.scrivi()
    verifica("(prima) l'ospite era su disco", "ospite:cucina" in disco.chiavi())
    regs2 = Registri(disco, log=lambda m: None, conserva=cons.registro_su_disco)
    rip = regs2.riprendi()
    verifica("riavvio: il registro del minore si riprende dal disco, quello dell'ospite no",
             rip["ripresi"] == 2
             and [e.dati.get("testo") for e in regs2.della_corsia("persona:p-min").eventi()
                  if e.tipo == "detto_persona"] == ["la frase di prova"]
             and not regs2.della_corsia("ospite:cucina").eventi(), str(rip))
    disco.ruota(60, effimero=lambda k: not cons.registro_su_disco(k))
    verifica("rotazione: via le righe dell'ospite, l'adulto e il minore restano",
             set(disco.chiavi()) == {"persona:p-adu", "persona:p-min"}, str(disco.chiavi()))
    # Il turno incerto nel registro di un adulto: le parole restano in memoria
    ev = Evento("persona:p-adu", 9, "c", None, time.time(), "detto_persona", 1, "modello",
                senza_parole("detto_persona", {"testo": "parole incerte", "canale": "voce"}))
    verifica("turno incerto: parole solo in memoria", "testo" not in per_disco(ev)
             and ev.dati["testo"] == "parole incerte")
    verifica("CAMPI_TESTO: tipi e campi dell'elenco chiuso",
             all(t in TIPI and set(c) <= set(TIPI[t].campi) for t, c in CAMPI_TESTO.items()))
    ev = Evento("persona:p-adu", 10, "c", None, time.time(), "dati_del_turno", 1, "turno",
                {"blocchi": [{"nome": "ricordi", "caratteri": 42},
                             {"nome": "turno", "testo": "ore 10"}]})
    verifica("dati_del_turno su disco: nomi e lunghezze",
             per_disco(ev)["blocchi"] == [{"nome": "ricordi", "caratteri": 42},
                                          {"nome": "turno", "caratteri": 6}])

    # ───────── svuotare ─────────
    adulto.voce_conservata = True
    rec = turno("Ginevra")
    cons.al_turno(rec, audio, sr)
    log.write(rec)
    r = cons.svuota("p-adu", "Ginevra")
    testi = [json.loads(x) for x in (Path(cfg.turn_log_dir) / f"turni-{oggi}.jsonl").read_text(
        encoding="utf-8").splitlines()]
    verifica("svuota una persona: voce, parole nei turni, eventi",
             r["voce"] == 1 and r["eventi"] >= 1 and r["turni"] >= 1
             and cons.registrazioni("p-adu") == 0 and "persona:p-adu" not in disco.chiavi()
             and not any(x.get("voce") and x["voce"].get("nome") == "Ginevra" and x.get("testo")
                         for x in testi), str(r))
    verifica("svuota una persona, contrario: chi amministra resta",
             cons.registrazioni("p-amm") > 0)
    r = cons.svuota()
    verifica("svuota tutto: niente voce, niente turni, niente eventi",
             not cons.voce_dir.exists() and not list(Path(cfg.turn_log_dir).glob("turni-*"))
             and disco.chiavi() == [], str(r))

    # ───────── il tool ─────────
    sc = SimpleNamespace(current_speaker="Ginevra", identified_by="voce", conferma_breve=False)
    ctx = SimpleNamespace(conserva=cons, speakers=reg, speaker_ctx=sc, turno=5, cfg=cfg,
                          regole=[])
    adulto.voce_conservata = None
    q = _dati_conservati(ctx, "consenso_voce")
    verifica("consenso: prima la domanda, con cosa e per quanto",
             q["ok"] is False and "60 giorni" in q["conferma"]
             and q["in_sospeso"]["argomenti"] == {"azione": "consenso_voce"}
             and adulto.voce_conservata is None, str(q))
    sc.identified_by, ctx.turno = "breve", 6
    r = _dati_conservati(ctx, "consenso_voce")
    verifica("il «sì» (anche breve) nella risposta dopo: consenso salvato",
             r["ok"] and adulto.voce_conservata is True, str(r))
    sc.identified_by = "schermo"
    adulto.voce_conservata = None
    r = _dati_conservati(ctx, "consenso_voce")
    verifica("contrario: scritto, mai il consenso", r["ok"] is False
             and adulto.voce_conservata is None and "in_sospeso" not in r)
    sc.identified_by = "conversazione"
    r = _dati_conservati(ctx, "consenso_voce")
    verifica("contrario: zona grigia, mai il consenso", r["ok"] is False
             and "in_sospeso" not in r)
    sc.current_speaker, sc.identified_by = "Leo", "voce"
    r = _dati_conservati(ctx, "consenso_voce")
    verifica("contrario: un minore non può dare il consenso", r["ok"] is False
             and minore.voce_conservata is None and "genitori" in r["conferma"]
             and "in_sospeso" not in r, str(r))
    r = _dati_conservati(ctx, "consenso_voce", "Leo")
    verifica("contrario: nemmeno nominandosi", r["ok"] is False
             and minore.voce_conservata is None)
    minore.voce_conservata, minore.voce_conservata_da = True, "p-amm"
    r = _dati_conservati(ctx, "revoca_voce")
    verifica("contrario: un minore non revoca da solo il consenso dei tutori", r["ok"] is False
             and minore.voce_conservata is True)
    r = _dati_conservati(ctx, "stato")
    verifica("stato per un minore: i testi si tengono, i genitori li rileggono, la voce sì",
             r["ok"] and "60 giorni" in r["conferma"] and "genitori" in r["conferma"]
             and "voce sì" in r["conferma"], str(r))
    minore.voce_conservata = minore.voce_conservata_da = None
    # Il tutore (16/10, decisione 0031): con la voce, il minore come persona, domanda e «sì»
    sc.current_speaker, ctx.turno = "Primo", 20
    q = _dati_conservati(ctx, "consenso_voce", "Leo")
    verifica("tutore: prima la domanda sulla voce del minore",
             q["ok"] is False and "voce di Leo" in q["conferma"]
             and q["in_sospeso"]["argomenti"] == {"azione": "consenso_voce", "persona": "Leo"}
             and minore.voce_conservata is None, str(q))
    sc.identified_by, ctx.turno = "breve", 21
    r = _dati_conservati(ctx, "consenso_voce", "Leo")
    verifica("tutore: il «sì» salvato nel profilo del minore con chi l'ha dato",
             r["ok"] and minore.voce_conservata is True and minore.voce_conservata_da == "p-amm"
             and minore.voce_conservata_il == oggi and C.consenso_voce(minore), str(r))
    verifica("…e chi amministra non ha cambiato la sua scelta", amm.voce_conservata is None)
    sc.current_speaker, sc.identified_by, ctx.turno = "Ginevra", "voce", 22
    r = _dati_conservati(ctx, "revoca_voce", "Leo")
    verifica("contrario: un adulto che non è tutore non revoca la voce del minore",
             r["ok"] is False and minore.voce_conservata is True)
    r = _dati_conservati(ctx, "consenso_voce", "Primo")
    verifica("contrario: per la voce di un altro adulto decide solo lui",
             r["ok"] is False and "in_sospeso" not in r and amm.voce_conservata is None)
    sc.current_speaker = "Primo"
    C._scrivi_privato(cons.voce_dir / "p-min" / oggi / "1.wav", C.wav_mulaw(audio, sr))
    r = _dati_conservati(ctx, "revoca_voce", "Leo")
    verifica("tutore: revoca subito, le registrazioni del minore cancellate",
             r["ok"] and minore.voce_conservata is False and r["cancellate"] == 1
             and cons.registrazioni("p-min") == 0 and "voce di Leo" in r["conferma"], str(r))
    sc.current_speaker = None
    r = _dati_conservati(ctx, "stato")
    verifica("contrario: ospite, niente", r["ok"] is False)
    sc.current_speaker, sc.identified_by = "Ginevra", "breve"
    adulto.voce_conservata = True
    r = _dati_conservati(ctx, "revoca_voce")
    verifica("revoca a voce (anche breve): subito, senza domanda",
             r["ok"] and adulto.voce_conservata is False)
    sc.identified_by, ctx.turno = "voce", 10
    r = _dati_conservati(ctx, "svuota", "Leo")
    verifica("contrario: svuota da chi non amministra, rifiutato", r["ok"] is False
             and "in_sospeso" not in r)
    sc.current_speaker = "Primo"
    q = _dati_conservati(ctx, "svuota", "Ginevra")
    ctx.turno = 11
    r = _dati_conservati(ctx, "svuota", "Ginevra")
    verifica("svuota di chi amministra: domanda, poi il «sì»",
             q["ok"] is False and "di Ginevra" in q["conferma"] and r["ok"], f"{q} {r}")
    r = _dati_conservati(ctx, "svuota", "Nessuno")
    verifica("svuota, contrario: persona sconosciuta", r["ok"] is False)
    spec = conserva_specs()[0]
    verifica("tool: famiglia, azione, classe con «stato» in sola lettura e «svuota» distruttiva",
             spec.name == "dati_conservati" and spec.risk == "azione"
             and spec.classe.sola_lettura[1] == frozenset({"stato"})
             and "svuota" in spec.classe.distruttiva)

    # ───────── l'archivio delle conversazioni (12/10 sera) ─────────
    from calliope.ciclo import Ciclo
    from calliope.conversazione import Conversazione, turni as turni_conv
    from calliope.conversazioni import (ArchivioConversazioni, load_conversazioni,
                                        senza_non_conservati)
    verifica("decidi, conversazioni: adulto, chi amministra e minore sì; ospite no",
             C.decidi(adulto, "conversazioni").ok and C.decidi(amm, "conversazioni").ok
             and C.decidi(minore, "conversazioni").ok and not C.decidi(None, "conversazioni"))
    verifica("conversazioni_su_disco: adulto e minore sì, profilo tolto no",
             cons.conversazioni_su_disco("p-adu") is True
             and cons.conversazioni_su_disco("p-min") is True
             and cons.conversazioni_su_disco("p-tolto") is False)
    verifica("conversazioni_su_disco: profili non letti → «non so» (None)",
             C.Conservazione(cfg, Registro(), log=lambda m: None)
             .conversazioni_su_disco("p-adu") is None)

    arch = ArchivioConversazioni(tmp / "conv.db", giorni=cons.giorni, log=lambda m: None,
                                 avvia=False, conserva=cons.conversazioni_su_disco)
    cons.conversazioni = arch
    nomi = {"p-adu": "Ginevra", "p-min": "Leo", "p-amm": "Primo"}

    def archivia(chi, testo, meta=None, conv=None):
        conv = conv or Conversazione(f"persona:{chi}" if chi else "ospite:studio")
        conv.owner, conv.last_turn_at = chi, time.monotonic()
        m = {"role": "user", "content": testo, **({"_turno": meta} if meta else {})}
        msgs = [m, {"role": "assistant", "content": "Va bene."}]
        conv.history += msgs
        arch.archivia(conv, turni_conv(msgs), chi, nomi.get(chi), ospite=chi is None)
        return conv

    def su_disco():
        return {(p, o) for p, o in arch.db.execute("SELECT persona, ospite FROM conversazioni")}

    def parole_su_disco():
        return " ".join(str(d) for (d,) in arch.db.execute("SELECT domanda FROM turni"))

    ca = archivia("p-adu", "il mio libro preferito è il barone rampante")
    cm = archivia("p-min", "domani ho la verifica di storia")
    co = archivia(None, "sono un ospite e il mio cane si chiama Fido")
    verifica("adulto: la conversazione su disco", ("p-adu", 0) in su_disco()
             and "barone" in parole_su_disco(), str(su_disco()))
    verifica("minore: la conversazione su disco (16/10, decisione 0031)",
             ("p-min", 0) in su_disco() and "verifica" in parole_su_disco())
    verifica("contrario: ospite, niente su disco", not any(o for _p, o in su_disco())
             and "Fido" not in parole_su_disco())
    verifica("minore: la conversazione nell'archivio su disco (ricerca e scheda)",
             arch.cerca("verifica di storia", "p-min")["risultati"]
             and arch.chat("p-min") and cm.archiviata_in == "disco"
             and ca.archiviata_in == "disco" and co.archiviata_in == "sessione")
    # Dopo un riavvio: un archivio nuovo sullo stesso file la ritrova
    rilegge = ArchivioConversazioni(tmp / "conv.db", giorni=cons.giorni, log=lambda m: None,
                                    avvia=False, conserva=cons.conversazioni_su_disco)
    verifica("minore: la conversazione si ritrova dopo un riavvio, l'ospite no",
             rilegge.cerca("verifica di storia", "p-min")["risultati"]
             and not rilegge.cerca("cane Fido", None, ospiti=True)["risultati"])
    rilegge.close()
    verifica("ospite: nella sessione, la trova solo chi cerca quelle degli ospiti",
             arch.cerca("cane Fido", None, ospiti=True)["risultati"]
             and not arch.cerca("cane Fido", "p-adu")["risultati"])
    # Il turno incerto: la decisione è quella del registro dei turni (testo_turno), il ciclo la
    # scrive nel `_turno` del messaggio
    finto = SimpleNamespace(s=SimpleNamespace(conserva=cons), _meta_turno={"luogo": "studio"})
    Ciclo._segna_conserva(finto, turno("Ginevra", modo="conversazione"))
    grigia = finto._meta_turno
    finto._meta_turno = None
    Ciclo._segna_conserva(finto, turno("Primo", livello="amministra",
                                       voce={"incerta": ["Primo", "Leo"]}))
    dubbio = finto._meta_turno
    finto._meta_turno = {"luogo": "studio"}
    Ciclo._segna_conserva(finto, turno("Ginevra"))
    verifica("ciclo: la zona grigia segnata; il dubbio con un minore (dal 16/10) e l'adulto "
             "certo no", grigia == {"luogo": "studio", "conserva": False} and dubbio is None
             and finto._meta_turno == {"luogo": "studio"}, f"{grigia} {dubbio}")
    archivia("p-adu", "frase in zona grigia sul garage", meta=grigia, conv=ca)
    archivia("p-adu", "e poi il cavaliere inesistente", conv=ca)
    verifica("contrario: incerto, il turno non va su disco (l'adulto certo sì)",
             "garage" not in parole_su_disco() and "cavaliere" in parole_su_disco()
             and not arch.cerca("garage", "p-adu")["risultati"])
    # La conversazione in corso salvata: solo dell'adulto, senza il turno incerto
    ca.archiviati = len(ca.history)
    for c in (ca, cm, co):
        arch.salva_corrente(c)
    salvata = arch.leggi_corrente("persona:p-adu")
    verifica("conversazione in corso su disco: l'adulto senza il turno incerto",
             salvata and len(salvata["history"]) == 4 and "garage" not in json.dumps(salvata)
             and salvata["archiviati"] == 4, str(salvata)[:300])
    verifica("la conversazione in corso del minore su disco, quella dell'ospite no",
             sorted(arch.chiavi_correnti()) == ["persona:p-adu", "persona:p-min"],
             str(arch.chiavi_correnti()))
    verifica("senza_non_conservati: niente da togliere, lo stesso dizionario",
             senza_non_conservati({"history": [{"role": "user", "content": "x"}]})
             == {"history": [{"role": "user", "content": "x"}]})

    # Il riassunto di chiusura (12/10 sera): va su disco intero, quindi senza i turni incerti
    from calliope.compressione import Compressore, Lavoro
    from calliope.conversazioni import storia_conservata

    class Riassuntore:
        """Riassume ripetendo le domande che riceve (come il modello della voce e l'agente)."""
        nome, voce = "finto", True

        def __init__(self):
            self.visti = []

        def riassumi(self, lav, controlla=None):
            self.visti.append(lav)
            testi = [str(m.get("content") or "") for m in (lav.messaggi_voce or [])
                     + lav.da_riassumere if m.get("role") in ("user", "system")]
            return {"dati": {"argomenti": [t for t in testi if t and t != "S"][:12]},
                    "token": 1, "s": 0.0}

    def brain_di(conv):
        return SimpleNamespace(
            conv=conv, schemi=lambda: [],
            _system_messages=lambda: [{"role": "system", "content": "S"}],
            _riassunto_msgs=lambda c=None: (
                [{"role": "system", "content": conv.riassunto["testo"]}]
                if isinstance(conv.riassunto, dict) and conv.riassunto.get("testo") else []))

    def riassunto_su_disco(conv):
        for _ in range(250):
            r = archc.db.execute("SELECT riassunto, riassunto_dati FROM conversazioni "
                                "WHERE id = ?", (conv.id_archivio,)).fetchone()
            if r and r[0]:
                return " ".join(str(x) for x in r)
            time.sleep(0.02)
        return ""

    rf = Riassuntore()
    # Un archivio a parte: i conteggi dell'archivio di sopra restano quelli delle prove dopo
    archc = ArchivioConversazioni(tmp / "chiusura.db", giorni=cons.giorni, log=lambda m: None,
                                  avvia=False, conserva=cons.conversazioni_su_disco)

    def archivia_c(chi, testo, meta=None, conv=None):
        conv = conv or Conversazione(f"persona:{chi}")
        conv.owner, conv.last_turn_at = chi, time.monotonic()
        m = {"role": "user", "content": testo, **({"_turno": meta} if meta else {})}
        msgs = [m, {"role": "assistant", "content": "Va bene."}]
        conv.history += msgs
        archc.archivia(conv, turni_conv(msgs), chi, nomi.get(chi), ospite=False)
        return conv

    comp = Compressore(cfg, [rf], archc, log=lambda m: None)
    cc = archivia_c("p-adu", "parliamo della gita al lago di Braies")
    archivia_c("p-adu", "il codice del garage è quattro sette due", meta=grigia, conv=cc)
    archivia_c("p-adu", "e poi la cena da Ottavio", conv=cc)
    comp.chiudi(brain_di(cc), cc, "esci")
    disco = riassunto_su_disco(cc)
    verifica("chiusura: il riassunto su disco senza il turno incerto (zona grigia)",
             "Braies" in disco and "Ottavio" in disco and "garage" not in disco, disco[:300])
    verifica("…e il modello non l'ha nemmeno ricevuto (voce e trascrizione)",
             rf.visti and not any("garage" in str(m.get("content")) for m in
                                  rf.visti[-1].messaggi_voce + rf.visti[-1].da_riassumere))
    cn = archivia_c("p-adu", "parliamo della gita al lago di Braies")
    archivia_c("p-adu", "e poi la cena da Ottavio", conv=cn)
    comp.chiudi(brain_di(cn), cn, "esci")
    verifica("contrario: senza turni incerti il modello riceve la conversazione intera",
             "Ottavio" in riassunto_su_disco(cn) and len(rf.visti[-1].messaggi_voce) == 5,
             str(len(rf.visti[-1].messaggi_voce)))
    # Un riassunto di prima (compressione) fatto anche con il turno incerto: non entra in quello
    # di chiusura e non va su disco con la conversazione in corso
    cr = archivia_c("p-adu", "e poi la cena da Ottavio")
    cr.riassunto = {"tipo": "compressione", "testo": "Riassunto: il codice del garage, Braies",
                    "dati": {}, "non_conservati": True}
    comp.chiudi(brain_di(cr), cr, "esci")
    disco = riassunto_su_disco(cr)
    verifica("chiusura: un riassunto di prima fatto col turno incerto non entra",
             "Ottavio" in disco and "garage" not in disco, disco[:300])
    cr2 = archivia_c("p-adu", "e poi la cena da Ottavio")
    cr2.riassunto = {"tipo": "compressione", "testo": "Riassunto: la gita a Braies", "dati": {}}
    comp.chiudi(brain_di(cr2), cr2, "esci")
    verifica("contrario: un riassunto di prima pulito entra", "Braies" in riassunto_su_disco(cr2))
    verifica("conversazione in corso su disco: senza il riassunto fatto col turno incerto",
             senza_non_conservati({"history": [], "riassunto": cr.riassunto})["riassunto"]
             is None)
    verifica("contrario: il riassunto pulito resta nella conversazione in corso su disco",
             senza_non_conservati({"history": [], "riassunto": cr2.riassunto})["riassunto"]
             == cr2.riassunto)
    # La compressione segna il riassunto fatto con il turno incerto (in memoria vale)
    cs = Conversazione("persona:p-adu")
    finto_brain = SimpleNamespace(conv=cs, _archivia_turni=lambda: None,
                                  _stima_storia=lambda: 0, last_compressione=None,
                                  last_context=None)
    for incerto, atteso in ((True, True), (False, False)):
        cs.history = [{"role": "user", "content": "il codice del garage",
                       **({"_turno": grigia} if incerto else {})},
                      {"role": "assistant", "content": "Va bene."},
                      {"role": "user", "content": "la gita"}]
        cs.riassunto = None
        lav = Lavoro(cs, "compressione", cs.history[2], [dict(m) for m in cs.history[:2]],
                     None, [], "Ginevra", None, None)
        comp._applica_risultato(finto_brain, lav, {"argomenti": ["x"]}, "finto")
        verifica(f"compressione: riassunto segnato non conservato = {atteso}",
                 bool((cs.riassunto or {}).get("non_conservati")) is atteso, str(cs.riassunto))
    cs.history = [{"role": "user", "content": "il codice del garage", "_turno": grigia},
                  {"role": "assistant", "content": "Va bene."},
                  {"role": "user", "content": "la gita"}]
    verifica("storia_conservata: il turno incerto e le sue risposte via, il resto uguale",
             [m["content"] for m in storia_conservata(cs.history)] == ["la gita"])
    # La coda della conversazione chiusa per una pausa (in memoria nella nuova): segnata se tra
    # gli ultimi scambi c'è il turno incerto, così non va su disco con la conversazione in corso
    from calliope.brain import Brain
    for incerto, atteso in ((True, True), (False, False)):
        vecchia = Conversazione("persona:p-adu")
        vecchia.owner = "p-adu"
        vecchia.history = [{"role": "user", "content": "il codice del garage",
                            **({"_turno": grigia} if incerto else {})},
                           {"role": "assistant", "content": "Va bene."},
                           {"role": "user", "content": "la gita"},
                           {"role": "assistant", "content": "Bella."}]
        fb = SimpleNamespace(cfg=SimpleNamespace(conversazione_coda_scambi=3),
                             conv=Conversazione("persona:p-adu"))
        Brain._coda_della_chiusa(fb, vecchia)
        verifica(f"coda della chiusa: segnata non conservata = {atteso}",
                 bool((fb.conv.riassunto or {}).get("non_conservati")) is atteso
                 and "gita" in fb.conv.riassunto["testo"], str(fb.conv.riassunto)[:200])
    comp.close()
    archc.close()
    # Le conversazioni di prima del 12/10 (ospite, profilo tolto): via alla prima rotazione, con
    # le conversazioni in corso salvate; l'adulto, chi amministra e (dal 16/10) il minore restano
    vecchio = ArchivioConversazioni(tmp / "conv.db", log=lambda m: None, avvia=False,
                                    sessione=False)
    for chi in ("p-min", "p-tolto", "p-amm"):
        cv = Conversazione(f"persona:{chi}")
        cv.owner, cv.last_turn_at = chi, time.monotonic()
        cv.history = [{"role": "user", "content": f"frase di prima di {chi}"}]
        vecchio.archivia(cv, turni_conv(cv.history), chi, None, False)
        vecchio.salva_corrente(cv)
    vecchio.db.execute("INSERT INTO conversazioni (persona, nome, ospite, inizio) "
                       "VALUES (NULL, NULL, 1, ?)", (time.time(),))
    vecchio.db.execute("INSERT INTO correnti (chiave, stato, aggiornata) VALUES (?, ?, ?)",
                       ("ospite:studio", "{}", time.time()))
    vecchio.db.commit()
    vecchio.close()
    verifica("(prima) minore, ospite e profilo tolto erano su disco",
             {("p-min", 0), ("p-tolto", 0), (None, 1)} <= su_disco(), str(su_disco()))
    # Con i profili non letti la rotazione toglie solo gli ospiti
    arch.conserva = lambda p: None
    arch.togli_non_conservate()
    verifica("profili non letti: via gli ospiti, le persone restano",
             (None, 1) not in su_disco() and ("p-min", 0) in su_disco())
    arch.conserva = cons.conversazioni_su_disco
    n = arch.togli_non_conservate()
    # Dal 16/10 (decisione 0031) la pulizia non toglie più le conversazioni dei minori
    verifica("rotazione: via il profilo tolto, restano l'adulto, chi amministra e il minore",
             n == 1 and su_disco() == {("p-adu", 0), ("p-amm", 0), ("p-min", 0)}
             and "di prima di p-min" in parole_su_disco()
             and "di prima di p-tolto" not in parole_su_disco()
             and set(arch.chiavi_correnti()) == {"persona:p-adu", "persona:p-amm",
                                                 "persona:p-min"},
             f"{n} {su_disco()} {arch.chiavi_correnti()}")
    # La tenuta: quella della conservazione (turn_log_days), non un numero suo
    cfg_a = Config()
    cfg_a.conversazioni_db = str(tmp / "tenuta.db")
    cfg_a.conversazioni_embedding = ""
    a60 = load_conversazioni(cfg_a, log=lambda m: None, avvia=False,
                             conserva=cons.conversazioni_su_disco)
    verifica("tenuta: turn_log_days (60), niente conversazioni_giorni",
             a60.giorni == cfg_a.turn_log_days == 60
             and not hasattr(cfg_a, "conversazioni_giorni"))
    a60.close()
    for giorni_fa, testo in ((61, "conversazione di sessantuno giorni fa"),
                             (59, "conversazione di cinquantanove giorni fa")):
        cv = Conversazione("persona:p-adu")
        cv.owner, cv.inizio = "p-adu", time.time() - giorni_fa * 86400
        arch.archivia(cv, turni_conv([{"role": "user", "content": testo}],
                                     quando=time.time() - giorni_fa * 86400),
                      "p-adu", "Ginevra", False)
        arch.chiudi(cv, "fine")
        arch.db.execute("UPDATE conversazioni SET fine = ? WHERE id = ?",
                        (time.time() - giorni_fa * 86400, cv.id_archivio))
    arch.db.commit()
    arch._pulizia()
    verifica("scadenza: via la conversazione di 61 giorni fa, resta quella di 59",
             "sessantuno" not in parole_su_disco() and "cinquantanove" in parole_su_disco())
    st = cons.stato()
    verifica("riepilogo: le conversazioni archiviate contate", st["conversazioni"] == 5
             and st["conversazioni_turni"] >= 4
             and "conversazioni archiviate" in C.testo_stato(st), str(st))
    # Svuotare: una persona (anche nella sessione), poi tutto
    r = cons.svuota("p-min", "Leo")
    verifica("svuota un minore: le sue conversazioni su disco",
             r["conversazioni"] == 2 and not arch.chat("p-min")
             and ("p-min", 0) not in su_disco()
             and "persona:p-min" not in arch.chiavi_correnti(), str(r))
    r = cons.svuota("p-adu", "Ginevra")
    verifica("svuota una persona: le sue conversazioni archiviate e quella in corso",
             r["conversazioni"] == 2 and ("p-adu", 0) not in su_disco()
             and arch.chiavi_correnti() == ["persona:p-amm"], str(r))
    verifica("svuota una persona, contrario: quelle di chi amministra restano",
             ("p-amm", 0) in su_disco())
    r = cons.svuota()
    verifica("svuota tutto: archivio vuoto, anche le conversazioni in corso",
             r["conversazioni"] == 1 and arch.conteggi()["conversazioni"] == 0
             and arch.chiavi_correnti() == [] and arch.db.execute(
                 "SELECT COUNT(*) FROM turni_fts").fetchone()[0] == 0, str(r))
    # Dopo lo svuotamento la conversazione che continua apre una riga nuova (niente orfani)
    cx = Conversazione("persona:p-amm")
    cx.id_archivio = 999
    archivia("p-amm", "una conversazione con la riga tolta", conv=cx)
    verifica("riga tolta mentre la conversazione continua: una riga nuova, niente orfani",
             cx.id_archivio != 999 and arch.db.execute(
                 "SELECT COUNT(*) FROM turni WHERE conv NOT IN (SELECT id FROM conversazioni)"
             ).fetchone()[0] == 0)
    cons.conversazioni = None
    arch.close()

    # ───────── esercizi e richieste ai tutori (12/10 sera) ─────────
    # La stessa tenuta di turni e voce (turn_log_days), alla prima rotazione anche quelli di
    # prima; svuotati con la persona e con tutto
    from calliope.esercizi.registro import Registro as RegistroEsercizi
    from calliope.minori import Richieste
    RegistroEsercizi(cfg.memory_db).db.close()
    Richieste(cfg.memory_db, cfg, log=lambda m: None).db.close()
    import sqlite3

    def riempi():
        db = sqlite3.connect(cfg.memory_db)
        db.execute("DELETE FROM esercizi_tentativi")
        db.execute("DELETE FROM richieste_tutori")
        db.execute("DELETE FROM esercizi_segnalazioni")
        for chi in ("p-min", "p-min2"):
            for fa in (59, 60, 61):
                g = datetime.date.today() - datetime.timedelta(days=fa)
                db.execute("INSERT INTO esercizi_tentativi (persona, giorno, quando, materia, "
                           "argomento, esercizio, domanda, attesa, data, esito) VALUES "
                           "(?, ?, ?, 'matematica', 'tabelline', 'f', '7 per 8', '56', '54', "
                           "'sbagliata')", (chi, g.isoformat(), f"{g.isoformat()}T10:00:00"))
                db.execute("INSERT INTO richieste_tutori (minore, tipo, oggetto, creata, "
                           "creata_ts) VALUES (?, 'gioco', 'il gioco dei pirati', ?, ?)",
                           (chi, f"{g.isoformat()}T10:00:00", time.time() - fa * 86400))
                db.execute("INSERT INTO esercizi_segnalazioni (persona, quando, esercizio, "
                           "nota) VALUES (?, ?, 'f', 'secondo me è sbagliato')",
                           (chi, f"{g.isoformat()}T10:00:00"))
        db.commit()
        db.close()

    def righe(chi=None):
        db = sqlite3.connect(cfg.memory_db)
        out = []
        for tabella, col, quando in C.TABELLE_MEMORIA:
            q = f"SELECT {quando} FROM {tabella}" + (f" WHERE {col} = ?" if chi else "")
            out += [r[0][:10] for r in db.execute(q, (chi,) if chi else ())]
        db.close()
        return out

    riempi()
    giorno = {fa: (datetime.date.today() - datetime.timedelta(days=fa)).isoformat()
              for fa in (59, 60, 61)}
    r = cons.ruota()
    rimaste = righe()
    verifica("rotazione: esercizi, segnalazioni e richieste di 61 giorni fa via, 59 e 60 restano",
             giorno[61] not in rimaste and rimaste.count(giorno[59]) == 6
             and rimaste.count(giorno[60]) == 6 and r.get("memoria") == 6, f"{r} {rimaste}")
    cons.giorni = 30
    verifica("tenuta: è turn_log_days (con 30 via anche quelli di 59 giorni)",
             cons.ruota().get("memoria") == 12 and righe() == [])
    cons.giorni = 60
    riempi()
    r = cons.svuota("p-min", "Leo")
    verifica("svuota una persona: anche i suoi esercizi e le sue richieste ai tutori",
             r["esercizi_richieste"] == 9 and righe("p-min") == [] and len(righe("p-min2")) == 9,
             str(r))
    verifica("svuota, contrario: quelli degli altri restano", len(righe("p-min2")) == 9)
    r = cons.svuota()
    verifica("svuota tutto: anche esercizi e richieste", r["esercizi_richieste"] == 9
             and righe() == [], str(r))
    cfg_senza = SimpleNamespace(memory_db=str(tmp / "non-esiste.db"), turn_log_dir=None,
                                turn_log_days=60)
    verifica("contrario: senza il file della memoria niente errori né file nuovi",
             C.Conservazione(cfg_senza, reg, log=lambda m: None)._memoria(
                 limite=datetime.date.today()) == 0
             and not (tmp / "non-esiste.db").exists())

    # ───────── da terminale ─────────
    cart = tmp / "dati"
    cart.mkdir()
    (cart / "speakers.json").write_text(json.dumps([amm.to_dict(), adulto.to_dict(),
                                                    minore.to_dict()]), encoding="utf-8")
    prima = os.getcwd()
    env = {k: os.environ.get(k) for k in ("CALLIOPE_TURN_LOG", "CALLIOPE_CONVERSAZIONI_DB",
                                          "CALLIOPE_CONFIG", "CALLIOPE_MEMORY_DB")}
    try:
        os.chdir(cart)
        os.environ["CALLIOPE_TURN_LOG"] = str(cart / "registro")
        os.environ["CALLIOPE_CONVERSAZIONI_DB"] = str(cart / "conversazioni.db")
        os.environ["CALLIOPE_CONFIG"] = str(cart / "calliope.yaml")
        os.environ["CALLIOPE_MEMORY_DB"] = str(cart / "memoria.db")
        c2 = C.Conservazione(SimpleNamespace(turn_log_dir=str(cart / "registro"),
                                             turn_log_days=60, conserva_voce=True,
                                             conserva_voce_mb=10), Registro(amm), lambda m: None)
        C._scrivi_privato(c2.voce_dir / "p-amm" / oggi / "1.wav", C.wav_mulaw(audio, sr))
        a_t = ArchivioConversazioni(cart / "conversazioni.db", log=lambda m: None, avvia=False,
                                    sessione=False)
        cv = Conversazione("persona:p-amm")
        cv.owner = "p-amm"
        a_t.archivia(cv, turni_conv([{"role": "user", "content": "una frase di Primo"}]),
                     "p-amm", "Primo", False)
        a_t.close()
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--json"])
        d = json.loads(out.getvalue()[out.getvalue().index("{"):])
        verifica("terminale: conteggi in JSON (anche le conversazioni archiviate)",
                 rc == 0 and d["voce_file"] == 1 and d["conversazioni"] == 1, out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main([])
        verifica("terminale: le conversazioni archiviate nel riepilogo e per persona",
                 rc == 0 and "1 conversazioni archiviate" in out.getvalue()
                 and "conversazioni archiviate 1" in out.getvalue(), out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--svuota", "--persona", "Primo"])
        verifica("terminale: --svuota --persona (anche le conversazioni archiviate)",
                 rc == 0 and not (c2.voce_dir / "p-amm").exists()
                 and C.conta_archivio(SimpleNamespace(conversazioni_db=str(
                     cart / "conversazioni.db")))["conversazioni"] == 0
                 and "1 conversazioni archiviate" in out.getvalue(), out.getvalue())
        # Un minore (16/10, decisione 0031): i suoi dati conservati via come quelli di un adulto
        C._scrivi_privato(c2.voce_dir / "p-min" / oggi / "1.wav", C.wav_mulaw(audio, sr))
        a_t = ArchivioConversazioni(cart / "conversazioni.db", log=lambda m: None, avvia=False,
                                    sessione=False)
        cv = Conversazione("persona:p-min")
        cv.owner = "p-min"
        a_t.archivia(cv, turni_conv([{"role": "user", "content": "una frase di Leo"}]),
                     "p-min", "Leo", False)
        a_t.close()
        (cart / "registro" / f"turni-{oggi}.jsonl").write_text(json.dumps(
            {"inizio": f"{oggi}T09:00:00", "livello": "familiare", "testo": "una frase di Leo",
             "voce": {"nome": "Leo", "id": "p-min", "modo": "voce"}}) + "\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = C.main(["--svuota", "--persona", "Leo"])
        verifica("terminale: --svuota --persona di un minore (voce, conversazioni, turni)",
                 rc == 0 and not (c2.voce_dir / "p-min").exists()
                 and C.conta_archivio(SimpleNamespace(conversazioni_db=str(
                     cart / "conversazioni.db")), "p-min")["conversazioni"] == 0
                 and "una frase di Leo" not in (cart / "registro" / f"turni-{oggi}.jsonl")
                 .read_text(encoding="utf-8"), out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            C.main([])
        verifica("terminale: il minore nel riepilogo, la voce decisa dai tutori",
                 "Leo: minore, voce no (lo decidono i tutori)" in out.getvalue(), out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            rc = C.main(["--svuota", "--persona", "Nessuno"])
        verifica("terminale, contrario: persona sconosciuta → 1", rc == 1)
    finally:
        os.chdir(prima)
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
