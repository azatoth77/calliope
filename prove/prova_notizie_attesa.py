import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dell'attesa delle notizie (17/10, issue #132): col 26B la voce delle notizie
partiva a 2,91 s di mediana (fino a 4,3), perché `notizie` non aveva la frase d'attesa e la
risposta arrivava in una frase sola, coi fatti uniti dal «;», tenuta intera fino all'ultimo
token. Testate, luoghi e nomi di fantasia.

1. Il taglio al «; » (testi.taglio_voce, tts.split_sentences): una frase di 600 caratteri con
   tre «; » e senza punti, data a token, esce a pezzi prima dell'ultimo token; uguale tutta in
   una volta. Contrari: frase di 100 caratteri con un «;», frase normale col punto, «3;4» e
   «3; 4», il «;» fra virgolette e in parentesi, un elenco breve, la virgola mai,
   `tts_spezza_streaming` 0; la regola `taglio_punto_e_virgola` solo per i tagli al «;».
2. Brain: la stessa risposta dopo `notizie` passa dalle reti (ClaimHold, FraseTolta) senza
   restare trattenuta fino alla fine; contrario: una dichiarazione d'azione falsa nel primo
   pezzo si trattiene ancora.
3. La frase d'attesa di `notizie`: detta una volta, diversa da quelle di web_cerca; con
   l'annuncio detto il tool non riceve `ctx.attesa` (la frase dello scarico non si somma);
   contrari: con una frase già detta niente annuncio, senza `announce` il tool riceve
   `ctx.attesa` come prima.
4. Il testo per il modello chiede frasi chiuse dal punto.
5. La prima voce per tool in `calliope stato --turni` (latenza.per_tool), con le risposte
   lunghe in un pezzo solo (`frasi_voce`).
"""

import json
import re

from calliope import latenza
from calliope.brain import Brain, ClaimHold, FraseTolta, SCRIVO_QUI
from calliope.config import Config
from calliope.testi import PAUSA_OLTRE, taglio_voce
from calliope.tools import notizie as tool_notizie
from calliope.tools.builtin import build_registry
from calliope.tools.spec import ToolContext
from calliope.tts import split_sentences

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if ok:
        print(f"  ok  {nome}")
    else:
        errori += 1
        print(f"  ERRORE  {nome}" + (f"\n        {dettaglio}" if dettaglio else ""))


def token(testo: str) -> list[str]:
    """Il testo a pezzi come lo dà il modello: una parola con lo spazio dopo."""
    return re.findall(r"\S+\s*", testo)


# Una risposta di ~600 caratteri senza punti, coi fatti uniti da tre «; » (la forma vera del
# 16/10, nomi di fantasia)
LUNGA = ("Secondo la Gazzetta di Borgo Lieto oggi riapre il ponte sul fiume Arvo dopo due anni "
         "di lavori e molte proteste dei residenti del quartiere vecchio; un'altra testata, il "
         "Corriere di Valfiorita, scrive che il sindaco ha promesso un nuovo parcheggio vicino "
         "alla stazione entro la prossima primavera e che i lavori partiranno a gennaio; una "
         "terza aggiunge che la festa del paese si terrà comunque nella piazza grande come ogni "
         "anno, anche se le previsioni danno pioggia per tutto il fine settimana; infine Radio "
         "Monteverde riporta che la squadra locale ha vinto la partita di domenica per tre a "
         "uno davanti a duemila persone")
assert 560 <= len(LUNGA) <= 660 and LUNGA.count("; ") == 3 and "." not in LUNGA, len(LUNGA)

# ─────────────────────────── 1. il taglio al «; » ───────────────────────────
print("1. taglio al «; »")
tok = token(LUNGA)
visti = {"n": 0}


def flusso(pezzi):
    for p in pezzi:
        visti["n"] += 1
        yield p


uscite, primo_a = [], None
for f in split_sentences(flusso(tok)):
    if primo_a is None:
        primo_a = visti["n"]
    uscite.append(f)
verifica("600 caratteri con tre «; » e senza punto: il primo pezzo esce prima dell'ultimo "
         "token", primo_a is not None and primo_a < len(tok) // 3,
         f"primo pezzo al token {primo_a} di {len(tok)}")
verifica("... quattro pezzi, ognuno finito al «;» (la punteggiatura resta nel pezzo)",
         len(uscite) == 4 and all(u.endswith(";") for u in uscite[:3]), str(uscite))
verifica("... il testo resta uguale", " ".join(uscite) == LUNGA)
verifica("... tutta in una volta si taglia negli stessi punti (la storia come detta)",
         list(split_sentences([LUNGA])) == uscite)
verifica("... a pezzi di tre caratteri, uguale", list(split_sentences(
    [LUNGA[i:i + 3] for i in range(0, len(LUNGA), 3)])) == uscite)

cento = ("Il mercato di Borgo Lieto apre alle otto di mattina; quello di Valfiorita apre alle "
         "nove e mezza.")
verifica("contrario: una frase di 100 caratteri con un «;» non si taglia",
         len(cento) < PAUSA_OLTRE and list(split_sentences(token(cento))) == [cento])
normali = ("Secondo la Gazzetta di Borgo Lieto riapre il ponte sul fiume. Il sindaco promette un "
           "parcheggio nuovo. ")
verifica("contrario: frasi normali col punto escono come prima",
         list(split_sentences(token(normali))) == ["Secondo la Gazzetta di Borgo Lieto riapre "
                                                   "il ponte sul fiume.",
                                                   "Il sindaco promette un parcheggio nuovo."])
virgole = ("La squadra di Borgo Lieto ha vinto in casa, davanti a duemila persone, con due gol "
           "nel primo tempo, uno nel secondo, e una parata decisiva del portiere all'ultimo "
           "minuto, quando ormai tutti pensavano al pareggio")
verifica("contrario: la virgola non taglia mai, anche in una frase lunga",
         len(virgole) > PAUSA_OLTRE and list(split_sentences(token(virgole))) == [virgole])
numeri = ("Nella classifica del torneo di Valfiorita la squadra di casa ha i punteggi 3;4 e 5;6 "
          "nelle ultime due giornate, e la partita di ritorno finirà forse 3; 4 come l'andata "
          "di settembre secondo i giornali")
verifica("contrario: «3;4» e «3; 4» non contano",
         len(numeri) > PAUSA_OLTRE and list(split_sentences(token(numeri))) == [numeri])
citazione = ("Il sindaco ha detto «riapriremo il ponte sul fiume Arvo entro la fine del mese; "
             "poi toccherà al parcheggio della stazione vecchia» e poi è andato via senza "
             "rispondere alle domande dei giornalisti")
verifica("contrario: il «;» dentro le virgolette non conta",
         list(split_sentences(token(citazione))) == [citazione])
parentesi = ("La festa del paese (spostata in piazza grande per i lavori della scuola elementare; "
             "lo dice il comune) si terrà comunque domenica pomeriggio con la banda e i fuochi "
             "d'artificio della sera")
verifica("contrario: il «;» dentro la parentesi non conta",
         list(split_sentences(token(parentesi))) == [parentesi])
elenco = ("Per la torta della festa di Borgo Lieto servono queste cose: farina; uova; latte; "
          "zucchero; burro; lievito; vaniglia; sale; un limone; cannella; miele di castagno")
verifica("contrario: un elenco breve unito dal «;» non si spezza",
         len(elenco) > PAUSA_OLTRE and list(split_sentences(token(elenco))) == [elenco])
elenco2 = ("Ho comprato farina; uova; latte; zucchero; burro; lievito; vaniglia; sale; un limone; "
           "cannella; miele di castagno; noci; mandorle; pinoli; uvetta; cioccolato fondente")
verifica("contrario: ... anche senza i due punti davanti",
         len(elenco2) > PAUSA_OLTRE and list(split_sentences(token(elenco2))) == [elenco2])
verifica("contrario: tts_spezza_streaming 0, la frase intera come prima",
         list(split_sentences(token(LUNGA), pausa_oltre=0)) == [LUNGA])
regole = []
list(split_sentences(token(LUNGA), al_taglio=lambda: regole.append(1)))
verifica("la regola: un taglio al «;» per pezzo tagliato così", len(regole) == 3, str(regole))
regole = []
list(split_sentences(token(normali + cento), al_taglio=lambda: regole.append(1)))
verifica("contrario: nessuna regola per i tagli a fine frase", regole == [])
verifica("taglio_voce: (fine, False) per la fine della frase, None se manca",
         taglio_voce("Una frase abbastanza lunga da contare. E poi") == (39, False)
         and taglio_voce("Una frase senza fine ancora") is None)

# ─────────────────────────── 2. le reti di Brain ───────────────────────────
print("2. reti di Brain")
hold = ClaimHold(True, ["ricorda"])
fuori, primo_h = [], None
for i, p in enumerate(tok):
    o = hold.feed(p)
    if o and primo_h is None:
        primo_h = i + 1
    fuori.append(o)
fuori.append(hold.flush())
verifica("ClaimHold: la risposta unita dai «;» non resta trattenuta fino alla fine",
         primo_h is not None and primo_h < len(tok) // 3 and "".join(fuori) == LUNGA,
         f"rilasciata al token {primo_h} di {len(tok)}")
falsa = ("Ho salvato nella memoria che il ponte di Borgo Lieto riapre oggi dopo due anni di "
         "lavori e proteste; e che il sindaco ha promesso un parcheggio vicino alla stazione "
         "entro la prossima primavera")
hold = ClaimHold(True, ["ricorda"])
fuori = "".join(hold.feed(p) for p in token(falsa)) + hold.flush()
verifica("contrario ClaimHold: la dichiarazione d'azione falsa nel primo pezzo si trattiene",
         fuori == "" and hold.kind == "claim", f"{fuori!r} {hold.kind}")
qui = FraseTolta(SCRIVO_QUI, True)
fuori, primo_q = [], None
for i, p in enumerate(tok):
    o = qui.feed(p)
    if o and primo_q is None:
        primo_q = i + 1
    fuori.append(o)
fuori.append(qui.flush())
verifica("FraseTolta: la risposta unita dai «;» esce a pezzi",
         primo_q is not None and primo_q < len(tok) // 3 and "".join(fuori) == LUNGA,
         f"rilasciata al token {primo_q} di {len(tok)}")

# ─────────────────────────── 3. la frase d'attesa ───────────────────────────
print("3. frase d'attesa")
cfg = Config()
cfg.web_searxng_url = ""
reg = build_registry(web=cfg, notizie=cfg)
spec_n, spec_w = reg.get("notizie"), reg.get("web_cerca")
verifica("notizie ha la frase d'attesa, diversa da quelle di web_cerca",
         spec_n.announce and not set(spec_n.announce) & set(spec_w.announce or ()),
         str(spec_n.announce))
viste = []


def notizie_finto(ctx, **kw):
    viste.append(getattr(ctx, "attesa", None))
    a = getattr(ctx, "attesa", None)
    if a is not None:
        a("Un attimo, guardo i giornali.")          # lo scarico lento di Notizie.prepara
    return {"ok": True, "trovato": True, "attenzione": tool_notizie.AVVISO,
            "fatti": [{"n": 1, "titolo": "Riapre il ponte sul fiume Arvo",
                       "testate": ["Gazzetta di Borgo Lieto"], "quando": "stamattina"}],
            "cosa_fare": tool_notizie.COSA_FARE}


spec_n.func = notizie_finto


class SpeakerCtx:
    current_speaker, current_level, from_session = "Lucia", "familiare", False
    profile_level, identified_by = "familiare", "voce"


class BackendFinto:
    def __init__(self, copione):
        self.copione = list(copione)

    def stream(self, messages, tools):
        yield from self.copione.pop(0)


def brain(copione):
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, reg, []
    b.tool_ctx = ToolContext(cfg=cfg, speakers=None, speaker_ctx=SpeakerCtx(), speaker=None)
    b.backend = BackendFinto(copione)
    b.on_tool_start = None
    return b


def chiama(i=0):
    return {"id": f"call_{i}", "name": "notizie", "arguments": {}}


visti["n"] = 0
b = brain([[("calls", [chiama()])], flusso([("text", t) for t in tok])])
attese = []
b.on_tool_start = attese.append
dette, primo_b = [], None
for f in split_sentences(b.stream_reply("Che notizie ci sono?", "familiare")):
    if primo_b is None:
        primo_b = visti["n"]
    dette.append(f)
verifica("brain: la frase d'attesa di notizie detta una volta", len(attese) == 1
         and attese[0] in tool_notizie.ANNUNCI, str(attese))
verifica("brain: con l'annuncio detto il tool non riceve ctx.attesa (lo scarico non si somma)",
         viste == [None], str(viste))
verifica("brain: dopo notizie la risposta unita dai «;» va alla voce a pezzi, il primo prima "
         "dell'ultimo token", len(dette) == 4 and " ".join(dette) == LUNGA
         and primo_b < len(tok) // 3, f"primo pezzo al token {primo_b} di {len(tok)}: "
         f"{str(dette)[:300]}")
viste.clear()
b = brain([[("text", "Certo, guardo subito i giornali di oggi per te. "),
            ("calls", [chiama()])], [("text", "Riapre il ponte sul fiume Arvo.")]])
attese = []
b.on_tool_start = attese.append
"".join(b.stream_reply("Che notizie ci sono?", "familiare"))
verifica("contrario: una risposta che ha già detto una frase non annuncia", attese == [],
         str(attese))
viste.clear()
annunci, spec_n.announce = spec_n.announce, ()
b = brain([[("calls", [chiama()])], [("text", "Riapre il ponte sul fiume Arvo.")]])
attese = []
b.on_tool_start = attese.append
"".join(b.stream_reply("Che notizie ci sono?", "familiare"))
spec_n.announce = annunci
verifica("contrario: senza announce il tool riceve ctx.attesa e la frase dello scarico è "
         "l'unica (com'era prima)", viste and viste[0] is not None
         and attese == ["Un attimo, guardo i giornali."], f"{viste} {attese}")

# ─────────────────────────── 4. il testo per il modello ───────────────────────────
print("4. testo per il modello")
verifica("COSA_FARE: una frase per fatto chiusa dal punto, non unita dal punto e virgola",
         "chiusa dal punto" in tool_notizie.COSA_FARE
         and "punto e virgola" in tool_notizie.COSA_FARE)
verifica("tts_spezza_streaming di serie a 120, come PAUSA_OLTRE",
         Config().tts_spezza_streaming == PAUSA_OLTRE == 120)

# ─────────────────────────── 5. la prima voce per tool ───────────────────────────
print("5. prima voce per tool")


def turno(tool, voce, risposta="Va bene.", frasi=1):
    return {"inizio": "2026-10-17T10:00:00", "prima_frase_s": 1.0, "prima_voce_s": voce,
            "tool": [{"nome": n, "ok": True} for n in tool], "risposta": risposta,
            "frasi_voce": frasi}


turni = ([turno(["notizie"], v) for v in (2.5, 2.9, 3.0, 4.3)]
         + [turno(["notizie"], 3.7, "x" * 476, 1), turno(["notizie"], 1.4, "y" * 476, 4)]
         + [turno(["web_cerca"], v) for v in (1.1, 1.6, 3.1)]
         + [turno(["web_cerca", "notizie"], 1.5)]
         + [{"inizio": "2026-10-17T10:00:00", "prima_frase_s": 1.0,
             "tool": [{"nome": "notizie"}]},                     # senza la misura della voce
            {"inizio": "2026-10-17T10:00:00", "prima_frase_s": 0.9, "prima_voce_s": 1.0,
             "tool": []}])
r = latenza.per_tool(turni)
verifica("per_tool: notizie 7 turni, mediana e p90 della prima voce",
         r["notizie"]["turni"] == 7 and r["notizie"]["mediana"] == 2.9
         and r["notizie"]["p90"] == 4.3, json.dumps(r))
verifica("per_tool: le risposte lunghe in un pezzo solo (476 caratteri con 1 pezzo sì, con 4 "
         "no)", r["notizie"]["lunghe_un_pezzo"] == 1)
verifica("per_tool: web_cerca 4 turni (un turno con due tool conta per entrambi), il più "
         "chiamato prima", r["web_cerca"]["turni"] == 4 and list(r) == ["notizie", "web_cerca"])
verifica("contrario: i turni senza tool o senza la misura della voce non contano",
         sum(d["turni"] for d in r.values()) == 11)
riga = latenza.testo_per_tool(r)
verifica("la riga di stato --turni", riga.startswith("Prima voce sentita per tool: notizie 7 "
                                                     "turni, 2,90 s (p90 4,30 s), 1 lunghe")
         and "web_cerca 4 turni" in riga, riga)
verifica("contrario: senza turni con un tool la riga lo dice",
         "nessun turno" in latenza.testo_per_tool(latenza.per_tool([])))

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
