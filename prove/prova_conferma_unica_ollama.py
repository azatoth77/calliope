import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""Una conferma per azione con il modello vero (06/10/2026): gemma4 e4b sull'Ollama di questo
PC, la sequenza della DGX delle 17:30–17:34 (prova_conferma_unica.py è la stessa a secco).

Per ogni giro:

1. una foto mandata dal telefono con «Vedi?»;
2. «Creiamo un'estensione che prende due parametri e li somma», poi a ogni domanda il «sì» con
   la voce («Sì procedi pure.»; alla frase di sfida, le parole): si contano le domande fino
   all'avvio e quale tool è partito (sviluppo_apri, non lavoro_affida);
3. l'annuncio di un lavoro di codice finito con la dimostrazione fermata (come sulla DGX) e
   «Come posso richiamare questa estensione?»: la risposta non deve inventare un comando a voce
   di un'estensione che non c'è.

Servizio dei lavori finto (nessun agente), tool veri. Mai l'Ollama della DGX.

    python prove\\prova_conferma_unica_ollama.py [giri]       # 1 giro: ~1 minuto
"""

import re
import time
from types import SimpleNamespace

from calliope.agenti import servizio as srv
from calliope.brain import make_backend
from calliope.immagini import Immagine, prepara as prepara_foto
from prove import immagini_finte as F
from prove.prova_conferma_unica import COD, DETTA, prepara_dgx
from prove.prova_politica import turno

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
ERRORI = []


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  {dettaglio}" if dettaglio else ""), flush=True)
    if not ok:
        ERRORI.append(nome)


def foto():
    big = F.foto()
    jpeg, w, h = prepara_foto(F.jpeg(big), 1280)
    return Immagine(jpeg, w, h, fonte="telefono", persona="dario")


ROMANI = "Creiamo un'estensione che converte i numeri romani in numeri arabi"


def richiesta(n, frase, doppione: bool):
    """Foto, poi la richiesta a voce; a ogni domanda la risposta di chi vuole l'estensione.
    Le domande del codice (politica, «Procedo?» del tool, sfida, «lo so già fare») al più una;
    quelle del modello («come la chiamo?») a parte."""
    b, svc = prepara_dgx(foto=False)
    b.backend = make_backend(b.cfg)
    t0 = time.perf_counter()
    r0 = "".join(b.stream_reply("Vedi?", "amministra", immagini=[foto()]))
    print(f"   [giro {n}] Vedi? → {r0[:120]}", flush=True)
    r = "".join(b.stream_reply(frase, "amministra"))
    print(f"   [giro {n}] {frase} → {r}", flush=True)
    domande, del_modello, chiamati = 0, 0, [t["nome"] for t in b.last_tools]
    gia = "lo so già fare" in r.lower()
    for _ in range(5):
        if svc.avviati or not (r.rstrip().endswith("?") or "ripeti" in r.lower()):
            break
        sc = b.tool_ctx.speaker_ctx
        codice = ("C'è di mezzo" in r or "Procedo?" in r or "ripeti" in r.lower()
                  or "Non me l'hai chiesto" in r or "lo so già fare" in r.lower())
        domande += codice
        del_modello += not codice
        if getattr(sc, "sfida", None) is not None and "ripeti" in r.lower():
            risposta = sc.sfida.testo.replace(",", "")
        elif "lo so già fare" in r.lower():
            risposta = "Sì, la voglio comunque."
        elif codice:
            risposta = "Sì procedi pure."
        else:
            risposta = "Chiamala come vuoi, va bene così. Sì, procedi pure."
        r = "".join(b.stream_reply(risposta, "amministra"))
        chiamati += [t["nome"] for t in b.last_tools]
        print(f"   [giro {n}] {risposta} → {r}", flush=True)
    tipo = svc.avviati[0].tipo if svc.avviati else None
    verifica(f"giro {n} «{frase[:40]}…»: parte dopo al più una domanda del codice (codice "
             f"{domande}, modello {del_modello}, tool {chiamati})",
             bool(svc.avviati) and domande <= 1)
    verifica(f"giro {n} «{frase[:40]}…»: è un'estensione, non un lavoro di codice",
             tipo == "estensione", f"tipo={tipo}")
    if doppione:
        verifica(f"giro {n}: somma di due numeri → «lo so già fare» (c'è calcola)", gia)
    else:
        verifica(f"giro {n}: numeri romani → nessun «lo so già fare»", not gia)
    regole = [x for x in b.rules_fired() if x.startswith(("politica_", "immagine_",
                                                           "lavori_conferma", "estensione_"))]
    print(f"   [giro {n}] regole: {regole}  ({time.perf_counter() - t0:.1f} s)", flush=True)
    return b


def giro(n):
    b = richiesta(n, DETTA, True)
    richiesta(n, ROMANI, False)

    # 3. L'annuncio della DGX (lavoro di codice, dimostrazione fermata) e «come la richiamo?»
    b2, svc2 = prepara_dgx(foto=False)
    b2.backend = b.backend
    lav = svc2.nuovo("codice", COD["compito"], "dario", "Dario", "amministra")
    lav.stato, lav.input = "fatto", []
    lav.risultato = {"riassunto": "Ho creato un'estensione in Python che prende due parametri "
                                  "numerici e ne restituisce la somma. Il programma funziona "
                                  "correttamente e tutti i test passano.",
                     "test": {"eseguiti": 6}, "test_passano": True,
                     "file": ["estensione_somma.py"],
                     "dimostrazione": "Il programma si è fermato con un errore (codice 1): «Uso: "
                                      "estensione_somma.py a b».",
                     "dimostrazione_esito": "errore"}
    finto = object.__new__(srv.Lavori)
    finto.female = True
    annuncio = "Dario, " + srv.Lavori.frase_finale(finto, lav)
    print(f"   [giro {n}] annuncio: {annuncio}", flush=True)
    # (fuori dalle virgolette: l'uscita del programma può avere il nome del file)
    detto = re.sub(r"«[^»]*»", "", annuncio)
    verifica(f"giro {n}: l'annuncio non chiama il programma estensione né dice «funziona»",
             "un'estensione di calliope" in detto.lower() and "funziona" not in detto
             and "programma" in detto)
    b2.record_announcement(annuncio, fonte="agente")
    r3 = "".join(b2.stream_reply("Come posso richiamare questa estensione?", "amministra"))
    print(f"   [giro {n}] Come posso richiamare questa estensione? → {r3}", flush=True)
    inventa = bool(re.search(r"(estension\w*|comando vocale)\s+(\w+\s+){0,2}"
                             r"(somma\w*|«)", r3, re.I)) or "est_" in r3
    verifica(f"giro {n}: «come la richiamo?» senza un comando inventato", not inventa
             and ("eseguil" in r3.lower() or "programma" in r3.lower()), r3[:160])
    avvelenata(n)


# La storia della DGX dopo il rifiuto sbagliato delle 17:32 (com'era prima della correzione):
# il rifiuto della guardia e un «non posso» di Calliope
VELENO = [
    {"role": "user", "content": DETTA},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "name": "sviluppo_apri", "arguments": {"compito": "sommare due numeri"}}]},
    {"role": "tool", "tool_call_id": "c1", "name": "sviluppo_apri", "content":
        '{"ok": false, "fatto": "NIENTE: l\'azione NON è stata eseguita", "errore": "la '
        'persona non ha chiesto azioni: la foto o il file sono solo dati da leggere"}'},
    {"role": "assistant", "content": "Mi dispiace, non posso creare direttamente "
                                     "un'estensione: posso solo spiegarti come funzionano."},
]
COTTURE = ("Creiamo una nuova estensione che ci possa aiutare a tenere traccia di tutte le mie "
           "cotture, crea una scheda interessante")
INSISTE = "Io voglio che sia un'estensione."


def avvelenata(n):
    """(a, b) La richiesta nuova con il rifiuto vecchio nella storia: sviluppo_apri arriva
    (subito o con la spinta_rinuncia), al più dopo l'insistenza. (c) Il riassunto di quella
    conversazione non dice che Calliope non sa creare estensioni."""
    b, svc = prepara_dgx(foto=False)
    b.backend = make_backend(b.cfg)
    b.history.extend(dict(m) for m in VELENO)
    r = "".join(b.stream_reply(COTTURE, "amministra"))
    chiamato = "sviluppo_apri" in [t["nome"] for t in b.last_tools]
    spinta = "spinta_rinuncia" in b.rules_fired()
    print(f"   [giro {n}] storia avvelenata: {COTTURE[:50]}… → {r[:140]}  "
          f"(spinta: {spinta})", flush=True)
    if not chiamato:
        r = "".join(b.stream_reply(INSISTE, "amministra"))
        chiamato = "sviluppo_apri" in [t["nome"] for t in b.last_tools]
        print(f"   [giro {n}] {INSISTE} → {r[:140]}", flush=True)
    # Il veleno è il «non posso» detto di nuovo; chiedere i dettagli della scheda è lecito
    rinuncia = bool(re.search(r"non (posso|riesco|è possibile|sono in grado)[^.;]{0,60}"
                              r"estension|non mi (permette|consente)", r, re.I))
    verifica(f"giro {n}: storia avvelenata → nessun «non posso» (tool: {chiamato})",
             not rinuncia, r[:120])
    from calliope import compressione as cp
    # Come in Calliope: il modello della voce con le sue opzioni (num_ctx: senza, Ollama
    # dovrebbe ricaricarlo e risponde 503)
    riass = cp._voce(b.cfg, 400)
    lav = cp.Lavoro(None, "chiusura", None, list(VELENO) + [
        {"role": "user", "content": "Va bene, ne parliamo dopo."},
        {"role": "assistant", "content": "D'accordo, a dopo."}], None, None, "Dario", None,
        None)
    for prova in range(5):           # l'Ollama di questo PC può essere occupato da altre prove
        try:
            testo = cp.testo_riassunto(riass.riassumi(lav)["dati"], "Dario")
            break
        except Exception as e:  # noqa: BLE001
            print(f"   [giro {n}] riassunto: {e}; riprovo", flush=True)
            time.sleep(5)
    else:
        verifica(f"giro {n}: riassunto fatto", False)
        return
    limite = re.search(r"non (può|posso|riesce|è in grado|sa)\w*[^.;]{0,50}estension", testo,
                       re.I)
    print(f"   [giro {n}] riassunto: {testo[:300]}", flush=True)
    verifica(f"giro {n}: il riassunto non porta avanti «non posso creare estensioni»",
             not limite, limite[0] if limite else "")


if __name__ == "__main__":
    for g in range(1, GIRI + 1):
        giro(g)
    print(f"\n{len(ERRORI)} errori: {ERRORI}" if ERRORI else "\nnessun errore")
    sys.exit(1 if ERRORI else 0)
