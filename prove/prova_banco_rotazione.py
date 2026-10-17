import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco della rotazione dell'audio del banco della stanza (17/10, issue #32;
calliope/stanza/banco.py, calliope/conserva.py, calliope/turnlog.py; eccezione del 14/10 sera
della decisione 0029).

Il difetto: `banco.ruota` girava solo dentro `Banco.salva`, cioè solo con l'eccezione accesa.
Scaduta (dal 21/10 sulla DGX) o spenta, nessuno toglieva i giorni oltre `turn_log_days`, e i file
restavano oltre i 60 giorni promessi dalla decisione. Ora la chiama anche la conservazione
(`Conservazione.ruota`, all'avvio in main.py e a ogni giorno nuovo dal registro dei turni).

Casi (senza mai chiamare `salva`):
- eccezione scaduta: il giorno di 61 giorni fa via (audio e `.json`, anche un giorno di soli
  blocchi), quelli di 60, 59 giorni fa e di oggi restano, `acceso.json` resta (la scadenza resta
  quella);
- eccezione spenta nel file (`stanza_audio_banco_giorni: 0`) e senza corsia lenta: ruota lo
  stesso;
- `turn_log_days` diverso (10) rispettato;
- dal registro dei turni: il primo turno di un giorno nuovo fa girare la rotazione (in secondo
  piano), un altro turno dello stesso giorno no;
- contrari: cartelle che non sono date e file sciolti non toccati, nessuna cartella del banco
  (niente errori), un errore del banco non ferma la rotazione del resto, i giorni non scaduti
  restano, con il codice di main (`Conservazione.ruota` senza banco) i vecchi restavano.

Nomi di fantasia. Tutto in una cartella temporanea. <1 s.
"""

import datetime
import json
import shutil
import tempfile
import time
from pathlib import Path

from calliope import conserva as C
from calliope.config import Config
from calliope.stanza import banco as B
from calliope.turnlog import TurnLog

errori = 0


def check(nome, cond, extra=""):
    global errori
    if cond:
        print(f"  ok   {nome}")
    else:
        errori += 1
        print(f"  NO   {nome} {extra}")


OGGI = datetime.date.today()


def giorno(n: int) -> str:
    return (OGGI - datetime.timedelta(days=n)).isoformat()


def prepara(tmp: Path, giorni_banco=7, lenta=True, tenuta=60, acceso_da=30):
    """Una cartella del banco come sulla DGX dopo la scadenza: `acceso.json` di `acceso_da`
    giorni fa, due satelliti, giorni vecchi e nuovi."""
    cfg = Config()
    cfg.turn_log_dir = str(tmp / "registro")
    cfg.memory_db = str(tmp / "memoria.db")     # mai quella vera
    cfg.turn_log_days = tenuta
    cfg.stanza_audio_banco_giorni = giorni_banco
    cfg.stanza_lenta = lenta
    d = B.cartella(cfg)
    d.mkdir(parents=True, exist_ok=True)
    (d / B.ACCESO).write_text(json.dumps({"dal": time.time() - acceso_da * B.GIORNO_S,
                                          "giorni": giorni_banco}), encoding="utf-8")
    for sat in ("telefono-carlo", "cucina"):
        for n in (tenuta + 5, tenuta + 1, tenuta, tenuta - 1, 0):
            g = d / sat / giorno(n)
            g.mkdir(parents=True, exist_ok=True)
            (g / "203000-seg1.wav").write_bytes(b"RIFF")
            (g / "203000-seg1.json").write_text("{}", encoding="utf-8")
    # Un giorno vecchio di soli blocchi (niente audio)
    gb = d / "cucina" / giorno(tenuta + 3)
    gb.mkdir(parents=True, exist_ok=True)
    (gb / "203000-blocco-b1.json").write_text("{}", encoding="utf-8")
    # Contrari: una cartella che non è una data e un file sciolto
    (d / "cucina" / "appunti").mkdir(parents=True, exist_ok=True)
    (d / "cucina" / "appunti" / "x.wav").write_bytes(b"RIFF")
    (d / "cucina" / "leggimi.txt").write_text("x", encoding="utf-8")
    return cfg, d


def giorni_presenti(d: Path, sat: str) -> set:
    return {g.name for g in (d / sat).iterdir() if g.is_dir()}


def conservazione(cfg):
    righe = []
    cons = C.Conservazione(cfg, None, log=righe.append)
    return cons, righe


tmp_radice = Path(tempfile.mkdtemp(prefix="calliope_banco_rot_"))
try:
    # ── 1. Eccezione scaduta: la conservazione ruota il banco senza salva ──
    print("Eccezione scaduta (7 giorni, accesa 30 giorni fa)")
    cfg, d = prepara(tmp_radice / "scaduta")
    banco = B.Banco(cfg, log=lambda m: None)
    check("l'eccezione è davvero scaduta (non salva)", not banco.attivo())
    cons, righe = conservazione(cfg)
    out = cons.ruota()
    for sat in ("telefono-carlo", "cucina"):
        g = giorni_presenti(d, sat)
        check(f"{sat}: via i giorni oltre 60 (65, 61)", giorno(65) not in g and giorno(61) not in g,
              str(sorted(g)))
        check(f"{sat}: restano 60, 59 giorni fa e oggi",
              {giorno(60), giorno(59), giorno(0)} <= g, str(sorted(g)))
    check("via anche il giorno di soli blocchi (nessun audio)",
          not (d / "cucina" / giorno(63)).exists())
    check("conteggio dei file audio tolti (2 satelliti × 2 giorni)", out.get("banco") == 4,
          str(out))
    check("una riga nel log, senza parole", any("banco della stanza: tolti 4" in r for r in righe),
          str(righe))
    check("acceso.json resta (la scadenza non si riapre)", (d / B.ACCESO).exists())
    check("contrario: la cartella che non è una data resta",
          (d / "cucina" / "appunti" / "x.wav").exists())
    check("contrario: il file sciolto resta", (d / "cucina" / "leggimi.txt").exists())
    check("dopo la rotazione l'eccezione resta scaduta", not banco.attivo())
    out2 = cons.ruota()
    check("seconda rotazione: niente da togliere", out2.get("banco") == 0, str(out2))

    # ── 2. Eccezione spenta nel file e senza corsia lenta: ruota lo stesso ──
    print("Eccezione spenta (giorni 0) e senza stanza_lenta")
    cfg, d = prepara(tmp_radice / "spenta", giorni_banco=0, lenta=False)
    check("spenta: Banco.attivo è falso", not B.Banco(cfg, log=lambda m: None).attivo())
    out = conservazione(cfg)[0].ruota()
    g = giorni_presenti(d, "cucina")
    check("spenta: via i giorni oltre 60", giorno(61) not in g and giorno(65) not in g,
          str(sorted(g)))
    check("spenta: i non scaduti restano", {giorno(60), giorno(59), giorno(0)} <= g)
    check("spenta: 4 file audio tolti", out.get("banco") == 4, str(out))
    cfg, d = prepara(tmp_radice / "senza_lenta", giorni_banco=7, lenta=False)
    conservazione(cfg)[0].ruota()
    g = giorni_presenti(d, "telefono-carlo")
    check("senza corsia lenta: via il vecchio, resta il nuovo",
          giorno(61) not in g and giorno(59) in g, str(sorted(g)))

    # ── 3. turn_log_days diverso ──
    print("turn_log_days: 10")
    cfg, d = prepara(tmp_radice / "dieci", tenuta=10)
    conservazione(cfg)[0].ruota()
    g = giorni_presenti(d, "cucina")
    check("10 giorni: via 11 e 15, restano 10, 9 e oggi",
          giorno(11) not in g and giorno(15) not in g
          and {giorno(10), giorno(9), giorno(0)} <= g, str(sorted(g)))

    # ── 4. banco.ruota con il giorno dato ──
    print("banco.ruota con `oggi`")
    cfg, d = prepara(tmp_radice / "oggi")
    n = B.ruota(cfg, OGGI - datetime.timedelta(days=10))
    g = giorni_presenti(d, "cucina")
    check("con oggi = 10 giorni fa il limite è 70 giorni: 65 e 61 restano",
          giorno(65) in g and giorno(61) in g, str(sorted(g)))
    check("con oggi = 10 giorni fa: niente tolto", n == 0, str(n))
    n = B.ruota(cfg)
    check("senza oggi: il giorno vero, 4 file", n == 4, str(n))

    # ── 5. Dal registro dei turni: a ogni giorno nuovo ──
    print("Registro dei turni: rotazione a ogni giorno nuovo")
    cfg, d = prepara(tmp_radice / "turni")
    cons, _ = conservazione(cfg)
    cons._ruotata_il = OGGI          # come dopo la pulizia dell'avvio di oggi
    log = TurnLog(cfg.turn_log_dir, 60, conserva=cons)
    log.write({"inizio": datetime.datetime.now().isoformat(), "testo": "che ore sono"})
    time.sleep(0.2)
    check("contrario: un turno dello stesso giorno non ruota",
          giorno(61) in giorni_presenti(d, "cucina"))
    # Il giorno dopo: registro e conservazione puliti ieri
    log._pulito_il = OGGI - datetime.timedelta(days=1)
    cons._ruotata_il = OGGI - datetime.timedelta(days=1)
    log.write({"inizio": datetime.datetime.now().isoformat(), "testo": "che ore sono"})
    for _ in range(50):              # la rotazione è in secondo piano
        if giorno(61) not in giorni_presenti(d, "cucina"):
            break
        time.sleep(0.05)
    g = giorni_presenti(d, "cucina")
    check("primo turno del giorno nuovo: via i giorni oltre 60", giorno(61) not in g,
          str(sorted(g)))
    check("primo turno del giorno nuovo: i non scaduti restano", giorno(59) in g)
    check("la conservazione segna il giorno della rotazione", cons._ruotata_il == OGGI)
    log2 = TurnLog(None, 60, conserva=None)
    log2.write({"testo": "x"})
    check("contrario: registro senza conservazione, niente errori", True)

    # ── 6. Contrari: nessuna cartella, errore del banco ──
    print("Contrari")
    cfg = Config()
    cfg.turn_log_dir = str(tmp_radice / "vuota")
    cfg.memory_db = str(tmp_radice / "vuota" / "memoria.db")
    out = conservazione(cfg)[0].ruota()
    check("nessuna cartella del banco: 0, niente errori", out.get("banco") == 0, str(out))
    cfg, d = prepara(tmp_radice / "guasto")
    cons, righe = conservazione(cfg)
    vero = B.ruota
    try:
        def guasto(*a, **k):
            raise OSError("disco")
        B.ruota = guasto
        out = cons.ruota()
    finally:
        B.ruota = vero
    check("errore del banco: la rotazione del resto finisce", "memoria" in out and
          out.get("banco") == 0, str(out))
    check("errore del banco: detto nel log", any("banco della stanza non riuscita" in r
                                                  for r in righe), str(righe))
finally:
    shutil.rmtree(tmp_radice, ignore_errors=True)

print()
if errori:
    print(f"{errori} controlli NON passati")
    sys.exit(1)
print("Tutti i controlli passati")
