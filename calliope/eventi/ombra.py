"""
Il registro degli eventi in ombra accanto al ciclo della voce (10/10/2026, passi 0 e 1 del § 8
di docs/ricerche/2026-10-10-registro-eventi.md).

Una `Ombra` per corsia. Non decide niente e non tocca la storia di Brain:

1. **Che cosa è andato alla voce.** La voce della corsia (`tts.Speaker.osservatore`) le dice
   ogni frase mandata (`say`, `say_cached`) e, a ogni `start_turn`, quali si sono sentite per
   intero (`played`) e se c'è stata un'interruzione. In memoria, microsecondi: niente disco nel
   percorso della prima frase. L'atto (quale parte del ciclo ha parlato) si ricava dalla funzione
   del ciclo che chiama la voce: nel passo 2 lo dirà l'uscita unica (`Uscita.di`).
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
"""
from __future__ import annotations

import json
import sys
import threading
import time
import weakref

from . import misura, proiezioni
from .registro import (Registri, porta_annuncio, porta_avviso_tutore, porta_coda,
                       porte_usate)
from .tipi import per_disco

SPENTO, OMBRA, ATTIVO = "spento", "ombra", "attivo"
MODI = (SPENTO, OMBRA)


def modo(cfg) -> str:
    """`eventi` della configurazione: «spento» o «ombra» («attivo» è il passo 3: config.py lo
    rifiuta e resta «ombra»)."""
    m = str(getattr(cfg, "eventi", OMBRA) or OMBRA).strip().lower()
    return m if m in MODI else OMBRA


# La funzione del ciclo che ha chiamato la voce → l'atto (§ 1.1, § 4.2)
ATTI = {
    "_di_frase": "risposta", "_ricerca_promessa": "risposta",
    "_rispondi": "errore", "errore_nel_giro": "errore",
    "_chiusure": "cortesia",
    "_secondo_cancello": "protezione_cancello",
    "richieste_al_tutore": "richiesta_tutore",
    "_annuncia_documenti": "annuncio", "_annuncia_installazioni": "annuncio",
    "_annuncia_lavori": "annuncio", "_annuncia_estensioni": "annuncio",
    "_cassetto_dopo": "cassetto", "_modulo_dallo_schermo": "modulo",
    "_annuncia_agenda": "agenda", "avvisi_ai_tutori": "avviso_tutore",
    "_inizio_giro": "registrazione", "_esito_registrazione": "registrazione",
    "_arruolamento": "registrazione", "_dopo_la_risposta": "registrazione",
    "_inizia_primo_utente": "registrazione", "_nome_reale": "registrazione",
    "_solo_il_nome": "saluto", "_chiedi_chi_parla": "chi_parla",
    "_senza_domanda": "senza_domanda",
    "_fuori_orario": "protezione", "_protezione_dopo": "protezione",
    "_annuncia_giochi": "giochi",
    "_addormentati": "chiusura", "_uscite": "chiusura", "_esci_dalla_registrazione": "chiusura",
    "_saluto_ed_eco": "saluto_avvio",
}
_FILE_CICLO = ("ciclo.py", "main.py")
# Esiti del turno con la frase della persona nella conversazione (oggi entra nella storia)
ESITI_PERSONA = frozenset({"risposta", "interruzione", "cortesia", "protezione",
                           "non_rivolta", "modulo"})
# Esiti che chiudono la conversazione: la frase e la chiusura vanno nel segmento che si chiude
ESITI_CHIUSURA = frozenset({"dormi", "uscita", "nuova_conversazione"})
FINESTRA_MAX = 400                  # frasi in memoria al più (un ciclo finto che non chiude mai)


def atto_del_chiamante(tipo: str, profondita: int = 12) -> str:
    """Il nome dell'atto dalla funzione del ciclo che ha chiamato la voce. `say_cached` è una
    frase d'attesa, tranne la cortesia («Prego!»)."""
    f = sys._getframe(2)
    nome = None
    for _ in range(profondita):
        if f is None:
            break
        co = f.f_code
        if co.co_name in ATTI and co.co_filename.endswith(_FILE_CICLO):
            nome = co.co_name
            break
        f = f.f_back
    if tipo == "cached":
        return "cortesia" if nome == "_chiusure" else "attesa"
    return ATTI.get(nome, "altro") if nome else "altro"


def _forma_brain() -> proiezioni.Forma:
    """I numeri della forma dei turni chiusi di Brain di oggi (la proiezione non importa Brain)."""
    try:
        from .. import brain as b
        return proiezioni.Forma(risultato_max=int(b.OLD_RESULT_CHARS), traccia=b._OLD_TRACE,
                                ora_di_allora=tuple(dict(b._OLD_TIME).items()))
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

    # ── 1. che cosa va alla voce (dal thread di chi chiama say) ──
    def collega(self, speaker):
        try:
            speaker.osservatore = self.sente
        except Exception:  # noqa: BLE001 — una voce finta senza attributi
            pass

    def sente(self, tipo: str, testo=None, played=None, interrotta=False, muto=False):
        """Dalla voce: «say» e «cached» (una frase mandata), «fine» (le frasi sentite per
        intero del pezzo che si chiude). In memoria e basta."""
        try:
            if tipo == "fine":
                item = ("fine", list(played or ()), bool(interrotta))
            else:
                item = (tipo, str(testo or ""), atto_del_chiamante(tipo), bool(muto))
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
            if self.errori == 1 or self.errori % 100 == 0:
                self.log(f"   [EVENTI] ombra non riuscita ({type(e).__name__}: {e}); errori "
                         f"finora: {self.errori}")
            if rec is not None:
                rec.setdefault("eventi_ombra", {})["errori"] = 1

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
        scritto = t is not None and getattr(t, "scritto", None) is not None
        pezzi: list[dict] = []
        cur: list[tuple] = []

        def chiudi(played, interrotta):
            if not cur:
                return
            frasi = []
            for tipo, testo, atto, muto in cur:
                canale = "muta" if muto else ("scritto" if scritto and atto == "risposta"
                                               else "voce")
                frasi.append((testo, atto, canale, tipo))
            k = len(frasi)
            if interrotta:
                sentito = _norm(" ".join(played or ()))
                k, pos = 0, 0
                for testo, _a, _c, tipo in frasi:
                    if tipo == "cached":
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
                          "inviate": len(frasi), "interrotta": bool(interrotta)})
            cur.clear()

        for item in finestra:
            if item[0] == "fine":
                chiudi(item[1], item[2])
            else:
                cur.append(item)
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
        parlato = misura.misura_finestra(pezzi, _testo_assistente(ultimo), info)
        if reg is None:
            st["pending"] = pending
        ombra = None
        # Una frase non rivolta a Calliope (ignorata, scartata, vuota, doppione) non è di
        # nessuna conversazione: resta solo nel registro dei turni (§ 1.4)
        esito = (rec or {}).get("esito")
        della_conv = bool(pezzi) or esito in ESITI_PERSONA or esito in ESITI_CHIUSURA
        if reg is not None and della_conv:
            ombra = self._scrivi_e_confronta(reg, conv, rec, t, pezzi, info, turni_s)
        if rec is None:
            self._riporta(parlato, ombra)
            return
        self._unisci_riporto(rec)
        if parlato:
            rec["parlato"] = _somma(rec.get("parlato") or {}, parlato)
        if ombra is not None:
            rec["eventi_ombra"] = _somma(rec.get("eventi_ombra") or {}, ombra)

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
            if not persona and atti and atti <= misura.ANNUNCI | {"attesa"} \
                    and "avviso_tutore" not in atti:
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
                self._ritagga(reg, conv, nuovo=bool(info.get("turno_nuovo")))
                # Le differenze già nella conversazione ripresa erano state contate prima del
                # riavvio: si segnano come dette, senza contarle di nuovo
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
            st["da"] = _finestra(st, conv) or st.get("da")
        if self.registri is not None:
            self.registri.scrivi()
        if self._forma is None:
            self._forma = _forma_brain()
        t0 = time.perf_counter()
        vista = proiezioni.turni(eventi, st.get("da"))
        msgs = proiezioni.messaggi(vista, self._forma)
        ms = (time.perf_counter() - t0) * 1000.0
        diff, non_oss, aperte = self._confronta(reg, conv, vista, msgs)
        out: dict = {"eventi": reg.seq - n0, "contesto_ms": round(ms, 3),
                     "registro": reg.chiave.split(":", 1)[0],
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

        def add(_tipo, **dati):
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
        if esito in ESITI_PERSONA or (solo_chiusura and esito in ESITI_CHIUSURA):
            sc = getattr(self.c, "speaker_ctx", None)
            canale = "scritto" if t is not None and getattr(t, "scritto", None) is not None \
                else "voce"
            if esito == "modulo":
                persona = add("modulo_compilato", modulo=rec.get("modulo"),
                              campi=list(rec.get("campi") or ()))
            elif isinstance(testo, str):
                fermato = (rec.get("testo") is None and esito not in ("non_rivolta",))                     or bool(riservato(testo))
                persona = add(
                    "detto_persona", testo=testo, canale=canale,
                    come=getattr(sc, "identified_by", None),
                    satellite=sat, sfida=bool(getattr(getattr(self.c, "brain", None),
                                                      "last_sfida", False)
                                              and esito == "risposta"),
                    brain=esito == "risposta",
                    **({"_non_su_disco": ["testo"]} if fermato else {}))
            if persona is not None:
                st["frase"] = 0
                if esito == "non_rivolta":
                    add("turno_escluso", escluso=persona.seq, motivo="non_rivolta")
                elif not solo_chiusura and turni_s is not None:
                    scritti += self._dalla_storia(reg, conv, persona, info, turni_s, add)
        # Ciò che è andato alla voce, frase per frase, e quanto si è sentito
        for p in pezzi:
            frasi = [(i, f) for i, f in enumerate(p["frasi"])
                     if not solo_chiusura or f[1] == "chiusura"]
            if not frasi:
                continue
            da = st.get("frase", 0)
            for i, (testo_f, atto, canale) in frasi:
                autore = "contenuto" if atto == "risposta" else "atto"
                if atto == "risposta" and any(_norm(testo_f) and _norm(testo_f) in _norm(f)
                                              for f, _s in info.get("frasi_tool") or ()):
                    autore = "esito"
                add("detto_calliope", testo=testo_f, autore=autore, atto=atto,
                    frase=st.get("frase", 0), canale=canale, satellite=sat,
                    vis="registro" if atto in proiezioni.ATTI_FUORI else None,
                    **riservato(testo_f))
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
            da = _finestra(st, conv)
            add("compressione", fino_a=max(0, int(da or 1) - 1), riassunto=str(r["testo"]))
        return scritti

    def _dalla_storia(self, reg, conv, persona, info, turni_s, add) -> list:
        """Il messaggio nuovo della persona nella storia: lo si riconosce (per il confronto),
        gli ingressi davanti alla frase e le chiamate del turno (ricopiate a fine turno)."""
        st = reg.stato
        nuovi = [(u, msgs) for u, msgs in turni_s if u is not None
                 and id(u) not in st["visti"]]
        for u, _m in turni_s:
            if u is not None:
                st["visti"].add(id(u))
        if not nuovi:
            return []
        u, msgs = nuovi[-1]
        st["tag"][id(u)] = (u, persona.seq)
        if st.get("da") is None:
            st["da"] = persona.seq
        scritti = []
        contenuto = str(u.get("content") or "")
        frase = str(persona.dati.get("testo") or "") if persona.tipo == "detto_persona" else ""
        if info.get("capito") and persona.tipo == "detto_persona":
            cap = getattr(getattr(self.c, "brain", None), "last_capito", None) or {}
            scritti.append(add("trascrizione_capita", prima=cap.get("prima"),
                               dopo=cap.get("dopo"), accettata=True))
            frase = str(cap.get("dopo") or frase)
        if frase and contenuto.endswith(frase) and len(contenuto) > len(frase):
            prefisso = contenuto[:len(contenuto) - len(frase)]
            tipo = "foto_in_ingresso" if u.get("_img") else "dato_in_ingresso"
            dati = {"testo": prefisso}
            if tipo == "dato_in_ingresso":
                dati["fonte"] = "busta"
            scritti.append(add(tipo, **dati))
        for m in msgs:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for c in m["tool_calls"]:
                    if isinstance(c, dict):
                        scritti.append(add("chiamata_tool", id=c.get("id"), nome=c.get("name"),
                                           argomenti=c.get("arguments") or {}))
            elif m.get("role") == "tool":
                scritti.append(add("esito_tool", id=m.get("tool_call_id"), nome=m.get("name"),
                                   contenuto=str(m.get("content") or "")))
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
                tipo="dato" if p.get("su_misura") or p.get("risposta") else "si_no",
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


def _finestra(st: dict, conv) -> int | None:
    """Il primo turno della storia di Brain ancora in vista (dopo un taglio o una compressione):
    il seq del suo detto_persona, o None."""
    vivi = {id(m) for m in getattr(conv, "history", None) or () if isinstance(m, dict)}
    seqs = [s for k, (u, s) in (st.get("tag") or {}).items() if k in vivi and u is not None]
    return min(seqs) if seqs else None


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
