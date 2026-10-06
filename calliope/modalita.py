"""
La modalità cambiata a voce, intera e subito (05/10).

Prima la modalità (`modalita: startrek` in configurazione, config.MODALITA) si sceglieva solo
nei file e con un riavvio; a voce c'era solo il tono «computer di bordo», e il 05/10 sulla DGX
«la proviamo la modalità Star Trek» cambiava il tono e diceva «Modalità computer di bordo
attiva.» senza wake word né suoni. Ora `cambia_voce(modalita=…)` (solo chi amministra,
riconosciuto dalla voce nella frase) chiama `Modalita.cambia`, che:

- cambia la configurazione in memoria (config.cambia_modalita: wake word, posizione,
  tolleranza, tono, suoni; le chiavi di calliope.locale.yaml restano) e la salva in
  personalita.json accanto al tono della casa (vale il più recente tra lui e i file);
- avvisa chi tiene una copia di quei valori (`ascoltatori`, registrati da main.py): il
  rilevatore acustico locale, i suoni, il barge-in, il saluto e i satelliti collegati
  (messaggio «modalita»: un satellite senza il modello della parola nuova lo chiede al
  server; uno vecchio la prende alla prossima connessione);
- risponde con quello che è acceso davvero (wake word acustica o testuale, suoni, tono,
  satelliti da riavviare), mai una capacità che non c'è.

Whisper (prompt e hotwords), wake word testuale, uscite, schermi leggono `Config.wake_names`
a ogni uso: cambiano da soli.
"""
from __future__ import annotations

import os
import threading

from .config import MODALITA, TONI, cambia_modalita, nome_modalita, nome_tono

NOMI = {"normale": "normale", "startrek": "Star Trek"}


class Modalita:
    """La modalità di questa Calliope, cambiata a voce. Un oggetto per processo."""

    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.ascoltatori: list = []          # funzioni(cfg) → dict con note per la risposta
        self._lock = threading.Lock()

    @property
    def attuale(self) -> str:
        return nome_modalita(self.cfg.modalita) or "normale"

    def cambia(self, nome, chi: str | None = None) -> dict:
        """Passa alla modalità `nome` adesso. {"ok", "modalita", "gia", "stato", "note"}."""
        from .personalita import salva_modalita, tono_fuori_modalita
        n = nome_modalita(nome)
        if n is None:
            return {"ok": False, "errore": f"modalità «{nome}» sconosciuta",
                    "modalita_disponibili": ["normale", *MODALITA]}
        with self._lock:
            prima = self.attuale
            if n == prima:
                return {"ok": True, "modalita": n, "gia": True, "stato": self.stato()}
            tono_casa = nome_tono(self.cfg.tono) or "normale"
            # Il tono della casa da rimettere alla fine: quello di prima della modalità
            fuori = tono_casa if prima == "normale" else (tono_fuori_modalita(self.cfg)
                                                          or tono_casa)
            cambia_modalita(self.cfg, n)
            if n == "normale":
                self.cfg.tono = fuori
            try:
                salva_modalita(self.cfg, n, fuori, chi)
            except OSError as e:
                self.log(f"[MODALITÀ] Non riesco a salvare personalita.json ({e}): vale fino "
                         f"al riavvio")
            note: dict = {}
            for f in list(self.ascoltatori):
                try:
                    note.update(f(self.cfg) or {})
                except Exception as e:  # noqa: BLE001 — un pezzo che non segue non ferma gli altri
                    self.log(f"[MODALITÀ] {getattr(f, '__name__', f)}: {type(e).__name__}: {e}")
            self.log(f"[MODALITÀ] {NOMI.get(prima, prima)} → {NOMI.get(n, n)}"
                     + (f" (da {chi})" if chi else "") + f": wake word "
                     f"«{self.cfg.wake_names[0]}», tono {self.cfg.tono}, suoni "
                     f"{'accesi' if self.cfg.suoni_ascolto else 'spenti'}")
            return {"ok": True, "modalita": n, "gia": False, "stato": self.stato(note)}

    def stato(self, note: dict | None = None) -> dict:
        """Cosa è acceso davvero: parole, wake word acustica o testuale, suoni, tono."""
        cfg = self.cfg
        note = dict(note or {})
        modelli = list(getattr(cfg, "wake_models", None) or [cfg.wake_model])
        acustica = (bool(cfg.wake_word_enabled) and cfg.wake_mode == "modello"
                    and os.path.isfile(str(cfg.wake_model)))
        out = {"modalita": self.attuale, "parola": cfg.wake_names[0],
               "anche": cfg.wake_names[1:], "solo_inizio": bool(cfg.wake_start_only),
               "wake": ("acustica" if acustica else "testuale"),
               "modelli": [os.path.basename(m) for m in modelli] if acustica else [],
               "suoni": bool(cfg.suoni_ascolto),
               "tono": nome_tono(cfg.tono) or "normale"}
        out.update(note)
        return out


def frase(esito: dict) -> str:
    """La frase pronta per la voce (risposta_finale): dice cosa è acceso e cosa no."""
    if not esito.get("ok"):
        return "Questa modalità non la conosco: ho la modalità normale e la modalità Star Trek."
    st = esito.get("stato") or {}
    n = esito.get("modalita")
    parola, anche = st.get("parola", "Calliope"), st.get("anche") or []
    if n == "normale":
        testa = ("Sono già nella modalità normale." if esito.get("gia") else
                 "Modalità normale: torno a rispondere a «" + parola + "», senza i suoni di "
                 "ascolto.")
        parti = [testa]
    else:
        nome = NOMI.get(n, n)
        if esito.get("gia"):
            parti = [f"Sono già nella modalità {nome}."]
        else:
            chiama = f"chiamami «{parola}»" + (f" o «{anche[0]}»" if anche else "")
            if st.get("solo_inizio"):
                chiama += " all'inizio della frase"
            parti = [f"Modalità {nome} attiva: {chiama}"
                     + (", con i suoni di inizio e fine ascolto" if st.get("suoni") else "")
                     + (f" e il tono {TONI[st['tono']]['detto']}" if st.get("tono") in TONI
                        and st.get("tono") != "normale" else "") + "."]
    if n != "normale" or not esito.get("gia"):
        if st.get("wake") == "testuale" and n != "normale":
            parti.append(f"«{parola}» la riconosco solo dalla trascrizione, perché qui manca "
                         "il suo modello acustico.")
        mancanti = st.get("satelliti_senza_modello") or []
        if mancanti:
            parti.append(f"Sul satellite {_elenco(mancanti)} manca il modello di «{parola}»: lo sto "
                         f"mandando, e intanto lì vale «{anche[0] if anche else 'Calliope'}».")
        vecchi = st.get("satelliti_da_riavviare") or []
        if vecchi:
            parti.append(("Il satellite " if len(vecchi) == 1 else "I satelliti ")
                         + _elenco(vecchi) + (" ha" if len(vecchi) == 1 else " hanno")
                         + " una versione vecchia: lì la modalità nuova arriva dopo un "
                         "riavvio.")
    return " ".join(parti)


def _elenco(nomi) -> str:
    nomi = [f"«{x}»" for x in nomi]
    return nomi[0] if len(nomi) == 1 else ", ".join(nomi[:-1]) + " e " + nomi[-1]
