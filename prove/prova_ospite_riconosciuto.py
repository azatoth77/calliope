"""
Prova a secco: da ospite a voce riconosciuta sullo stesso satellite (22/10/2026, issue #171).

Caso vero del 18/10 (qui con nomi di fantasia: Carlo amministra, Luca è il minore): dal telefono
in auto le prime due frasi di chi amministra non sono riconosciute (ospite); dalla terza la voce
lo riconosce, ma il modello continua a dirgli «il sistema dice che sei un ospite». I dati del
turno della terza dicevano solo «persona: Carlo, riconosciuta dalla voce», senza il cambio, e con
la stanza nei dati del turno le risposte date all'ospite entravano nella conversazione di Carlo
come «Calliope: …», senza dire a chi erano rivolte.

- Con le conversazioni per persona (calliope/corsie.py, il flusso vero dei satelliti): due frasi
  da ospite nella conversazione anonima del satellite, poi Carlo riconosciuto dalla voce nella
  sua conversazione → i dati del turno della terza dicono il cambio (regola
  `voce_ora_riconosciuta`); la quarta no, e nemmeno un'altra alternanza ospite → Carlo (una volta
  per conversazione). Le frasi da ospite restano nella conversazione anonima.
- Con la stanza accesa (`stanza_contesto`, `stanza_contesto_in_storia`: la causa del caso vero):
  le risposte all'ospite arrivano come «Calliope → voce non riconosciuta: …» e restano così al
  turno dopo (nella storia, in sola aggiunta, uguali byte per byte); la risposta a Carlo resta
  «Calliope: …»; il cambio è detto al terzo turno.
- Revisione della PR #221: nella conversazione anonima condivisa in compagnia nessuna riga (anche
  alternando); solo con la voce (non zona grigia, profilo più protetto, schermo, estensione); la
  corsia (un Brain per satellite) e non il luogo del satellite attivo; al più `VOCE_ORA_MAX_S`
  anche con `storia_inattiva_s: 0`.
- Contrari: Carlo riconosciuto dall'inizio (nessuna riga in più); la frase da ospite oltre
  `storia_inattiva_s`; un altro luogo; un conoscente dopo l'ospite e Carlo dopo il conoscente; un
  ospite dopo Carlo (il verso inverso non ha la riga); l'etichetta senza `per`, per un conoscente
  e per la zona grigia; interruttore spento.

Su main (950b877) falliscono il cambio con le corsie, il cambio e le risposte marcate con la
stanza, le corsie contro il luogo; con un'eccezione sui segni che main non ha.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope import corsie
from calliope.brain import Brain
from calliope.config import Config
from calliope.conversazione import Conversazione

errori = 0
CAMBIO = "Ora la voce è riconosciuta: parla Carlo."


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""),
          flush=True)


class Backend:
    def __init__(self):
        self.visti = []

    def stream(self, messages, tools):
        self.visti.append([dict(m) for m in messages])
        yield ("text", "Va bene.")


class Prof:
    def __init__(self, pid, name):
        self.id, self.name = pid, name


class Voci:
    """Carlo amministra; Luca è il minore del profilo più protetto (prova_solo_voce)."""
    def get(self, n):
        return {"Carlo": Prof("carlo-id", "Carlo"), "Luca": Prof("luca-id", "Luca")}.get(n)


class Chi:
    """Lo stato di chi parla (speaker_id.SpeakerContext), quanto basta a Brain."""
    current_speaker = None
    current_level = "ospite"
    identified_by = None
    compagnia, compagnia_sconosciute = False, False
    conoscente = None


def brain_finto(chiave="ospite:sat:tel", cfg=None):
    from calliope.tools.builtin import build_registry
    cfg = cfg or Config()
    b = Brain.__new__(Brain)
    b.cfg, b.tools, b.history = cfg, build_registry(), []
    b.conv = Conversazione(chiave)
    chi = Chi()
    b.tool_ctx = type("T", (), {"speaker_ctx": chi, "speakers": Voci()})()
    b.backend = Backend()
    return b, chi


def dati(b) -> str:
    """I messaggi di sistema dell'ultima richiesta al modello dopo il prompt (i dati)."""
    return " ".join(m.get("content") or "" for m in b.backend.visti[-1][1:]
                    if m.get("role") == "system")


def ospite(chi):
    chi.current_speaker, chi.current_level, chi.identified_by = None, "ospite", None
    chi.conoscente = None


def carlo(chi, how="voce"):
    chi.current_speaker, chi.current_level, chi.identified_by = "Carlo", "amministra", how
    chi.conoscente = None


def di(b, testo, chi):
    return "".join(b.stream_reply(testo, chi.current_level))


def con_corsie(b=None, chi=None, sat="tel"):
    """Il flusso vero dei satelliti: una conversazione per persona, una anonima per satellite."""
    if b is None:
        b, chi = brain_finto()
    reg = corsie.RegistroConversazioni(b.cfg)
    tel = corsie.Corsia(f"sat:{sat}", satellite_id=sat, nome="telefono", registro=reg)

    def turno(testo):
        nome = chi.current_speaker
        tel.turno(b, nome, chi.identified_by, True, testo,
                  persona_id="carlo-id" if nome == "Carlo" else None)
        return di(b, testo, chi)
    return b, chi, tel, turno


def prova_corsie():
    b, chi, tel, turno = con_corsie()
    ospite(chi)
    turno("Che tempo fa domani a Lucca?")
    anonima = b.conv
    turno("Puoi aggiungere il latte alla lista della spesa?")
    verifica("due frasi da ospite: dati del turno da ospite, senza il cambio",
             "persona: un ospite" in dati(b) and "Ora la voce è riconosciuta" not in dati(b))
    carlo(chi)
    turno("Aggiungi il latte alla lista della spesa.")
    d3 = dati(b)
    verifica("terza frase, Carlo riconosciuto: i dati del turno dicono il cambio",
             CAMBIO in d3 and "le frasi di prima" in d3.lower()
             and "persona: Carlo, riconosciuta dalla voce" in d3
             and "voce_ora_riconosciuta" in b.last_rules, d3[-400:])
    verifica("…nella conversazione di Carlo, senza le frasi da ospite",
             b.conv is not anonima and b.conv.chiave == "persona:carlo-id"
             and [m["content"] for m in b.history if m["role"] == "user"]
             == ["Aggiungi il latte alla lista della spesa."]
             and len([m for m in anonima.history if m["role"] == "user"]) == 2,
             b.conv.chiave)
    verifica("…la riga sta nei dati del turno, non nella storia",
             all(CAMBIO not in (m.get("content") or "") for m in b.history))
    turno("E anche il pane.")
    verifica("quarta frase, ancora Carlo: la riga non si ripete",
             CAMBIO not in dati(b) and "voce_ora_riconosciuta" not in b.last_rules,
             dati(b)[-300:])
    # Contrario: Carlo riconosciuto dall'inizio
    b, chi, tel, turno = con_corsie()
    carlo(chi)
    for testo in ("Che tempo fa domani?", "Aggiungi il latte.", "E anche il pane."):
        turno(testo)
        verifica(f"contrario: Carlo riconosciuto dall'inizio, «{testo}» → nessuna riga",
                 "Ora la voce è riconosciuta" not in dati(b)
                 and "voce_ora_riconosciuta" not in b.last_rules)
    # Contrario: l'ospite dopo Carlo (il verso inverso non ha la riga)
    ospite(chi)
    turno("Chi sei?")
    verifica("contrario: un ospite dopo Carlo → solo «persona: un ospite»",
             "persona: un ospite" in dati(b) and "riconosciuta" not in dati(b).split(
                 "Se ti chiedono l'ora")[0], dati(b)[:300])


def prova_alternanza_corsie():
    """Al più una volta per conversazione: ospite, Carlo, ospite, Carlo sullo stesso satellite."""
    b, chi, tel, turno = con_corsie()
    visti = []
    for i, testo in enumerate(("Che tempo fa?", "Aggiungi il latte.", "Chi sei?", "E il pane.")):
        (carlo if i % 2 else ospite)(chi)
        turno(testo)
        visti.append(CAMBIO in dati(b))
    verifica("ospite, Carlo, ospite, Carlo: la riga una volta sola nella conversazione di Carlo",
             visti == [False, True, False, False], str(visti))


def prova_condivisa():
    """La conversazione anonima condivisa in compagnia (13/10, passo 0 della decisione 0029): la
    frase «ospite» è di una delle persone presenti; niente riga, anche alternando (revisione
    della PR #221, P1)."""
    b, chi = brain_finto()
    chi.compagnia = True
    for n in range(3):
        ospite(chi)
        di(b, f"Ci fermiamo a fare benzina? ({n})", chi)
        carlo(chi, "voce")
        di(b, f"Sì, alla prossima. ({n})", chi)
        verifica(f"in compagnia, conversazione condivisa, alternanza {n + 1}: niente riga",
                 CAMBIO not in dati(b) and "voce_ora_riconosciuta" not in b.last_rules
                 and "compagnia_anonima_continua" in b.last_rules, dati(b)[-300:])
    verifica("…le frasi di prima marcate come di una voce non riconosciuta (nota del gruppo)",
             "dalla più vecchia: voce non riconosciuta, Carlo" in dati(b), dati(b)[-400:])


def prova_solo_voce():
    """Solo con la voce (revisione della PR #221, P2): il nome scelto dal codice per prudenza o
    da uno schermo non è «la voce riconosciuta»."""
    for how, nome, caso in (("conversazione", "Carlo", "zona grigia o continuità"),
                            ("conversazione", "Luca", "profilo più protetto (minore)"),
                            ("schermo", "Carlo", "scritto da uno schermo"),
                            ("estensione", "Carlo", "un'estensione")):
        b, chi = brain_finto()
        ospite(chi)
        di(b, "Che tempo fa?", chi)
        chi.current_speaker, chi.current_level, chi.identified_by = nome, "familiare", how
        di(b, "Aggiungi il latte.", chi)
        verifica(f"contrario: {caso} (identified_by «{how}») → nessuna riga",
                 "Ora la voce è riconosciuta" not in dati(b)
                 and "voce_ora_riconosciuta" not in b.last_rules, dati(b)[:200])
    b, chi = brain_finto()
    ospite(chi)
    di(b, "Che tempo fa?", chi)
    carlo(chi, None)
    di(b, "Aggiungi il latte.", chi)
    verifica("…con identified_by None (la voce, come in _turn_context) la riga c'è",
             CAMBIO in dati(b))


def prova_stanza():
    """La causa del caso vero: con la stanza nei dati del turno, in sola aggiunta nella storia, le
    risposte all'ospite entravano nella conversazione di Carlo come «Calliope: …»."""
    import prova_stanza_storia as PS
    from calliope.stanza import contesto as ctx_mod
    cfg = PS.cfg_base(stanza_contesto_in_storia=True)
    st = PS.nuova_stanza(cfg, sat=1, nome="auto")
    b, chi = brain_finto(cfg=cfg)
    b.tool_ctx = type("T", (), {"speaker_ctx": chi, "speakers": PS.Voci(), "stanza": st})()
    reg = corsie.RegistroConversazioni(cfg)
    tel = corsie.Corsia("sat:1", satellite_id=1, nome="telefono", registro=reg)
    t0 = time.time() - 120
    risposte = ["Il sistema dice che sei un ospite.",
                "Per aggiornare le impostazioni chiedi a chi gestisce la casa."]

    def turno(testo, inizio, risposta=None):
        nome = chi.current_speaker
        who = ({"chi": "persona:carlo-id", "persona": "carlo-id", "nome": "Carlo",
                "sicurezza": "voce"} if nome else {"chi": "ignoto", "sicurezza": "nessuna"})
        seq = st.turno_testo(1, None, testo, who, inizio=inizio, fine=inizio + 2)
        tel.turno(b, nome, chi.identified_by, True, testo,
                  persona_id="carlo-id" if nome else None)
        b.stanza_turno = ctx_mod.costruisci(st, 1, cfg, inizio, seq_turno=seq)
        di(b, testo, chi)
        if risposta:
            # Come Ciclo._stanza_esito: a chi rispondeva
            st.detto(1, risposta, inizio=inizio + 3, fine=inizio + 6,
                     per={"persona": "carlo-id" if nome else None,
                          "sicurezza": "voce" if nome else "nessuna"})

    def richiesta() -> str:
        return "\n".join(str(m.get("content") or "") for m in b.backend.visti[-1])
    ospite(chi)
    turno("Aggiungi il latte alla lista.", t0, risposte[0])
    turno("Perché no?", t0 + 20, risposte[1])
    carlo(chi)
    turno("Aggiungi il latte alla lista della spesa.", t0 + 40, "Fatto, ho aggiunto il latte.")
    r3 = richiesta()
    verifica("stanza: davanti al modello le risposte di prima sono date all'ospite",
             f"Calliope → voce non riconosciuta: {risposte[0]}" in r3
             and f"Calliope → voce non riconosciuta: {risposte[1]}" in r3
             and "voce non riconosciuta → Calliope: Perché no?" in r3, r3[-1500:])
    verifica("stanza: …e il cambio è detto al terzo turno", CAMBIO in dati(b), dati(b)[-300:])
    turno("E anche il pane.", t0 + 60)
    r4 = richiesta()
    verifica("stanza: al quarto turno le risposte all'ospite restano marcate (nella storia), il "
             "cambio non si ripete, la risposta a Carlo resta «Calliope: …»",
             f"Calliope → voce non riconosciuta: {risposte[0]}" in r4 and CAMBIO not in dati(b)
             and "Calliope: Fatto, ho aggiunto il latte." in r4, r4[-1500:])
    pezzi = [m.get("content") for m in b.backend.visti[-2]
             if "fonte: stanza" in str(m.get("content"))]
    verifica("stanza: i pezzi del terzo turno uguali byte per byte al quarto (cache)",
             bool(pezzi) and all(p in [m.get("content") for m in b.backend.visti[-1]]
                                 for p in pezzi))
    # Contrari dell'etichetta: senza `per` (righe di prima del 22/10), conoscente, zona grigia
    verifica("contrario: una riga di Calliope senza «per», a un conoscente o alla zona grigia "
             "resta «Calliope»",
             ctx_mod.etichetta({"chi": "calliope"}) == "Calliope"
             and ctx_mod.etichetta({"chi": "calliope", "per": {
                 "persona": None, "sicurezza": "nessuna", "conoscente": "k1"}}) == "Calliope"
             and ctx_mod.etichetta({"chi": "calliope", "per": {
                 "persona": "carlo-id", "sicurezza": "grigia"}}) == "Calliope")
    st.detto(1, "Ciao Gino.", per={"persona": None, "sicurezza": "nessuna", "conoscente": "k1"})
    ultima = st.registro(1).righe()[-1]
    verifica("contrario: la risposta a un conoscente resta «Calliope» (il segno arriva al "
             "registro)", (ultima.get("per") or {}).get("conoscente") == "k1"
             and ctx_mod.etichetta(ultima) == "Calliope", str(ultima.get("per")))


def prova_esito_ciclo():
    """Il giro vero di `Ciclo._stanza_esito` (seconda revisione della PR #221, Q2): la risposta a
    un conoscente porta `per.conoscente` e resta «Calliope»; quella a un ospite è «Calliope →
    voce non riconosciuta»."""
    import types
    from types import SimpleNamespace

    import prova_stanza_storia as PS
    from calliope.ciclo import Ciclo
    from calliope.stanza import contesto as ctx_mod
    cfg = PS.cfg_base(stanza_contesto_in_storia=True)
    st = PS.nuova_stanza(cfg, sat=1, nome="auto")
    f = SimpleNamespace()
    f.s = SimpleNamespace(stanza=st, registry=PS.Voci(), cfg=cfg)
    f.rec = {"voce": {"nome": None, "modo": None}}
    f.speaker_ctx = SimpleNamespace(sfida=None, conoscente=None)
    f.listener = SimpleNamespace(started_at=time.monotonic() - 2.0,
                                 ended_at=time.monotonic() - 0.5)
    f._stanza_dove = lambda: (1, None)
    f.brain = SimpleNamespace(rules_fired=lambda: [], redact=lambda x: x)
    f._ripulisci_per_registro = types.MethodType(Ciclo._ripulisci_per_registro, f)

    def esito(testo, detto):
        t = SimpleNamespace(text=testo, scritto=None, said=[detto], non_rivolta=False,
                            stanza_seq=None, stanza_esito_fatto=False)
        Ciclo._stanza_turno(f, t)
        Ciclo._stanza_esito(f, t, {**f.rec, "esito": "risposta", "testo": testo,
                                   "regole": []})
        return [r for r in st.registro(1).righe() if r.get("chi") == "calliope"][-1]
    f.speaker_ctx.conoscente = {"id": "k1", "nome": "Gino Neri", "nota": "collega di Carlo",
                                "modo": "voce"}
    r = esito("Mi senti?", "Ti sento bene, Gino.")
    verifica("ciclo: la risposta a un conoscente porta per.conoscente e resta «Calliope»",
             (r.get("per") or {}).get("conoscente") == "k1"
             and ctx_mod.etichetta(r) == "Calliope", str(r.get("per")))
    f.speaker_ctx.conoscente = None
    r = esito("Che tempo fa?", "Domani sole.")
    verifica("ciclo: la risposta a un ospite è «Calliope → voce non riconosciuta»",
             ctx_mod.etichetta(r) == "Calliope → voce non riconosciuta", str(r.get("per")))


def prova_contrari():
    from calliope.brain import VOCE_ORA_MAX_S
    # La frase da ospite è troppo vecchia (oltre storia_inattiva_s)
    b, chi, tel, turno = con_corsie()
    ospite(chi)
    turno("Che tempo fa domani?")
    prima = b._voce_prima
    b._voce_prima = (prima[0], prima[1] - b.cfg.storia_inattiva_s - 5, prima[2])
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("contrario: la frase da ospite oltre storia_inattiva_s → nessuna riga",
             CAMBIO not in dati(b))
    # storia_inattiva_s 0: comunque al più VOCE_ORA_MAX_S
    b, chi, tel, turno = con_corsie()
    b.cfg.storia_inattiva_s = 0
    ospite(chi)
    turno("Che tempo fa domani?")
    prima = b._voce_prima
    b._voce_prima = (prima[0], prima[1] - VOCE_ORA_MAX_S - 5, prima[2])
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("contrario: storia_inattiva_s 0 e l'ospite oltre VOCE_ORA_MAX_S → nessuna riga",
             CAMBIO not in dati(b))
    # Un altro luogo (il Brain solo che segue il satellite attivo)
    b, chi, tel, turno = con_corsie()
    luogo = ["cucina"]
    b.luogo_fn = lambda: luogo[0]
    ospite(chi)
    turno("Che tempo fa domani?")
    luogo[0] = "studio"
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("contrario: Brain solo, l'ospite era in un altro luogo → nessuna riga",
             CAMBIO not in dati(b))
    b, chi, tel, turno = con_corsie()
    b.luogo_fn = lambda: "cucina"
    ospite(chi)
    turno("Che tempo fa domani?")
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("…nello stesso luogo sì", CAMBIO in dati(b))
    # Un Brain per satellite: conta la corsia, non il luogo del satellite attivo (P4)
    b, chi, tel, turno = con_corsie()
    b.satellite = "sat:tel"
    luogo = ["cucina"]
    b.luogo_fn = lambda: luogo[0]
    ospite(chi)
    turno("Che tempo fa domani?")
    luogo[0] = "studio"            # il satellite attivo è un altro, in un'altra stanza
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("un Brain per satellite: conta la corsia, non il luogo del satellite attivo",
             CAMBIO in dati(b))
    b, chi, tel, turno = con_corsie()
    b.satellite = "sat:tel"
    ospite(chi)
    turno("Che tempo fa domani?")
    b.satellite = "sat:cucina"
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("contrario: un'altra corsia → nessuna riga", CAMBIO not in dati(b))
    # Un conoscente dopo l'ospite: resta un ospite (livello), niente riga
    b, chi, tel, turno = con_corsie()
    ospite(chi)
    turno("Che tempo fa domani?")
    chi.conoscente = {"id": "k1", "nome": "Gino Neri", "nota": "collega di Carlo"}
    di(b, "Mi senti?", chi)
    verifica("contrario: un conoscente dopo l'ospite → nessuna riga",
             "Ora la voce è riconosciuta" not in dati(b))
    # …e Carlo dopo il conoscente: il turno di prima non era di un ospite
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("contrario: Carlo dopo un conoscente → nessuna riga", CAMBIO not in dati(b))
    # In compagnia con voci sconosciute (seconda revisione): l'ospite può essere un'altra persona
    for quando in ("al turno da ospite", "al turno di Carlo"):
        b, chi, tel, turno = con_corsie()
        ospite(chi)
        chi.compagnia = chi.compagnia_sconosciute = quando == "al turno da ospite"
        turno("Mi chiamo Gino, sono allergico alle noci.")
        carlo(chi)
        chi.compagnia = chi.compagnia_sconosciute = quando == "al turno di Carlo"
        turno("E allora prenota tu.")
        verifica(f"contrario: compagnia con voci sconosciute {quando} → nessuna riga",
                 "Ora la voce è riconosciuta" not in dati(b) and b.conv.chiave
                 == "persona:carlo-id", dati(b)[:200])
    b, chi, tel, turno = con_corsie()
    ospite(chi)
    chi.compagnia, chi.compagnia_sconosciute = True, False
    turno("Che tempo fa domani?")
    carlo(chi)
    chi.compagnia = False
    turno("Aggiungi il latte.")
    verifica("…in compagnia senza voci sconosciute (conversazione di Carlo) la riga c'è, senza "
             "«forse la stessa persona»", CAMBIO in dati(b) and "forse" not in dati(b),
             dati(b)[:300])
    # Interruttore spento
    b, chi, tel, turno = con_corsie()
    b.cfg.voce_ora_riconosciuta = False
    ospite(chi)
    turno("Che tempo fa domani?")
    carlo(chi)
    turno("Aggiungi il latte.")
    verifica("interruttore spento (voce_ora_riconosciuta: false) → nessuna riga",
             CAMBIO not in dati(b))


if __name__ == "__main__":
    t0 = time.monotonic()
    for f in (prova_corsie, prova_alternanza_corsie, prova_condivisa, prova_solo_voce,
              prova_stanza, prova_esito_ciclo, prova_contrari):
        try:
            f()
        except Exception as e:  # noqa: BLE001 — un'eccezione è un errore, le altre parti girano
            errori += 1
            print(f"ERR {f.__name__}: eccezione {type(e).__name__}: {e}", flush=True)
    print(f"\n{errori} errori ({time.monotonic() - t0:.1f} s)")
    sys.exit(1 if errori else 0)
