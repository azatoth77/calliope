"""
Misura per la «modalità compagnia» (09/10/2026, docs/ricerche/2026-10-09-piu-persone.md): dentro
la finestra d'ascolto (frase senza il nome) il modello giudica se la frase è rivolta a Calliope.

Manuale, non nel runner. Ollama su 127.0.0.1 con il modello dato (predefinito gemma4:e4b-it-qat).
Frasi e nomi di fantasia: 27 rivolte a Calliope (seguiti, conferme, ospite che le parla, terze
persone dentro un comando: i contrari) e 29 no (chiacchiere, Calliope in terza persona, un altro
nominato come interlocutore). Due modi: un giudizio separato con JSON e la risposta stessa con
«[silenzio]»; ciascuno con e senza l'indizio della voce («voce non registrata, diversa da Marco»).
A fine misura il modello resta caricato 5 minuti: `ollama stop <modello>`.

    .venv\\Scripts\\python prove\\misura_rivolta.py [modello]
"""

import json
import sys
import time
import urllib.request

URL = "http://127.0.0.1:11434/api/chat"
MOD = sys.argv[1] if len(sys.argv) > 1 else "gemma4:e4b-it-qat"
U, A = "Marco (registrato)", "Calliope"
G = "voce non registrata, diversa da Marco"
S_ = "stessa voce di Marco"
C = [
 # ── rivolte a Calliope ──
 ([(U, "Calliope, che tempo fa domani a Bologna?"), (A, "Domani a Bologna sole, massima ventidue gradi.")], S_, "E dopodomani?", True),
 ([(U, "Calliope, metti la sveglia alle sette."), (A, "Fatto, sveglia alle sette.")], S_, "Anzi, facciamo alle sette e mezza.", True),
 ([(U, "Calliope, aggiungi il pane alla lista della spesa."), (A, "Aggiunto il pane.")], S_, "Anche il latte.", True),
 ([(U, "Calliope, quanto fa diciotto per sette?"), (A, "Fa centoventisei.")], S_, "E diviso tre?", True),
 ([(U, "Calliope, accendi la luce in cucina."), (A, "Luce della cucina accesa.")], S_, "Spegnila tra dieci minuti.", True),
 ([(U, "Calliope, chi ha scritto I promessi sposi?"), (A, "Alessandro Manzoni.")], S_, "In che anno?", True),
 ([(U, "Calliope, ricordami di chiamare il dentista."), (A, "Quando te lo ricordo?")], S_, "Domani alle dieci.", True),
 ([(U, "Calliope, spegni la TV."), (A, "Vuoi che spenga la TV del salotto?")], S_, "Sì.", True),
 ([(U, "Calliope, raccontami una barzelletta."), (A, "Perché il libro di matematica è triste? Ha troppi problemi.")], S_, "Ahah, un'altra.", True),
 ([(U, "Calliope, com'è la strada per Verona?"), (A, "Traffico regolare, un'ora e dieci.")], S_, "Grazie.", True),
 ([(U, "Calliope, ricorda che a Giulia piace la pizza."), (A, "Me lo ricorderò.")], S_, "E che Luca è allergico alle noci.", True),
 ([(U, "Calliope, che ore sono?"), (A, "Sono le nove e un quarto.")], S_, "Manda un messaggio a Giulia: arrivo tra mezz'ora.", True),
 ([(U, "Calliope, lui è il mio amico Paolo."), (A, "Ciao Paolo, piacere!")], G, "Ciao! Ma tu sai anche le ricette?", True),
 ([(U, "Calliope, che tempo fa domani?"), (A, "Pioggia nel pomeriggio.")], G, "E a Torino invece?", True),
 ([(U, "Calliope, metti un po' di musica."), (A, "Metto la playlist rilassante.")], G, "Puoi alzare il volume?", True),
 ([(U, "Calliope, spiegami cos'è un buco nero."), (A, "È una regione dove la gravità è così forte che nemmeno la luce sfugge.")], S_, "Perché nemmeno la luce?", True),
 ([(U, "Calliope, quanto manca a Natale?"), (A, "Mancano settantasette giorni.")], S_, "Ripeti, non ho sentito.", True),
 ([(U, "Calliope, leggimi l'agenda di domani."), (A, "Domani alle nove riunione con Sara.")], S_, "Spostala alle undici.", True),
 ([(U, "Calliope, che film c'è stasera?"), (A, "Su Rai Uno c'è una commedia.")], G, "Chi sono gli attori?", True),
 ([(U, "Calliope, traduci buongiorno in inglese."), (A, "Good morning.")], S_, "E in tedesco?", True),
 # ── non rivolte a Calliope ──
 ([(U, "Calliope, che ore sono?"), (A, "Sono le dieci e mezza.")], G, "Non lo portavo in giro.", False),
 ([(U, "Calliope, che tempo fa domani?"), (A, "Sole e venti gradi.")], G, "Marco, mi passi il sale?", False),
 ([(U, "Calliope, quanto fa sette per otto?"), (A, "Fa cinquantasei.")], G, "Ma lei capisce tutto quello che dici?", False),
 ([(U, "Calliope, metti la sveglia alle sette."), (A, "Fatto.")], S_, "Paolo, dai, andiamo che è tardi.", False),
 ([(U, "Calliope, accendi la luce."), (A, "Luce accesa.")], G, "Sì sì, poi te lo racconto con calma.", False),
 ([(U, "Calliope, chi era Garibaldi?"), (A, "Un generale del Risorgimento.")], G, "Ah, quello è mio cugino, quello col cappello.", False),
 ([(U, "Calliope, che ore sono?"), (A, "Le undici.")], G, "Hai visto? Ti ha risposto subito.", False),
 ([(U, "Calliope, che tempo fa?"), (A, "Nuvoloso.")], S_, "Comunque l'ho comprata l'anno scorso, costava poco.", False),
 ([(U, "Calliope, raccontami una barzelletta."), (A, "Perché il pomodoro arrossisce? Ha visto l'insalata spogliarsi.")], G, "Questa era terribile, Marco.", False),
 ([(U, "Calliope, metti un po' di musica."), (A, "Metto un po' di jazz.")], G, "Io prendo un'altra birra, tu vuoi qualcosa?", False),
 ([(U, "Calliope, quanto dista Milano?"), (A, "Circa duecento chilometri.")], G, "Lo sai che mia sorella vive lì?", False),
 ([(U, "Calliope, che giorno è oggi?"), (A, "Oggi è venerdì nove ottobre.")], S_, "Giulia, hai preso le chiavi?", False),
 ([(U, "Calliope, che tempo fa?"), (A, "Sole.")], G, "Ma come fa a sapere che voce hai?", False),
 ([(U, "Calliope, che ore sono?"), (A, "Le otto.")], G, "No dai, non ci credo, davvero?", False),
 ([(U, "Calliope, spegni la luce."), (A, "Luce spenta.")], S_, "Aspetta, che ti faccio vedere la foto.", False),
 ([(U, "Calliope, chi ha vinto ieri?"), (A, "Ha vinto il Bologna due a uno.")], G, "Te l'avevo detto io che vincevano!", False),
 ([(U, "Calliope, che ore sono?"), (A, "Le nove.")], G, "Il cameriere non è ancora arrivato.", False),
 ([(U, "Calliope, metti il timer di dieci minuti."), (A, "Timer di dieci minuti avviato.")], G, "Senti, ma domani vieni alla partita?", False),
 ([(U, "Calliope, ricordami il compleanno di Sara."), (A, "Quando è il compleanno di Sara?")], G, "Sara chi, quella del lavoro?", False),
 ([(U, "Calliope, accendi la TV."), (A, "TV accesa.")], S_, "Mamma mia che fame che ho.", False),
 # ── casi difficili e contrari ──
 ([(U, "Calliope, metti un po' di jazz."), (A, "Metto un po' di jazz.")], S_, "Ti piace il jazz?", True),
 ([(U, "Calliope, quanto è alto il Monte Bianco?"), (A, "Quattromilaottocentocinque metri.")], S_, "Sei sicura?", True),
 ([(U, "Calliope, quanto fa nove per sette?"), (A, "Fa sessantatré.")], S_, "Brava.", True),
 ([(U, "Calliope, che ore sono a New York?"), (A, "Sono le tre del mattino.")], S_, "No, non hai capito, intendevo a Los Angeles.", True),
 ([(U, "Calliope, lei è mia sorella Sara."), (A, "Ciao Sara!")], G, "Ciao! E tu come ti chiami?", True),
 ([(U, "Calliope, che tempo fa?"), (A, "Pioggia tutto il giorno.")], G, "Allora domani porto l'ombrello. Anche dopodomani piove?", True),
 ([(U, "Calliope, dimmi una curiosità sui gatti."), (A, "I gatti dormono fino a sedici ore al giorno.")], G, "Che ne pensi dei cani?", True),
 ([(U, "Calliope, chi ha vinto il mondiale del 2006?"), (A, "L'Italia.")], G, "Sei sicuro? Io mi ricordavo la Francia.", False),
 ([(U, "Calliope, quanto fa nove per sette?"), (A, "Fa sessantatré.")], G, "Bravo, l'hai addestrata bene.", False),
 ([(U, "Calliope, che tempo fa domani?"), (A, "Sole.")], G, "Chiedile se domani piove a Rimini.", False),
 ([(U, "Calliope, metti la sveglia."), (A, "A che ora?")], G, "Dille alle sette, che domani lavoriamo.", False),
 ([(U, "Calliope, che ore sono?"), (A, "Le dieci.")], G, "Dai, chiediglielo tu che a me non risponde.", False),
 ([(U, "Calliope, che ore sono?"), (A, "Le undici e mezza.")], G, "Ok.", False),
 ([(U, "Calliope, raccontami una storia."), (A, "C'era una volta un drago che aveva paura del buio.")], G, "Che ne pensi, la facciamo sentire a tua figlia?", False),
 ([(U, "Calliope, qual è la capitale del Perù?"), (A, "Lima.")], S_, "Visto? Te l'avevo detto che era Lima.", False),
 ([(U, "Calliope, metti il timer di cinque minuti."), (A, "Timer avviato.")], G, "Quanto ci mette la pasta, Marco?", False),
]


def chiama(messages, fmt=None, num_predict=40):
    body = {"model": MOD, "messages": messages, "stream": False, "think": False,
            "options": {"temperature": 0, "num_predict": num_predict, "num_ctx": 4096},
            "keep_alive": "5m"}
    if fmt:
        body["format"] = fmt
    t0 = time.perf_counter()
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=120).read())
    return r["message"]["content"], time.perf_counter() - t0, r.get("prompt_eval_count"), r.get("eval_count")


GIUDICE = ("Sei il filtro di un'assistente vocale di casa che si chiama Calliope. Dopo una sua risposta il "
           "microfono resta aperto qualche secondo e sente anche le persone che parlano tra loro. "
           "Decidi se l'ultima frase è rivolta a Calliope (una domanda, un comando, un seguito o una "
           "risposta a ciò che ha detto lei) oppure a un'altra persona presente (chiacchiere, commenti su "
           "Calliope in terza persona, frasi che nominano un altro come interlocutore). Nel dubbio, se la "
           "frase è un seguito plausibile della conversazione con Calliope, è rivolta a lei. "
           'Rispondi solo con JSON {"per_calliope": true|false}.')
SCHEMA = {"type": "object", "properties": {"per_calliope": {"type": "boolean"}},
          "required": ["per_calliope"]}
VOCE = "Sei Calliope, assistente vocale di casa. Rispondi in italiano, in una o due frasi brevi, senza elenchi."
SIL = (" Il microfono resta aperto qualche secondo dopo le tue risposte e sente anche chi parla con "
       "altre persone. Se l'ultima frase dell'utente non è rivolta a te (chiacchiere tra persone, "
       "commenti su di te in terza persona, una frase per qualcun altro), rispondi solo «[silenzio]».")


def giudice(ctx, voce, frase, con_voce):
    righe = [f"{chi}: {t}" for chi, t in ctx]
    righe.append(f"{'Frase nuova (' + voce + ')' if con_voce else 'Frase nuova'}: {frase}")
    m = [{"role": "system", "content": GIUDICE}, {"role": "user", "content": "\n".join(righe)}]
    out, s, pe, ev = chiama(m, SCHEMA, 20)
    try:
        return bool(json.loads(out)["per_calliope"]), s, out
    except Exception:
        return None, s, out


def inline(ctx, voce, frase, con_voce):
    m = [{"role": "system", "content": VOCE + SIL}]
    for chi, t in ctx:
        m.append({"role": "assistant" if chi == A else "user", "content": t})
    m.append({"role": "user", "content": (f"[{voce}] " if con_voce else "") + frase})
    out, s, pe, ev = chiama(m, None, 40)
    return ("silenzio" not in out.lower()), s, out


def main():
    chiama([{"role": "user", "content": "ciao"}], None, 2)   # carica il modello
    for modo in ("giudice", "inline"):
        for con_voce in (False, True):
            ok = {True: [0, 0], False: [0, 0]}
            tempi, errori = [], []
            for ctx, voce, frase, atteso in C:
                f = giudice if modo == "giudice" else inline
                got, s, out = f(ctx, voce, frase, con_voce)
                tempi.append(s)
                ok[atteso][1] += 1
                if got == atteso:
                    ok[atteso][0] += 1
                else:
                    errori.append(frase)
            tempi.sort()
            print(f"{modo:7s} voce={'si' if con_voce else 'no'}: rivolte giuste {ok[True][0]}/{ok[True][1]}, "
                  f"non rivolte giuste {ok[False][0]}/{ok[False][1]}; tempo mediano "
                  f"{1000 * tempi[len(tempi) // 2]:.0f} ms, p90 {1000 * tempi[int(.9 * len(tempi))]:.0f} ms",
                  flush=True)
            print("   sbagliate:", errori, flush=True)


if __name__ == "__main__":
    main()
