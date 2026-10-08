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
"""

import json
import os
import sys


class ErroreCalliope(Exception):
    """Calliope non ha fatto quello che l'estensione chiedeva: il messaggio dice perché."""


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
    che alzano ErroreCalliope. `richieste` registra ogni (azione, argomenti)."""

    def __init__(self, risposte=None, negate=()):
        self.risposte = dict(risposte or {})
        self.negate = set(negate)
        self.richieste = []
        self.avvisi = []
        self.dati = {}
        super().__init__(self._finta)

    def _finta(self, azione, argomenti):
        self.richieste.append((azione, argomenti))
        if azione in self.negate:
            raise ErroreCalliope(f"{azione}: negato (finto)")
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
        r = self.risposte.get(azione, {"ok": True})
        return r(argomenti) if callable(r) else r


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
                testo = f"{type(e).__name__}: {e}"[:500]
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
