"""La modalità sviluppo con il modello vero della voce (Ollama locale, `llm_model`), il docker
FINTO e un servizio dei lavori finto (08/10/2026; la sessione del meteo per città della DGX del
07/10 sera, riscritta come iter, nomi di fantasia).

C'è «Meteo Borgoverde e Valfiorita» (città fisse). Dario, con la voce:
 1. «Voglio un'estensione che mi dica il meteo di una città qualunque…» → sviluppo_apri
    (apre lo sviluppo) e «Procedo?»;
 2. «Sì, procedi.» → il lavoro parte (sviluppo);
 3. «Che ore sono?» → risponde e resta in modalità (la riga che ricorda dove eravamo, del
    modello o del codice);
    … il lavoro finisce (finto): l'annuncio, collaudo;
 4. «Prova con Bergamo.» → sviluppo_collauda, mai est_ né internet;
 5. «Prova una città che non esiste, tipo Atlantide.» → sviluppo_collauda;
 6. «Aggiungi il latte alla lista della spesa.» → lista_aggiungi, e lo sviluppo resta al collaudo;
 7. «Fammi anche un'estensione che converte le valute.» → nessun lavoro nuovo (o rifiutato dal
    codice, o il modello propone di sospendere);
 8. «Anzi, torniamo all'analisi: se la città non esiste deve dirmi che non l'ha trovata.» →
    sviluppo analisi con cambia; «Sì.» → di nuovo allo sviluppo;
    … il lavoro finisce di nuovo: collaudo;
 9. «Va bene, andiamo avanti.» → revisione;
10. «Attivala.» → la frase di sfida; detta → attiva e sviluppo chiuso.

Ogni giro due volte: con i dati del turno (SVILUPPO_MSG) e con la rete `modalita_sviluppo`
spenta (il confronto: lo stato c'è, il modello non lo sa). Si contano i passi giusti; fallisce
se con i dati del turno il collaudo (4) non va almeno 2 volte su 3 a giro o l'iter non arriva
mai all'attivazione.

    python prove\\prova_sviluppo_ollama.py      # 2 giri
    python prove\\prova_sviluppo_ollama.py 1    # 1 giro
    python prove\\prova_sviluppo_ollama.py 1 --tutti   # con tutti i tool di Calliope
"""

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RADICE)
sys.path.insert(0, os.path.join(_RADICE, "prove"))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.tools.agenti import agenti_specs  # noqa: E402
from calliope.tools.spec import ToolSpec  # noqa: E402
from calliope.tools.web import web_spec  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
# --tutti: anche gli altri tool di Calliope (casa, archivio, PC, documenti: ~60 schemi come sulla
# DGX), con funzioni che non fanno niente
TUTTI = "--tutti" in sys.argv
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


class Voce:
    def __init__(self, nome, livello, come="voce"):
        self.current_speaker, self.current_level, self.identified_by = nome, livello, come
        self.profile_level, self.from_session = livello, False
        self.sfida, self.sfida_superata, self.conferma_breve = None, False, False
        self.voce_sicura, self.punteggio = nome, 0.7


def parla(b, voce, frase):
    voce.sfida_superata = voce.conferma_breve = False
    b.tool_ctx.speaker_ctx = voce
    t0 = time.perf_counter()
    pezzi, prima = [], None
    for p in b.stream_reply(frase, voce.current_level):
        if prima is None and p.strip():
            prima = time.perf_counter() - t0
        pezzi.append(p)
    return "".join(pezzi).strip(), [t["nome"] for t in b.last_tools], prima or 0.0


def ambiente(tmp, iso, web):
    cfg, reg, ctx, est, svc = S.ambiente(tmp, iso)
    for s in agenti_specs():
        reg.register(s)
    if TUTTI:
        from calliope.tools.builtin import build_registry
        from pc_finto import FakePC
        pieno = build_registry(casa=True, web=True, archivio=True, agenti=True,
                               pc={"portatile": FakePC()}, documenti=("word", "pdf"))
        for sch in pieno.all_schemas():
            nome = sch["function"]["name"]
            if reg.get(nome) is None:
                spec = pieno.get(nome)
                reg.register(ToolSpec(**{**spec.__dict__, "func": lambda ctx, **a: {
                    "ok": False, "errore": "non disponibile in questa prova"}}))
    vista = web_spec(cfg)

    def cerca(ctx, domanda="", tipo="web"):
        web.append(domanda)
        return {"ok": True, "trovato": True, "risultati": [
            {"sito": "iLMeteo", "titolo": "Meteo", "testo": "Oggi pioggia debole, 15-19 gradi."}],
            "cosa_fare": "Rispondi in 1–3 frasi citando il sito per nome."}
    reg.register(ToolSpec(**{**vista.__dict__, "func": cerca}))
    reg.register(ToolSpec("ora_attuale", "Dice l'ora attuale.", {"type": "object",
                                                                 "properties": {}},
                          lambda c, **a: {"ok": True, "conferma": "Sono le 18:30."},
                          levels=frozenset({"ospite", "familiare", "amministra"})))
    P.installa(est, S.M1, S.CODICE1)
    return cfg, reg, ctx, est, svc


def finisci(est, svc, codice=S.CODICE2):
    """Il lavoro in corso dello sviluppo finisce (finto): la versione candidata, l'annuncio."""
    sv = svc.sviluppi.corrente("u1")
    lav = next((lv for lv in reversed(svc.lavori) if lv.id == getattr(sv, "lavoro", None)),
               None)
    if sv is None or lav is None:
        return None
    nome = lav.estensione or "meteo_ovunque"
    m = dict(S.M2, nome=nome)
    mv = P.valida(m)
    n = est.archivio.nuova_candidata(mv, {"estensione.py": codice.encode()}, "Dario",
                                     {"eseguiti": 6, "falliti": 0},
                                     {"rischi": [], "sintassi": []}, lav.id, True)
    lav.estensione = nome
    return svc.finisci(lav, "fatto", estensione={"nome": nome, "versione": n},
                       messaggio="Dario, ho preparato l'estensione «Meteo per città»: dice il "
                                 "meteo attuale in una città. Permessi: legge pagine pubbliche "
                                 "di internet; i test passano, 6 su 6. Vuoi approvarla?")


def sessione(giro, tmp, iso, spenta: bool, conteggi: dict, tempi: list):
    etichetta = "rete spenta" if spenta else "dati del turno"
    web = []
    cfg, reg, ctx, est, svc = ambiente(tmp, iso, web)
    svs = svc.sviluppi
    if spenta:
        cfg.llm_reti_spente = ["modalita_sviluppo"]
    dario = Voce("Dario", "amministra")
    b = Brain(cfg, reg, ctx)
    b.conv_owner = "u1"

    def passo(n, frase, giusto, descr):
        r, tools, s = parla(b, dario, frase)
        tempi.append(s)
        sv = svs.corrente("u1")
        ok = bool(giusto(r, tools, sv))
        c = conteggi.setdefault((etichetta, f"{n:02d} {descr}"), [0, 0])
        c[0] += ok
        c[1] += 1
        print(f"{'ok ' if ok else '-- '} [{giro}/{etichetta}] {n}. «{frase[:55]}» → "
              f"{', '.join(tools) or '—'} [{getattr(sv, 'fase', '—')}] {s:.1f}s {r[:150]!r}",
              flush=True)
        return r, tools, sv

    def annuncia():
        item = finisci(est, svc)
        if item is not None:
            b.record_announcement(item["messaggio"], pending=item.get("in_sospeso"),
                                  fonte="agente")
        return item

    passo(1, "Voglio un'estensione che mi dica il meteo di una città qualunque, non solo di "
             "Borgoverde e Valfiorita.",
          lambda r, t, sv: "sviluppo_apri" in t and sv is not None and sv.fase == "analisi",
          "richiesta → sviluppo aperto")
    passo(2, "Sì, procedi.",
          lambda r, t, sv: sv is not None and sv.fase == "sviluppo", "sì → sviluppo")
    sv = svs.corrente("u1")
    if sv is not None and sv.fase == "analisi" and sv.proposto:
        # Il 4B a volte risponde alla prima richiesta senza chiamare il tool, e lo chiama al
        # «sì»: la proposta arriva un turno dopo (prima dello sviluppo, uguale con e senza)
        passo(2, "Sì.", lambda r, t, sv: sv is not None and sv.fase == "sviluppo",
              "sì → sviluppo (proposta arrivata tardi)")
        sv = svs.corrente("u1")
    if sv is not None and sv.tipo != "estensione":
        # Il 4B a volte chiede l'estensione con lavoro_affida di codice («Crea un'estensione
        # che…»): è uno sviluppo di un programma, e il resto dell'iter non vale per questa prova
        print(f"   [{giro}/{etichetta}] aperto lo sviluppo di un PROGRAMMA: il giro finisce",
              flush=True)
        c = conteggi.setdefault((etichetta, "00 giri finiti come programma"), [0, 0])
        c[0] += 1
        c[1] += 1
        return
    passo(3, "Che ore sono?",
          lambda r, t, sv: re.search(r"\d{1,2}[:.]\d{2}", r) and sv is not None
          and sv.fase == "sviluppo" and ("svilupp" in r.lower() or sv.titolo.lower()
                                         in r.lower()), "fuori tema, resta e lo dice")
    if annuncia() is None:
        # Il lavoro non è partito: l'iter si ferma qui per questo giro (contato come errore)
        print(f"   [{giro}/{etichetta}] nessun lavoro dello sviluppo: il giro finisce", flush=True)
        return
    passo(4, "Prova con Bergamo.",
          lambda r, t, sv: "sviluppo_collauda" in t and "web_cerca" not in t
          and not any(x.startswith("est_") for x in t) and "Bergamo" in r, "collaudo Bergamo")
    passo(5, "Prova una città che non esiste, tipo Atlantide.",
          lambda r, t, sv: "sviluppo_collauda" in t and "web_cerca" not in t,
          "collaudo città inesistente")
    passo(6, "Aggiungi il latte alla lista della spesa.",
          lambda r, t, sv: "lista_aggiungi" in t and sv is not None and sv.fase == "collaudo",
          "fuori tema con un'azione")
    n_lavori = len(svc.lavori) + len(svc.offerte)
    passo(7, "Fammi anche un'estensione che converte le valute.",
          lambda r, t, sv: len(svc.lavori) + len(svc.offerte) == n_lavori and sv is not None
          and sv.fase == "collaudo" and "C'è di mezzo" not in r, "sviluppo nuovo non parte")
    svc.offerte.clear()
    passo(8, "Anzi, torniamo all'analisi: se la città non esiste deve dirmi che non l'ha "
             "trovata.",
          lambda r, t, sv: sv is not None and sv.fase == "analisi" and sv.proposto,
          "ritorno all'analisi")
    passo(9, "Sì.", lambda r, t, sv: sv is not None and sv.fase == "sviluppo",
          "sì → di nuovo sviluppo")
    annuncia()
    passo(10, "Va bene, andiamo avanti.",
          lambda r, t, sv: sv is not None and sv.fase == "revisione" and "Permessi" in r,
          "avanti → revisione")
    r, t, sv = passo(11, "Attivala.",
                     lambda r, t, sv: dario.sfida is not None and "ripeti" in r.lower(),
                     "attivala → sfida")
    if dario.sfida is not None:
        parole = dario.sfida.testo.replace(",", "")
        passo(12, parole, lambda r, t, sv: sv is None and any(
            s.motivo == "attivata" for s in svs.sviluppi), "sfida → attiva, chiuso")


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-sviluppo-ollama-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    conteggi: dict = {}
    tempi = {"dati del turno": [], "rete spenta": []}
    for giro in range(1, GIRI + 1):
        for spenta in (False, True):
            et = "rete spenta" if spenta else "dati del turno"
            sessione(giro, tmp0 / f"g{giro}{'s' if spenta else ''}", iso, spenta, conteggi,
                     tempi[et])
    print("\nRiepilogo (riusciti / casi):")
    for (etichetta, chiave), (k, n) in sorted(conteggi.items()):
        print(f"  {etichetta:15} {chiave:40} {k}/{n}")
    for et, t in tempi.items():
        if t:
            t = sorted(t)
            print(f"  prima frase, {et}: mediana {t[len(t) // 2]:.2f} s, massimo {t[-1]:.2f} s "
                  f"({len(t)} turni)")
    k, n = conteggi.get(("dati del turno", "04 collaudo Bergamo"), [0, 1])
    k2, n2 = conteggi.get(("dati del turno", "12 sfida → attiva, chiuso"), [0, 1])
    verifica("con i dati del turno: il collaudo con sviluppo_collauda (almeno 2 volte su 3)",
             k * 3 >= n * 2, f"{k}/{n}")
    verifica("con i dati del turno: l'iter arriva all'attivazione almeno una volta", k2 >= 1,
             f"{k2}/{n2}")
    print(json.dumps({f"{a}|{b}": v for (a, b), v in conteggi.items()}, ensure_ascii=False))
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
