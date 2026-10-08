"""Misura delle frasi pronte (analisi del 08/10, docs/ricerche/2026-10-08-frasi-pronte.md).

Per ogni frase pronta tipica (valori di fantasia) e per ogni tono, tre modi:
- coda: la frase pronta resta com'è (già detta) e il modello aggiunge una frase breve col tono;
- riformula: il modello riscrive la frase col tono, con i fatti bloccati;
- fatti: la frase pronta arriva come «dati del turno» e il modello risponde (come
  SFIDA_ESITO_MSG di brain.py).
Controllo automatico: fatti presenti (riformula, fatti), niente fatti nuovi (numeri, nomi tra
«», azioni dichiarate), domanda finale conservata, registro (lei nel formale), lunghezza.
Tempi: primo token, prima frase intera, fine.

Misura, non una prova registrata: `python prove/misura_frasi_pronte.py <uscita.jsonl>`.
Modello e indirizzo da CALLIOPE_MISURA_MODELLO e CALLIOPE_MISURA_URL (predefiniti: gemma4
e4b sull'Ollama locale). Alla fine `ollama stop` del modello. ~270 richieste, ~3 min sul
portatile. Il banco non mette nella storia la chiamata del tool e il suo risultato: è il motivo
probabile delle «chiamate scritte» (vedi il documento), da rifare con la storia completa.
"""
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from calliope.config import Config  # noqa: E402

URL = os.environ.get("CALLIOPE_MISURA_URL", "http://127.0.0.1:11434/api/chat")
MODELLO = os.environ.get("CALLIOPE_MISURA_MODELLO", "gemma4:e4b-it-qat")
TONI = ["normale", "amichevole", "ironico", "formale", "computer_di_bordo"]

# (id, classe, richiesta, frase pronta, fatti: liste di alternative, domanda finale?)
FRASI = [
    ("lavoro_avviato", "annuncio", "Sì, procedi.",
     "Ci lavoro in secondo piano: ti avviso quando è pronto. Intanto puoi chiedermi altro.",
     [["avvis", "avvert", "faccio sapere", "dirò", "comunic"]], False),
    ("estensione_attiva", "esito", "Approva l'estensione.",
     "Fatto: «Meteo città» è attiva, versione 3. Da adesso puoi chiedermela.",
     [["«Meteo città»", "Meteo città"], ["3", "tre", "terza"]], False),
    ("politica_agente", "politica", "Affidalo all'agente.",
     "C'è di mezzo il lavoro di un agente, quindi chiedo a te: vuoi che affidi all'agente il "
     "lavoro «Orario dei treni»?",
     [["agente"], ["Orario dei treni"]], True),
    ("ora", "lettura", "Che ore sono?", "Sono le 18:05.", [["18:05", "18 e 5", "18 e 05"]],
     False),
    ("timer", "esito", "Metti un timer di 10 minuti.", "Va bene, timer di 10 minuti avviato.",
     [["10", "dieci"], ["timer"]], False),
    ("lista", "esito", "Aggiungi latte e pane alla spesa.",
     "Ho aggiunto latte e pane alla lista della spesa.",
     [["latte"], ["pane"], ["spesa"]], False),
    ("promemoria", "esito", "Domani alle 9 ricordami di chiamare l'idraulico.",
     "Va bene, domani alle 9 ti ricordo di chiamare l'idraulico.",
     [["9", "nove"], ["idraulico"], ["domani"]], False),
    ("lavori_nessuno", "lettura", "Ci sono lavori in corso?", "Non ho lavori in corso.",
     [["non", "nessun"], ["lavor"]], False),
    ("documento", "esito", "Scrivi una lettera di disdetta della palestra.",
     "Ho preparato la lettera «Disdetta palestra»: 4 paragrafi, nella cartella Calliope dei "
     "Documenti. La apro?",
     [["Disdetta palestra"], ["4", "quattro"], ["Documenti"]], True),
    ("annullato", "esito", "Annulla il timer.", "Ho annullato il timer di 5 minuti.",
     [["annullat", "cancellat", "tolto"], ["timer"], ["5", "cinque"]], False),
    ("modalita", "esito", "Torna alla modalità normale.",
     "Modalità normale: torno a rispondere a «Calliope», senza i suoni di ascolto.",
     [["Calliope"], ["suon"]], False),
    ("proposta_lavoro", "proposta", "Scrivimi un programma che calcola il codice fiscale.",
     "È un lavoro di programmazione: lo affido all'agente su questo computer. Ci vorranno "
     "alcuni minuti e ti avviso quando ha finito. Procedo?",
     [["agente"], ["minut"]], True),
    ("correzione", "sviluppo", "Non funziona con Roma, fallo correggere.",
     "D'accordo: lo faccio correggere a chi l'ha scritto. Ci lavora in secondo piano; quando "
     "è pronto rifacciamo la prova con «Roma».",
     [["corregg", "corress", "correzion"], ["Roma"]], False),
    ("programma", "esito", "Esegui il programma.",
     "Il programma ha finito in 3 secondi. Risultato: 42.",
     [["3", "tre"], ["42"]], False),
    ("schermo", "esito", "Mostralo sullo schermo della cucina.",
     "Ecco, è sullo schermo della cucina.", [["schermo"], ["cucina"]], False),
    ("temperatura", "lettura", "Quanti gradi ci sono in cucina?", "In cucina ci sono 21 gradi.",
     [["cucina"], ["21"]], False),
    ("lavori_attesa", "lettura", "Qualche lavoro aspetta una mia risposta?",
     "Non ho lavori che aspettano una risposta.", [["non", "nessun"], ["rispost"]], False),
    ("permesso", "permesso", "Affida all'agente un programma per il meteo.",
     "I lavori di programmazione li può affidare solo chi amministra: chiedi a chi amministra.",
     [["amministra"]], False),
]

CODA_MSG = ("Hai appena detto a chi parla: «{f}». Aggiungi adesso SOLO una frase brevissima "
            "(al massimo 10 parole) con il tuo tono, che dia calore o colore senza aggiungere "
            "fatti: niente numeri, nomi, domande, promesse né azioni. Non ripetere la frase "
            "detta.")
RIFORMULA_MSG = ("Il risultato è pronto. Dillo adesso a chi parla con il tuo tono, in una o "
                 "due frasi brevi, usando tutti questi fatti senza cambiarli né aggiungerne: "
                 "«{f}». Tieni identici i numeri e i nomi tra «»{q}.")
FATTI_MSG = ("Dati del turno: il tool ha già risposto, e la frase pronta è «{f}». Di' a chi "
             "parla questo esito, come risposta; non aggiungere altro{q}.")

AZIONI = re.compile(r"\b(ho (fatto|acceso|spento|aperto|chiuso|mandato|inviato|salvato|"
                    r"aggiunto|creato|avviato|annullato|preparato|installato|approvato)|"
                    r"apro|accendo|spengo|avvio|faccio subito)\b", re.I)
TU = re.compile(r"\b(ti|tu|tuo|tua|tuoi|tue|puoi|vuoi|dimmi|chiedimi|chiedimelo|sai|hai)\b",
                re.I)
# Una chiamata di tool scritta come testo: con TextCallGuard il tool ripartirebbe
CHIAMATA = re.compile(r"\b[a-z]+_[a-z_]+\s*\(|```")
FRASE = re.compile(r"[.!?…](\s|$)")


def chiama(messages):
    """Una passata in streaming: testo, primo token, prima frase intera, fine (secondi)."""
    t0 = time.perf_counter()
    first = sentence = None
    out = []
    with requests.post(URL, json={"model": MODELLO, "messages": messages, "stream": True,
                                  "think": False, "keep_alive": "5m",
                                  "options": {"temperature": 0.3, "num_ctx": 8192}},
                       stream=True, timeout=120) as r:
        for line in r.iter_lines():
            if not line:
                continue
            d = json.loads(line)
            piece = (d.get("message") or {}).get("content") or ""
            if piece and first is None:
                first = time.perf_counter() - t0
            out.append(piece)
            if sentence is None and FRASE.search("".join(out)):
                sentence = time.perf_counter() - t0
            if d.get("done"):
                break
    end = time.perf_counter() - t0
    return "".join(out).strip(), first, sentence or end, end


def numeri(s):
    return set(re.findall(r"\d+", s))


def nomi(s):
    return set(re.findall(r"«([^»]*)»", s))


def controlla(modo, tono, frase, fatti, domanda, testo):
    """Esito del controllo automatico: lista di difetti (vuota = buono)."""
    dif = []
    low = testo.lower()
    if not testo:
        return ["vuoto"]
    if CHIAMATA.search(testo):
        dif.append("chiamata_scritta")
    if modo == "coda":
        if re.search(r"\d", testo):
            dif.append("numero")
        if "«" in testo:
            dif.append("nome")
        if "?" in testo:
            dif.append("domanda")
        if AZIONI.search(testo):
            dif.append("azione")
        if len(testo.split()) > 14:
            dif.append("lunga")
        if testo.lower()[:30] in frase.lower():
            dif.append("ripete")
    else:
        for alt in fatti:
            if not any(a.lower() in low for a in alt):
                dif.append("manca:" + alt[0])
        nuovi = numeri(testo) - numeri(frase)
        if nuovi:
            dif.append("numero_nuovo:" + ",".join(sorted(nuovi)))
        if nomi(testo) - nomi(frase):
            dif.append("nome_nuovo")
        if domanda and not testo.rstrip().endswith("?"):
            dif.append("domanda_persa")
        if not domanda and testo.rstrip().endswith("?"):
            dif.append("domanda_nuova")
        if AZIONI.search(testo) and not AZIONI.search(frase):
            dif.append("azione_nuova")
        if len(testo.split()) > max(30, 2 * len(frase.split())):
            dif.append("lunga")
    if tono == "formale" and TU.search(testo):
        dif.append("tu_nel_formale")
    if tono == "computer_di_bordo" and "!" in testo:
        dif.append("esclamativo")
    return dif


def main(out_path):
    cfg = Config()
    righe = []
    with open(out_path, "w", encoding="utf-8") as out:
        for tono in TONI:
            cfg.tono = tono
            system = cfg.prompt_for(biblioteca=False)
            # Riscaldamento: prefisso del prompt in cache, come in uso (non misurato)
            chiama([{"role": "system", "content": system}, {"role": "user", "content": "Ciao."}])
            for fid, classe, richiesta, frase, fatti, domanda in FRASI:
                q = ", e finisci con la stessa domanda" if domanda else ""
                for modo in ("coda", "riformula", "fatti"):
                    base = [{"role": "system", "content": system},
                            {"role": "user", "content": richiesta}]
                    if modo == "coda":
                        msgs = base + [{"role": "assistant", "content": frase},
                                       {"role": "system", "content": CODA_MSG.format(f=frase)}]
                    elif modo == "riformula":
                        msgs = base + [{"role": "system",
                                        "content": RIFORMULA_MSG.format(f=frase, q=q)}]
                    else:
                        msgs = base + [{"role": "system",
                                        "content": FATTI_MSG.format(f=frase, q=q)}]
                    testo, primo, prima_frase, fine = chiama(msgs)
                    dif = controlla(modo, tono, frase, fatti, domanda, testo)
                    r = {"id": fid, "classe": classe, "tono": tono, "modo": modo,
                         "frase": frase, "testo": testo, "difetti": dif,
                         "parole": len(testo.split()), "parole_frase": len(frase.split()),
                         "primo_s": round(primo or fine, 3),
                         "prima_frase_s": round(prima_frase, 3), "fine_s": round(fine, 3)}
                    righe.append(r)
                    out.write(json.dumps(r, ensure_ascii=False) + "\n")
                    out.flush()
                    print(f"{tono:18s} {modo:9s} {fid:18s} {fine:5.2f}s "
                          f"{'OK ' if not dif else 'KO '+','.join(dif)} | {testo[:90]}",
                          flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
