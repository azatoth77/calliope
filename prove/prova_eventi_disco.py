"""
Il registro degli eventi su disco (10/10/2026, passo 1 del § 8 di
docs/ricerche/2026-10-10-registro-eventi.md): `prova_eventi_riavvio` e `prova_eventi_dimentica`.

    python prove/prova_eventi_disco.py

**Riavvio** (§ 2.3, § 11.5): una conversazione col ciclo vero (Brain a copione) e una proposta
aperta, poi un riavvio simulato (registri nuovi sullo stesso file, la conversazione di Brain
ripresa come da `correnti`): stessa proiezione, la proposta chiusa `persa_riavvio`, il turno dopo
confrontato senza differenze; una riga rovinata a metà del segmento → il rigioco si ferma
all'ultimo evento buono (`eventi_troncati`, nessun arresto); disco in sola lettura e disco che
non scrive → gli eventi restano in memoria, gli errori si contano, la conversazione continua.

**Dimentica** (§ 2.4, § 2.6 f, § 10 punto 1): una persona di fantasia dice «zafferano viola 42»
(eventi, archivio delle conversazioni, conversazione salvata), un'altra «melograno blu 7»;
«dimentica» → la frase di prova non c'è più nei byte di `conversazioni.db` né del WAL, quella
dell'altra persona sì; il registro in memoria è vuoto; `calliope stato` conta 0 residui (e non 0
se una riga resta); la conversazione in corso si chiude senza tornare nell'archivio.

**Rotazione e ospiti** (§ 2.3, § 2.4): le conversazioni chiuse oltre `eventi_giorni` si
cancellano, quelle mai chiuse oltre il doppio; gli eventi di un ospite alla chiusura della sua
conversazione (anche gli ultimi del lotto). **Sfida e segreti**: le parole della frase di sfida e
il codice di abbinamento restano in memoria, mai su disco. ~3 s.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calliope.conversazione import Conversazione, turni as turni_archivio  # noqa: E402
from calliope.conversazioni import ArchivioConversazioni  # noqa: E402
from calliope.eventi import proiezioni  # noqa: E402
from calliope.eventi.registro import Disco, Registri, stato_disco, testo_stato  # noqa: E402

import prova_eventi_ciclo as pe  # noqa: E402
import prova_stati_buchi as sb  # noqa: E402

errori = 0


def verifica(nome, ok, info=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({info})" if info and not ok else ""),
          flush=True)


def _contesto(registri, chiave):
    return proiezioni.contesto(registri.della_corsia(chiave).eventi())


def prova_riavvio():
    print("— riavvio: rigioco, proposta persa, riga rovinata, disco che non scrive")
    tmp = tempfile.mkdtemp(prefix="eventi-riavvio-")
    b, c, voce, stt, turni, annunci, registri = pe.prepara(
        tmp, [[("text", "Sono le dieci.")], [("text", "Il Po è lungo 652 chilometri.")]])
    pe.giro(c, stt, "Calliope, che ore sono?")
    pe.giro(c, stt, "Calliope, quanto è lungo il Po?")
    annunci.documenti.put({"messaggio": "Il documento è pronto. Lo apro?", "owner": None,
                           "in_sospeso": {"domanda": "Lo apro?", "tool": "apri_finto",
                                          "cosa": "aprire il documento",
                                          "argomenti": {"conferma": True}}})
    c.sveglia.set()
    pe.giro(c, stt)
    c._inizio_giro()                        # il turno e l'annuncio nel registro, su disco
    chiave = b.conv.chiave
    prima = _contesto(registri, chiave)
    proposta = proiezioni.proposta_aperta(registri.della_corsia(chiave).eventi())
    verifica("prima del riavvio: proposta aperta nel registro («Lo apro?»)",
             (proposta or {}).get("domanda") == "Lo apro?", str(proposta))
    salvata = b.conv.esporta()
    registri.disco.db.close()
    copia = os.path.join(tmp, "copia.db")
    shutil.copy(os.path.join(tmp, "conversazioni.db"), copia)

    # Riavvio: registri nuovi sullo stesso file
    r2 = Registri(Disco.file(os.path.join(tmp, "conversazioni.db")), log=lambda m: None)
    esito = r2.riprendi(3600.0)
    dopo = _contesto(r2, chiave)
    verifica("rigioco: la conversazione aperta ripresa, stessa proiezione",
             esito["ripresi"] == 1 and dopo == prima, f"{esito} {len(prima)} {len(dopo)}")
    ev = r2.della_corsia(chiave).eventi()
    verifica("la proposta aperta si perde al riavvio (proposta_chiusa persa_riavvio)",
             esito["proposte_perse"] == 1 and proiezioni.proposta_aperta(ev) is None
             and ev[-1].tipo == "proposta_chiusa" and ev[-1].dati.get("come") == "persa_riavvio",
             str(ev[-1]))
    verifica("seq senza buchi dopo il riavvio",
             [e.seq for e in ev] == list(range(ev[0].seq, ev[0].seq + len(ev))))
    # Il turno dopo, con Brain ripreso da `correnti` (messaggi nuovi): riconosciuti, nessuna
    # differenza
    b2, c2, voce2, stt2, turni2, _a, _r = pe.prepara(tempfile.mkdtemp(prefix="eventi-x-"), [[("text", "Prego.")]])
    c2.s.eventi = r2
    c2.ombra.registri = r2
    b2.conv = Conversazione.importa(salvata, 3600.0)
    pe.giro(c2, stt2, "Calliope, grazie mille per tutto.")
    c2._inizio_giro()
    r = turni2[-1]
    o = r.get("eventi_ombra") or {}
    verifica("dopo il riavvio la conversazione ripresa si confronta: nessuna differenza, "
             "nessun turno non osservato",
             not o.get("differenze") and not o.get("non_osservati") and o.get("eventi", 0) > 0,
             str(o))
    r2.disco.db.close()

    # Una riga rovinata a metà del segmento aperto (disco rovinato, non l'API: sola aggiunta)
    db = sqlite3.connect(copia)
    seq_max = db.execute("SELECT MAX(seq) FROM eventi").fetchone()[0]
    rovinata = seq_max - 3
    db.execute("UPDATE eventi SET dati = '{\"testo\": \"tronc' WHERE seq = ?", (rovinata,))
    db.commit()
    db.close()
    r3 = Registri(Disco.file(copia), log=lambda m: None)
    esito = r3.riprendi(3600.0)
    ev = r3.della_corsia(chiave).eventi()
    verifica("riga rovinata: rigioco fino all'ultimo evento buono, eventi_troncati, nessun "
             "arresto", esito["troncati"] == 1 and ev and max(e.seq for e in ev if e.tipo
                                                                 != "proposta_chiusa") < rovinata,
             f"{esito} {[e.seq for e in ev][-3:]}")
    n = r3.della_corsia(chiave).seq
    e_nuovo = r3.della_corsia(chiave).aggiungi("turno_chiuso", 9, esito="risposta", regole=[])
    verifica("…e il registro continua dopo l'ultima riga del disco (nessuna chiave doppia)",
             e_nuovo.seq == n + 1 and n >= seq_max, f"{n} {seq_max}")
    r3.scrivi()
    r3.disco.db.close()
    # L'ombra del ciclo dice il troncato una volta, con la regola
    b4, c4, _v, stt4, turni4, _a, _r = pe.prepara(tempfile.mkdtemp(prefix="eventi-y-"), [[("text", "Ok.")]])
    r4 = Registri(Disco.file(copia), log=lambda m: None)
    r4.riprendi(3600.0)
    c4.s.eventi = c4.ombra.registri = r4
    b4.conv = Conversazione.importa(salvata, 3600.0)
    pe.giro(c4, stt4, "Calliope, va bene così.")
    c4._inizio_giro()
    verifica("…nel registro dei turni eventi_troncati (campo e regola)",
             (turni4[-1].get("eventi_ombra") or {}).get("troncati") == 1
             and "eventi_troncati" in turni4[-1].get("regole", []), str(turni4[-1].get(
                 "eventi_ombra")))
    r4.disco.db.close()

    # Disco in sola lettura: niente arresto, eventi in memoria, persi contati
    ro = sqlite3.connect(f"file:{Path(copia).as_posix()}?mode=ro", uri=True,
                         check_same_thread=False)
    d = Disco(ro, log=lambda m: None)
    r5 = Registri(d, log=lambda m: None)
    reg = r5.della_corsia("persona:p-ettore")
    reg.apri("persona", 1)
    reg.aggiungi("detto_persona", 1, testo="Che tempo fa?", canale="voce")
    r5.scrivi()
    verifica("disco in sola lettura: nessun arresto, eventi in memoria, persi contati",
             len(reg.eventi()) == 2 and (d.persi >= 2 or d.errori >= 1), f"{d.persi} {d.errori}")
    ro.close()

    class DBRotto:
        def executemany(self, *a):
            raise sqlite3.OperationalError("disk I/O error")

        def rollback(self):
            pass
    d2 = Disco(DBRotto(), log=lambda m: None, scrivibile=False)
    d2.scrivibile = True
    log = []
    d2.log = log.append
    r6 = Registri(d2, log=lambda m: None)
    reg = r6._di("ospite:sat:1")
    reg.apri("anonima", 1)
    for _ in range(3):
        reg.aggiungi("detto_calliope", 1, testo="Ciao.", autore="atto", atto="saluto", frase=0)
        r6.scrivi()
    verifica("disco che non scrive: errori contati, il log una volta, la conversazione continua",
             d2.errori == 3 and len(log) == 1 and len(reg.eventi()) == 4, f"{d2.errori} {log}")


def _byte(cartella: str, frase: str) -> list[str]:
    """I file della cartella che contengono la frase (utf-8), nei byte."""
    b = frase.encode("utf-8")
    return [p.name for p in Path(cartella).iterdir() if p.is_file() and b in p.read_bytes()]


def prova_dimentica():
    print("— «dimentica» vera: righe, archivio, conversazione salvata, WAL, memoria")
    tmp = tempfile.mkdtemp(prefix="eventi-dimentica-")
    db = os.path.join(tmp, "conversazioni.db")
    arch = ArchivioConversazioni(db, giorni=30, embedder=None, log=lambda m: None, avvia=False)
    disco = Disco.da_archivio(arch, log=lambda m: None)
    arch.eventi = disco
    registri = Registri(disco, log=lambda m: None)
    frase, altra = "zafferano viola 42", "melograno blu 7"
    for persona, testo in (("p-giulia", f"Il codice del lucchetto è {frase}"),
                           ("p-ettore", f"La mia parola segreta è {altra}")):
        chiave = f"persona:{persona}"
        reg = registri.della_corsia(chiave)
        reg.apri("persona", 1, owner=persona)
        reg.aggiungi("detto_persona", 1, testo=testo, canale="voce", brain=True)
        reg.aggiungi("detto_calliope", 1, testo="Me lo ricordo.", autore="contenuto",
                     atto="risposta", frase=0, canale="voce")
        reg.aggiungi("voce_fine", 1, da=0, inviate=1, sentite=1, interrotta=False)
        conv = Conversazione(chiave)
        conv.owner = persona
        conv.history = [{"role": "user", "content": testo},
                        {"role": "assistant", "content": "Me lo ricordo."}]
        conv.last_turn_at = time.monotonic()
        arch.archivia(conv, turni_archivio(conv.history), persona, persona.title(), False)
        arch.salva_corrente(conv)
    registri.scrivi()
    with arch.lock:
        arch.db.commit()
    verifica("prima: la frase di prova è nei file", bool(_byte(tmp, frase)), str(_byte(tmp, frase)))
    n = arch.dimentica("p-giulia")
    registri.dimentica("persona:p-giulia")
    verifica("dimentica: una conversazione cancellata", n == 1, str(n))
    verifica("la frase di prova non è più nei byte di conversazioni.db né del WAL",
             not _byte(tmp, frase), str(_byte(tmp, frase)))
    verifica("…quella dell'altra persona sì (contrario)", bool(_byte(tmp, altra)))
    verifica("il registro della persona in memoria è vuoto, quello dell'altra no",
             not registri.della_corsia("persona:p-giulia").eventi()
             and registri.della_corsia("persona:p-ettore").eventi())
    st = stato_disco(db)
    verifica("calliope stato: dimentica 1 richiesta, residui 0",
             st and st["dimentica"] == {"richieste": 1, "residui": 0}, str(st))
    riga = testo_stato(st) or ""
    verifica("…la riga di calliope stato", "Dimentica: 1 richieste, residui 0" in riga, riga)
    # Contrario: una riga rimasta (scritta prima della richiesta) è un residuo
    with arch.lock:
        arch.db.execute("INSERT INTO eventi (registro, seq, conv, corsia, t, tipo, turno, vis, "
                        "persona, ospite, dati, v) VALUES ('persona:p-giulia', 999, 'x', NULL, "
                        "?, 'turno_chiuso', 1, 'registro', 'p-giulia', 0, '{}', 1)",
                        (time.time() - 3600,))
        arch.db.commit()
    st = stato_disco(db)
    verifica("contrario: una riga di prima rimasta → residui 1 e l'avviso",
             st["dimentica"]["residui"] == 1 and "ATTENZIONE" in (testo_stato(st) or ""),
             str(st))
    # La conversazione in corso della persona (Brain vero): si chiude senza tornare nell'archivio
    b = sb.brain([])
    b.archivio_conv = arch
    b.conv = Conversazione("persona:p-giulia")
    b.conv.owner = "p-giulia"
    b.conv.history = [{"role": "user", "content": f"Ripeti: {frase}"},
                      {"role": "assistant", "content": "Va bene."}]
    b.salva_conversazione()                 # come a fine turno, prima della chiusura
    turni_prima = arch.conteggi()["turni"]
    b.dimentica_conversazione()
    arch.pulisci_wal()
    verifica("la conversazione in corso si chiude vuota, senza tornare nell'archivio",
             not b.conv.history and arch.conteggi()["turni"] == turni_prima)
    verifica("…e la frase non resta nemmeno nella conversazione salvata né nel WAL",
             not _byte(tmp, frase), str(_byte(tmp, frase)))
    arch.close()


def prova_rotazione():
    print("— rotazione e ospiti: cosa resta su disco")
    with tempfile.TemporaryDirectory() as tmp:
        d = Disco.file(os.path.join(tmp, "c.db"))
        r = Registri(d, log=lambda m: None)
        ora = time.time()
        vecchio = ora - 10 * 86400
        # Una conversazione chiusa di dieci giorni fa, una aperta di dieci giorni fa (mai
        # chiusa: un arresto), una chiusa ieri
        for chiave, t0, chiudi in (("persona:p-ettore", vecchio, True),
                                   ("persona:p-bianca", vecchio, False),
                                   ("persona:p-nadia", ora - 86400, True)):
            reg = r.della_corsia(chiave)
            reg.aggiungi("conversazione_aperta", 1, t=t0, chiave=chiave, come="persona")
            reg.aggiungi("detto_persona", 1, t=t0, testo="Una frase di prova.", canale="voce")
            if chiudi:
                reg.aggiungi("conversazione_chiusa", 1, t=t0, motivo="esci")
        r.scrivi()

        def quanti(chiave):
            return d.db.execute("SELECT COUNT(*) FROM eventi WHERE registro = ?",
                                (chiave,)).fetchone()[0]
        d.ruota(7, ora)
        verifica("rotazione: via la conversazione chiusa più vecchia di eventi_giorni",
                 quanti("persona:p-ettore") == 0)
        verifica("…resta quella chiusa ieri", quanti("persona:p-nadia") == 3)
        verifica("…e quella mai chiusa finché non passa il doppio (14 giorni)",
                 quanti("persona:p-bianca") == 2)
        d.ruota(4, ora)
        verifica("…oltre il doppio va via anche lei", quanti("persona:p-bianca") == 0)
        # Ospite: alla chiusura della sua conversazione gli eventi con testo si cancellano
        reg = r.della_corsia("ospite:sat:cucina")
        reg.apri("anonima", 1)
        reg.aggiungi("detto_persona", 1, testo="Dov'è il bagno?", canale="voce")
        r.scrivi()
        verifica("ospite: gli eventi ci sono finché la conversazione è aperta",
                 quanti("ospite:sat:cucina") == 2)
        reg.chiudi("esci", 1)
        r.scrivi()
        verifica("ospite: alla chiusura si cancellano (anche gli ultimi)",
                 quanti("ospite:sat:cucina") == 0,
                 str(quanti("ospite:sat:cucina")))
        d.db.close()


def prova_sfida_su_disco():
    print("— frase di sfida e segreti: in memoria sì, su disco no")
    from calliope.eventi.ombra import Ombra
    import types
    with tempfile.TemporaryDirectory() as tmp:
        d = Disco.file(os.path.join(tmp, "c.db"))
        r = Registri(d, log=lambda m: None)
        conv = Conversazione("persona:p-ettore")
        conv.history = [{"role": "user", "content": "Calliope, cancella il documento."},
                        {"role": "assistant", "content": "Per conferma ripeti: girasole, treno."}]
        brain = types.SimpleNamespace(conv=conv, last_capito=None, last_sfida=False,
                                      redact=lambda x: x)
        c = types.SimpleNamespace(brain=brain, speaker=types.SimpleNamespace(
            played=[], interrupted=False), corsia=types.SimpleNamespace(chiave="locale",
                                                                        nome="locale"),
            speaker_ctx=None, rule=lambda n: None)
        o = Ombra(types.SimpleNamespace(eventi="ombra"), r, c, log=lambda m: None)
        o._finestra.append(("say", "Per conferma ripeti: girasole, treno.", "risposta", False))
        t = types.SimpleNamespace(text="Calliope, cancella il documento.", scritto=None)
        o.chiudi_turno({"esito": "risposta", "regole": ["sfida_voce"]}, t)
        d.db.commit()
        dentro = b"girasole" in Path(tmp, "c.db").read_bytes() + (
            Path(tmp, "c.db-wal").read_bytes() if Path(tmp, "c.db-wal").exists() else b"")
        mem = " ".join(str(e.dati.get("testo")) for e in r.della_corsia(conv.chiave).eventi())
        verifica("le parole della sfida in memoria (il confronto) ma mai su disco",
                 "girasole" in mem and not dentro)
        brain.redact = lambda x: x.replace("123456", "******")
        conv.history += [{"role": "user", "content": "Il codice è 123456."},
                         {"role": "assistant", "content": "Abbinato."}]
        t.text = "Il codice è 123456."
        o._finestra.append(("say", "Abbinato.", "risposta", False))
        o.chiudi_turno({"esito": "risposta", "regole": []}, t)
        dentro = b"123456" in Path(tmp, "c.db").read_bytes() + (
            Path(tmp, "c.db-wal").read_bytes() if Path(tmp, "c.db-wal").exists() else b"")
        verifica("il codice di abbinamento detto dalla persona non va su disco", not dentro)
        d.db.close()


def main():
    prova_rotazione()
    prova_sfida_su_disco()
    prova_riavvio()
    prova_dimentica()
    print(f"\n{'Tutto bene' if not errori else f'{errori} errori'}")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
