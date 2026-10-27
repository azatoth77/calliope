"""
L'aspetto dei satelliti personali (27/10, passo 1c di
docs/ricerche/2026-10-27-telefono-sezioni-e-studio.md, § 2.1 e § 3.1; decisioni 2 e 8 del 27/10).

- **Accento.** Il lilla è l'accento di serie su tutto (telefono, PC, schermi condivisi: è nei CSS).
  In più l'accento è una preferenza della persona, scelta in Io › Aspetto: vale sui suoi
  satelliti personali, mai sugli schermi condivisi. Le scelte sono in `ACCENTI`, controllate per
  il contrasto (prove/prova_aspetto.py): la pagina riceve i colori da qui, mai un colore libero.
  La scelta sta in memoria.db (`aspetto_preferenze`, una riga per persona) e si cancella con i
  dati della persona (conserva.TABELLE_PREFERENZE).
- **Sezioni per età.** Sul satellite personale di un minore: sotto i 13 anni Casa nascosta, a ogni
  età la raccolta Ufficio nascosta. Calcolate a ogni accesso dal profilo del proprietario
  (`minori.eta`); la pagina non decide sull'età. Nascondere non toglie e non aggiunge permessi:
  quelli restano in ToolRegistry.call.
"""

import datetime
import threading

# Ogni accento: il colore e la sua famiglia (le variabili --accento* della pagina). «tenue» è la
# terna RGB dell'accento, per i fondi trasparenti. L'oro è quello di prima del 27/10 (telefono)
ACCENTI = {
    "lilla": {"nome": "Lilla", "accento": "#b9a3e3", "chiaro": "#cdbcf0", "bordo": "#5b4a80",
              "selezione": "#2a2140", "fondo": "#15111f", "su": "#1a1226", "tenue": "185, 163, 227"},
    "oro": {"nome": "Oro", "accento": "#cfa760", "chiaro": "#e2c48a", "bordo": "#5a4a2c",
            "selezione": "#2a2316", "fondo": "#17140d", "su": "#1a1408", "tenue": "207, 167, 96"},
    "rosa": {"nome": "Rosa", "accento": "#e8a6c8", "chiaro": "#f2c4dc", "bordo": "#6e3f58",
             "selezione": "#2e1824", "fondo": "#1c1017", "su": "#2a0f1d", "tenue": "232, 166, 200"},
}
DI_SERIE = "lilla"
# Sezioni e raccolte nascoste sul satellite personale di un minore (§ 3.1, decisione 2)
ETA_CASA = 13


def colori(nome: str | None) -> dict:
    """I colori di un accento (quello di serie se il nome non c'è)."""
    a = ACCENTI.get(nome or "") or ACCENTI[DI_SERIE]
    return {k: v for k, v in a.items() if k != "nome"}


def per_pagina(nome: str | None, personale: bool) -> dict:
    """Ciò che riceve la pagina: l'accento in uso e, su uno schermo personale, le scelte."""
    nome = nome if nome in ACCENTI else DI_SERIE
    out = {"accento": nome, "colori": colori(nome)}
    if personale:
        out["scelte"] = [{"id": k, "nome": v["nome"], "colore": v["accento"]} for k, v in ACCENTI.items()]
    return out


def nascoste(prof, oggi: datetime.date | None = None) -> dict:
    """Le sezioni e le raccolte da non mostrare sul satellite personale di `prof`."""
    from .. import minori
    out = {"sezioni": [], "raccolte": []}
    if prof is None or not minori.e_minore(prof, oggi):
        return out
    out["raccolte"].append("ufficio")
    anni = minori.eta(getattr(prof, "nascita", None), oggi)
    # Senza data di nascita (la fascia scritta a mano) l'età non si sa: Casa nascosta, come
    # per i più piccoli, finché non c'è la data
    if anni is None or anni < ETA_CASA:
        out["sezioni"].append("casa")
    return out


class PreferenzeAspetto:
    """La scelta dell'accento per persona, in memoria.db."""

    def __init__(self, path: str):
        from ..persistenza import apri_db, prepara_schema
        self._lock = threading.Lock()
        self.db = apri_db(path)

        def v1(db):
            db.execute("CREATE TABLE IF NOT EXISTS aspetto_preferenze (persona TEXT PRIMARY KEY, "
                       "accento TEXT NOT NULL, aggiornato TEXT NOT NULL)")
        self.scrivibile = prepara_schema(self.db, "aspetto", [v1])

    def accento(self, persona: str | None) -> str:
        if not persona:
            return DI_SERIE
        with self._lock:
            r = self.db.execute("SELECT accento FROM aspetto_preferenze WHERE persona = ?",
                                (str(persona),)).fetchone()
        return r[0] if r and r[0] in ACCENTI else DI_SERIE

    def salva(self, persona: str, accento: str) -> bool:
        if not persona or accento not in ACCENTI:
            return False
        with self._lock:
            self.db.execute(
                "INSERT INTO aspetto_preferenze (persona, accento, aggiornato) VALUES (?, ?, ?) "
                "ON CONFLICT(persona) DO UPDATE SET accento = excluded.accento, "
                "aggiornato = excluded.aggiornato",
                (str(persona), accento, datetime.date.today().isoformat()))
            self.db.commit()
        return True

    def close(self):
        with self._lock:
            self.db.close()
