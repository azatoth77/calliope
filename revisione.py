"""
Revisione dei turni: trova le frasi ripetute subito dopo, segnale di una trascrizione
sbagliata (docs/visione.md, "Auto-miglioramento").

Se una frase viene ridetta entro pochi secondi con un testo simile ma diverso, la prima
è quasi certamente un errore di Whisper e la seconda il suo riferimento. Il 24/09:
«Equale rospaniac» → «E quella della Spagna?», «Dimitra, città della Toscana» →
«Dimmi tre città della Toscana».

La somiglianza del testo da sola sbaglia su richieste diverse con parole in comune
(«Ricordati che il mio numero preferito…» → «Qual è il mio numero preferito?»): con
--llm ogni candidata viene confermata dal modello, che deve solo classificare.

Uso:
    python revisione.py                          # registro dei turni (Config.turn_log_dir)
    python revisione.py registrazioni\\2026-09-24-v03 [altre cartelle]   # trascrizioni.tsv
    python revisione.py --llm ...                 # conferma con l'LLM
    python revisione.py --tsv candidati.tsv ...   # salva le coppie trovate
"""

import csv
import datetime
import difflib
import re
import sys
from pathlib import Path

from calliope.config import Config, load_config
from calliope.turnlog import read_turns

MAX_GAP_S = 20.0          # la ripetizione arriva entro questi secondi dall'inizio della prima
MIN_RATIO = 0.35          # sotto: frasi diverse
MAX_RATIO = 0.97          # sopra: la stessa trascrizione (il problema non era Whisper)


def normalize(text: str, name: str) -> str:
    """Minuscolo, senza punteggiatura e senza il nome (che c'è in una e non nell'altra)."""
    t = re.sub(r"[^\wàèéìòù ]", " ", (text or "").lower())
    t = re.sub(rf"\b{re.escape(name.lower())}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def turns_from_tsv(folder: Path) -> list[dict]:
    """Turni ricostruiti da trascrizioni.tsv (test vocali senza registro dei turni)."""
    out = []
    with open(folder / "trascrizioni.tsv", encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 3:
                continue
            when = datetime.datetime.strptime(row[0], "%Y%m%d-%H%M%S")
            out.append({"inizio": when.isoformat(), "testo": row[2], "audio": row[0],
                        "cartella": str(folder), "voce": None})
    return out


def find_repetitions(turns: list[dict], name: str) -> list[dict]:
    """Coppie (prima, ripetizione) candidate, in ordine di tempo."""
    pairs = []
    for a, b in zip(turns, turns[1:]):
        if not a.get("testo") or not b.get("testo"):
            continue
        who_a = (a.get("voce") or {}).get("migliore")
        who_b = (b.get("voce") or {}).get("migliore")
        if who_a and who_b and who_a != who_b:
            continue                                   # due persone diverse
        gap = (datetime.datetime.fromisoformat(b["inizio"])
               - datetime.datetime.fromisoformat(a["inizio"])).total_seconds()
        if not 0 < gap <= MAX_GAP_S:
            continue
        na, nb = normalize(a["testo"], name), normalize(b["testo"], name)
        if not na or not nb:
            continue
        ratio = difflib.SequenceMatcher(None, na, nb).ratio()
        if MIN_RATIO <= ratio < MAX_RATIO:
            pairs.append({"prima": a, "ripetizione": b, "somiglianza": round(ratio, 2),
                          "distanza_s": round(gap, 1)})
    return pairs


def confirm_with_llm(pairs: list[dict], cfg: Config):
    """Chiede al modello se B ridice A. Solo classificazione: sì o no."""
    import httpx
    http = httpx.Client(base_url=cfg.llm_native_url, timeout=60.0)
    for p in pairs:
        # Esempi inventati, diversi dalle frasi dei test: senza, gemma4 rispondeva
        # DIVERSA quasi sempre (2 coppie vere confermate su ~12, prova del 24/09)
        prompt = (
            "Una persona parla a un'assistente vocale. Il riconoscimento vocale a volte "
            "storpia le parole in altre parole che SUONANO simili. Se l'assistente non "
            "capisce, la persona ripete la stessa frase.\n"
            "Decidi se la seconda frase è la stessa frase della prima ridetta (la prima "
            "era storpiata), oppure una richiesta nuova.\n\n"
            "Esempi:\n"
            "«Accendi la lucertola» → «Accendi la luce in cucina»: STESSA\n"
            "«Metti un po' di musica ammazza» → «Metti un po' di musica jazz»: STESSA\n"
            "«Quanto fa sette per otto?» → «E sette per nove?»: DIVERSA\n"
            "«Mi piace il mare» → «Qual è il mare più grande?»: DIVERSA\n\n"
            f"«{p['prima']['testo']}» → «{p['ripetizione']['testo']}»: ?\n"
            "Rispondi solo con STESSA o DIVERSA.")
        r = http.post("/api/chat", json={
            "model": cfg.llm_model, "stream": False, "think": False,
            "keep_alive": cfg.llm_keep_alive,
            "options": {"num_ctx": cfg.llm_num_ctx, "temperature": 0},
            "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        answer = r.json()["message"]["content"].strip().upper()
        p["llm"] = "stessa" if answer.startswith("STESSA") else "diversa"


def main(argv: list[str]):
    cfg = load_config()
    use_llm = "--llm" in argv
    tsv_out = None
    if "--tsv" in argv:
        i = argv.index("--tsv")
        tsv_out = argv[i + 1]
        del argv[i:i + 2]
    folders = [a for a in argv if not a.startswith("--")]

    if folders:
        turns = [t for f in folders for t in turns_from_tsv(Path(f))]
    elif cfg.turn_log_dir and Path(cfg.turn_log_dir).exists():
        turns = read_turns(cfg.turn_log_dir)
    else:
        sys.exit("Nessun registro dei turni: indica una cartella di registrazioni.")

    pairs = find_repetitions(turns, cfg.name)
    if use_llm:
        confirm_with_llm(pairs, cfg)

    print(f"{len(turns)} turni, {len(pairs)} ripetizioni candidate\n")
    for p in pairs:
        verdict = f"  [LLM: {p['llm']}]" if "llm" in p else ""
        print(f"{p['somiglianza']:.2f}  +{p['distanza_s']:>4}s  "
              f"«{p['prima']['testo']}» → «{p['ripetizione']['testo']}»{verdict}")

    if tsv_out:
        with open(tsv_out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["audio", "trascritto", "riferimento", "somiglianza", "llm"])
            for p in pairs:
                if p.get("llm", "stessa") == "stessa":
                    w.writerow([p["prima"].get("audio"), p["prima"]["testo"],
                                p["ripetizione"]["testo"], p["somiglianza"], p.get("llm", "")])
        print(f"\nCoppie confermate salvate in {tsv_out}")


if __name__ == "__main__":
    main(sys.argv[1:])
