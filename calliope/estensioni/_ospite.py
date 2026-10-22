"""
calliope_estensione: il runtime di un'estensione di Calliope (04/10/2026). Solo libreria
standard. Non si importa da Calliope: si monta in sola lettura nel container come
/opt/calliope/calliope_estensione.py e si lancia così:

    python -I -B -X utf8 /opt/calliope/calliope_estensione.py /lavoro

L'estensione (estensione.py nella cartella) definisce

    def esegui(dati: dict, calliope) -> dict:
        ...
        return {"da_dire": "10 chilometri sono 6,2 miglia.", "valore": 6.21}

e chiede a Calliope tutto quello che le serve con i metodi di `calliope` (porta stretta):
casa_stato, casa_comando, lista_leggi, lista_aggiungi, lista_togli, agenda_elenca,
timer_imposta, schermo_mostra, dati_leggi, dati_scrivi, dati_elenca, dati_cancella,
rete_leggi, rete_invia. Ognuno può alzare ErroreCalliope (permesso non concesso, azione
negata dalla persona, quota superata): l'estensione la gestisce o la lascia salire.

Protocollo: JSON-RPC 2.0, un messaggio per riga su stdin/stdout, come il trasporto stdio di
MCP (`tools/list`, `tools/call` con risultato MCP). Le richieste dell'estensione a Calliope
sono richieste JSON-RPC nell'altro senso, con metodi «calliope/<azione>». Le `print`
dell'estensione vanno su stderr: stdout è del protocollo.

Per i test dell'estensione c'è `CalliopeFinta`: risposte preparate e l'elenco delle richieste.
Come la porta vera, rifiuta un indirizzo con spazi o caratteri non codificati (08/10): i
parametri si scrivono con urllib.parse.urlencode o quote, mai a mano. Una possibile doppia
codifica («Borgo%2BAlto»: quote_plus e poi urlencode) non la rifiuta: la scrive in
`avvisi` e su stderr.

Dal 22/10 (issue #228, § 3.5 n. 33 e 36 della ricerca del 19/10 sulla solidità dell'agente)
CalliopeFinta si costruisce dal manifesto della cartella: un'azione che il manifesto non
dichiara, e una lettura senza risposta preparata, sono un `ErroreDelTest` («è il test: …»)
invece di un `{"ok": True}` che faceva uscire un KeyError in estensione.py. E `chiama(dati,
risposte=…, negate=…)`, che i test usano, sta qui (in sola lettura) e non più nel file di test
che l'agente può riscrivere.
"""

import json
import os
import sys


class ErroreCalliope(Exception):
    """Calliope non ha fatto quello che l'estensione chiedeva: il messaggio dice perché."""


class ErroreDelTest(BaseException):
    """Lo alza CalliopeFinta quando a non andare è il test o il manifesto, non l'estensione:
    un'azione che il manifesto non dichiara (con quel manifesto la porta non la lascerebbe
    passare) o una lettura senza risposta preparata. Non è un'Exception apposta (come SystemExit): un «except Exception»
    dell'estensione non lo nasconde dietro un da_dire di ripiego, e unittest lo conta come
    errore del test con il suo messaggio."""


# I permessi del manifesto visti da CalliopeFinta (22/10, #228): la stessa regola di
# guardrail.valuta_porta per il permesso e lo scope di ogni azione (le stanze, le liste, gli host,
# lo schema dell'indirizzo), copiata perché questo file non importa Calliope;
# prova_contratto_estensioni controlla che dicano lo stesso su una griglia di manifesti e che lo
# scope suggerito sia quello del contratto (contratto.PORTA). La fonte resta una sola: i permessi
# del manifesto come li legge la porta (con le concessioni della decisione 0033 cambiano lì, e la
# prova lo dice). Ciò che dipende dall'esecuzione (quote, flussi dopo una lettura di dati di
# casa, conferme della persona) lo controlla solo la porta vera, al collaudo.
_SCOPE_AZIONE = {
    "casa_stato": "legge.casa", "casa_comando": "scrive.casa", "lista_leggi": "legge.liste",
    "lista_aggiungi": "scrive.liste", "lista_togli": "scrive.liste",
    "agenda_elenca": "legge.agenda", "timer_imposta": "scrive.agenda",
    "schermo_mostra": "scrive.schermi", "dati_leggi": "scrive.dati", "dati_scrivi": "scrive.dati",
    "dati_elenca": "scrive.dati", "dati_cancella": "scrive.dati",
    "rete_leggi": "rete.pubblica o rete.host", "rete_invia": "rete.host con rete.post",
}
# Le azioni che restituiscono dati: senza una risposta preparata il test non può sapere cosa
# risponderebbe Calliope. Le altre (comandi, voci aggiunte o tolte, timer, schermo) riescono
# con {"ok": True}, come la porta quando l'azione va
_LETTURE_CON_RISPOSTA = ("casa_stato", "lista_leggi", "agenda_elenca", "rete_leggi",
                         "rete_invia")
# Le letture senza risposta con `letture="vuote"` (prima revisione della PR #231): la forma
# della porta senza niente dentro; la rete alza ErroreCalliope (nessuna risposta)
LETTURE_VUOTE = {"casa_stato": {"testo": "", "entita": []},
                 "lista_leggi": {"ok": True, "lista": "spesa", "voci": [], "numero": 0},
                 "agenda_elenca": {"voci": [], "numero": 0}}
# Come calliope/liste._LIST_WORDS (list_key): «la lista della spesa» → «spesa»
_PAROLE_LISTA = (r"\b(la|nella|alla|dalla|sulla)?\s*lista\b|^\s*(della|delle|dei|degli|"
                 r"del|dello|di|per|la|le|il|i)\s+")


def _lista(nome):
    import re
    n = (str(nome or "")).lower().strip(" .,!?")
    for _ in range(3):
        n = re.sub(_PAROLE_LISTA, " ", n, flags=re.I).strip()
    return re.sub(r"\s+", " ", n) or "spesa"


def _host(url):
    from urllib.parse import urlsplit
    try:
        return (urlsplit(str(url or "")).hostname or "").rstrip(".").lower()
    except ValueError:
        return ""


def _nomi_scope(v, lista=False):
    """Come manifesto._nomi, ma senza mai rifiutare: true → ["*"], un elenco → i nomi."""
    if isinstance(v, dict):
        v = v.get("stanze", v.get("nomi", v.get("liste")))
    if v is True:
        return ["*"]
    if not v:
        return []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, (list, tuple)):
        return []
    out = []
    for x in v:
        s = " ".join(str(x).split()).strip().lower()
        out.append("*" if s == "*" else (_lista(s) if lista else s))
    return ["*"] if "*" in out else out


def permessi_scope(p):
    """I permessi del manifesto nella forma a scope (come manifesto.normalizza_permessi, anche
    dal formato del 04/10), senza i controlli di forma: quelli sono in motivo_permessi."""
    p = p if isinstance(p, dict) else {}
    if not ({"legge", "scrive", "invia"} & set(p)) and not isinstance(p.get("rete"), dict):
        def lv(sez, voce):
            v = p.get(sez) or []
            return voce in (v if isinstance(v, list) else [v])
        hosts = p.get("rete") if isinstance(p.get("rete"), list) else []
        p = {"legge": {"casa": lv("casa", "leggi"), "liste": lv("liste", "leggi"),
                       "agenda": lv("agenda", "leggi"), "dati": bool(p.get("dati"))},
             "scrive": {"casa": lv("casa", "comanda"), "liste": lv("liste", "scrivi"),
                        "agenda": lv("agenda", "scrivi"), "dati": bool(p.get("dati")),
                        "schermi": bool(p.get("schermi"))},
             "rete": {"pubblica": False, "host": hosts, "post": bool(p.get("rete_invia"))},
             "invia": []}
    le = p.get("legge") if isinstance(p.get("legge"), dict) else {}
    sc = p.get("scrive") if isinstance(p.get("scrive"), dict) else {}
    r = p.get("rete") or {}
    if isinstance(r, list):
        r = {"host": r}
    if not isinstance(r, dict):
        r = {}
    hosts = r.get("host") if isinstance(r.get("host"), list) else []
    invia = []
    for f in p.get("invia") if isinstance(p.get("invia"), list) else ():
        if isinstance(f, dict):
            invia.append({"dati": str(f.get("dati") or "").strip().lower(),
                          "host": str(f.get("host") or "").strip().lower().rstrip("."),
                          "metodo": str(f.get("metodo") or "GET").upper()})
    return {"legge": {"casa": _nomi_scope(le.get("casa")),
                      "liste": _nomi_scope(le.get("liste"), True),
                      "agenda": bool(le.get("agenda")), "dati": bool(le.get("dati"))},
            "scrive": {"casa": _nomi_scope(sc.get("casa")),
                       "liste": _nomi_scope(sc.get("liste"), True),
                       "agenda": bool(sc.get("agenda")), "dati": bool(sc.get("dati")),
                       "schermi": bool(sc.get("schermi"))},
            "rete": {"pubblica": bool(r.get("pubblica")),
                     "host": [str(h).strip().lower().rstrip(".") for h in hosts],
                     "post": bool(r.get("post"))},
            "invia": invia}


# Come manifesto.HOST e manifesto._host: solo nomi pubblici
_HOST_OK = r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
_HOST_NO = (".local", ".lan", ".home", ".internal", ".localdomain", ".intranet", ".corp",
            ".localhost", ".test", ".invalid", ".example", ".arpa")


def _host_non_valido(h):
    import re
    h = str(h).strip().lower().rstrip(".")
    return "" if re.match(_HOST_OK, h) and not h.endswith(_HOST_NO) else f"host non valido «{h}»"


def _nomi_non_validi(v, cosa):
    if isinstance(v, dict):
        v = v.get("stanze", v.get("nomi", v.get("liste")))
    if v is True or not v:
        return ""
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or len(v) > 10:
        return f"«{cosa}»: true oppure un elenco di al più 10 nomi"
    for x in v:
        s = " ".join(str(x).split()).strip()
        if not s or len(s) > 40:
            return f"«{cosa}»: nome non valido"
    return ""


def motivo_permessi(p):
    """"" se i «permessi» passano manifesto.normalizza_permessi, se no il motivo (22/10, prima
    revisione della PR #231): con permessi così la porta non dà niente
    (guardrail._scope → nessun permesso), e la Calliope finta nemmeno."""
    p = p or {}
    if not isinstance(p, dict):
        return "«permessi» deve essere un oggetto"
    if not ({"legge", "scrive", "invia"} & set(p)) and not isinstance(p.get("rete"), dict):
        # Il formato del 04/10 (manifesto._vecchio_formato)
        noti = {"casa": ("leggi", "comanda"), "liste": ("leggi", "scrivi"),
                "agenda": ("leggi", "scrivi")}
        altri = [k for k in p if k not in set(noti) | {"schermi", "dati", "rete", "rete_invia"}]
        if altri:
            return f"permesso sconosciuto: {', '.join(map(str, altri))}"
        for sez, ammessi in noti.items():
            v = p.get(sez) or []
            if isinstance(v, str):
                v = [v]
            if not isinstance(v, list) or any(x not in ammessi for x in v):
                return f"«permessi.{sez}»: solo {', '.join(ammessi)}"
        hosts = p.get("rete") or []
        if not isinstance(hosts, list):
            return "«permessi.rete»: un elenco di host"
        if p.get("rete_invia") and not hosts:
            return "«permessi.rete_invia» senza host in «permessi.rete»"
        p = {"rete": {"host": hosts}}
    altri = [k for k in p if k not in ("legge", "scrive", "rete", "invia")]
    if altri:
        return f"permesso sconosciuto: {', '.join(map(str, altri))}"
    le, sc = p.get("legge") or {}, p.get("scrive") or {}
    if not isinstance(le, dict) or not isinstance(sc, dict):
        return "«legge» e «scrive» sono oggetti"
    for sez, d, noti in (("legge", le, ("casa", "liste", "agenda", "dati")),
                         ("scrive", sc, ("casa", "liste", "agenda", "dati", "schermi"))):
        altri = [k for k in d if k not in noti]
        if altri:
            return f"«{sez}»: sconosciuto {', '.join(map(str, altri))}"
        for k in ("casa", "liste"):
            m = _nomi_non_validi(d.get(k), f"{sez}.{k}")
            if m:
                return m
    r = p.get("rete") or {}
    if isinstance(r, list):
        r = {"host": r}
    if not isinstance(r, dict) or any(k not in ("pubblica", "host", "post") for k in r):
        return "«rete»: pubblica, host, post"
    hosts = r.get("host") or []
    if not isinstance(hosts, list) or len(hosts) > 5:
        return "«rete.host»: un elenco di al più 5 host"
    for h in hosts:
        if _host_non_valido(h):
            return _host_non_valido(h)
    if r.get("post") and not hosts:
        return "«rete.post» senza host in «rete.host»"
    flussi = p.get("invia") or []
    if not isinstance(flussi, list) or len(flussi) > 6:
        return "«invia»: un elenco di al più 6 flussi"
    legge = permessi_scope({"legge": le})["legge"]
    for f in flussi:
        if not isinstance(f, dict) or any(k not in ("dati", "host", "metodo") for k in f):
            return "«invia»: ogni flusso è {dati, host, metodo}"
        dati = str(f.get("dati") or "").strip().lower()
        cat, _, nome = dati.partition(":")
        if cat not in ("casa", "agenda", "liste") or (nome and cat != "liste"):
            return f"«invia.dati» non valido: «{dati}»"
        if not legge[cat] or (nome and "*" not in legge["liste"]
                              and _lista(nome) not in legge["liste"]):
            return f"«invia»: il flusso di «{dati}» vuole il permesso di leggerli in «legge»"
        if str(f.get("metodo") or "GET").upper() not in ("GET", "POST"):
            return "«invia.metodo»: GET o POST"
        if _host_non_valido(f.get("host") or ""):
            return _host_non_valido(f.get("host") or "")
    return ""


def _stanza_ok(nomi, testo):
    if "*" in nomi:
        return True
    t = " " + " ".join(str(testo or "").lower().split()) + " "
    return any(f" {n} " in t or f"'{n} " in t for n in nomi)


def permesso_mancante(azione, argomenti, permessi):
    """"" se il manifesto con questi `permessi` lascia passare l'azione con questi argomenti
    alla porta (permesso e scope, come guardrail.valuta_porta); se no il motivo in parole."""
    a = argomenti or {}
    invalidi = motivo_permessi(permessi)
    if invalidi:
        return f"i permessi del manifesto non sono validi ({invalidi}): così non vale nessuno"
    sc = permessi_scope(permessi)
    le, scr, rete = sc["legge"], sc["scrive"], sc["rete"]
    if azione in ("casa_stato", "casa_comando"):
        nomi = le["casa"] if azione == "casa_stato" else scr["casa"]
        if not nomi:
            return "non dichiarata"
        testo = a.get("cosa") if azione == "casa_stato" else a.get("comando")
        if not _stanza_ok(nomi, testo):
            return f"fuori dallo scope: solo le stanze {', '.join(nomi)}"
        return ""
    if azione in ("lista_leggi", "lista_aggiungi", "lista_togli"):
        nomi = le["liste"] if azione == "lista_leggi" else scr["liste"]
        if not nomi:
            return "non dichiarata"
        lista = _lista(a.get("lista") or "spesa")
        if "*" not in nomi and lista not in nomi:
            return f"fuori dallo scope: la lista «{lista}» (il manifesto ha {', '.join(nomi)})"
        return ""
    if azione in ("agenda_elenca", "timer_imposta", "schermo_mostra"):
        ok = {"agenda_elenca": le["agenda"], "timer_imposta": scr["agenda"],
              "schermo_mostra": scr["schermi"]}[azione]
        return "" if ok else "non dichiarata"
    if azione in ("dati_leggi", "dati_elenca"):
        return "" if le["dati"] or scr["dati"] else "non dichiarata"
    if azione in ("dati_scrivi", "dati_cancella"):
        return "" if scr["dati"] else "non dichiarata"
    if azione not in ("rete_leggi", "rete_invia"):
        return "non è un'azione che Calliope offre"
    url = str(a.get("url") or "").strip()
    host = _host(url)
    schema = url.split(":", 1)[0].lower() if ":" in url else ""
    if azione == "rete_leggi":
        if not (rete["pubblica"] or rete["host"] or sc["invia"]):
            return "non dichiarata"
        if schema not in ("http", "https") or not host:
            return "solo indirizzi http o https"
        if rete["pubblica"] or host in rete["host"] or any(f["host"] == host
                                                            for f in sc["invia"]):
            return ""
        return f"l'host «{host}» non è in «rete.host», e «rete.pubblica» non c'è"
    if not (rete["post"] or any(f["metodo"] == "POST" for f in sc["invia"])):
        return "non dichiarata"
    if schema not in ("http", "https") or not host:
        return "solo indirizzi http o https"
    hosts = set(rete["host"]) | {f["host"] for f in sc["invia"] if f["metodo"] == "POST"}
    if host not in hosts or (host in rete["host"] and not rete["post"]
                             and not any(f["host"] == host and f["metodo"] == "POST"
                                         for f in sc["invia"])):
        return f"l'invio verso «{host}» non è nel manifesto"
    if schema != "https":
        return "gli invii solo in https"
    return ""


# La stessa regola di calliope/web/pagina.url_non_codificato (questo file non importa
# Calliope: è copiata, e prova_estensioni_rete controlla che le due dicano lo stesso)
_URL_AMMESSI = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                         "-._~:/?#[]@!$&'()*+,;=%")


def url_non_codificato(url):
    """"" se percorso e parametri dell'URL sono codificati; se no il messaggio d'errore."""
    import re
    from urllib.parse import urlsplit
    percento = re.compile(r"%(?![0-9A-Fa-f]{2})")
    testo = str(url or "").strip()
    try:
        u = urlsplit(testo)
    except ValueError:
        return "URL non valido: non si riesce a leggere"
    i = testo.find(u.netloc) if u.netloc else -1
    resto = testo[i + len(u.netloc):] if i >= 0 else testo
    cattivo = next((c for c in resto if c not in _URL_AMMESSI), None)
    if cattivo is None and not percento.search(resto):
        return ""
    if cattivo is None:
        cosa = "un «%» non seguito da due cifre esadecimali"
    elif cattivo == " ":
        cosa = "uno spazio"
    elif ord(cattivo) < 32 or ord(cattivo) == 127:
        cosa = "un carattere di controllo"
    else:
        cosa = f"il carattere «{cattivo}» non codificato"
    dove = "nel percorso"
    for pezzo in (u.query.split("&") if u.query else ()):
        if (cattivo is not None and cattivo in pezzo) or (
                cattivo is None and percento.search(pezzo)):
            nome = pezzo.partition("=")[0]
            dove = (f"nel parametro «{nome[:40]}»"
                    if nome and all(c in _URL_AMMESSI for c in nome) else "nei parametri")
            break
    return (f"URL non valido: c'è {cosa} {dove}. Codifica i valori con urllib.parse.urlencode "
            "(o urllib.parse.quote per un pezzo del percorso), mai a mano nell'indirizzo: es. "
            "\"https://sito/cerca?\" + urlencode({\"nome\": valore})")


def doppia_codifica(url):
    """"" o l'avviso «possibile doppia codifica» (08/10 sera): la stessa regola di
    calliope/web/pagina.doppia_codifica, copiata. Un valore che decodificato una volta
    contiene ancora «%XX», o un «+» tra due lettere (era «%2B», un più letterale)."""
    import re
    from urllib.parse import unquote_plus, urlsplit
    try:
        u = urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    for pezzo in (u.query.split("&") if u.query else ()):
        nome, _, valore = pezzo.partition("=")
        if not valore:
            continue
        uno = unquote_plus(valore)
        if re.search(r"%[0-9A-Fa-f]{2}", uno):
            cosa = "«%25» è un «%» letterale"
        elif re.search(r"[^\W\d_]\+[^\W\d_]", uno):
            cosa = "«%2B» è un «+» letterale, mentre lo spazio è «+» o «%20»"
        else:
            continue
        dove = (f"nel parametro «{nome[:40]}»"
                if nome and all(c in _URL_AMMESSI for c in nome) else "nei parametri")
        return (f"possibile doppia codifica {dove}: {cosa}. Il valore è stato codificato due "
                "volte (per esempio quote_plus e poi urlencode): codifica una volta sola, con "
                "urlencode passa il testo com'è")
    return ""


def _chiave_url(url):
    """L'indirizzo per il confronto con le risposte vere: schema, host (minuscolo), percorso e
    i parametri com'erano scritti, in ordine alfabetico."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(str(url or "").strip())
    except ValueError:
        return str(url or "")
    q = sorted(u.query.split("&")) if u.query else []
    return (u.scheme.lower(), (u.netloc or "").lower(), u.path or "/", tuple(q))


class Calliope:
    """La porta stretta vista dall'estensione: ogni metodo è una richiesta a Calliope, che
    decide (permessi del manifesto, guardrail, conferma della persona)."""

    def __init__(self, chiedi):
        self._chiedi = chiedi

    def _c(self, azione, **argomenti):
        return self._chiedi(azione, {k: v for k, v in argomenti.items() if v is not None})

    # casa (permessi.casa: leggi, comanda)
    def casa_stato(self, cosa=""):
        """Com'è la casa («temperatura in camera», «cosa c'è acceso»): {testo, entita}."""
        return self._c("casa_stato", cosa=cosa)

    def casa_comando(self, comando):
        """Un comando nella forma di Home Assistant («accendi la luce della cucina»)."""
        return self._c("casa_comando", comando=comando)

    # liste (permessi.liste: leggi, scrivi)
    def lista_leggi(self, lista="spesa"):
        return self._c("lista_leggi", lista=lista)

    def lista_aggiungi(self, lista, voci):
        return self._c("lista_aggiungi", lista=lista, voci=list(voci))

    def lista_togli(self, lista, voci):
        return self._c("lista_togli", lista=lista, voci=list(voci))

    # agenda (permessi.agenda: leggi, scrivi)
    def agenda_elenca(self):
        return self._c("agenda_elenca")

    def timer_imposta(self, durata, nome=""):
        return self._c("timer_imposta", durata=durata, nome=nome)

    # schermi (permessi.schermi)
    def schermo_mostra(self, titolo, testo):
        return self._c("schermo_mostra", titolo=titolo, testo=testo)

    # dati propri (permessi.dati): testi piccoli, per nome
    def dati_leggi(self, nome):
        """Il testo salvato con questo nome, o None."""
        return self._c("dati_leggi", nome=nome).get("testo")

    def dati_scrivi(self, nome, testo):
        return self._c("dati_scrivi", nome=nome, testo=str(testo))

    def dati_elenca(self):
        return self._c("dati_elenca").get("nomi", [])

    def dati_cancella(self, nome):
        return self._c("dati_cancella", nome=nome)

    # rete (05/10): pagine pubbliche (permessi.rete.pubblica) o host precisi (rete.host); dopo
    # aver letto dati di casa solo verso gli host dei flussi in permessi.invia
    def rete_leggi(self, url):
        """{stato, tipo, testo} della risposta a una GET; il JSON si legge con json.loads."""
        return self._c("rete_leggi", url=url)

    def rete_invia(self, url, dati):
        """POST di `dati` (dict, mandato come JSON): solo verso gli host del manifesto con
        rete.post o un flusso POST, e sempre dopo il «sì» della persona."""
        return self._c("rete_invia", url=url, dati=dati)


class CalliopeFinta(Calliope):
    """Per i test: `risposte` = {azione: risultato o funzione(argomenti)}; `negate` = azioni
    che alzano ErroreCalliope. `richieste` registra ogni (azione, argomenti).

    Dal 22/10 (#228) segue il manifesto: `manifesto` è il dict del manifesto, o None per
    manifesto.json della cartella dove girano i test (senza il file nessun controllo), o False
    per nessun controllo. Un'azione che i permessi non lasciano passare (`permesso_mancante`) e
    una lettura senza risposta preparata alzano ErroreDelTest; i messaggi restano anche in
    `errori_test`, così `chiama` li rialza se l'estensione li ha inghiottiti.

    `letture="vuote"` (22/10, prima revisione della PR #231): una lettura senza risposta
    preparata risponde vuota (`LETTURE_VUOTE`: lo stato della casa senza niente, una lista e
    un'agenda vuote) e la rete alza ErroreCalliope come un servizio che non risponde. È per i
    test che l'agente non prepara: gli esempi di accettazione, in sola lettura, e il primo test
    di partenza (`chiama({})`). Il controllo dei permessi resta."""

    def __init__(self, risposte=None, negate=(), esempi_veri=True, manifesto=None,
                 letture="preparate"):
        self.risposte = dict(risposte or {})
        self.letture = "vuote" if letture == "vuote" else "preparate"
        self.negate = set(negate)
        self.richieste = []
        self.avvisi = []
        self.errori_test = []
        self.dati = {}
        self.permessi = self._permessi_del_manifesto(manifesto)
        # Le risposte vere dei collaudi (08/10 notte): per un indirizzo registrato in
        # esempi_veri/indice.json risponde quella, non la risposta preparata dal test (un test
        # che «trova» ciò che il servizio vero non trova fallisce). `vere`: gli indirizzi così
        self.esempi_veri = bool(esempi_veri)
        self.vere = []
        self._indice = None
        super().__init__(self._finta)

    def _permessi_del_manifesto(self, manifesto):
        """I «permessi» da seguire, o None (nessun controllo)."""
        if manifesto is False:
            return None
        if manifesto is None:
            try:
                with open(os.path.join(os.getcwd(), "manifesto.json"), encoding="utf-8") as f:
                    manifesto = json.load(f)
            except FileNotFoundError:
                return None
            except (OSError, ValueError) as e:
                # Un manifesto che non si legge lo dice la consegna; qui solo l'avviso
                self.avvisi.append(f"manifesto.json non si legge ({e}): niente controllo dei "
                                   "permessi")
                print(f"AVVISO di CalliopeFinta: {self.avvisi[-1]}", file=sys.stderr)
                return None
        if not isinstance(manifesto, dict):
            return None
        p = manifesto.get("permessi")
        return {} if p is None else p

    def _errore_test(self, testo):
        self.errori_test.append(testo)
        raise ErroreDelTest(testo)

    def _risposta_vera(self, url):
        """{stato, tipo, testo} della risposta vera registrata per questo indirizzo, o None.
        Solo quelle intere e non ripulite; l'indirizzo uguale a meno dell'ordine dei
        parametri. Cerca esempi_veri/indice.json nella cartella di lavoro (dove girano i
        test)."""
        if not self.esempi_veri:
            return None
        if self._indice is None:
            self._indice = {}
            base = os.getcwd()
            try:
                with open(os.path.join(base, "esempi_veri", "indice.json"),
                          encoding="utf-8") as f:
                    voci = json.load(f)
            except (OSError, ValueError):
                voci = []
            for v in voci if isinstance(voci, list) else ():
                if isinstance(v, dict) and v.get("url") and v.get("file") \
                        and not v.get("troncata") and not v.get("ripulita") \
                        and str(v["file"]).startswith("esempi_veri/") and ".." not in v["file"]:
                    self._indice[_chiave_url(v["url"])] = os.path.join(
                        base, *str(v["file"]).split("/"))
        percorso = self._indice.get(_chiave_url(url))
        if not percorso:
            return None
        try:
            with open(percorso, encoding="utf-8") as f:
                r = json.load(f).get("risposta") or {}
        except (OSError, ValueError, AttributeError):
            return None
        return {"stato": r.get("stato"), "tipo": r.get("tipo") or "",
                "testo": str(r.get("testo") or "")}

    def _finta(self, azione, argomenti):
        self.richieste.append((azione, argomenti))
        if azione in self.negate:
            raise ErroreCalliope(f"{azione}: negato (finto)")
        if self.permessi is not None:
            invalidi = motivo_permessi(self.permessi)
            if invalidi:
                # Come la porta: con permessi che non si leggono non vale nessun permesso. Il
                # testo si compone prima della chiamata: nel traceback c'è solo la riga della
                # chiamata, non il sorgente del messaggio (in sola lettura chiederebbe cose
                # che lì non si fanno)
                testo = (
                    f"è il test: i «permessi» di manifesto.json non sono validi ({invalidi}), "
                    f"e con permessi così «{azione}» alla porta di Calliope non passa, come "
                    "nessun'altra azione. Correggi il manifesto: la consegna dice tutti gli "
                    "errori")
                self._errore_test(testo)
            motivo = permesso_mancante(azione, argomenti, self.permessi)
            if motivo:
                scope = _SCOPE_AZIONE.get(azione, "")
                testo = (
                    f"è il test: l'azione «{azione}» non è nel manifesto"
                    + ("" if motivo == "non dichiarata" else f" ({motivo})") + ", e con "
                    "questo manifesto la porta di Calliope non la lascerebbe passare. "
                    "Dichiarala in «permessi» del manifesto"
                    + (f" ({scope}, come nel §2 del contratto)" if scope else "")
                    + ", chiedendola con chiedi_permesso se il contratto non la dà da sola, "
                    "oppure non chiamarla"
                    + ("" if self.letture == "vuote" else
                       ". Per provare il caso «negato» c'è negate=[…]"))
                self._errore_test(testo)
        if azione in ("rete_leggi", "rete_invia"):
            # Come la porta vera: un URL scritto a mano con spazi o accenti non parte
            rotto = url_non_codificato(argomenti.get("url"))
            if rotto:
                raise ErroreCalliope(f"rete: {rotto}")
            # Una doppia codifica non si rifiuta (può essere voluta): l'avviso resta in
            # `avvisi` e su stderr, dove pytest lo mostra se il test fallisce
            doppia = doppia_codifica(argomenti.get("url"))
            if doppia:
                self.avvisi.append(doppia)
                print(f"AVVISO di CalliopeFinta: {doppia}", file=sys.stderr)
            if azione == "rete_leggi":
                vera = self._risposta_vera(argomenti.get("url"))
                if vera is not None:
                    self.vere.append(argomenti.get("url"))
                    print("CalliopeFinta: per questo indirizzo c'è la risposta vera di un "
                          "collaudo (esempi_veri/): uso quella, non quella del test",
                          file=sys.stderr)
                    return vera
        if azione == "dati_scrivi":
            self.dati[argomenti["nome"]] = argomenti["testo"]
            return {"ok": True}
        if azione == "dati_leggi":
            return {"testo": self.dati.get(argomenti["nome"])}
        if azione == "dati_elenca":
            return {"nomi": sorted(self.dati)}
        if azione == "dati_cancella":
            self.dati.pop(argomenti["nome"], None)
            return {"ok": True}
        if azione not in self.risposte:
            if azione in _LETTURE_CON_RISPOSTA and self.letture == "vuote":
                if azione.startswith("rete_"):
                    raise ErroreCalliope("rete: nessuna risposta (Calliope finta, letture "
                                         "vuote: nel test il servizio non risponde)")
                vuota = json.loads(json.dumps(LETTURE_VUOTE[azione]))
                if azione == "lista_leggi":
                    vuota["lista"] = _lista(argomenti.get("lista") or "spesa")
                return vuota
            if azione in _LETTURE_CON_RISPOSTA:
                forma = {"casa_stato": '{"testo": "...", "entita": [...]}',
                         "lista_leggi": '{"voci": [...]}',
                         "agenda_elenca": '{"voci": [...], "numero": 0}'}.get(
                    azione, '{"stato": 200, "tipo": "application/json", "testo": "..."}')
                testo = (
                    f"è il test: «{azione}» non ha una risposta preparata, e senza non si sa "
                    f"cosa direbbe Calliope. Passala con risposte={{\"{azione}\": {forma}}} "
                    f"(o una funzione degli argomenti), oppure negate=[\"{azione}\"] per il "
                    "caso d'errore")
                self._errore_test(testo)
            return {"ok": True}
        r = self.risposte[azione]
        return r(argomenti) if callable(r) else r


def chiama(dati=None, risposte=None, negate=(), calliope=None, manifesto=None,
           letture="preparate"):
    """esegui(dati, calliope) dell'estensione della cartella (estensione.py) con una Calliope
    finta: risposte = {azione: risultato} (per esempio {"rete_leggi": {"stato": 200, "tipo":
    "text/html", "testo": "..."}}), negate = le azioni che alzano ErroreCalliope (per esempio
    ["rete_leggi"]). `calliope`: una CalliopeFinta già fatta, per guardarne poi `richieste`
    (risposte e negate le si aggiungono). `letture="vuote"`: le letture senza risposta
    rispondono vuote (CalliopeFinta). Un ErroreDelTest che l'estensione ha inghiottito si
    rialza qui. Sta in calliope_estensione, in sola lettura (22/10, #228): nel file di test,
    riscritto con esegui(dati), tornava il bug del 13/10 (manca l'argomento «calliope»)."""
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    import estensione  # noqa: PLC0415 — l'estensione della cartella dove girano i test
    finta = calliope
    if finta is None:
        finta = CalliopeFinta(risposte=risposte, negate=list(negate), manifesto=manifesto,
                              letture=letture)
    else:
        finta.risposte.update(risposte or {})
        finta.negate |= set(negate)
    prima = len(finta.errori_test)
    out = estensione.esegui(dict(dati or {}), finta)
    if len(finta.errori_test) > prima:
        raise ErroreDelTest(finta.errori_test[prima])
    return out


# ─────────────────────────── server (dentro il container) ───────────────────────────

def _audit(lavoro):
    """Seconda linea dentro il container (la prima è il container stesso: niente rete, disco
    in sola lettura): niente socket, processi, codice nativo, scritture fuori da /tmp."""
    tmp = os.path.realpath(os.environ.get("TMPDIR") or "/tmp")
    bloccati = ("socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
                "os.fork", "os.startfile", "os.kill", "ctypes.", "_winapi.", "winreg.",
                "webbrowser.", "urllib.Request", "http.client.", "ftplib.", "smtplib.",
                "_posixsubprocess.", "sys.remote_exec", "cpython.PyInterpreterState_New")
    scritture = {"os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate",
                 "shutil.rmtree", "shutil.move", "os.symlink", "os.link"}
    stato = {"dentro": False}

    def dentro(p):
        try:
            full = os.path.realpath(os.fsdecode(p) if isinstance(p, bytes) else os.fspath(p))
        except TypeError:
            return False
        return full == tmp or full.startswith(tmp + os.sep) or full == os.devnull

    def hook(evento, args):
        if stato["dentro"]:
            return
        stato["dentro"] = True
        try:
            if evento == "open":
                path, mode = (list(args) + [None, None])[:2]
                if path is not None and not isinstance(path, int) and isinstance(mode, str) \
                        and any(c in mode for c in "wax+") and not dentro(path):
                    raise PermissionError("Bloccato da Calliope: scrittura fuori da /tmp (usa "
                                          "calliope.dati_scrivi)")
            elif evento in scritture:
                if any(isinstance(a, (str, bytes)) and not dentro(a) for a in args):
                    raise PermissionError(f"Bloccato da Calliope: {evento}")
            elif evento.startswith(bloccati):
                raise PermissionError(f"Bloccato da Calliope: {evento} (la rete e il resto si "
                                      f"chiedono a calliope)")
        finally:
            stato["dentro"] = False
    sys.addaudithook(hook)


def _servi(lavoro):
    proto_in = sys.stdin
    proto_out = sys.stdout
    sys.stdout = sys.stderr            # le print dell'estensione non rompono il protocollo
    n = [0]

    def scrivi(msg):
        proto_out.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proto_out.flush()

    def chiedi(azione, argomenti):
        n[0] += 1
        rid = f"c{n[0]}"
        scrivi({"jsonrpc": "2.0", "id": rid, "method": f"calliope/{azione}",
                "params": argomenti})
        while True:
            riga = proto_in.readline()
            if not riga:
                raise ErroreCalliope("Calliope ha chiuso il collegamento")
            msg = json.loads(riga)
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                raise ErroreCalliope(str((msg["error"] or {}).get("message") or "errore"))
            return msg.get("result") or {}

    with open(os.path.join(lavoro, "manifesto.json"), encoding="utf-8") as f:
        manifesto = json.load(f)
    sys.path.insert(0, lavoro)
    # «from calliope_estensione import ErroreCalliope» dentro l'estensione: è questo modulo
    sys.modules.setdefault("calliope_estensione", sys.modules[__name__])
    calliope = Calliope(chiedi)
    modulo = None
    # Pronta: da qui Calliope conta il tempo di lavoro del manifesto (l'avvio del container
    # ha il suo margine, esecuzione.AVVIO_S)
    scrivi({"jsonrpc": "2.0", "method": "notifications/calliope/pronta"})
    for riga in proto_in:
        if not riga.strip():
            continue
        try:
            msg = json.loads(riga)
        except ValueError:
            continue
        mid, metodo = msg.get("id"), msg.get("method")
        if metodo == "tools/list":
            scrivi({"jsonrpc": "2.0", "id": mid, "result": {"tools": [{
                "name": manifesto.get("nome"), "description": manifesto.get("descrizione"),
                "inputSchema": manifesto.get("input") or {"type": "object"}}]}})
        elif metodo == "tools/call":
            try:
                if modulo is None:
                    import estensione as modulo   # noqa: PLC0415 — dopo l'audit hook
                dati = (msg.get("params") or {}).get("arguments") or {}
                out = modulo.esegui(dict(dati), calliope)
                if not isinstance(out, dict):
                    out = {"da_dire": str(out)}
                json.dumps(out)        # deve essere JSON
                scrivi({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}],
                    "structuredContent": out, "isError": False}})
            except BaseException as e:  # noqa: BLE001 — l'errore torna a Calliope
                import traceback
                traceback.print_exc(file=sys.stderr)
                # Dove (11/10): l'ultima riga dei file dell'estensione nel traceback, per il
                # collaudo e il ricollaudo che la riportano all'agente
                dove = ""
                try:
                    for fr, n in reversed(list(traceback.walk_tb(e.__traceback__))):
                        nome = fr.f_code.co_filename
                        if os.path.realpath(nome).startswith(lavoro + os.sep):
                            dove = f" (in {os.path.basename(nome)}:{n})"
                            break
                except Exception:  # noqa: BLE001 — il messaggio va anche senza
                    dove = ""
                testo = f"{type(e).__name__}: {str(e)[:440]}{dove}"[:500]
                scrivi({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": testo}], "isError": True}})
        elif mid is not None:
            scrivi({"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": f"metodo sconosciuto: {metodo}"}})


if __name__ == "__main__":
    _cartella = os.path.realpath(sys.argv[1] if len(sys.argv) > 1 else ".")
    os.chdir(_cartella)
    _audit(_cartella)
    try:
        _servi(_cartella)
    except BaseException:   # noqa: BLE001
        import traceback
        traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    os._exit(0)
