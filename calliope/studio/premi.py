"""
I premi dello Studio (31/10, issue #296, epic #251, decisione 0035 punto 45; analisi nel commento
della #296): la serie di giorni di studio, le stelle e i duelli fra persone di casa, con la regola
per i minori. Decisione di chi amministra del 28/10: «il minimo di gamification sullo studio che è
un rinforzo positivo»; davanti a un dubbio, meno meccaniche e non di più. Le soglie le sceglie chi
sviluppa (30/10) e si cambiano con l'uso: sono tutte qui, in cima.

**Tutto dal codice, dai dati che ci sono.** Niente modello, niente autovalutazioni, niente tempo
passato nell'app né numero di aperture:
- **il giorno di studio** (`studiato`) è un giorno con almeno una pratica vera: una sessione del
  piano misurata fra «Inizia» e «Fatto» di almeno `SERIE_MINUTI` minuti (una sessione aperta e
  chiusa subito non conta), almeno `SERIE_CARTE` carte diverse ripassate da chi studia quando
  erano da ripassare, nell'arco di almeno `CARTE_SECONDI` (la stessa carta ripetuta conta una
  volta, e l'esito, che è un'autovalutazione, non conta), una prova consegnata con almeno metà
  delle risposte date, almeno una giusta o a metà per il codice e durata almeno `PROVA_SECONDI`,
  oppure almeno `SERIE_CASELLE` caselle giuste o a metà di una mappa controllata dal codice;
- **la serie** (`serie`) conta i giorni di studio andando indietro da oggi. Un giorno senza piano
  (nessuna verifica aperta, giorno senza scuola, fuori dagli orari del tutore: il piano lì ha zero
  minuti) non conta e non la ferma; un giorno del piano senza pratica, o saltato con «non ce la
  faccio oggi», usa un giorno di pausa (`studio_serie_pause` ogni 7, di serie 1). Oggi non ancora
  studiato non la ferma. Quando la serie si ferma non si dice e non si mostra: sparisce, e la
  prossima pratica ne comincia un'altra; mai «l'hai persa», mai un conto alla rovescia;
- **le stelle** (`TIPI_STELLA`) sono traguardi di padronanza, ognuno al più una volta per
  verifica (per argomento il primo): un argomento portato all'obiettivo (solo con la padronanza
  mostrata, contando i soli esiti decisi dal codice o dal tutore, mai le autovalutazioni né i
  giudizi del tutore), una verifica finta o un'interrogazione superate (le risposte giuste decise
  dal codice o dal tutore su tutte le domande, almeno l'obiettivo), il ripasso delle carte fatto
  (almeno `RIPASSO_CARTE` carte, ognuna ripassata in almeno `RIPASSO_GIORNI` giorni diversi), il
  piano seguito (alla data della verifica, almeno `PIANO_QUOTA` dei giorni del piano chiusi con
  una sessione misurata, e almeno `PIANO_MIN`). Una stella presa resta;
- **i duelli** sono una partita fra persone di casa sulle domande di una verifica di chi propone,
  sugli schermi: domande uguali, ognuno al suo ritmo, gli esiti decisi dal codice alla consegna,
  i punti di tutti e due alla fine, senza «vinto» né «perso». Non danno stelle, non contano per la
  serie e non scrivono tentativi: non c'è niente da guadagnare imbrogliando. Mai con ospiti o
  conoscenti, mai classifiche; per un minore li accende il tutore.

**La regola per i minori** (la proposta della #296, decisa qui): i premi seguono la padronanza e
la pratica, mai il tempo d'uso; la serie non punisce (pause, giorni senza piano, nessuna perdita
detta); niente avvisi che spingono (nessuna notifica, nessun promemoria: a voce la serie si dice al
più una volta al giorno e solo dentro una risposta a ciò che la persona ha fatto o chiesto); duelli
solo in casa, accesi dal tutore; il tutore vede tutto nella sua vista e spegne serie, stelle e
duelli, tutti o in parte, per ciascun minore. Per un adulto le stesse meccaniche, e gli
interruttori li decide lui. Lo stato d'animo non entra mai.

Permessi come il resto dello Studio (`servizio.permesso`); tutto dentro `self.dati.lock` quando
legge e scrive insieme. Le frasi le scrive il codice: numeri, tipi e nomi dei profili, mai titoli
di argomenti né testo delle pagine o delle domande.
"""

from __future__ import annotations

import datetime
import json
import random

from . import dati as D
from . import padronanza as PD
from . import resoconto as R

# ─────────────────────────── le soglie (iniziali, si cambiano con l'uso) ───────────────────────────
# Un giorno di studio
SERIE_MINUTI = 10
SERIE_CARTE = 5
SERIE_CASELLE = 3
# Revisione della PR #355: le carte contano solo se erano da ripassare quando la persona ha dato
# l'esito (`studio_pratica`), una volta per carta e per giorno, e fra la prima e l'ultima che
# contano devono passare almeno `CARTE_SECONDI` secondi (cinque tocchi di fila non sono un
# ripasso); una prova conta con almeno una risposta «giusto» o «indizio» decisa dal codice e
# almeno `PROVA_SECONDI` secondi fra l'inizio e la consegna; le caselle della mappa solo giuste o
# a metà (tentativi «mappa» del codice, scritti solo da «Controlla» e «Ho finito»)
CARTE_SECONDI = 120
PROVA_SECONDI = 120
ESITI_PRATICA = ("giusto", "indizio")
# La serie: la finestra delle pause e quanto indietro si guarda
PAUSA_FINESTRA = 7
PAUSE_MAX = 3
SERIE_MAX_GIORNI = 400
# Le stelle
FONTI_STELLE = ("codice", "tutore")
RIPASSO_CARTE = 5
RIPASSO_GIORNI = 2
PIANO_QUOTA = 0.8
PIANO_MIN = 3
TIPI_STELLA = ("argomento", "prova_scritta", "prova_orale", "ripasso", "piano")
# I duelli
DUELLO_DOMANDE = 5
DUELLO_MIN = 3
DUELLO_ORE = 24
DUELLI_APERTI_MAX = 3
PROPOSTO, IN_CORSO, FINITO, RIFIUTATO, ANNULLATO, SCADUTO = (
    "proposto", "in_corso", "finito", "rifiutato", "annullato", "scaduto")
APERTI = (PROPOSTO, IN_CORSO)
# Gli interruttori di una persona
CHIAVI = ("serie", "stelle", "duelli")

# Le frasi del codice (mai testo di un dato)
NOMI_STELLA = {"argomento": "argomento all'obiettivo",
               "prova_scritta": "verifica finta superata",
               "prova_orale": "interrogazione simulata superata",
               "ripasso": "ripasso delle carte fatto",
               "piano": "piano seguito"}
DUELLI_SPENTI = "i duelli sono spenti"
DUELLI_NON_PER_TE = "i duelli per te non sono accesi"
DUELLI_NON_PER_LUI = "con questa persona i duelli non sono accesi"
DUELLO_POCHE = (f"per un duello servono almeno {DUELLO_MIN} domande che il codice sa correggere: "
                "scrivile o fai le carte con una risposta breve")
DUELLO_PROVA = ("c'è una prova o una mappa da zero aperta su questa verifica: il duello aspetta "
                "che finisca")
DUELLI_TROPPI = f"al più {DUELLI_APERTI_MAX} duelli aperti per persona"
SOLO_TUTORE = "i premi di un ragazzo li decide chi lo segue"


def _d(x) -> datetime.date:
    if isinstance(x, datetime.datetime):
        return x.date()
    if isinstance(x, datetime.date):
        return x
    return datetime.date.fromisoformat(str(x)[:10])


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def _da(x, vuoto):
    try:
        v = json.loads(x) if x else vuoto
    except (TypeError, ValueError):
        return vuoto
    return v if isinstance(v, type(vuoto)) else vuoto


# ─────────────────────────── funzioni pure ───────────────────────────

def _t(x) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(str(x))
    except (TypeError, ValueError):
        return None


def pratica(sessioni: list[dict], tentativi: list[dict], prove: list[dict], persona: str,
            oggi, carte: list[dict] = ()) -> dict[str, dict]:
    """{giorno: {minuti, carte, caselle, prove}} della pratica di `persona` fino a oggi (i giorni
    dopo oggi, un orologio spostato, non contano):
    - `sessioni`: le sessioni del piano (`resoconto.sessioni`), i minuti misurati di quelle fatte;
    - `carte`: righe di `studio_pratica` (`giorno`, `ora`, `rif`): le carte ripassate quando erano
      da ripassare, una volta per carta e per giorno; se fra la prima e l'ultima di un giorno
      passano meno di `CARTE_SECONDI` il giorno non ne ha nessuna;
    - `tentativi`: righe di `studio_tentativi`; contano solo le caselle della mappa decise dal
      codice, giuste o a metà, registrate dalla persona (`chi`);
    - `prove`: righe di `studio_prove` consegnate o scadute con almeno metà delle risposte date,
      almeno una «giusto» o «indizio» decisa dal codice e `PROVA_SECONDI` fra inizio e fine."""
    oggi = _d(oggi).isoformat()
    out: dict[str, dict] = {}

    def g(giorno):
        return out.setdefault(giorno, {"minuti": 0, "carte": set(), "caselle": 0, "prove": 0})
    for s in sessioni:
        if s.get("stato") == R.FATTO and s.get("minuti") and str(s["giorno"]) <= oggi:
            g(str(s["giorno"]))["minuti"] += int(s["minuti"])
    ore: dict[str, list] = {}
    for c in carte:
        giorno = str(c.get("giorno") or "")
        t = _t(c.get("ora"))
        if not giorno or giorno > oggi or c.get("rif") is None or t is None:
            continue
        g(giorno)["carte"].add(int(c["rif"]))
        ore.setdefault(giorno, []).append(t)
    for giorno, tt in ore.items():
        if (max(tt) - min(tt)).total_seconds() < CARTE_SECONDI:
            out[giorno]["carte"] = set()
    for t in tentativi:
        giorno = str(t.get("giorno") or "")
        if not giorno or giorno > oggi or str(t.get("chi") or "") != str(persona):
            continue
        if (t.get("tipo") == "mappa" and t.get("fonte") == "codice"
                and t.get("esito") in ESITI_PRATICA):
            g(giorno)["caselle"] += 1
    for p in prove:
        fine = str(p.get("fine") or "")[:10]
        if (not fine or fine > oggi or p.get("stato") not in ("consegnata", "scaduta")
                or str(p.get("persona") or "") != str(persona)):
            continue
        rp = _da(p.get("riepilogo"), {})
        if rp.get("poche_risposte") or not rp.get("domande"):
            continue
        voci = [x for x in _da(p.get("voci"), []) if isinstance(x, dict)]
        if not any(x.get("esito") in ESITI_PRATICA and x.get("fonte_esito") == "codice"
                   for x in voci):
            continue
        a, b = _t(p.get("inizio")), _t(p.get("fine"))
        if a is None or b is None or (b - a).total_seconds() < PROVA_SECONDI:
            continue
        g(fine)["prove"] += 1
    return out


def studiato(x: dict | None) -> bool:
    """Un giorno con una pratica vera (le soglie in cima)."""
    if not x:
        return False
    return (x.get("minuti", 0) >= SERIE_MINUTI or len(x.get("carte") or ()) >= SERIE_CARTE
            or x.get("prove", 0) >= 1 or x.get("caselle", 0) >= SERIE_CASELLE)


def serie(giorni_pratica: dict[str, dict], pianificati: set[str], oggi, pause: int = 1) -> dict:
    """La serie a oggi: {giorni, pause (i giorni di pausa usati), oggi (oggi conta già), dal (il
    primo giorno della serie)}. Andando indietro: un giorno studiato conta; oggi non studiato
    aspetta; un giorno del piano senza pratica usa una pausa, se nella sua finestra di
    `PAUSA_FINESTRA` giorni ce n'è ancora una, altrimenti la serie si ferma lì; un giorno senza
    piano non conta e non ferma."""
    oggi_d = _d(oggi)
    pause = max(0, min(PAUSE_MAX, int(pause or 0)))
    conta, usate, dal = 0, [], None
    for i in range(SERIE_MAX_GIORNI):
        d = oggi_d - datetime.timedelta(days=i)
        k = d.isoformat()
        if studiato(giorni_pratica.get(k)):
            conta += 1
            dal = k
        elif i == 0:
            continue
        elif k in pianificati:
            vicine = [u for u in usate if (u - d).days < PAUSA_FINESTRA]
            if len(vicine) >= pause:
                break
            usate.append(d)
    return {"giorni": conta, "pause": [u.isoformat() for u in usate if dal and u.isoformat() > dal],
            "oggi": studiato(giorni_pratica.get(oggi_d.isoformat())), "dal": dal}


def punti_affidabili(voci: list[dict]) -> float:
    """I punti delle risposte decise dal codice o dal tutore (giusto 1, indizio 0,5): quelle
    rivedute dalla persona stessa non contano per le stelle."""
    return sum(PD.ESITI.get(x.get("esito"), 0.0) for x in voci
               if x.get("fonte_esito") in FONTI_STELLE and x.get("esito") in PD.ESITI)


def superata(voci: list[dict], obiettivo: int) -> bool:
    """Una prova superata per la stella: almeno `DUELLO_MIN` domande e i punti affidabili su
    tutte le domande (le vuote e le autovalutate valgono 0) almeno l'obiettivo."""
    if len(voci) < DUELLO_MIN:
        return False
    return 100.0 * punti_affidabili(voci) / len(voci) >= int(obiettivo)


def frase_serie(giorni: int, nome: str | None = None) -> str:
    """«La tua serie è a 4 giorni di studio.» (al tutore: «La serie di Leo è a 4 giorni…»)."""
    n = int(giorni)
    quanti = "1 giorno" if n == 1 else f"{n} giorni"
    chi = "La tua serie" if nome is None else (f"La serie di {nome}" if nome else "La serie")
    return f"{chi} è a {quanti} di studio."


def nome_stella(s: dict) -> str:
    if s.get("tipo") == "argomento" and s.get("numero"):
        return f"l'argomento {s['numero']} all'obiettivo"
    return NOMI_STELLA.get(s.get("tipo"), "un traguardo")


def frase_stelle_nuove(nuove: list[dict]) -> str:
    """«Hai una stella nuova: verifica finta superata.»"""
    if not nuove:
        return ""
    cosa = ", ".join(nome_stella(s) for s in nuove[:3])
    if len(nuove) == 1:
        return f"Hai una stella nuova: {cosa}."
    return f"Hai {len(nuove)} stelle nuove: {cosa}" + (" e altre." if len(nuove) > 3 else ".")


# ─────────────────────────── il mixin di Studio ───────────────────────────

class Premi:
    """Il mixin dei premi di `Studio` (`self.dati`, `self._verifica`, `self._chi_puo`…)."""

    # ── interruttori ──
    def _premi_cfg(self, k: str) -> bool:
        return bool(getattr(self.cfg, f"studio_{k}", k != "duelli"))

    def _pause(self) -> int:
        try:
            return max(0, min(PAUSE_MAX, int(getattr(self.cfg, "studio_serie_pause", 1))))
        except (TypeError, ValueError):
            return 1

    def _riga_premi(self, persona) -> dict:
        try:
            return self.dati.uno("SELECT * FROM studio_premi WHERE persona = ?",
                                 (str(persona),)) or {}
        except Exception:  # noqa: BLE001 — uno schema di prima: i valori di serie
            return {}

    def _e_minore(self, persona) -> bool:
        from .servizio import _categoria
        p = self._profilo(persona)
        return p is not None and _categoria(p) == "minore"

    def impostazioni_premi(self, persona) -> dict:
        """{serie, stelle, duelli} per la persona: l'interruttore dell'installazione **e** il
        suo (NULL = di serie: serie e stelle accese, i duelli accesi per un adulto e spenti per un
        minore finché il tutore non li accende); più `scelte` (i suoi valori) e `di_serie`."""
        r = self._riga_premi(persona)
        minore = self._e_minore(persona)
        di_serie = {"serie": True, "stelle": True, "duelli": not minore}
        scelte = {k: (bool(r[k]) if r.get(k) is not None else di_serie[k]) for k in CHIAVI}
        return {**{k: self._premi_cfg(k) and scelte[k] for k in CHIAVI},
                "scelte": scelte, "di_serie": di_serie, "minore": minore,
                "installazione": {k: self._premi_cfg(k) for k in CHIAVI},
                "cambiati": r.get("cambiati"), "cambiati_da": r.get("cambiati_da")}

    def imposta_premi(self, chi, persona, **valori) -> dict:
        """Accende o spegne serie, stelle e duelli di una persona: per un minore solo un suo
        tutore, per un adulto solo lui. Spegnere i duelli annulla quelli aperti. Le impostazioni."""
        from .servizio import NonPermesso
        self._scrivibile()
        persona = str(persona or getattr(chi, "id", "") or "")
        with self.dati.lock:
            ruolo = self._chi_puo(chi, persona)
            if (self._e_minore(persona) and ruolo != "tutore") or (
                    not self._e_minore(persona) and ruolo != "proprietario"):
                raise NonPermesso(SOLO_TUTORE)
            nuovi = {k: (None if v is None else int(bool(v))) for k, v in valori.items()
                     if k in CHIAVI}
            if not nuovi:
                raise ValueError("niente da cambiare")
            r = self._riga_premi(persona)
            att = {k: r.get(k) for k in CHIAVI}
            att.update(nuovi)
            db = self.dati.db
            try:
                db.execute("INSERT INTO studio_premi (persona, serie, stelle, duelli, cambiati, "
                           "cambiati_da) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(persona) DO UPDATE "
                           "SET serie = excluded.serie, stelle = excluded.stelle, duelli = "
                           "excluded.duelli, cambiati = excluded.cambiati, cambiati_da = "
                           "excluded.cambiati_da",
                           (persona, att["serie"], att["stelle"], att["duelli"],
                            self.adesso().isoformat(timespec="seconds"),
                            getattr(chi, "id", None)))
                if nuovi.get("duelli") == 0:
                    db.execute("UPDATE studio_duelli SET stato = ?, fine = ? WHERE (da = ? OR "
                               "a = ?) AND stato IN (?, ?)",
                               (ANNULLATO, self.adesso().isoformat(timespec="seconds"), persona,
                                persona, *APERTI))
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        # Nel registro solo cosa e chi (per sé o da un tutore), mai nomi
        self._registra("premi cambiati (" + self._chi_registro(chi, persona) + "): "
                       + ", ".join(f"{k} {'sì' if v else 'no' if v is not None else 'di serie'}"
                                   for k, v in nuovi.items()))
        return self.impostazioni_premi(persona)

    def premi_accesi(self) -> bool:
        """I premi arrivano alla persona solo con lo Studio attivo (agli schermi e al modello)."""
        return self.per_schermi()

    # ── la serie ──
    def _sessioni_persona(self, persona) -> tuple[list[dict], set[str]]:
        """Le sessioni del piano di tutte le verifiche della persona e i giorni pianificati fino
        a oggi: con un giorno del piano con minuti, o un evento fatto, mancato o saltato."""
        oggi = self._oggi()
        sess, pianificati = [], set()
        for v in self.dati.tutti("SELECT id FROM studio_verifiche WHERE persona = ?",
                                 (str(persona),)):
            righe = self.dati.tutti("SELECT giorno, fase, pagine, minuti, fatto FROM studio_piano "
                                    "WHERE verifica = ?", (v["id"],))
            for r in righe:
                r["pagine"] = D.da_j(r["pagine"])
                if r["giorno"] <= oggi.isoformat() and int(r["minuti"] or 0) > 0:
                    pianificati.add(r["giorno"])
            passate = [r for r in righe if r["giorno"] < oggi.isoformat() and not r["fatto"]]
            for s in R.sessioni(self._eventi(v["id"]), passate, oggi):
                if s["giorno"] > oggi.isoformat():
                    continue
                sess.append(s)
                if s["stato"] in (R.FATTO, R.MANCATO, R.SALTATO):
                    pianificati.add(s["giorno"])
        return sess, pianificati

    def _serie_di(self, persona) -> dict:
        oggi = self._oggi()
        sess, pianificati = self._sessioni_persona(persona)
        tent = self.dati.tutti("SELECT giorno, tipo, esito, fonte, chi, carta FROM "
                               "studio_tentativi WHERE persona = ? AND tipo = 'mappa'",
                               (str(persona),))
        prove = self.dati.tutti("SELECT persona, stato, inizio, fine, riepilogo, voci FROM "
                                "studio_prove WHERE persona = ?", (str(persona),))
        carte = self.dati.tutti("SELECT giorno, ora, rif FROM studio_pratica WHERE persona = ? "
                                "AND tipo = 'carta'", (str(persona),))
        pr = pratica(sess, tent, prove, persona, oggi, carte)
        return serie(pr, pianificati, oggi, self._pause())

    # ── le stelle ──
    def _stelle_da_dare(self, persona) -> list[tuple[int, str, str]]:
        """Le stelle che i dati di oggi danno (verifica, tipo, chiave), anche quelle già prese."""
        oggi = self._oggi()
        out = []
        for v in self.dati.tutti("SELECT * FROM studio_verifiche WHERE persona = ? AND stato != "
                                 "'bozza'", (str(persona),)):
            ob = int(v["obiettivo"] or 75)
            if self.padronanza_mostrata():
                # Un argomento all'obiettivo coi soli esiti del codice e del tutore (mai le
                # autovalutazioni né i giudizi del tutore, che non sono pratica)
                tent = [t for t in self.dati.tutti(
                    "SELECT id, argomento, giorno, ora, tipo, esito, fonte FROM studio_tentativi "
                    "WHERE verifica = ?", (v["id"],))
                    if t["fonte"] in FONTI_STELLE and t["tipo"] != PD.GIUDIZIO
                    and str(t["giorno"]) <= oggi.isoformat()]
                pad = PD.calcola(tent, oggi)
                for a in self._argomenti_numerati(v["id"]):
                    p = pad.get(a["id"])
                    if p and p["valore"] is not None and p["valore"] >= ob:
                        out.append((v["id"], "argomento", str(a["id"])))
            for modalita, tipo in (("scritta", "prova_scritta"), ("orale", "prova_orale")):
                for p in self.dati.tutti("SELECT voci, fine FROM studio_prove WHERE verifica = ? "
                                         "AND modalita = ? AND stato IN ('consegnata', 'scaduta')",
                                         (v["id"], modalita)):
                    if str(p["fine"] or "")[:10] > oggi.isoformat():
                        continue
                    # Tutte le voci: le vuote e le autovalutate valgono 0
                    voci = [x for x in _da(p["voci"], []) if isinstance(x, dict)]
                    if superata(voci, ob):
                        out.append((v["id"], tipo, ""))
                        break
            # Il ripasso delle carte fatto: ogni carta attiva in almeno due giorni diversi
            carte = [c["id"] for c in self.dati.tutti(
                "SELECT id FROM studio_carte WHERE verifica = ? AND stato = 'attiva'", (v["id"],))]
            if len(carte) >= RIPASSO_CARTE:
                giorni: dict = {}
                for t in self.dati.tutti(
                        "SELECT carta, giorno FROM studio_tentativi WHERE verifica = ? AND tipo = "
                        "'carta' AND chi = ? AND carta IS NOT NULL", (v["id"], str(persona))):
                    if str(t["giorno"]) <= oggi.isoformat():
                        giorni.setdefault(int(t["carta"]), set()).add(str(t["giorno"]))
                if all(len(giorni.get(c, ())) >= RIPASSO_GIORNI for c in carte):
                    out.append((v["id"], "ripasso", ""))
            # Il piano seguito, alla data della verifica (o chiusa)
            if v["stato"] in ("fatta", "archiviata") or _d(v["data"]) <= oggi:
                righe = self.dati.tutti("SELECT giorno, fase, pagine, minuti, fatto FROM "
                                        "studio_piano WHERE verifica = ?", (v["id"],))
                for r in righe:
                    r["pagine"] = D.da_j(r["pagine"])
                passate = [r for r in righe if r["giorno"] < oggi.isoformat() and not r["fatto"]]
                sess = [s for s in R.sessioni(self._eventi(v["id"]), passate, oggi)
                        if s["giorno"] <= oggi.isoformat()]
                chiusi = [s for s in sess if s["stato"] in (R.FATTO, R.MANCATO)]
                buoni = [s for s in sess if s["stato"] == R.FATTO
                         and (s.get("minuti") or 0) >= SERIE_MINUTI]
                if len(buoni) >= PIANO_MIN and len(buoni) >= PIANO_QUOTA * len(chiusi):
                    out.append((v["id"], "piano", ""))
        return out

    def aggiorna_stelle(self, persona) -> list[dict]:
        """Scrive le stelle nuove che i dati danno (una volta: la riga è unica) e le restituisce.
        Niente con lo Studio non attivo, con le stelle spente per la persona o in sola lettura."""
        if not self.premi_accesi() or not self.impostazioni_premi(persona)["stelle"] \
                or not self.dati.scrivibile:
            return []
        nuove = []
        with self.dati.lock:
            adesso = self.adesso()
            db = self.dati.db
            try:
                for vid, tipo, chiave in self._stelle_da_dare(persona):
                    c = db.execute("INSERT OR IGNORE INTO studio_stelle (persona, verifica, tipo, "
                                   "chiave, giorno, ora) VALUES (?, ?, ?, ?, ?, ?)",
                                   (str(persona), vid, tipo, chiave, adesso.date().isoformat(),
                                    adesso.isoformat(timespec="seconds")))
                    if c.rowcount:
                        nuove.append({"verifica": vid, "tipo": tipo, "chiave": chiave})
                db.commit()
            except Exception:
                if db.in_transaction:
                    db.rollback()
                raise
        for s in nuove:
            self._registra(f"stella nuova sulla verifica {s['verifica']}: {s['tipo']}")
        m = self.misure.setdefault("premi", {"stelle": 0, "serie_dette": 0, "duelli": {}})
        m["stelle"] += len(nuove)
        return nuove

    def _stelle(self, persona) -> list[dict]:
        out = []
        numeri: dict = {}
        for s in self.dati.tutti("SELECT s.*, v.materia, v.data FROM studio_stelle s JOIN "
                                 "studio_verifiche v ON v.id = s.verifica WHERE s.persona = ? "
                                 "ORDER BY s.id", (str(persona),)):
            n = None
            if s["tipo"] == "argomento" and str(s["chiave"]).isdecimal():
                if s["verifica"] not in numeri:
                    numeri[s["verifica"]] = {a["id"]: i for i, a in enumerate(self.dati.tutti(
                        "SELECT id FROM studio_argomenti WHERE verifica = ? ORDER BY ordine, id",
                        (s["verifica"],)), 1)}
                n = numeri[s["verifica"]].get(int(s["chiave"]))
            out.append({"id": s["id"], "verifica": s["verifica"], "materia": s["materia"],
                        "data": s["data"], "tipo": s["tipo"], "numero": n, "giorno": s["giorno"],
                        "detta": bool(s["detta"]), "nome": None})
        for s in out:
            s["nome"] = nome_stella(s)
        return out

    # ── per lo schermo, la voce e il tutore ──
    def premi(self, chi, persona=None) -> dict:
        """I premi di una persona (di serie chi chiede; un tutore quelli del suo minore): le
        impostazioni, la serie, le stelle (prima aggiornate) e i duelli. Vuoto (`acceso` falso)
        con lo Studio non attivo."""
        persona = str(persona or getattr(chi, "id", "") or "")
        self._chi_puo(chi, persona)
        imp = self.impostazioni_premi(persona)
        out = {"persona": persona, "acceso": self.premi_accesi(), "impostazioni": imp,
               "serie": None, "stelle": None, "duelli": None}
        if not out["acceso"]:
            return out
        with self.dati.lock:
            if imp["serie"]:
                out["serie"] = self._serie_di(persona)
            if imp["stelle"]:
                self.aggiorna_stelle(persona)
                out["stelle"] = self._stelle(persona)
            if imp["installazione"]["duelli"]:
                out["duelli"] = self._duelli_di(chi, persona)
        return out

    def frase_premi(self, chi) -> str:
        """La frase dei premi dopo una pratica di chi parla (dal tool, dopo «fatto»): la serie al
        più una volta al giorno e solo se oggi conta già, le stelle nuove una volta. "" se non c'è
        niente da dire. Mai al tutore per il minore: è la persona che ha studiato."""
        persona = str(getattr(chi, "id", "") or "")
        if not persona or not self.premi_accesi() or not self.dati.scrivibile:
            return ""
        pezzi = []
        with self.dati.lock:
            imp = self.impostazioni_premi(persona)
            oggi = self._oggi().isoformat()
            if imp["serie"]:
                s = self._serie_di(persona)
                r = self._riga_premi(persona)
                # «<» e non «!=»: con l'orologio tornato indietro non si ripete
                if s["oggi"] and s["giorni"] >= 1 and (r.get("serie_detta") or "") < oggi:
                    pezzi.append(frase_serie(s["giorni"]))
                    self.dati.scrivi(
                        "INSERT INTO studio_premi (persona, serie_detta) VALUES (?, ?) ON "
                        "CONFLICT(persona) DO UPDATE SET serie_detta = excluded.serie_detta",
                        (persona, oggi))
                    self.misure.setdefault("premi", {"stelle": 0, "serie_dette": 0,
                                                     "duelli": {}})["serie_dette"] += 1
            if imp["stelle"]:
                self.aggiorna_stelle(persona)
                nuove = [s for s in self._stelle(persona) if not s["detta"]]
                if nuove:
                    pezzi.append(frase_stelle_nuove(nuove))
                    self.dati.scrivi("UPDATE studio_stelle SET detta = 1 WHERE persona = ? AND "
                                     "detta = 0", (persona,))
        return " ".join(pezzi)

    def frase_premi_letti(self, chi, persona=None) -> str:
        """«Quante stelle ho?», «a che punto è la mia serie?»: la serie e il conto delle stelle,
        sempre (è una domanda). Al tutore alla terza persona col nome del minore."""
        persona = str(persona or getattr(chi, "id", "") or "")
        p = self.premi(chi, persona)
        nome = None if persona == getattr(chi, "id", None) else str(
            getattr(self._profilo(persona), "name", "") or "")
        if not p["acceso"]:
            return ""
        imp = p["impostazioni"]
        pezzi = []
        if imp["serie"]:
            g = (p["serie"] or {}).get("giorni") or 0
            if g:
                pezzi.append(frase_serie(g, nome))
            else:
                pezzi.append("La serie di studio comincia con la prossima sessione." if nome is None
                             else f"Per {nome or 'chi studia'} la serie comincia con la prossima "
                                  "sessione.")
        if imp["stelle"]:
            n = len(p["stelle"] or ())
            chi_ = "Hai" if nome is None else (f"{nome} ha" if nome else "Ha")
            pezzi.append(f"{chi_} {'una stella' if n == 1 else f'{n} stelle'}." if n else
                         ("Le stelle arrivano con i traguardi: un argomento all'obiettivo, una "
                          "verifica finta superata, il ripasso delle carte, il piano seguito."))
        if not pezzi:
            return ("I premi dello Studio per te sono spenti." if nome is None else
                    f"I premi dello Studio per {nome or 'chi studia'} sono spenti.")
        return " ".join(pezzi)

    # ── i duelli ──
    def _duelli_possibili(self, persona) -> bool:
        return self.premi_accesi() and self.impostazioni_premi(persona)["duelli"]

    def persone_per_duello(self, chi) -> list[dict]:
        """Le persone di casa con cui `chi` può fare un duello: profili veri (mai ospiti né
        conoscenti), non lui, coi duelli accesi. Vuoto se per lui sono spenti."""
        from .servizio import _categoria
        if not self._duelli_possibili(getattr(chi, "id", None)):
            return []
        out = []
        reg = self.registry
        for p in (getattr(reg, "users", {}) or {}).values() if reg is not None else ():
            pid = getattr(p, "id", None)
            if not pid or pid == getattr(chi, "id", None):
                continue
            if _categoria(p) in ("ospite", "conoscente"):
                continue
            if self._duelli_possibili(pid):
                out.append({"id": pid, "nome": str(getattr(p, "name", "") or "")})
        out.sort(key=lambda x: x["nome"])
        return out

    def _pool_duello(self, v: dict) -> list[dict]:
        """Le domande di un duello: quelle delle prove che il codice sa correggere (mai le
        aperte: senza chi rivede resterebbero «da rivedere»)."""
        return [d for d in self._pool(v) if d["tipo"] != "aperta"]

    def proponi_duello(self, chi, vid, a) -> int:
        """Un duello sulle domande di una verifica aperta di `chi` (solo la persona della
        verifica), con un'altra persona di casa coi duelli accesi. L'id."""
        from .servizio import NonPermesso, NonTrovata, VerificaChiusa
        self._scrivibile()
        a = str(a or "")
        with self.dati.lock:
            if not self._premi_cfg("duelli") or not self.premi_accesi():
                raise ValueError(DUELLI_SPENTI)
            v = self._verifica(chi, vid)
            if self._chi_puo(chi, v["persona"]) != "proprietario":
                raise NonPermesso("il duello lo propone chi studia")
            if not self._duelli_possibili(v["persona"]):
                raise ValueError(DUELLI_NON_PER_TE)
            if a not in {x["id"] for x in self.persone_per_duello(chi)}:
                # Un ospite, un conoscente, sé stesso, qualcuno coi duelli spenti: lo stesso rifiuto
                raise NonTrovata()
            if v["stato"] != "aperta":
                raise VerificaChiusa()
            if self._prova_aperta(v["id"]) is not None:
                raise ValueError(DUELLO_PROVA)
            for p in (v["persona"], a):
                if self._aperti_di(p) >= DUELLI_APERTI_MAX:
                    raise ValueError(DUELLI_TROPPI)
            pool = self._pool_duello(v)
            if len(pool) < DUELLO_MIN:
                raise ValueError(DUELLO_POCHE)
            rnd = random.Random(random.SystemRandom().randrange(1, 2 ** 31))
            scelte = rnd.sample(pool, min(DUELLO_DOMANDE, len(pool)))
            voci = [self._voce(d, k) for k, d in enumerate(scelte, 1)]
            adesso = self.adesso().replace(microsecond=0)
            did = self.dati.scrivi(
                "INSERT INTO studio_duelli (verifica, da, a, stato, voci, creato, scade) VALUES "
                "(?, ?, ?, ?, ?, ?, ?)",
                (v["id"], str(v["persona"]), a, PROPOSTO, _j(voci), adesso.isoformat(),
                 (adesso + datetime.timedelta(hours=DUELLO_ORE)).isoformat()))
        self._misura_duello("proposti")
        self._registra(f"duello {did} proposto sulla verifica {v['id']} ({len(voci)} domande)")
        return did

    def _misura_duello(self, k: str):
        m = self.misure.setdefault("premi", {"stelle": 0, "serie_dette": 0, "duelli": {}})
        m["duelli"][k] = m["duelli"].get(k, 0) + 1

    def _aperti_di(self, persona) -> int:
        return len([r for r in self.dati.tutti(
            "SELECT id FROM studio_duelli WHERE (da = ? OR a = ?) AND stato IN (?, ?)",
            (str(persona), str(persona), *APERTI))])

    def _duello(self, chi, did) -> dict:
        """Il duello, se `chi` ne è parte (altrimenti lo stesso «non c'è»), dopo averlo chiuso se
        è scaduto o se la sua verifica non è più aperta."""
        from .servizio import NonTrovata
        r = self.dati.uno("SELECT * FROM studio_duelli WHERE id = ?", (int(did),))
        me = str(getattr(chi, "id", "") or "")
        if r is None or me not in (r["da"], r["a"]):
            raise NonTrovata()
        return self._rinfresca_duello(r)

    def _rinfresca_duello(self, r: dict) -> dict:
        if r["stato"] not in APERTI:
            return r
        v = self.dati.uno("SELECT stato FROM studio_verifiche WHERE id = ?", (r["verifica"],))
        adesso = self.adesso()
        if v is None or v["stato"] != "aperta" or not (
                self._duelli_possibili(r["da"]) and self._duelli_possibili(r["a"])):
            self._chiudi_duello(r, ANNULLATO)
        elif adesso > datetime.datetime.fromisoformat(r["scade"]):
            self._chiudi_duello(r, FINITO if (r["consegna_da"] or r["consegna_a"])
                                and r["stato"] == IN_CORSO else SCADUTO)
        else:
            return r
        return self.dati.uno("SELECT * FROM studio_duelli WHERE id = ?", (r["id"],)) or r

    def _chiudi_duello(self, r: dict, stato: str):
        """Chiude un duello aperto una volta sola (dentro il lock): «finito» valuta le risposte
        di chi ha consegnato (il codice, `risposte.valuta`), gli altri stati niente."""
        from . import risposte as RS
        with self.dati.lock:
            att = self.dati.uno("SELECT * FROM studio_duelli WHERE id = ?", (r["id"],))
            if att is None or att["stato"] not in APERTI:
                return
            voci = _da(att["voci"], [])
            campi = {}
            if stato == FINITO:
                for lato in ("da", "a"):
                    risp = _da(att[f"risposte_{lato}"], {})
                    if not att[f"consegna_{lato}"]:
                        continue
                    esiti = {}
                    for x in voci:
                        e, _f = RS.valuta(x, risp.get(str(x["n"])))
                        esiti[str(x["n"])] = e
                    campi[f"risposte_{lato}"] = _j({"risposte": risp, "esiti": esiti})
            sets = ", ".join(f"{k} = ?" for k in campi)
            self.dati.scrivi(
                "UPDATE studio_duelli SET stato = ?, fine = ?" + (", " + sets if sets else "")
                + " WHERE id = ? AND stato IN (?, ?)",
                (stato, self.adesso().isoformat(timespec="seconds"), *campi.values(), att["id"],
                 *APERTI))
        self._misura_duello(stato)
        self._registra(f"duello {r['id']} {stato}")

    def _prova_del_duello(self, r: dict) -> bool:
        """Il duello aspetta, per tutti e due, se la persona della verifica ha una prova aperta
        (le domande sono le stesse delle prove: nessuna strada laterale le mostra prima) o una
        mappa da zero aperta e il duello ha una carta nata dalla mappa (direbbe i concetti dello
        scheletro nascosto, decisione 0035 punto 38)."""
        try:
            if self._prova_aperta(r["verifica"]) is not None:
                return True
            if self._libera_aperta(r["verifica"]):
                ids = [int(x["id"]) for x in _da(r["voci"], []) if x.get("fonte") == "carta"]
                if ids and self.dati.tutti(
                        "SELECT id FROM studio_carte WHERE origine = 'mappa' AND id IN ("
                        + ",".join("?" * len(ids)) + ")", ids):
                    return True
            return False
        except Exception:  # noqa: BLE001 — nel dubbio aspetta
            return True

    def _vista_duello(self, r: dict, chi) -> dict:
        """Il duello per lo schermo di chi ne fa parte. Aperto: le domande e le sue risposte, mai
        le risposte attese né gli esiti; finito: le sue risposte con l'esito e quella attesa, e i
        punti di tutti e due. Con una prova aperta sulla verifica niente domande."""
        from . import risposte as RS
        me = str(getattr(chi, "id", "") or "")
        lato, altro = ("da", "a") if me == r["da"] else ("a", "da")
        voci = _da(r["voci"], [])
        mie = _da(r[f"risposte_{lato}"], {})
        sue = _da(r[f"risposte_{altro}"], {})
        finito = r["stato"] == FINITO
        attesa = self._prova_del_duello(r)
        v = self.dati.uno("SELECT materia, data FROM studio_verifiche WHERE id = ?",
                          (r["verifica"],)) or {}
        out = {"id": r["id"], "stato": r["stato"], "io": lato, "verifica": r["verifica"],
               "materia": v.get("materia"), "data": v.get("data"),
               "con": str(getattr(self._profilo(r[altro]), "name", "") or ""),
               "creato": r["creato"], "scade": r["scade"], "domande": len(voci),
               "consegnato": bool(r[f"consegna_{lato}"]),
               "consegnato_altro": bool(r[f"consegna_{altro}"]),
               "puo_accettare": r["stato"] == PROPOSTO and lato == "a",
               "puo_rispondere": (r["stato"] == IN_CORSO and not r[f"consegna_{lato}"]
                                  and not attesa),
               "in_attesa_prova": attesa and r["stato"] in APERTI, "voci": []}
        if finito:
            punti = {}
            for k, risp in (("io", mie), ("altro", sue)):
                es = (risp.get("esiti") or {}) if isinstance(risp, dict) else {}
                punti[k] = (sum(e == "giusto" for e in es.values()) if es else None)
            out["punti"] = punti
        if attesa and not finito:
            return out
        if attesa and finito:
            out["in_attesa_prova"] = True
            return out
        if r["stato"] in (IN_CORSO, FINITO):
            risposte = (mie.get("risposte") if finito else mie) or {}
            esiti = (mie.get("esiti") or {}) if finito else {}
            for x in voci:
                y = {"n": x["n"], "tipo": x["tipo"], "testo": x["testo"],
                     "opzioni": list(x.get("opzioni") or ()),
                     "risposta": risposte.get(str(x["n"]))}
                if finito:
                    y.update(esito=esiti.get(str(x["n"])), attesa=RS.attesa_detta(x))
                out["voci"].append(y)
        return out

    def vista_duello(self, chi, did) -> dict:
        with self.dati.lock:
            return self._vista_duello(self._duello(chi, did), chi)

    def _duelli_di(self, chi, persona) -> list[dict]:
        """I duelli di una persona, dal più recente (al più 10): per lei la vista intera senza
        testi (i testi li dà `vista_duello`), per il tutore solo con chi, stato e punti."""
        out = []
        for r in self.dati.tutti("SELECT * FROM studio_duelli WHERE da = ? OR a = ? ORDER BY id "
                                 "DESC LIMIT 10", (str(persona), str(persona))):
            r = self._rinfresca_duello(r)
            chi_vede = chi if getattr(chi, "id", None) == persona else self._profilo(persona)
            if chi_vede is None:
                continue
            x = self._vista_duello(r, chi_vede)
            x.pop("voci", None)
            if getattr(chi, "id", None) != persona:
                for k in ("puo_accettare", "puo_rispondere"):
                    x[k] = False
            out.append(x)
        return out

    def accetta_duello(self, chi, did, si: bool = True) -> dict:
        """Accetta (o rifiuta) un duello proposto: solo chi lo riceve."""
        from .servizio import NonTrovata
        self._scrivibile()
        with self.dati.lock:
            r = self._duello(chi, did)
            if r["a"] != getattr(chi, "id", None) or r["stato"] != PROPOSTO:
                raise NonTrovata()
            if si and self._prova_del_duello(r):
                raise ValueError(DUELLO_PROVA)
            self.dati.scrivi("UPDATE studio_duelli SET stato = ? WHERE id = ? AND stato = ?",
                             (IN_CORSO if si else RIFIUTATO, r["id"], PROPOSTO))
            if not si:
                self.dati.scrivi("UPDATE studio_duelli SET fine = ? WHERE id = ?",
                                 (self.adesso().isoformat(timespec="seconds"), r["id"]))
            self._misura_duello("accettati" if si else RIFIUTATO)
            self._registra(f"duello {r['id']} {'accettato' if si else 'rifiutato'}")
            return self._vista_duello(self._duello(chi, did), chi)

    def annulla_duello(self, chi, did) -> dict:
        """Chi ne fa parte lo annulla finché è aperto."""
        self._scrivibile()
        with self.dati.lock:
            r = self._duello(chi, did)
            if r["stato"] in APERTI:
                self._chiudi_duello(r, ANNULLATO)
            return self._vista_duello(self._duello(chi, did), chi)

    def rispondi_duello(self, chi, did, n: int, risposta) -> dict:
        """Una risposta di chi fa il duello, finché non consegna."""
        from . import risposte as RS
        self._scrivibile()
        with self.dati.lock:
            r = self._duello(chi, did)
            lato = "da" if getattr(chi, "id", None) == r["da"] else "a"
            if r["stato"] != IN_CORSO or r[f"consegna_{lato}"]:
                raise ValueError("il duello è chiuso")
            if self._prova_del_duello(r):
                raise ValueError(DUELLO_PROVA)
            voci = _da(r["voci"], [])
            if not any(x["n"] == int(n) for x in voci):
                raise ValueError("domanda sconosciuta")
            risp = _da(r[f"risposte_{lato}"], {})
            risp[str(int(n))] = RS.riga(risposta, RS.RISPOSTA_MAX) or None
            self.dati.scrivi(f"UPDATE studio_duelli SET risposte_{lato} = ? WHERE id = ? AND "
                             f"stato = ? AND consegna_{lato} IS NULL",
                             (_j(risp), r["id"], IN_CORSO))
            return self._vista_duello(self._duello(chi, did), chi)

    def consegna_duello(self, chi, did) -> dict:
        """«Consegna»: le risposte non cambiano più; quando hanno consegnato tutti e due il
        codice corregge e il duello è finito. Un secondo «consegna» non cambia niente."""
        self._scrivibile()
        with self.dati.lock:
            r = self._duello(chi, did)
            lato = "da" if getattr(chi, "id", None) == r["da"] else "a"
            if r["stato"] == IN_CORSO and not r[f"consegna_{lato}"]:
                if self._prova_del_duello(r):
                    raise ValueError(DUELLO_PROVA)
                self.dati.scrivi(f"UPDATE studio_duelli SET consegna_{lato} = ? WHERE id = ? AND "
                                 f"stato = ? AND consegna_{lato} IS NULL",
                                 (self.adesso().isoformat(timespec="seconds"), r["id"], IN_CORSO))
                r = self._duello(chi, did)
                if r["consegna_da"] and r["consegna_a"]:
                    self._chiudi_duello(r, FINITO)
            return self._vista_duello(self._duello(chi, did), chi)
