"""La città della casa, le estensioni prima di internet e le notizie per tema, con il modello vero
della voce (Ollama locale, `llm_model`) e il docker FINTO (09/10/2026, casi veri della DGX con
nomi di fantasia: la casa è a Borgoverde).

1. «Che tempo fa?» senza città, con l'estensione «Meteo città» attiva (input città, giorni,
   paese, come sulla DGX) e `casa_citta: Borgoverde` → l'estensione con Borgoverde, non
   web_cerca. Contrari: «Che tempo fa a Parigi?» (mai Borgoverde), «Che tempo fa da Ettore?»
   (una persona, non una città: mai Borgoverde come se fosse il posto di Ettore).
2. La stessa casa senza l'estensione (disattivata) → web_cerca con Borgoverde nella domanda;
   «Che tempo fa a Parigi?» → Parigi.
3. Senza `casa_citta` (il confronto, com'era prima): si conta e basta.
4. Le notizie: «Sentimi le notizie di sport» → web_cerca tipo notizie con «sport» (la domanda
   del modello e quella che esce davvero, dopo servizio.tema_notizie); «Dimmi le ultime
   notizie»; «Che notizie ci sono su Torino?».

Fallisce se, con città ed estensione, «Che tempo fa?» non va all'estensione con Borgoverde
almeno 2 volte su 3; se senza estensione non va a internet con Borgoverde almeno 2 su 3; se un
contrario prende Borgoverde; se «le notizie di sport» non esce con «sport» almeno 2 su 3.
`CALLIOPE_RADICE`: un'altra copia del codice (il confronto con main).

    python prove\\prova_citta_casa_ollama.py      # 3 ripetizioni per frase
    python prove\\prova_citta_casa_ollama.py 1    # 1 ripetizione
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
from calliope.tools.spec import ToolSpec  # noqa: E402
from calliope.tools.web import web_spec  # noqa: E402

try:
    from calliope.web.servizio import tema_notizie
except ImportError:                       # main prima del 09/10: la domanda esce com'è
    def tema_notizie(q):
        return q

RIPETI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 3
CITTA = "Borgoverde"
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


METEO = P.manifesto(
    "meteo_codifica_citta", "Meteo città",
    "Dice il meteo di una città per i prossimi giorni.",
    input_={"type": "object", "properties": {
        "citta": {"type": "string", "description": "nome della città"},
        "giorni": {"type": "integer", "description": "quanti giorni di previsione, da 1 a 7"},
        "paese": {"type": "string", "description": "sigla del paese, per esempio IT"}},
        "required": ["citta"]},
    permessi={"rete": {"pubblica": True, "host": ["api.open-meteo.com"]}})
CODICE = '''
def esegui(dati, calliope):
    c = str(dati.get("citta") or "")
    return {"da_dire": "A " + c + ": cielo nuvoloso, 17 gradi, domani pioggia debole."}
'''


class Voce:
    def __init__(self, nome, livello, come="voce"):
        self.current_speaker, self.current_level, self.identified_by = nome, livello, come
        self.profile_level, self.from_session = livello, False
        self.sfida, self.sfida_superata, self.conferma_breve = None, False, False


def ambiente(tmp, iso, chiamate, citta, estensione):
    cfg, reg, ctx, est, casa, liste = P.ambiente(tmp, iso)
    if citta:
        cfg.casa_citta = citta
    vista = web_spec(cfg)

    def cerca(ctx, domanda="", tipo="web"):
        chiamate.append(("web_cerca", {"domanda": domanda, "tipo": tipo,
                                       "esce": tema_notizie(domanda) if tipo == "notizie"
                                       else domanda}))
        if tipo == "notizie":
            return {"ok": True, "trovato": True, "risultati": [
                {"sito": "ANSA", "titolo": "Serie A, il Napoli vince a Lecce",
                 "testo": "Il Napoli batte il Lecce 2 a 1 nell'anticipo di ieri."}],
                "cosa_fare": "Rispondi in 1–3 frasi citando il sito per nome."}
        return {"ok": True, "trovato": True, "risultati": [
            {"sito": "iLMeteo", "titolo": "Meteo", "testo": "Oggi pioggia debole, 15-19 gradi."}],
            "cosa_fare": "Rispondi in 1–3 frasi citando il sito per nome."}
    reg.register(ToolSpec(**{**vista.__dict__, "func": cerca}))
    if estensione:
        P.installa(est, METEO, CODICE)
        spec = reg.get("est_meteo_codifica_citta")
        vera = spec.func

        def usa(ctx, **kw):
            chiamate.append(("est_meteo_codifica_citta", dict(kw)))
            return vera(ctx, **kw)
        reg.register(ToolSpec(**{**spec.__dict__, "func": usa}))
    return cfg, reg, ctx


def parla(cfg, reg, ctx, chiamate, frase, b=None):
    """Una frase; con `b` nella stessa conversazione (il turno dopo una ricerca)."""
    chiamate.clear()
    voce = Voce("Dario", "amministra")
    ctx.speaker_ctx = voce
    b = b or Brain(cfg, reg, ctx)
    t0 = time.perf_counter()
    risposta = "".join(b.stream_reply(frase, "amministra")).strip()
    return risposta, list(chiamate), time.perf_counter() - t0


def con_citta(args) -> bool:
    return CITTA.lower() in json.dumps(args, ensure_ascii=False).lower()


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-citta-casa-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    conti: dict = {}

    def conta(chiave, ok):
        c = conti.setdefault(chiave, [0, 0])
        c[0] += bool(ok)
        c[1] += 1

    scenari = [
        ("città+estensione", CITTA, True, [
            ("Che tempo fa?", "meteo_casa_est"), ("Che tempo farà domani?", "meteo_casa_est"),
            ("Che tempo fa a Parigi?", "parigi"), ("Che tempo fa da Ettore?", "ettore")]),
        ("città, senza estensione", CITTA, False, [
            ("Che tempo fa?", "meteo_casa_web"), ("Che tempo fa a Parigi?", "parigi"),
            ("Sentimi le notizie di sport.", "notizie_sport"),
            ("Dimmi le ultime notizie.", "notizie"),
            ("Che notizie ci sono su Torino?", "notizie_torino")]),
        ("senza città, estensione", "", True, [("Che tempo fa?", "senza_citta")]),
        # Nella stessa conversazione, subito dopo una ricerca (09/10: il turno dopo una ricerca
        # ha RICERCA_MSG nei dati del turno, «chiama di nuovo web_cerca se vuole approfondire»).
        # Con l'estensione si conta soltanto: un'estensione che legge internet è un'«azione» per
        # la politica (estensioni/servizio._agisce) e con un risultato web nella conversazione
        # «Che tempo fa?» non la chiede (politica_azione_non_chiesta); il 4B allora inventa il
        # meteo. Problema della politica, non del prompt (docs/aree/voce-e-regole.md, 09/10)
        ("dopo le notizie, estensione", CITTA, True, [
            ("Sentimi le notizie di sport.", "notizie_sport"), ("Che tempo fa?", "meteo_casa_est")]),
        ("dopo le notizie, senza estensione", CITTA, False, [
            ("Sentimi le notizie di sport.", "notizie_sport"), ("Che tempo fa?", "meteo_casa_web")]),
    ]
    for etichetta, citta, est, frasi in scenari:
        for i in range(RIPETI):
            chiamate: list = []
            cfg, reg, ctx = ambiente(tmp0 / f"{etichetta[:5]}{i}".replace(" ", "_")
                                     .replace(",", "").replace("+", "_"), iso, chiamate,
                                     citta, est)
            stessa = Brain(cfg, reg, ctx) if etichetta.startswith("dopo") else None
            for frase, chiave in frasi:
                r, ch, s = parla(cfg, reg, ctx, chiamate, frase, stessa)
                nomi = [n for n, _ in ch]
                args = [a for _, a in ch]
                if chiave == "meteo_casa_est":
                    ok = (any(n.startswith("est_") and con_citta(a) for n, a in ch)
                          and "web_cerca" not in nomi)
                elif chiave == "meteo_casa_web":
                    ok = any(n == "web_cerca" and con_citta(a) for n, a in ch)
                elif chiave == "parigi":
                    ok = (not any(con_citta(a) for a in args)
                          and any("parigi" in json.dumps(a).lower() for a in args))
                    conta(f"{etichetta}|parigi_mai_casa", not any(con_citta(a) for a in args))
                elif chiave == "ettore":
                    ok = not any(con_citta(a) for a in args)
                elif chiave == "notizie_sport":
                    ok = any(n == "web_cerca" and a.get("tipo") == "notizie"
                             and "sport" in a.get("esce", "").lower() for n, a in ch)
                    conta(f"{etichetta}|notizie_sport_esce_solo_tema", any(
                        n == "web_cerca" and "notizi" not in a.get("esce", "").lower()
                        for n, a in ch))
                    # La città della casa non serve alle notizie di sport (si conta)
                    conta(f"{etichetta}|notizie_sport_senza_casa",
                          not any(con_citta(a) for a in args))
                elif chiave == "notizie":
                    ok = any(n == "web_cerca" and a.get("tipo") == "notizie" for n, a in ch)
                elif chiave == "notizie_torino":
                    ok = any(n == "web_cerca" and "torino" in a.get("esce", "").lower()
                             for n, a in ch)
                else:                       # senza città: si conta (com'era prima)
                    ok = True
                    conta(f"{etichetta}|web", "web_cerca" in nomi)
                    conta(f"{etichetta}|estensione", any(n.startswith("est_") for n in nomi))
                    conta(f"{etichetta}|chiede_la_città", not ch)
                conta(f"{etichetta}|{chiave}", ok)
                print(f"{'ok ' if ok else '-- '} [{etichetta} {i + 1}] «{frase}» → "
                      f"{json.dumps(ch, ensure_ascii=False)[:220]}  {s:.1f}s {r[:120]!r}",
                      flush=True)
    print("\nRiepilogo (riuscite / casi):")
    for k, (a, n) in sorted(conti.items()):
        print(f"  {k:55} {a}/{n}")

    def quota(chiave, minimo):
        a, n = conti.get(chiave, [0, 0])
        return n and a * 3 >= n * minimo, f"{a}/{n}"
    for chiave, descr in (("città+estensione|meteo_casa_est",
                           "«che tempo fa?» con città ed estensione → l'estensione con la città"),
                          ("città, senza estensione|meteo_casa_web",
                           "«che tempo fa?» senza estensione → internet con la città"),
                          ("città, senza estensione|notizie_sport",
                           "«le notizie di sport» → notizie con «sport»"),
                          ("dopo le notizie, senza estensione|meteo_casa_web",
                           "dopo le notizie, «che tempo fa?» → internet con la città")):
        ok, det = quota(chiave, 2)
        verifica(descr + " (almeno 2 su 3)", ok, det)
    for chiave, descr in (("città+estensione|parigi_mai_casa", "Parigi mai Borgoverde (estensione)"),
                          ("città, senza estensione|parigi_mai_casa", "Parigi mai Borgoverde (web)"),
                          ("città+estensione|ettore", "«da Ettore» mai Borgoverde")):
        a, n = conti.get(chiave, [0, 0])
        verifica("contrario: " + descr, a == n, f"{a}/{n}")
    print(json.dumps({k: v for k, v in conti.items()}, ensure_ascii=False))
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
