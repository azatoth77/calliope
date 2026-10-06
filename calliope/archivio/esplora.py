"""
L'esplorazione libera del grafo per l'agente (03/10/2026): le domande complesse sui documenti
di casa delegate al modello grande («quanto ho speso di luce quest'anno rispetto al 2025?»,
«quali garanzie scadono e di cosa?»).

Niente SQL scritto dal modello: sei strumenti chiusi, con argomenti JSON, che il codice
traduce in query parametriche sulle tabelle del grafo (connessione in sola lettura):

  grafo_schema      i tipi di nodo e di relazione, con quanti ce ne sono
  grafo_trova       nodi per nome (persone, enti, beni, luoghi, categorie, documenti)
  grafo_vicini      gli archi di un nodo, con i nodi all'altro capo
  grafo_cammino     un piccolo linguaggio di cammini: partenza + fino a 4 passi
                    {relazione, verso, tipo}, il codice li segue
  grafo_documenti   i documenti filtrati, con i campi principali della scheda
  grafo_somma       le somme degli importi, raggruppate per anno, mese, ente o categoria

Permessi: valgono quelli della voce per chi ha delegato il lavoro (servizio.Archivio.puo_vedere):
un documento che non può vedere non esiste, e non esistono nemmeno gli archi che solo lui
afferma (un referto di un altro non fa comparire il medico né le sue date).
"""

import json

from . import normalizza as nz
from .grafo import TIPI_ARCO, TIPI_NODO, riga_nodo
from .servizio import Chi, periodo


def _fn(name, desc, props=None, required=()):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": list(required)}}}


_TIPI_DOC = ["bolletta", "ricevuta", "contratto", "assicurazione", "garanzia", "referto",
             "identita", "manuale", "altro"]
_FILTRI = {"tipo_doc": {"type": "string", "enum": _TIPI_DOC},
           "categoria": {"type": "string", "description": "luce, gas, acqua, telefono, "
                         "internet, auto, casa, salute…"},
           "ente": {"type": "string", "description": "nome dell'azienda o dell'ente"},
           "persona": {"type": "string", "description": "nome della persona, o «io» per chi "
                       "ha chiesto il lavoro"},
           "dal": {"type": "string", "description": "data AAAA-MM-GG (compresa)"},
           "al": {"type": "string", "description": "data AAAA-MM-GG (esclusa)"},
           "periodo": {"type": "string", "description": "in alternativa a dal/al, come detto: "
                       "«2025», «quest'anno», «settembre 2026»"}}

STRUMENTI = [
    _fn("grafo_schema", "I tipi di nodo e di relazione del grafo dei documenti di casa, con "
        "quanti ce ne sono. Chiamalo per primo."),
    _fn("grafo_trova", "Cerca nodi per nome: persone, enti (aziende), beni (auto, "
        "elettrodomestici, forniture), luoghi, categorie, documenti.",
        {"testo": {"type": "string"}, "tipo": {"type": "string", "enum": list(TIPI_NODO)}},
        ["testo"]),
    _fn("grafo_vicini", "Gli archi di un nodo (in uscita, in entrata o entrambi), con il nodo "
        "all'altro capo: per esempio i documenti emessi da un ente, le scadenze di un documento.",
        {"nodo": {"type": "integer"}, "relazione": {"type": "string", "enum": list(TIPI_ARCO)},
         "verso": {"type": "string", "enum": ["uscenti", "entranti", "entrambi"]}}, ["nodo"]),
    _fn("grafo_cammino", "Segue un cammino nel grafo da uno o più nodi: ogni passo dice la "
        "relazione, il verso (uscenti: da→a; entranti: a→da) e facoltativamente il tipo del "
        "nodo d'arrivo. Esempio: dalla categoria luce, passo {relazione: riguarda, verso: "
        "entranti} dà i documenti della luce; poi {relazione: ha_importo, verso: uscenti} i loro "
        "importi. Al massimo 4 passi.",
        {"partenza": {"type": "array", "items": {"type": "integer"}},
         "passi": {"type": "array", "maxItems": 4, "items": {
             "type": "object", "properties": {
                 "relazione": {"type": "string", "enum": list(TIPI_ARCO)},
                 "verso": {"type": "string", "enum": ["uscenti", "entranti"]},
                 "tipo": {"type": "string", "enum": list(TIPI_NODO)}},
             "required": ["relazione", "verso"]}}},
        ["partenza", "passi"]),
    _fn("grafo_documenti", "I documenti filtrati (tipo, categoria, ente, persona, periodo), con "
        "i campi principali della scheda: data, totale, scadenze, numero, intestatari.",
        dict(_FILTRI, testo={"type": "string", "description": "parole da cercare nel testo"})),
    _fn("grafo_somma", "Somma gli importi dei documenti filtrati (bollette, ricevute, polizze; "
        "i canoni dei contratti no), raggruppati. Le somme le fa il programma: usale così come "
        "sono, non rifare i conti.",
        dict(_FILTRI, raggruppa={"type": "string",
                                 "enum": ["anno", "mese", "ente", "categoria", "nessuno"]})),
]

NOMI = {s["function"]["name"] for s in STRUMENTI}


class Esploratore:
    def __init__(self, archivio, chi: Chi):
        self.a = archivio
        self.chi = chi
        self._vis: set[int] | None = None

    def visibili(self) -> set[int]:
        if self._vis is None:
            self._vis = {d["id"] for d in self.a.documenti(self.chi)}
        return self._vis

    def _arco_ok(self, r) -> bool:
        return r["fonte"] is None or r["fonte"] in self.visibili()

    def _nodo_ok(self, nid: int, tipo: str) -> bool:
        if tipo == "documento":
            return nid in self.visibili()
        rows = self.a.grafo.leggi("SELECT fonte FROM archi WHERE da = ? OR a = ?", (nid, nid))
        return any(self._arco_ok(r) for r in rows)

    def esegui(self, nome: str, args: dict) -> dict:
        args = args if isinstance(args, dict) else {}
        try:
            return getattr(self, nome)(**{k: v for k, v in args.items() if v not in (None, "")})
        except TypeError as e:
            return {"errore": f"argomenti non validi: {e}"}
        except AttributeError:
            return {"errore": f"strumento sconosciuto: {nome}"}

    # ── strumenti ──
    def grafo_schema(self) -> dict:
        g = self.a.grafo
        conta = {}
        for r in g.leggi("SELECT id, tipo FROM nodi"):
            if self._nodo_ok(r["id"], r["tipo"]):
                conta[r["tipo"]] = conta.get(r["tipo"], 0) + 1
        return {"nodi": {k: {"descrizione": v, "quanti": conta.get(k, 0)}
                         for k, v in TIPI_NODO.items()},
                "relazioni": {k: {"da": sorted(d), "a": sorted(a), "descrizione": desc}
                              for k, (d, a, desc) in TIPI_ARCO.items()}}

    def grafo_trova(self, testo: str, tipo: str | None = None) -> dict:
        parole = set(nz.piatto(testo).split())
        if not parole:
            return {"nodi": []}
        out = []
        sql = "SELECT * FROM nodi" + (" WHERE tipo = ?" if tipo else "")
        for r in self.a.grafo.leggi(sql, (tipo,) if tipo else ()):
            nome = set(nz.piatto(r["nome"]).split())
            if parole <= nome or (len(parole) == 1 and any(w.startswith(next(iter(parole)))
                                                           for w in nome)):
                if self._nodo_ok(r["id"], r["tipo"]):
                    out.append(riga_nodo(r))
            if len(out) >= 30:
                break
        return {"nodi": out}

    def grafo_vicini(self, nodo: int, relazione: str | None = None,
                     verso: str = "entrambi") -> dict:
        info = self.a.grafo.nodo_info(int(nodo))
        if info is None or not self._nodo_ok(info["id"], info["tipo"]):
            return {"errore": "nodo non trovato"}
        out = []
        for direzione, col, altro in (("uscenti", "da", "a"), ("entranti", "a", "da")):
            if verso not in (direzione, "entrambi"):
                continue
            sql = (f"SELECT r.rel, r.da, r.a, r.fonte, r.attributi AS attr_arco, n.id, n.tipo, "
                   f"n.nome, n.data, n.valore, n.attributi FROM archi r "
                   f"JOIN nodi n ON n.id = r.{altro} WHERE r.{col} = ?")
            params = [int(nodo)]
            if relazione:
                sql += " AND r.rel = ?"
                params.append(relazione)
            for r in self.a.grafo.leggi(sql, tuple(params)):
                if not self._arco_ok(r) or (r["tipo"] == "documento" and
                                            r[altro] not in self.visibili()):
                    continue
                d = {"relazione": r["rel"], "verso": direzione, "nodo": riga_nodo(r)}
                at = json.loads(r["attr_arco"] or "{}")
                if at:
                    d["attributi"] = at
                out.append(d)
                if len(out) >= 60:
                    return {"nodo": info, "archi": out, "troncato": True}
        return {"nodo": info, "archi": out}

    def grafo_cammino(self, partenza, passi) -> dict:
        ids = [int(x) for x in (partenza if isinstance(partenza, list) else [partenza])][:50]
        fronte = {i for i in ids if (n := self.a.grafo.nodo_info(i)) and
                  self._nodo_ok(i, n["tipo"])}
        for p in list(passi or [])[:4]:
            rel, verso, tipo = p.get("relazione"), p.get("verso", "uscenti"), p.get("tipo")
            if rel not in TIPI_ARCO or not fronte:
                return {"errore": f"relazione sconosciuta: {rel}"} if rel not in TIPI_ARCO \
                    else {"nodi": [], "quanti": 0}
            col, altro = ("da", "a") if verso == "uscenti" else ("a", "da")
            nuovi = set()
            lst = list(fronte)
            for i in range(0, len(lst), 500):
                pezzo = lst[i:i + 500]
                for r in self.a.grafo.leggi(
                        f"SELECT r.{altro} AS x, r.fonte, n.tipo FROM archi r JOIN nodi n ON "
                        f"n.id = r.{altro} WHERE r.rel = ? AND r.{col} IN "
                        f"({','.join('?' * len(pezzo))})", (rel, *pezzo)):
                    if not self._arco_ok(r) or (tipo and r["tipo"] != tipo):
                        continue
                    if r["tipo"] == "documento" and r["x"] not in self.visibili():
                        continue
                    nuovi.add(r["x"])
            fronte = nuovi
            if len(fronte) > 2000:
                return {"errore": "troppi nodi: aggiungi un filtro o parti da nodi più precisi"}
        nodi = [self.a.grafo.nodo_info(i) for i in sorted(fronte)[:100]]
        return {"nodi": [n for n in nodi if n], "quanti": len(fronte)}

    def _filtri(self, tipo_doc=None, categoria=None, ente=None, persona=None, dal=None, al=None,
                periodo_detto=None):
        if periodo_detto and not (dal or al):
            dal, al, _ = periodo(periodo_detto)
        persone = self.a.persone_da(persona, self.chi) if persona else None
        return dict(tipo=tipo_doc, dal=nz.data_iso(dal) if dal else None,
                    al=nz.data_iso(al) if al else None, persone=persone,
                    categoria=categoria, ente=ente)

    def grafo_documenti(self, tipo_doc=None, categoria=None, ente=None, persona=None, dal=None,
                        al=None, periodo=None, testo=None) -> dict:
        f = self._filtri(tipo_doc, categoria, ente, persona, dal, al, periodo)
        docs = self.a.documenti(self.chi, **f)
        if testo:
            ok = {d["id"] for d in self.a.cerca(self.chi, testo, tipo_doc, limite=500)["documenti"]}
            docs = [d for d in docs if d["id"] in ok]
        out = []
        for d in docs[:30]:
            s = self.a.scheda(d["id"])
            out.append({"id": d["id"], "nome": d["nome"], "data": d["data"], "totale": d["totale"],
                        "tipo": s.get("tipo"), "categoria": d["attributi"].get("categoria"),
                        "numero": s.get("numero"),
                        "emittente": (s.get("emittente") or {}).get("nome"),
                        "intestatari": [p["nome"] for p in s.get("intestatari") or []],
                        "scadenze": s.get("scadenze") or [],
                        **{k: s[k] for k in ("periodo_dal", "periodo_al", "consumo", "unita",
                                             "prodotto", "data_fine", "ramo", "esame")
                           if s.get(k) is not None}})
        return {"documenti": out, "quanti": len(docs)}

    def grafo_somma(self, tipo_doc=None, categoria=None, ente=None, persona=None, dal=None,
                    al=None, periodo=None, raggruppa="anno") -> dict:
        f = self._filtri(tipo_doc, categoria, ente, persona, dal, al, periodo)
        tipi_somma = [f["tipo"]] if f["tipo"] else ["bolletta", "ricevuta", "assicurazione"]
        docs = []
        for t in tipi_somma:
            docs += self.a.documenti(self.chi, **dict(f, tipo=t))
        con = [d for d in docs if d["totale"] is not None]
        gruppi: dict[str, dict] = {}
        for d in con:
            if raggruppa == "anno":
                k = (d["data"] or "senza data")[:4]
            elif raggruppa == "mese":
                k = (d["data"] or "senza data")[:7]
            elif raggruppa == "categoria":
                k = d["attributi"].get("categoria") or "altro"
            elif raggruppa == "ente":
                s = self.a.scheda(d["id"])
                k = (s.get("emittente") or {}).get("nome") or "sconosciuto"
            else:
                k = "tutto"
            g = gruppi.setdefault(k, {"totale": 0.0, "documenti": 0})
            g["totale"] = round(g["totale"] + d["totale"], 2)
            g["documenti"] += 1
        return {"totale": round(sum(d["totale"] for d in con), 2), "documenti": len(con),
                "senza_importo": len(docs) - len(con),
                "gruppi": dict(sorted(gruppi.items()))}
