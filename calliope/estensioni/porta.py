"""
La porta stretta (04/10/2026): l'unico modo in cui un'estensione tocca qualcosa.

Per ogni richiesta «calliope/<azione>» dal container:
1. guardrail (calliope/guardrail.py): permesso del manifesto **approvato**, quote, classe
   sicura / pericolosa / vietata; il secondo parere del modello grande può solo alzarla;
2. vietata → errore all'estensione; pericolosa → l'esecuzione si ferma e si chiede alla
   persona (salvo un «sì, sempre» valido); sicura → si esegue;
3. l'azione la fanno **i tool veri di Calliope** (`ToolRegistry.call`) con il livello di chi ha
   usato l'estensione (mai più alto di quello del manifesto): regole della casa, permessi e
   frasi d'errore sono gli stessi della voce. Dal risultato si tolgono i campi per Brain;
4. ogni decisione va nel registro (`decisioni.jsonl`) con il nome della regola.

Dal 05/10 (scope e flussi, calliope/estensioni/manifesto.py): ogni lettura di dati personali
riuscita **contamina** l'esecuzione con la sua categoria («casa», «agenda», «liste:spesa»), e i
dati propri scritti dopo una lettura restano contaminati anche per le esecuzioni dopo
(`Archivio.contamina`). Una richiesta di rete con dati letti va solo lungo un flusso approvato
(guardrail.valuta_porta); la richiesta la fa `calliope.web.rete.RetePubblica` (solo internet
pubblico, anche dopo i reindirizzamenti), e ogni uscita, fatta o bloccata, va nel registro
delle uscite (`uscite.jsonl`).

Nessun segreto passa da qui: l'estensione vede risultati, mai token o percorsi.

Dal 08/10 (giro vero della DGX, il meteo per città: cinque versioni corrette alla cieca) ogni
richiesta di rete lascia nell'esecuzione una **traccia per lo sviluppo** (`Esecuzione.traccia`:
metodo, URL ripulito, esito, l'inizio della risposta o l'errore, durata), che il collaudo passa
all'agente (calliope/sviluppo.py); e un URL con spazi o caratteri non codificati si rifiuta
con un errore che dice come scriverlo (`pagina.url_non_codificato`), anche con la funzione finta
delle prove.

Dal 08/10 notte (sonde dell'agente, docs/ricerche/2026-10-08-sonde-agente.md § 9.6): una riga
della traccia dice se la richiesta l'ha rifiutata la porta (`rifiutata`: non conta per gli host
«noti» dello sviluppo), e un'esecuzione di **ricollaudo** (`es.modo == "ricollaudo"`, la
versione appena consegnata provata da Calliope con i casi della persona) non chiede mai
conferme: una classe pericolosa diventa vietata (regola `ricollaudo_senza_conferme`).
"""

from __future__ import annotations

import copy
import json
import re
import time
from types import SimpleNamespace

from .. import guardrail as gr

# Campi dei risultati dei tool che sono per Brain o per la voce, non per l'estensione
_PER_BRAIN = {"in_sospeso", "scheda", "schede", "riferimento", "riferimento_agenda",
              "risposta_finale", "per_il_resto"}
MAX_DATI_BYTE = 1_000_000
MAX_DATO_BYTE = 200_000
_NOME_DATO = re.compile(r"^[a-zA-Z0-9][\w\-. ]{0,60}$")
# Risposta di rete data all'estensione: troncata
MAX_RETE_BYTE = 1_000_000
MAX_RETE_TESTO = 200_000
# Traccia di rete per lo sviluppo: richieste tenute, caratteri dell'URL e della risposta
MAX_TRACCIA = 12
TRACCIA_URL = 300
TRACCIA_RISPOSTA = 300
# Chiavi JSON di primo livello tenute per richiesta (il confronto tra collaudi, 08/10 notte)
TRACCIA_CHIAVI = 20
# La risposta vera intera come esempio per i test dell'agente (08/10 notte, esempi_veri/):
# solo GET verso un host del manifesto, senza dati di casa letti né dati riservati; al più
# ESEMPI_PER_ESECUZIONE indirizzi diversi per esecuzione, ESEMPIO_MAX caratteri ciascuno
ESEMPIO_MAX = 8000
ESEMPI_PER_ESECUZIONE = 2


class Porta:
    def __init__(self, servizio, secondo_parere=None, scarica=None):
        self.svc = servizio
        self.parere = secondo_parere
        # La funzione che scarica (le prove la sostituiscono): calliope.web.pagina.scarica
        self._scarica = scarica

    # ── decisione ──
    def gestisci(self, es, azione: str, params: dict) -> dict:
        """{"risultato": …} | {"errore": …} | {"conferma": True, "valutazione", "domanda"}."""
        perm = (es.manifesto or {}).get("permessi") or {}
        v = gr.valuta_porta(azione, params, perm, es.storia, es.manifesto.get("titolo", ""))
        if v.classe == gr.VIETATA and azione.startswith("rete_"):
            # Anche un'uscita bloccata prima di partire resta nel registro delle uscite
            self.svc.rete.registra(self._origine(es), gr.host_di(params.get("url")),
                                   "POST" if azione == "rete_invia" else "GET", "bloccata",
                                   f"{v.regola}: {v.motivo}")
            self._traccia(es, azione, params.get("url"),
                          {"errore": f"non concesso: {v.motivo}"}, 0, rifiutata=True)
        if v.classe == gr.SICURA and self.parere is not None and azione in gr.CON_TESTO:
            v = self.parere.applica(v, es.manifesto.get("titolo", ""),
                                    es.manifesto.get("descrizione", ""), azione, params)
        if v.classe == gr.PERICOLOSA and getattr(es, "modo", "") == "ricollaudo":
            # Il ricollaudo gira senza la persona (08/10 notte): niente domande, mai
            self.svc.nota_regola("ricollaudo_senza_conferme")
            if azione.startswith("rete_"):
                self.svc.rete.registra(self._origine(es), gr.host_di(params.get("url")),
                                       "POST" if azione == "rete_invia" else "GET", "bloccata",
                                       "ricollaudo_senza_conferme")
                self._traccia(es, azione, params.get("url"),
                              {"errore": "non concesso: nel ricollaudo niente conferme"}, 0,
                              rifiutata=True)
            v = gr.Valutazione(gr.VIETATA, "nel ricollaudo di Calliope non si chiede niente "
                               f"alla persona ({v.motivo})", "ricollaudo_senza_conferme")
        es.storia.conta(azione)
        if v.classe == gr.VIETATA:
            return self._registra(es, azione, params, v, "rifiutata",
                                  {"errore": f"non concesso: {v.motivo}"})
        if v.classe == gr.PERICOLOSA:
            if v.ricorrente and self.svc.archivio.sempre(es.nome, es.persona, v.regola,
                                                         v.bersaglio):
                return self._esegui(es, azione, params, v, "sempre")
            return {"conferma": True, "valutazione": v,
                    "domanda": gr.domanda(v, es.manifesto.get("titolo", es.nome))}
        return self._esegui(es, azione, params, v, "eseguita")

    def dopo_conferma(self, es, azione: str, params: dict, esito: dict, dec: dict | None) -> dict:
        v = esito["valutazione"]
        if dec is None:
            return self._registra(es, azione, params, v, "scaduta",
                                  {"errore": "nessuna risposta dalla persona: non fatto"})
        if not dec.get("si"):
            return self._registra(es, azione, params, v, "negata",
                                  {"errore": "la persona ha detto di no: non fatto"},
                                  chi=dec.get("chi"))
        if dec.get("sempre") and v.ricorrente:
            self.svc.archivio.concedi_sempre(es.nome, es.persona, v.regola, v.bersaglio)
        return self._esegui(es, azione, params, v, "confermata", chi=dec.get("chi"),
                            sempre=bool(dec.get("sempre") and v.ricorrente))

    def _registra(self, es, azione, params, v, esito_txt, out, **extra) -> dict:
        riga = {"esecuzione": es.id, "estensione": es.nome, "versione": es.versione,
                "persona": es.persona_nome, "azione": azione,
                "argomenti": _riduci(params, self.svc.rete), "classe": v.classe, "regola": v.regola,
                "motivo": _motivo(v.motivo, params, self.svc.rete), "esito": esito_txt, **extra}
        es.decisioni.append(riga)
        self.svc.archivio.registra(riga)
        if esito_txt in ("rifiutata", "negata", "scaduta"):
            self.svc.nota_regola(v.regola if esito_txt == "rifiutata" else
                                 f"estensione_{esito_txt}")
        return out

    # ── esecuzione con i tool di Calliope ──
    def _ctx(self, es):
        base = self.svc.tool_ctx
        ctx = copy.copy(base)
        livello = es.livello
        ctx.speaker_ctx = SimpleNamespace(
            current_level=livello, current_speaker=es.persona_nome, identified_by="estensione",
            profile_level=livello, from_session=False, sfida=None, sfida_superata=False)
        ctx.schermi = None           # le schede le manda la porta, non i tool
        ctx.regole = []
        ctx.user_text = ""
        # Le azioni dell'estensione le governa il guardrail della porta, non lo stato del turno
        # della voce (la politica dei tool, calliope/politica.py, vale per il modello)
        ctx.politica = None
        return ctx

    def _tool(self, es, nome: str, args: dict) -> dict:
        reg = self.svc.registry
        if reg is None or reg.get(nome) is None:
            return {"errore": f"«{nome}» non c'è su questo Calliope"}
        try:
            out = json.loads(reg.call(nome, args, self._ctx(es), es.livello))
        except (ValueError, TypeError) as e:
            return {"errore": f"risposta non valida: {e}"}
        if not isinstance(out, dict):
            return {"risultato": {"valore": out}}
        frase = out.get("conferma") or out.get("risposta_finale") or ""
        pulito = {k: v for k, v in out.items() if k not in _PER_BRAIN}
        if frase and "testo" not in pulito:
            pulito["testo"] = frase
        if out.get("ok") is False or "errore" in out:
            return {"errore": str(out.get("errore") or out.get("fatto") or frase
                                  or "non riuscito")[:300]}
        return {"risultato": pulito}

    @staticmethod
    def _origine(es) -> dict:
        if getattr(es, "modo", "") == "ricollaudo":
            # Il ricollaudo alla consegna (08/10 notte): il lavoro e lo sviluppo, per il
            # registro delle uscite; «esecuzione» tiene la somma dei dati riservati a pezzi
            return {"origine": "ricollaudo", "estensione": es.nome, "esecuzione": es.id,
                    "lavoro": getattr(es, "lavoro", None), "sviluppo": getattr(es, "sviluppo",
                                                                               None),
                    "persona": es.persona_nome}
        return {"origine": "estensione", "estensione": es.nome, "versione": es.versione,
                "esecuzione": es.id, "persona": es.persona_nome}

    def _esegui(self, es, azione: str, params: dict, v, esito_txt: str, **extra) -> dict:
        try:
            out = self._fai(es, azione, params)
        except Exception as e:  # noqa: BLE001 — l'errore torna all'estensione
            out = {"errore": f"{type(e).__name__}: {e}"[:300]}
        if "errore" not in out and azione in gr.LETTURE_CASA:
            # I dati letti contaminano l'esecuzione: da qui in poi la rete solo lungo i flussi
            # Anche l'elenco: i nomi dei dati sono dati (05/10, banco d'attacco: un segreto
            # scritto come nome di un file passava all'esecuzione dopo senza contaminarla)
            if azione in ("dati_leggi", "dati_elenca"):
                es.storia.contamina(*self.svc.archivio.contaminazione(es.nome))
            else:
                es.storia.contamina(gr.categoria_lettura(azione, params))
        if "errore" in out:
            extra["errore"] = str(out["errore"])[:200]
        return self._registra(es, azione, params, v,
                              esito_txt if "errore" not in out else "errore", out,
                              **extra)

    def _fai(self, es, azione: str, p: dict) -> dict:
        s = lambda k, d="": str(p.get(k) if p.get(k) is not None else d).strip()  # noqa: E731
        if azione == "casa_stato":
            return self._tool(es, "casa_stato", {"cosa": s("cosa")})
        if azione == "casa_comando":
            return self._tool(es, "casa_comando", {"comando": s("comando")})
        if azione in ("lista_leggi", "lista_aggiungi", "lista_togli"):
            voci = p.get("voci") or []
            cose = ", ".join(str(x) for x in voci) if isinstance(voci, list) else str(voci)
            args = {"lista": s("lista", "spesa")}
            if azione != "lista_leggi":
                args["cose"] = cose
            return self._tool(es, azione, args)
        if azione == "agenda_elenca":
            return self._tool(es, "agenda_elenca", {})
        if azione == "timer_imposta":
            return self._tool(es, "timer_imposta", {"durata": s("durata"), "nome": s("nome")})
        if azione == "schermo_mostra":
            return self.svc.mostra(es, s("titolo")[:80], s("testo")[:2000])
        if azione.startswith("dati_"):
            return self._dati(es, azione, p)
        if azione in ("rete_leggi", "rete_invia"):
            return self._rete(es, azione, p)
        return {"errore": f"azione sconosciuta: {azione}"}

    # ── dati propri ──
    def _dati(self, es, azione: str, p: dict) -> dict:
        cart = self.svc.archivio.cartella_dati(es.nome)
        if azione == "dati_elenca":
            nomi = sorted(x.name for x in cart.iterdir()) if cart.is_dir() else []
            return {"risultato": {"nomi": nomi}}
        nome = str(p.get("nome") or "").strip()
        if not _NOME_DATO.match(nome) or ".." in nome:
            return {"errore": "nome dei dati non valido (lettere, cifre, - _ . e spazi)"}
        f = cart / nome
        if azione == "dati_leggi":
            return {"risultato": {"testo": f.read_text(encoding="utf-8") if f.is_file()
                                  else None}}
        if azione == "dati_cancella":
            if f.is_file():
                f.unlink()
            if not any(x.is_file() for x in cart.iterdir()):
                self.svc.archivio.pulisci_contaminazione(es.nome)
            return {"risultato": {"ok": True}}
        testo = str(p.get("testo") or "")
        b = len(testo.encode("utf-8"))
        if b > MAX_DATO_BYTE:
            return {"errore": f"dati troppo grandi (al massimo {MAX_DATO_BYTE} byte)"}
        cart.mkdir(parents=True, exist_ok=True)
        altri = sum(x.stat().st_size for x in cart.iterdir() if x.is_file() and x != f)
        if altri + b > MAX_DATI_BYTE:
            return {"errore": "spazio dei dati esaurito"}
        from ..persistenza import scrivi_atomico
        # Prima la contaminazione, poi i dati: mai dati scritti senza la loro etichetta
        self.svc.archivio.contamina(es.nome, es.storia.contaminazione)
        scrivi_atomico(f, testo)
        return {"risultato": {"ok": True}}

    # ── rete ──
    def _rete(self, es, azione: str, p: dict) -> dict:
        """La richiesta la fa RetePubblica (solo internet pubblico); `host_ammesso` ricontrolla
        lo scope anche dopo ogni reindirizzamento: senza dati letti un sito pubblico (o gli
        host del manifesto), con dati letti solo gli host dei loro flussi."""
        from ..web import pagina
        url = str(p.get("url") or "")
        t0 = time.monotonic()
        # Un URL scritto a mano con spazi o accenti non parte (anche con la funzione finta
        # delle prove): l'errore dice a chi scrive il codice come codificarlo
        rotto = pagina.url_non_codificato(url)
        if rotto:
            if self._scarica is None:
                self.svc.rete.registra(self._origine(es), gr.host_di(url),
                                       "POST" if azione == "rete_invia" else "GET", "bloccata",
                                       "url_non_codificato")
            self.svc.nota_regola("estensione_url_non_codificato")
            return self._traccia(es, azione, url, {"errore": f"rete: {rotto}"}, t0,
                                 rifiutata=True)
        scope = gr._scope((es.manifesto or {}).get("permessi") or {})
        kw = {"max_byte": MAX_RETE_BYTE,
              "timeout_s": float(getattr(self.svc, "rete_timeout_s", 8.0))}
        if azione == "rete_invia":
            host = gr.host_di(url)
            kw.update(metodo="POST", corpo=json.dumps(p.get("dati"), ensure_ascii=False),
                      host_ammesso=lambda h: h == host, max_rimandi=0)
        else:
            kw["host_ammesso"] = gr.host_rete(scope, frozenset(es.storia.contaminazione))
        try:
            if self._scarica is not None:            # le prove vecchie: una funzione finta
                r = self._scarica(url, **kw)
            else:
                r = self.svc.rete.richiesta(url, self._origine(es), **kw)
        except pagina.PaginaVietata as e:
            return self._traccia(es, azione, url, {"errore": f"rete: {e}"}, t0, rifiutata=True)
        except pagina.PaginaNonLetta as e:
            return self._traccia(es, azione, url, {"errore": f"rete: {e}"}, t0)
        if not kw["host_ammesso"](gr.host_di(r.get("url") or url)):
            return self._traccia(es, azione, url,
                                 {"errore": "rete: reindirizzato verso un host non ammesso"}, t0,
                                 rifiutata=True)
        return self._traccia(es, azione, url, {"risultato": {
            "stato": 200, "tipo": r.get("tipo"),
            "testo": str(r.get("testo_grezzo") or "")[:MAX_RETE_TESTO]}}, t0,
            corpo=p.get("dati") if azione == "rete_invia" else None)

    # ── traccia per lo sviluppo (08/10) ──
    def _traccia(self, es, azione: str, url, out: dict, t0: float, corpo=None,
                 rifiutata: bool = False) -> dict:
        """Aggiunge la richiesta alla traccia dell'esecuzione e restituisce `out`. L'URL senza
        dati riservati (e, dopo una lettura di dati di casa, senza i valori dei parametri);
        della risposta solo l'inizio. `rifiutata`: l'ha fermata la porta (o RetePubblica) prima
        che il sito rispondesse. Mai un'eccezione."""
        try:
            tr = getattr(es, "traccia", None)
            if not isinstance(tr, list) or len(tr) >= MAX_TRACCIA:
                return out
            rete = getattr(self.svc, "rete", None)
            contaminata = bool(getattr(getattr(es, "storia", None), "contaminazione", None))
            riga = {"metodo": "POST" if azione == "rete_invia" else "GET",
                    "url": url_per_traccia(url, rete, contaminata),
                    "ms": int((time.monotonic() - t0) * 1000) if t0 else 0}
            if "errore" in out:
                riga["esito"] = "errore"
                riga["errore"] = _pulisci_testo(str(out["errore"]), rete)[:400]
                if rifiutata:
                    riga["rifiutata"] = True
            else:
                ris = out.get("risultato") or {}
                testo = str(ris.get("testo") or "")
                riga.update(esito=f"stato {ris.get('stato')}",
                            tipo=str(ris.get("tipo") or "")[:60],
                            byte=len(testo.encode("utf-8")),
                            inizio=_pulisci_testo(" ".join(testo[:TRACCIA_RISPOSTA * 2].split()),
                                                  rete)[:TRACCIA_RISPOSTA])
                # La forma della risposta (08/10 notte): le chiavi JSON di primo livello, per il
                # confronto tra collaudi riusciti e falliti (sviluppo.confronto)
                forma, chiavi, vuote = forma_json(testo)
                if forma:
                    riga["forma"] = forma
                if chiavi:
                    riga["chiavi"] = [_pulisci_testo(k, rete)[:40] for k in chiavi]
                if vuote:
                    riga["vuote"] = [_pulisci_testo(k, rete)[:40] for k in vuote]
                if (azione == "rete_leggi" and not contaminata and riga["url"] == str(url)
                        and getattr(es, "modo", "") != "ricollaudo"):
                    esempio = self._esempio(es, url, ris, testo, rete)
                    if esempio is not None:
                        riga["esempio"] = esempio
            if azione == "rete_invia" and corpo is not None:
                # Il corpo mandato, ripulito, per il confronto; dopo una lettura di dati di
                # casa solo la sua dimensione
                c = json.dumps(corpo, ensure_ascii=False, default=str)
                riga["corpo"] = (f"({len(c)} caratteri, tolto: dati di casa letti)"
                                 if contaminata else _pulisci_testo(c, rete)[:TRACCIA_RISPOSTA])
            # La doppia codifica (08/10 sera): la richiesta parte, ma la traccia lo dice in
            # chiaro (l'agente, con «name=Borgo%2BAlto» davanti, l'aveva preso per giusto)
            from ..web.pagina import doppia_codifica
            doppia = doppia_codifica(url)
            if doppia:
                riga["avviso"] = doppia
                self.svc.nota_regola("estensione_doppia_codifica")
            tr.append(riga)
        except Exception:  # noqa: BLE001 — la traccia non cambia la richiesta
            pass
        return out

    def _esempio(self, es, url: str, ris: dict, testo: str, rete) -> dict | None:
        """La risposta vera come esempio per i test dell'agente (08/10 notte; sviluppo.py,
        `esempi_veri/`), o None. Solo verso un host scritto nel manifesto (un servizio scelto,
        non una pagina qualunque), al più ESEMPI_PER_ESECUZIONE indirizzi per esecuzione, mai
        con un dato riservato di casa; un dato personale riconosciuto si toglie (e l'esempio
        si segna «ripulito»: CalliopeFinta allora non lo usa al posto della risposta del
        test)."""
        scope = gr._scope((es.manifesto or {}).get("permessi") or {})
        if gr.host_di(url) not in set((scope.get("rete") or {}).get("host") or ()):
            return None
        tr = getattr(es, "traccia", None) or []
        if len({r.get("url") for r in tr if r.get("esempio")} - {url}) >= ESEMPI_PER_ESECUZIONE:
            return None
        if any(r.get("esempio") and r.get("url") == url for r in tr):
            return None                  # lo stesso indirizzo due volte: basta il primo
        corpo = testo[:ESEMPIO_MAX]
        ripulito = corpo
        r = getattr(rete, "riservati", None)
        if r is not None:
            try:
                if r.trova(corpo, forme_personali=False):
                    return None
                if r.ripulitore is not None:
                    ripulito = r.ripulitore.pulisci(corpo)[0]
            except Exception:  # noqa: BLE001 — nel dubbio niente esempio
                return None
        return {"stato": ris.get("stato"), "tipo": str(ris.get("tipo") or "")[:60],
                "testo": ripulito, "troncato": len(testo) > ESEMPIO_MAX,
                "ripulito": ripulito != corpo}


def forma_json(testo: str) -> tuple[str, list[str], list[str]]:
    """(«oggetto JSON» | «lista JSON di N» | «», le chiavi di primo livello, quelle con un
    valore vuoto: [], {}, "", null): la forma della risposta per il confronto tra collaudi
    («results» che manca o che è vuoto). Un testo che non è JSON → («», [], [])."""
    t = str(testo or "").strip()
    if not t or t[0] not in "[{":
        return "", [], []
    try:
        dati = json.loads(t)
    except ValueError:
        return "", [], []
    if isinstance(dati, dict):
        chiavi = [str(k) for k in list(dati)[:TRACCIA_CHIAVI]]
        return "oggetto JSON", chiavi, [k for k in chiavi if dati.get(k) in ([], {}, "", None)]
    if isinstance(dati, list):
        return f"lista JSON di {len(dati)}", [], []
    return "", [], []


def _pulisci_testo(testo: str, rete=None) -> str:
    """Un testo per la traccia senza dati riservati di casa né dati personali riconosciuti."""
    r = getattr(rete, "riservati", None)
    if r is None or not testo:
        return testo
    try:
        if r.trova(testo, forme_personali=False):
            return "[tolto: contiene un dato riservato]"
        if r.ripulitore is not None:
            return r.ripulitore.pulisci(testo)[0]
    except Exception:  # noqa: BLE001
        return "[tolto]"
    return testo


def url_per_traccia(url, rete=None, contaminata: bool = False) -> str:
    """L'URL per la traccia di sviluppo: com'era scritto (gli spazi non codificati restano:
    sono spesso la causa), con l'host del registro, e i valori dei parametri tolti se portano
    un dato riservato o, dopo una lettura di dati di casa, sempre."""
    from urllib.parse import urlsplit
    testo = str(url or "")[:2000].strip()
    try:
        u = urlsplit(testo)
    except ValueError:
        return "[URL illeggibile]"
    host = u.hostname or ""
    if host and rete is not None and hasattr(rete, "host_per_registro"):
        if rete.host_per_registro(host) != host:
            return f"{u.scheme}://[tolto: dato riservato]/[tolto]"
    pezzi = []
    for pezzo in (u.query.split("&") if u.query else ()):
        nome, uguale, valore = pezzo.partition("=")
        if uguale and valore:
            if contaminata:
                valore = "[tolto: dati di casa letti]"
            elif _pulisci_testo(valore, rete) != valore:
                valore = "[tolto]"
        pezzi.append(nome + uguale + valore)
    percorso = u.path
    if contaminata and percorso.count("/") > 1:
        percorso = percorso.rsplit("/", 1)[0] + "/[tolto]"
    elif _pulisci_testo(percorso, rete) != percorso:
        percorso = "/[tolto]"
    out = f"{u.scheme}://{u.netloc}{percorso}" + ("?" + "&".join(pezzi) if u.query else "")
    return out[:TRACCIA_URL] + ("…" if len(out) > TRACCIA_URL else "")


def _motivo(motivo: str, params: dict, rete=None) -> str:
    """Il motivo per il registro, senza un host che porta un dato riservato."""
    h = gr.host_di((params or {}).get("url"))
    if h and rete is not None and hasattr(rete, "host_per_registro"):
        hh = rete.host_per_registro(h)
        if hh != h:
            return str(motivo).replace(h, hh)
    return motivo


def _riduci(params: dict, rete=None) -> dict:
    """Gli argomenti per il registro: testi lunghi accorciati; di un indirizzo solo l'host
    (percorso e query possono portare dati), e i dati mandati no (05/10)."""
    out = {}
    for k, v in (params or {}).items():
        if k == "url":
            h = gr.host_di(v)
            out["host"] = rete.host_per_registro(h) if rete is not None else h
            continue
        if k == "dati":
            out["dati"] = f"({len(json.dumps(v, ensure_ascii=False, default=str))} caratteri)"
            continue
        t = v if isinstance(v, (int, float, bool)) or v is None else str(v)
        out[k] = t[:120] + "…" if isinstance(t, str) and len(t) > 120 else t
    return out
