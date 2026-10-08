import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""L'attrito della sicurezza come metrica (08/10/2026, fase 1 del progetto «sicurezza per
valore», calliope/attrito.py). A secco, su un registro dei turni finto (nomi di fantasia):

- le domande di sicurezza si contano per tipo (politica, ciò che dice, sfida d'identità a parte),
  ogni 100 turni con una frase; i turni senza frase o di cortesia non contano;
- le domande ripetute per lo stesso tool e la stessa persona entro 5 minuti (un'altra persona o
  dopo 5 minuti no), quelle seguite dall'esecuzione dello stesso tool entro 3 turni della stessa
  persona, le frasi «te l'ho già detto»;
- l'avviso (D6): oltre 3 ogni 100 turni con almeno 50 turni, oppure una domanda ripetuta;
  sotto i 50 turni e senza ripetute, niente avviso;
- il confronto con la politica per valore in ombra (`politica_ombra`): domande evitate, in più,
  esecuzioni con un bersaglio dal dato, attrito simulato;
- `calliope stato --turni` stampa la tabella; nessun testo delle frasi nell'uscita.

    python prove\\prova_attrito.py
"""

import datetime
import json
import tempfile
from pathlib import Path

from calliope import attrito

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok else ""),
          flush=True)


T0 = datetime.datetime(2026, 10, 7, 17, 0, 0)


def turno(s, testo="che ore sono?", chi="Bianca", regole=(), risposta="Sono le cinque.",
          tool=(), esito="risposta", **k):
    return {"inizio": (T0 + datetime.timedelta(seconds=s)).isoformat(), "esito": esito,
            "testo": testo, "voce": {"nome": chi}, "regole": list(regole),
            "risposta": risposta, "tool": list(tool), **k}


def domanda_apri(s, chi="Bianca", testo="apri il file"):
    return turno(s, testo, chi, ["politica_conferma"],
                 "C'è di mezzo una foto, quindi chiedo a te: vuoi che apra il file?",
                 [{"nome": "pc_apri_file", "ok": False}])


def prova_conti():
    turni = [domanda_apri(0), domanda_apri(30, testo="te l'ho già detto, aprilo"),
             turno(60, "sì", tool=[{"nome": "pc_apri_file", "ok": True}]),
             # un'altra persona entro 5 minuti: non è una ripetuta
             domanda_apri(90, chi="Carlo"),
             # la stessa persona dopo più di 5 minuti dall'ultima: non è ripetuta
             domanda_apri(30 + 400),
             # ciò che dice
             turno(900, regole=["uscita_istruzione"], risposta="Te lo dico se me lo chiedi."),
             # sfida d'identità senza dato: a parte
             turno(960, "registra la voce", regole=["sfida_voce"],
                   risposta="Per registrare la voce, ripeti: …"),
             # sfida della politica: «c'è di mezzo»
             turno(1000, "approva", regole=["sfida_voce", "politica_conferma_unica"],
                   risposta="C'è di mezzo il lavoro di un agente. Per approvare, ripeti: …",
                   tool=[{"nome": "estensioni_gestisci", "ok": False}]),
             turno(1100, "", esito="vuoto"), turno(1110, "grazie", esito="cortesia")]
    turni += [turno(1200 + i) for i in range(10)]
    d = attrito.giorno(turni)
    verifica("conti: turni con una frase (senza vuoti e cortesia)", d["turni"] == 18, str(d))
    verifica("conti: domande per tipo", (d["politica"], d["riferire"], d["voce"]) == (5, 1, 1),
             str(d))
    verifica("conti: attrito senza le sfide d'identità", d["domande"] == 6
             and d["attrito"] == round(600 / 18, 1), str(d))
    verifica("conti: una sola ripetuta (stessa persona e tool entro 5 minuti)",
             d["ripetute"] == 1, str(d))
    verifica("conti: poi eseguite entro 3 turni della stessa persona", d["accettate"] == 2
             and d["fermate"] == 5, str(d))
    verifica("conti: «te l'ho già detto»", d["gia_detto"] == 1, str(d))
    verifica("conti: per tool", d["per_tool"] == {"pc_apri_file": 4, "estensioni_gestisci": 1},
             str(d["per_tool"]))


def prova_avviso():
    pochi = [turno(i * 10) for i in range(20)] + [domanda_apri(500)]
    d = attrito.giorno(pochi)
    verifica("avviso: sotto i 50 turni e senza ripetute, niente", attrito.avviso(d) is None, str(d))
    pochi.append(domanda_apri(520))
    verifica("avviso: una ripetuta basta anche con pochi turni",
             "ripetute" in (attrito.avviso(attrito.giorno(pochi)) or ""))
    tanti = [turno(i * 10) for i in range(60)] + [domanda_apri(1000 + i * 400) for i in range(1)]
    d = attrito.giorno(tanti)
    verifica("avviso: 1 su 61 sotto la soglia di 3 ogni 100", attrito.avviso(d) is None, str(d))
    tanti += [domanda_apri(5000 + i * 400) for i in range(5)]
    a = attrito.avviso(attrito.giorno(tanti))
    verifica("avviso: 6 su 66 sopra la soglia", a is not None and "9,1" in a, a)
    verifica("avviso: soglia 0 = solo le ripetute", attrito.avviso(attrito.giorno(tanti), 0)
             is None)


def prova_ombra():
    def chiamata(vera, nuova, bersagli=()):
        return {"nome": "pc_apri_file", "ok": vera == "esegui",
                "politica_ombra": {"vera": vera, "nuova": nuova, "bersagli": list(bersagli)}}
    turni = [turno(0, tool=[chiamata("conferma", "esegui")], regole=["politica_conferma"]),
             turno(10, tool=[chiamata("esegui", "esegui")]),
             turno(20, tool=[chiamata("esegui", "conferma")]),
             turno(30, tool=[chiamata("conferma", "esegui", ["dato"])],
                   regole=["politica_conferma"])]
    o = attrito.giorno(turni)["ombra"]
    verifica("ombra: chiamate, diverse, evitate, in più", (o["chiamate"], o["diverse"],
             o["evitate"], o["in_piu"]) == (4, 3, 2, 1), str(o))
    verifica("ombra: esecuzione in più con un bersaglio dal dato", o["dato_eseguite"] == 1, str(o))
    verifica("ombra: attrito simulato (2 − 2 + 1 su 4)", o["attrito_simulato"] == 25.0, str(o))
    verifica("ombra: senza il campo, attrito simulato assente",
             attrito.giorno([turno(0)])["ombra"]["attrito_simulato"] is None)


def prova_stato():
    with tempfile.TemporaryDirectory() as d:
        righe = [domanda_apri(0), domanda_apri(30)] + [turno(100 + i) for i in range(5)]
        (Path(d) / "turni-2026-10-07.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in righe) + "\nrotta\n",
            encoding="utf-8")
        from calliope.latenza import leggi
        g = attrito.per_giorno(leggi(d))
        t = attrito.testo(g)
        verifica("stato: la tabella ha il giorno e l'avviso della ripetuta",
                 "2026-10-07" in t and "ATTENZIONE" in t, t)
        verifica("stato: nessun testo delle frasi nell'uscita", "apri il file" not in t
                 and "di mezzo una foto" not in t, t)

        class Cfg:
            turn_log_dir = d
            attrito_avviso = 3.0
        a = attrito.avviso_recente(Cfg(), datetime.date(2026, 10, 8))
        verifica("stato: avviso di ieri all'avvio", a is not None and "del 2026-10-07" in a, a)
        verifica("stato: nessun avviso con un registro che non c'è", attrito.avviso_recente(
            type("C", (), {"turn_log_dir": d + "_no"})()) is None)
        src = (Path(__file__).resolve().parent.parent / "calliope" / "stato.py").read_text("utf-8")
        verifica("stato: `calliope stato --turni` stampa l'attrito", "attrito.testo(" in src
                 and "attrito.avviso_recente(" in src)


if __name__ == "__main__":
    prova_conti()
    prova_avviso()
    prova_ombra()
    prova_stato()
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)
