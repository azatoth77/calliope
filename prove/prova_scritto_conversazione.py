import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco: la conversazione a voce e lo scritto (05/10, calliope/schermi/conversazione.py).
Dal 28/10 (#301) dallo schermo personale la casella, le foto e i file valgono sempre (al più
familiare, come il tocco); la conversazione a voce resta per i moduli e per gli schermi di stanza.

- la regola pura `scrittura_consentita(schermo, conversazione)`: schermo personale del
  proprietario che parla, di un'altra persona, di un ospite, conversazione scaduta, schermo di
  stanza nella stessa stanza o in un'altra, audio di questo computer;
- `Conversazioni.voce`: la voce apre e rinnova, la frase breve, la zona grigia e lo scritto
  della stessa persona non rinnovano, un'altra persona o un ospite chiudono, «esci» chiude;
- `scritto_libero`: casella, foto e file dallo schermo personale sì, il modulo no, lo schermo
  di stanza mai;
- il server vero (uvicorn su 127.0.0.1) con tre pagine SSE: benvenuto con lo stato (casella
  accesa sullo schermo personale, moduli spenti), evento «scrittura» che accende e spegne i
  moduli, /api/scrivi e /api/immagine senza conversazione (200, anche da un'altra persona mentre
  parla Dario), /api/modulo con e senza conversazione (403 `senza_conversazione`, niente al
  ciclo, regola `scritto_senza_conversazione` nel registro senza il testo), modulo chiuso con una
  nota quando la conversazione scade a metà o parla un'altra persona, schermo di stanza
  (`schermi_scritto_stanza`) solo con un ospite nella stanza.
"""

import json
import tempfile
import threading
import time
from pathlib import Path

import httpx

from calliope.config import Config
from calliope.schermi import ArchivioSchermi, Mittente, Schermi
from calliope.schermi import conversazione as C
from calliope.schermi.moduli import campo
from calliope.schermi.server import ServerSchermi

TMP = Path(tempfile.mkdtemp(prefix="calliope-scritto-conv-"))
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    print(("ok  " if ok else "ERR ") + nome + (f"  ({dettaglio})" if dettaglio else ""),
          flush=True)
    if not ok:
        errori += 1


def aspetta(cond, max_s=3.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_s:
        if cond():
            return True
        time.sleep(0.01)
    return False


# ─────────────────────────── la regola pura ───────────────────────────

def prova_regola():
    dario = {"id": 1, "stanza": "studio", "proprietario": "dario-id"}
    sogg = {"id": 2, "stanza": "soggiorno", "proprietario": None}
    t = 1000.0
    f = C.scrittura_consentita
    verifica("nessuna conversazione: no", f(dario, None, ora=t, durata_s=300)
             == (False, "nessuna_conversazione"))
    cd = C.Conversazione("dario-id", t - 10, "studio")
    verifica("proprietario in conversazione: sì", f(dario, cd, ora=t, durata_s=300) == (True, ""))
    verifica("proprietario, ma la voce è dal satellite di un'altra stanza: sì (qualunque "
             "satellite)", f(dario, C.Conversazione("dario-id", t, "cucina"), ora=t,
                             durata_s=300) == (True, ""))
    verifica("conversazione scaduta: no", f(dario, C.Conversazione("dario-id", t - 301),
                                            ora=t, durata_s=300) == (False, "scaduta"))
    verifica("al limite esatto: ancora sì", f(dario, C.Conversazione("dario-id", t - 300),
                                              ora=t, durata_s=300)[0])
    verifica("parla un'altra persona: no", f(dario, C.Conversazione("bianca-id", t), ora=t,
                                             durata_s=300) == (False, "altra_persona"))
    verifica("parla un ospite: no (schermo personale)", f(dario, C.Conversazione(None, t,
                                                                                 "studio"),
                                                          ora=t, durata_s=300)[0] is False)
    verifica("schermo di stanza, ospite nella stessa stanza: sì",
             f(sogg, C.Conversazione(None, t, "Soggiorno"), ora=t, durata_s=300) == (True, ""))
    verifica("schermo di stanza, Dario nella stessa stanza: sì",
             f(sogg, C.Conversazione("dario-id", t, "soggiorno"), ora=t, durata_s=300)[0])
    verifica("schermo di stanza, conversazione in un'altra stanza: no",
             f(sogg, C.Conversazione(None, t, "cucina"), ora=t, durata_s=300)
             == (False, "altra_stanza"))
    verifica("schermo di stanza, conversazione senza stanza: no (salvo il controllo locale)",
             f(sogg, C.Conversazione(None, t, None, locale=True), ora=t, durata_s=300)[0]
             is False and f(sogg, C.Conversazione(None, t, None, locale=True), ora=t,
                            durata_s=300, stanza_ok=lambda s, c: c.locale)[0])
    cfg = Config()
    cfg.storia_inattiva_s = 0
    verifica("storia_inattiva_s spenta: lo scritto scade comunque (300 s)",
             C.durata(cfg) == 300.0)
    # Dal 28/10 (#301): dallo schermo personale casella, foto e file senza conversazione
    lib = C.scritto_libero
    verifica("schermo personale: casella, foto e file liberi (28/10, #301)",
             all(lib(dario, k) for k in ("scritto", "immagine", "allegato")))
    verifica("caso contrario: il modulo vuole la conversazione", not lib(dario, "modulo"))
    verifica("caso contrario: lo schermo di stanza mai", not any(
        lib(sogg, k) for k in ("scritto", "immagine", "allegato", "modulo")))
    verifica("caso contrario: niente schermo, un canale sconosciuto",
             not lib(None, "scritto") and not lib(dario, "tocco?"))


def prova_conversazioni():
    cv = C.Conversazioni(lambda: 300.0)
    a = cv.voce("dario-id", "voce", stanza="studio", ora=100.0)
    verifica("la voce apre la conversazione", a and a.persona == "dario-id" and a.voce_at == 100)
    b = cv.voce("dario-id", "breve", ora=150.0)
    verifica("frase breve della stessa persona: resta, senza allungare il tempo",
             b is a and cv.di().voce_at == 100.0)
    cv.voce("dario-id", "conversazione", ora=160.0)
    cv.voce("dario-id", "schermo", ora=170.0)
    verifica("zona grigia e scritto della stessa persona: nemmeno",
             cv.di().voce_at == 100.0)
    cv.voce("dario-id", "voce", ora=200.0)
    verifica("una frase riconosciuta dalla voce rinnova", cv.di().voce_at == 200.0)
    cv.voce("bianca-id", "breve", ora=210.0)
    verifica("frase breve di un'altra persona: chiude, non apre la sua", cv.di() is None)
    cv.voce("dario-id", "voce", ora=220.0)
    cv.voce(None, None, stanza="cucina", ora=230.0)
    c = cv.di()
    verifica("un ospite (voce non riconosciuta): conversazione senza persona nella sua stanza",
             c.persona is None and c.stanza == "cucina")
    cv.voce("dario-id", "voce", ora=240.0)
    verifica("«esci»: chiusa", cv.chiudi() and cv.di() is None and not cv.chiudi())


# ─────────────────────────── server vero ───────────────────────────

class Pagina:
    """Una pagina ridotta: riceve benvenuto, schede ed eventi «scrittura»."""

    def __init__(self, base, sessione):
        self.eventi = []
        threading.Thread(target=self._run, args=(base, sessione), daemon=True).start()

    def _run(self, base, sessione):
        ev = None
        try:
            with httpx.stream("GET", f"{base}/eventi?sessione={sessione}", timeout=60) as r:
                for line in r.iter_lines():
                    if line.startswith("event: "):
                        ev = line[7:]
                    elif line.startswith("data: "):
                        self.eventi.append((ev, json.loads(line[6:])))
        except Exception:  # noqa: BLE001
            pass

    def scrittura(self):
        """L'ultimo stato dello scritto ricevuto (benvenuto o evento)."""
        for e, d in reversed(self.eventi):
            if e == "scrittura":
                return d
            if e == "benvenuto":
                return d.get("scrittura")
        return None

    def moduli(self):
        return [d for e, d in self.eventi if e == "scheda" and d.get("tipo") == "modulo"]


def accedi(c, hub, stanza, owner=None, nome=None):
    r = c.post("/api/abbinamento").json()
    assert hub.abbina(r["codice"], stanza, owner, nome)["ok"]
    return c.post("/api/accedi", headers={"Authorization": f"Bearer {r['richiesta']}"}).json()


def prova_server():
    cfg = Config()
    cfg.memory_db = str(TMP / "schermi.db")
    cfg.schermi_scritto_stanza = True
    cfg.storia_inattiva_s = 0.8
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db))
    registro = []
    hub.registro_turni = registro.append
    srv = ServerSchermi(hub, "127.0.0.1", 0).avvia()
    base = f"http://127.0.0.1:{srv.port}"
    c = httpx.Client(base_url=base, timeout=5)
    try:
        studio = accedi(c, hub, "studio", "dario-id", "Dario")
        bianca = accedi(c, hub, "camera", "bianca-id", "Bianca")
        sogg = accedi(c, hub, "soggiorno")
        p_studio, p_bianca, p_sogg = (Pagina(base, x["sessione"]) for x in (studio, bianca, sogg))
        aspetta(lambda: len(hub.collegati()) == 3)

        def scrivi(sess, testo="che ore sono?"):
            return c.post("/api/scrivi", json={"testo": testo},
                          headers={"X-Calliope-Sessione": sess})

        verifica("accesso: la casella accesa, i moduli spenti con la loro frase (28/10, #301)",
                 studio["scrittura"]["attiva"] is True and studio["scrittura"]["moduli"] is False
                 and "Calliope" in studio["scrittura"]["testo_moduli"]
                 and not studio["scrittura"]["testo"], str(studio["scrittura"]))
        verifica("benvenuto: casella accesa, moduli spenti", aspetta(
            lambda: (p_studio.scrittura() or {}).get("attiva") is True
            and (p_studio.scrittura() or {}).get("moduli") is False))
        verifica("schermo di stanza: tutto spento, con la frase da dire",
                 sogg["scrittura"]["attiva"] is False and "Calliope" in sogg["scrittura"]["testo"])
        import base64
        import immagini_finte as F
        foto = "data:image/jpeg;base64," + base64.b64encode(F.jpeg(F.foto())).decode()

        def manda_foto(sess):
            return c.post("/api/immagine", json={"immagine": foto, "testo": "cos'è?"},
                          headers={"X-Calliope-Sessione": sess}, timeout=10)
        r = manda_foto(studio["sessione"])
        it = hub.ingresso.prendi()
        verifica("foto senza conversazione: 200 e in coda (28/10, #301)", r.status_code == 200
                 and it and it["tipo"] == "immagine" and it["persona"] == "dario-id", r.text)
        r = scrivi(studio["sessione"])
        it = hub.ingresso.prendi()
        verifica("scritto senza conversazione: 200 e in coda, con la persona dello schermo",
                 r.status_code == 200 and r.json()["come"] == "persona" and it
                 and it["tipo"] == "scritto" and it["persona"] == "dario-id", r.text)
        verifica("registro dei turni: nessun rifiuto", not registro, str(registro))
        r = scrivi(sogg["sessione"])
        verifica("caso contrario: lo schermo di stanza senza conversazione resta 403",
                 r.status_code == 403 and r.json()["codice"] == "senza_conversazione"
                 and hub.ingresso.vuoto(), r.text)
        verifica("registro dei turni: la regola, lo schermo, il motivo, mai il testo",
                 registro and registro[-1]["regole"] == ["scritto_senza_conversazione"]
                 and registro[-1]["canale"] == "scritto" and "ore" not in json.dumps(registro),
                 str(registro[-1:]))

        # Dario parla (riconosciuto dalla voce, dal satellite della cucina)
        hub.conversazioni.voce("dario-id", "voce", stanza="cucina")
        verifica("Dario parla: evento «scrittura» coi moduli accesi sul suo schermo", aspetta(
            lambda: (p_studio.scrittura() or {}).get("moduli") is True))
        verifica("caso contrario: sullo schermo di Bianca i moduli restano spenti, la casella no",
                 (p_bianca.scrittura() or {}).get("moduli") is False
                 and (p_bianca.scrittura() or {}).get("attiva") is True)
        verifica("caso contrario: lo schermo del soggiorno resta spento (Dario è in cucina)",
                 (p_sogg.scrittura() or {}).get("attiva") is False)
        r = scrivi(studio["sessione"])
        it = hub.ingresso.prendi()
        verifica("in conversazione: 200 e in coda", r.status_code == 200 and it
                 and it["persona"] == "dario-id", r.text)
        r = scrivi(bianca["sessione"])
        it = hub.ingresso.prendi()
        verifica("Bianca che scrive mentre parla Dario: 200, a nome suo (28/10, #301)",
                 r.status_code == 200 and it and it["persona"] == "bianca-id", r.text)
        r = manda_foto(bianca["sessione"])
        it = hub.ingresso.prendi()
        verifica("foto di Bianca mentre parla Dario: 200, a nome suo",
                 r.status_code == 200 and it and it["persona"] == "bianca-id", r.text)

        # Un modulo aperto durante la conversazione; la conversazione scade a metà
        dario = Mittente(persona="dario-id", nome="Dario", livello="amministra", certo=True)
        spec = {"chiave": "prova", "titolo": "Dati", "domanda": "Mi serve la data.",
                "campi": [campo("data", "Data", "data")]}
        res = hub.moduli.apri(spec, lambda v, t: None, dario, "prova", "amministra")
        verifica("modulo aperto sullo schermo di Dario", res["mostrato"])
        r = c.post("/api/modulo", json={"modulo": res["id"], "valori": {"data": "2026-10-05"}},
                   headers={"X-Calliope-Sessione": studio["sessione"]})
        verifica("modulo inviato in conversazione: 200", r.status_code == 200, r.text)
        hub.ingresso.prendi()
        hub.moduli.chiudi(hub.moduli.aperto(res["id"]), "Inviato", stato="inviato")
        t0 = time.monotonic()
        hub.conversazioni.voce("dario-id", "voce", stanza="cucina", ora=t0)
        res = hub.moduli.apri(spec, lambda v, t: None, dario, "prova", "amministra")
        # Un «sì» breve mezzo secondo dopo: se allungasse, la scadenza sarebbe a t0 + 1,3 s
        hub.conversazioni.voce("dario-id", "breve", ora=t0 + 0.5)
        verifica("la conversazione scade da sola: evento «scrittura» coi moduli spenti", aspetta(
            lambda: (p_studio.scrittura() or {}).get("moduli") is False, 3))
        verifica("…e la casella resta accesa", (p_studio.scrittura() or {}).get("attiva") is True)
        trascorso = time.monotonic() - t0
        verifica("…dopo storia_inattiva_s (0,8 s) dalla voce, non dalla frase breve",
                 0.75 <= trascorso < 1.2, f"{trascorso:.2f} s")
        verifica("il modulo aperto si chiude con la nota", aspetta(lambda: any(
            m.get("stato") == "chiuso" and "conversazione è finita" in (m.get("nota") or "")
            for m in p_studio.moduli())) and not hub.moduli.aperti("dario-id"))
        r = c.post("/api/modulo", json={"modulo": res["id"], "valori": {"data": "2026-10-05"}},
                   headers={"X-Calliope-Sessione": studio["sessione"]})
        verifica("modulo dopo la scadenza: 403, con la frase dei moduli", r.status_code == 403
                 and r.json()["motivo"] == "scaduta" and "modulo" in r.json()["errore"], r.text)
        verifica("…e nel registro col canale «modulo»", registro and registro[-1]["canale"] == "modulo"
                 and registro[-1]["regole"] == ["scritto_senza_conversazione"], str(registro[-1:]))

        # Parla un'altra persona: lo scritto di Dario si spegne, quello di Bianca si accende
        hub.conversazioni.voce("dario-id", "voce", stanza="studio")
        aspetta(lambda: (p_studio.scrittura() or {}).get("moduli") is True)
        res = hub.moduli.apri(spec, lambda v, t: None, dario, "prova", "amministra")
        hub.conversazioni.voce("bianca-id", "voce", stanza="camera")
        verifica("parla Bianca: i moduli di Dario spenti, quelli di Bianca accesi", aspetta(
            lambda: (p_studio.scrittura() or {}).get("moduli") is False
            and (p_bianca.scrittura() or {}).get("moduli") is True))
        verifica("parla Bianca: il modulo di Dario si chiude", not hub.moduli.aperti("dario-id"))
        r = c.post("/api/modulo", json={"modulo": res["id"], "valori": {"data": "2026-10-05"}},
                   headers={"X-Calliope-Sessione": studio["sessione"]})
        verifica("il modulo di Dario mentre parla Bianca: rifiutato", r.status_code in (403, 409)
                 and hub.ingresso.vuoto(), r.text)
        verifica("lo scritto di Dario e di Bianca: tutti e due 200",
                 scrivi(studio["sessione"]).status_code == 200
                 and scrivi(bianca["sessione"]).status_code == 200)
        hub.ingresso.prendi()
        hub.ingresso.prendi()

        # Un ospite nel soggiorno: lo schermo di stanza scrive (come ospite), quelli personali no
        hub.conversazioni.voce(None, None, stanza="soggiorno")
        verifica("ospite nel soggiorno: schermo di stanza acceso, i moduli di Bianca spenti",
                 aspetta(lambda: (p_sogg.scrittura() or {}).get("attiva") is True
                         and (p_bianca.scrittura() or {}).get("moduli") is False))
        r = scrivi(sogg["sessione"])
        it = hub.ingresso.prendi()
        verifica("schermo di stanza in conversazione: 200 come ospite", r.status_code == 200
                 and r.json()["come"] == "ospite" and it["persona"] is None, r.text)
        hub.conversazioni.chiudi()
        verifica("«esci»: tutto spento", aspetta(
            lambda: (p_sogg.scrittura() or {}).get("attiva") is False)
            and scrivi(sogg["sessione"]).status_code == 403)
        # Audio di questo computer, schermi_stanza vuota: le pagine aperte qui
        hub.conversazioni.voce(None, None, stanza=None, locale=True)
        verifica("audio locale senza stanza: lo schermo di stanza aperto su questo computer",
                 aspetta(lambda: (p_sogg.scrittura() or {}).get("attiva") is True))
        hub.conversazioni.chiudi()
    finally:
        c.close()
        srv.ferma()
        hub.archivio.close()


if __name__ == "__main__":
    prova_regola()
    prova_conversazioni()
    prova_server()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    sys.exit(1 if errori else 0)
