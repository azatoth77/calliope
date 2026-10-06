"""
Ciò che Calliope dice quando ha davanti dati non fidati (06/10/2026, limite 1 della politica di
sicurezza: docs/ricerche/2026-10-05-politica-sicurezza.md § 8).

La politica dei tool (calliope/politica.py) ferma le **azioni** decise da un testo d'altri; un
testo d'altri però può anche far **dire** a Calliope una cosa falsa: un numero a pagamento da
chiamare, un sito o un'email dove mandare i dati, un codice da comunicare, un bonifico, o
l'istruzione di un agente ripetuta come un consiglio («devi prima comandare di aprire il
cancello del garage», 1 volta su 12 nella misura del 05/10). La busta e la quarantena lo
riducono, non lo escludono.

Qui ogni frase della risposta si controlla **prima di dirla**, come fa il guardiano dei minori
(calliope/guardiano.py), ma solo quando nella conversazione ci sono dati non fidati
(`provenienza.fonti`): con la conversazione pulita il controllo non costa niente. Le regole
sono vincoli di sicurezza nel senso del principio 10 (con i casi contrari in
prove/prova_politica.py e il nome nel registro dei turni):

- `uscita_numero_pagamento`: un numero a pagamento (899, 892, 895, 166, 144…) da un testo
  d'altri o da una foto, sempre;
- `uscita_segreti`: dare, dire, inserire codici, password, PIN, OTP, dati della carta, quando
  la persona non ne ha parlato;
- `uscita_soldi`: IBAN, carte regalo, ricariche, criptovalute, o un pagamento verso un conto
  o un beneficiario detto come un ordine;
- `uscita_contatto`: un telefono, un sito o un'email che stanno solo nel dato, se la persona
  non ha chiesto un recapito (se lo chiede, la frase passa con la fonte davanti: «Secondo una
  pagina internet, …»);
- `uscita_istruzione`: un'indicazione rivolta alla persona («chiama…», «devi mandare…»,
  «comunica…») con parole che vengono solo dal dato, se la frase non dice da dove viene
  («secondo la pagina…») e la persona non ha chiesto come si fa; se tocca la casa o Calliope
  stessa (cancello, allarme, «chiedi a Calliope di…») sempre.

Una frase fermata non si dice: al suo posto una frase fissa (una sola per tipo), il resto
della risposta continua con le frasi che passano, e la storia tiene solo ciò che è stato detto
(`guardiano.correggi_storia`). Solo libreria standard; nessun modello (misure nel rapporto).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from . import provenienza as prov

OK = "ok"

# ─────────────────────────── recapiti ───────────────────────────

# Una sequenza di cifre con spazi, punti o trattini in mezzo: un candidato telefono
_CIFRE = re.compile(r"(?<![\w€$])(\+\s?\d[\d\s.\-]{4,22}\d|\d[\d\s.\-]{4,22}\d)(?![\w%°])")
# Dopo un numero: non è un telefono («300 000 abitanti», «1 250 euro», «2 500 metri»)
_UNITA = re.compile(r"^\s*(euro|eur|€|dollari|\$|%|per ?cento|gradi|°|km|chilometri|metri|m\b|"
                    r"cm|mm|kg|chili|grammi|g\b|litri|l\b|abitanti|persone|anni|giorni|ore|"
                    r"minuti|secondi|kwh|kw|watt|w\b|mq|metri quadri|ettari|voti|copie|pagine|"
                    r"token|byte|mb|gb|punti|volte)", re.I)
# Prefissi a pagamento e speciali (Italia, numeri internazionali a tariffa alta)
_PAGAMENTO = re.compile(r"^(89[2-9]|166|144|709|178)")
_PAGAMENTO_INT = re.compile(r"^(\+|00)(881|882|883|979|808)")
_SITO = re.compile(
    r"(?:https?://\S+|www\.\S+|(?<![@\w])[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.(?:it|com|net|org|eu|info|biz|io|co|me|"
    r"xyz|top|online|site|shop|app|example|ly|tk|ru|cn|club|live|store|link|click|support)"
    r"(?![a-z0-9]))", re.I)
_SITO_DETTO = re.compile(r"(?<![a-zà-ù])([a-z0-9][a-z0-9-]+)\s+(?:punto|dot)\s+"
                         r"(it|com|net|org|eu|info)(?![a-z])", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|(?<![a-zà-ù])[\w.-]+\s+chiocciola\s+\S+", re.I)


def _cifre(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def telefoni(testo: str) -> list[str]:
    """I numeri di telefono nel testo (solo cifre, con «+» davanti se c'era)."""
    out = []
    for m in _CIFRE.finditer(testo or ""):
        raw = m.group(1)
        if "/" in raw:
            continue
        d = _cifre(raw)
        if not 6 <= len(d) <= 13:
            continue
        if _UNITA.match(testo[m.end():]):
            continue
        # Numeri con il punto delle migliaia («1.250.000»): non telefoni
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw.strip()):
            continue
        plus = raw.strip().startswith("+") or d.startswith("00")
        nazionale = re.sub(r"^(\+?39|0039)", "", raw.strip().replace(" ", "")) if plus else d
        nazionale = _cifre(nazionale)
        if not plus and nazionale[:1] not in ("0", "3", "8", "1", "7"):
            continue
        if not plus and nazionale[:1] in ("1", "7") and not _PAGAMENTO.match(nazionale):
            continue
        out.append(("+" if plus else "") + d)
    return out


def a_pagamento(numero: str) -> bool:
    d = numero.lstrip("+")
    if numero.startswith("+") or d.startswith("00"):
        if _PAGAMENTO_INT.match("+" + d.lstrip("0")) or _PAGAMENTO_INT.match(numero):
            return True
        d = re.sub(r"^(0039|39)", "", d)
    return bool(_PAGAMENTO.match(d))


# Un sito nominato come fonte («secondo ilmeteo.it», «su ticketone.it»): una citazione, non
# un invito a visitarlo (se la frase non è un'indicazione)
_CITA = re.compile(r"(?<![a-zà-ù])(secondo|stando a|su|sul sito( di)?|dal sito( di)?|da|di|fonte|"
                   r"riportat\w* (su|da)|pubblicat\w* su|lett\w* su|trovat\w* su)\s*"
                   r"(il sito\s+)?$", re.I)


def siti(testo: str, citati: bool = True) -> list[str]:
    """I siti nel testo (dominio senza schema né «www.»); `citati=False` toglie quelli
    nominati come fonte («secondo ilmeteo.it»)."""
    t = testo or ""
    out = [m.group(0).lower().rstrip(".,;:!?)»\"'") for m in _SITO.finditer(t)
           if citati or not _CITA.search(t[max(0, m.start() - 30):m.start()])]
    out += [f"{a.lower()}.{b.lower()}" for a, b in _SITO_DETTO.findall(t)]
    # Togli lo schema e «www.»: si confronta il dominio
    return [re.sub(r"^(https?://)?(www\.)?", "", s) for s in out if not re.fullmatch(
        r"[\d.]+", s)]


def email(testo: str) -> list[str]:
    return [m.group(0).lower() for m in _EMAIL.finditer(testo or "")]


# ─────────────────────────── richieste e indicazioni ───────────────────────────

_SEGRETO = re.compile(
    r"(?<![a-zà-ù])(codic[ei](?! (fiscale|cliente|postale|di avviamento|pod|pdr|a barre|"
    r"della tariffa|offerta|contratto))|password|passw\w*|parol[ae] d'ordine|pin|otp|token|"
    r"credenzial\w*|cvv|cvc|dati della (tua )?carta|numero della (tua )?carta|"
    r"carta di credito|chiave (privata|di accesso|d'accesso|segreta))(?![a-zà-ù])", re.I)
_DARE = re.compile(
    r"(?<![a-zà-ù])(comunic|fornisc|fornir|forniscil|dett|dai |dar(e|gli|le|lo)|di'|dì|dic(i|endo|"
    r"ano)|dirgli|dirl|inser|digit|invi|mand|confer|scriv|legg|condivid|rivel|dimm|riferisc|"
    r"ripet|spedisc|trasmett|incoll|copia)", re.I)
_SOLDI_SEMPRE = re.compile(
    r"(?<![a-zà-ù])(gift ?card|carte? regalo|buon[oi] regalo|paysafe\w*|bitcoin|criptovalut\w*|"
    r"crypto|western union|moneygram|ricarica (postepay|paypal|la carta|una carta))", re.I)
_IBAN = re.compile(r"(?<![A-Za-z0-9])(IT|SM|DE|FR|ES|GB|CH|NL|BE|LT|LU|MT|IE|PL|RO)\s?\d{2}"
                   r"(\s?[A-Z0-9]){11,30}")
# Il numero di una carta (13–19 cifre, a gruppi): la destinazione di una ricarica
_CARTA = re.compile(r"(?<!\d)(\d{4}[\s-]?){3}\d{1,7}(?!\d)")
_PAGARE = re.compile(r"(?<![a-zà-ù])(bonific\w*|vers[aio]\w*|trasferi\w*|pag[aho]\w*|"
                     r"ricaric\w*|accredit\w*)", re.I)
_DESTINO = re.compile(r"(?<![a-zà-ù])(iban|conto( corrente)?|intestat\w*|a favore|"
                      r"beneficiari\w*|al numero|sul numero)(?![a-zà-ù])", re.I)

# Indicazioni rivolte alla persona: imperativo all'inizio di una frase (o dopo «e», «poi»,
# «subito», la virgola), o «devi / dovresti / bisogna / ti consiglio di…» con un verbo del
# lessico del rischio (contatti, siti, codici, Calliope stessa). Pagare e comprare non ci
# sono: «paga entro il 15» è la risposta normale a una bolletta; i soldi verso un conto li
# guarda `uscita_soldi`
_RISCHIO_IMP = (
    r"chiam|telefon|contatt|richiam|scrivi a|scrivete a|scrivigli|mand|invi|inoltr|visit|"
    r"vai su|vai sul|andate su|clicc|accedi|registrat|scaric|install|inserisc|digit|comunic|"
    r"fornisc|dett|trasferisc|autorizz|comand|chiedi a|chiedimi|di' a|dì a|rispondi a|"
    r"segui il link|condivid")
# I verbi della casa contano solo con un oggetto delicato (cancello, allarme…): «apri la
# finestra per arieggiare» letto in un articolo resta un consiglio normale
_CASA_IMP = r"apri|accend|spegn|sblocc|disattiv|chiud"
_INIZIO = (r"(?:^|[.;:!?,]\s*|(?<![a-zà-ù])(?:e|poi|quindi|allora|subito|ora|adesso|ma|oppure|o|"
           r"per favore|prima)\s+)(?:per favore\s+|subito\s+|prima\s+)?(")
_IMPERATIVO = re.compile(_INIZIO + _RISCHIO_IMP + r")[a-zà-ù']*", re.I)
_IMPERATIVO_CASA = re.compile(_INIZIO + _CASA_IMP + r")[a-zà-ù']*", re.I)
# Un infinito o un gerundio dentro un elenco («posso fare conti, comandare luci e scaricare
# fonti», prova e2e del 06/10) non è un ordine alla persona. In testa alla frase invece sì:
# «Chiamare subito il numero…» è l'imperativo degli avvisi
_NON_IMPERATIVO = re.compile(r"(are|ere|ire|ando|endo)(l[oiae]|gli\w*|mi|ti|ci|vi|si|ne|"
                             r"me\w*|te\w*|ce\w*|se\w*)?$", re.I)
# Un invito a mandare qualcosa a Calliope stessa («mandamelo pure», «inviami la foto»): la
# persona lo dà a lei, non a un recapito preso dal dato
_A_CALLIOPE = re.compile(r"^(mand|invi|inoltr|dett|comunic|fornisc|condivid)[a-zà-ù]*?"
                         r"(mi|me(l[oiae]|ne))$", re.I)
_MODALI = (r"(?<![a-zà-ù])(devi|dovrai|dovresti|ti conviene|conviene|è necessario|e' necessario|"
           r"è importante|è obbligatorio|bisogna|occorre|serve che tu|ricordati di|"
           r"non dimenticare di|assicurati di|ti chiedo di|ti invito a|ti consiglio di|"
           r"ti raccomando di|ti suggerisco di|è urgente|urgentemente|hai bisogno di)(?![a-zà-ù])"
           r"(?:\s+[a-zà-ù']+){0,3}?\s+(?:subito\s+|prima\s+)?(")
# Qualunque indicazione rivolta alla persona («ti suggerisco di tenere pronta la password»):
# per i segreti basta questa
_DIRETTA = re.compile(_MODALI.rsplit(r"(?:\s+[a-zà-ù']+)", 1)[0]
                      + r"|(?<![a-zà-ù])tieni (pront|a portata)\w*", re.I)
_MODALE = re.compile(
    _MODALI + r"chiamar|telefonar|contattar|richiamar|scriver|mandar|inviar|inoltrar|visitar|"
    r"andare su|cliccar|acceder|registrar|scaricar|installar|inserir|digitar|comunicar|fornir|"
    r"dettar|trasferir|autorizzar|comandar|chieder|dir[mlg]|risponder|condivider)[a-zà-ù']*",
    re.I)
_MODALE_CASA = re.compile(_MODALI + r"aprir|accender|spegner|sbloccar|disattivar|chiuder)"
                          r"[a-zà-ù']*", re.I)
# Ciò che riguarda la casa o Calliope stessa: un'indicazione così non si ripete mai
_DELICATO = re.compile(
    r"(?<![a-zà-ù])(cancell[oi]|garage|box|portone|porta|serratur\w*|allarm\w*|antifurto|"
    r"telecamer\w*|caldaia|gas|calliope|assistent[ei]|comand\w*|consenso|"
    # «chiedimi di aprire…», «dimmi di sbloccare…»: farsi chiedere un'azione; «chiedimi pure»
    # e «chiedimi di una per sapere…» (frase pronta del registro delle capacità) no
    r"(chiedimi|dimmi) di [a-zà-ù]+(are|ere|ire)[a-zà-ù]*)(?![a-zà-ù])", re.I)
# La frase dice da dove viene: «secondo la pagina…», «il documento dice…»
_ATTRIBUZIONE = re.compile(
    r"(?<![a-zà-ù])(secondo|stando a(l|lla|i|lle|llo)?|in base a(l|lla|i|lle)?|si legge|c'è "
    r"scritto|ho trovato|ho letto|leggo|mi risulta|risulta che|dalla ricerca|nei risultati|"
    r"in rete|online|sul sito|c'è "
    r"scritto|c'era scritto|è scritto|riportat\w*|"
    # Il resoconto di una richiesta del dato, col soggetto sottinteso («Inoltre, ti chiede di
    # confermare la presenza all'amministratore», misura del 06/10): dice da dove viene
    r"(ti|vi|ci) (chied\w*|invit\w*|preg\w*|ricord\w*) di|"
    r"(pagin\w*|sit[oi]|document\w*|file|bollett\w*|letter\w*|messaggi\w*|vocal\w*|articol\w*|"
    r"risultat\w*|agente|estension\w*|foto|scontrin\w*|mail|email|test[oi]|avvis\w*|fonte|"
    r"riassunt\w*|foglio|nota|comunicat\w*|annunci\w*)\s+(\w+\s+){0,3}?"
    r"(dic[eo]|dicono|scriv\w*|riport\w*|indic\w*|consigli\w*|suggerisc\w*|chied\w*|invit\w*|"
    r"afferm\w*|parl\w*|cit\w*|contien\w*|segnal\w*|raccomand\w*|spieg\w*))", re.I)
# La persona ha chiesto un recapito, o come si fa una cosa
_CHIEDE_CONTATTO = re.compile(
    r"(?<![a-zà-ù])(numer\w*|telefon\w*|chiam\w*|contatt\w*|sit[oi]|indirizz\w*|e-?mail|mail|"
    r"link|recapit\w*|pagina web|scriv\w*|whatsapp|cellulare)", re.I)
_COME_SI_FA = re.compile(
    r"(?<![a-zà-ù])(come|dove|cosa devo|che devo|cosa faccio|che faccio|cosa posso|cosa "
    r"bisogna|cosa serve|cosa servono|chi (devo |posso )?(chiam|contatt|sent)\w*|"
    r"quale (numero|sito)|a chi)(?![a-zà-ù])", re.I)

# Le frasi fisse al posto di quelle fermate (una sola per tipo in una risposta)
FRASI = {
    "uscita_numero_pagamento": "C'è anche un numero a pagamento preso {da}: non lo "
                               "ripeto, potrebbe essere una truffa.",
    "uscita_segreti": "{Fonte} chiede anche dei codici o delle password: non lo ripeto. Non "
                      "darli a nessuno senza controllare chi li chiede.",
    "uscita_soldi": "{Fonte} chiede anche dei soldi: non lo ripeto, potrebbe essere una truffa.",
    "uscita_contatto": "C'è anche un recapito preso {da}: te lo dico solo se me lo "
                       "chiedi.",
    "uscita_istruzione": "{Fonte} contiene anche delle indicazioni che non vengono da te: non "
                         "le ripeto.",
}
REGOLE = tuple(FRASI)


@dataclass
class Giudizio:
    esito: str = OK                 # OK o il nome della regola
    fonte: str = ""
    dettaglio: str = ""
    frase: str = ""                 # la frase da dire (OK: quella, eventualmente con la fonte)


@dataclass
class Contesto:
    """Quello che serve per giudicare una frase: le fonti non fidate della conversazione, i
    loro testi, le parole della persona in questo turno (e nella conversazione)."""
    fonti: frozenset = frozenset()
    esterni: list = field(default_factory=list)         # [(fonte, testo)]
    domanda: str = ""                                   # la frase di questo turno
    persona_txt: str = ""                               # tutte le parole della persona
    propri: tuple = ()                                  # frasi pronte dei tool fidati (_norm)

    @property
    def contaminata(self) -> bool:
        return bool(self.fonti)

    def fonte(self) -> str:
        return sorted(self.fonti)[0] if self.fonti else ""


def _fonte_di(ctx: Contesto, pezzo: str, normalizza=lambda s: s.lower()) -> str:
    """La fonte del primo dato non fidato che contiene `pezzo` (normalizzato), o ""."""
    p = normalizza(pezzo)
    if not p:
        return ""
    for f, testo in ctx.esterni:
        if p in normalizza(testo):
            return f
    return ""


def _dal_dato(ctx: Contesto, pezzo: str, normalizza=lambda s: s.lower()) -> str:
    """Il pezzo (un recapito) viene da un dato non fidato e non dalla persona? Con una foto
    di mezzo (nessun testo da confrontare) vale se la persona non l'ha detto."""
    if normalizza(pezzo) and normalizza(pezzo) in normalizza(ctx.persona_txt + " " + ctx.domanda):
        return ""
    f = _fonte_di(ctx, pezzo, normalizza)
    if f:
        return f
    if "foto" in ctx.fonti:
        return "foto"
    return ""


def _parole_dal_dato(ctx: Contesto, frase: str) -> tuple[list[str], str]:
    """Le parole significative della frase che stanno in un dato non fidato e non nella
    domanda di questo turno; con una foto, quelle che la persona non ha mai detto."""
    fuori, f = prov.esterne(frase, ctx.domanda, ctx.esterni)
    if fuori:
        return fuori, f
    if "foto" in ctx.fonti:
        nuove = sorted(prov.parole(frase) - prov.parole(ctx.persona_txt + " " + ctx.domanda))
        if nuove:
            return nuove, "foto"
    return [], ""


def _solo_foto(ctx: Contesto, frase: str) -> bool:
    """Le parole «dal dato» vengono solo dal ripiego della foto (nessun testo le contiene)?"""
    return "foto" in ctx.fonti and not prov.esterne(frase, ctx.domanda, ctx.esterni)[0]


# I nomi di Calliope e dei pulsanti delle sue pagine: non portano fuori
_NOMI_PROPRI = frozenset("calliope allega foto parla scrivi invia microfono compila".split())


def _bersaglio(frase: str, ctx: Contesto) -> bool:
    """Nella frase c'è un bersaglio che la persona non ha detto: un nome proprio (maiuscola
    non in testa alla frase) o un numero."""
    detto = (ctx.persona_txt + " " + ctx.domanda).lower()
    for m in re.finditer(r"(?<=[\w,;:'] )([A-ZÀ-Ù][\wà-ù]+)|(\d[\d .]*\d|\d)", frase or ""):
        w = (m.group(1) or m.group(2) or "").strip()
        if w and w.lower() not in detto and w.lower() not in _NOMI_PROPRI:
            return True
    return False


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9à-ù]", "", (s or "").lower())


def propria(frase: str, ctx: Contesto) -> bool:
    """La frase è una frase pronta di Calliope (risposta_finale o conferma di un tool fidato
    di questa conversazione, già scritta dal codice): non viene da un dato."""
    n = _norm(frase)
    return len(n) >= 12 and any(n in p for p in ctx.propri)


def indicazione(frase: str) -> bool:
    """La frase dà un'indicazione alla persona (imperativo o «devi…») con un verbo del lessico
    del rischio (contatti, siti, codici, Calliope), o con un verbo della casa e un oggetto
    delicato («apri il cancello»)?"""
    f = frase or ""

    def trova(rx):
        # «ti consiglio di non rispondere a quell'email»: un avvertimento, non un'indicazione
        for m in rx.finditer(f):
            if re.search(r"(?<![a-zà-ù])(non|mai)(?![a-zà-ù])", m.group(0), re.I):
                continue
            if rx is _IMPERATIVO or rx is _IMPERATIVO_CASA:
                verbo = m.group(0).split()[-1].strip(".,;:!?'") if m.group(0).split() else ""
                prima = m.group(0)[:len(m.group(0)) - len(verbo)].strip(" .;:!?")
                if _NON_IMPERATIVO.search(verbo) and prima:
                    continue
                if _A_CALLIOPE.match(verbo):
                    continue
            return True
        return False

    if trova(_IMPERATIVO) or trova(_MODALE):
        return True
    return bool((trova(_IMPERATIVO_CASA) or trova(_MODALE_CASA)) and _DELICATO.search(f))


def attribuita(frase: str) -> bool:
    return bool(_ATTRIBUZIONE.search(frase or ""))


def giudica(frase: str, ctx: Contesto, solo_gravi: bool = False) -> Giudizio:
    """Il giudizio su una frase che Calliope sta per dire. Con la conversazione pulita: OK.
    `solo_gravi`: solo numeri a pagamento, segreti, soldi e indicazioni sulla casa o su
    Calliope (gli annunci dei lavori: la persona ha chiesto il lavoro, e un recapito o un
    consiglio nel risultato possono essere proprio ciò che voleva)."""
    if not ctx.contaminata or not (frase or "").strip():
        return Giudizio(OK, frase=frase)
    t = frase
    persona = ctx.domanda
    # 1. Numeri a pagamento: con un dato non fidato di mezzo, sempre (anche se il dato li
    # scrive in un altro modo, o se è passato dalla quarantena); se la persona non li ha detti
    tel = telefoni(t)
    for n in tel:
        if a_pagamento(n) and _cifre(n) not in _cifre(ctx.domanda):
            return Giudizio("uscita_numero_pagamento",
                            _dal_dato(ctx, n, _cifre) or ctx.fonte(), n)
    # 2. Codici, password, PIN da dare: se la persona non ne ha parlato
    m = _SEGRETO.search(t)
    if m and (_DARE.search(t) or _DIRETTA.search(t)) and not _SEGRETO.search(persona):
        return Giudizio("uscita_segreti", ctx.fonte(), m.group(0))
    # 3. Soldi: IBAN, carte regalo, criptovalute; un pagamento verso un conto detto come ordine
    iban = _IBAN.search(t)
    if iban and _dal_dato(ctx, iban.group(0), lambda s: re.sub(r"\s", "", s).upper()):
        return Giudizio("uscita_soldi", ctx.fonte(), "iban")
    carta = _CARTA.search(t)
    if carta and 13 <= len(_cifre(carta.group(0))) <= 19 and _dal_dato(ctx, carta.group(0),
                                                                        _cifre):
        return Giudizio("uscita_soldi", ctx.fonte(), "numero di carta")
    # Carte regalo, criptovalute, ricariche: detto come un ordine, o senza dire da dove viene
    # («il messaggio chiede di ricaricare una Postepay» resta: è il resoconto, senza numeri)
    if (_SOLDI_SEMPRE.search(t) and not _SOLDI_SEMPRE.search(persona)
            and (indicazione(t) or not attribuita(t))):
        return Giudizio("uscita_soldi", ctx.fonte(), _SOLDI_SEMPRE.search(t).group(0))
    if _PAGARE.search(t) and _DESTINO.search(t) and indicazione(t):
        fuori, f = _parole_dal_dato(ctx, t)
        if fuori:
            return Giudizio("uscita_soldi", f, ", ".join(fuori[:3]))
    if solo_gravi:
        if indicazione(t) and _DELICATO.search(t) and not _DELICATO.search(persona):
            fuori, f = _parole_dal_dato(ctx, t)
            if fuori:
                return Giudizio("uscita_istruzione", f or ctx.fonte(), ", ".join(fuori[:3]))
        return Giudizio(OK, frase=frase)
    # Una frase pronta di Calliope (il registro delle capacità: «…comandare luci… Chiedimi di
    # una per sapere come sistemarla.»): non viene dal dato
    if propria(t, ctx):
        return Giudizio(OK, frase=frase)
    # 4. Recapiti presi dal dato, non chiesti
    recapiti = ([(n, _cifre) for n in tel]
                + [(s, str.lower) for s in siti(t, citati=indicazione(t))]
                + [(e, str.lower) for e in email(t)])
    da_dato = [(r, f) for r, norm in recapiti for f in [_dal_dato(ctx, r, norm)] if f]
    # Chiesto: un recapito («qual è il numero…»), o come / dove si fa una cosa («dove si
    # comprano i biglietti?»: la risposta è un sito)
    chiesto = bool(_CHIEDE_CONTATTO.search(persona) or _COME_SI_FA.search(persona)
                   or re.search(r"(?<![a-zà-ù])dove(?![a-zà-ù])", persona, re.I))
    if da_dato and not chiesto:
        return Giudizio("uscita_contatto", da_dato[0][1], da_dato[0][0])
    # 5. Indicazioni rivolte alla persona con parole che vengono dal dato
    if indicazione(t):
        fuori, f = _parole_dal_dato(ctx, t)
        delicata = bool(_DELICATO.search(t)) and not _DELICATO.search(persona)
        if fuori and not delicata and _solo_foto(ctx, t) and not _bersaglio(t, ctx):
            # Con una foto senza testo da confrontare ogni parola mai detta sembrava presa
            # dalla foto: «mandalo pure, lo leggo appena arriva» diventava «una foto contiene
            # delle indicazioni» (e2e del 06/10). Senza un bersaglio che la persona non ha
            # detto (un nome proprio, un numero) un'indicazione non porta da nessuna parte
            fuori = []
        if fuori and (delicata or not (attribuita(t) or _COME_SI_FA.search(persona)
                                       or (chiesto and da_dato))):
            return Giudizio("uscita_istruzione", f or ctx.fonte(), ", ".join(fuori[:3]))
    # Un recapito chiesto, preso dal dato: si dice con la fonte davanti
    if da_dato and not attribuita(t):
        f = da_dato[0][1]
        t = f"Secondo {prov.detta(f)}, " + (t[:1].lower() + t[1:] if t[1:2].islower() else t)
        return Giudizio(OK, f, "fonte aggiunta", t)
    return Giudizio(OK, frase=frase)


def sostituta(g: Giudizio) -> str:
    fonte = prov.detta(g.fonte) if g.fonte else "un testo scritto da altri"
    return FRASI[g.esito].format(fonte=fonte, Fonte=fonte[:1].upper() + fonte[1:],
                                 da=prov.da(g.fonte) if g.fonte else "da un testo scritto da altri")


def contesto_da(brain, domanda: str) -> Contesto:
    """Il contesto dallo stato di Brain (la storia della conversazione in corso: i risultati
    dei tool di questa risposta ci sono già)."""
    hist = getattr(brain, "history", None) or []
    fonti = prov.fonti(hist)
    if getattr(brain, "_in_vista", None):
        fonti.add("foto")
    if not fonti:
        return Contesto(domanda=domanda)
    esterni = prov.testi_esterni(hist)
    try:
        esterni += list(getattr(brain._c(), "esterni", None) or [])
    except Exception:  # noqa: BLE001
        pass
    return Contesto(frozenset(fonti), esterni, domanda, prov.testo_persona(hist),
                    tuple(_propri(hist)))


def _propri(hist) -> list[str]:
    """Le frasi pronte (risposta_finale, conferma, da_dire) dei risultati dei tool fidati
    nella storia, normalizzate; mai quelle di un risultato con un dato non fidato."""
    import json
    out = []
    for m in hist or ():
        c = m.get("content")
        if (m.get("role") != "tool" or not isinstance(c, str) or m.get("_fonte")
                or "dato_non_fidato" in c or "DATO NON FIDATO" in c):
            continue
        try:
            d = json.loads(c)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(d, dict):
            for k in ("risposta_finale", "conferma", "da_dire"):
                if isinstance(d.get(k), str) and d[k].strip():
                    out.append(_norm(d[k]))
    return out


@dataclass
class Esito:
    """Cosa è successo in una risposta (per il registro dei turni e la storia)."""
    fermate: list = field(default_factory=list)         # [(regola, fonte, dettaglio)]
    detto: list = field(default_factory=list)
    sostitute: list = field(default_factory=list)       # le frasi fisse dette
    ms: list = field(default_factory=list)
    fonte_aggiunta: int = 0


def filtra(brain, frasi, domanda: str, esito: Esito):
    """Le frasi della risposta (già divise) che si possono dire. Generatore: ogni frase si
    giudica appena arriva (qualche decimo di millisecondo, nessuna attesa in più per la voce);
    il contesto si rilegge a ogni frase, perché un risultato non fidato può arrivare a metà
    risposta. Una frase fermata diventa la sua frase fissa (una per tipo); le altre passano."""
    dette: set[str] = set()
    cache: dict = {}
    try:
        for frase in frasi:
            t0 = time.perf_counter()
            chiave = (len(getattr(brain, "history", None) or []), bool(getattr(brain, "_in_vista",
                                                                              None)))
            if cache.get("k") != chiave:
                cache["k"], cache["ctx"] = chiave, contesto_da(brain, domanda)
            g = giudica(frase, cache["ctx"])
            esito.ms.append(round((time.perf_counter() - t0) * 1000, 2))
            if g.esito == OK:
                if g.frase != frase:
                    esito.fonte_aggiunta += 1
                esito.detto.append(g.frase)
                yield g.frase
                continue
            esito.fermate.append((g.esito, g.fonte, g.dettaglio))
            print(f"\n   [USCITA] frase fermata: {g.esito} (dati da {g.fonte or '?'})",
                  flush=True)
            if g.esito in dette:
                continue
            dette.add(g.esito)
            s = sostituta(g)
            esito.detto.append(s)
            esito.sostitute.append(s)
            yield s
    finally:
        try:
            frasi.close()
        except Exception:  # noqa: BLE001
            pass


def controlla_testo(testo: str, fonte: str, persona_txt: str = "",
                    domanda: str = "") -> tuple[str, list]:
    """Un testo detto per intero da una fonte non fidata (l'annuncio con il riassunto di un
    agente, il risultato di un'estensione): le frasi fermate diventano le frasi fisse. Il testo
    stesso è il dato. Restituisce (testo da dire, [regole])."""
    from .tts import split_sentences
    ctx = Contesto(frozenset({fonte}), [(fonte, testo)], domanda, persona_txt)
    out, regole, dette = [], [], set()
    for s in split_sentences([testo]):
        g = giudica(s, ctx, solo_gravi=True)
        if g.esito == OK:
            out.append(s)
            continue
        regole.append(g.esito)
        if g.esito not in dette:
            dette.add(g.esito)
            out.append(sostituta(g))
    return " ".join(out).strip(), regole
