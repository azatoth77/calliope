"""Banco dei risultati della ricerca fuori tema, col modello vero (16/10/2026, issue #101).

Brain vero con web_cerca, biblioteca_cerca e notizie, ricerca e biblioteca finte (risultati
scritti qui, nomi di fantasia), chi amministra che parla. Tre scenari dai casi veri della DGX del
15/10 sera, `--giri` volte ciascuno:

- `fuori`: dopo il mito di Orione cercato nella biblioteca, «Approfondiamo questo argomento»;
  qualunque ricerca dà risultati fuori tema (una startup dal nome simile su internet, voci
  omonime nella biblioteca). Riuscito: dice che su quello non ha trovato niente (anche
  nominando ciò che è uscito) o chiede cosa cercare senza riferirli. Senza nessuna ricerca il
  giro si conta a parte («senza ricerca»).
- `dentro` (il contrario): gli stessi turni, risultati sul mito. Riuscito: li riferisce (un nome
  dei risultati nella risposta) e non dice che non ha trovato niente.
- `notizie`: le notizie sullo sciopero dei treni lette tre turni prima (nella storia restano
  solo titoli e testate, e la risposta di allora non diceva chi), poi «Chi ha detto che è
  possibile la precettazione?». Riuscito: richiama `notizie` invece di rispondere a memoria;
  «no» se dice una persona (inventata: nei dati rimasti non c'è), «a memoria» a parte se
  risponde con le testate e il titolo rimasti.

Criterio della issue: `fuori` ≥ 9/10, `dentro` ≥ 9/10, `notizie` ≥ 9/10.

Col 26B sulla DGX (il profilo della voce dal file locale), a Calliope inattiva:

    cd ~/calliope && V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale) \\
        && $V/.venv/bin/python $V/prove/manuali/banco_ricerca_fuori_tema.py --giri 10

Con un Ollama di prova (`--url`, e `--num-ctx` uguale a quello del modello già caricato):

    python prove\\manuali\\banco_ricerca_fuori_tema.py --url http://127.0.0.1:11434 --giri 3

Prima e dopo: lo stesso file lanciato dalla cartella di main misura i testi di prima (non usa
niente di nuovo). Non scrive niente su disco.
"""

import argparse
import json
import os
import re
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from calliope import politica, provenienza  # noqa: E402
from calliope.brain import Brain  # noqa: E402
from calliope.config import load_config  # noqa: E402
from calliope.tools.builtin import build_registry  # noqa: E402
from calliope.tools.spec import ToolContext  # noqa: E402


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin
        self.preferred_voice = self.nascita = self.fascia = self.tono = None
        self.preferred_tone = None
        self.tutori = []


class Persone:
    P = {"Carlo": Prof("carlo-id", "Carlo", True)}

    def get(self, n):
        return self.P.get(n)

    def known_speakers(self):
        return list(self.P)


class Chi:
    current_speaker, current_level, identified_by = "Carlo", "amministra", "voce"
    from_session = False
    sfida = incerta = minore_vicino = None
    voce_sicura, conferma_breve, sfida_superata = "Carlo", False, False
    compagnia = compagnia_sconosciute = senza_nome = False


STARTUP = [("Orionyx raccoglie 40 milioni", "La startup di modelli linguistici Orionyx annuncia "
            "un nuovo round di finanziamento guidato da fondi americani."),
           ("Orionyx presenta il nuovo modello", "Il modello linguistico open source di Orionyx "
            "supera i concorrenti nei test di programmazione.")]
OMONIMI = [("Orione (nave)", "Orione fu un incrociatore ausiliario della Regia Marina varato nel "
            "1931."), ("Orione (fumetto)", "Personaggio dei fumetti americani creato nel 1971.")]
MITO = [("Orione (mitologia)", "Orione è un gigante cacciatore della mitologia greca, figlio di "
         "Poseidone; Artemide lo amava, e Apollo la ingannò facendoglielo colpire con una "
         "freccia mentre nuotava."),
        ("La costellazione di Orione", "Una delle costellazioni più riconoscibili del cielo "
         "invernale: le stelle più luminose sono Betelgeuse e Rigel, e la cintura ha tre "
         "stelle allineate.")]
# Parole che dicono «li ha riferiti»
FUORI_DETTO = re.compile(r"orionyx|startup|finanziament|incrociator|regia marina|fumett", re.I)
DENTRO_DETTO = re.compile(r"betelgeuse|rigel|artemide|apollo|cintura", re.I)
# Una persona detta a memoria nello scenario delle notizie: nei dati rimasti non c'è nessuno
PERSONA = re.compile(r"ministr|president|sottosegretar|segretari|portavoce|deputat|senator|"
                     r"sindac|Ferri|leader", re.I)
NON_TROVATO = re.compile(r"non (?:ho trovato|trovo|c'è|ci sono|ho niente|riesco a trovare)|"
                         r"niente (?:su|di)|parlano d'altro|non riguardano|non c'entrano", re.I)


class WebFinto:
    def __init__(self, risultati):
        self.risultati = risultati

    def cerca(self, domanda, tipo="web", **kw):
        return {"ok": True, "domanda": domanda, "risultati": [
            SimpleNamespace(sito="Sito di esempio", titolo=t, testo=x, url="https://esempio.it/a",
                            data=None, vecchio=False) for t, x in self.risultati]}


class BibliotecaFinta:
    def __init__(self, passaggi):
        self.passaggi = passaggi

    def cerca(self, domanda, semplice=False):
        return [SimpleNamespace(titolo=t, testo=x, fonte="Wikipedia") for t, x in self.passaggi]

    def richieste(self, q):
        return set()

    def opzioni(self, q):
        return []

    def testo_voce(self, p):
        return p.testo


def _call(i, nome, args):
    return {"id": f"call_{i}", "name": nome, "arguments": args}


def storia_orione(reg):
    """Il mito di Orione cercato nella biblioteca e raccontato (come il 15/10 alle 18:53)."""
    risultato = json.dumps({"ok": True, "trovato": True, "passaggi": [
        {"voce": "Orione (mitologia)", "fonte": "Wikipedia",
         "testo": "Orione è un gigante cacciatore della mitologia greca."}]},
        ensure_ascii=False)
    return [{"role": "user", "content": "Raccontami il mito di Orione"},
            {"role": "assistant", "content": "", "tool_calls": [
                _call(0, "biblioteca_cerca", {"domanda": "mito di Orione"})]},
            {"role": "tool", "name": "biblioteca_cerca", "tool_call_id": "call_0",
             "content": risultato},
            {"role": "assistant", "content": "Secondo Wikipedia, Orione era un gigante cacciatore "
             "della mitologia greca, figlio di Poseidone. Fu ucciso da uno scorpione e Zeus lo "
             "mise tra le stelle come costellazione."}]


def storia_notizie(reg):
    """Le notizie sullo sciopero lette tre turni prima: nella storia la forma ridotta."""
    from calliope.notizie.contesto import riduci
    pieno = json.dumps({"ok": True, "trovato": True, "fatti": [
        {"n": 1, "titolo": "Sciopero dei treni venerdì, possibile la precettazione",
         "testate": ["Il Corriere di Esempio", "Gazzetta di Fantasia"], "quando": "stamattina",
         "sommario": "La ministra Ornella Ferri non esclude la precettazione; i sindacati "
                     "confermano lo stop di 24 ore."},
        {"n": 2, "titolo": "Pendolari, le fasce garantite",
         "testate": ["Il Corriere di Esempio"], "quando": "ieri sera",
         "sommario": "Treni garantiti dalle 6 alle 9 e dalle 18 alle 21."}]},
        ensure_ascii=False)
    fonte = politica.fonte_di("notizie", reg.get("notizie")) or "web"
    ridotto = riduci(provenienza.racchiudi_risultato(fonte, pieno))
    out = [{"role": "user", "content": "Che notizie ci sono sullo sciopero dei treni?"},
           {"role": "assistant", "content": "", "tool_calls": [
               _call(0, "notizie", {"tema": "sciopero treni"})]},
           {"role": "tool", "name": "notizie", "tool_call_id": "call_0", "content": ridotto},
           # Il nome di chi l'ha detto è solo nel sommario, che non c'è più: dirlo a memoria
           # è inventarlo (il 15/10 alle 19:02 un altro politico)
           {"role": "assistant", "content": "Venerdì c'è sciopero dei treni per 24 ore, e il "
            "governo non esclude la precettazione. Ci sono fasce garantite la mattina e la "
            "sera."}]
    for u, a in (("Che ore sono?", "Sono le 19 e 2."), ("Grazie", "Prego!"),
                 ("Metti la musica più bassa", "Non posso farlo da qui.")):
        out += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    return out


def giro(cfg, scenario: str):
    cfg.stanza = "spento"
    reg = build_registry(web=cfg, notizie=cfg, biblioteca=True)
    risultati_web = MITO if scenario == "dentro" else STARTUP
    risultati_bib = MITO if scenario == "dentro" else OMONIMI
    ctx = ToolContext(cfg=cfg, speakers=Persone(), speaker_ctx=Chi(), speaker=None,
                      web=WebFinto(risultati_web), biblioteca=BibliotecaFinta(risultati_bib))
    b = Brain(cfg, reg, ctx)
    if scenario == "notizie":
        b.history = storia_notizie(reg)
        frase = "Chi ha detto che è possibile la precettazione?"
    else:
        b.history = storia_orione(reg)
        frase = "Approfondiamo questo argomento"
    t1 = time.perf_counter()
    primo, parti = None, []
    for pezzo in b.stream_reply(frase, "amministra"):
        if primo is None and pezzo.strip():
            primo = time.perf_counter() - t1
        parti.append(pezzo)
    detto = "".join(parti).strip()
    tool = [t["nome"] for t in (b.last_tools or [])]
    if scenario == "notizie":
        # Senza richiamare: «no» se dice una persona (nei dati non c'è), altrimenti «a memoria»
        # (risponde con le testate e il titolo rimasti, che è vero ma non è il dettaglio)
        if tool[:1] == ["notizie"]:
            esito = "ok"
        else:
            esito = "no" if PERSONA.search(detto) else "a memoria"
    elif scenario == "fuori":
        cercato = any(t in ("web_cerca", "biblioteca_cerca") for t in tool)
        if not cercato:
            esito = "senza ricerca"
        else:
            # Dire che su quello non ha trovato niente vale anche nominando ciò che è uscito
            # («ho trovato solo un incrociatore omonimo: cerco su internet?»); riferirli come
            # risposta no
            esito = ("ok" if NON_TROVATO.search(detto)
                     or ("?" in detto and not FUORI_DETTO.search(detto)) else "no")
    else:
        cercato = any(t in ("web_cerca", "biblioteca_cerca") for t in tool)
        if not cercato:
            esito = "senza ricerca"
        else:
            esito = "ok" if DENTRO_DETTO.search(detto) and not NON_TROVATO.search(detto) else "no"
    return esito, tool, detto, primo, sorted(set(b.rules_fired()) & {
        "ricerca_recente", "ricerca_elenco", "ricerca_fuori_tema", "spinta_ricerca"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--giri", type=int, default=10)
    ap.add_argument("--scenari", default="fuori,dentro,notizie")
    ap.add_argument("--num-ctx", type=int, default=0,
                    help="il num_ctx del modello già caricato (un altro lo fa ricaricare)")
    ap.add_argument("--url", default="", help="un altro Ollama (di prova) al posto di quello "
                                               "del profilo")
    a = ap.parse_args()
    cfg = load_config()
    cfg.online = True
    if a.url:
        cfg.llm_native_url = a.url
    if a.num_ctx:
        cfg.llm_num_ctx = a.num_ctx
    print(f"modello: {cfg.llm_model} ({cfg.llm_backend}, {cfg.llm_native_url})", flush=True)
    riepilogo = {}
    for scenario in a.scenari.split(","):
        conti = {}
        for n in range(a.giri):
            esito, tool, detto, primo, regole = giro(cfg, scenario)
            conti[esito] = conti.get(esito, 0) + 1
            print(f"[{scenario} {n + 1}] {esito:13} tool={tool} regole={regole} "
                  f"prima frase={primo or 0:.2f}s\n    {detto[:300]}", flush=True)
        riepilogo[scenario] = conti
    print("\nRiepilogo:")
    for s, c in riepilogo.items():
        contati = sum(v for k, v in c.items() if k != "senza ricerca")
        print(f"  {s:8} ok {c.get('ok', 0)}/{contati}"
              + "".join(f", {k} {v}" for k, v in c.items() if k not in ("ok", "no")))


if __name__ == "__main__":
    main()
