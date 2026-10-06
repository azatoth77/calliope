import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco di tempi.py: durate e orari detti a voce → secondi e istanti."""

import datetime

from calliope.tempi import (parse_day_range, parse_duration, parse_shift, parse_when, say_duration,
                            say_when)

DURATE = [("mezz'ora", 1800), ("mezzora", 1800), ("10 minuti", 600), ("dieci minuti", 600),
          ("un quarto d'ora", 900), ("tre quarti d'ora", 2700), ("un'ora", 3600),
          ("un'ora e mezza", 5400), ("un'ora e un quarto", 4500), ("due ore e un quarto", 8100),
          ("1 ora e 20 minuti", 4800), ("90 secondi", 90), ("un minuto e mezzo", 90),
          ("ventitré minuti", 1380), ("tra 5 minuti", 300), ("30", 1800), ("45 minuti", 2700),
          ("un'ora e 30", 5400), ("trentacinque secondi", 35), ("2,5 ore", 9000),
          # «un paio» vale 2 (04/10: era 1); «qualche minuto» resta 1 minuto
          ("un paio di minuti", 120), ("un paio d'ore", 7200), ("un paio di secondi", 2),
          ("tra un paio di minuti", 120), ("qualche minuto", 60), ("un minuto", 60)]

ADESSO = datetime.datetime(2026, 9, 26, 14, 0)            # sabato alle 14
ORARI = [("tra 20 minuti", "2026-09-26 14:20"), ("fra mezz'ora", "2026-09-26 14:30"),
         ("alle 18", "2026-09-26 18:00"), ("alle 18:30", "2026-09-26 18:30"),
         ("alle 6", "2026-09-26 18:00"), ("alle 6 e mezza", "2026-09-26 18:30"),
         ("alle 13", "2026-09-27 13:00"), ("domani alle 9", "2026-09-27 09:00"),
         ("domani mattina", "2026-09-27 09:00"), ("stasera alle 8", "2026-09-26 20:00"),
         ("lunedì alle 10", "2026-09-28 10:00"), ("a mezzogiorno", "2026-09-27 12:00"),
         ("dopodomani alle sette e un quarto", "2026-09-28 07:15"),
         ("alle sette meno un quarto", "2026-09-26 18:45"), ("sabato alle 9", "2026-10-03 09:00"),
         ("oggi pomeriggio alle 5", "2026-09-26 17:00"), ("alle nove", "2026-09-26 21:00")]

errori = 0
for testo, atteso in DURATE:
    got = parse_duration(testo)
    errori += got != atteso
    print(f"{'ok ' if got == atteso else 'ERR'} {testo!r:26} → {got}"
          + (f" ({say_duration(got)})" if got else "") + ("" if got == atteso else f"  atteso {atteso}"))
for testo, atteso in ORARI:
    got = parse_when(testo, ADESSO)
    g = got.strftime("%Y-%m-%d %H:%M") if got else None
    errori += g != atteso
    print(f"{'ok ' if g == atteso else 'ERR'} {testo!r:36} → {g}"
          + (f" ({say_when(got, ADESSO)})" if got else "") + ("" if g == atteso else f"  atteso {atteso}"))
# Date dette (05/10 sera, data_calcola): (testo, data attesa, anno detto)
from calliope.tempi import anni_compiuti, parse_date, prossima, say_date  # noqa: E402
OGGI_D = datetime.date(2026, 10, 5)
DATE = [("4 luglio 1977", "1977-07-04", True), ("il 4 luglio del 1977", "1977-07-04", True),
        ("04/07/1977", "1977-07-04", True), ("4.7.77", "1977-07-04", True),
        ("1977-07-04", "1977-07-04", True), ("4/7/26", "2026-07-04", True),
        ("25 dicembre", "2026-12-25", False), ("Natale", "2026-12-25", False),
        ("Natale 2027", "2027-12-25", True), ("primo maggio", "2026-05-01", False),
        ("1° maggio 2027", "2027-05-01", True), ("ventitré aprile 1990", "1990-04-23", True),
        ("domani", "2026-10-06", True), ("ieri", "2026-10-04", True),
        ("31 febbraio 1980", None, None), ("13/13/2020", None, None), ("boh", None, None),
        ("a luglio", None, None)]
for testo, atteso, anno in DATE:
    got = parse_date(testo, OGGI_D)
    g = (got[0].isoformat(), got[1]) if got else (None, None)
    ok = g == (atteso, anno)
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} data {testo!r:24} → {g}" + ("" if ok else f"  attesa {atteso}"))
for nascita, giorno, anni in (("1977-07-04", "2026-10-05", 49), ("1977-07-04", "2026-07-03", 48),
                              ("1977-07-04", "2026-07-04", 49), ("2000-02-29", "2025-02-28", 24),
                              ("2000-02-29", "2025-03-01", 25)):
    n = anni_compiuti(datetime.date.fromisoformat(nascita), datetime.date.fromisoformat(giorno))
    errori += n != anni
    print(f"{'ok ' if n == anni else 'ERR'} anni compiuti {nascita} al {giorno}: {n}")
for d, atteso in (("2026-12-25", "2026-12-25"), ("2026-01-01", "2027-01-01"),
                  ("2026-10-05", "2026-10-05")):
    p = prossima(datetime.date.fromisoformat(d), OGGI_D).isoformat()
    errori += p != atteso
    print(f"{'ok ' if p == atteso else 'ERR'} prossima {d} → {p}")
ok = say_date(datetime.date(2026, 5, 1)) == "primo maggio 2026" and \
    say_date(datetime.date(2026, 12, 25), OGGI_D, anno=False) == "25 dicembre"
errori += not ok
print(f"{'ok ' if ok else 'ERR'} say_date: «primo maggio 2026», «25 dicembre» senza l'anno di adesso")
# Giorni e intervalli per «cosa ho…?» (ADESSO è sabato 26/09 alle 14)
GIORNI = [("", "2026-09-26 14:00", "2026-10-03 14:00", "nei prossimi 7 giorni"),
          ("oggi", "2026-09-26 14:00", "2026-09-27 00:00", "oggi"),
          ("domani", "2026-09-27 00:00", "2026-09-28 00:00", "domani"),
          ("dopodomani", "2026-09-28 00:00", "2026-09-29 00:00", "dopodomani"),
          ("martedì", "2026-09-29 00:00", "2026-09-30 00:00", "martedì"),
          ("sabato", "2026-09-26 14:00", "2026-09-27 00:00", "oggi"),
          ("questa settimana", "2026-09-26 14:00", "2026-09-28 00:00", "questa settimana"),
          ("la prossima settimana", "2026-09-28 00:00", "2026-10-05 00:00", "la prossima settimana")]
for testo, a, b, etichetta in GIORNI:
    s, e, lab = parse_day_range(testo, ADESSO)
    got = (s.strftime("%Y-%m-%d %H:%M"), e.strftime("%Y-%m-%d %H:%M"), lab)
    ok = got == (a, b, etichetta)
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} giorni {testo!r:24} → {got}" + ("" if ok else f"  atteso {(a, b, etichetta)}"))
# Spostamenti per cambiare un timer o un promemoria già messo (03/10); casi contrari: una
# durata semplice, un orario con «meno», «tra 5 minuti» restano com'erano (None)
SPOSTAMENTI = [("5 minuti in più", 300), ("altri 5 minuti", 300), ("aggiungi cinque minuti", 300),
               ("+5 minuti", 300), ("mezz'ora più tardi", 1800), ("ancora 3 minuti", 180),
               ("rimandalo di 10 minuti", 600), ("2 minuti in meno", -120),
               ("toglici due minuti", -120), ("-2 minuti", -120), ("10 minuti prima", -600),
               ("dieci minuti più presto", -600), ("un minuto", None), ("di mezz'ora", None),
               ("un'ora e mezza", None), ("alle sette meno un quarto", None),
               ("tra 5 minuti", None), ("domani alle 9", None), ("più o meno 5 minuti", None)]
for testo, atteso in SPOSTAMENTI:
    got = parse_shift(testo)
    errori += got != atteso
    print(f"{'ok ' if got == atteso else 'ERR'} spostamento {testo!r:28} → {got}"
          + ("" if got == atteso else f"  atteso {atteso}"))
# Ora legale (03/10, analisi di robustezza): «tra N minuti/ore» è tempo reale. Solo con un
# fuso che cambia ora il 25/10/2026 e il 29/03/2026 (Europa/Roma, quello di casa); altrove
# i casi non dicono niente e si saltano
_ore = (datetime.datetime(2026, 10, 25, 4).timestamp()
        - datetime.datetime(2026, 10, 25, 1).timestamp()) / 3600
if _ore == 4:
    prima = datetime.datetime.fromtimestamp(datetime.datetime(2026, 10, 25, 2, 50).timestamp())
    seconda = datetime.datetime.fromtimestamp(prima.timestamp() + 3600)     # 02:50 di nuovo
    ORA_LEGALE = [(prima, "tra 20 minuti", 20), (prima, "tra un'ora", 60),
                  (seconda, "tra 20 minuti", 20),
                  (datetime.datetime(2026, 10, 25, 1, 30), "tra 2 ore", 120),
                  (datetime.datetime(2026, 3, 29, 1, 30), "tra 2 ore", 120),
                  (datetime.datetime(2026, 3, 29, 1, 50), "fra mezz'ora", 30)]
    for adesso, testo, minuti in ORA_LEGALE:
        got = parse_when(testo, adesso)
        reali = round((got.timestamp() - adesso.timestamp()) / 60) if got else None
        errori += reali != minuti
        print(f"{'ok ' if reali == minuti else 'ERR'} ora legale {adesso:%d/%m %H:%M} "
              f"(fold {adesso.fold}) {testo!r:16} → {got:%H:%M}, {reali} minuti veri"
              + ("" if reali == minuti else f"  attesi {minuti}"))
else:
    print("SALTATA IN PARTE: ora legale: il fuso di questa macchina non cambia ora il 25/10, casi saltati")
print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
