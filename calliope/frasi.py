"""
Frasi pronte meno monotone (12/10/2026, fasi 0 e 1 di docs/ricerche/2026-10-08-frasi-pronte.md;
roadmap V3).

Una risposta su quattro è una frase scritta nel codice, sempre uguale: tra le ultime 20
risposte alla stessa persona nello stesso giorno una frase pronta si ripete 20,5 volte ogni 100,
una risposta del modello 2,2. Qui:

- **il catalogo** (`CATALOGO`): le frasi più dette per id (`lavori.avviato`, `cortesia.grazie`…),
  con la forma di oggi (`base`), le varianti per tono (i 6 di `config.TONI`, col «lei» nel
  formale) e una forma breve per la seconda volta. Le varianti hanno gli stessi segnaposto della
  base e la stessa domanda in fondo («Procedo?» resta «Procedo?»); la forma breve tiene almeno i
  segnaposto `fissi` (i fatti su cui la persona decide). Le classi bloccate (sfida, permessi,
  politica fino alla fase 2, ripieghi, annunci con numeri e versioni) ci sono **solo per la
  misura**: nessuna variante (`prova_frasi`);
- **la scelta** (`Frasi.scegli`): col tono di chi parla o della casa, a rotazione per persona
  (con almeno tre varianti mai una delle ultime due dette a lei), e la forma breve se lo stesso
  id le è stato detto negli ultimi `frasi_breve_turni` turni (e nell'ultima ora). Latenza zero:
  niente modello, solo testo;
- **tre modi** (`frasi_varianti`): «spento» dice la base e scrive solo l'id; «ombra» (il
  predefinito) dice la base e scrive nel registro dei turni anche la variante che avrebbe scelto
  (`pronte[].ombra`), così le prove che leggono i testi esatti non cambiano e la misura stima
  già l'effetto; «attivo» dice la variante. Si accende a mano nel file locale **dopo** che chi
  amministra ha riletto un campione di 30 varianti: `python -m calliope.frasi --campione`;
- **la misura** (fase 0): l'id di ogni frase pronta passa dall'uscita unica
  (`eventi/uscita.Uscita.di` chiama `Frasi.detta`): le frasi scelte qui per testo, le altre del
  catalogo (politica, sfida…) per modello; nel registro dei turni il campo `pronte` (id, tono,
  variante, breve, ombra: mai parole). In `calliope stato --turni` le ripetizioni ogni 100
  risposte per frasi pronte e modello (`riassunto`, `testo`), con la stima della variante in
  ombra. Riferimento dell'08/10: 20,5 / 2,2 / 7,4; obiettivo dopo la fase 1: pronte sotto 8.

Profilo ridotto da 8 GB (decisione 0028): uguale. Nessun modello, nessuna memoria della GPU,
pochi kB di testo; la memoria per persona sta in RAM (al più `PERSONE_MAX` persone).

Solo libreria standard.
"""
from __future__ import annotations

import collections
import dataclasses
import datetime
import random
import re
import string
import sys
import threading
import time

TONI_FRASI = ("normale", "formale", "amichevole", "ironico", "essenziale", "computer_di_bordo")
MODI = ("spento", "ombra", "attivo")
BREVE_S = 3600.0          # la forma breve solo se l'ultima volta è stata nell'ultima ora
PERSONE_MAX = 200         # memoria per persona: oltre, si dimentica la più vecchia
SCELTE_MAX = 200          # scelte non ancora dette (un risultato scartato non resta per sempre)
FINESTRA = 20             # ripetizione: uguale a una delle ultime 20 risposte alla persona
OBIETTIVO = 8.0           # ripetizioni ogni 100 frasi pronte dopo la fase 1 (roadmap V3)

# Classi che non cambiano mai parola (§ 2 della ricerca): solo misura
CLASSI_BLOCCATE = frozenset({"sfida", "permesso", "politica", "ripiego", "annuncio"})


@dataclasses.dataclass(frozen=True)
class Voce:
    """Una frase pronta del catalogo."""
    id: str
    classe: str
    base: str | None                       # la forma di oggi (None: la decide chi chiama)
    toni: dict = dataclasses.field(default_factory=dict)    # tono → varianti
    breve: dict = dataclasses.field(default_factory=dict)   # tono → forme brevi
    fissi: tuple = ()                      # segnaposto che anche la forma breve deve avere
    domanda: str | None = None             # la domanda in fondo, identica in ogni forma
    esempio: dict = dataclasses.field(default_factory=dict)  # valori di fantasia (campione)

    @property
    def bloccata(self) -> bool:
        return self.classe in CLASSI_BLOCCATE

    def forme(self, tono: str, breve: bool = False) -> tuple:
        """Le varianti (o le forme brevi) di un tono. Senza varianti per quel tono: la base,
        e nessuna forma breve (mai il «tu» di un altro tono nel formale)."""
        d = self.breve if breve else self.toni
        if tono in d:
            return tuple(d[tono])
        if breve:
            return ()
        return (self.base,) if self.base else ()


def segnaposto(modello: str) -> set:
    """I nomi tra graffe di un modello («{titolo}»)."""
    return {n for _, n, _, _ in string.Formatter().parse(modello or "") if n}


# ─────────────────────────── il catalogo ───────────────────────────
# Le varianti le ha scritte un agente il 12/10; chi amministra ne rilegge un campione di 30
# prima di `frasi_varianti: attivo` (roadmap V3). La base è il testo di oggi, parola per parola.
_C: list[Voce] = []


def _v(*a, **k):
    _C.append(Voce(*a, **k))


_v("lavori.avviato", "avvio",
   "Ci lavoro in secondo piano: ti avviso quando è pronto. Intanto puoi chiedermi altro.",
   toni={
       "normale": (
           "Ci lavoro in secondo piano: ti avviso quando è pronto. Intanto puoi chiedermi altro.",
           "Me ne occupo in secondo piano e ti avviso quando è pronto. Nel frattempo puoi "
           "chiedermi altro.",
           "Lo preparo in secondo piano: quando è pronto te lo dico. Intanto chiedimi pure "
           "altro."),
       "formale": (
           "Me ne occupo in secondo piano e la avviso quando è pronto. Nel frattempo può "
           "chiedermi altro.",
           "Ci lavoro in secondo piano: la informo quando è pronto. Intanto può chiedermi altro.",
           "Lo preparo in secondo piano e la avviso appena è pronto. Se desidera, nel frattempo "
           "può chiedermi altro."),
       "amichevole": (
           "Ci penso io, in secondo piano: ti avviso quando è pronto. Intanto chiedimi pure "
           "quello che vuoi.",
           "Me ne occupo in secondo piano e ti avviso quando è pronto. Nel frattempo, se ti "
           "serve altro, sono qui.",
           "Lo preparo in secondo piano: appena è pronto ti avviso. Intanto, se ti serve altro, "
           "chiedi pure."),
       "ironico": (
           "Ci lavoro in secondo piano, senza fare rumore: ti avviso quando è pronto. Intanto "
           "puoi chiedermi altro.",
           "Me ne occupo in secondo piano: so fare due cose insieme. Ti avviso quando è pronto.",
           "Lo preparo in secondo piano e ti avviso quando è pronto. Nel frattempo sono libera "
           "per altro, o quasi."),
       "essenziale": (
           "Ci lavoro in secondo piano: ti avviso quando è pronto.",
           "In secondo piano. Ti avviso quando è pronto."),
       "computer_di_bordo": (
           "Elaborazione in secondo piano. Notifica al termine.",
           "In lavorazione in secondo piano. Avviso al completamento."),
   },
   # Le forme brevi (riviste il 12/10 sera) devono essere vere anche alla prima ripetizione,
   # con qualunque cosa sia successa nel frattempo: qui «anche questo» è vero (è un altro lavoro)
   breve={
       "normale": ("Ci lavoro, ti avviso.", "Anche questo in secondo piano: ti avviso."),
       "formale": ("Me ne occupo, la avviso.", "Anche questo in secondo piano: la avviso."),
       "amichevole": ("Ci penso io, ti avviso.", "Anche questo in secondo piano, ti avviso."),
       "ironico": ("Un altro in secondo piano: ti avviso.", "Ci lavoro, ti avviso."),
       "essenziale": ("In secondo piano. Ti avviso.",),
       "computer_di_bordo": ("In lavorazione. Notifica al termine.",),
   })

_v("lavori.in_coda", "avvio",
   "D'accordo: lo metto in coda dopo «{titolo}». Ti avviso quando è pronto.",
   fissi=("titolo",), esempio={"titolo": "la relazione sui pannelli"},
   toni={
       "normale": (
           "D'accordo: lo metto in coda dopo «{titolo}». Ti avviso quando è pronto.",
           "Va bene: lo metto in coda dopo «{titolo}» e ti avviso quando è pronto.",
           "D'accordo, viene dopo «{titolo}»: ti avviso quando è pronto."),
       "formale": (
           "D'accordo: lo metto in coda dopo «{titolo}». La avviso quando è pronto.",
           "Certamente: viene dopo «{titolo}», e la informo quando è pronto."),
       "amichevole": (
           "Va bene! Lo metto in coda dopo «{titolo}» e ti avviso quando è pronto.",
           "D'accordo: prima si finisce «{titolo}», poi tocca a questo. Ti avviso io."),
       "ironico": (
           "D'accordo: si mette in fila dopo «{titolo}», come alle poste. Ti avviso quando è "
           "pronto.",
           "Va bene: lo metto in coda dopo «{titolo}». Ti avviso quando è pronto."),
       "essenziale": ("In coda dopo «{titolo}». Ti avviso quando è pronto.",),
       "computer_di_bordo": ("In coda dopo «{titolo}». Notifica al completamento.",),
   },
   breve={
       "normale": ("In coda dopo «{titolo}», ti avviso.",),
       "formale": ("In coda dopo «{titolo}», la avviso.",),
       "amichevole": ("Anche questo in coda dopo «{titolo}», ti avviso.",),
       "ironico": ("In fila dopo «{titolo}», ti avviso.",),
       "essenziale": ("In coda dopo «{titolo}».",),
       "computer_di_bordo": ("In coda dopo «{titolo}».",),
   })

# `{dopo}` (12/10 sera): per le estensioni « Prima di usarla andrà approvata.», impersonale, così
# va bene col «tu» e col «lei» (prima la stima diceva «te la faccio approvare» anche nel formale)
_P = "{cosa}: lo affido all'agente{coda}{carico}."
_v("lavori.proposta", "proposta",
   _P + " {stima} e ti avviso quando ha finito.{dopo} Procedo?",
   fissi=("cosa", "coda", "carico", "dopo"), domanda="Procedo?",
   esempio={"cosa": "È un lavoro di programmazione", "coda": "",
            "carico": "", "stima": "Ci vorranno alcuni minuti", "dopo": ""},
   toni={
       "normale": (
           _P + " {stima} e ti avviso quando ha finito.{dopo} Procedo?",
           "{cosa}: lo passo all'agente{coda}{carico}. {stima} e ti avviso quando ha "
           "finito.{dopo} Procedo?",
           "{cosa}, quindi lo affido all'agente{coda}{carico}. {stima}; quando ha "
           "finito ti avviso.{dopo} Procedo?"),
       "formale": (
           "{cosa}: lo affiderei all'agente{coda}{carico}. {stima} e la avviso quando "
           "ha finito.{dopo} Procedo?",
           "{cosa}: se è d'accordo, lo passo all'agente{coda}{carico}. {stima}, e la "
           "informo al termine.{dopo} Procedo?"),
       "amichevole": (
           "{cosa}: lo do all'agente{coda}{carico}. {stima} e ti avviso appena ha "
           "finito.{dopo} Procedo?",
           "{cosa}: ci pensa l'agente{coda}{carico}. {stima}, poi ti avviso io.{dopo} "
           "Procedo?"),
       # L'inciso prima di {coda}{carico}: dopo («; prima devo caricare il modello, ci vuole un
       # minuto in più, che ha più pazienza di me») non si legava più all'agente
       "ironico": (
           "{cosa}: lo affido all'agente, che ha più pazienza di me{coda}{carico}. "
           "{stima} e ti avviso quando ha finito.{dopo} Procedo?",
           "{cosa}: pane per i denti dell'agente{coda}{carico}. {stima} e ti avviso "
           "quando ha finito.{dopo} Procedo?"),
       "essenziale": ("{cosa}: all'agente{coda}{carico}. {stima}.{dopo} Procedo?",),
       "computer_di_bordo": (
           "{cosa}. Assegnazione all'agente{coda}{carico}. {stima}.{dopo} Procedo?",),
   },
   breve={
       "normale": ("{cosa}: anche questo all'agente{coda}{carico}.{dopo} Procedo?",),
       "formale": ("{cosa}: come prima, lo affiderei all'agente{coda}{carico}.{dopo} "
                   "Procedo?",),
       "amichevole": ("{cosa}: come prima, ci pensa l'agente{coda}{carico}.{dopo} "
                      "Procedo?",),
       "ironico": ("{cosa}: anche questo all'agente{coda}{carico}.{dopo} Procedo?",),
       "essenziale": ("{cosa}: all'agente{coda}{carico}.{dopo} Procedo?",),
       "computer_di_bordo": ("{cosa}. All'agente{coda}{carico}.{dopo} Procedo?",),
   })

# Le forme brevi senza «ancora» (12/10 sera): «Ancora nessun lavoro in corso» sottintende che
# dall'ultima volta non è cambiato niente, e un lavoro può essere partito e finito nel frattempo
_v("lavori.nessuno", "lettura", "Non ho lavori in corso.",
   toni={
       "normale": ("Non ho lavori in corso.", "Al momento non ho lavori in corso.",
                   "Nessun lavoro in corso, per ora."),
       "formale": ("Al momento non ho lavori in corso.", "Non risultano lavori in corso."),
       "amichevole": ("Niente in corso, al momento.", "Per ora non ho lavori in corso."),
       "ironico": ("Non ho lavori in corso: per una volta sono libera.",
                   "Nessun lavoro in corso. Tutto tranquillo, sospettosamente."),
       "essenziale": ("Nessun lavoro in corso.",),
       "computer_di_bordo": ("Nessun lavoro in corso.", "Coda dei lavori vuota."),
   },
   breve={
       "normale": ("Nessun lavoro in corso.",),
       "formale": ("Nessun lavoro in corso.",),
       "amichevole": ("Niente in corso.",),
       "ironico": ("Niente in corso: tutto tranquillo.",),
       "essenziale": ("Nessun lavoro.",),
       "computer_di_bordo": ("Coda vuota.",),
   })

_v("lavori.nessuna_domanda", "lettura", "Non ho lavori che aspettano una risposta.",
   toni={
       "normale": ("Non ho lavori che aspettano una risposta.",
                   "Nessun lavoro aspetta una risposta, al momento."),
       "formale": ("Al momento nessun lavoro attende una risposta.",
                   "Non ho lavori in attesa di una risposta."),
       "amichevole": ("Nessun lavoro sta aspettando una tua risposta.",
                      "Per ora nessun lavoro aspetta una risposta."),
       "ironico": ("Nessun lavoro aspetta una risposta: per ora non devi niente a nessuno.",
                   "Non ho lavori che aspettano una risposta."),
       "essenziale": ("Nessun lavoro in attesa di risposta.",),
       "computer_di_bordo": ("Nessun lavoro in attesa di risposta.",),
   })

# «l'estensione «…»» (12/10 sera): il nome lo sceglie chi la scrive («il convertitore di
# misure», «Meteo per città»), quindi l'accordo («è attiva», «usarla») va col nome comune davanti
_v("estensione.attiva", "esito",
   "Fatto: l'estensione «{titolo}» è attiva, versione {versione}{cosa}. Da adesso puoi usarla.",
   fissi=("titolo", "versione", "cosa"),
   esempio={"titolo": "il convertitore di misure", "versione": 2, "cosa": ""},
   toni={
       "normale": (
           "Fatto: l'estensione «{titolo}» è attiva, versione {versione}{cosa}. Da adesso puoi "
           "usarla.",
           "Fatto: l'estensione «{titolo}» è attiva, versione {versione}{cosa}. Puoi usarla da "
           "subito.",
           "Fatto: ora l'estensione «{titolo}» è attiva, versione {versione}{cosa}. Chiedimi "
           "pure di usarla."),
       "formale": (
           "Fatto: l'estensione «{titolo}» è attiva, versione {versione}{cosa}. Da adesso può "
           "usarla.",
           "Fatto: l'estensione «{titolo}» è ora attiva, versione {versione}{cosa}. Può "
           "servirsene da subito."),
       "amichevole": (
           "Fatto! L'estensione «{titolo}» è attiva, versione {versione}{cosa}. Da adesso puoi "
           "usarla quando vuoi.",
           "Fatto: l'estensione «{titolo}» è attiva, versione {versione}{cosa}. Provala pure "
           "quando vuoi."),
       "ironico": (
           "Fatto: l'estensione «{titolo}» è attiva, versione {versione}{cosa}. Da adesso puoi "
           "usarla, e io non posso più dire di no.",
           "Fatto: l'estensione «{titolo}» è attiva, versione {versione}{cosa}. Un'altra cosa "
           "che so fare: usala quando vuoi."),
       "essenziale": ("Fatto: l'estensione «{titolo}» è attiva, versione {versione}{cosa}.",),
       "computer_di_bordo": (
           "Fatto: estensione «{titolo}» attiva, versione {versione}{cosa}. Disponibile da "
           "subito.",),
   })

_v("sviluppo.correzione", "sviluppo",
   "D'accordo: lo faccio correggere a chi l'ha scritto. Ci lavora in secondo piano; quando è "
   "pronto rifacciamo la prova{caso}.",
   fissi=("caso",), esempio={"caso": " con «venti gradi»"},
   toni={
       "normale": (
           "D'accordo: lo faccio correggere a chi l'ha scritto. Ci lavora in secondo piano; "
           "quando è pronto rifacciamo la prova{caso}.",
           "D'accordo: lo rimando a chi l'ha scritto perché lo corregga. Ci lavora in secondo "
           "piano; quando è pronto rifacciamo la prova{caso}."),
       "formale": (
           "D'accordo: lo faccio correggere a chi l'ha scritto. Ci lavora in secondo piano; "
           "quando è pronto ripetiamo la prova{caso}.",
           "Va bene: lo rimando a chi l'ha scritto per la correzione, in secondo piano. Quando "
           "è pronto ripetiamo la prova{caso}."),
       "amichevole": (
           "D'accordo, lo faccio sistemare a chi l'ha scritto. Ci lavora in secondo piano, e "
           "quando è pronto rifacciamo la prova{caso}.",
           "Va bene: torna a chi l'ha scritto per una sistemata. Quando è pronto rifacciamo la "
           "prova{caso}."),
       "ironico": (
           "D'accordo: torna a chi l'ha scritto, con tanti saluti. Ci lavora in secondo piano; "
           "quando è pronto rifacciamo la prova{caso}.",
           "D'accordo: lo faccio correggere a chi l'ha scritto. Quando è pronto rifacciamo la "
           "prova{caso}, e vediamo."),
       "essenziale": ("D'accordo: correzione in secondo piano. Poi rifacciamo la prova{caso}.",),
       "computer_di_bordo": (
           "Correzione affidata all'autore, in secondo piano. Nuova prova al termine{caso}.",),
   },
   # Brevi senza «di nuovo» (12/10 sera): la correzione di prima può essere di un altro sviluppo
   breve={
       "normale": ("Lo rimando in correzione; poi rifacciamo la prova{caso}.",),
       "formale": ("Lo rimando in correzione; poi ripetiamo la prova{caso}.",),
       "amichevole": ("Torna in correzione; poi rifacciamo la prova{caso}.",),
       "ironico": ("Torna in correzione, con pazienza; poi rifacciamo la prova{caso}.",),
       "essenziale": ("In correzione. Poi la prova{caso}.",),
       "computer_di_bordo": ("Correzione in corso. Nuova prova al termine{caso}.",),
   })

# Mai una preposizione davanti a «{titolo}» (12/10 sera): «Quanto a «il convertitore»» e
# «Sviluppo di «il convertitore»» non si dicono (al, del); il titolo fa da soggetto o da oggetto
_v("sviluppo.stato", "lettura", "Stiamo sviluppando «{titolo}»: {dove}.",
   fissi=("titolo", "dove"),
   esempio={"titolo": "il convertitore di misure",
            "dove": "siamo al collaudo (3 di 5): fatte analisi e sviluppo; mancano revisione e "
                    "attivazione"},
   toni={
       "normale": ("Stiamo sviluppando «{titolo}»: {dove}.",
                   "Lo sviluppo in corso è «{titolo}»: {dove}.",
                   "«{titolo}» è in sviluppo: {dove}."),
       "formale": ("Stiamo sviluppando «{titolo}»: {dove}.",
                   "Lo sviluppo in corso è «{titolo}»: {dove}."),
       "amichevole": ("Stiamo sviluppando «{titolo}»: {dove}.",
                      "Ecco a che punto siamo con «{titolo}»: {dove}."),
       "ironico": ("Stiamo sviluppando «{titolo}»: {dove}.", "«{titolo}» procede: {dove}."),
       "essenziale": ("«{titolo}»: {dove}.",),
       "computer_di_bordo": ("Sviluppo «{titolo}»: {dove}.",),
   })

# La cortesia (05/10, calliope/cortesia.py): la base la decide `Cortesia` (le frasi di oggi a
# rotazione per processo); con «attivo» queste, a rotazione per persona (6–8 per tono)
_v("cortesia.grazie", "cortesia", None, toni={
    "normale": ("Prego!", "Figurati.", "Di niente.", "A disposizione.", "Figurati, è un piacere.",
                "Ci mancherebbe.", "Quando vuoi."),
    "formale": ("Prego, è un piacere.", "Si figuri.", "Sono a sua disposizione.",
                "Non c'è di che.", "È un piacere esserle utile.", "Prego, si figuri."),
    "amichevole": ("Figurati, è un piacere!", "Ma di che!", "Quando vuoi!", "Ci mancherebbe!",
                   "Sempre volentieri!", "Per così poco!"),
    "ironico": ("Prego, lo metto in conto.", "Dovere, ogni tanto.", "Figurati, è il mio lavoro.",
                "Prego. Accetto anche applausi.", "Di niente: segno tutto su un quadernetto.",
                "Figurati, per così poco mi sono appena scaldata.",
                "Prego, la gratitudine mi fa funzionare meglio."),
    "essenziale": ("Prego.", "Di niente.", "Figurati."),
    "computer_di_bordo": ("Prego.", "A disposizione.", "Sempre a disposizione.",
                          "Nessun problema."),
})
_v("cortesia.conferma", "cortesia", None, toni={
    "normale": ("Bene!", "Ottimo.", "D'accordo.", "Perfetto.", "Molto bene.", "Mi fa piacere."),
    "formale": ("Molto bene.", "D'accordo.", "Bene.", "Perfetto.", "Benissimo.",
                "Lieta di esserle stata utile."),
    "amichevole": ("Benissimo!", "Ottimo!", "Che bello!", "Evviva!", "Perfetto, mi fa piacere!",
                   "Grande!"),
    "ironico": ("Lo prendo come un complimento.", "Bene, ne sono felice.",
                "Ottimo, segno un punto per me.", "Bene: un'altra soddisfazione in archivio.",
                "Perfetto, me lo segno tra i successi.", "Mi commuovo, quasi."),
    "essenziale": ("Bene.", "Ottimo.", "D'accordo."),
    "computer_di_bordo": ("Ricevuto.", "Confermato.", "Acquisito.", "Chiaro."),
})

# ── solo misura: classi bloccate, parola per parola (§ 2 della ricerca) ──
_v("politica.conferma", "politica", "C'è di mezzo {fonte}, quindi chiedo a te: vuoi che {cosa}?")
_v("politica.non_chiesto", "politica", "Non me l'hai chiesto: vuoi che {cosa}?")
_v("politica.valore", "politica", "«{valore}» viene {fonte}, non da te: vuoi davvero che {cosa}?")
_v("sfida.conferma", "sfida", "Per conferma ripeti: {testo}.")
_v("sfida.cosa", "sfida", "Per {cosa}, ripeti: {testo}.")
_v("sfida.parziale", "sfida", "Non ho sentito tutte le parole. Ripeti: {testo}.")
_v("sfida.fallita", "sfida",
   "Non ho sentito le parole giuste, quindi non procedo: chiedimelo di nuovo.")
_v("permesso.ospite", "permesso",
   "Mi dispiace, questo posso farlo solo per chi vive in casa, e la tua voce non la riconosco.")
_v("permesso.familiare", "permesso",
   "Mi dispiace, questo può chiederlo solo chi amministra Calliope.")
_v("permesso.lavori", "permesso",
   "I lavori di programmazione li può affidare solo chi amministra: chiedi a chi amministra.")
_v("ripiego.ripeti", "ripiego", "Non ci sono riuscita: puoi ripetere la richiesta?")
_v("annuncio.collaudo", "annuncio", "il lavoro di «{titolo}» è pronto: siamo al collaudo.")

CATALOGO: dict[str, Voce] = {v.id: v for v in _C}
del _C


# ─────────────────────────── riconoscere ───────────────────────────
_NORM_VIA = re.compile(r"«[^»]*»|\d+")
_NORM_SEGNI = re.compile(r"[^\wàèéìòù]+")


def normalizza(testo) -> str:
    """Per confrontare due risposte: minuscole, senza «…» né numeri né punteggiatura."""
    t = _NORM_VIA.sub(" ", str(testo or "").lower())
    return " ".join(_NORM_SEGNI.sub(" ", t).split())


def _chiave(testo) -> str:
    return " ".join(str(testo or "").lower().split())


def _modelli_regex() -> list[tuple[str, str, re.Pattern]]:
    """Per ogni id i suoi modelli interi (base, varianti, forme brevi) come espressioni: i
    segnaposto diventano «qualunque testo». Interi, non frase per frase: «Ti avviso quando è
    pronto.» è sia di `lavori.in_coda` sia dentro `lavori.avviato`. Solo i modelli con almeno tre
    parole fisse (né «Prego!» né «Procedo?»: troppo comuni per dire di chi sono)."""
    out, viste = [], set()
    for v in CATALOGO.values():
        modelli = [v.base] if v.base else []
        for d in (v.toni, v.breve):
            for forme in d.values():
                modelli.extend(forme)
        for m in modelli:
            fisse = re.sub(r"\{[^}]*\}", " ", m or "")
            if len(re.findall(r"[^\W\d_]+", fisse)) < 3 or (v.id, m) in viste:
                continue
            viste.add((v.id, m))
            pezzi = re.split(r"\{[^}]*\}", m)
            rx = r"(?<!\w)" + r".+?".join(re.escape(p) for p in pezzi)
            # Il pezzo fisso più lungo, cercato prima come sottostringa: l'uscita unica chiama
            # `riconosci` a ogni frase, e le espressioni costano (~0,7 ms in tutto senza)
            ancora = max(pezzi, key=len).lower()
            out.append((v.id, ancora, re.compile(rx, re.I)))
    return out


_REGEX = _modelli_regex()


def riconosci(testo) -> list[str]:
    """Gli id del catalogo le cui frasi compaiono nel testo (per modello), in ordine, una volta
    ciascuno. Per i turni di prima del 12/10 e per le frasi non scelte da `Frasi.scegli`."""
    s = str(testo or "")
    if not s.strip():
        return []
    basso = s.lower()
    trovati = []
    for ident, ancora, rx in _REGEX:
        if ancora in basso and ident not in trovati and rx.search(s):
            trovati.append(ident)
    return trovati


# ─────────────────────────── scegliere ───────────────────────────
class Frasi:
    """Il catalogo in uso: modo, contesto del turno (per thread: la corsia), memoria per persona
    di ciò che si è detto, e le scelte in attesa di andare alla voce."""

    def __init__(self, modo: str = "ombra", breve_turni: int = 6, tono_casa: str = "normale"):
        self.modo = modo if modo in MODI else "ombra"
        self.breve_turni = max(0, int(breve_turni or 0))
        self.tono_casa = tono_casa if tono_casa in TONI_FRASI else "normale"
        self._lock = threading.Lock()
        self._qui = threading.local()
        # persona → {"turno": n, "giri": {(id, tono, breve): n}, "ultimo": {id: (turno, t)},
        #            "recenti": {id: deque delle ultime 2 (breve, variante)}}
        self._persone: collections.OrderedDict = collections.OrderedDict()
        self._scelte: collections.OrderedDict = collections.OrderedDict()

    def configura(self, cfg):
        """Dai valori della configurazione (main, all'avvio)."""
        modo = str(getattr(cfg, "frasi_varianti", "ombra") or "ombra").strip().lower()
        self.modo = modo if modo in MODI else "ombra"
        self.breve_turni = max(0, int(getattr(cfg, "frasi_breve_turni", 6) or 0))
        t = str(getattr(cfg, "tono", "") or "")
        self.tono_casa = t if t in TONI_FRASI else "normale"
        return self

    # ── il turno (la corsia) ──
    def inizio_turno(self, persona, tono: str | None = None):
        """Un turno nuovo di `persona` in questo thread (Ciclo, fase 5): conta i turni per la
        forma breve e ricorda il tono per le scelte dei tool."""
        self._qui.persona = persona
        self._qui.tono = tono if tono in TONI_FRASI else None
        if persona is None:
            return
        with self._lock:
            p = self._persona(persona)
            p["turno"] += 1

    def _persona(self, persona) -> dict:
        p = self._persone.get(persona)
        if p is None:
            p = self._persone[persona] = {"turno": 0, "giri": {}, "ultimo": {}, "recenti": {}}
            while len(self._persone) > PERSONE_MAX:
                self._persone.popitem(last=False)
        else:
            self._persone.move_to_end(persona)
        return p

    def _tono(self, tono) -> str:
        t = tono if tono in TONI_FRASI else getattr(self._qui, "tono", None)
        return t if t in TONI_FRASI else self.tono_casa

    # ── la scelta ──
    def scegli(self, ident: str, *, persona=None, tono: str | None = None,
               base: str | None = None, **valori) -> str:
        """Il testo da dire per la frase `ident`, coi `valori` dei segnaposto. `base`: la forma
        di oggi decisa da chi chiama (la cortesia). Con «spento» e «ombra» è sempre la base; con
        «attivo» la variante scelta. La scelta resta in attesa finché l'uscita unica non la dice
        (`detta`): solo allora conta per la rotazione e per la forma breve."""
        v = CATALOGO[ident]
        testo_base = base if base is not None else (v.base or "").format(**valori)
        info = {"id": ident}
        if self.modo != "spento" and not v.bloccata:
            if persona is None:
                persona = getattr(self._qui, "persona", None)
            t = self._tono(tono)
            breve, i, forma = self._decidi(v, persona, t)
            if forma is not None:
                scelta = forma.format(**valori)
                info.update(tono=t, variante=i, breve=breve)
                if self.modo == "attivo":
                    testo = scelta
                else:
                    info["ombra"] = {"variante": i, "breve": breve,
                                     "uguale": _chiave(scelta) == _chiave(testo_base)}
                    info.pop("variante")
                    info.pop("breve")
                    testo = testo_base
                self._ricorda_scelta(testo, info, persona)
                return testo
        self._ricorda_scelta(testo_base, info, persona)
        return testo_base

    def _decidi(self, v: Voce, persona, tono: str) -> tuple[bool, int, str | None]:
        """(breve, indice, forma). A rotazione per persona, tono e forma; breve se lo stesso id è
        stato detto a questa persona negli ultimi `breve_turni` turni e nell'ultima ora."""
        with self._lock:
            p = self._persone.get(persona) if persona is not None else None
            breve = False
            if p is not None and self.breve_turni and v.forme(tono, breve=True):
                u = p["ultimo"].get(v.id)
                if u is not None and p["turno"] - u[0] <= self.breve_turni \
                        and time.time() - u[1] <= BREVE_S:
                    breve = True
            forme = v.forme(tono, breve=breve)
            if not forme:
                return False, 0, None
            giro = p["giri"].get((v.id, tono, breve), 0) if p is not None else 0
            recenti = list(p["recenti"].get(v.id, ())) if p is not None else []
            n = len(forme)
            i = giro % n
            # Mai una delle ultime due dette, se ce n'è un'altra (cambio di tono, forma breve)
            for k in range(n):
                j = (giro + k) % n
                if (breve, j) not in recenti:
                    i = j
                    break
            return breve, i, forme[i]

    def _ricorda_scelta(self, testo: str, info: dict, persona):
        k = _chiave(testo)
        if not k:
            return
        with self._lock:
            self._scelte[k] = (dict(info), persona)
            self._scelte.move_to_end(k)
            while len(self._scelte) > SCELTE_MAX:
                self._scelte.popitem(last=False)

    # ── detta: dall'uscita unica ──
    def detta(self, testo) -> list[dict]:
        """Una frase è andata alla voce (`Uscita.di`): le frasi pronte che contiene, come
        dizionari senza parole ({"id", "tono", "variante", "breve"} o {"id", "ombra"}). Una
        scelta di `scegli` si riconosce dal testo (anche un pezzo: la voce le divide in frasi) e
        si consuma: conta per la rotazione e la forma breve. Le altre del catalogo per modello."""
        k = _chiave(testo)
        if not k:
            return []
        trovata = None
        with self._lock:
            for chiave in reversed(self._scelte):
                if chiave == k or (len(k) >= 12 and k in chiave):
                    trovata = chiave
                    break
            if trovata is not None:
                info, persona = self._scelte.pop(trovata)
                self._conta(info, persona)
                return [info]
        return [{"id": i} for i in riconosci(testo)]

    def _conta(self, info: dict, persona):
        """Rotazione e forma breve (con il lock)."""
        if persona is None or "tono" not in info:
            return
        o = info.get("ombra") or {}
        breve = bool(info.get("breve", o.get("breve", False)))
        i = info.get("variante", o.get("variante"))
        p = self._persona(persona)
        chiave = (info["id"], info["tono"], breve)
        p["giri"][chiave] = p["giri"].get(chiave, 0) + 1
        p["ultimo"][info["id"]] = (p["turno"], time.time())
        r = p["recenti"].setdefault(info["id"], collections.deque(maxlen=2))
        r.append((breve, i))

    def tutte(self, ident: str, toni=None) -> list[str]:
        """Le forme (varianti e brevi) dei toni dati, senza segnaposto: per la cortesia da
        sintetizzare all'avvio (Speaker.prepare)."""
        v = CATALOGO[ident]
        out = []
        for t in (toni or TONI_FRASI):
            for breve in (False, True):
                out.extend(f for f in v.forme(t, breve) if not segnaposto(f))
        return list(dict.fromkeys(out))


FRASI = Frasi()


def scegli(ident: str, **k) -> str:
    """Scorciatoia: `FRASI.scegli`."""
    return FRASI.scegli(ident, **k)


# ─────────────────────────── misura (fase 0) ───────────────────────────
def _chi(t: dict):
    v = t.get("voce") if isinstance(t.get("voce"), dict) else {}
    lav = t.get("lavoro") if isinstance(t.get("lavoro"), dict) else {}
    return v.get("id") or v.get("nome") or lav.get("chi") or t.get("persona") or "?"


def _pronte(t: dict) -> list[dict]:
    p = [x for x in (t.get("pronte") or ()) if isinstance(x, dict) and x.get("id")]
    if p:
        return p
    if t.get("esito") == "cortesia":
        return [{"id": "cortesia"}]
    r = t.get("risposta")
    return [{"id": i} for i in riconosci(r)] if isinstance(r, str) else []


def _chiave_pronte(pronte: list[dict], ombra: bool) -> str:
    parti = []
    for x in pronte:
        o = x.get("ombra") if ombra else None
        if isinstance(o, dict):
            parti.append(f"{x['id']}/{x.get('tono')}/{o.get('variante')}/{o.get('breve')}")
        else:
            parti.append(f"{x['id']}/{x.get('tono')}/{x.get('variante')}/{x.get('breve')}")
    return "pronta:" + "|".join(parti)


def riassunto(turni: list[dict]) -> dict:
    """Ripetizioni ogni 100 risposte, per giorno e in tutto: una risposta (normalizzata) uguale a
    una delle ultime `FINESTRA` alla stessa persona nello stesso giorno. Separate per frasi
    pronte e modello. Senza parole (minori, ospiti) una frase pronta si confronta per id e
    variante; una risposta del modello senza parole non si conta. `stima_ombra`: le pronte se si
    fossero dette le varianti scelte in ombra."""
    giorni: dict = {}
    storia: dict = {}
    per_id: collections.Counter = collections.Counter()
    for t in turni:
        if not isinstance(t, dict):
            continue
        r = t.get("risposta")
        testo = r if isinstance(r, str) and r.strip() else None
        pronte = _pronte(t)
        if testo is None and not pronte:
            continue
        giorno = str(t.get("inizio") or "")[:10] or "?"
        g = giorni.setdefault(giorno, {k: {"n": 0, "ripetute": 0}
                                       for k in ("pronte", "modello", "tutte", "stima_ombra")}
                              | {"ombra": 0, "brevi": 0})
        classe = "pronte" if pronte else "modello"
        chi = (giorno, _chi(t))
        h = storia.setdefault(chi, {"vere": collections.deque(maxlen=FINESTRA),
                                    "ombra": collections.deque(maxlen=FINESTRA)})
        k = normalizza(testo) if testo is not None else _chiave_pronte(pronte, False)
        if pronte and any("ombra" in x for x in pronte):
            g["ombra"] += 1
            k_ombra = _chiave_pronte(pronte, True)
        else:
            k_ombra = k
        g["brevi"] += sum(1 for x in pronte if x.get("breve"))
        rip = bool(k) and k in h["vere"]
        rip_o = bool(k_ombra) and k_ombra in h["ombra"]
        for c in (classe, "tutte"):
            g[c]["n"] += 1
            g[c]["ripetute"] += rip
        if pronte:
            g["stima_ombra"]["n"] += 1
            g["stima_ombra"]["ripetute"] += rip_o
            for x in pronte:
                per_id[x["id"]] += 1
        h["vere"].append(k)
        h["ombra"].append(k_ombra)
    tot = {k: {"n": sum(g[k]["n"] for g in giorni.values()),
               "ripetute": sum(g[k]["ripetute"] for g in giorni.values())}
           for k in ("pronte", "modello", "tutte", "stima_ombra")}
    for d in list(giorni.values()) + [tot]:
        for k in ("pronte", "modello", "tutte", "stima_ombra"):
            d[k]["ogni_100"] = round(100.0 * d[k]["ripetute"] / d[k]["n"], 1) if d[k]["n"] \
                else None
    tot["ombra"] = sum(g["ombra"] for g in giorni.values())
    tot["brevi"] = sum(g["brevi"] for g in giorni.values())
    return {"giorni": dict(sorted(giorni.items())), "totale": tot,
            "piu_dette": per_id.most_common(8), "obiettivo": OBIETTIVO}


def testo(r: dict) -> str:
    """La sezione di `calliope stato --turni`."""
    tot = r.get("totale") or {}
    righe = ["Frasi pronte (12/10, calliope/frasi.py): ripetizioni ogni 100 risposte, stessa "
             f"persona e stesso giorno, ultime {FINESTRA} (obiettivo per le pronte: sotto "
             f"{r.get('obiettivo', OBIETTIVO):g})"]
    if not (tot.get("tutte") or {}).get("n"):
        return righe[0] + "\n    nessuna risposta nel registro"

    def f(d):
        x = d.get("ogni_100")
        return "—" if x is None else f"{x:.1f} su {d['n']}"

    for giorno, g in (r.get("giorni") or {}).items():
        riga = (f"    {giorno}  pronte {f(g['pronte'])}  modello {f(g['modello'])}  "
                f"tutte {f(g['tutte'])}")
        if g.get("ombra"):
            riga += f"  · con le varianti (ombra) {f(g['stima_ombra'])}"
        if g.get("brevi"):
            riga += f"  · forme brevi {g['brevi']}"
        righe.append(riga)
    riga = (f"    in tutto  pronte {f(tot['pronte'])}  modello {f(tot['modello'])}  "
            f"tutte {f(tot['tutte'])}")
    if tot.get("ombra"):
        riga += f"  · con le varianti (ombra) {f(tot['stima_ombra'])}"
    righe.append(riga)
    if r.get("piu_dette"):
        righe.append("    più dette: " + ", ".join(f"{i} {n}" for i, n in r["piu_dette"]))
    p = (tot.get("pronte") or {}).get("ogni_100")
    if p is not None and tot["pronte"]["n"] >= 50 and p >= r.get("obiettivo", OBIETTIVO):
        righe.append(f"    ⚠ frasi pronte ripetute {p:.1f} ogni 100: sopra l'obiettivo")
    return "\n".join(righe)


# ─────────────────────────── il campione per chi amministra ───────────────────────────
def campione(n: int = 30, seme: int = 12) -> list[dict]:
    """`n` forme da rileggere prima di «attivo»: a giro sugli id (non bloccati) e sui toni,
    varianti e forme brevi diverse dalla base, coi valori di fantasia dell'esempio. Sempre lo
    stesso a parità di `seme`."""
    rnd = random.Random(seme)
    from .cortesia import RISPOSTE        # le frasi di cortesia di oggi non sono da rileggere
    gia = {f for forme in RISPOSTE.values() for fs in forme.values() for f in fs}
    per_id: dict[str, list[dict]] = {}
    for v in CATALOGO.values():
        if v.bloccata:
            continue
        righe = []
        for t in TONI_FRASI:
            for breve in (False, True):
                for i, forma in enumerate(v.forme(t, breve)):
                    if (not breve and v.base and forma == v.base) or forma in gia:
                        continue
                    righe.append({"id": v.id, "tono": t, "breve": breve, "variante": i,
                                  "testo": forma.format(**v.esempio),
                                  "base": (v.base or "").format(**v.esempio) or None})
        rnd.shuffle(righe)
        per_id[v.id] = righe
    out = []
    while len(out) < n and any(per_id.values()):
        for ident in list(per_id):
            if per_id[ident] and len(out) < n:
                out.append(per_id[ident].pop())
    return out


def campione_testo(righe: list[dict]) -> str:
    oggi = datetime.date.today().isoformat()
    out = [f"# Frasi pronte: campione da rileggere ({len(righe)} forme, {oggi})", "",
           "Per ogni riga: va bene detta così, nel tono indicato? (fatti e domanda in fondo "
           "uguali alla frase di oggi, «lei» nel formale, niente «!» nel computer di bordo).",
           "Se va tutto bene: in calliope.locale.yaml `frasi_varianti: attivo` e riavvio.",
           "Se una non va: segnala l'id e il tono, si corregge in calliope/frasi.py.", ""]
    for k, x in enumerate(righe, 1):
        forma = "breve" if x["breve"] else f"variante {x['variante']}"
        out.append(f"{k:2d}. [ ] {x['id']} · {x['tono']} · {forma}")
        out.append(f"       {x['testo']}")
        if x.get("base"):
            out.append(f"       (oggi: {x['base']})")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    """`python -m calliope.frasi --campione [--n 30] [--seme 12] [--file PERCORSO]`: il
    campione da rileggere; `--tutte`: tutte le forme del catalogo."""
    argv = list(sys.argv[1:] if argv is None else argv)

    def opz(nome, predefinito):
        if nome in argv:
            i = argv.index(nome)
            if i + 1 < len(argv):
                return argv[i + 1]
        return predefinito

    if "--tutte" in argv:
        righe = campione(10_000)
    elif "--campione" in argv:
        try:
            righe = campione(max(1, int(opz("--n", 30))), int(opz("--seme", 12)))
        except ValueError:
            print("--n e --seme vogliono un numero")
            return 1
    else:
        print(main.__doc__)
        return 1
    testo_c = campione_testo(righe)
    dest = opz("--file", None)
    if dest:
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(testo_c)
        print(f"Campione di {len(righe)} forme scritto in {dest}")
    else:
        sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
        print(testo_c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
