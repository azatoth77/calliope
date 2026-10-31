"""
La conservazione dei dati per misurare e migliorare Calliope (12/10/2026, decisione 0028, T1;
dal 16/10 decisione 0031 per i minori).

Turni, eventi e voce delle **persone di casa riconosciute** (adulti e, dal 16/10, minori)
restano per `turn_log_days` (60) giorni, in privato nella cartella dei dati (mai nel repository:
`registro/` è in .gitignore, sulla DGX sta in ~/calliope/registro). Servono al banco della scelta
dei tool, ai set di regressione, al dizionario delle correzioni, alla taratura delle soglie e,
per i minori, alla rilettura dei tutori. Degli **ospiti mai**: né testo né audio oltre a ciò che
serve al turno. *Storico, 12–16/10 (0028 T1): anche dei minori mai; superato dalla 0031 («la
privacy in casa di un minore non esiste»). Le parole dei minori tolte in quei giorni non tornano.*

**Un solo posto decide** chi è conservabile: `decidi(profilo, cosa, modo, dubbi)`, puro.
- `testo` (turni ed eventi con le parole): una persona di casa riconosciuta (adulto o minore),
  dalla voce sopra soglia, da una frase breve o per continuità, da uno schermo personale, o il
  proprietario di un satellite personale incerto con un minore (`proprietario`). Anche nel
  dubbio tra un adulto e un minore (`incerta`, `minore_vicino`, `minore_incerto`: dal 16/10) il
  testo resta, sotto la persona decisa dal ciclo: sono due persone di casa. Il ciclo scrive quei
  turni con `modo: conversazione` e il segno del dubbio nel campo `voce`: è il segno che li
  distingue dalla zona grigia (`conversazione` senza segni, una voce sola sotto soglia), che
  resta fuori.
- `voce` (l'audio della frase): come il testo, ma solo con la voce riconosciuta sopra soglia
  in quella frase (`modo: voce`), senza altre voci vicino al satellite (`compagnia`: l'audio
  potrebbe avere dentro un'altra persona), **senza dubbi con un minore** (l'audio può essere
  dell'altra persona) e con il **consenso**: della persona, o per un minore dei suoi tutori.
- `eventi` (il registro degli eventi su disco): i registri delle persone di casa, minori
  compresi (dal 16/10). Quelli degli ospiti restano solo in memoria (`registro_su_disco`), e
  quelli già su disco li cancella la rotazione.
- `conversazioni` (l'archivio delle conversazioni, calliope/conversazioni.py, dal 12/10 sera):
  come gli eventi, le conversazioni delle persone di casa (`conversazioni_su_disco`); quelle
  degli ospiti stanno nell'archivio della sessione, in memoria. Dentro la conversazione di una
  persona, i turni le cui parole non restano (`testo_turno`: zona grigia) non vanno su disco.
  Stessi `turn_log_days` giorni.
- `stanza` (il testo della conversazione di stanza su disco, calliope/stanza/tenuta.py, dal
  14/10, decisione 0029 punto 5): solo con `stanza_tenuta` accesa, per `stanza_tenuta_giorni`;
  per tutta la famiglia, **minori compresi** (scelta di chi amministra), solo con la voce
  riconosciuta sopra soglia; mai gli ospiti né la zona grigia. Non è un dato per le misure.
  Dal 14/10 (decisione 0030) anche i **conoscenti** confermati da chi amministra.
- **I conoscenti** (categoria «conoscente», 14/10 sera, decisione 0030 aggiornata da Dario):
  per la conservazione valgono come un adulto della famiglia (turni con le parole, eventi,
  archivio delle conversazioni per `turn_log_days`, la stanza; la voce solo con il consenso,
  che un conoscente, di livello ospite, oggi non ha modo di dare), mentre i **permessi** restano
  da ospite. Il profilo si cerca in `conoscenti` (o nel file `conoscenti_file`, da terminale e
  con i conoscenti spenti); un conoscente tolto (dimenticato, scaduto, svuotato) si porta via
  turni, eventi e conversazioni (`conoscente_tolto`); promosso a familiare (stesso id) li tiene.

**Il consenso** è un dato della persona, nel suo profilo (speakers.json, `voce_conservata`):
None = mai detto, True = «sì» detto una volta a Calliope (tool `dati_conservati`), False =
revocato (anche a voce; le registrazioni che c'erano si cancellano). Per chi amministra vale la
sua scelta, e senza una scelta è sì. **Per un minore** (16/10, decisione 0031) il consenso è
dei **tutori** ed è **implicito**: chi amministra lo dà registrando il minore (`registra_utente`
scrive `voce_conservata` e `voce_conservata_da`, l'id di chi registra), e un minore già
registrato con i tutori nel profilo ce l'ha senza domanda. Lo revoca un tutore
(`minori.e_tutore`), a voce, con la stessa conferma di «svuota»; lo ridà a mano un tutore. Vale
finché c'è un tutore valido (il profilo esiste ed è ancora tutore). Il minore da solo non lo dà
né lo revoca. Il consenso dei tutori vale finché la persona è minore: da adulta lo ridice lei.

**La voce** si salva in G.711 μ-law (8 bit, 16 kHz, WAV con il formato 7): metà della PCM a 16
bit, letta da ffmpeg e sox, e codificata con numpy (già una dipendenza di base: principio 4,
niente librerie native nuove). Una frase di 3 s pesa ~48 KB; con le giornate vere della DGX
(dall'08 al 09/10: 1 300 s di parlato al giorno, ~75 % riconosciuto dalla voce) sono ~15 MB al
giorno, ~0,9 GB in 60 giorni. Tetto `conserva_voce_mb`: oltre, si tolgono i giorni più vecchi.
Cartella: `<turn_log_dir>/voce/<id della persona>/<AAAA-MM-GG>/<ora>.wav`, file 600 e
cartelle 700 su Linux. Fino al 14/10 sera la codifica non era G.711 (i lettori standard
sentivano rumore): i file nuovi portano un segno nel WAV, `leggi_wav` legge anche i vecchi e
`--converti-audio` li riscrive.

**La valutazione** (18/10, decisione 0032, issue #173): con `conserva_valutazione_fino:
"AAAA-MM-GG"`, fino a quella data compresa, si conserva tutto, ospiti compresi (sezione «la
valutazione» qui sotto). Vuoto di serie: le regole sopra, invariate.

**Privacy**: niente esce mai da qui (nessun invio, nessun tool che legga la cartella); nei log
solo conteggi, mai testo né nomi. La conservazione non usa la GPU: nel profilo ridotto da 8 GB
c'è uguale.

    python -m calliope.conserva                  quanto è conservato (solo conteggi)
    python -m calliope.conserva --svuota         tutto: voce, eventi, registro dei turni,
                                                 archivio delle conversazioni, testo della
                                                 stanza su disco, trascrizione e audio degli
                                                 avvisi di pericolo (14/10) e conoscenti
                                                 (impronte e profili)
    python -m calliope.conserva --svuota --persona NOME
                                                 i dati di una persona
    python -m calliope.conserva --converti-audio una tantum (14/10 sera): riscrive nel G.711
                                                 vero i WAV μ-law di prima (voce, banco della
                                                 stanza, audio degli avvisi); rilanciabile

Il consenso alla voce si dà e si revoca solo a voce, a Calliope (tool `dati_conservati`): da
terminale si legge e si svuota, non si cambia una scelta che è della persona.

Solo libreria standard e numpy.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import struct
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

CARTELLA_VOCE = "voce"
SEGNO_RIPULITO = ".conservazione-1"       # il registro dei turni di prima è già stato ripulito
COSE = ("testo", "voce", "eventi", "conversazioni", "stanza")
# Come è stata decisa l'identità della frase (SpeakerContext.identified_by e i modi del ciclo):
# con questi il testo resta. Fuori: la zona grigia («conversazione»), nessun modo. Il
# proprietario incerto con un minore («proprietario») dal 16/10 sì (decisione 0031: due persone
# di casa, il testo resta; la voce no, perché il modo non è «voce»)
MODI_TESTO = frozenset({"voce", "breve", "continuita", "schermo", "proprietario"})
# I segni di un dubbio con un minore nel campo `voce` del turno (ciclo._riconosci_voce): dal
# 16/10 tolgono solo la voce (l'audio può essere dell'altra persona), non il testo
DUBBI_MINORE = ("incerta", "minore_vicino", "minore_incerto")
# Esiti dei turni il cui audio non si tiene: frasi non rivolte a Calliope, la registrazione
# della voce, niente capito
ESITI_SENZA_VOCE = frozenset({None, "ignorato", "non_rivolta", "arruolamento", "vuoto",
                              "doppione", "saluto"})
# I campi con le parole nel registro dei turni (gli stessi che per gli ospiti erano già null)
CAMPI_TESTO = ("testo", "richiesta", "risposta", "risposta_inviata", "risposta_scritta")


@dataclass(frozen=True)
class Decisione:
    ok: bool
    motivo: str

    def __bool__(self) -> bool:
        return self.ok


# ─────────────────────────── la valutazione (18/10, decisione 0032) ───────────────────────────
# Con `conserva_valutazione_fino: "AAAA-MM-GG"` fino a quel giorno compreso si conserva tutto,
# ospiti compresi (eccezione alle decisioni 0031 e 0029 decisa da chi amministra, issue #173). Le
# scritture sono quelle di sempre, con meno filtri: le parole dei turni di tutti, l'audio di ogni
# frase del turno in `voce/_valutazione/<persona o «ospiti»>/` (quando la regola di sempre non lo
# terrebbe), il testo della stanza (righe segnate `sicurezza: valutazione`, che la ricerca e la
# guardia non leggono), l'audio di tutti i segmenti del banco, le conversazioni degli ospiti su
# disco (`ospite = 2`, che nessuna ricerca legge). Restano fuori sempre: la frase di sfida e i
# codici detti (`_segreto`), lo scritto (non c'è audio), la pausa della stanza, `conserva_voce:
# false`. I file restano per `turn_log_days`; «dimentica» e `--svuota` li tolgono come gli altri.
CARTELLA_VALUTAZIONE = "_valutazione"     # dentro la cartella della voce; mai un id (uuid hex)
VALUTAZIONE_OSPITI = "ospiti"             # la cartella delle frasi senza un profilo
# I motivi di `voce_turno` che valgono anche durante la valutazione: niente audio (scritto), frasi
# non rivolte o vuote (le prende la stanza), la voce spenta nel file, la frase di sfida e i codici
VOCE_MAI = frozenset({"scritto", "non_rivolta", "spenta", "segreto"})


def valutazione_fino(cfg) -> datetime.date | None:
    """La data di `conserva_valutazione_fino`, o None (vuoto o scritta male: spento)."""
    v = getattr(cfg, "conserva_valutazione_fino", "") if cfg is not None else ""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v or "").strip()) if v else None
    except ValueError:
        return None


def valutazione_attiva(cfg, oggi: datetime.date | None = None) -> bool:
    """Vale adesso la valutazione? Fino alla data compresa."""
    f = valutazione_fino(cfg)
    return f is not None and (oggi or datetime.date.today()) <= f


def testo_valutazione(cfg, oggi: datetime.date | None = None) -> str | None:
    """La riga dell'avvio, di `calliope stato` e del cruscotto; None se non c'è una data."""
    f = valutazione_fino(cfg)
    if f is None:
        return None
    if valutazione_attiva(cfg, oggi):
        return (f"Valutazione: si conserva tutto fino al {f.strftime('%d/%m/%Y')} compreso "
                f"(testo e audio, ospiti compresi; decisione 0032)")
    return (f"Valutazione finita il {f.strftime('%d/%m/%Y')}: si conserva come di serie (i file "
            f"fatti restano per {int(getattr(cfg, 'turn_log_days', 60) or 60)} giorni)")


def categoria(prof) -> str:
    """«ospite» (nessun profilo), «conoscente» (14/10, stanza/conoscenti.py: livello ospite),
    «minore», «amministra» o «adulto»."""
    if prof is None:
        return "ospite"
    if getattr(prof, "tipo", None) == "conoscente":
        return "conoscente"
    from . import minori
    try:
        if minori.e_minore(prof):
            return "minore"
    except Exception:  # noqa: BLE001 — una data rovinata: nel dubbio minore
        return "minore"
    return "amministra" if getattr(prof, "admin", False) else "adulto"


def tutori_validi(prof, registry=None) -> list[str]:
    """Gli id dei tutori nel profilo del minore che esistono ancora (con il registro delle voci;
    senza, tutti quelli scritti)."""
    ids = [str(t) for t in (getattr(prof, "tutori", None) or []) if t]
    by_id = getattr(registry, "by_id", None) if registry is not None else None
    if not callable(by_id):
        return ids
    return [t for t in ids if by_id(t) is not None]


def consenso_voce(prof, registry=None) -> bool:
    """La persona ha detto sì a tenere la sua voce? Per chi amministra, senza una scelta, sì.

    Per un minore (16/10, decisione 0031) il consenso è dei tutori e implicito: sì finché non
    è revocato (`voce_conservata` False) e c'è un tutore valido, cioè il tutore che l'ha dato
    (`voce_conservata_da`, il profilo esiste ed è ancora tutore: `minori.e_tutore`) o uno dei
    tutori del profilo che esiste ancora. Senza tutori validi, no. Per un adulto solo il suo sì:
    quello dato da un tutore quando era minore non vale più."""
    v = getattr(prof, "voce_conservata", None)
    da = getattr(prof, "voce_conservata_da", None)
    if categoria(prof) == "minore":
        if v is False:
            return False
        if v is True and da:
            by_id = getattr(registry, "by_id", None) if registry is not None else None
            if not callable(by_id):
                return True
            from . import minori
            t = by_id(da)
            if t is not None and minori.e_tutore(t, prof):
                return True
        return bool(tutori_validi(prof, registry))
    if v is True and da and da != getattr(prof, "id", None):
        return False
    if v is None:
        return bool(getattr(prof, "admin", False))
    return bool(v)


def voce_dei_tutori_scaduta(prof) -> bool:
    """Una persona diventata maggiorenne che aveva la voce conservata col sì dei tutori (16/10,
    issue #108): adulta, senza un suo sì, con il sì dato da un altro (`voce_conservata_da`) o i
    tutori ancora nel profilo (il consenso implicito della registrazione). Alla prima rotazione
    le sue registrazioni si cancellano (`consenso_voce`); serve solo a dirlo («stato», e una riga
    nel journal), non decide niente."""
    if prof is None or categoria(prof) in ("minore", "ospite", "conoscente"):
        return False
    v = getattr(prof, "voce_conservata", None)
    da = getattr(prof, "voce_conservata_da", None)
    if v is False or (v is True and (not da or da == getattr(prof, "id", None))):
        return False
    if v is None and getattr(prof, "admin", False):
        return False
    return bool((da and da != getattr(prof, "id", None)) or getattr(prof, "tutori", None))


def decidi(prof, cosa: str, modo: str | None = None, dubbi=(), cfg=None,
           registry=None) -> Decisione:
    """Il solo posto che decide se qualcosa di questa persona si conserva. Puro.

    `cosa`: «testo», «voce», «eventi», «conversazioni» o «stanza»; `modo`: come è stata decisa l'identità della frase;
    `dubbi`: i segni del turno («incerta», «minore_vicino», «compagnia»…).

    Un conoscente (categoria «conoscente», 14/10 sera, decisione 0030 aggiornata) segue le
    regole di un adulto: non è un minore (i bambini non si salvano come conoscenti) e la voce
    vuole il suo consenso (`voce_conservata`, che un conoscente non ha: niente voce).

    Un minore di casa (16/10, decisione 0031) come un adulto: testo, eventi e conversazioni sì;
    la voce col consenso dei tutori (`consenso_voce`). Nel dubbio tra un adulto e un minore il
    testo sì, la voce no."""
    if cosa not in COSE:
        raise ValueError(f"cosa sconosciuta: {cosa!r}")
    cat = categoria(prof)
    if cosa == "stanza":
        # Il testo della stanza (14/10, decisione 0029 punto 5, calliope/stanza/tenuta.py): con
        # la tenuta accesa (lo decide chi chiama) per tutta la famiglia, minori compresi, solo
        # con la voce riconosciuta sopra soglia; mai gli ospiti, nel dubbio no
        if cat == "ospite":
            return Decisione(False, cat)
        return Decisione(True, cat) if modo == "voce" else Decisione(False, "voce_incerta")
    if cat == "ospite":
        return Decisione(False, cat)
    if cosa in ("eventi", "conversazioni"):
        return Decisione(True, cat)
    dubbi = set(dubbi or ())
    if cosa == "testo":
        # Nel dubbio tra un adulto e un minore il ciclo scrive `modo: conversazione` con il segno
        # del dubbio (16/10, decisione 0031): il testo resta. Senza segno è la zona grigia: no
        if modo in MODI_TESTO or (modo == "conversazione" and dubbi & set(DUBBI_MINORE)):
            return Decisione(True, cat)
        return Decisione(False, "voce_incerta")
    if dubbi & set(DUBBI_MINORE):
        # Solo la voce (16/10, decisione 0031): l'audio può essere dell'altra persona
        return Decisione(False, "dubbio_minore")
    if cfg is not None and not getattr(cfg, "conserva_voce", True):
        return Decisione(False, "spenta")
    if modo != "voce":
        return Decisione(False, "voce_incerta")
    if "compagnia" in dubbi:
        return Decisione(False, "compagnia")
    if not consenso_voce(prof, registry):
        return Decisione(False, "senza_consenso")
    return Decisione(True, cat)


def console_riservata(speaker_ctx, registry) -> str | None:
    """Le parole di questa frase vanno nel terminale? Sulla DGX la console finisce nel journal di
    systemd, che resta: è conservazione anche lei. «ospite» (dal 03/10, analisi S9) → niente
    parole; None → le parole. *Storico, 12–16/10: anche «minore» (un minore riconosciuto, o la
    frase nel dubbio tra un adulto e un minore); dal 16/10 (decisione 0031) le frasi dei minori
    vanno nel journal come quelle degli adulti. `registry` resta per i chiamanti.*"""
    if speaker_ctx is None:
        return None
    k = getattr(speaker_ctx, "conoscente", None)
    if (isinstance(k, dict) and k.get("id")
            and not getattr(speaker_ctx, "current_speaker", None)):
        # Un conoscente (14/10 sera, decisione 0030 aggiornata): come un adulto, il nome e le
        # parole nel terminale (resta ospite per i permessi)
        return None
    if getattr(speaker_ctx, "current_level", None) == "ospite":
        return "ospite"
    return None


def dubbi_del_turno(rec: dict) -> set:
    """I segni di dubbio scritti dal ciclo nel campo `voce` del turno."""
    v = rec.get("voce") if isinstance(rec.get("voce"), dict) else {}
    out = {k for k in DUBBI_MINORE if v.get(k)}
    if v.get("compagnia"):
        out.add("compagnia")
    return out


def togli_testo(rec: dict) -> dict:
    """Il turno senza le parole (come per gli ospiti dal 01/10): restano i numeri, le regole e
    i nomi dei tool. Cambia `rec` e lo restituisce."""
    for key in ("testo", "risposta"):
        # Quante parole c'erano (07/10): «testo: null» si confondeva con una frase vuota
        if isinstance(rec.get(key), str):
            rec.setdefault(f"{key}_parole", len(rec[key].split()))
    for key in CAMPI_TESTO:
        if rec.get(key) is not None:
            rec[key] = None
    if rec.get("stt_corretta"):              # prima e dopo: le sue parole
        rec["stt_corretta"] = {}
    if isinstance(rec.get("stt_capito"), dict):
        rec["stt_capito"] = {k: v for k, v in rec["stt_capito"].items()
                             if k not in ("prima", "dopo")}
    if isinstance(rec.get("stt_argomento"), list):
        # Gli argomenti che nominano qualcosa (08/10): il valore detto, il nome noto vicino, la
        # correzione e il «forse intendeva» sono parole; restano probabilità ed esiti
        rec["stt_argomento"] = [{k: v for k, v in x.items()
                                 if k not in ("valore", "noto", "correzione", "forse")
                                 and not (k == "parole" and not isinstance(v, (int, float)))}
                                for x in rec["stt_argomento"] if isinstance(x, dict)]
    if isinstance(rec.get("tool"), list):
        rec["tool"] = [{k: v for k, v in ev.items() if k != "argomenti"}
                       for ev in rec["tool"] if isinstance(ev, dict)]
    rec.pop("approfondimento", None)
    if isinstance(rec.get("dopo_tool"), dict) and "frase" in rec["dopo_tool"]:
        # La frase del codice dopo un tool (15/10, system1/dopo_tool.py): parole
        rec["dopo_tool"] = {k: v for k, v in rec["dopo_tool"].items() if k != "frase"}
    return rec


# ─────────────────────────── la voce in μ-law ───────────────────────────
# G.711 μ-law vero (14/10 sera). Fino al 14/10 `mulaw` quantizzava in modo lineare la curva
# continua di μ-law su 0..255 e complementava il risultato: Calliope si rileggeva giusto, ma ogni
# lettore standard (ffmpeg, sox, libsndfile, il browser) sentiva un'onda capovolta e storta
# (SNR -4 dB su un tono). Ora i segmenti e la mantissa di G.711 (come il g711.c di riferimento,
# a 16 bit con BIAS 0x84 e tetto 32635), con numpy. I file nuovi portano un segno (un chunk
# LIST/INFO con ISFT «Calliope G.711»), quelli di prima no: `leggi_wav` legge tutti e due e
# `python -m calliope.conserva --converti-audio` riscrive i vecchi una volta per tutte.
_MU = 255.0
_BIAS = 0x84
_TETTO = 32635
SEGNO_G711 = b"Calliope G.711"
_TABELLA = None


def _tabella():
    """I 256 valori a 16 bit della decodifica G.711 (calcolati una volta)."""
    global _TABELLA
    if _TABELLA is None:
        import numpy as np
        u = (~np.arange(256, dtype=np.int32)) & 0xFF
        t = (((u & 0x0F) << 3) + _BIAS) << ((u & 0x70) >> 4)
        _TABELLA = np.where(u & 0x80, _BIAS - t, t - _BIAS).astype(np.float32) / 32768.0
    return _TABELLA


def mulaw(audio) -> bytes:
    """float32 in [-1, 1] (o int16) → byte G.711 μ-law (formato dei file WAV 7). Vettoriale."""
    import numpy as np
    a = np.asarray(audio)
    if a.dtype == np.int16:
        x = a.astype(np.int32)
    else:
        x = np.round(np.clip(a.astype(np.float32), -1.0, 1.0) * 32768.0).astype(np.int32)
        x = np.clip(x, -32768, 32767)
    x = x.reshape(-1)
    neg = x < 0
    mag = np.minimum(np.abs(x), _TETTO) + _BIAS            # 132..32767
    seg = np.clip(np.frexp(mag.astype(np.float64))[1] - 8, 0, 7)
    mant = (mag >> (seg + 3)) & 0x0F
    u = (seg << 4) | mant
    return np.where(neg, 0x7F ^ u, 0xFF ^ u).astype(np.uint8).tobytes()


def da_mulaw(dati: bytes):
    """Byte G.711 μ-law → float32 in [-1, 1]."""
    import numpy as np
    return _tabella()[np.frombuffer(dati, dtype=np.uint8)]


def da_mulaw_vecchio(dati: bytes):
    """Byte del formato di prima del 14/10 sera (curva continua quantizzata in modo lineare,
    complementata) → float32: per leggere e convertire i file senza il segno."""
    import numpy as np
    q = (~np.frombuffer(dati, dtype=np.uint8)).astype(np.float32)
    y = q / 255.0 * 2.0 - 1.0
    return (np.sign(y) * (np.power(1.0 + _MU, np.abs(y)) - 1.0) / _MU).astype(np.float32)


def _chunk_segno() -> bytes:
    """LIST/INFO con ISFT: il segno del formato G.711 vero, ignorato dai lettori standard."""
    testo = SEGNO_G711 + b"\x00"
    if len(testo) % 2:
        testo += b"\x00"
    info = b"INFO" + b"ISFT" + struct.pack("<I", len(testo)) + testo
    return b"LIST" + struct.pack("<I", len(info)) + info


def wav_da_byte(dati: bytes, sr: int) -> bytes:
    """Un file WAV μ-law intero da byte G.711 già codificati (RIFF, fmt con il formato 7,
    fact, LIST con il segno, data)."""
    n = len(dati)
    fmt = struct.pack("<HHIIHHH", 7, 1, int(sr), int(sr), 1, 8, 0)
    pad = b"\x00" if n % 2 else b""
    corpo = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
             + b"fact" + struct.pack("<II", 4, n) + _chunk_segno()
             + b"data" + struct.pack("<I", n) + dati + pad)
    return b"RIFF" + struct.pack("<I", len(corpo)) + corpo


def wav_mulaw(audio, sr: int) -> bytes:
    """Un file WAV μ-law intero dall'audio (float32 in [-1, 1] o int16)."""
    return wav_da_byte(mulaw(audio), sr)


def _pezzi_wav(b: bytes) -> dict:
    """I chunk di un WAV: fmt (formato, frequenza), dati, e se porta il segno G.711."""
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError("non è un WAV")
    i, out = 12, {"fmt": None, "sr": 16000, "dati": None, "segno": False}
    while i + 8 <= len(b):
        nome, lung = b[i:i + 4], struct.unpack("<I", b[i + 4:i + 8])[0]
        pezzo = b[i + 8:i + 8 + lung]
        if nome == b"fmt " and len(pezzo) >= 8:
            out["fmt"], _ch, out["sr"] = struct.unpack("<HHI", pezzo[:8])
        elif nome == b"data":
            out["dati"] = pezzo
        elif nome == b"LIST" and pezzo[:4] == b"INFO" and SEGNO_G711 in pezzo:
            out["segno"] = True
        i += 8 + lung + (lung % 2)
    return out


def formato_wav(b: bytes) -> str:
    """«g711» (μ-law vero, col segno), «vecchio» (μ-law senza il segno: scritto da Calliope
    prima del 14/10 sera), «pcm16» o «altro». Basta l'intestazione (il segno sta prima dei
    dati)."""
    try:
        w = _pezzi_wav(b)
    except (ValueError, struct.error):
        return "altro"
    if w["fmt"] == 7:
        return "g711" if w["segno"] else "vecchio"
    return "pcm16" if w["fmt"] == 1 else "altro"


def leggi_wav(path) -> tuple:
    """(audio float32, frequenza) da un WAV μ-law o PCM a 16 bit (per il banco e le prove).
    Un μ-law senza il segno è un file di Calliope di prima del 14/10 sera: si legge con la
    decodifica di allora (per un μ-law di fuori, senza segno, il risultato sarebbe storto:
    `leggi_wav` è per i file di Calliope)."""
    import numpy as np
    w = _pezzi_wav(Path(path).read_bytes())
    dati, fmt, sr = w["dati"], w["fmt"], w["sr"]
    if dati is None:
        raise ValueError("WAV senza dati")
    if fmt == 7:
        return (da_mulaw(dati) if w["segno"] else da_mulaw_vecchio(dati)), sr
    if fmt == 1:
        return np.frombuffer(dati, dtype="<i2").astype(np.float32) / 32768.0, sr
    raise ValueError(f"formato WAV {fmt} non letto")


# ── la conversione una tantum dei file di prima (14/10 sera) ──
TEMPORANEO_CONV = ".conv.tmp"


def converti_file(path: Path) -> tuple[str, int]:
    """Riscrive un WAV del formato di prima nel G.711 vero, al suo posto: (esito, byte nuovi).
    Esiti: «convertito», «nuovo» (già G.711 col segno: non si tocca), «altro» (non è un μ-law
    di Calliope: non si tocca), «sparito» (tolto nel frattempo, per esempio dalla rotazione).
    Atomico (file temporaneo accanto e `os.replace`): un'interruzione lascia il file vecchio
    intero, e rilanciare lo converte. Tiene i permessi (600) e la data del file."""
    path = Path(path)
    try:
        b = path.read_bytes()
        st = path.stat()
    except FileNotFoundError:
        return "sparito", 0
    f = formato_wav(b)
    if f != "vecchio":
        return ("nuovo" if f == "g711" else "altro"), 0
    w = _pezzi_wav(b)
    if w["dati"] is None:
        return "altro", 0
    nuovo = wav_da_byte(mulaw(da_mulaw_vecchio(w["dati"])), w["sr"])
    tmp = path.with_name(path.name + TEMPORANEO_CONV)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
                 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(nuovo)
            fh.flush()
            os.fsync(fh.fileno())
        if os.name != "nt":
            os.chmod(tmp, st.st_mode & 0o777)
        os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
        if not path.exists():               # tolto mentre lo riscrivevo: non lo si ricrea
            tmp.unlink(missing_ok=True)
            return "sparito", 0
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return "convertito", len(nuovo)


def converti_audio(cfg, log=print) -> dict:
    """`calliope conserva --converti-audio`: i WAV μ-law scritti da Calliope prima del 14/10
    sera (voce conservata, audio del banco della stanza, audio degli avvisi nei cassetti dei
    tutori) riscritti nel G.711 vero. Idempotente: i file già nuovi e quelli d'altro formato non
    si toccano; i temporanei lasciati da un giro interrotto si tolgono. Solo conteggi."""
    out = {"convertiti": 0, "voce": 0, "banco": 0, "avvisi": 0, "gia_nuovi": 0, "altri": 0,
           "spariti": 0, "errori": 0, "temporanei": 0}

    def uno(p: Path, area: str):
        try:
            esito, _n = converti_file(p)
        except Exception as e:  # noqa: BLE001 — un file storto non ferma gli altri
            out["errori"] += 1
            log(f"   [CONSERVA] un file non convertito: {type(e).__name__}")
            return None
        if esito == "convertito":
            out["convertiti"] += 1
            out[area] += 1
        else:
            out[{"nuovo": "gia_nuovi", "altro": "altri", "sparito": "spariti"}[esito]] += 1
        return esito

    def temporanei(base: Path):
        for t in base.rglob("*" + TEMPORANEO_CONV):
            try:
                t.unlink()
                out["temporanei"] += 1
            except OSError:
                pass

    d = getattr(cfg, "turn_log_dir", None)
    if d:
        from .stanza.banco import CARTELLA as CARTELLA_BANCO
        for sotto, area in ((CARTELLA_VOCE, "voce"), (CARTELLA_BANCO, "banco")):
            base = Path(d) / sotto
            if not base.exists():
                continue
            temporanei(base)
            for p in sorted(base.rglob("*.wav")):
                uno(p, area)
    _converti_avvisi(cfg, uno, temporanei, out, log)
    return out


def _converti_avvisi(cfg, uno, temporanei, out, log):
    """L'audio degli avvisi di pericolo nei cassetti dei tutori (righe `fonte = 'avviso'`,
    categoria audio): solo quelle, mai gli altri file del cassetto (un audio mandato da una
    persona resta com'è). La dimensione nella riga si aggiorna (il segno aggiunge pochi byte)."""
    import sqlite3
    db = str(getattr(cfg, "memory_db", "") or "")
    if not db or not Path(db).exists():
        return
    base = (Path(getattr(cfg, "cassetto_cartella", "") or "")
            if getattr(cfg, "cassetto_cartella", "") else Path(db).resolve().parent / "cassetto")
    try:
        con = sqlite3.connect(db, timeout=10)
    except sqlite3.Error:
        return
    try:
        if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                       "AND name = 'cassetto_file'").fetchone() is None:
            return
        from .cassetto import _cartella_persona
        righe = con.execute("SELECT id, persona, file FROM cassetto_file WHERE fonte = 'avviso' "
                            "AND categoria = 'audio' AND stato = 'attivo'").fetchall()
        if righe and base.exists():
            temporanei(base)
        for fid, persona, nome in righe:
            p = base / _cartella_persona(persona) / nome
            if uno(p, "avvisi") == "convertito":
                try:
                    with con:
                        con.execute("UPDATE cassetto_file SET dimensione = ? WHERE id = ?",
                                    (p.stat().st_size, fid))
                except (OSError, sqlite3.Error) as e:
                    log(f"   [CONSERVA] dimensione di un avviso non aggiornata: "
                        f"{type(e).__name__}")
    except sqlite3.Error as e:
        log(f"   [CONSERVA] cassetto non letto: {type(e).__name__}")
    finally:
        con.close()


def testo_conversione(r: dict) -> str:
    conv = r["convertiti"]
    righe = [f"Audio riscritto nel G.711 vero: {conv} file"
             + (f" ({r['voce']} della voce conservata, {r['banco']} del banco della stanza, "
                f"{r['avvisi']} degli avvisi)" if conv else "") + "."]
    righe.append(f"Già nel formato vero: {r['gia_nuovi']}; d'altro formato, non toccati: "
                 f"{r['altri']}; tolti durante il giro: {r['spariti']}; errori: {r['errori']}.")
    if r["temporanei"]:
        righe.append(f"Temporanei di un giro interrotto tolti: {r['temporanei']}.")
    if r["errori"]:
        righe.append("Rilancia il comando: i file già convertiti non si toccano.")
    return "\n".join(righe)


def _segreto(rec: dict) -> bool:
    """Nella frase c'è qualcosa che non deve restare nemmeno come suono: le parole della frase
    di sfida, un codice o un segreto detto (tolti dal testo: «******»)."""
    if {"sfida_voce", "sfida_risposta"} & set(rec.get("regole") or ()):
        return True
    if rec.get("testo") == "(frase di conferma)" or "******" in str(rec.get("testo") or ""):
        return True
    return any(isinstance(ev, dict) and "******" in json.dumps(ev.get("argomenti") or {},
                                                               ensure_ascii=False)
               for ev in rec.get("tool") or ())


def _scrivi_privato(path: Path, dati: bytes):
    """Il file con i permessi stretti già alla creazione (600 su Linux), atomico."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0),
                 0o600)
    try:
        os.write(fd, dati)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _mb(p: Path) -> float:
    tot = 0
    for f in p.rglob("*.wav") if p.exists() else ():
        try:
            tot += f.stat().st_size
        except OSError:
            pass
    return tot / 1e6


# ─────────────────────────── il registro dei turni ───────────────────────────
def ripulisci_turni(cartella, tieni, lock=None) -> dict:
    """Riscrive i file del registro dei turni togliendo le parole dei turni per cui `tieni(rec)`
    è falso (minori, ospiti, voci incerte, una persona da dimenticare). Atomico per file;
    restituisce {"file", "turni"} cambiati. Righe rotte: restano come sono."""
    out = {"file": 0, "turni": 0}
    p = Path(cartella)
    if not p.exists():
        return out
    for f in sorted(p.glob("turni-*.jsonl")):
        with (lock or threading.Lock()):
            try:
                righe = f.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            nuove, cambiati = [], 0
            for r in righe:
                try:
                    rec = json.loads(r)
                except ValueError:
                    nuove.append(r)
                    continue
                if isinstance(rec, dict) and _ha_testo(rec) and not tieni(rec):
                    togli_testo(rec)
                    cambiati += 1
                    r = json.dumps(rec, ensure_ascii=False, default=str)
                nuove.append(r)
            if cambiati:
                _scrivi_privato(f, ("\n".join(nuove) + "\n").encode("utf-8"))
                out["file"] += 1
                out["turni"] += cambiati
    return out


def _ha_testo(rec: dict) -> bool:
    return any(isinstance(rec.get(k), str) and rec.get(k) for k in CAMPI_TESTO) or bool(
        rec.get("stt_corretta")) or any(isinstance(ev, dict) and ev.get("argomenti")
                                        for ev in rec.get("tool") or ()) or (
        isinstance(rec.get("dopo_tool"), dict) and bool(rec["dopo_tool"].get("frase")))


# Le tabelle di memoria.db con il testo dei ragazzi che scadono con la stessa tenuta (12/10
# sera, decisione di Dario): (tabella, colonna della persona, colonna della data ISO). Le
# richieste ai tutori (con `oggetto`, ciò che il ragazzo ha chiesto). *[storico: fino al 28/10
# anche le quattro tabelle degli esercizi (`esercizi_tentativi`, `_segnalazioni`,
# `_preferenze`, `_punto`), tolte con gli esercizi, #279; le righe vecchie nel db non si
# migrano]*
TABELLE_MEMORIA = (("richieste_tutori", "minore", "creata"),)
# Le tabelle dello Studio (29/10, issue #280, decisione 0035, punto 4): non scadono con la data
# della riga ma con quella della verifica, `studio_tenuta_giorni` (60) giorni dopo; mai se
# archiviata. Le cancella solo calliope/studio/dati.cancella (verifiche, materiali, pagine col
# testo letto e i loro file, argomenti, piano, misure, giorni e, dal 30/10 (#244), gli eventi
# delle sessioni; dal 30/10, #245 e #246, i tentativi e le carte; dal 31/10, #248, le domande e le
# prove; dal 31/10, #250, le indicazioni dei tutori; dal 31/10, #296, le stelle, gli interruttori
# dei premi e i duelli; dal 31/10, #278, gli esercizi guidati), dalla rotazione e da «svuota»;
# «dimentica le nostre conversazioni» le toglie tranne le verifiche archiviate (main.py)
TABELLE_STUDIO = ("studio_verifiche", "studio_materiali", "studio_pagine", "studio_argomenti",
                  "studio_piano", "studio_giorni", "studio_misure", "studio_eventi",
                  "studio_tentativi", "studio_carte", "studio_mappe", "studio_domande",
                  "studio_prove", "studio_indicazioni", "studio_stelle", "studio_premi",
                  "studio_duelli", "studio_pratica", "studio_esercizi")
# Le preferenze che non scadono col tempo ma vanno via con i dati della persona (27/10):
# (tabella, colonna della persona). L'accento scelto in Io › Aspetto (schermi/aspetto.py)
TABELLE_PREFERENZE = (("aspetto_preferenze", "persona"),)
# Le tabelle dismesse di memoria.db (28/10, revisione della PR #292): quelle degli esercizi e il
# riepilogo dei compiti, tolti con la #279. Avevano domande, risposte e note dei ragazzi, e
# nessuno le ruota né le svuota più: si tolgono da sole all'apertura della memoria
# (`togli_tabelle_dismesse`, da memory.Memory), con una riga nel registro. Una tabella dismessa
# in futuro si aggiunge qui
TABELLE_DISMESSE = ("esercizi_tentativi", "esercizi_segnalazioni", "esercizi_preferenze",
                    "esercizi_punto", "esercizi_banco", "compiti_giorno")
# Le versioni di schema che vanno via con loro: «esercizi» (le sue tabelle) e «dismesse» (il segno
# «una volta sola» del primo giro di questa pulizia, 28/10, che non si usa più)
_MODULI_DISMESSI = ("esercizi", "dismesse")


def togli_tabelle_dismesse(db, log=print) -> list[str]:
    """`DROP TABLE` delle TABELLE_DISMESSE che ci sono, a ogni apertura (seconda revisione della
    PR #292): costa un SELECT su `sqlite_master`, e se si torna a una versione di prima, che le
    ricrea, al ritorno avanti si tolgono di nuovo. Nessun segno in `meta_schema`, quindi nessuna
    versione «più nuova» che possa mettere la memoria in sola lettura. Toglie anche le versioni
    di `_MODULI_DISMESSI`. Tutto in una transazione: un errore la annulla e non la lascia aperta.
    `secure_delete` solo per il tempo del DROP, poi com'era. Le tabelle tolte, per la riga nel
    registro (scritta solo se ne toglie qualcuna); [] se non c'era niente."""
    nomi = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    tolte = [t for t in TABELLE_DISMESSE if t in nomi]
    moduli = []
    if "meta_schema" in nomi:
        segni = ",".join("?" * len(_MODULI_DISMESSI))
        moduli = [r[0] for r in db.execute(
            f"SELECT modulo FROM meta_schema WHERE modulo IN ({segni})", _MODULI_DISMESSI)]
    if not tolte and not moduli:
        return []
    if db.in_transaction:
        db.commit()
    prima = db.execute("PRAGMA secure_delete").fetchone()[0]
    db.execute("PRAGMA secure_delete = ON")
    try:
        db.execute("BEGIN IMMEDIATE")
        for t in tolte:
            db.execute(f"DROP TABLE IF EXISTS {t}")
        for m in moduli:
            db.execute("DELETE FROM meta_schema WHERE modulo = ?", (m,))
        db.commit()
    except Exception:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.execute(f"PRAGMA secure_delete = {int(prima)}")
    if tolte:
        log(f"[CONSERVA] tabelle dismesse tolte da memoria.db (esercizi e compiti, #279): "
            f"{', '.join(tolte)}")
    return tolte


class Conservazione:
    """La conservazione di questa installazione: chi, dove, per quanto. Un oggetto per processo
    (main.py), condiviso da registro dei turni, ciclo, registro degli eventi e tool."""

    def __init__(self, cfg, registry=None, log=print):
        self.cfg = cfg
        self.registry = registry
        self.log = log
        d = getattr(cfg, "turn_log_dir", None)
        self.cartella = Path(d) if d else None
        self.voce_dir = self.cartella / CARTELLA_VOCE if self.cartella else None
        self.giorni = int(getattr(cfg, "turn_log_days", 60) or 60)
        self.mb = float(getattr(cfg, "conserva_voce_mb", 2000) or 0)
        self.eventi = None          # eventi.registro.Disco, se c'è (main.py)
        # L'archivio delle conversazioni (calliope/conversazioni.ArchivioConversazioni), se c'è:
        # «svuota» lo svuota e il riepilogo lo conta (main.py e il terminale)
        self.conversazioni = None
        self.turnlog = None         # TurnLog, se c'è (main.py)
        # La tenuta su disco della stanza (stanza/tenuta.Tenuta, 14/10), se c'è: «svuota» la
        # svuota e il riepilogo la conta; senza (il terminale), il file in `stanza_tenuta_db`
        self.stanza = None
        # I conoscenti (stanza/conoscenti.Conoscenti, 14/10), se ci sono: «svuota» di tutto li
        # cancella; senza (il terminale), il file `conoscenti_file`. Dal 14/10 sera sono anche
        # profili della conservazione (`profilo`)
        self.conoscenti = None
        self._conoscenti_file = (None, {})     # (firma, id → Conoscente) dal file
        self._svuotando = False
        self._lock = threading.Lock()
        self._ruotata_il = None
        # La valutazione (18/10, decisione 0032): vista accesa in questo processo, per dire una
        # volta nel log quando finisce
        self._valutazione_vista = None
        self.salvate = 0            # frasi salvate da quando è partita
        self.errori = 0
        self.proposte: dict = {}    # persona → turno della domanda (tool dati_conservati)

    # ── i profili ──
    def profilo(self, nome=None, persona_id=None):
        reg = self.registry
        if reg is None:
            return None
        if persona_id:
            by_id = getattr(reg, "by_id", None)
            p = by_id(persona_id) if by_id else None
            if p is not None:
                return p
            # Un conoscente (14/10 sera): lo stesso id dopo una promozione è del familiare
            k = self.conoscente(persona_id)
            if k is not None:
                return k
        if nome:
            get = getattr(reg, "get", None)
            return get(nome) if get else None
        return None

    def conoscente(self, persona_id):
        """Il conoscente con questo id (14/10 sera, decisione 0030 aggiornata), o None: dai
        conoscenti di Calliope, o (terminale, conoscenti spenti) dal file in sola lettura."""
        if not persona_id:
            return None
        con = self.conoscenti
        try:
            if con is not None:
                return con.per_id(persona_id)
            from .stanza import conoscenti as K
            firma, dati = self._conoscenti_file
            nuova = K.firma_file(self.cfg)
            if nuova != firma:
                dati = K.leggi_file(self.cfg) if nuova is not None else {}
                self._conoscenti_file = (nuova, dati)
            return dati.get(str(persona_id))
        except Exception:  # noqa: BLE001 — un file che non si legge: nessun conoscente
            return None

    def _conoscenti_tutti(self) -> list:
        con = self.conoscenti
        try:
            if con is not None:
                return list(con.elenco())
            self.conoscente("-")                    # rilegge il file se è cambiato
            return list(self._conoscenti_file[1].values())
        except Exception:  # noqa: BLE001
            return []

    def conoscenti_ids(self) -> list[str]:
        """Gli id dei conoscenti salvati (14/10 sera): le loro conversazioni su disco le ritrova
        chi amministra con `ospiti=true` (conversazioni.ArchivioConversazioni.cerca)."""
        return [str(c.id) for c in self._conoscenti_tutti()]

    def trova_conoscenti(self, chi: str) -> list:
        """I conoscenti che rispondono a «Marco», «Marco Rossi», «Marco collega di Carlo»
        (Conoscenti.trova, anche dal file): per svuotare i dati di uno di loro."""
        from .stanza.conoscenti import trova_in
        return trova_in(self._conoscenti_tutti(), chi)

    def conoscente_tolto(self, persona_id):
        """Un conoscente dimenticato, scaduto o svuotato (Conoscenti.su_tolto, 14/10 sera): via
        anche i suoi turni con le parole, gli eventi e le conversazioni archiviate. Dentro uno
        «svuota» di tutto non serve (si cancella già tutto)."""
        if self._svuotando or not persona_id:
            return None
        try:
            r = self.svuota(str(persona_id))
            self.log(f"   [CONSERVA] conoscente tolto: parole tolte da {r['turni']} turni, "
                     f"{r['conversazioni']} conversazioni, {r['eventi']} eventi")
            return r
        except Exception as e:  # noqa: BLE001 — la pulizia non ferma niente
            self.log(f"   [CONSERVA] dati del conoscente non tolti: {type(e).__name__}")
            return None

    # ── la valutazione (18/10, decisione 0032) ──
    def valutazione(self) -> bool:
        """Vale adesso la valutazione? Alla scadenza (vista accesa in questo processo) lo dice
        una volta nel log: da lì si conserva come di serie."""
        attiva = valutazione_attiva(self.cfg)
        if self._valutazione_vista and not attiva:
            f = valutazione_fino(self.cfg)
            self.log(f"   [CONSERVA] Valutazione finita"
                     + (f" il {f.strftime('%d/%m/%Y')}" if f else "")
                     + f": da adesso si conserva come di serie (i file fatti restano per "
                       f"{self.giorni} giorni)")
        self._valutazione_vista = attiva
        return attiva

    # ── le decisioni (sempre da `decidi`) ──
    def testo_turno(self, rec: dict) -> Decisione:
        """Le parole di questo turno restano nel registro dei turni e negli eventi su disco?
        Durante la valutazione (18/10, decisione 0032) sì per tutti: «valutazione»."""
        d = self._testo_turno(rec)
        if not d and isinstance(rec, dict) and self.valutazione():
            return Decisione(True, "valutazione")
        return d

    def testo_di_serie(self, rec: dict) -> Decisione:
        """La regola di serie, quale che sia la valutazione: per chi **usa** le parole (l'archivio
        della persona, il registro degli eventi, il contesto), non solo le conserva (revisione
        della PR #178: la zona grigia diventava leggibile da `chat` e `cerca`)."""
        return self._testo_turno(rec)

    def _testo_turno(self, rec: dict) -> Decisione:
        """La regola di serie (decisioni 0028, 0030 e 0031)."""
        if not isinstance(rec, dict):
            return Decisione(False, "ospite")
        v = rec.get("voce") if isinstance(rec.get("voce"), dict) else {}
        if v.get("conoscente") and v.get("id") and not v.get("nome"):
            # Un conoscente (14/10 sera, decisione 0030 aggiornata): livello ospite, ma per la
            # conservazione vale come un adulto, se il suo profilo c'è ancora. Una fascia d'età
            # nel turno vuol dire un bambino: mai come conoscente (0030 punto 6)
            if isinstance(rec.get("ascolto"), dict) and rec["ascolto"].get("fascia"):
                return Decisione(False, "minore")
            prof = self.conoscente(v.get("id"))
            if prof is None:
                return Decisione(False, "ospite")
            return decidi(prof, "testo", v.get("modo"), dubbi_del_turno(rec), self.cfg)
        if rec.get("livello") == "ospite":
            return Decisione(False, "ospite")
        if not v.get("nome"):
            return Decisione(False, "ospite")
        # Dal 16/10 (decisione 0031) la fascia d'età nel campo `ascolto` non toglie più le
        # parole: un minore di casa si conserva come un adulto
        prof = self.profilo(nome=v.get("nome"), persona_id=v.get("id"))
        return decidi(prof, "testo", v.get("modo"), self.dubbi_di_casa(rec), self.cfg)

    def dubbi_di_casa(self, rec: dict) -> set:
        """I segni di dubbio del turno, con «incerta» solo se la voce è davvero di una delle due
        persone di casa (16/10, decisione 0031): il punteggio migliore della frase sopra
        `speaker_id_threshold`. Sotto, `minori.piu_protetto` ha dato al minore una voce di
        nessuno (un ospite vicino al suo profilo), e il turno resta fuori come la zona grigia."""
        dubbi = dubbi_del_turno(rec)
        v = rec.get("voce") if isinstance(rec.get("voce"), dict) else {}
        if "incerta" in dubbi and v.get("modo") == "conversazione":
            soglia = float(getattr(self.cfg, "speaker_id_threshold", 0.48) or 0.48)
            try:
                sopra = float(v.get("punteggio")) >= soglia
            except (TypeError, ValueError):
                sopra = False
            if not sopra:
                dubbi.discard("incerta")
        return dubbi

    def voce_turno(self, rec: dict) -> Decisione:
        """L'audio di questo turno si tiene?"""
        if not isinstance(rec, dict) or rec.get("canale") == "scritto":
            return Decisione(False, "scritto")
        if rec.get("esito") in ESITI_SENZA_VOCE or not (isinstance(rec.get("testo"), str)
                                                        and rec["testo"].strip()):
            return Decisione(False, "non_rivolta")
        if not self.voce_dir:
            return Decisione(False, "spenta")
        if _segreto(rec):
            return Decisione(False, "segreto")
        d = self.testo_turno(rec)
        if not d:
            return d
        v = rec.get("voce") or {}
        prof = self.profilo(nome=v.get("nome"), persona_id=v.get("id"))
        if prof is None:
            return Decisione(False, "ospite")
        return decidi(prof, "voce", v.get("modo"), dubbi_del_turno(rec), self.cfg,
                      self.registry)

    def registro_su_disco(self, chiave: str) -> bool:
        """Il registro degli eventi di questa chiave va su disco? Le persone di casa sì, minori
        compresi (16/10, decisione 0031); ospiti, voci incerte (`ospite:<corsia>`) e profili
        tolti restano in memoria."""
        chiave = str(chiave or "")
        if chiave == "casa":
            return True
        if not chiave.startswith("persona:"):
            return False
        return bool(decidi(self.profilo(persona_id=chiave.split(":", 1)[1]), "eventi"))

    def conversazioni_su_disco(self, persona_id) -> bool | None:
        """Le conversazioni di questa persona vanno nell'archivio su disco? Le persone di casa
        sì, minori compresi (16/10, decisione 0031); ospiti e profili tolti no (restano
        nell'archivio della sessione). None quando
        non si può dire: nessun profilo letto (speakers.json mancante o illeggibile). Allora
        l'archivio non scrive su disco (nel dubbio no), ma la rotazione non cancella le
        conversazioni delle persone (un file illeggibile per un momento non toglie 60 giorni)."""
        reg = self.registry
        if reg is None or not getattr(reg, "users", None):
            return None
        if not persona_id:
            return False
        return bool(decidi(self.profilo(persona_id=str(persona_id)), "conversazioni"))

    # ── al turno (il ciclo, prima del registro degli eventi e di quello dei turni) ──
    def al_turno(self, rec: dict, audio=None, sr: int = 16000) -> dict:
        """Segna nel turno se le parole restano (`conserva`, letto dall'ombra degli eventi e dal
        registro dei turni) e salva la voce se si può. Non solleva mai."""
        try:
            d = self.testo_turno(rec)
            if not d:
                rec["conserva"] = {"testo": False, "motivo": d.motivo}
            elif d.motivo == "valutazione":
                # Le parole restano per la valutazione (18/10, decisione 0032): il segno dice
                # anche la regola di serie, così le misure distinguono questi turni
                rec["conserva"] = {"testo": True, "motivo": "valutazione",
                                   "di_serie": self._testo_turno(rec).motivo}
            if audio is not None and len(audio):
                f = self.salva_voce(rec, audio, sr)
                if f:
                    rec["voce_file"] = f
        except Exception as e:  # noqa: BLE001 — la conservazione non ferma la voce
            self.errori += 1
            if self.errori == 1 or self.errori % 100 == 0:
                self.log(f"   [CONSERVA] turno non conservato ({type(e).__name__}); errori: "
                         f"{self.errori}")
        return rec

    def salva_voce(self, rec: dict, audio, sr: int = 16000) -> str | None:
        """La frase in μ-law, se la decisione lo permette: il percorso relativo alla cartella
        della voce, o None."""
        d = self.voce_turno(rec)
        if not d:
            if (d.motivo in VOCE_MAI or not getattr(self.cfg, "conserva_voce", True)
                    or not self.valutazione() or self._voce_revocata(rec)):
                return None
            return self._salva_valutazione(rec, audio, sr)
        v = rec.get("voce") or {}
        prof = self.profilo(nome=v.get("nome"), persona_id=v.get("id"))
        pid = getattr(prof, "id", None)
        if not pid:
            return None
        quando = str(rec.get("inizio") or datetime.datetime.now().isoformat())
        giorno = quando[:10]
        ora = quando[11:23].replace(":", "").replace(".", "-") or time.strftime("%H%M%S")
        rel = f"{pid}/{giorno}/{ora}.wav"
        _scrivi_privato(self.voce_dir / rel, wav_mulaw(audio, sr))
        self.salvate += 1
        self.ruota_se_serve()
        return rel

    def _voce_revocata(self, rec: dict) -> bool:
        """La persona del turno ha detto «no» alla voce (`voce_conservata: false`, anche la revoca
        di un tutore): la revoca vale anche durante la valutazione (revisione della PR #178). Un
        consenso mai chiesto, invece, non ferma la valutazione."""
        v = rec.get("voce") if isinstance(rec.get("voce"), dict) else {}
        prof = self.profilo(nome=v.get("nome"), persona_id=v.get("id"))
        return prof is not None and getattr(prof, "voce_conservata", None) is False

    def _chi_valutazione(self, rec: dict) -> str:
        """La cartella della valutazione per questo turno: l'id del profilo (o del conoscente)
        se c'è, anche quello deciso nella zona grigia; altrimenti «ospiti»."""
        v = rec.get("voce") if isinstance(rec.get("voce"), dict) else {}
        prof = self.profilo(nome=v.get("nome"), persona_id=v.get("id"))
        pid = str(getattr(prof, "id", None) or "")
        pulito = "".join(c for c in pid if c.isalnum() or c in "-_")[:64]
        return pulito if pulito and pulito != CARTELLA_VALUTAZIONE else VALUTAZIONE_OSPITI

    def _salva_valutazione(self, rec: dict, audio, sr: int = 16000) -> str | None:
        """La frase che la regola di serie non terrebbe (ospite, zona grigia, senza consenso,
        compagnia, dubbio con un minore), durante la valutazione (18/10, decisione 0032): stesso
        formato, in `voce/_valutazione/<persona o «ospiti»>/<giorno>/<ora>.wav`. Sotto il tetto
        `conserva_voce_mb` come il resto."""
        if not self.voce_dir:
            return None
        quando = str(rec.get("inizio") or datetime.datetime.now().isoformat())
        giorno = quando[:10]
        ora = quando[11:23].replace(":", "").replace(".", "-") or time.strftime("%H%M%S")
        rel = f"{CARTELLA_VALUTAZIONE}/{self._chi_valutazione(rec)}/{giorno}/{ora}.wav"
        _scrivi_privato(self.voce_dir / rel, wav_mulaw(audio, sr))
        rec["voce_valutazione"] = True
        self.salvate += 1
        self.ruota_se_serve()
        return rel

    # ── consenso ──
    def imposta_consenso(self, prof, valore: bool, da: str | None = None) -> int:
        """Salva la scelta nel profilo; con un no cancella anche la voce che c'era. Restituisce
        quante registrazioni ha cancellato. `da`: l'id del tutore che decide per un minore
        (16/10, decisione 0031); None quando decide la persona stessa."""
        prof.voce_conservata = bool(valore)
        prof.voce_conservata_il = datetime.date.today().isoformat()
        prof.voce_conservata_da = str(da) if da else None
        save = getattr(self.registry, "save", None)
        if callable(save):
            save()
        if valore:
            return 0
        return self.cancella_voce(getattr(prof, "id", None))

    def cancella_voce(self, persona_id) -> int:
        if not persona_id or not self.voce_dir:
            return 0
        n = 0
        # Anche le frasi della valutazione (18/10, decisione 0032) sotto il suo id
        for p in (self.voce_dir / str(persona_id),
                  self.voce_dir / CARTELLA_VALUTAZIONE / str(persona_id)):
            n += sum(1 for _ in p.rglob("*.wav")) if p.exists() else 0
            shutil.rmtree(p, ignore_errors=True)
        return n

    def registrazioni(self, persona_id) -> int:
        if not persona_id or not self.voce_dir:
            return 0
        return sum(sum(1 for _ in p.rglob("*.wav")) if p.exists() else 0
                   for p in (self.voce_dir / str(persona_id),
                             self.voce_dir / CARTELLA_VALUTAZIONE / str(persona_id)))

    # ── rotazione ──
    def ruota_se_serve(self):
        """Una volta al giorno, in secondo piano: la voce non aspetta il giro delle cartelle."""
        oggi = datetime.date.today()
        if self._ruotata_il != oggi:
            self._ruotata_il = oggi
            if self._valutazione_vista:
                self.valutazione()        # il giorno dopo la data: lo dice il log (decisione 0032)

            def giro():
                try:
                    self.ruota(oggi)
                except Exception as e:  # noqa: BLE001 — la rotazione non ferma niente
                    self.log(f"   [CONSERVA] rotazione non riuscita: {type(e).__name__}")
            threading.Thread(target=giro, daemon=True, name="conserva-rotazione").start()

    def _cartelle_voce(self) -> list[tuple[Path, bool]]:
        """(cartella di una persona, della valutazione?): quelle delle persone e, dentro
        `_valutazione` (18/10, decisione 0032), quelle per persona o «ospiti»."""
        out = []
        for x in self.voce_dir.iterdir():
            if not x.is_dir():
                continue
            if x.name == CARTELLA_VALUTAZIONE:
                out += [(y, True) for y in x.iterdir() if y.is_dir()]
            else:
                out.append((x, False))
        return out

    def ruota(self, oggi: datetime.date | None = None) -> dict:
        """Esercizi e richieste ai tutori oltre `turn_log_days` (12/10 sera). La voce: via i
        giorni oltre `turn_log_days`, le persone senza più il diritto (consenso
        revocato, profilo tolto, un minore senza il sì di un tutore, un adulto col sì dato da un
        tutore quando era minore… nel dubbio via) e, oltre il tetto di spazio, i giorni più
        vecchi. Il registro dei turni ha la sua (TurnLog._prune), gli eventi pure
        (Disco.ruota)."""
        oggi = oggi or datetime.date.today()
        self._ruotata_il = oggi
        out = {"giorni": 0, "persone": 0, "tetto": 0}
        limite = oggi - datetime.timedelta(days=self.giorni)
        # Esercizi e richieste ai tutori (12/10 sera): la stessa tenuta, anche quelli di prima
        # (alla prima rotazione, all'avvio: niente migrazioni)
        out["memoria"] = self._memoria(limite=limite)
        # Lo Studio (29/10, #280): le verifiche non archiviate oltre `studio_tenuta_giorni` dopo
        # la loro data, con pagine, testo letto e file
        out["studio"] = self._studio(scadute_prima=oggi - datetime.timedelta(
            days=int(getattr(self.cfg, "studio_tenuta_giorni", 60) or 60)))
        # L'audio del banco della stanza (17/10, issue #32): la sua rotazione girava solo
        # salvando, cioè con l'eccezione accesa; scaduta o spenta, i giorni oltre
        # `turn_log_days` restavano. Ora anche qui, all'avvio e a ogni giorno nuovo
        out["banco"] = self._ruota_banco(oggi)
        if not self.voce_dir or not self.voce_dir.exists():
            return out
        with self._lock:
            giorni: list[tuple[str, Path]] = []
            for pdir, valut in self._cartelle_voce():
                prof = self.profilo(persona_id=pdir.name)
                if valut:
                    # La valutazione (18/10, decisione 0032): niente consenso da guardare, i
                    # giorni restano per `turn_log_days` anche a valutazione finita; via le
                    # cartelle di un profilo tolto, e tutto con `conserva_voce: false`
                    via = (not getattr(self.cfg, "conserva_voce", True)
                           or (pdir.name != VALUTAZIONE_OSPITI and prof is None))
                elif prof is None or not consenso_voce(prof, self.registry) \
                        or not getattr(self.cfg, "conserva_voce", True):
                    via = True
                else:
                    via = False
                if via:
                    if (not valut and voce_dei_tutori_scaduta(prof)
                            and getattr(self.cfg, "conserva_voce", True)):
                        # Diventata maggiorenne (16/10, issue #108): il sì dei tutori non vale
                        # più, da adulta lo ridice lei. Una riga con l'id, mai il nome
                        self.log(f"   [CONSERVA] {pdir.name}: maggiorenne, tolte le "
                                 "registrazioni della voce tenute col sì dei tutori")
                        out["maggiorenni"] = out.get("maggiorenni", 0) + 1
                    shutil.rmtree(pdir, ignore_errors=True)
                    out["persone"] += 1
                    continue
                for gdir in [x for x in pdir.iterdir() if x.is_dir()]:
                    try:
                        g = datetime.date.fromisoformat(gdir.name)
                    except ValueError:
                        continue
                    if g < limite:
                        shutil.rmtree(gdir, ignore_errors=True)
                        out["giorni"] += 1
                    else:
                        giorni.append((gdir.name, gdir))
            if self.mb > 0:
                tot = _mb(self.voce_dir)
                for _g, gdir in sorted(giorni):
                    if tot <= self.mb:
                        break
                    tot -= _mb(gdir)
                    shutil.rmtree(gdir, ignore_errors=True)
                    out["tetto"] += 1
                if out["tetto"]:
                    self.log(f"   [CONSERVA] voce oltre {self.mb:.0f} MB: tolti {out['tetto']} "
                             f"giorni dei più vecchi")
        return out

    def _ruota_banco(self, oggi: datetime.date) -> int:
        """I giorni del banco della stanza oltre `turn_log_days` (stanza/banco.ruota), quale che
        sia lo stato dell'eccezione. Quanti file audio tolti; un errore non ferma il resto."""
        try:
            from .stanza.banco import ruota
            n = ruota(self.cfg, oggi)
        except Exception as e:  # noqa: BLE001 — il banco non ferma la rotazione del resto
            self.log(f"   [CONSERVA] rotazione del banco della stanza non riuscita: "
                     f"{type(e).__name__}")
            return 0
        if n:
            self.log(f"   [CONSERVA] banco della stanza: tolti {n} segmenti audio oltre "
                     f"{self.giorni} giorni")
        return n

    # ── richieste ai tutori e preferenze (memoria.db) ──
    def _memoria(self, limite: datetime.date | None = None, persona_id=None,
                 tutto: bool = False) -> int:
        """Righe tolte da TABELLE_MEMORIA, con `secure_delete`: più vecchie di `limite`, di una
        persona, o tutte. Una tabella che non c'è (mai usata) non conta; il file della
        memoria che non si apre non ferma niente."""
        path = getattr(self.cfg, "memory_db", None)
        if not path or not Path(path).exists():
            return 0
        if limite is None and persona_id is None and not tutto:
            return 0
        import sqlite3
        from .persistenza import apri_db
        n = 0
        try:
            db = apri_db(path)
        except (sqlite3.Error, OSError):
            return 0
        try:
            db.execute("PRAGMA secure_delete = ON")
            if tutto or persona_id is not None:
                for tabella, chi in TABELLE_PREFERENZE:
                    sql = f"DELETE FROM {tabella}" + ("" if tutto else f" WHERE {chi} = ?")
                    try:
                        n += db.execute(sql, () if tutto else (str(persona_id),)).rowcount or 0
                    except sqlite3.OperationalError:
                        continue                  # la tabella non c'è
            for tabella, chi, quando in TABELLE_MEMORIA:
                if tutto:
                    sql, arg = f"DELETE FROM {tabella}", ()
                elif persona_id is not None:
                    sql, arg = f"DELETE FROM {tabella} WHERE {chi} = ?", (str(persona_id),)
                else:
                    # ISO: «2026-08-13» e «2026-08-13T10:00:00» del giorno limite restano
                    sql, arg = f"DELETE FROM {tabella} WHERE {quando} < ?", (limite.isoformat(),)
                try:
                    n += db.execute(sql, arg).rowcount or 0
                except sqlite3.OperationalError:
                    continue                      # la tabella non c'è
            db.commit()
        except sqlite3.Error as e:
            self.log(f"   [CONSERVA] richieste ai tutori non ripulite: {type(e).__name__}")
        finally:
            db.close()
        if n and limite is not None and persona_id is None and not tutto:
            self.log(f"   [CONSERVA] richieste ai tutori oltre {self.giorni} giorni: "
                     f"{n} righe tolte")
        return n

    # ── il registro dei turni di prima (una volta) ──
    def ripulisci_registro(self, lock=None) -> dict | None:
        """Le parole dei turni di ospiti e voci incerte scritte prima del 12/10 (il registro dei
        turni le teneva 30 giorni per tutti tranne gli ospiti): tolte una volta, poi il segno
        nella cartella. Decide `testo_turno`: dal 16/10 (decisione 0031) i turni dei minori
        restano con le parole (fino al 16/10 li toglieva anche loro)."""
        if not self.cartella or not self.cartella.exists():
            return None
        segno = self.cartella / SEGNO_RIPULITO
        if segno.exists():
            return None
        out = ripulisci_turni(self.cartella, lambda r: bool(self.testo_turno(r)), lock)
        _scrivi_privato(segno, datetime.datetime.now().isoformat().encode())
        if out["turni"]:
            self.log(f"   [CONSERVA] registro dei turni ripulito: {out['turni']} turni di "
                     f"ospiti o voci incerte senza più le parole")
        return out

    # ── svuotare ──
    def svuota(self, persona_id: str | None = None, nome: str | None = None) -> dict:
        """Tutto (persona_id None) o i dati di una persona: la voce, gli eventi su disco (con
        `secure_delete`), nel registro dei turni le parole (di tutti: i file interi) e, dal 12/10
        sera, l'archivio delle conversazioni (anche le conversazioni in corso salvate) e le
        richieste ai tutori (TABELLE_MEMORIA; fino al 28/10 anche i tentativi degli esercizi);
        dal 29/10 lo Studio (TABELLE_STUDIO), con le verifiche archiviate."""
        # Le righe della stanza di un conoscente (14/10 sera) hanno la chiave «conoscente:<id>»
        stanza_id = (f"conoscente:{persona_id}" if persona_id is not None
                     and self.conoscente(persona_id) is not None else persona_id)
        out = {"voce": 0, "eventi": 0, "turni": 0, "conversazioni": 0,
               "richieste": self._memoria(persona_id=persona_id, tutto=persona_id is None),
               "stanza": self._svuota_stanza(stanza_id),
               "stanza_banco": self._svuota_banco(persona_id),
               "avvisi": self._svuota_avvisi(persona_id),
               # Le impronte per satellite (15/10): imparate dall'uso, si tolgono con i dati
               # conservati; l'impronta della registrazione resta
               "impronte_satellite": self._svuota_impronte(persona_id),
               # Le foto tenute con la Conversazione (28/10, decisione 0034): file e righe
               "foto": self._svuota_foto(persona_id),
               # Lo Studio (29/10, #280): le verifiche, archiviate comprese, e i giorni
               "studio": (self._studio(tutto=True) if persona_id is None
                          else self._studio(persona=str(persona_id)))["verifiche"]}
        arch = self.conversazioni
        lock = getattr(self.turnlog, "_lock", None)
        if persona_id is None:
            self._svuotando = True
            try:
                out["conoscenti"] = self._svuota_conoscenti()
            finally:
                self._svuotando = False
            if self.voce_dir and self.voce_dir.exists():
                out["voce"] = sum(1 for _ in self.voce_dir.rglob("*.wav"))
                shutil.rmtree(self.voce_dir, ignore_errors=True)
            if self.cartella and self.cartella.exists():
                for f in self.cartella.glob("turni-*.jsonl"):
                    with (lock or threading.Lock()):
                        f.unlink(missing_ok=True)
                    out["turni"] += 1
            if arch is not None:
                out["conversazioni"] = arch.svuota()
            out["eventi"] = self._svuota_eventi(None)
            return out
        out["voce"] = self.cancella_voce(persona_id)
        if self.cartella:
            def tieni(r):
                v = r.get("voce") if isinstance(r.get("voce"), dict) else {}
                return not (v.get("id") == persona_id or (nome and v.get("nome") == nome))
            out["turni"] = ripulisci_turni(self.cartella, tieni, lock)["turni"]
        if arch is not None:
            out["conversazioni"] = arch.dimentica(str(persona_id))
        out["eventi"] = self._svuota_eventi(f"persona:{persona_id}")
        return out

    def _studio(self, **kw) -> dict:
        """calliope/studio/dati.cancella sul file della memoria (tenuta e «svuota»); un errore
        non ferma il resto."""
        try:
            from .studio.dati import cancella_file
            # L'audio del ripasso da ascoltare (31/10, #249) scade anche da sé, dall'ultimo ascolto
            kw.setdefault("ascolta_giorni",
                          int(getattr(self.cfg, "studio_ascolta_giorni", 7) or 7))
            out = cancella_file(getattr(self.cfg, "memory_db", None), log=self.log,
                                cartella=getattr(self.cfg, "studio_cartella", None), **kw)
        except Exception as e:  # noqa: BLE001 — lo Studio non ferma la rotazione del resto
            self.log(f"   [CONSERVA] Studio non ripulito: {type(e).__name__}")
            return {"verifiche": 0, "file": 0}
        if (out["verifiche"] or out.get("giorni")) and "scadute_prima" in kw:
            self.log(f"   [CONSERVA] Studio: tolte {out['verifiche']} verifiche e "
                     f"{out.get('giorni', 0)} giorni segnati oltre "
                     f"{getattr(self.cfg, 'studio_tenuta_giorni', 60)} giorni")
        return out

    def _svuota_foto(self, persona_id) -> int:
        """Le foto tenute nel cassetto (decisione 0034) di una persona o di tutti; quelle
        archiviate restano nei documenti. Dal processo di Calliope il suo cassetto, da terminale
        quello del file della memoria."""
        cas, chiudi = getattr(self, "cassetto", None), False
        try:
            if cas is None:
                db = str(getattr(self.cfg, "memory_db", "") or "")
                if not db or not Path(db).exists():
                    return 0
                from .cassetto import load_cassetto
                cas, chiudi = load_cassetto(self.cfg, log=lambda m: None), True
                if cas is None:
                    return 0
            return cas.dimentica_foto(None if persona_id is None else str(persona_id))
        except Exception as e:  # noqa: BLE001 — le foto non fermano lo svuotamento
            self.log(f"   [CONSERVA] foto tenute non tolte: {type(e).__name__}")
            return 0
        finally:
            if chiudi and cas is not None:
                cas.close()

    def _svuota_impronte(self, persona_id) -> int:
        """Le impronte per satellite (15/10, calliope/impronte_satellite.py) di una persona o di
        tutti: dal processo di Calliope il registro delle voci e i conoscenti; da terminale i
        file (speakers.json e i conoscenti, con le copie)."""
        n = 0
        try:
            f = getattr(self.registry, "svuota_impronte_satellite", None)
            if callable(f):
                n += int(f(persona_id) or 0)
            else:
                from .impronte_satellite import svuota_file
                from .speaker_id import SpeakerRegistry
                n += svuota_file(SpeakerRegistry.PATH, persona_id)
            con = self.conoscenti
            if con is not None and hasattr(con, "svuota_impronte_satellite"):
                n += int(con.svuota_impronte_satellite(persona_id) or 0)
            else:
                from .impronte_satellite import svuota_file
                from .stanza.conoscenti import percorso
                n += svuota_file(percorso(self.cfg), persona_id)
        except Exception as e:  # noqa: BLE001 — le impronte non fermano lo svuotamento
            self.log(f"   [CONSERVA] impronte per satellite non tolte: {type(e).__name__}")
        return n

    def _svuota_avvisi(self, persona_id) -> int:
        """Trascrizione e audio degli avvisi di pericolo (14/10 sera, minori.Avvisi): tutti, o
        quelli di una persona (come tutore o come minore). L'avviso resta, senza parole. Dal
        processo di Calliope i suoi avvisi; da terminale il file della memoria e il cassetto."""
        av, chiudi = getattr(self, "avvisi", None), False
        try:
            if av is None:
                db = str(getattr(self.cfg, "memory_db", "") or "")
                if not db or not Path(db).exists():
                    return 0
                from .cassetto import load_cassetto
                from .minori import Avvisi
                av, chiudi = Avvisi(db, log=lambda m: None, cfg=self.cfg), True
                av.cassetto = load_cassetto(self.cfg, log=lambda m: None)
            if persona_id is None:
                return av.dimentica_materiale(tutto=True)
            return (av.dimentica_materiale(tutore=str(persona_id))
                    + av.dimentica_materiale(minore=str(persona_id)))
        except Exception as e:  # noqa: BLE001 — gli avvisi non fermano lo svuotamento
            self.log(f"   [CONSERVA] materiale degli avvisi non svuotato: {type(e).__name__}")
            return 0
        finally:
            if chiudi and av is not None:
                if av.cassetto is not None:
                    av.cassetto.close()
                av.close()

    def _svuota_banco(self, persona_id) -> int:
        """L'audio della stanza per il banco del passo 3 (eccezione del 14/10 sera,
        calliope/stanza/banco.py): tutto (con il segno dell'accensione), o i segmenti con la
        voce della persona. Funziona anche da un altro processo (sono file)."""
        try:
            from .stanza.banco import svuota
            return svuota(self.cfg, persona_id)
        except Exception as e:  # noqa: BLE001 — il banco non ferma lo svuotamento del resto
            self.log(f"   [CONSERVA] audio del banco non svuotato: {type(e).__name__}")
            return 0

    def _svuota_stanza(self, persona_id) -> int:
        """Il testo della stanza su disco (14/10): tutto, o le righe di una persona (con le
        risposte di Calliope a lei). Dal processo di Calliope la sua tenuta; da terminale il
        file (la memoria della stanza di Calliope resta fino al riavvio, al più 24 h)."""
        try:
            if self.stanza is not None:
                return self.stanza.svuota(persona_id)
            from .stanza.tenuta import svuota_file
            return svuota_file(self.cfg, persona_id)
        except Exception as e:  # noqa: BLE001 — la stanza non ferma lo svuotamento del resto
            self.log(f"   [CONSERVA] testo della stanza non svuotato: {type(e).__name__}")
            return 0

    def _svuota_conoscenti(self) -> int:
        """I conoscenti (14/10): impronte e profili, con le loro righe della stanza (già tolte
        con la stanza intera). Dal processo di Calliope i suoi; da terminale il file (Calliope se
        ne accorge alla lettura dopo)."""
        try:
            if self.conoscenti is not None:
                return self.conoscenti.svuota()
            from .stanza.conoscenti import svuota_file
            return svuota_file(self.cfg)
        except Exception as e:  # noqa: BLE001 — i conoscenti non fermano lo svuotamento
            self.log(f"   [CONSERVA] conoscenti non svuotati: {type(e).__name__}")
            return 0

    def _svuota_eventi(self, chiave: str | None) -> int:
        disco = self.eventi
        if disco is None:
            return 0
        return disco.svuota(chiave)

    # ── quanto c'è (solo conteggi) ──
    def stato(self) -> dict:
        out = {"giorni": self.giorni, "voce_mb_tetto": self.mb,
               "voce_accesa": bool(getattr(self.cfg, "conserva_voce", True)),
               "voce_file": 0, "voce_mb": 0.0, "voce_persone": 0, "voce_giorni": 0,
               "turni_file": 0, "conversazioni": 0, "conversazioni_turni": 0}
        if self.voce_dir and self.voce_dir.exists():
            cartelle = self._cartelle_voce()
            persone = [p for p, valut in cartelle if not valut]
            out["voce_persone"] = len(persone)
            out["voce_file"] = sum(1 for _ in self.voce_dir.rglob("*.wav"))
            out["voce_mb"] = round(_mb(self.voce_dir), 2)
            out["voce_giorni"] = len({g.name for p, _v in cartelle for g in p.iterdir()
                                      if g.is_dir()})
        # La valutazione (18/10, decisione 0032): fino a quando, e quanto audio in più
        f = valutazione_fino(self.cfg)
        if f is not None or (self.voce_dir and (self.voce_dir / CARTELLA_VALUTAZIONE).exists()):
            vd = self.voce_dir / CARTELLA_VALUTAZIONE if self.voce_dir else None
            out["valutazione"] = {
                "fino": f.isoformat() if f else None, "attiva": valutazione_attiva(self.cfg),
                "voce_file": sum(1 for _ in vd.rglob("*.wav")) if vd and vd.exists() else 0,
                "voce_mb": round(_mb(vd), 2) if vd and vd.exists() else 0.0,
                "testo": testo_valutazione(self.cfg)}
        if self.cartella and self.cartella.exists():
            out["turni_file"] = len(list(self.cartella.glob("turni-*.jsonl")))
        out.update(self.conta_conversazioni())
        out["stanza"] = self.conta_stanza()
        return out

    def conta_stanza(self, persona_id=None) -> dict | None:
        """Il testo della stanza su disco (14/10): dalla tenuta aperta o dal file in sola
        lettura; None con la tenuta spenta e senza file."""
        try:
            if self.stanza is not None:
                d = self.stanza.conteggi(persona_id)
                if persona_id is None:
                    d["giorni_tenuta"], d["accesa"] = self.stanza.giorni, True
                return d
            from .stanza.tenuta import conta_file
            return conta_file(self.cfg, persona_id)
        except Exception:  # noqa: BLE001 — i conteggi non fermano niente
            return None

    def conta_conversazioni(self, persona_id=None) -> dict:
        """Quante conversazioni (e turni) ci sono nell'archivio su disco, di tutti o di una
        persona: dall'archivio aperto, o dal file in sola lettura (`calliope stato`)."""
        out = {"conversazioni": 0, "conversazioni_turni": 0}
        try:
            arch = self.conversazioni
            c = (arch.conteggi(persona_id) if arch is not None
                 else conta_archivio(self.cfg, persona_id))
            out["conversazioni"], out["conversazioni_turni"] = c["conversazioni"], c["turni"]
        except Exception:  # noqa: BLE001 — i conteggi non fermano niente
            pass
        return out


def testo_stato(d: dict | None) -> str | None:
    """Una riga per `calliope stato`."""
    if not d:
        return None
    voce = (f"voce {d['voce_file']} frasi di {d['voce_persone']} persone, {d['voce_mb']:.1f} MB "
            f"(tetto {d['voce_mb_tetto']:.0f})" if d.get("voce_accesa") else "voce spenta")
    conv = (f"; {d['conversazioni']} conversazioni archiviate ({d['conversazioni_turni']} "
            f"turni)" if "conversazioni" in d else "")
    st = d.get("stanza")
    stanza = (f"; stanza su disco {st['righe']} righe ({st['mb']:.1f} MB, "
              f"{st.get('giorni_tenuta', 60)} giorni, famiglia e minori)" if st else "")
    riga = (f"Conservazione ({d['giorni']} giorni, persone di casa): {d['turni_file']} giorni "
            f"di turni; {voce}{conv}{stanza}")
    val = d.get("valutazione")
    if val:
        # La valutazione (18/10, decisione 0032): la riga prima, con l'audio in più
        riga = ((val.get("testo") or "Valutazione: file rimasti")
                + f"; voce della valutazione {val.get('voce_file', 0)} frasi, "
                  f"{float(val.get('voce_mb') or 0):.1f} MB\n" + riga)
    return riga


def conta_archivio(cfg, persona_id=None) -> dict:
    """Le conversazioni e i turni nel file dell'archivio, in sola lettura (senza aprire
    l'archivio né il suo thread). File mancante: zero."""
    import sqlite3
    from .conversazioni import percorso_db
    p = Path(percorso_db(cfg))
    if not p.exists():
        return {"conversazioni": 0, "turni": 0}
    db = sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True, timeout=2.0)
    try:
        dove, args = ("WHERE persona = ?", (str(persona_id),)) if persona_id else ("", ())
        n = db.execute(f"SELECT COUNT(*) FROM conversazioni {dove}", args).fetchone()[0]
        t = db.execute(f"SELECT COUNT(*) FROM turni WHERE conv IN (SELECT id FROM "
                       f"conversazioni {dove})", args).fetchone()[0]
        return {"conversazioni": int(n), "turni": int(t)}
    except sqlite3.Error:
        return {"conversazioni": 0, "turni": 0}
    finally:
        db.close()


# ─────────────────────────── da terminale ───────────────────────────
def _profili(cfg):
    """I profili senza caricare il modello dell'impronta (solo speakers.json)."""
    from .speaker_id import UserProfile
    from .persistenza import leggi_json

    class _Reg:
        def __init__(self):
            self.users = {}
            try:
                dati, _da = leggi_json(Path("speakers.json"))
            except Exception:  # noqa: BLE001 — rovinato: nessun profilo (si legge e basta)
                dati = []
            for d in dati or ():
                try:
                    u = UserProfile.from_dict(d, d.get("model"))
                    self.users[u.name] = u
                except Exception:  # noqa: BLE001
                    continue

        def get(self, nome):
            return self.users.get(nome)

        def by_id(self, pid):
            return next((u for u in self.users.values() if u.id == pid), None)

    return _Reg()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if {"-h", "--help"} & set(argv):
        print(__doc__.strip())
        return 0
    from .config import load_config
    cfg = load_config()
    if "--converti-audio" in argv:
        # Una tantum (14/10 sera): i WAV μ-law di prima nel G.711 vero; si può rilanciare
        r = converti_audio(cfg)
        print(testo_conversione(r))
        return 1 if r["errori"] else 0
    reg = _profili(cfg)
    c = Conservazione(cfg, reg)
    try:
        from .eventi.registro import Disco
        from .conversazioni import percorso_db
        p = Path(percorso_db(cfg))
        if p.exists():
            c.eventi = Disco.file(p, log=lambda m: None)
    except Exception:  # noqa: BLE001 — senza la tabella degli eventi si svuota il resto
        c.eventi = None
    if "--svuota" in argv:
        # L'archivio delle conversazioni (12/10 sera): si apre solo per svuotarlo, senza il suo
        # thread né l'archivio della sessione (quello vive nel processo di Calliope)
        try:
            from .conversazioni import ArchivioConversazioni, percorso_db
            p = Path(percorso_db(cfg))
            if p.exists():
                c.conversazioni = ArchivioConversazioni(p, giorni=c.giorni, log=lambda m: None,
                                                        avvia=False, sessione=False)
        except Exception:  # noqa: BLE001 — senza l'archivio si svuota il resto
            c.conversazioni = None

    def nome_arg(opz):
        i = argv.index(opz)
        if i + 1 >= len(argv):
            raise SystemExit(f"{opz} vuole un nome")
        return argv[i + 1]

    if "--svuota" in argv:
        if "--persona" in argv:
            nome = nome_arg("--persona")
            prof = reg.get(nome)
            if prof is None:
                # Un conoscente (14/10 sera, decisione 0030 aggiornata): i suoi dati come quelli
                # di un adulto; il profilo resta (si dimentica con «dimentica …» a voce)
                kk = c.trova_conoscenti(nome)
                if len(kk) > 1:
                    print("Più conoscenti con quel nome: "
                          + "; ".join(k.descrizione() for k in kk)
                          + ". Aggiungi il cognome o la nota.")
                    return 1
                prof = kk[0] if kk else None
            if prof is None:
                print("Nessuna persona con quel nome.")
                return 1
            r = c.svuota(prof.id, getattr(prof, "name", None) if categoria(prof) != "conoscente"
                         else None)
            print(f"Dati conservati di {nome} cancellati: {r['voce']} registrazioni, "
                  f"{r['eventi']} eventi, parole tolte da {r['turni']} turni, "
                  f"{r['conversazioni']} conversazioni archiviate, "
                  f"{r['richieste']} tra richieste ai tutori e preferenze, "
                  f"{r['stanza']} righe della stanza, {r['avvisi']} trascrizioni e audio di "
                  f"avvisi" + (f", {r['stanza_banco']} segmenti audio del banco della stanza"
                               if r.get("stanza_banco") else "")
                  + (f", {r['impronte_satellite']} impronte per satellite"
                     if r.get("impronte_satellite") else "")
                  + (f", {r['studio']} verifiche dello Studio" if r.get("studio") else "")
                  + ".")
        else:
            r = c.svuota()
            print(f"Dati conservati cancellati: {r['voce']} registrazioni, {r['eventi']} eventi, "
                  f"{r['turni']} giorni del registro dei turni, {r['conversazioni']} "
                  f"conversazioni archiviate, {r['richieste']} tra richieste ai "
                  f"tutori e preferenze, {r['stanza']} righe della stanza, {r['avvisi']} "
                  f"trascrizioni e audio di avvisi, {r.get('conoscenti', 0)} conoscenti"
                  + (f", {r['stanza_banco']} segmenti audio del banco della stanza"
                     if r.get("stanza_banco") else "")
                  + (f", {r['impronte_satellite']} impronte per satellite"
                     if r.get("impronte_satellite") else "")
                  + (f", {r['studio']} verifiche dello Studio" if r.get("studio") else "")
                  + ".")
        if c.conversazioni is not None:
            c.conversazioni.close()
        return 0
    d = c.stato()
    if "--json" in argv:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print(testo_stato(d))
        for u in reg.users.values():
            cat = categoria(u)
            stato_voce = "sì" if consenso_voce(u, reg) else (
                "no" if u.voce_conservata is False else "non chiesto")
            if cat == "minore":
                # Il consenso alla voce di un minore è dei tutori (16/10, decisione 0031)
                stato_voce += " (lo decidono i tutori)"
            conv = c.conta_conversazioni(u.id)["conversazioni"]
            st = c.conta_stanza(u.id)
            print(f"    {u.name}: {cat}, voce {stato_voce}, registrazioni "
                  f"{c.registrazioni(u.id)}, conversazioni archiviate {conv}"
                  + (f", righe della stanza {st['righe']}" if st else ""))
        # I conoscenti (14/10 sera): conservati come gli adulti, la voce no (niente consenso)
        for k in c._conoscenti_tutti():
            conv = c.conta_conversazioni(k.id)["conversazioni"]
            print(f"    {k.descrizione()}: conoscente, voce no, conversazioni archiviate {conv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
