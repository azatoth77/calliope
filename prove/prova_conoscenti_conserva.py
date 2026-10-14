"""
Prova a secco della conservazione dei conoscenti (14/10/2026 sera, decisione 0030 aggiornata da
Dario: «per un conoscente si conservano il nome e le sue parole, non come un ospite»;
calliope/conserva.py, turnlog.py, conversazioni.py, ciclo._conoscente_turno, Brain._speaker_key).

- il turno di un conoscente nel registro dei turni con il suo id, il nome e le parole; il
  contrario: un ospite vero resta senza parole né nome; la voce registrata no (niente consenso);
- terminale e journal: il nome e le parole per il conoscente, mai per l'ospite;
- la sua conversazione (una per conoscente, `persona:<id>`), anche con una frase breve nella
  finestra d'ascolto; contrari: fuori dalla finestra, conversazione anonima, famiglia nella zona
  grigia; l'archivio delle conversazioni su disco (l'ospite nella sessione), gli eventi su disco,
  la pulizia di ogni giorno che non lo toglie;
- chi le ritrova: chi amministra con `ospiti=true` (col nome); contrari: il conoscente stesso,
  un familiare, chi amministra senza `ospiti`;
- «dimentica», la scadenza dei 180 giorni, «svuota» di una persona (tool dati_conservati e
  terminale, dal file) e di tutto: via turni, conversazioni ed eventi; gli altri restano;
- promozione a familiare (stesso id: turni e archivio restano suoi) e ritorno (restano; la voce
  registrata da familiare si toglie, un conoscente non ha il consenso);
- permessi invariati: livello ospite, niente tool della famiglia.

Nomi di fantasia (gli stessi di prova_stanza_conoscenti.py). ~3 s.
"""

import datetime
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))
sys.path.insert(0, QUI)

import prova_stanza_conoscenti as K  # noqa: E402  (scena, voci finte, ciclo)
from calliope import conserva as C  # noqa: E402
from calliope import corsie  # noqa: E402
from calliope.conversazione import Conversazione, turni as turni_conv  # noqa: E402
from calliope.conversazioni import ArchivioConversazioni  # noqa: E402
from calliope.tools import conserva as tool_cons  # noqa: E402
from calliope.tools import conversazioni as tool_conv  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402
from calliope.turnlog import TurnLog, read_turns  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                  else ""), flush=True)


class Mondo:
    """Stanza, conoscenti, conservazione, registro dei turni e archivio collegati come in main."""

    def __init__(self, nome: str):
        self.tmp = Path(tempfile.mkdtemp(prefix=f"calliope-conoscenti-{nome}-"))
        self.cfg = K.cfg_base(conoscenti_file=str(self.tmp / "conoscenti.json"),
                              stanza_tenuta_db=str(self.tmp / "stanza.db"),
                              turn_log_dir=str(self.tmp / "registro"), config_dir=str(self.tmp))
        self.sc = K.Scena(self.cfg)
        self.voci, self.con = self.sc.voci, self.sc.con
        self.log = []
        cons = self.cons = C.Conservazione(self.cfg, self.voci, log=self.log.append)
        cons.stanza, cons.conoscenti = self.sc.st.tenuta, self.con
        self.con.su_tolto.append(cons.conoscente_tolto)
        self.tl = TurnLog(self.cfg.turn_log_dir, 60, conserva=cons)
        cons.turnlog = self.tl
        self.arch = ArchivioConversazioni(self.tmp / "conv.db", giorni=60,
                                          log=lambda m: None, avvia=False,
                                          conserva=cons.conversazioni_su_disco)
        self.arch.conoscenti_ids = cons.conoscenti_ids
        cons.conversazioni = self.arch
        self.ciclo, self.sctx = K.ciclo_per(self.sc, self.cfg, self.voci)
        self.n = 0

    def salva(self, v, nome, cognome="", nota=""):
        K.marco_presentato(self.sc, v, nome)
        out = self.con.risposta(K.scheda_a(self.sc.hub, 1)[-1]["proposta"], "si", "carlo-id",
                                nome, cognome, nota)
        return self.con.per_id(out["conoscente"])

    def turno(self, emb, testo, voce_s=2.5, prev=None, in_session=False, audio=None):
        """Un turno rivolto a Calliope fino al registro dei turni (come il ciclo)."""
        self.n += 1
        t = K.turno(self.ciclo, self.sctx, emb, testo=testo, voce_s=voce_s, prev=prev,
                    in_session=in_session)
        rec = self.ciclo.rec
        rec.update(esito="risposta", risposta=f"Risposta {self.n}.",
                   inizio=datetime.datetime.now().isoformat(timespec="milliseconds"))
        self.cons.al_turno(rec, audio)
        self.tl.write(rec)
        return t, rec

    def righe(self):
        return read_turns(self.cfg.turn_log_dir)

    def archivia(self, chi, nome, testo, ospite=False, conv=None):
        conv = conv or Conversazione(f"persona:{chi}" if chi else "ospite:sat:1")
        conv.owner, conv.nome, conv.last_turn_at = chi, nome, time.monotonic()
        msgs = [{"role": "user", "content": testo}, {"role": "assistant", "content": "Va bene."}]
        conv.history += msgs
        self.arch.archivia(conv, turni_conv(msgs), chi, nome, ospite=ospite)
        return conv

    def su_disco(self, persona):
        return [d for (d,) in self.arch.db.execute(
            "SELECT t.domanda FROM turni t JOIN conversazioni c ON c.id = t.conv "
            "WHERE c.persona = ? AND c.ospite = 0", (str(persona),))]

    def chiudi(self):
        self.arch.close()
        self.sc.chiudi()


def ctx_di(m: Mondo, nome, livello=None, come="voce", turno=1, sctx=None):
    c = K.contesto(m.sc, nome, livello, come, turno=turno)
    if sctx is not None:
        c.speaker_ctx = sctx
    c.conversazioni, c.conserva = m.arch, m.cons
    return c


def chiave_di(sctx, voci):
    from calliope.brain import Brain
    b = Brain.__new__(Brain)
    b.tool_ctx = ToolContext(cfg=None, speakers=voci, speaker_ctx=sctx, speaker=None)
    return b._speaker_key()


# ─────────────────────────── 1. turni, console, voce ───────────────────────────
def prova_turni(m: Mondo, c):
    t, rec = m.turno(K.voce(K.MARCO, 0.03, seme=11), "Calliope, porto io il vino stasera?",
                     audio=np.zeros(16000, dtype=np.float32) + 0.01)
    r = m.righe()[-1]
    verifica("conoscente: nel registro dei turni il suo id, il nome e le parole",
             r["voce"].get("conoscente") is True and r["voce"].get("id") == c.id
             and r["voce"].get("nome_conoscente") == "Marco Rossi"
             and r["testo"] == "Calliope, porto io il vino stasera?"
             and r["risposta"] == f"Risposta {m.n}." and "conserva" not in r, json.dumps(r))
    verifica("…ma resta un ospite (livello, chi parla)",
             r["livello"] == "ospite" and r["voce"]["nome"] is None
             and m.sctx.current_level == "ospite" and m.sctx.current_speaker is None)
    verifica("la voce registrata no: un conoscente non ha il consenso",
             "voce_file" not in r and m.cons.voce_turno(rec).motivo == "senza_consenso"
             and not (m.tmp / "registro" / "voce").exists())
    verifica("terminale e journal: il nome e le parole (come un adulto)",
             C.console_riservata(m.sctx, m.voci) is None)
    verifica("la chiave della conversazione è il suo id (Brain._speaker_key)",
             chiave_di(m.sctx, m.voci) == c.id)
    # Contrario: un ospite vero
    t, rec = m.turno(K.voce(15, 0.03, seme=12), "Calliope, il mio cane si chiama Fido")
    r = m.righe()[-1]
    verifica("contrario: un ospite vero resta senza parole né nome",
             r["testo"] is None and r["risposta"] is None and r["testo_parole"] == 7
             and "conoscente" not in r["voce"] and "id" not in r["voce"], json.dumps(r))
    verifica("contrario: per l'ospite niente parole nel terminale, nessuna chiave",
             C.console_riservata(m.sctx, m.voci) == "ospite"
             and chiave_di(m.sctx, m.voci) is None)
    # Contrario: un TurnLog senza conservazione (prove, stato) non tiene le parole del conoscente
    tl2 = TurnLog(str(m.tmp / "senza"), 60)
    tl2.write({"livello": "ospite", "testo": "ciao", "voce": {"nome": None, "conoscente": True,
                                                                "id": c.id}})
    verifica("contrario: senza la conservazione collegata, nel dubbio senza parole",
             read_turns(str(m.tmp / "senza"))[-1]["testo"] is None)
    # Contrario: un id che non è più un conoscente
    verifica("contrario: un id di conoscente sconosciuto vale ospite",
             not m.cons.testo_turno({"livello": "ospite", "testo": "x", "voce": {
                 "nome": None, "conoscente": True, "id": "nessuno", "modo": "voce"}}))
    # Carlo, per vedere che i suoi turni restano quando si dimentica il conoscente
    m.turno(K.voce(K.CARLO, 0.03, seme=13), "Calliope, accendi la luce in cucina")


# ─────────────────────────── 2. la sua conversazione ───────────────────────────
def prova_conversazione(m: Mondo, c):
    reg = corsie.RegistroConversazioni(m.cfg, log=lambda s: None)
    corsia = corsie.Corsia("sat:1", 1, "satellite cucina", reg)
    m.ciclo.corsia = corsia
    m.ciclo.s.instradamento = SimpleNamespace(persona=lambda p: None)
    m.ciclo._frasi_turno = lambda t: None
    m.ciclo.brain = SimpleNamespace(conv=None)

    def conv_del(emb, testo, **k):
        t = K.turno(m.ciclo, m.sctx, emb, testo=testo, **k)
        m.ciclo._conversazione_del_turno(t)
        return corsia.conv

    cv = conv_del(K.voce(K.MARCO, 0.03, seme=21), "Calliope, che ore sono?")
    verifica("la sua conversazione, una per conoscente (persona:<id>)",
             cv is not None and cv.chiave == f"persona:{c.id}", getattr(cv, "chiave", None))
    cv2 = conv_del(K.voce(K.MARCO, 0.03, seme=22), "Sì.", voce_s=0.6, in_session=True)
    verifica("una frase breve nella finestra d'ascolto continua la sua conversazione",
             cv2 is cv and m.sctx.conoscente and m.sctx.conoscente["modo"] == "breve"
             and m.ciclo.rec["voce"]["modo"] == "breve"
             and m.sctx.current_level == "ospite", str(m.sctx.conoscente))
    rec = dict(m.ciclo.rec, testo="Sì.")
    verifica("…e le sue parole restano (frase breve come per un adulto)",
             bool(m.cons.testo_turno(rec)))
    conv_del(K.voce(K.MARCO, 0.03, seme=23), "Sì.", voce_s=0.6, in_session=False)
    verifica("contrario: frase breve fuori dalla finestra d'ascolto → ospite",
             m.sctx.conoscente is None and corsia.conv.chiave.startswith("ospite:"))
    conv_del(K.voce(K.MARCO, 0.03, seme=24), "Sì.", voce_s=0.6, in_session=True)
    verifica("contrario: frase breve nella conversazione anonima → ospite",
             m.sctx.conoscente is None)
    conv_del(K.voce(K.MARCO, 0.03, seme=25), "Calliope, e domani?")
    conv_del(K.miscela({K.CARLO: 0.44, K.MARCO: 0.85}), "Sì.", voce_s=0.6, in_session=True)
    verifica("contrario: frase breve con la famiglia nella zona grigia → mai il conoscente",
             m.sctx.conoscente is None)
    verifica("eventi su disco per il conoscente, mai per l'ospite",
             m.cons.registro_su_disco(f"persona:{c.id}")
             and not m.cons.registro_su_disco("ospite:sat:1"))
    # L'archivio
    cm = m.archivia(c.id, "Marco Rossi", "porto io il vino rosso stasera")
    co = m.archivia(None, None, "sono un ospite e il mio cane si chiama Fido", ospite=True)
    m.archivia("carlo-id", "Carlo", "il vino lo compro io domani")
    m.arch.attendi()
    verifica("archivio: la conversazione del conoscente su disco (col nome)",
             cm.archiviata_in == "disco" and m.su_disco(c.id) == ["porto io il vino rosso stasera"]
             and m.arch.db.execute("SELECT nome FROM conversazioni WHERE persona = ?",
                                   (c.id,)).fetchone()[0] == "Marco Rossi")
    verifica("contrario: l'ospite nella sessione, mai su disco",
             co.archiviata_in == "sessione"
             and not m.arch.db.execute("SELECT 1 FROM conversazioni WHERE ospite = 1").fetchone())
    verifica("la pulizia di ogni giorno non toglie il conoscente",
             m.arch.togli_non_conservate() == 0 and m.su_disco(c.id))


# ─────────────────────────── 3. chi le ritrova ───────────────────────────
def prova_ricerca(m: Mondo, c):
    r = tool_conv._cerca_archivio(ctx_di(m, "Carlo"), "vino rosso", ospiti=True)
    chi = [x.get("chi") for x in r.get("risultati", [])]
    verifica("chi amministra con ospiti=true ritrova il conoscente, col nome",
             r["ok"] and "Marco Rossi, conoscente" in chi
             and any("vino rosso" in x.get("detto_da_ospite", "") for x in r["risultati"]),
             str(r)[:400])
    r = tool_conv._cerca_archivio(ctx_di(m, "Carlo"), "cane Fido", ospiti=True)
    verifica("…e gli ospiti come prima (sessione)",
             r["ok"] and any("Fido" in x.get("detto_da_ospite", "") for x in r["risultati"]))
    r = tool_conv._cerca_archivio(ctx_di(m, "Carlo"), "vino rosso")
    verifica("contrario: chi amministra senza ospiti=true trova solo le sue",
             not any("rosso" in json.dumps(x, ensure_ascii=False)
                     for x in r.get("risultati", [])), str(r)[:300])
    r = tool_conv._cerca_archivio(ctx_di(m, "Bianca"), "vino rosso", ospiti=True)
    verifica("contrario: un familiare con ospiti=true no", not r["ok"])
    r = tool_conv._cerca_archivio(ctx_di(m, "Carlo", come="conversazione"), "vino", ospiti=True)
    verifica("contrario: chi amministra dalla zona grigia no", not r["ok"])
    K.turno(m.ciclo, m.sctx, K.voce(K.MARCO, 0.03, seme=31), "Calliope, cosa ti ho detto?")
    ctx_k = ctx_di(m, None, sctx=m.sctx)
    r = tool_conv._cerca_archivio(ctx_k, "vino")
    verifica("contrario: il conoscente non ritrova le sue (è un ospite)",
             m.sctx.conoscente and not r["ok"], str(r)[:200])
    specs = {s.name: s for s in tool_conv.conversazioni_specs() + tool_cons.conserva_specs()}
    verifica("permessi invariati: conversazione_cerca e dati_conservati non sono per gli ospiti",
             "ospite" not in specs["conversazione_cerca"].levels
             and "ospite" not in specs["dati_conservati"].levels)


# ─────────────────────────── 4. dimentica e scadenza ───────────────────────────
def prova_dimentica(m: Mondo, c):
    m.con.dimentica(c.id)
    m.arch.attendi()
    righe = m.righe()
    suoi = [r for r in righe if r["voce"].get("id") == c.id]
    carlo = [r for r in righe if r["voce"].get("nome") == "Carlo"]
    verifica("«dimentica Marco»: le parole dei suoi turni tolte",
             suoi and all(r["testo"] is None for r in suoi), json.dumps(suoi)[:300])
    verifica("…le sue conversazioni archiviate e gli eventi su disco via",
             not m.su_disco(c.id) and not m.cons.registro_su_disco(f"persona:{c.id}")
             and m.cons.conversazioni_su_disco(c.id) is False)
    verifica("contrario: i turni e le conversazioni di Carlo restano",
             carlo and carlo[-1]["testo"] == "Calliope, accendi la luce in cucina"
             and m.su_disco("carlo-id"))
    verifica("contrario: dopo il dimentica la sua voce vale un ospite (parole non restano)",
             not m.cons.testo_turno({"livello": "ospite", "testo": "x", "voce": {
                 "nome": None, "conoscente": True, "id": c.id, "modo": "voce"}}))
    # La scadenza
    k = m.salva(K.MARCO2, "Luigi")
    m.turno(K.voce(K.MARCO2, 0.03, seme=41), "Calliope, a che ora parte il treno?")
    m.archivia(k.id, "Luigi", "il treno per Bologna parte alle otto")
    m.arch.attendi()
    prima = bool(m.su_disco(k.id)) and m.righe()[-1]["testo"]
    m.con.ruota(time.time() + 181 * 86400)
    m.arch.attendi()
    verifica("scadenza (180 giorni senza sentirlo): via profilo, parole dei turni e archivio",
             prima and m.con.per_id(k.id) is None and not m.su_disco(k.id)
             and all(r["testo"] is None for r in m.righe() if r["voce"].get("id") == k.id))


# ─────────────────────────── 5. svuota ───────────────────────────
def prova_svuota(m: Mondo):
    k = m.salva(K.PAOLO, "Paolo")
    m.turno(K.voce(K.PAOLO, 0.03, seme=51), "Calliope, il mio numero è il tre due uno")
    m.archivia(k.id, "Paolo", "il mio numero di maglia è il ventitré")
    m.sc.di(K.PAOLO, "Domani porto io il pallone.")
    m.arch.attendi()
    m.sc.st.tenuta.attendi()

    def righe_stanza():
        import sqlite3
        db = sqlite3.connect(m.cfg.stanza_tenuta_db)
        try:
            return db.execute("SELECT COUNT(*) FROM righe WHERE persona = ?",
                              (f"conoscente:{k.id}",)).fetchone()[0]
        finally:
            db.close()
    stanza_prima = righe_stanza()
    r = tool_cons._dati_conservati(ctx_di(m, "Carlo", turno=1), "svuota", "Ugo")
    verifica("contrario: svuota di un nome che nessuno ha", not r["ok"]
             and "Non conosco" in r["risposta_finale"])
    r = tool_cons._dati_conservati(ctx_di(m, "Bianca", turno=1), "svuota", "Paolo")
    verifica("contrario: un familiare non svuota i dati del conoscente", not r["ok"]
             and m.su_disco(k.id))
    r1 = tool_cons._dati_conservati(ctx_di(m, "Carlo", turno=2), "svuota", "Paolo")
    r2 = tool_cons._dati_conservati(ctx_di(m, "Carlo", turno=3), "svuota", "Paolo")
    m.arch.attendi()
    verifica("dati_conservati svuota «Paolo» (conoscente), con la domanda e il sì",
             not r1["ok"] and "in_sospeso" in r1 and r2["ok"] and not m.su_disco(k.id)
             and all(r["testo"] is None for r in m.righe() if r["voce"].get("id") == k.id),
             str(r2)[:300])
    verifica("…anche le sue righe della stanza su disco",
             stanza_prima >= 1 and righe_stanza() == 0, f"{stanza_prima}")
    verifica("…il profilo resta (si dimentica con «dimentica Paolo»)",
             m.con.per_id(k.id) is not None)
    # Da terminale (senza i conoscenti di Calliope): dal file
    cons_t = C.Conservazione(m.cfg, m.voci, log=lambda s: None)
    trovati = cons_t.trova_conoscenti("Paolo")
    verifica("da terminale: il conoscente si trova nel file (svuota --persona)",
             [x.id for x in trovati] == [k.id] and cons_t.conoscente(k.id) is not None
             and C.categoria(cons_t.profilo(persona_id=k.id)) == "conoscente")
    m.turno(K.voce(K.PAOLO, 0.03, seme=52), "Calliope, ricordati di me")
    m.archivia(k.id, "Paolo", "sono ancora io, Paolo")
    m.arch.attendi()
    out = m.cons.svuota()
    m.arch.attendi()
    verifica("svuota di tutto: conoscenti, turni e archivio via (anche i suoi)",
             out.get("conoscenti") == 1 and not m.righe() and not m.su_disco(k.id)
             and m.con.per_id(k.id) is None
             and not any("non tolti" in x for x in m.log), str(out))


# ─────────────────────────── 6. promozione e ritorno ───────────────────────────
def prova_promozione(m: Mondo):
    k = m.salva(K.BIANCA2, "Gina", "Neri")
    m.turno(K.voce(K.BIANCA2, 0.03, seme=61), "Calliope, che tempo fa a Bologna?")
    m.archivia(k.id, "Gina Neri", "la torta di mele la porto io")
    m.arch.attendi()
    prof = m.con.promuovi(k.id)
    m.arch.attendi()
    verifica("promossa a familiare: stesso id, turni e archivio restano suoi",
             prof.id == k.id and C.categoria(m.cons.profilo(persona_id=k.id)) == "adulto"
             and m.su_disco(k.id) == ["la torta di mele la porto io"]
             and any(r["testo"] == "Calliope, che tempo fa a Bologna?" for r in m.righe()
                     if r["voce"].get("id") == k.id)
             and m.arch.cerca("torta di mele", k.id)["risultati"])
    verifica("…e la conversazione resta su disco (pulizia di ogni giorno)",
             m.arch.togli_non_conservate() == 0 and m.su_disco(k.id))
    # Da familiare dà il consenso alla voce: una registrazione
    prof.voce_conservata = True
    wav = m.cons.voce_dir / k.id / datetime.date.today().isoformat() / "100000-000.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(C.wav_mulaw(np.zeros(1600, dtype=np.float32), 16000))
    m.cons.ruota()
    verifica("da familiare col consenso la voce resta", wav.exists())
    m.con.declassa(m.voci.users["Gina Neri"])
    m.arch.attendi()
    verifica("tornata conoscente: turni e archivio restano (stesso id)",
             C.categoria(m.cons.profilo(persona_id=k.id)) == "conoscente"
             and m.su_disco(k.id) and m.arch.togli_non_conservate() == 0)
    m.cons.ruota()
    verifica("…la voce registrata no: un conoscente non ha il consenso", not wav.exists())


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    m = Mondo("a")
    c = m.salva(K.MARCO, "Marco", "Rossi", "collega di Carlo")
    try:
        prova_turni(m, c)
        prova_conversazione(m, c)
        prova_ricerca(m, c)
        prova_dimentica(m, c)
        prova_svuota(m)
        prova_promozione(m)
    finally:
        m.chiudi()
    print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
    return 1 if errori else 0


if __name__ == "__main__":
    raise SystemExit(main())
