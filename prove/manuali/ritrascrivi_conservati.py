"""Le registrazioni conservate ritrascritte con la corsia lenta (14/10 sera, conversazione di stanza,
passo 3; richiesta di Dario: il primo riferimento per la WER viene dal materiale vero che c'è).

NON fa parte del runner. Si lancia **sulla DGX**, dalla cartella dei dati di Calliope:

    V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)
    cd ~/calliope && $V/.venv/bin/python $V/prove/manuali/ritrascrivi_conservati.py

Legge il registro dei turni (`turn_log_dir`, `turni-*.jsonl`) e la voce conservata (decisione
0028 T1, calliope/conserva.py: `<turn_log_dir>/voce/<id>/<giorno>/<ora>.wav`, μ-law, solo adulti
col consenso): per ogni turno con la voce e il testo di Whisper (`testo`), ritrascrive l'audio
**come la corsia lenta** (calliope/stanza/lenta.py): il prompt col nome di chi parla e le parole
del turno di prima della stessa persona entro 5 minuti (al più `stanza_lenta_prompt_caratteri`),
il Whisper della corsia lenta (`stanza_lenta_stt_url` se c'è, altrimenti quello dei turni con
`stt_motore`/`stt_url`), il beam `stanza_lenta_beam` con faster-whisper; il prompt solo se
`stanza_lenta_prompt` lo accende (di serie «auto»: solo con un Whisper suo); `--prompt` lo
accende comunque, per confrontare. Confronta le parole
normalizzate con la trascrizione originale e scrive **solo i casi diversi** in
`privato/ritrascrizione-conservati-AAAAMMGG-HHMM.md` (cartella `privato/` della cartella di
lavoro, fuori da git; file 600), uno per caso:

    ## 7 · 2026-10-12 18:03:21 · 2,4 s · p-xxxx/2026-10-12/180321-123.wav
    - originale: Che ore sono a Tokio
    - lenta: Che ore sono a Tokyo?
    - scelta:
    - corretto:

Chi rilegge (ascoltando il file, se serve) scrive in `scelta` **o** (giusta l'originale), **l**
(giusta la lenta), **c** (nessuna delle due: la frase giusta in `corretto`), **?** (non si
capisce: fuori dal conto). In testa al file i numeri dei casi uguali (le parole dove le due
trascrizioni coincidono valgono come giuste, assunzione dichiarata). Il banco
`prove/manuali/banco_stanza_lenta.py --conservati FILE.md` ne ricava WER dell'originale e della
lenta sul set intero.

Opzioni:
    --persona ID|NOME   solo una persona (di serie tutte quelle con la voce conservata)
    --giorni N          solo gli ultimi N giorni del registro
    --max N             al più N registrazioni
    --senza-prompt      ritrascrive senza prompt
    --prompt            ritrascrive col prompt anche con lo stesso Whisper dei turni
    --uscita DIR        di serie privato/
    --pausa S           secondi fra una richiesta e l'altra (di serie 0,3: Calliope resta
                        accesa e ha la precedenza, ma il Whisper dei turni è lo stesso)

Il file contiene le parole dette a Calliope dalla persona: resta in privato/ sulla DGX, mai nel
repository, e `calliope conserva --svuota` non lo conosce (cancellarlo a mano dopo l'uso).
"""
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
SALTA = 77


def opzioni(argv):
    o, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k = a[2:].replace("-", "_")
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                o[k] = argv[i + 1]
                i += 2
            else:
                o[k] = True
                i += 1
        else:
            i += 1
    return o


def parole(t) -> list[str]:
    """Le parole normalizzate come nel filtro dell'eco (minuscole, senza accenti, cifre in
    lettere: «19» e «diciannove» sono la stessa parola), «%» come «per cento»."""
    from calliope.stanza.eco import parole as pp
    return [w for w, _ in pp(str(t or "").replace("%", " per cento"))]


def prompt_lento(cfg, nome: str | None, prima: str | None, senza: bool) -> str:
    """Il prompt della corsia lenta per una frase sola: «Parla Carlo.» e la coda delle parole di
    prima (calliope/stanza/lenta.Lenta.prompt, qui senza la stanza)."""
    v = str(getattr(cfg, "stanza_lenta_prompt", "auto") or "auto").strip().lower()
    acceso = (v in ("si", "sì") or (v not in ("no",) and bool(str(
        getattr(cfg, "stanza_lenta_stt_url", "") or "").strip())))
    if senza or not acceso:
        return ""
    testa = f"Parla {str(nome).split()[0]}." if nome else ""
    car = int(getattr(cfg, "stanza_lenta_prompt_caratteri", 160) or 0)
    coda = " ".join(str(prima or "").split())[-car:] if car > 0 and prima else ""
    if coda and len(coda) == car and " " in coda:
        coda = coda.split(" ", 1)[1]
    return " ".join(x for x in (testa, coda) if x)


def trascrittore(cfg):
    """(funzione(audio, prompt) → testo, descrizione): il Whisper della corsia lenta."""
    url = str(getattr(cfg, "stanza_lenta_stt_url", "") or "").strip()
    if url:
        import httpx

        from calliope.stt import unisci_righe, wav_bytes
        modello = str(getattr(cfg, "stanza_lenta_stt_modello", "") or "") or cfg.stt_modello

        def f(audio, prompt):
            r = httpx.post(url.rstrip("/") + "/audio/transcriptions",
                           files={"file": ("frase.wav", wav_bytes(audio, 16000), "audio/wav")},
                           data={"model": modello, "language": cfg.language, "prompt": prompt,
                                 "temperature": "0", "response_format": "json"},
                           timeout=max(10.0, 3 * len(audio) / 16000))
            r.raise_for_status()
            return unisci_righe(str(r.json().get("text") or "")).strip()
        return f, f"Whisper della corsia lenta su {url} ({modello})"
    from calliope.stt import make_transcriber
    stt = make_transcriber(cfg)
    beam = int(getattr(cfg, "stanza_lenta_beam", 8) or 8)

    def g(audio, prompt):
        return stt.transcribe(audio, prompt=prompt, beam=beam)
    return g, (f"Whisper dei turni ({getattr(stt, 'device', '?')}, "
               f"{getattr(cfg, 'stt_modello', '') if getattr(stt, 'device', '') == 'server' else cfg.whisper_model}), "
               f"beam {beam} se locale")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    o = opzioni(sys.argv[1:])
    from calliope.config import load_config
    from calliope.conserva import CARTELLA_VOCE, leggi_wav
    from calliope.latenza import leggi
    cfg = load_config()
    cartella = Path(cfg.turn_log_dir or "")
    voce_dir = cartella / CARTELLA_VOCE
    if not voce_dir.is_dir():
        print(f"Nessuna voce conservata in {voce_dir}: niente da fare.")
        return SALTA
    giorni = int(o["giorni"]) if o.get("giorni") else None
    turni = [r for r in leggi(str(cartella), giorni)
             if r.get("voce_file") and str(r.get("testo") or "").strip()
             and r.get("testo") != "(frase di conferma)"]
    chi = str(o.get("persona") or "").strip().lower()
    if chi:
        turni = [r for r in turni if chi in (str((r.get("voce") or {}).get("id") or "").lower(),
                                             str((r.get("voce") or {}).get("nome") or "").lower())]
    turni.sort(key=lambda r: str(r.get("inizio") or ""))
    if o.get("max"):
        turni = turni[:int(o["max"])]
    if not turni:
        print("Nessun turno con la voce conservata e il testo: niente da fare.")
        return SALTA
    try:
        trascrivi, come = trascrittore(cfg)
    except Exception as e:  # noqa: BLE001
        print(f"Whisper non disponibile ({type(e).__name__}: {e}): salto.")
        return SALTA
    print(f"{len(turni)} registrazioni; ritrascrivo con {come}")
    pausa = float(o.get("pausa") or 0.3)
    diversi, uguali, parole_uguali, mancanti, errori = [], 0, 0, 0, 0
    ultimo: dict = {}                                # persona → (istante, testo)
    t_tot = 0.0
    usato_prompt = False
    for i, r in enumerate(turni, 1):
        f = voce_dir / str(r["voce_file"])
        v = r.get("voce") or {}
        pid = str(v.get("id") or v.get("nome") or "?")
        try:
            quando = datetime.datetime.fromisoformat(str(r.get("inizio"))[:23])
        except ValueError:
            quando = None
        prima = None
        if quando is not None and pid in ultimo and (quando - ultimo[pid][0]).total_seconds() < 300:
            prima = ultimo[pid][1]
        if quando is not None:
            ultimo[pid] = (quando, str(r.get("testo")))
        if not f.exists():
            mancanti += 1
            continue
        try:
            audio, sr = leggi_wav(f)
            if sr != 16000:
                import numpy as np
                n = int(len(audio) * 16000 / sr)
                audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)),
                                  audio).astype("float32")
            t0 = time.perf_counter()
            if o.get("prompt"):
                cfg.stanza_lenta_prompt = "si"
            pr = prompt_lento(cfg, v.get("nome"), prima, bool(o.get("senza_prompt")))
            usato_prompt = usato_prompt or bool(pr)
            lenta = trascrivi(audio, pr)
            t_tot += time.perf_counter() - t0
        except Exception as e:  # noqa: BLE001
            errori += 1
            print(f"  {i}: errore {type(e).__name__}: {e}")
            continue
        orig = str(r.get("testo"))
        if parole(orig) == parole(lenta):
            uguali += 1
            parole_uguali += len(parole(orig))
        else:
            diversi.append({"n": len(diversi) + 1, "quando": str(r.get("inizio"))[:19].replace(
                "T", " "), "durata": round(len(audio) / 16000, 1), "file": str(r["voce_file"]),
                "originale": orig, "lenta": lenta})
        if i % 10 == 0:
            print(f"  {i}/{len(turni)}: diverse {len(diversi)}, uguali {uguali}")
        time.sleep(pausa)
    uscita = Path(o.get("uscita") or "privato")
    uscita.mkdir(parents=True, exist_ok=True, mode=0o700)
    nome = f"ritrascrizione-conservati-{datetime.datetime.now():%Y%m%d-%H%M}.md"
    righe = [f"# Registrazioni conservate: originale e corsia lenta ({datetime.date.today()})",
             "",
             f"<!-- banco: {json.dumps({'totale': len(turni), 'uguali': uguali, 'parole_uguali': parole_uguali, 'diversi': len(diversi), 'mancanti': mancanti, 'errori': errori, 'come': come, 'prompt': usato_prompt}, ensure_ascii=False)} -->",
             "",
             f"{len(turni)} registrazioni, {uguali} uguali (non elencate), **{len(diversi)} "
             f"diverse** qui sotto; file mancanti {mancanti}, errori {errori}. Ritrascritte con "
             f"{come}.",
             "",
             "In `scelta` scrivi: **o** = giusta l'originale, **l** = giusta la lenta, **c** = "
             "nessuna delle due (la frase giusta in `corretto`), **?** = non si capisce. I file "
             "audio sono sotto `registro/voce/`.", ""]
    for d in diversi:
        righe += [f"## {d['n']} · {d['quando']} · {str(d['durata']).replace('.', ',')} s · "
                  f"{d['file']}",
                  f"- originale: {d['originale']}",
                  f"- lenta: {d['lenta']}",
                  "- scelta: ",
                  "- corretto: ", ""]
    p = uscita / nome
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(righe))
    print(f"\nFatto: {len(diversi)} casi diversi su {len(turni)} ({uguali} uguali), Whisper "
          f"{t_tot:.1f} s in tutto. Da rileggere: {p.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
