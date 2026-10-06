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
"""

from __future__ import annotations

import copy
import json
import re
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
        if v.classe == gr.SICURA and self.parere is not None and azione in gr.CON_TESTO:
            v = self.parere.applica(v, es.manifesto.get("titolo", ""),
                                    es.manifesto.get("descrizione", ""), azione, params)
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
        except (pagina.PaginaVietata, pagina.PaginaNonLetta) as e:
            return {"errore": f"rete: {e}"}
        if not kw["host_ammesso"](gr.host_di(r.get("url") or url)):
            return {"errore": "rete: reindirizzato verso un host non ammesso"}
        return {"risultato": {"stato": 200, "tipo": r.get("tipo"),
                              "testo": str(r.get("testo_grezzo") or "")[:MAX_RETE_TESTO]}}


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
