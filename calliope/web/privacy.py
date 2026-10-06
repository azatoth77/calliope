"""
Le domande che escono di casa: mai dati personali (03/10/2026).

La domanda per il motore di ricerca la compone il modello della voce (o l'agente), e la
descrizione del tool gli dice di non metterci nomi né dati personali. Questo filtro è la
rete sotto: un vincolo di sicurezza sul testo che esce (principio 10, «vincolo di sicurezza o
di permesso»), con un effetto reversibile (la domanda resta, senza quel pezzo). Toglie:

- i nomi delle persone registrate (speakers.json) e degli intestatari dell'archivio, solo
  con l'iniziale maiuscola e come parola intera: «Bianca» sì, «bianca» (il colore) no. I nomi
  provvisori del primo avvio («Primo», «Prima») no: sono anche parole comuni;
- le stringhe private di questa installazione: `web_dati_privati` (indirizzo di casa,
  cognome di famiglia…) e i dati dell'emittente delle fatture (denominazione, indirizzo,
  partita IVA, IBAN, email, telefono);
- per forma: codici fiscali, IBAN, email, numeri di telefono e altre sequenze lunghe di
  cifre (carte, partite IVA, numeri di conto). Le date («3/10/2026») e gli anni restano.

Restituisce la domanda ripulita e i **tipi** di dato tolti (mai i dati): vanno nel registro dei
turni come regola `web_dati_tolti`. Se non resta niente da cercare, la ricerca non parte.
"""

import re

_CF = re.compile(r"\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z]"
                 r"[0-9LMNPQRSTUV]{3}[A-Z]\b", re.I)
# Maiuscolo, come lo scrive il modello: con re.I «ab12 la partita di oggi» sembrava un IBAN
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
# Date e orari restano: si tolgono prima di contare le cifre
_DATA = re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b|\b\d{1,2}[:.]\d{2}\b")
# Telefoni e altre sequenze lunghe: almeno 7 cifre, con spazi, punti, trattini o «+» in mezzo
_CIFRE = re.compile(r"(?<![\w])\+?\d(?:[\s./-]?\d){6,}(?![\w])")
# Nomi provvisori del primo avvio (speaker_id.py): sono anche parole comuni
_NOMI_COMUNI = {"primo", "prima"}
# Dati dell'emittente delle fatture (fatture_emittente) che identificano la casa o chi ci vive
_CAMPI_EMITTENTE = ("denominazione", "nome", "cognome", "indirizzo", "partita_iva",
                    "codice_fiscale", "iban", "email", "telefono", "pec")


def _spazi(t: str) -> str:
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    return t.strip(" ,;:-")


class Ripulitore:
    """Toglie i dati personali da una domanda per il motore di ricerca.

    `nomi` e `privati` possono essere funzioni (si rileggono a ogni domanda: una persona
    registrata a voce conta subito) o elenchi."""

    def __init__(self, nomi=(), privati=()):
        self._nomi = nomi
        self._privati = privati

    @staticmethod
    def _valori(fonte) -> list[str]:
        try:
            v = fonte() if callable(fonte) else fonte
        except Exception:  # noqa: BLE001 — il filtro non deve mai rompersi
            return []
        return [str(x).strip() for x in (v or ()) if str(x or "").strip()]

    def pulisci(self, testo: str) -> tuple[str, list[str]]:
        t = str(testo or "")
        tolti: list[str] = []

        def via(pattern, tipo, flags=0, sostituto=" "):
            nonlocal t
            nuovo = re.sub(pattern, sostituto, t, flags=flags)
            if nuovo != t:
                t = nuovo
                if tipo not in tolti:
                    tolti.append(tipo)

        # Prima le forme intere (un'email contiene un cognome), poi le stringhe private (un
        # indirizzo con il numero civico), poi i numeri lunghi e i nomi
        via(_EMAIL, "email")
        via(_IBAN, "iban")
        via(_CF, "codice_fiscale")
        for s in sorted(self._valori(self._privati), key=len, reverse=True):
            if len(s) >= 3:
                via(r"(?<!\w)" + re.escape(s) + r"(?!\w)", "dato_privato", re.I)
        # Le date restano: si mettono da parte prima di cercare i numeri lunghi
        date: list[str] = []

        def tieni(m):
            date.append(m.group(0))
            return f"\x00{len(date) - 1}\x00"
        t = _DATA.sub(tieni, t)
        via(_CIFRE, "numero")
        t = re.sub(r"\x00(\d+)\x00", lambda m: date[int(m.group(1))], t)
        for nome in sorted(self._valori(self._nomi), key=len, reverse=True):
            for parte in {nome, *nome.split()}:
                if len(parte) < 3 or parte.lower() in _NOMI_COMUNI:
                    continue
                cap = parte[:1].upper() + parte[1:]
                # Solo con l'iniziale maiuscola: «Bianca» è un nome, «bianca» un colore
                via(r"(?<!\w)" + re.escape(cap) + r"(?!\w)", "nome")
        return _spazi(t), tolti


def privati_da_config(cfg) -> list[str]:
    """Le stringhe private di questa installazione: web_dati_privati e i dati
    dell'emittente delle fatture."""
    out = [str(x) for x in (getattr(cfg, "web_dati_privati", None) or ()) if x]
    em = getattr(cfg, "fatture_emittente", None) or {}
    if isinstance(em, dict):
        out += [str(em[k]) for k in _CAMPI_EMITTENTE if em.get(k)]
    return out


def nomi_da(cfg, speakers=None):
    """Funzione che dà i nomi delle persone di casa: registrate (anche a voce, dopo l'avvio)
    e intestatari dell'archivio."""
    def nomi():
        out = []
        if speakers is not None:
            try:
                for n in speakers.known_speakers():
                    out.append(n)
                    p = speakers.get(n)
                    nome = getattr(p, "name", None)
                    if nome:
                        out.append(nome)
            except Exception:  # noqa: BLE001
                pass
        inte = getattr(cfg, "archivio_intestatari", None) or {}
        if isinstance(inte, dict):
            out += [str(k) for k in inte] + [str(v) for v in inte.values()]
        return out
    return nomi
