"""
L'audio del podcast: quando parte, il controllo con Whisper, cosa si fa se non torna (04/11/2026, issue #387, decisione
0035 punto 58).

**Quando parte** (`Preparatore.motivo`): MOSS occupa 24,7 GB di GPU e non convive con vLLM acceso (la pausa non libera
memoria), quindi vLLM si ferma. Solo se, tutti insieme: siamo nella fascia, la voce è ferma da `studio_podcast_quiete_s`
(`arbitro_memoria.quiete`, che qui deve avere i suoi segnali: altrimenti non si parte), nessun lavoro dell'agente, il
lettore non ha niente da fare, vLLM acceso, libero e non in pausa, memoria sopra la soglia. **La fascia** (di serie
le ore piccole) non serve alla sicurezza, la fanno i controlli qui sopra: serve perché ogni sessione interrotta costa
4 minuti di vLLM che riparte a chi poi chiede un agente, e il banco del 04/11 ha spostato in swap anche la voce: il
primo turno dopo può essere più lento. Di notte nessuno ne paga il prezzo, e la verifica è di domani o dopo.

**Durante** (`_cede`): prima di ogni pezzo e ogni secondo di attesa. Una voce, un lavoro, la prova aperta, la
firma cambiata, la memoria sotto il pavimento, il tetto di tempo: MOSS si toglie subito e vLLM riparte. La voce e gli
agenti vengono prima. I pezzi finiti stanno su disco (`<firma>-stato.json`), e la sessione dopo riparte da lì.

**Sempre** (`try`/`finally` in `sessione`, `Ripresa.riparti`): vLLM riparte con ogni uscita, col confronto delle
impostazioni e `is_paused` falso. Una sessione caduta la riprende `Ripresa.all_avvio`.

**Il controllo** (`confronta`): ogni pezzo si ritrascrive con Whisper e si confronta col copione, numeri compresi. Il
banco ha visto MOSS saltare frasi («Attorno al Sole girano otto pianeti») e cambiarle («molto meno calda» →
«molto meravigliosa»). Ciò che non torna si rigenera con un altro seme, al più `RIGENERA_MAX` volte; poi quel pezzo lo
dice Calliope con la sua voce, dicendolo. Se succede a più di `UNA_VOCE_MAX` dei pezzi il podcast non c'è, e resta il
riassunto. Whisper non è la verità: sbaglia lui (lo misura il banco, `prove/manuali/banco_podcast.py`, sui
numeri in lettere con Piper), e le soglie vengono da lì. Il testo trascritto non esce da `confronta`: nei
conti e nel registro solo numeri.

**In testa a ogni parte** la frase del riassunto, in voce di Calliope (Piper), portata alla frequenza di MOSS.
"""

from __future__ import annotations

import difflib
import io
import json
import os
import re
import threading
import time
import unicodedata
import wave
from pathlib import Path

from . import ascolta as S
from . import podcast as P
from .podcast_motore import Ceduto, Guasto, MotoreMoss, TESTO_RIFERIMENTO, memoria_disponibile_mb

# ─────────────────────────── soglie (dal banco: `docs/aree/studio.md`, 04/11) ───────────────────────
RIGENERA_MAX = 2              # i tentativi in più su un pezzo che non torna
SOGLIA_FRASE = 0.70           # delle parole piene di una battuta, ritrovate
SOGLIA_INVENTATO = 0.30       # delle parole sentite, in più rispetto al copione
UNA_VOCE_MAX = 0.5            # dei pezzi: oltre, niente podcast
PAVIMENTO_MB = 4000           # durante la sessione, sotto si ferma tutto (la guardia del banco)
ATTESA_MEMORIA_S = 60.0       # dopo il fermo di vLLM la memoria torna in qualche secondo
ANCORA_OGNI_S = 5.0
PAUSA_DOPO_GUASTO_S = 3600.0
PAUSA_FRA_SESSIONI_S = 1800.0
GIRO_S = 60.0
INTRO_SILENZIO_S = 0.6
FRA_BATTUTE_S = 0.35
WHISPER_RATE = 16000


# ─────────────────────────── il confronto col copione ───────────────────────────
_VUOTE = frozenset("""il lo la i gli le l un una uno del della dello dei degli delle al alla allo ai agli alle dal dalla
dallo dai dagli dalle nel nella nello nei negli nelle sul sulla sullo sui sugli sulle col con per tra fra su di da in a e ed
o ma che si ne ci d c""".split())
# Le parole che cambiano il senso anche da sole: «molto meno calda» → «molto meravigliosa» (banco del 04/11) in una
# frase lunga non si vedrebbe dalla parte di parole ritrovate
_NEGAZIONI = frozenset(("non", "mai", "nessun", "nessuno", "nessuna", "senza", "meno", "piu"))


def _parole(testo: str) -> list[str]:
    """Le parole di un testo con i numeri in cifre, in tutti e due i versi: Whisper scrive «1.492», il copione
    «millequattrocentonovantadue»."""
    from . import riassunto_controllo as C
    # I separatori delle migliaia che Whisper mette: «5.800», «100.000»
    t = re.sub(r"(?<!\d)(\d{1,3})((?:\.\d{3})+)(?!\d)", lambda m: m.group(1) + m.group(2).replace(".", ""),
               str(testo or ""))
    t = C._normale(t.replace("%", " per cento "))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    # La virgola dei decimali: «99,8» di Whisper e «99.8» di `_in_cifre`
    return [x.replace(",", ".") for x in re.findall(r"\d+(?:[.,]\d+)?|[a-z]+", t)]


def _simile(a: str, b: str) -> bool:
    """Whisper storpia i nomi («Kuiper», «cromosfera»): la stessa radice, o una lettera su cinque. Mai sui numeri."""
    if a == b:
        return True
    if a[:1].isdigit() or b[:1].isdigit() or a in _NEGAZIONI or b in _NEGAZIONI:
        return False
    if len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]:
        return True
    return len(a) >= 5 and difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.8


def confronta(battute: list[dict], trascritto: str) -> dict:
    """{ok, frasi, sbagliate, numeri, numeri_persi, inventate, parole}: il copione di un pezzo contro ciò che si
    sente. Una battuta con la fonte è a posto se si ritrovano abbastanza parole piene, tutti i numeri e la
    negazione; i cenni e i titoli non contano (non affermano niente, e MOSS può mangiarne uno). Solo numeri: il
    testo non esce di qui."""
    att: list[str] = []
    dove: list[int] = []
    for i, b in enumerate(battute):
        w = _parole(b.get("detto") or b.get("testo") or "")
        att += w
        dove += [i] * len(w)
    sent = _parole(trascritto)
    trovate = [False] * len(att)
    usate = [False] * len(sent)
    sm = difflib.SequenceMatcher(None, att, sent, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                trovate[i1 + k] = usate[j1 + k] = True
        elif op == "replace":
            # Le storpiature di Whisper: la parola simile nello stesso tratto
            for k in range(i1, i2):
                for h in range(j1, j2):
                    if not usate[h] and _simile(att[k], sent[h]):
                        trovate[k] = usate[h] = True
                        break
    frasi = []
    numeri = numeri_persi = 0
    for i, b in enumerate(battute):
        if b.get("tipo") != "frase":
            continue
        idx = [k for k, d in enumerate(dove) if d == i]
        piene = [k for k in idx if att[k] not in _VUOTE or att[k] in _NEGAZIONI]
        nums = [k for k in idx if att[k][:1].isdigit()]
        negs = [k for k in idx if att[k] in _NEGAZIONI]
        copre = (sum(trovate[k] for k in piene) / len(piene)) if piene else 1.0
        persi = sum(not trovate[k] for k in nums)
        numeri += len(nums)
        numeri_persi += persi
        motivi = []
        if copre < SOGLIA_FRASE:
            motivi.append("persa" if copre < 0.4 else "cambiata")
        if persi:
            motivi.append("numero")
        if any(not trovate[k] for k in negs):
            motivi.append("negazione")
        frasi.append({"copre": round(copre, 3), "motivi": motivi})
    inventate = sum(not u for u in usate)
    sbagliate = sum(bool(f["motivi"]) for f in frasi)
    troppe = bool(sent) and inventate / len(sent) > SOGLIA_INVENTATO
    return {"ok": bool(frasi) and not sbagliate and not troppe, "frasi": frasi, "sbagliate": sbagliate,
            "numeri": numeri, "numeri_persi": numeri_persi, "inventate": inventate, "parole": len(att),
            "sentite": len(sent), "copre": round(sum(f["copre"] for f in frasi) / max(1, len(frasi)), 3)}


# ─────────────────────────── i WAV ───────────────────────────
def pcm_e_rate(wav_byte: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(wav_byte), "rb") as w:
        return w.readframes(w.getnframes()), w.getframerate()


def porta_a(pcm: bytes, da: int, a: int) -> bytes:
    from ..suoni import ricampiona
    import numpy as np
    if da == a or not pcm:
        return pcm
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    return np.clip(ricampiona(x, da, a), -32768, 32767).astype("<i2").tobytes()


def in_wav_byte(pcm: bytes, rate: int) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return b.getvalue()


def per_whisper(wav_byte: bytes) -> bytes:
    pcm, r = pcm_e_rate(wav_byte)
    return in_wav_byte(porta_a(pcm, r, WHISPER_RATE), WHISPER_RATE)


def ritrascrivi_http(stt_url: str, modello: str, lingua: str = "it", timeout_s: float = 300.0):
    """Il Whisper dei turni, senza prompt (non si allunga il suo prompt, e il prompt di Calliope qui non c'entra)."""
    def chiedi(wav_byte: bytes) -> str:
        import httpx
        with httpx.Client(timeout=timeout_s, trust_env=False) as c:
            r = c.post(stt_url.rstrip("/") + "/audio/transcriptions",
                       files={"file": ("pezzo.wav", per_whisper(wav_byte), "audio/wav")},
                       data={"model": modello, "language": lingua, "temperature": "0", "response_format": "json"})
        r.raise_for_status()
        return str(r.json().get("text") or "")
    return chiedi


def nella_fascia(fascia, ora=None) -> bool:
    """«00:30-07:00» (anche a cavallo della mezzanotte); vuota: sempre. Una fascia illeggibile è mai: non si ferma
    vLLM per un refuso."""
    f = str(fascia or "").strip()
    if not f:
        return True
    m = re.fullmatch(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", f)
    if not m:
        return False
    a, b = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])
    t = ora if ora is not None else time.localtime()
    x = t.tm_hour * 60 + t.tm_min
    return a <= x < b if a <= b else (x >= a or x < b)


# ─────────────────────────── il preparatore ───────────────────────────
class Preparatore:
    """Un thread, un podcast per volta. Tutto ciò che tocca il mondo è iniettato: le prove usano un motore finto."""

    def __init__(self, studio, ripresa, crea_motore, ritrascrivi, voce_calliope, voce_ferma, lavori_vivi,
                 lettore_libero=None, vllm_libero=None, memoria=memoria_disponibile_mb, log=print,
                 orologio=time.monotonic, dorme=time.sleep):
        self.studio = studio
        self.cfg = studio.cfg
        self.ripresa = ripresa
        self.crea_motore = crea_motore
        self.ritrascrivi = ritrascrivi
        self.voce_calliope = voce_calliope       # `in_wav(testo) → wav`, `VocePiper`: l'avviso e i pezzi a una voce
        self.voce_ferma = voce_ferma             # voce_ferma(secondi) → bool
        self.lavori_vivi = lavori_vivi
        self.lettore_libero = lettore_libero or (lambda: True)
        self.vllm_libero = vllm_libero or (lambda: None)
        self.memoria = memoria
        self.log = log
        self.orologio = orologio
        self.dorme = dorme
        self.misure = {"sessioni": 0, "cedute": {}, "pezzi": 0, "rigenerati": 0, "a_una_voce": 0, "pronti": 0,
                       "scarsi": 0, "fermo_s": 0.0, "ultima": None}
        self._riprova_dopo = 0.0
        self._chiuso = False
        self._sveglia = threading.Event()
        self._thread = None
        self.in_sessione = False
        self._fine = 0.0
        self._d = None
        self._ancora = (0.0, True)     # la firma non si ricalcola ogni mezzo secondo: CPU nel processo della voce
        # Dopo una sessione la voce può essere finita in swap (banco del 04/11): un riscaldamento a voce ferma, così non
        # lo paga il primo turno. Lo mette main.py
        self.dopo_sessione = None

    # ── il thread ──
    def avvia(self):
        self._thread = threading.Thread(target=self._ciclo, daemon=True, name="studio-podcast")
        self._thread.start()

    def close(self):
        self._chiuso = True
        self._sveglia.set()

    def _ciclo(self):
        while not self._chiuso:
            try:
                self.passo()
            except Exception as e:  # noqa: BLE001 — un giro rotto non ferma il processo
                self.log(f"   [STUDIO] podcast: errore nel giro ({type(e).__name__})")
                self._riprova_dopo = self.orologio() + PAUSA_DOPO_GUASTO_S
            self._sveglia.wait(GIRO_S)
            self._sveglia.clear()

    def passo(self) -> str:
        """Un giro: «niente», il motivo per cui non parte, o l'esito della sessione."""
        if not self.ripresa.controlla():        # una ripartenza non riuscita prima di tutto
            return "vllm_da_riprendere"
        per = self.studio.podcast_da_preparare()
        if not per:
            return "niente"
        motivo = self.motivo()
        if motivo is not None:
            return motivo
        return self.sessione(per[0])

    def motivo(self) -> str | None:
        """Perché adesso non si parte; None se si può fermare vLLM."""
        cfg = self.cfg
        if self.orologio() < self._riprova_dopo:
            return "pausa"
        if not nella_fascia(getattr(cfg, "studio_podcast_fascia", "")):
            return "fuori_fascia"
        if not self.voce_ferma(float(getattr(cfg, "studio_podcast_quiete_s", 900) or 0)):
            return "voce_non_ferma"
        if self.lavori_vivi():
            return "lavoro_agente"
        if not self.lettore_libero():
            return "lettore_occupato"
        if not self.ripresa.vllm.acceso():
            return "vllm_spento"
        m = self.vllm_libero()
        if m:
            return "vllm_occupato"
        mem = self.memoria()
        if mem is None or mem < PAVIMENTO_MB:
            return "memoria"
        return None

    def _cede(self) -> str | None:
        """Durante la sessione: il motivo per fermarsi adesso. Senza quiete: basta un segno della voce."""
        if self._chiuso:
            return "chiusura"
        if not self.voce_ferma(0):
            return "voce"
        if self.lavori_vivi():
            return "lavoro_agente"
        if self.orologio() > self._fine:
            return "tetto"
        mem = self.memoria()
        if mem is not None and mem < PAVIMENTO_MB:
            return "memoria_bassa"
        d = self._d
        if d is not None:
            ora = self.orologio()
            if ora - self._ancora[0] >= ANCORA_OGNI_S:
                self._ancora = (ora, self.studio.podcast_ancora(d["id"], d["firma"]))
            if not self._ancora[1]:
                return "verifica_cambiata"
        return None

    # ── lo stato su disco ──
    def _cartella(self, vid) -> Path:
        c = P.cartella_podcast(self.cfg, vid)
        c.mkdir(parents=True, exist_ok=True)
        return c

    @staticmethod
    def _file_stato(c: Path, firma: str) -> Path:
        return c / f"{firma}-stato.json"

    def _stato(self, c: Path, firma: str) -> dict:
        try:
            return json.loads(self._file_stato(c, firma).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"pezzi": {}, "sessioni": 0, "fermo_s": 0.0}

    def _salva(self, c: Path, firma: str, st: dict) -> None:
        f = self._file_stato(c, firma)
        t = f.with_name(f.name + ".tmp")
        t.write_text(json.dumps(st), encoding="utf-8")
        os.replace(t, f)

    # ── la sessione ──
    def sessione(self, d: dict) -> str:
        """Un podcast, una finestra: vLLM fermo, i pezzi che mancano, vLLM di nuovo in piedi. Sempre."""
        cfg = self.cfg
        vid, firma = d["id"], d["firma"]
        c = self._cartella(vid)
        st = self._stato(c, firma)
        self.in_sessione = True
        self._d = d
        self._ancora = (0.0, True)
        self._fine = self.orologio() + float(getattr(cfg, "studio_podcast_tetto_min", 60) or 60) * 60
        fine, motore = "finito", None
        m = self.misure
        m["sessioni"] += 1
        st["sessioni"] = int(st.get("sessioni") or 0) + 1
        conti = {"verifica": vid, "carico_s": None, "pezzi_fatti": 0, "rigenerati": 0}
        self.log(f"   [STUDIO] podcast della verifica {vid}: fermo vLLM ({len(d['pezzi'])} pezzi)")
        try:
            self.ripresa.ferma({"verifica": vid})
            motivo = self._aspetta_memoria()
            if motivo:
                raise Ceduto(motivo)
            motore = self.crea_motore(self._cede)
            motore.avvia()
            conti["carico_s"] = getattr(motore, "carico_s", None)
            for p in d["pezzi"]:
                self._pezzo(motore, p, c, firma, st, conti)
        except Ceduto as e:
            fine = str(e)
        except Guasto as e:
            fine = f"guasto_{e}"
            conti["guasto"] = {k: v for k, v in (getattr(motore, "ultima", None) or {}).items() if k != "messaggio"}
            self._riprova_dopo = self.orologio() + PAUSA_DOPO_GUASTO_S
        except Exception as e:  # noqa: BLE001 — qualunque cosa, vLLM riparte
            fine = f"errore_{type(e).__name__}"
            self._riprova_dopo = self.orologio() + PAUSA_DOPO_GUASTO_S
        finally:
            if motore is not None:
                try:
                    motore.ferma()
                except Exception as e:  # noqa: BLE001
                    self.log(f"   [STUDIO] container di MOSS non tolto: {type(e).__name__}")
            ripartito = False
            try:
                ripartito = self.ripresa.riparti()
            except Exception as e:  # noqa: BLE001 — `passo` riprova
                self.log(f"   [STUDIO] vLLM non ripartito: {type(e).__name__}")
            self.in_sessione = False
            self._d = None
            fermo = self.ripresa.ultimo_fermo_s or 0.0
            st["fermo_s"] = round(float(st.get("fermo_s") or 0) + fermo, 1)
            self._salva(c, firma, st)
            m["fermo_s"] = round(m["fermo_s"] + fermo, 1)
            m["ultima"] = {**conti, "fine": fine, "fermo_s": fermo, "ripartito": ripartito,
                           "differenze": list(self.ripresa.ultime_differenze)}
            m["cedute"][fine] = m["cedute"].get(fine, 0) + 1
            self.log(f"   [STUDIO] podcast della verifica {vid}: {fine}, {conti['pezzi_fatti']} pezzi in questa "
                     f"sessione, vLLM fermo {fermo:.0f} s, ripartito: {'sì' if ripartito else 'NO'}")
            if self.dopo_sessione is not None and self.voce_ferma(0):
                try:
                    self.dopo_sessione()
                except Exception as e:  # noqa: BLE001
                    self.log(f"   [STUDIO] riscaldamento dopo il podcast: {type(e).__name__}")
        if fine == "tetto":
            self._riprova_dopo = self.orologio() + PAUSA_FRA_SESSIONI_S
        if fine == "finito":
            self._finisci(d, c, st)
        return fine

    def _aspetta_memoria(self) -> str | None:
        """Dopo il fermo di vLLM la memoria deve bastare a MOSS: altrimenti si riparte subito."""
        soglia = float(getattr(self.cfg, "studio_podcast_memoria_gb", 32) or 0) * 1024
        fine = self.orologio() + ATTESA_MEMORIA_S
        while True:
            m = self._cede()
            if m:
                return m
            mem = self.memoria()
            if mem is None or mem >= soglia:
                return None
            if self.orologio() >= fine:
                self._riprova_dopo = self.orologio() + PAUSA_FRA_SESSIONI_S
                return "memoria_insufficiente"
            self.dorme(2.0)

    def _pezzo(self, motore, p: dict, c: Path, firma: str, st: dict, conti: dict) -> None:
        n = str(p["n"])
        x = st["pezzi"].setdefault(n, {"stato": "da_fare", "tentativi": 0, "firma": p["firma"]})
        if x["stato"] in ("ok", "una_voce"):
            return
        file_ok = c / f"{firma}-p{n}.wav"
        massimo = 1 + int(getattr(self.cfg, "studio_podcast_rigenera", RIGENERA_MAX))
        prova = c / f"{firma}-p{n}.prova.wav"
        # `prova` può essere rimasta da una sessione interrotta dopo l'ultimo tentativo: va controllata
        while x["tentativi"] < massimo or prova.exists():
            m = self._cede()
            if m:
                raise Ceduto(m)
            if not prova.exists():
                motore.seme = 42 + int(x["tentativi"])
                wav = motore.in_wav(p["moss"])
                tmp = prova.with_name(prova.name + ".tmp")
                tmp.write_bytes(wav)
                os.replace(tmp, prova)
                x["tentativi"] += 1
                x["motore"] = dict(getattr(motore, "ultima", None) or {})
                if x["tentativi"] > 1:
                    conti["rigenerati"] += 1
                    self.misure["rigenerati"] += 1
                self._salva(c, firma, st)
            wav = prova.read_bytes()
            m = self._cede()
            if m:
                raise Ceduto(m)      # il pezzo fatto resta: la sessione dopo lo controlla senza rifarlo
            testo = self.ritrascrivi(wav)
            e = confronta(p["battute"], testo)
            x["confronto"] = {k: e[k] for k in ("ok", "sbagliate", "numeri", "numeri_persi", "inventate", "parole",
                                                "sentite", "copre")}
            if e["ok"]:
                os.replace(prova, file_ok)
                x["stato"] = "ok"
                break
            prova.unlink()
        else:
            x["stato"] = "una_voce"
            self.misure["a_una_voce"] += 1
        conti["pezzi_fatti"] += 1
        self.misure["pezzi"] += 1
        self._salva(c, firma, st)

    # ── alla fine ──
    def _finisci(self, d: dict, c: Path, st: dict) -> None:
        """Tutti i pezzi hanno un esito: le parti con l'avviso in testa, poi la riga. Troppi pezzi a una voce: niente
        podcast, e resta il riassunto."""
        vid, firma = d["id"], d["firma"]
        pezzi = d["pezzi"]
        esiti = [st["pezzi"].get(str(p["n"]), {}).get("stato") for p in pezzi]
        if any(s not in ("ok", "una_voce") for s in esiti):
            return
        a_una = esiti.count("una_voce")
        conti = {"pezzi": len(pezzi), "a_una_voce": a_una, "sessioni": st.get("sessioni"),
                 "fermo_s": st.get("fermo_s"),
                 "tentativi": sum(int(x.get("tentativi") or 0) for x in st["pezzi"].values()),
                 "frasi": sum(b["tipo"] == "frase" for p in pezzi for b in p["battute"]),
                 "frasi_a_due_voci": sum(b["tipo"] == "frase" for p in pezzi for b in p["battute"]
                                         if st["pezzi"][str(p["n"])]["stato"] == "ok")}
        conti["copre"] = _media([(x.get("confronto") or {}).get("copre") for x in st["pezzi"].values()
                                 if x.get("stato") == "ok"])
        if a_una / max(1, len(pezzi)) > UNA_VOCE_MAX:
            self.studio.podcast_audio_finito(vid, firma, {"esito": "scarso", "firma": firma, "parti": [], "conti": conti})
            self.studio._togli_audio_podcast(vid)
            self.misure["scarsi"] += 1
            self.log(f"   [STUDIO] podcast della verifica {vid}: {a_una} pezzi su {len(pezzi)} non tornano, resta il "
                     "riassunto")
            return
        try:
            parti = self._componi(d, c, st)
        except Exception as e:  # noqa: BLE001 — senza la voce di Calliope non c'è l'avviso: niente podcast adesso
            self.log(f"   [STUDIO] podcast della verifica {vid}: parti non composte ({type(e).__name__})")
            self._riprova_dopo = self.orologio() + PAUSA_DOPO_GUASTO_S
            return
        audio = {"esito": "pronto", "firma": firma, "parti": parti, "conti": conti}
        if self.studio.podcast_audio_finito(vid, firma, audio):
            self.misure["pronti"] += 1
            self.log(f"   [STUDIO] podcast della verifica {vid} pronto: {len(parti)} parti, "
                     f"{sum(p['secondi'] for p in parti):.0f} s, {a_una} a una voce")
            for f in c.glob(f"{firma}-p*.wav"):
                f.unlink()

    def _componi(self, d: dict, c: Path, st: dict) -> list[dict]:
        firma = d["firma"]
        parti = []
        rate = None
        for p in d["pezzi"]:
            x = st["pezzi"][str(p["n"])]
            if x["stato"] == "ok":
                pcm, rate = pcm_e_rate((c / f"{firma}-p{p['n']}.wav").read_bytes())
                parti.append((p, pcm, rate))
            else:
                parti.append((p, None, None))
        rate = rate or int(self.voce_calliope.rate)
        intro = porta_a(pcm_e_rate(self.voce_calliope.in_wav(S.PODCAST_INTRO))[0], int(self.voce_calliope.rate), rate)
        intro += b"\0\0" * int(rate * INTRO_SILENZIO_S)
        intro_s = len(intro) / 2 / rate
        out = []
        for p, pcm, r in parti:
            una_voce = pcm is None
            if una_voce:
                pcm = self._a_una_voce(p, rate)
            elif r != rate:
                pcm = porta_a(pcm, r, rate)
            dati = in_wav_byte(intro + pcm, rate)
            f = c / S.nome_file(firma, p["n"])
            t = f.with_name(f.name + ".tmp")
            t.write_bytes(dati)
            os.replace(t, f)
            out.append({"n": p["n"], "secondi": round((len(intro) + len(pcm)) / 2 / rate, 1), "intro_s": round(intro_s, 3),
                        "una_voce": una_voce, "argomenti": p["argomenti"],
                        "frasi": sum(b["tipo"] == "frase" for b in p["battute"])})
        return out

    def _a_una_voce(self, p: dict, rate: int) -> bytes:
        """Il pezzo che non è tornato, nella voce di Calliope, dicendolo: solo le battute con la fonte."""
        v = self.voce_calliope
        pausa = b"\0\0" * int(rate * FRA_BATTUTE_S)
        pcm = porta_a(pcm_e_rate(v.in_wav(S.PODCAST_PEZZO_A_UNA_VOCE))[0], int(v.rate), rate) + pausa
        for b in p["battute"]:
            if b["tipo"] != "cenno":
                pcm += porta_a(pcm_e_rate(v.in_wav(b["detto"]))[0], int(v.rate), rate) + pausa
        return pcm


def _media(xs: list) -> float | None:
    xs = [float(x) for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


# ─────────────────────────── il montaggio ───────────────────────────
def percorso_voce(cfg, chiave: str) -> str:
    """La voce di Piper di una delle due voci del podcast: mai una persona reale (`studio_podcast_voce_a`, `_b`)."""
    p = str(getattr(cfg, chiave, "") or "")
    if p and not os.path.isabs(p):
        p = os.path.join(str(getattr(cfg, "config_dir", "") or os.getcwd()), p)
    return p


def riferimento(cfg, voce_per, chiave: str, pronuncia=None) -> Path:
    """Il WAV di riferimento di una voce, generato con Piper una volta (nessun dato di nessuno: la frase è fissa)."""
    from . import dati as D
    percorso = percorso_voce(cfg, chiave)
    c = D.cartella_di(cfg) / "podcast_riferimenti"
    c.mkdir(parents=True, exist_ok=True)
    f = c / (Path(percorso).stem + ".wav")
    if not f.exists():
        dati = S.VocePiper(voce_per(percorso), pronuncia).in_wav(TESTO_RIFERIMENTO)
        t = f.with_name(f.name + ".tmp")
        t.write_bytes(dati)
        os.replace(t, f)
    return f


def radice_moss(cfg) -> Path:
    return Path(str(getattr(cfg, "studio_podcast_moss", "") or "~/calliope-motore/moss")).expanduser()


def crea_motore_moss(cfg, voce_per, pronuncia=None):
    def crea(cede):
        return MotoreMoss(radice_moss(cfg), P.cartella_lavoro(cfg),
                          riferimento(cfg, voce_per, "studio_podcast_voce_a", pronuncia),
                          riferimento(cfg, voce_per, "studio_podcast_voce_b", pronuncia), cede=cede)
    return crea


def prepara(studio, ripresa, lavori, speaker, log=print, avvia: bool = True) -> Preparatore | None:
    """Il preparatore di questa installazione, o None: podcast spento, niente Whisper a server, niente voci."""
    from .. import arbitro_memoria as am
    cfg = studio.cfg
    if P.modo(cfg) != P.ATTIVA or speaker is None or ripresa is None:
        return None
    if getattr(studio, "lettore", None) is None:
        log("[STUDIO] podcast: senza il lettore nessuno scrive il copione: non parte")
        return None
    if not cfg.stt_url:
        log("[STUDIO] podcast: senza Whisper a server (`stt_url`) non parte")
        return None
    pron = getattr(speaker, "pronuncia", None)
    studio.podcast_pronuncia = pron
    voce = S.VocePiper(speaker.voce_per(cfg.piper_voice), pron)
    lettore = getattr(studio, "lettore", None)
    guardia = getattr(lettore, "guardia", None)

    def vivi() -> bool:
        return bool(lavori is not None and lavori.attivi(attesa=True))

    def turni_fermi(secondi: float) -> bool:
        # Senza i suoi segnali (`arbitro_memoria: ombra`) quiete() direbbe sempre sì: qui vale no
        return bool(am.QUIETE.segnali) and am.quiete(secondi)
    preparatore = Preparatore(
        studio, ripresa, crea_motore_moss(cfg, speaker.voce_per, pron),
        ritrascrivi_http(cfg.stt_url, cfg.stt_modello, cfg.language), voce, turni_fermi, vivi,
        lettore_libero=(lambda: not (lettore and lettore.occupato())) if lettore is not None else None,
        vllm_libero=guardia.motivo if guardia is not None else None, log=log)
    if avvia:
        preparatore.avvia()
    return preparatore
