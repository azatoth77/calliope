"""
Il registro degli eventi in ombra accanto al ciclo della voce (10/10/2026, passi 0 e 1 del § 8
di docs/ricerche/2026-10-10-registro-eventi.md).

Una `Ombra` per corsia. Non decide niente e non tocca la storia di Brain:

1. **Che cosa è andato alla voce.** Dal passo 2 l'uscita unica della corsia
   (`calliope/eventi/uscita.py`, `Uscita.osservatore`) le dice ogni frase mandata, già con
   l'atto, l'autore, il canale e la posizione fra le chiamate dei tool (il `detto_calliope` nato
   all'invio), e, a ogni turno della voce nuovo, quali si sono sentite per intero (`played`) e se
   c'è stata un'interruzione. In memoria, microsecondi: niente disco nel percorso della prima
   frase. Nel passo 1 l'atto si ricavava dalla funzione del ciclo che chiamava la voce (pila).
2. **A turno finito** (`chiudi_turno`, in cima al giro dopo, quando la voce ha finito): il passo 0
   (`misura.misura_finestra`: parlato diverso dalla storia, domande non registrate) nel campo
   `parlato` del registro dei turni; gli eventi del turno nel registro della conversazione
   (persona o anonimo del satellite), su disco a lotti nel thread dell'archivio; la proiezione
   del contesto (`proiezioni.contesto`) confrontata con la storia di Brain, le differenze per
   meccanismo nel campo `eventi_ombra` (solo quelle nuove: ogni differenza si conta una volta).

In ombra chiamate ed esiti dei tool si ricopiano dalla storia di Brain a fine turno (sono già
nella forma di fine risposta: sigillati, senza il web): il confronto ne controlla la forma nei turni
dopo. Le buste e le etichette delle foto davanti alla frase della persona si ricopiano allo stesso
modo (`dato_in_ingresso`). Dal passo 3 li scriverà Brain dove nascono.

Non solleva mai: un errore si conta (`errori`) e il turno continua come prima.

**Passo 3** (`eventi: attivo`): l'ombra è anche il proiettore di Brain (`contesto`): i turni chiusi
della conversazione per la risposta che comincia (§ 3.1), l'indice degli argomenti, i promemoria
non parlati. Gli eventi del turno si scrivono dal turno vivo di Brain non sigillato, con la
visibilità di ogni esito decisa qui; il passo 0 si misura sulla proiezione; il turno chiuso va
nell'archivio dalla proiezione (`_archivia`). Un turno non scritto rimanda Brain alla sua storia
per quella conversazione (`_guasti`).
"""
from __future__ import annotations

import json
import threading
import time
import weakref

from . import misura, proiezioni
from .registro import (Registri, porta_annuncio, porta_avviso_tutore, porta_coda,
                       porte_usate)
from .tipi import e_annuncio, per_disco, senza_parole

SPENTO, OMBRA, ATTIVO = "spento", "ombra", "attivo"
MODI = (SPENTO, OMBRA, ATTIVO)


def modo(cfg) -> str:
    """`eventi` della configurazione: «spento», «ombra» (passi 1–2, il predefinito) o «attivo»
    (passo 3: Brain legge il contesto dalla proiezione, `Proiettore`)."""
    m = str(getattr(cfg, "eventi", OMBRA) or OMBRA).strip().lower()
    return m if m in MODI else OMBRA


# Esiti del turno con la frase della persona nella conversazione (oggi entra nella storia)
# Dal 28/10 anche il tocco dallo schermo personale (schermi/tocchi.py): la sua descrizione
# («(Ho tolto «latte» dalla lista della spesa toccando lo schermo.)») è un detto_persona
ESITI_PERSONA = frozenset({"risposta", "interruzione", "cortesia", "protezione",
                           "non_rivolta", "modulo", "tocco"})
# Esiti che chiudono la conversazione: la frase e la chiusura vanno nel segmento che si chiude
ESITI_CHIUSURA = frozenset({"dormi", "uscita", "nuova_conversazione"})
FINESTRA_MAX = 400                  # frasi in memoria al più (un ciclo finto che non chiude mai)


def _forma_brain() -> proiezioni.Forma:
    """I numeri della forma dei turni chiusi di Brain di oggi (la proiezione non importa Brain)."""
    try:
        from .. import brain as b
        from ..notizie import contesto as nc
        return proiezioni.Forma(risultato_max=int(b.OLD_RESULT_CHARS), traccia=b._OLD_TRACE,
                                ora_di_allora=tuple(dict(b._OLD_TIME).items()),
                                web_tolto=b.WEB_TOLTO, traccia_privata=b._PRIVATE_TRACE,
                                riduzioni=((nc.TOOL, nc.riduci),))
    except Exception:  # noqa: BLE001
        return proiezioni.FORMA


def _norm(s) -> str:
    return misura.norm(str(s or ""))


def _turni_storia(history: list) -> list[tuple]:
    """La storia di Brain divisa in turni: [(messaggio della persona o None, [messaggi])]."""
    out: list[tuple] = []
    cur = None
    for m in history:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "user":
            cur = (m, [])
            out.append(cur)
        elif m.get("role") in ("assistant", "tool"):
            if cur is None:
                cur = (None, [])
                out.append(cur)
            cur[1].append(m)
    return out


def _testo_assistente(msgs: list) -> str:
    return " ".join(str(m.get("content") or "").strip() for m in msgs
                    if m.get("role") == "assistant" and str(m.get("content") or "").strip())


def _frasi_tool(msgs: list) -> list[tuple]:
    """Le frasi pronte dei tool del turno, con True se il risultato apre una proposta."""
    out = []
    for m in msgs:
        if m.get("role") != "tool":
            continue
        try:
            res = json.loads(m.get("content") or "{}")
        except (ValueError, TypeError):
            continue
        if not isinstance(res, dict):
            continue
        for k in ("conferma", "risposta_finale", "da_dire"):
            if isinstance(res.get(k), str) and res[k].strip():
                out.append((res[k], bool(res.get("in_sospeso"))))
                break
    return out


class Ombra:
    """Il registro degli eventi in ombra di una corsia."""

    def __init__(self, cfg, registri: Registri | None, ciclo, log=print):
        self.cfg = cfg
        self.registri = registri
        self.c = ciclo
        self.log = log
        self._finestra: list[tuple] = []
        self._lock = threading.Lock()
        self.errori = 0
        self._riporto: dict = {}
        self._forma = None
        # Passo 3: Brain legge il contesto da qui (Proiettore); il confronto con la sua storia
        # non serve più (la storia è la proiezione), resta la misura del passo 0 sulla proiezione
        self.attivo = modo(cfg) == ATTIVO
        self._vista = None
        self._pezzi_turno: list = []
        self._guasti: set = set()           # conversazioni con un turno non scritto (attivo)

    # ── 1. che cosa va alla voce (dall'uscita unica, nel thread di chi parla) ──
    def collega(self, uscita):
        uscita.osservatore = self.sente

    def sente(self, item):
        """Dall'uscita unica: ("frase", detto) per una frase mandata (il detto_calliope nato
        all'invio), ("fine", played, interrotta) per il pezzo che si chiude. In memoria e
        basta."""
        try:
            with self._lock:
                if len(self._finestra) < FINESTRA_MAX:
                    self._finestra.append(item)
        except Exception:  # noqa: BLE001 — la voce non si ferma mai per l'ombra
            pass

    # ── 2. a turno finito ──
    def chiudi_turno(self, rec: dict | None, t=None):
        """In cima al giro dopo (la voce ha finito), prima di scrivere il registro dei turni.
        Non solleva mai."""
        try:
            self._chiudi_turno(rec, t)
        except Exception as e:  # noqa: BLE001
            self.errori += 1
            if self.attivo:
                # Un turno non scritto per intero: la proiezione di questa conversazione non è
                # più completa (potrebbe mancare la traccia di un dato non fidato). Brain torna
                # alla sua storia, con le scritture a mano di prima (`contesto` → None)
                conv = getattr(getattr(self.c, "brain", None), "conv", None)
                if conv is not None:
                    self._guasti.add(id(conv))
            if self.errori == 1 or self.errori % 100 == 0:
                self.log(f"   [EVENTI] ombra non riuscita ({type(e).__name__}: {e}); errori "
                         f"finora: {self.errori}")
            if rec is not None:
                rec.setdefault("eventi_ombra", {})["errori"] = 1

    # ── 3. passo 3: il contesto della risposta dalla proiezione ──
    def contesto(self, conv) -> dict | None:
        """Con `eventi: attivo`, all'inizio di una risposta (e in cima al giro): la proiezione
        della conversazione `conv` per il modello (§ 3.1), dal suo registro. None se il registro
        non è (ancora) quello di `conv` (una conversazione appena aperta: la sua storia è vuota o
        è la coda; Brain tiene la sua). Dopo un riavvio adotta qui il segmento rigiocato. Puro
        in lettura: niente disco.

        Restituisce {"messaggi" (turni chiusi dell'argomento corrente, con `_seq`), "indice"
        (gli argomenti messi da parte, o None), "argomenti" (il fold), "interrotta" e
        "cosa_fare" (promemoria non parlati), "fughe", "ms"}."""
        if not self.attivo or self.registri is None or conv is None:
            return None
        if id(conv) in self._guasti:
            return None
        chiave = getattr(conv, "chiave", None)
        if not isinstance(chiave, str):
            return None
        try:
            if not self.registri.esiste(chiave):
                return None
            reg = self.registri.della_corsia(chiave)
        except Exception:  # noqa: BLE001 — una chiave che non è una conversazione
            return None
        t0 = time.perf_counter()
        with reg.lotto():
            st = reg.stato
            ref = st.get("conv_ref")
            prima = ref() if ref is not None else None
            if prima is not conv:
                if not (prima is None and st.get("ripreso") and not st.get("adottato")
                        and reg.conv is not None):
                    return None
                # Dopo un riavvio: il segmento rigiocato è la conversazione ripresa da Brain
                # (da `correnti`, con i `_seq` della proiezione di prima)
                st["conv_ref"], st["adottato"] = weakref.ref(conv), True
                r0 = getattr(conv, "riassunto", None)
                st.setdefault("riassunto", r0.get("testo") if isinstance(r0, dict) else None)
                seqs = [m["_seq"] for m in getattr(conv, "history", None) or ()
                        if isinstance(m, dict) and m.get("role") == "user"
                        and isinstance(m.get("_seq"), int)]
                if seqs:
                    st["da"] = min(seqs)
            if reg.conv is None:
                return None
            eventi = reg.eventi()
            da = st.get("da")
        if self._forma is None:
            self._forma = _forma_brain()
        vista = proiezioni.turni(eventi, da)
        msgs = proiezioni.messaggi(vista, self._forma, per_risposta=True, seq=True,
                                   riassunto=False)
        out = {"messaggi": msgs, "indice": proiezioni.indice(vista),
               "argomenti": proiezioni.argomenti(vista),
               "interrotta": proiezioni.promemoria_interrotta(vista),
               "cosa_fare": proiezioni.promemoria_cosa_fare(vista),
               "fughe": proiezioni.fughe(eventi, msgs)}
        out["ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
        return out

    def dimentica(self, chiave: str):
        """«Dimentica le nostre conversazioni» (§ 2.4): la finestra in corso e il registro in
        memoria della persona (il disco lo cancella l'archivio, `Disco.dimentica`)."""
        with self._lock:
            self._finestra = []
        if self.registri is not None:
            self.registri.dimentica(chiave)

    def _pezzi(self, finestra: list[tuple], t) -> list[dict]:
        """I pezzi di voce della finestra, fra un `start_turn` e l'altro, con le frasi sentite
        per intero (tutte senza interruzione; con l'interruzione quelle in `played`)."""
        speaker = getattr(self.c, "speaker", None)
        pezzi: list[dict] = []
        cur: list[dict] = []

        def chiudi(played, interrotta):
            if not cur:
                return
            frasi = [(str(d.get("testo") or ""), d.get("atto"), d.get("canale") or "voce",
                      bool(d.get("pronta"))) for d in cur]
            k = len(frasi)
            if interrotta:
                sentito = _norm(" ".join(played or ()))
                k, pos = 0, 0
                for testo, _a, _c, pronta in frasi:
                    if pronta:
                        k += 1
                        continue
                    n = _norm(testo)
                    if n and sentito.startswith(n, pos):
                        pos += len(n)
                        while pos < len(sentito) and sentito[pos] == " ":
                            pos += 1
                        k += 1
                    else:
                        break
            pezzi.append({"frasi": [(a, b, c) for a, b, c, _ in frasi], "sentite": k,
                          "inviate": len(frasi), "interrotta": bool(interrotta),
                          "detti": list(cur)})
            cur.clear()

        for item in finestra:
            if item[0] == "fine":
                chiudi(item[1], item[2])
            elif item[0] == "frase" and isinstance(item[1], dict):
                cur.append(item[1])
        if cur:
            chiudi(list(getattr(speaker, "played", None) or ()),
                   bool(getattr(speaker, "interrupted", False)))
        return pezzi

    def _info(self, rec, t, brain) -> dict:
        rec = rec or {}
        regole = list(rec.get("regole") or ())
        capito = getattr(brain, "last_capito", None) if rec.get("esito") == "risposta" else None
        per = rec.get("pericolo") if isinstance(rec.get("pericolo"), dict) else {}
        # La proposta di un tool in questa risposta (Brain._offer: il risultato con in_sospeso,
        # che nella storia non resta)
        offerta = getattr(brain, "_offer", None) if rec.get("esito") == "risposta" else None
        return {"esito": rec.get("esito"), "regole": regole, "offerta": bool(offerta),
                "capito": bool(isinstance(capito, dict) and capito.get("accettata")
                               and capito.get("dopo")),
                "cancello": per.get("cancello")}

    def _chiudi_turno(self, rec: dict | None, t):
        with self._lock:
            finestra, self._finestra = self._finestra, []
        brain = getattr(self.c, "brain", None)
        pezzi = self._pezzi(finestra, t)
        if rec is None and not pezzi:
            return                          # niente detto fra un turno e l'altro
        info = self._info(rec, t, brain)
        info["turno_nuovo"] = rec is not None and rec.get("esito") in ESITI_PERSONA
        conv = getattr(brain, "conv", None)
        hist = getattr(conv, "history", None)
        storia = hist if isinstance(hist, list) else []
        turni_s = _turni_storia(storia)
        ultimo = turni_s[-1][1] if turni_s else []
        info["frasi_tool"] = _frasi_tool(ultimo)
        # Le proposte (il campo `pending` della conversazione): nuova in questo turno?
        reg = None
        if self.registri is not None and conv is not None and isinstance(
                getattr(conv, "chiave", None), str) and isinstance(hist, list):
            reg = self._registro(conv.chiave, rec, pezzi)
        st = reg.stato if reg is not None else self.__dict__.setdefault("_stato_locale", {})
        pending = getattr(conv, "pending", None) if conv is not None else None
        info["proposta_nuova"] = bool(pending) and pending is not st.get("pending")
        # Passo 3: il passo 0 si misura sulla proiezione (la storia del modello), dopo la
        # scrittura; in ombra sulla storia di Brain, prima
        parlato = (misura.misura_finestra(pezzi, _testo_assistente(ultimo), info)
                   if not self.attivo else {})
        if reg is None:
            st["pending"] = pending
        ombra = None
        self._vista = None
        # Una frase non rivolta a Calliope (ignorata, scartata, vuota, doppione) non è di
        # nessuna conversazione: resta solo nel registro dei turni (§ 1.4)
        esito = (rec or {}).get("esito")
        della_conv = bool(pezzi) or esito in ESITI_PERSONA or esito in ESITI_CHIUSURA
        if reg is not None and della_conv:
            ombra = self._scrivi_e_confronta(reg, conv, rec, t, pezzi, info, turni_s)
        # Il criterio di E1 (15/10, issue #11): il passo 0 sulla proiezione, misurabile già in
        # ombra (sulla storia di Brain non va a zero per costruzione); con attivo è `parlato`
        proiettato = (self._parlato_attivo(pezzi, info)
                      if self.attivo or ombra is not None else None)
        if self.attivo:
            parlato = proiettato
        if ombra is not None and proiettato and "sentite" in proiettato:
            diversa, motivi_p = misura.proiezione_diversa(proiettato)
            ombra["proiezione_diversa"] = diversa
            if motivi_p:
                ombra["proiezione_motivi"] = motivi_p
            # Il turno interrotto (18/10, issue #159): quante frasi erano andate alla voce,
            # quante si sono sentite per intero e il motivo, contato a parte nel criterio
            # Solo per un turno della persona: un annuncio interrotto fra un turno e l'altro
            # (`rec` None) andrebbe nel riporto e farebbe «interrotto» il turno dopo
            inter = [p for p in pezzi if p["interrotta"]]
            if inter and rec is not None:
                inviate = sum(p["inviate"] for p in inter)
                sentite = sum(min(p["sentite"], p["inviate"]) for p in inter)
                ombra["interrotta"] = {
                    "inviate": inviate, "sentite": sentite,
                    "motivo": "niente_di_intero" if not sentite else "in_parte"}
        if rec is None:
            self._riporta(parlato, ombra)
            return
        self._unisci_riporto(rec)
        if parlato:
            rec["parlato"] = _somma(rec.get("parlato") or {}, parlato)
        if ombra is not None:
            rec["eventi_ombra"] = _somma(rec.get("eventi_ombra") or {}, ombra)

    def _parlato_attivo(self, pezzi, info) -> dict:
        """Il passo 0 con `eventi: attivo`: ciò che si è sentito contro la proiezione dell'ultimo
        turno, cioè la storia che il modello vedrà. Deve dare 0 per costruzione (§ 3.1); la frase
        interrotta non è più «persa» (la parte non detta è il promemoria del turno dopo, § 11.4)."""
        vista = self._vista
        storia = ""
        if vista is not None and vista["turni"]:
            storia = proiezioni.testo_assistente(vista["turni"][-1])
        parlato = misura.misura_finestra(pezzi, storia, info)
        motivi = parlato.get("motivi") or {}
        motivi.pop("interrotta_persa", None)
        if "motivi" in parlato and not motivi:
            parlato.pop("motivi")
            parlato.pop("diverso", None)
        return parlato

    # ── annunci fra un turno e l'altro: si aggiungono al turno dopo ──
    def _riporta(self, parlato: dict, ombra: dict | None):
        if parlato:
            self._riporto["parlato"] = _somma(self._riporto.get("parlato") or {}, parlato)
        if ombra:
            self._riporto["eventi_ombra"] = _somma(self._riporto.get("eventi_ombra") or {},
                                                   ombra)

    def _unisci_riporto(self, rec: dict):
        r, self._riporto = self._riporto, {}
        for k in ("parlato", "eventi_ombra"):
            if r.get(k):
                rec[k] = _somma(rec.get(k) or {}, r[k])
                rec[k]["fra_turni"] = 1

    # ── il registro della conversazione del turno ──
    def _registro(self, chiave: str, rec, pezzi):
        atti = {a for p in pezzi for _t, a, _c in p["frasi"]}
        persona = (rec or {}).get("esito") in ESITI_PERSONA
        try:
            if not persona and atti and all(e_annuncio(a) or a in misura.VOLUTI for a in atti) \
                    and any(e_annuncio(a) for a in atti) and "avviso_tutore" not in atti:
                return porta_annuncio(self.registri, chiave)
            if not persona and atti == {"avviso_tutore"} and chiave.startswith("persona:"):
                return porta_avviso_tutore(self.registri, chiave)
            return self.registri.della_corsia(chiave)
        except Exception:  # noqa: BLE001 — una chiave che non è una conversazione
            return None

    def _scrivi_e_confronta(self, reg, conv, rec, t, pezzi, info, turni_s) -> dict:
        corsia = getattr(getattr(self.c, "corsia", None), "chiave", None)
        rec_ = rec or {}
        esito = rec_.get("esito")
        n0 = reg.seq
        scritti: list = []
        with reg.lotto():
            st = reg.stato
            ref = st.get("conv_ref")
            prima = ref() if ref is not None else None
            turno = int(getattr(conv, "turn_number", 0) or 0)
            cambiata = reg.conv is not None and prima is not conv
            if cambiata and prima is None and st.get("ripreso") and not st.get("adottato"):
                # Dopo un riavvio: il segmento rigiocato è la conversazione ripresa da Brain
                st["conv_ref"], st["adottato"] = weakref.ref(conv), True
                r0 = getattr(conv, "riassunto", None)
                st.setdefault("riassunto", r0.get("testo") if isinstance(r0, dict) else None)
                if not self.attivo:
                    self._ritagga(reg, conv, nuovo=bool(info.get("turno_nuovo")))
                    # Le differenze già nella conversazione ripresa erano state contate prima
                    # del riavvio: si segnano come dette, senza contarle di nuovo
                    if self._forma is None:
                        self._forma = _forma_brain()
                    v0 = proiezioni.turni(reg.eventi(), st.get("da"))
                    self._confronta(reg, conv, v0, proiezioni.messaggi(v0, self._forma))
                cambiata = False
            chiusura = esito in ESITI_CHIUSURA
            if cambiata:
                if chiusura:
                    scritti += self._eventi_turno(reg, conv, rec_, t, pezzi, info, turno,
                                                  corsia, None, solo_chiusura=True)
                    pezzi = []
                reg.chiudi(self._motivo(rec_), turno, corsia)
            if reg.conv is None:
                self._apri(reg, conv, turno, corsia, nuovo=bool(info.get("turno_nuovo")))
            scritti += self._eventi_turno(reg, conv, rec_, t, pezzi, info, turno, corsia,
                                          turni_s)
            if rec is not None:
                scritti.append(reg.aggiungi("turno_chiuso", turno, corsia=corsia,
                                            **_turno_chiuso(rec_)))
            eventi = reg.eventi()
            st["pending"] = getattr(conv, "pending", None)
            if self.attivo:
                da = _finestra_attiva(conv, scritti)
                if da is not None:
                    st["da"] = max(int(st.get("da") or 0), da)
            else:
                st["da"] = _finestra(st, conv) or st.get("da")
        if self.registri is not None:
            self.registri.scrivi()
        if self._forma is None:
            self._forma = _forma_brain()
        t0 = time.perf_counter()
        vista = proiezioni.turni(eventi, st.get("da"))
        msgs = proiezioni.messaggi(vista, self._forma, per_risposta=self.attivo,
                                   seq=self.attivo, riassunto=not self.attivo)
        ms = (time.perf_counter() - t0) * 1000.0
        self._vista = vista
        if self.attivo:
            # La storia del modello è questa proiezione: niente da confrontare. Il turno appena
            # chiuso va nell'archivio dalla proiezione (sigillato, ciò che si è sentito)
            diff, non_oss, aperte = {}, 0, 0
            if rec is not None and n0 < reg.seq:
                self._archivia(conv, vista, n0)
        else:
            diff, non_oss, aperte = self._confronta(reg, conv, vista, msgs)
        out: dict = {"eventi": reg.seq - n0, "contesto_ms": round(ms, 3),
                     "registro": reg.chiave.split(":", 1)[0],
                     **({"modo": ATTIVO} if self.attivo else {}),
                     "byte": sum(len(json.dumps(per_disco(e), ensure_ascii=False,
                                                sort_keys=True, default=str))
                                 for e in scritti)}
        if diff:
            out["differenze"] = diff
        if aperte:
            out["aperte"] = aperte
        if non_oss:
            out["non_osservati"] = non_oss
        f = proiezioni.fughe(eventi, msgs)
        if f:
            out["fughe"] = f
        porte = porte_usate()
        if porte:
            out["porte"] = sorted(set(porte))
        if reg.troncati and not st.get("troncati_detti"):
            st["troncati_detti"] = True
            out["troncati"] = reg.troncati
            try:
                self.c.rule("eventi_troncati")
            except Exception:  # noqa: BLE001
                pass
        return out

    def _archivia(self, conv, vista, n0: int):
        """Passo 3: il turno appena scritto nell'archivio delle conversazioni, dalla proiezione
        (la scheda «Conversazione» lo mostra subito, come Ciclo._archivia_turno di prima), con
        dove e come è arrivato (`_meta_turno` del ciclo). Gli annunci attaccati a un turno già
        archiviato non si riarchiviano (come prima)."""
        nuovi = [x for x in vista["turni"] if x["chiave"] > n0 and x["persona"] is not None]
        if not nuovi:
            return
        msgs = proiezioni.messaggi({"riassunto": None, "turni": nuovi}, self._forma)
        meta = getattr(self.c, "_meta_turno", None)
        try:
            self.c._meta_turno = None
        except AttributeError:
            pass
        if isinstance(meta, dict):
            for m in reversed(msgs):
                if m.get("role") == "user":
                    m["_turno"] = meta
                    break
        archivia = getattr(getattr(self.c, "brain", None), "archivia_messaggi", None)
        if callable(archivia):
            try:
                archivia(conv, msgs)
            except Exception as e:  # noqa: BLE001 — l'archivio non ferma la voce
                self.log(f"   [EVENTI] turno non archiviato: {type(e).__name__}: {e}")

    def _motivo(self, rec: dict) -> str:
        esito = rec.get("esito")
        regole = set(rec.get("regole") or ())
        if esito in ("dormi", "uscita"):
            return "esci"
        if esito == "nuova_conversazione" or rec.get("conversazione_nuova"):
            return "nuova"
        if "conversazione_altra_persona" in regole:
            return "altra_persona"
        if "conversazione_scaduta" in regole:
            return "scaduta"
        return "sostituita"

    def _apri(self, reg, conv, turno, corsia, nuovo: bool = False):
        r = getattr(conv, "riassunto", None)
        r = r if isinstance(r, dict) else {}
        tipo = r.get("tipo")
        dati = {}
        if tipo in ("ripresa", "coda") and r.get("testo"):
            if tipo == "coda":
                porta_coda(self.registri, reg.chiave, reg.chiave)
            dati = {"riassunto": str(r["testo"]), "riassunto_tipo": tipo}
        owner = getattr(conv, "owner", None)
        reg.apri("coda" if tipo == "coda" else "ripresa" if tipo == "ripresa"
                 else "anonima" if reg.ospite else "persona", turno, corsia,
                 owner=owner if isinstance(owner, (str, int)) else None,
                 luogo=getattr(conv, "luogo", None), **dati)
        reg.stato.clear()
        reg.stato.update(conv_ref=weakref.ref(conv), tag={}, visti=set(), dette=set(),
                         riassunto=dati.get("riassunto"), frase=0)
        # I messaggi già nella storia prima dell'ombra (una conversazione di prima) non sono
        # osservati: si contano, non si confrontano. Tranne quello del turno appena finito
        utenti = [m for m in getattr(conv, "history", None) or ()
                  if isinstance(m, dict) and m.get("role") == "user"]
        for m in utenti[:-1] if nuovo else utenti:
            reg.stato["visti"].add(id(m))

    def _ritagga(self, reg, conv, nuovo: bool = False):
        """Dopo il riavvio i messaggi della storia sono oggetti nuovi (da `correnti`): si
        riconoscono dalla coda, frase per frase."""
        st = reg.stato
        st.setdefault("tag", {})
        st.setdefault("visti", set())
        st.setdefault("dette", set())
        st.setdefault("frase", 0)
        vista = proiezioni.turni(reg.eventi())
        persone = [x for x in vista["turni"] if x["persona"] is not None]
        utenti = [m for m in conv.history if isinstance(m, dict) and m.get("role") == "user"]
        if nuovo and utenti:
            utenti = utenti[:-1]             # quello di questo turno: lo riconosce _dalla_storia
        while persone and utenti:
            p, u = persone.pop(), utenti.pop()
            if _norm(u.get("content")).endswith(_norm(p["persona"])):
                st["tag"][id(u)] = (u, p["chiave"])
                st["visti"].add(id(u))
            else:
                break
        for u in utenti:
            st["visti"].add(id(u))
        if st["tag"]:
            st["da"] = min(s for _u, s in st["tag"].values())

    # ── gli eventi di un turno ──
    def _eventi_turno(self, reg, conv, rec, t, pezzi, info, turno, corsia, turni_s,
                      solo_chiusura: bool = False) -> list:
        st = reg.stato
        scritti = []
        esito = rec.get("esito")
        testo = getattr(t, "text", None) if t is not None else None
        sat = getattr(getattr(self.c, "corsia", None), "nome", None)

        # Le parole di questo turno non si conservano (12/10, calliope/conserva.py: zona
        # grigia; dal 12 al 16/10 anche il dubbio con un minore): restano solo in memoria
        # Dal 18/10 (decisione 0032) anche i turni tenuti solo per la valutazione: le parole
        # restano nel registro dei turni, mai nel registro della persona (né nel contesto)
        c = rec.get("conserva") if isinstance(rec.get("conserva"), dict) else {}
        anonimo = c.get("testo") is False or c.get("motivo") == "valutazione"

        def add(_tipo, **dati):
            if anonimo:
                dati = senza_parole(_tipo, dati)
            ev = reg.aggiungi(_tipo, turno, corsia=corsia, **dati)
            scritti.append(ev)
            return ev

        # Mai su disco (§ 2.4): le parole della frase di sfida (chiesta o ripetuta) e i segreti
        # detti nel turno (il codice di abbinamento: Brain.redact); in memoria restano
        brain = getattr(self.c, "brain", None)
        redact = getattr(brain, "redact", None)
        regole_t = set(rec.get("regole") or ())
        sfida_t = bool({"sfida_voce", "sfida_risposta"} & regole_t)

        def riservato(x) -> dict:
            segreto = False
            if callable(redact) and isinstance(x, str):
                try:
                    segreto = redact(x) != x
                except Exception:  # noqa: BLE001
                    segreto = True
            return {"_non_su_disco": ["testo"]} if sfida_t or segreto else {}

        persona = None
        self._pezzi_turno = pezzi
        if esito in ESITI_PERSONA or (solo_chiusura and esito in ESITI_CHIUSURA):
            sc = getattr(self.c, "speaker_ctx", None)
            canale = "scritto" if t is not None and getattr(t, "scritto", None) is not None \
                else "voce"
            if rec.get("canale") == "tocco":
                canale = "tocco"
            if esito == "modulo":
                persona = add("modulo_compilato", modulo=rec.get("modulo"),
                              campi=list(rec.get("campi") or ()))
            elif isinstance(testo, str):
                fermato = (rec.get("testo") is None and esito not in ("non_rivolta",))                     or bool(riservato(testo))
                # Con attivo la storia si rifà dalla proiezione (15/10, issue #12): i segni che
                # Brain mette sul messaggio della persona (chi l'ha detta nella conversazione
                # anonima, i pezzi della stanza legati alla frase) vanno nell'evento. I pezzi
                # stanno solo in memoria (`Conversazione.stanza`): il loro numero non su disco
                segni = self._segni_persona(conv) if self.attivo else {}
                nsd = ((["testo"] if fermato else [])
                       + [k for k in ("stanza", "dati") if k in segni])
                persona = add(
                    "detto_persona", testo=testo, canale=canale,
                    # Il tocco (28/10): chi parlava prima è già rimesso al suo posto quando
                    # l'ombra scrive, il modo vero è nel registro del turno
                    come=("schermo" if canale == "tocco"
                          else getattr(sc, "identified_by", None)),
                    satellite=sat, sfida=bool(getattr(getattr(self.c, "brain", None),
                                                      "last_sfida", False)
                                              and esito == "risposta"),
                    brain=esito == "risposta", **segni,
                    **({"_non_su_disco": nsd} if nsd else {}))
            if persona is not None:
                st["frase"] = 0
                if esito == "non_rivolta":
                    add("turno_escluso", escluso=persona.seq, motivo="non_rivolta")
                elif not solo_chiusura and turni_s is not None:
                    scritti += self._dalla_storia(reg, conv, persona, info, turni_s, add)
        # Ciò che è andato alla voce, frase per frase, e quanto si è sentito: i detto_calliope
        # nati all'invio nell'uscita unica (autore, atto, canale, posizione fra le chiamate)
        for p in pezzi:
            detti = p.get("detti") or [{"testo": a, "atto": b, "canale": c}
                                       for a, b, c in p["frasi"]]
            frasi = [(i, d) for i, d in enumerate(detti)
                     if not solo_chiusura or d.get("atto") == "chiusura"]
            if not frasi:
                continue
            da = st.get("frase", 0)
            for i, d in frasi:
                testo_f, atto = str(d.get("testo") or ""), d.get("atto")
                extra = {k: d[k] for k in ("fonte", "dopo_chiamate") if d.get(k) is not None}
                add("detto_calliope", testo=testo_f, autore=d.get("autore") or "atto",
                    atto=atto, frase=st.get("frase", 0), canale=d.get("canale") or "voce",
                    satellite=sat, vis="registro" if atto in proiezioni.ATTI_FUORI else None,
                    **extra, **riservato(testo_f))
                st["frase"] = st.get("frase", 0) + 1
            add("voce_fine", da=da, inviate=len(frasi), sentite=min(p["sentite"], len(frasi)),
                interrotta=p["interrotta"])
        if solo_chiusura:
            return scritti
        # Le proposte: aperta in questo turno, o chiusa
        scritti += self._proposte(reg, conv, add)
        regole = set(rec.get("regole") or ())
        if "sfida_voce" in regole:
            add("sfida_chiesta")
        if "sfida_risposta" in regole:
            add("sfida_esito", esito="risposta")
        # Compressione: il riassunto della conversazione è cambiato
        r = getattr(conv, "riassunto", None)
        if isinstance(r, dict) and r.get("testo") and r.get("tipo") not in ("ripresa", "coda") \
                and r.get("testo") != st.get("riassunto"):
            st["riassunto"] = r["testo"]
            da = (_finestra_attiva(conv, scritti) if self.attivo else _finestra(st, conv))
            add("compressione", fino_a=max(0, int(da or 1) - 1), riassunto=str(r["testo"]))
        return scritti

    def _turno_vivo(self, conv) -> tuple | None:
        """Passo 3: il turno vivo della storia di Brain (dopo `vivo_da`, la parte che la
        proiezione non ha ancora): (messaggio della persona, [messaggi dopo]), o None."""
        hist = getattr(conv, "history", None) or []
        vivo = getattr(conv, "vivo_da", None)
        vivi = [m for m in hist[vivo if isinstance(vivo, int) else len(hist):]
                if isinstance(m, dict)]
        i = next((k for k, m in enumerate(vivi) if m.get("role") == "user"), None)
        if i is None:
            return None
        return vivi[i], vivi[i + 1:]

    def _segni_persona(self, conv) -> dict:
        """Passo 3: i segni del messaggio della persona del turno vivo che la proiezione deve
        rendere (15/10, issue #12): `_chi` → `chi`, `_stanza` → `stanza` (numero o elenco); dal
        16/10 (issue #95) `_dati` → `dati`, i dati fissi legati alla frase."""
        vivo = self._turno_vivo(conv)
        if vivo is None:
            return {}
        u = vivo[0]
        out: dict = {}
        if isinstance(u.get("_chi"), str) and u["_chi"]:
            out["chi"] = u["_chi"]
        for k in ("stanza", "dati"):
            s = u.get("_" + k)
            if isinstance(s, int) and not isinstance(s, bool):
                out[k] = s
            elif isinstance(s, (list, tuple)) and s and all(
                    isinstance(x, int) and not isinstance(x, bool) for x in s):
                out[k] = list(s)
        return out

    def _dalla_storia(self, reg, conv, persona, info, turni_s, add) -> list:
        """Il messaggio nuovo della persona nella storia: lo si riconosce (per il confronto),
        gli ingressi davanti alla frase e le chiamate del turno (ricopiate a fine turno). Con
        `eventi: attivo` dal turno vivo di Brain, non sigillato: la visibilità e i campi di ogni
        esito si decidono qui, alla scrittura (§ 11.1)."""
        st = reg.stato
        if self.attivo:
            vivo = self._turno_vivo(conv)
            if vivo is None:
                return []
            u, msgs = vivo
        else:
            nuovi = [(u, msgs) for u, msgs in turni_s if u is not None
                     and id(u) not in st["visti"]]
            for u, _m in turni_s:
                if u is not None:
                    st["visti"].add(id(u))
            if not nuovi:
                return []
            u, msgs = nuovi[-1]
            st["tag"][id(u)] = (u, persona.seq)
        if st.get("da") is None and not self.attivo:
            st["da"] = persona.seq           # in ombra: il primo turno osservato
        scritti = []
        contenuto = str(u.get("content") or "")
        frase = str(persona.dati.get("testo") or "") if persona.tipo == "detto_persona" else ""
        if info.get("capito") and persona.tipo == "detto_persona":
            cap = getattr(getattr(self.c, "brain", None), "last_capito", None) or {}
            scritti.append(add("trascrizione_capita", prima=cap.get("prima"),
                               dopo=cap.get("dopo"), accettata=True))
            frase = str(cap.get("dopo") or frase)
        fonti = _fonti_di(u)
        if frase and contenuto.endswith(frase) and len(contenuto) > len(frase):
            prefisso = contenuto[:len(contenuto) - len(frase)]
            tipo = "foto_in_ingresso" if u.get("_img") else "dato_in_ingresso"
            dati = {"testo": prefisso, "fonte": fonti or "busta"}
            if tipo == "foto_in_ingresso":
                dati["numeri"] = [n for n in u.get("_img") or () if isinstance(n, int)]
            scritti.append(add(tipo, **dati))
        elif u.get("_img"):
            scritti.append(add("foto_in_ingresso", testo="", fonte=fonti or "foto",
                               numeri=[n for n in u["_img"] if isinstance(n, int)]))
        if u.get("_all"):
            scritti.append(add("allegato_in_ingresso", testo="", fonte=fonti or "allegato",
                               numeri=[n for n in u["_all"] if isinstance(n, int)],
                               info=[str(x) for x in u.get("_all_info") or ()]))
        brain = getattr(self.c, "brain", None)
        # I dati del turno davanti alla frase (12/10, per il banco della scelta dei tool): quali
        # blocchi c'erano (ora e chi parla, ricordi, riferimenti, sviluppo, proposta…) e quanto
        # lunghi; mai il loro testo. Vis «turno»: la proiezione non li mette nella storia
        blocchi = [b for b in getattr(brain, "last_dati_turno", None) or ()
                   if isinstance(b, dict) and b.get("nome")]
        if blocchi:
            scritti.append(add("dati_del_turno", blocchi=[
                {"nome": str(b["nome"]), "caratteri": int(b.get("caratteri") or 0)}
                for b in blocchi]))
        # Gli argomenti decisi dal modello in questa risposta (§ 13): subito dopo la frase,
        # così il turno che ha cambiato argomento è del nuovo
        if self.attivo:
            for a in list(getattr(brain, "last_argomento", None) or ()):
                if isinstance(a, dict) and a.get("tipo") in ("argomento_nuovo",
                                                             "argomento_ripreso"):
                    scritti.append(add(a["tipo"], **{k: v for k, v in a.items()
                                                     if k != "tipo"}))
        tools = getattr(brain, "tools", None)
        passata = 0
        for m in msgs:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for c in m["tool_calls"]:
                    if isinstance(c, dict):
                        # proposta_rispondi: stato della macchina, mai storia (§ 3.8): la
                        # visibilità lo dice alla scrittura
                        fuori = c.get("name") == STATO_TOOL
                        scritti.append(add("chiamata_tool", id=c.get("id"), nome=c.get("name"),
                                           argomenti=c.get("arguments") or {},
                                           passata=passata,
                                           **({"vis": "registro"} if fuori else {})))
                passata += 1
            elif m.get("role") == "tool":
                nome = m.get("name")
                spec = tools.get(nome) if tools is not None and hasattr(tools, "get") else None
                f = _fonti_di(m)
                scritti.append(add(
                    "esito_tool", id=m.get("tool_call_id"), nome=nome,
                    contenuto=str(m.get("content") or ""),
                    riservato=bool(getattr(spec, "riservato", False)),
                    personale=nome in _personali(),
                    non_fidato=bool(getattr(spec, "non_fidato", False)),
                    # Il non fidato che resta nella storia in busta (13/10, il tool notizie)
                    **({"resta": True} if getattr(spec, "resta_in_storia", False) else {}),
                    **({"fonte": f} if f else {}),
                    **({"vis": "registro"} if nome == STATO_TOOL else {})))
        # Le schede mandate agli schermi in questa risposta (12/10): tipo, chiave, titolo e su
        # quanti schermi; il contenuto resta nella cronologia degli schermi (vis «schermo»)
        for sc in getattr(brain, "last_schede_mandate", None) or ():
            if isinstance(sc, dict):
                scritti.append(add("scheda_mandata", tipo=sc.get("tipo"), chiave=sc.get("chiave"),
                                   titolo=sc.get("titolo"), schermi=sc.get("schermi")))
        # Il testo generato del turno (vis registro): serve al promemoria della parte non
        # detta se la risposta è stata interrotta (§ 11.4)
        generato = getattr(brain, "testo_generato", None) if self.attivo else None
        if generato and any(x.get("interrotta") for x in self._pezzi_turno):
            scritti.append(add("passata_modello", n=len(generato),
                               testo=" ".join(str(x) for x in generato)[-4000:]))
        return scritti

    def _proposte(self, reg, conv, add) -> list:
        st = reg.stato
        p = getattr(conv, "pending", None)
        prima = st.get("pending")
        if p is prima:
            return []
        scritti = []
        if st.get("proposta"):
            come = "sostituita" if p else "chiusa_oggi"
            if getattr(getattr(self.c, "brain", None), "_proposta_da_parte", False):
                come = "da_parte"               # il cambio d'argomento (§ 13)
            if prima and isinstance(prima, dict) and time.monotonic() > float(
                    prima.get("scade") or 0):
                come = "scaduta_tempo"
            scritti.append(add("proposta_chiusa", id=st.pop("proposta"), come=come,
                               eseguita=None))
        if isinstance(p, dict) and p.get("tool"):
            pid = f"p{reg.seq + 1}"
            scade = p.get("scade")
            scritti.append(add(
                "proposta_aperta", id=pid, tool=p.get("tool"),
                argomenti=p.get("args") if isinstance(p.get("args"), dict) else None,
                domanda=p.get("domanda"), cosa=p.get("cosa"), origine="oggi",
                tipo="dato" if p.get("su_misura") or p.get("risposta") or p.get("args_testo")
                else "si_no",
                chi=p.get("chi_nome"), satellite=p.get("satellite"),
                scade=(time.time() + float(scade) - time.monotonic())
                if isinstance(scade, (int, float)) else None, turni=p.get("turno")))
            st["proposta"] = pid
        return scritti

    # ── il confronto con la storia di Brain ──
    def _confronta(self, reg, conv, vista, msgs) -> tuple[dict, int, int]:
        st = reg.stato
        hist = getattr(conv, "history", None) or []
        # I messaggi usciti dalla storia (taglio, compressione) non si tengono in memoria
        vivi = {id(m) for m in hist if isinstance(m, dict)}
        tag = st.setdefault("tag", {})
        for k in [k for k in tag if k not in vivi]:
            del tag[k]
        st["visti"] = {k for k in st.get("visti", set()) if k in vivi}
        per_seq = {x["chiave"]: x for x in vista["turni"]}
        trovate: list[tuple] = []
        non_oss = 0
        visti_seq = set()
        for u, ms in _turni_storia(hist):
            if u is None:
                testa = vista["turni"][0] if vista["turni"] and vista["turni"][0][
                    "persona"] is None else None
                if testa is not None:
                    visti_seq.add(testa["chiave"])
                    for m in self._parlato(testa, ms, {}):
                        trovate.append((testa["chiave"], m))
                continue
            tag = st.get("tag", {}).get(id(u))
            if tag is None or tag[0] is not u:
                non_oss += 1
                continue
            seq = tag[1]
            x = per_seq.get(seq)
            if x is None:
                trovate.append((seq, "turno_solo_storia"))
                continue
            visti_seq.add(seq)
            if _norm(u.get("content")) != _norm(x["ingressi"] + x["persona"]):
                trovate.append((seq, "persona_modulo" if x["modulo"] else "persona_altro"))
            for m in self._parlato(x, ms, {"esito": x.get("esito")}):
                trovate.append((seq, m))
            nomi_s = [c.get("name") for m in ms if m.get("role") == "assistant"
                      for c in m.get("tool_calls") or () if isinstance(c, dict)]
            if nomi_s != [c["name"] for c in x["chiamate"]]:
                trovate.append((seq, "tool_struttura"))
        # La forma dei risultati: i messaggi dei tool proiettati e quelli della storia
        storia_tool = [(m.get("tool_call_id"), m.get("content")) for m in hist
                       if isinstance(m, dict) and m.get("role") == "tool"]
        proj_tool = {m.get("tool_call_id"): m.get("content") for m in msgs
                     if m.get("role") == "tool"}
        for cid, contenuto in storia_tool:
            if cid in proj_tool and proj_tool[cid] != contenuto:
                trovate.append((f"tool:{cid}", "tool_forma"))
        for x in vista["turni"]:
            if x["chiave"] not in visti_seq and x["persona"] is not None \
                    and x["chiave"] >= int(st.get("da") or 0):
                trovate.append((x["chiave"], "turno_solo_eventi"))
        r = getattr(conv, "riassunto", None)
        rt = r.get("testo") if isinstance(r, dict) else None
        if (rt or None) != (vista.get("riassunto") or None) and st.get("tag"):
            trovate.append(("riassunto", "riassunto"))
        dette = st.setdefault("dette", set())
        nuove: dict[str, int] = {}
        for k in trovate:
            if k not in dette:
                dette.add(k)
                nuove[k[1]] = nuove.get(k[1], 0) + 1
        return nuove, non_oss, len({k[0] for k in trovate})

    @staticmethod
    def _parlato(x: dict, msgs: list, info: dict) -> list[str]:
        sentite = [(testo, atto) for testo, atto, _a, _c in proiezioni.detto(x)]
        canali = {c for _t, _a, _u, c in proiezioni.detto(x)}
        return misura.motivi_parlato(
            sentite, _testo_assistente(msgs),
            {**info, "interrotta": x["interrotta"],
             "canale": "scritto" if canali & {"scritto", "muta"} else "voce"})


STATO_TOOL = "proposta_rispondi"


def _personali() -> frozenset:
    """I tool personali di Brain (la loro frase pronta resta, i dati no: `_seal_private`)."""
    try:
        from ..brain import _PERSONAL_TOOLS
        return _PERSONAL_TOOLS
    except Exception:  # noqa: BLE001
        return frozenset()


def _fonti_di(m: dict) -> str:
    """Le fonti non fidate di un messaggio (la busta nel testo, la traccia `_fonte`, le foto)."""
    try:
        from ..provenienza import fonti
        return ",".join(sorted(fonti([m])))
    except Exception:  # noqa: BLE001
        return str(m.get("_fonte") or "")


def _finestra(st: dict, conv) -> int | None:
    """Il primo turno della storia di Brain ancora in vista (dopo un taglio o una compressione):
    il seq del suo detto_persona, o None."""
    vivi = {id(m) for m in getattr(conv, "history", None) or () if isinstance(m, dict)}
    seqs = [s for k, (u, s) in (st.get("tag") or {}).items() if k in vivi and u is not None]
    return min(seqs) if seqs else None


def _finestra_attiva(conv, scritti=()) -> int | None:
    """Passo 3: il primo turno ancora nella storia di Brain dopo un taglio in testa o una
    compressione (`Conversazione.finestra_da`, scritto da `togli_in_testa`): il `_seq` del
    primo turno proiettato rimasto, o il turno di adesso se non ne è rimasto nessuno."""
    f = getattr(conv, "finestra_da", None)
    if f == "vivo":
        return next((e.seq for e in scritti
                     if e.tipo in ("detto_persona", "modulo_compilato")), None)
    return f if isinstance(f, int) and not isinstance(f, bool) else None


def _turno_chiuso(rec: dict) -> dict:
    tempi = {k: rec[k] for k in ("stt_s", "prima_frase_s", "prima_voce_s", "primo_suono_s")
             if isinstance(rec.get(k), (int, float))}
    ctx = rec.get("contesto") if isinstance(rec.get("contesto"), dict) else {}
    contesto = {k: ctx[k] for k in ("token", "finestra") if k in ctx}
    if isinstance(rec.get("lettura_s"), (int, float)):
        contesto["lettura_s"] = rec["lettura_s"]
    out = {"esito": rec.get("esito"), "regole": list(rec.get("regole") or ())}
    if tempi:
        out["tempi"] = tempi
    if contesto:
        out["contesto"] = contesto
    return out


def _somma(a: dict, b: dict) -> dict:
    """Due campi `parlato` / `eventi_ombra` insieme (gli annunci fra un turno e l'altro)."""
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, bool) or not isinstance(v, (int, float, dict, list)):
            out[k] = v if k not in out else out[k]
        elif isinstance(v, dict):
            d = dict(out.get(k) or {})
            for kk, vv in v.items():
                d[kk] = d.get(kk, 0) + vv if isinstance(vv, (int, float)) else vv
            out[k] = d
        elif isinstance(v, list):
            out[k] = sorted(set(out.get(k) or []) | set(v))
        elif k == "contesto_ms":
            out[k] = max(float(out.get(k) or 0), float(v))
        elif k == "registro":
            out[k] = v
        else:
            out[k] = (out.get(k) or 0) + v
    return out
