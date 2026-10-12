"""
La conservazione dei dati per misurare e migliorare Calliope (12/10/2026, decisione 0028, T1).

Turni, eventi e voce dei **soli adulti riconosciuti** restano per `turn_log_days` (60) giorni,
in privato nella cartella dei dati (mai nel repository: `registro/` è in .gitignore, sulla DGX
sta in ~/calliope/registro). Servono al banco della scelta dei tool, ai set di regressione, al
dizionario delle correzioni e alla taratura delle soglie. Di **minori e ospiti mai**: né testo né
audio oltre a ciò che serve al turno.

**Un solo posto decide** chi è conservabile: `decidi(profilo, cosa, modo, dubbi)`, puro.
- `testo` (turni ed eventi con le parole): un adulto riconosciuto, dalla voce sopra soglia,
  da una frase breve o per continuità, o da uno schermo personale. La zona grigia
  (`conversazione`), il proprietario di un satellite incerto con un minore (`proprietario`) e
  ogni dubbio con un minore (`incerta`, `minore_vicino`) non si salvano: **nel dubbio no**.
- `voce` (l'audio della frase): come il testo, ma solo con la voce riconosciuta sopra soglia
  in quella frase (`modo: voce`), senza altre voci vicino al satellite (`compagnia`: l'audio
  potrebbe avere dentro un'altra persona) e con il **consenso** della persona.
- `eventi` (il registro degli eventi su disco): i registri delle persone adulte. Quelli dei
  minori e degli ospiti restano solo in memoria (`registro_su_disco`), e quelli già su disco
  li cancella la rotazione.
- `conversazioni` (l'archivio delle conversazioni, calliope/conversazioni.py, dal 12/10 sera):
  come gli eventi, le conversazioni delle persone adulte (`conversazioni_su_disco`); quelle di
  minori e ospiti stanno nell'archivio della sessione, in memoria. Dentro la conversazione di un
  adulto, i turni le cui parole non restano (`testo_turno`: zona grigia, dubbio con un minore)
  non vanno su disco. Stessi `turn_log_days` giorni.

**Il consenso** è un dato della persona, nel suo profilo (speakers.json, `voce_conservata`):
None = mai detto, True = «sì» detto una volta a Calliope (tool `dati_conservati`), False =
revocato (anche a voce; le registrazioni che c'erano si cancellano). Per chi amministra vale la
sua scelta, e senza una scelta è sì.

**La voce** si salva in G.711 μ-law (8 bit, 16 kHz, WAV con il formato 7): metà della PCM a 16
bit, letta da ffmpeg e sox, e codificata con numpy (già una dipendenza di base: principio 4,
niente librerie native nuove). Una frase di 3 s pesa ~48 KB; con le giornate vere della DGX
(dall'08 al 09/10: 1 300 s di parlato al giorno, ~75 % riconosciuto dalla voce) sono ~15 MB al
giorno, ~0,9 GB in 60 giorni. Tetto `conserva_voce_mb`: oltre, si tolgono i giorni più vecchi.
Cartella: `<turn_log_dir>/voce/<id della persona>/<AAAA-MM-GG>/<ora>.wav`, file 600 e
cartelle 700 su Linux.

**Privacy**: niente esce mai da qui (nessun invio, nessun tool che legga la cartella); nei log
solo conteggi, mai testo né nomi. La conservazione non usa la GPU: nel profilo ridotto da 8 GB
c'è uguale.

    python -m calliope.conserva                  quanto è conservato (solo conteggi)
    python -m calliope.conserva --svuota         tutto: voce, eventi, registro dei turni e
                                                 archivio delle conversazioni
    python -m calliope.conserva --svuota --persona NOME
                                                 i dati di una persona

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
COSE = ("testo", "voce", "eventi", "conversazioni")
# Come è stata decisa l'identità della frase (SpeakerContext.identified_by e i modi del ciclo):
# con questi il testo resta. Fuori: la zona grigia («conversazione»), il proprietario incerto
# con un minore («proprietario»), nessun modo
MODI_TESTO = frozenset({"voce", "breve", "continuita", "schermo"})
# I segni di un dubbio con un minore nel campo `voce` del turno (ciclo._riconosci_voce)
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


def categoria(prof) -> str:
    """«ospite» (nessun profilo), «minore», «amministra» o «adulto»."""
    if prof is None:
        return "ospite"
    from . import minori
    try:
        if minori.e_minore(prof):
            return "minore"
    except Exception:  # noqa: BLE001 — una data rovinata: nel dubbio minore
        return "minore"
    return "amministra" if getattr(prof, "admin", False) else "adulto"


def consenso_voce(prof) -> bool:
    """La persona ha detto sì a tenere la sua voce? Per chi amministra, senza una scelta, sì."""
    v = getattr(prof, "voce_conservata", None)
    if v is None:
        return bool(getattr(prof, "admin", False))
    return bool(v)


def decidi(prof, cosa: str, modo: str | None = None, dubbi=(), cfg=None) -> Decisione:
    """Il solo posto che decide se qualcosa di questa persona si conserva. Puro.

    `cosa`: «testo», «voce», «eventi» o «conversazioni»; `modo`: come è stata decisa l'identità della frase;
    `dubbi`: i segni del turno («incerta», «minore_vicino», «compagnia»…)."""
    if cosa not in COSE:
        raise ValueError(f"cosa sconosciuta: {cosa!r}")
    cat = categoria(prof)
    if cat in ("ospite", "minore"):
        return Decisione(False, cat)
    if cosa in ("eventi", "conversazioni"):
        return Decisione(True, cat)
    dubbi = set(dubbi or ())
    if dubbi & set(DUBBI_MINORE):
        return Decisione(False, "dubbio_minore")
    if cosa == "testo":
        return (Decisione(True, cat) if modo in MODI_TESTO
                else Decisione(False, "voce_incerta"))
    if cfg is not None and not getattr(cfg, "conserva_voce", True):
        return Decisione(False, "spenta")
    if modo != "voce":
        return Decisione(False, "voce_incerta")
    if "compagnia" in dubbi:
        return Decisione(False, "compagnia")
    if not consenso_voce(prof):
        return Decisione(False, "senza_consenso")
    return Decisione(True, cat)


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
    return rec


# ─────────────────────────── la voce in μ-law ───────────────────────────
_MU = 255.0


def mulaw(audio) -> bytes:
    """float32 in [-1, 1] → byte G.711 μ-law (formato dei file WAV 7). Vettoriale."""
    import numpy as np
    x = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    y = np.sign(x) * np.log1p(_MU * np.abs(x)) / np.log1p(_MU)
    # Il byte di G.711 è il complemento del valore quantizzato (segno nel bit alto)
    q = np.round((y + 1.0) / 2.0 * 255.0).astype(np.int16)
    q = np.clip(q, 0, 255).astype(np.uint8)
    return (~q).astype(np.uint8).tobytes()


def da_mulaw(dati: bytes):
    """Byte μ-law → float32 in [-1, 1]."""
    import numpy as np
    q = (~np.frombuffer(dati, dtype=np.uint8)).astype(np.float32)
    y = q / 255.0 * 2.0 - 1.0
    return (np.sign(y) * (np.power(1.0 + _MU, np.abs(y)) - 1.0) / _MU).astype(np.float32)


def wav_mulaw(audio, sr: int) -> bytes:
    """Un file WAV μ-law intero (RIFF, fmt con il formato 7, fact, data)."""
    dati = mulaw(audio)
    n = len(dati)
    fmt = struct.pack("<HHIIHHH", 7, 1, int(sr), int(sr), 1, 8, 0)
    pad = b"\x00" if n % 2 else b""
    corpo = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
             + b"fact" + struct.pack("<II", 4, n) + b"data" + struct.pack("<I", n) + dati + pad)
    return b"RIFF" + struct.pack("<I", len(corpo)) + corpo


def leggi_wav(path) -> tuple:
    """(audio float32, frequenza) da un WAV μ-law o PCM a 16 bit (per il banco e le prove)."""
    import numpy as np
    b = Path(path).read_bytes()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError("non è un WAV")
    i, fmt, sr, dati = 12, None, 16000, None
    while i + 8 <= len(b):
        nome, lung = b[i:i + 4], struct.unpack("<I", b[i + 4:i + 8])[0]
        pezzo = b[i + 8:i + 8 + lung]
        if nome == b"fmt ":
            fmt, _ch, sr = struct.unpack("<HHI", pezzo[:8])
        elif nome == b"data":
            dati = pezzo
        i += 8 + lung + (lung % 2)
    if dati is None:
        raise ValueError("WAV senza dati")
    if fmt == 7:
        return da_mulaw(dati), sr
    if fmt == 1:
        return np.frombuffer(dati, dtype="<i2").astype(np.float32) / 32768.0, sr
    raise ValueError(f"formato WAV {fmt} non letto")


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
                                        for ev in rec.get("tool") or ())


# Le tabelle di memoria.db con il testo dei ragazzi che scadono con la stessa tenuta (12/10
# sera, decisione di Dario): (tabella, colonna della persona, colonna della data ISO). I
# tentativi degli esercizi (domanda, risposta attesa e data, al più 60 caratteri: il dettaglio
# dei tutori), le richieste ai tutori (con `oggetto`, ciò che il ragazzo ha chiesto) e le
# segnalazioni degli esercizi (risposta data e nota del ragazzo; anche queste dal 12/10 sera)
TABELLE_MEMORIA = (("esercizi_tentativi", "persona", "giorno"),
                   ("richieste_tutori", "minore", "creata"),
                   ("esercizi_segnalazioni", "persona", "quando"))


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
        self._lock = threading.Lock()
        self._ruotata_il = None
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
        if nome:
            get = getattr(reg, "get", None)
            return get(nome) if get else None
        return None

    # ── le decisioni (sempre da `decidi`) ──
    def testo_turno(self, rec: dict) -> Decisione:
        """Le parole di questo turno restano nel registro dei turni e negli eventi su disco?"""
        if not isinstance(rec, dict):
            return Decisione(False, "ospite")
        if rec.get("livello") == "ospite":
            return Decisione(False, "ospite")
        v = rec.get("voce") if isinstance(rec.get("voce"), dict) else {}
        if not v.get("nome"):
            return Decisione(False, "ospite")
        if isinstance(rec.get("ascolto"), dict) and rec["ascolto"].get("fascia"):
            return Decisione(False, "minore")
        prof = self.profilo(nome=v.get("nome"), persona_id=v.get("id"))
        return decidi(prof, "testo", v.get("modo"), dubbi_del_turno(rec), self.cfg)

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
        return decidi(prof, "voce", v.get("modo"), dubbi_del_turno(rec), self.cfg)

    def registro_su_disco(self, chiave: str) -> bool:
        """Il registro degli eventi di questa chiave va su disco? Le persone adulte sì; minori,
        ospiti e voci incerte (`ospite:<corsia>`) restano in memoria."""
        chiave = str(chiave or "")
        if chiave == "casa":
            return True
        if not chiave.startswith("persona:"):
            return False
        return bool(decidi(self.profilo(persona_id=chiave.split(":", 1)[1]), "eventi"))

    def conversazioni_su_disco(self, persona_id) -> bool | None:
        """Le conversazioni di questa persona vanno nell'archivio su disco? Gli adulti sì;
        minori, ospiti e profili tolti no (restano nell'archivio della sessione). None quando
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
            return None
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

    # ── consenso ──
    def imposta_consenso(self, prof, valore: bool) -> int:
        """Salva la scelta nel profilo; con un no cancella anche la voce che c'era. Restituisce
        quante registrazioni ha cancellato."""
        prof.voce_conservata = bool(valore)
        prof.voce_conservata_il = datetime.date.today().isoformat()
        save = getattr(self.registry, "save", None)
        if callable(save):
            save()
        if valore:
            return 0
        return self.cancella_voce(getattr(prof, "id", None))

    def cancella_voce(self, persona_id) -> int:
        if not persona_id or not self.voce_dir:
            return 0
        p = self.voce_dir / str(persona_id)
        n = sum(1 for _ in p.rglob("*.wav")) if p.exists() else 0
        shutil.rmtree(p, ignore_errors=True)
        return n

    def registrazioni(self, persona_id) -> int:
        if not persona_id or not self.voce_dir:
            return 0
        p = self.voce_dir / str(persona_id)
        return sum(1 for _ in p.rglob("*.wav")) if p.exists() else 0

    # ── rotazione ──
    def ruota_se_serve(self):
        """Una volta al giorno, in secondo piano: la voce non aspetta il giro delle cartelle."""
        oggi = datetime.date.today()
        if self._ruotata_il != oggi:
            self._ruotata_il = oggi

            def giro():
                try:
                    self.ruota(oggi)
                except Exception as e:  # noqa: BLE001 — la rotazione non ferma niente
                    self.log(f"   [CONSERVA] rotazione non riuscita: {type(e).__name__}")
            threading.Thread(target=giro, daemon=True, name="conserva-rotazione").start()

    def ruota(self, oggi: datetime.date | None = None) -> dict:
        """Esercizi e richieste ai tutori oltre `turn_log_days` (12/10 sera). La voce: via i
        giorni oltre `turn_log_days`, le persone senza più il diritto (consenso
        revocato, profilo tolto, diventata minore… nel dubbio via) e, oltre il tetto di spazio, i
        giorni più vecchi. Il registro dei turni ha la sua (TurnLog._prune), gli eventi pure
        (Disco.ruota)."""
        oggi = oggi or datetime.date.today()
        self._ruotata_il = oggi
        out = {"giorni": 0, "persone": 0, "tetto": 0}
        limite = oggi - datetime.timedelta(days=self.giorni)
        # Esercizi e richieste ai tutori (12/10 sera): la stessa tenuta, anche quelli di prima
        # (alla prima rotazione, all'avvio: niente migrazioni)
        out["memoria"] = self._memoria(limite=limite)
        if not self.voce_dir or not self.voce_dir.exists():
            return out
        with self._lock:
            giorni: list[tuple[str, Path]] = []
            for pdir in [x for x in self.voce_dir.iterdir() if x.is_dir()]:
                prof = self.profilo(persona_id=pdir.name)
                if prof is None or categoria(prof) == "minore" or not consenso_voce(prof) \
                        or not getattr(self.cfg, "conserva_voce", True):
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

    # ── esercizi e richieste ai tutori (memoria.db) ──
    def _memoria(self, limite: datetime.date | None = None, persona_id=None,
                 tutto: bool = False) -> int:
        """Righe tolte da TABELLE_MEMORIA, con `secure_delete`: più vecchie di `limite`, di una
        persona, o tutte. Una tabella che non c'è (esercizi mai usati) non conta; il file della
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
            self.log(f"   [CONSERVA] esercizi e richieste non ripuliti: {type(e).__name__}")
        finally:
            db.close()
        if n and limite is not None and persona_id is None and not tutto:
            self.log(f"   [CONSERVA] esercizi e richieste ai tutori oltre {self.giorni} giorni: "
                     f"{n} righe tolte")
        return n

    # ── il registro dei turni di prima (una volta) ──
    def ripulisci_registro(self, lock=None) -> dict | None:
        """Le parole dei turni di minori, ospiti e voci incerte scritte prima del 12/10 (il
        registro dei turni le teneva 30 giorni per tutti tranne gli ospiti): tolte una volta,
        poi il segno nella cartella."""
        if not self.cartella or not self.cartella.exists():
            return None
        segno = self.cartella / SEGNO_RIPULITO
        if segno.exists():
            return None
        out = ripulisci_turni(self.cartella, lambda r: bool(self.testo_turno(r)), lock)
        _scrivi_privato(segno, datetime.datetime.now().isoformat().encode())
        if out["turni"]:
            self.log(f"   [CONSERVA] registro dei turni ripulito: {out['turni']} turni di minori, "
                     f"ospiti o voci incerte senza più le parole")
        return out

    # ── svuotare ──
    def svuota(self, persona_id: str | None = None, nome: str | None = None) -> dict:
        """Tutto (persona_id None) o i dati di una persona: la voce, gli eventi su disco (con
        `secure_delete`), nel registro dei turni le parole (di tutti: i file interi) e, dal 12/10
        sera, l'archivio delle conversazioni (anche le conversazioni in corso salvate) e i
        tentativi degli esercizi e le richieste ai tutori (TABELLE_MEMORIA)."""
        out = {"voce": 0, "eventi": 0, "turni": 0, "conversazioni": 0,
               "esercizi_richieste": self._memoria(persona_id=persona_id,
                                                   tutto=persona_id is None)}
        arch = self.conversazioni
        lock = getattr(self.turnlog, "_lock", None)
        if persona_id is None:
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
            persone = [x for x in self.voce_dir.iterdir() if x.is_dir()]
            out["voce_persone"] = len(persone)
            out["voce_file"] = sum(1 for _ in self.voce_dir.rglob("*.wav"))
            out["voce_mb"] = round(_mb(self.voce_dir), 2)
            out["voce_giorni"] = len({g.name for p in persone for g in p.iterdir()
                                      if g.is_dir()})
        if self.cartella and self.cartella.exists():
            out["turni_file"] = len(list(self.cartella.glob("turni-*.jsonl")))
        out.update(self.conta_conversazioni())
        return out

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
    return (f"Conservazione ({d['giorni']} giorni, soli adulti): {d['turni_file']} giorni di "
            f"turni; {voce}{conv}")


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
                print("Nessuna persona con quel nome.")
                return 1
            r = c.svuota(prof.id, nome)
            print(f"Dati conservati di {nome} cancellati: {r['voce']} registrazioni, "
                  f"{r['eventi']} eventi, parole tolte da {r['turni']} turni, "
                  f"{r['conversazioni']} conversazioni archiviate, "
                  f"{r['esercizi_richieste']} tra esercizi e richieste ai tutori.")
        else:
            r = c.svuota()
            print(f"Dati conservati cancellati: {r['voce']} registrazioni, {r['eventi']} eventi, "
                  f"{r['turni']} giorni del registro dei turni, {r['conversazioni']} "
                  f"conversazioni archiviate, {r['esercizi_richieste']} tra esercizi e "
                  f"richieste ai tutori.")
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
            if cat == "minore":
                stato_voce = "mai (minore)"
            else:
                stato_voce = "sì" if consenso_voce(u) else (
                    "no" if u.voce_conservata is False else "non chiesto")
            conv = c.conta_conversazioni(u.id)["conversazioni"]
            print(f"    {u.name}: {cat}, voce {stato_voce}, registrazioni "
                  f"{c.registrazioni(u.id)}, conversazioni archiviate {conv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
