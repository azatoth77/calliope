"""L'estensione nominata a voce, con il modello vero della voce (Ollama locale, `llm_model`) e il
docker FINTO (08/10/2026, giro 10: caso vero della DGX del 07/10 col 26B, nomi di fantasia).

C'è «Meteo per città» (versione 2 di meteo_citta, approvata adesso: dice il meteo di una città,
input `citta`) e c'è `web_cerca` (finto, con la sua descrizione vera: «meteo e previsioni»).

- conversazione pulita: «Usa l'estensione meteo per città per Bergamo» → est_meteo_citta;
  «Che tempo fa a Bergamo?» → l'estensione o internet, vanno bene tutti e due (si conta);
- la conversazione della DGX: prima Calliope ha detto tre volte che l'estensione «è configurata
  solo per Borgoverde e Valfiorita» e che per Bergamo serve internet; poi la persona approva la
  versione 2 (con il modello e la frase di sfida) e chiede «invoca l'estensione meteo per città
  su Bergamo», poi «Non devi guardare su internet…» → est_meteo_citta, mai web_cerca.

Ogni giro due volte: con i dati del turno EST_NOMINATA_MSG e con la rete `estensione_nominata`
spenta (il confronto). Fallisce se con i dati del turno la persona che nomina l'estensione non
la ottiene almeno 2 volte su 3 a giro nella conversazione pulita, o mai nella conversazione
della DGX. La seconda frase della DGX («Non devi guardare su internet…») solo se la prima è
andata su internet. `CALLIOPE_RADICE`: un'altra copia del codice (il confronto con main).

    python prove\\prova_estensione_nominata_ollama.py      # 2 giri
    python prove\\prova_estensione_nominata_ollama.py 1    # 1 giro
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

_RADICE = os.environ.get("CALLIOPE_RADICE") or os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
sys.path.insert(0, _RADICE)
sys.path.insert(0, os.path.join(_RADICE, "prove"))

import prova_estensioni as P  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.tools.estensioni import estensioni_specs  # noqa: E402
from calliope.tools.spec import ToolSpec  # noqa: E402
from calliope.tools.web import web_spec  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
# --tutti: anche gli altri tool di Calliope (casa, archivio, agenti, PC, documenti: ~50 schemi
# come sulla DGX), con funzioni che non fanno niente
TUTTI = "--tutti" in sys.argv
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


M1 = P.manifesto("meteo_citta", "Meteo Borgoverde e Valfiorita",
                 "Dice il meteo attuale a Borgoverde e Valfiorita.",
                 permessi={"rete": {"pubblica": True, "host": ["api.open-meteo.com"]}})
M2 = P.manifesto("meteo_citta", "Meteo per città", "Dice il meteo attuale in una città.",
                 input_={"type": "object", "properties": {"citta": {
                     "type": "string", "description": "nome della città per cui chiedere il "
                                                      "meteo"}}, "required": ["citta"]})
CODICE = '''
def esegui(dati, calliope):
    c = str(dati.get("citta") or "Borgoverde")
    return {"da_dire": "A " + c + ": cielo nuvoloso, 17 gradi, umidità al 80%."}
'''
STORIA_DGX = [
    ("user", "Attiva l'estensione Meteocittà."),
    ("assistant", "Fatto: «Meteo Borgoverde e Valfiorita» è di nuovo attiva."),
    ("user", "Io voglio l'estensione. Come posso richiamare l'azione di invocare l'estensione?"),
    ("assistant", "Per invocare l'estensione basta che tu mi chieda il meteo di una città "
                  "specifica. Se vuoi usare i dati dell'estensione che abbiamo appena attivato, "
                  "ti basterà chiedermi il meteo di Borgoverde o di Valfiorita."),
    ("user", "Ok, allora io vorrei che tu attivassi l'estensione per il meteo nella città di "
             "Bergamo."),
    ("assistant", "Mi piacerebbe poterti dare il meteo di Bergamo con l'estensione, ma quella è "
                  "configurata solo per Borgoverde e Valfiorita. Per Bergamo dovrò cercare sul "
                  "web. Vuoi che proceda?"),
    ("user", "Calliope, forse non ci capiamo: hai due versioni, quella attiva e quella nuova del "
             "meteo da approvare, corretto?"),
    ("assistant", "Esatto: «Meteo Borgoverde e Valfiorita» è attiva, e c'è una sua versione "
                  "nuova in attesa di essere approvata."),
]


class Voce:
    def __init__(self, nome, livello, come="voce"):
        self.current_speaker, self.current_level, self.identified_by = nome, livello, come
        self.profile_level, self.from_session = livello, False
        self.sfida, self.sfida_superata, self.conferma_breve = None, False, False


def parla(b, voce, frase):
    voce.sfida_superata = voce.conferma_breve = False
    b.tool_ctx.speaker_ctx = voce
    t0 = time.perf_counter()
    risposta = "".join(b.stream_reply(frase, voce.current_level)).strip()
    return risposta, [t["nome"] for t in b.last_tools], time.perf_counter() - t0


def ambiente(tmp, iso, web):
    cfg, reg, ctx, est, casa, liste = P.ambiente(tmp, iso)
    for s in estensioni_specs(crea=False):
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
            {"sito": "iLMeteo", "titolo": "Meteo Bergamo", "testo": "A Bergamo oggi pioggia "
                                                                    "debole, 15-19 gradi."}],
            "cosa_fare": "Rispondi in 1–3 frasi citando il sito per nome."}
    reg.register(ToolSpec(**{**vista.__dict__, "func": cerca}))
    P.installa(est, M1, CODICE)
    mv = P.valida(M2)
    est.archivio.nuova_candidata(mv, {"estensione.py": CODICE.encode()}, "Dario",
                                 {"eseguiti": 11}, {"rischi": [], "sintassi": []}, "L1", True)
    return cfg, reg, ctx, est


def sessione(giro, tmp, iso, spenta: bool, conteggi: dict):
    etichetta = "rete spenta" if spenta else "dati del turno"
    web = []
    cfg, reg, ctx, est = ambiente(tmp, iso, web)
    if spenta:
        cfg.llm_reti_spente = ["estensione_nominata"]
    dario = Voce("Dario", "amministra")

    def conta(chiave, ok):
        c = conteggi.setdefault((etichetta, chiave), [0, 0])
        c[0] += bool(ok)
        c[1] += 1

    # 1. La conversazione della DGX, poi l'approvazione con il modello e la sfida
    b = Brain(cfg, reg, ctx)
    b.history = [{"role": r, "content": t} for r, t in STORIA_DGX]
    r, tools, s = parla(b, dario, "Sì, voglio che la approvi, ma voglio che la approvi nella "
                                  "nuova versione.")
    if dario.sfida is not None:
        parole = dario.sfida.testo.replace(",", "")
        r2, _, _ = parla(b, dario, parole)
    else:
        # Il modello non ha chiamato estensione_gestisci: approvata dal codice (si dice)
        print(f"   [{giro}/{etichetta}] il modello non ha chiesto l'approvazione: {tools} "
              f"{r[:100]!r}", flush=True)
        est.archivio.approva("meteo_citta", 2, "Dario")
        est.aggiorna_tool()
    verifica(f"[{giro}/{etichetta}] versione 2 approvata",
             est.archivio.voce("meteo_citta")["attiva"] == 2)
    # La seconda frase della DGX solo se la prima non ha usato l'estensione (com'è andata
    # sulla DGX): dopo una risposta giusta «non devi guardare su internet» non ha senso
    for i, frase in enumerate((
            "Perfetto, ora vorrei che tu invocassi l'estensione meteo per città e la "
            "ricercassi su Bergamo.",
            "Non devi guardare su internet, devi fare quello che ti ho chiesto. Invoca "
            "l'estensione Meteo per città su Bergamo.")):
        r, tools, s = parla(b, dario, frase)
        ok = "est_meteo_citta" in tools and "web_cerca" not in tools
        conta("nominata_dgx" if i == 0 else "nominata_dgx_dopo_web", ok)
        print(f"{'ok ' if ok else '-- '} [{giro}/{etichetta}] DGX: «{frase[:60]}…» → "
              f"{', '.join(tools) or '—'}  {s:.1f}s {r[:110]!r}", flush=True)
        if ok:
            break
    # 2. Conversazione pulita
    for frase, chiave in (("Usa l'estensione meteo per città per Bergamo.", "nominata"),
                          ("Calliope, usa meteo per città per Valfiorita.", "nominata"),
                          ("Invoca l'estensione meteo per città su Torino.", "nominata"),
                          ("Che tempo fa a Bergamo?", "libera")):
        b = Brain(cfg, reg, ctx)
        r, tools, s = parla(b, dario, frase)
        if chiave == "nominata":
            ok = "est_meteo_citta" in tools and "web_cerca" not in tools
            conta("nominata", ok)
        else:
            ok = any(t in tools for t in ("est_meteo_citta", "web_cerca"))
            conta("libera_estensione", "est_meteo_citta" in tools)
            conta("libera_web", "web_cerca" in tools)
        print(f"{'ok ' if ok else '-- '} [{giro}/{etichetta}] pulita: «{frase}» → "
              f"{', '.join(tools) or '—'}  {s:.1f}s {r[:110]!r}", flush=True)


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-est-nominata-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    conteggi: dict = {}
    for giro in range(1, GIRI + 1):
        for spenta in (False, True):
            sessione(giro, tmp0 / f"g{giro}{'s' if spenta else ''}", iso, spenta, conteggi)
    print("\nRiepilogo (riuscite / casi):")
    for (etichetta, chiave), (k, n) in sorted(conteggi.items()):
        print(f"  {etichetta:15} {chiave:18} {k}/{n}")
    k, n = conteggi.get(("dati del turno", "nominata"), [0, 1])
    k2, n2 = conteggi.get(("dati del turno", "nominata_dgx"), [0, 1])
    verifica("con i dati del turno: l'estensione nominata la si ottiene (conversazione pulita, "
             "almeno 2 su 3 a giro)", k >= 2 * GIRI, f"{k}/{n}")
    verifica("con i dati del turno: nella conversazione della DGX, dopo l'approvazione (almeno "
             "una volta su due giri)", k2 >= (GIRI + 1) // 2, f"{k2}/{n2}")
    print(json.dumps({f"{a}|{b}": v for (a, b), v in conteggi.items()}, ensure_ascii=False))
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
