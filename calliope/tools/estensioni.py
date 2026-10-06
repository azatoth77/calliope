"""
I tool delle estensioni (04/10/2026, calliope/estensioni/).

- estensione_crea(compito, nome): chi amministra chiede una funzione permanente nuova (o la
  modifica di una esistente, `nome`). È un lavoro di codice per l'agente, con proposta e «sì»
  (come delega_lavoro: la proposta si conferma con delega_lavoro proposta=id). A lavoro finito
  la versione è «da approvare» e si annuncia.
- estensioni_gestisci(azione, nome, esecuzione, sempre): elenca; approva, indietro (sempre
  con la frase di sfida); rifiuta, disattiva, riattiva, revoca, rimuovi (con «Procedo?»);
  consenti e nega per un'azione pericolosa sospesa di un'estensione.
- est_<nome>: un tool per estensione attiva (calliope/estensioni/servizio.py, `specs`).
"""

import re

from .spec import ToolContext, ToolSpec
from ..testi import FAMILY, NIENTE


def _final(text: str, **extra) -> dict:
    return {"ok": True, **extra, "conferma": text, "risposta_finale": text}


def _permesso_gioco(ctx, rigido: bool = True):
    """Un gioco nuovo (05/10) lo chiede anche un familiare adulto, con la voce riconosciuta
    nella frase: (profilo, "") o (None, frase). Se l'agente gli dà permessi, lo approverà
    comunque solo chi amministra (servizio._approva)."""
    from .. import minori
    from . import agenti as ta
    prof = ta._person(ctx)
    sc = getattr(ctx, "speaker_ctx", None)
    if prof is None or ta._level(ctx) not in ("familiare", "amministra"):
        return None, "I giochi nuovi li chiede chi vive in casa."
    if minori.e_minore(prof):
        return None, "I giochi nuovi li chiede un adulto."
    if rigido and getattr(sc, "identified_by", None) != "voce" \
            and not getattr(sc, "sfida_superata", False):
        return None, ("In questa frase non ti ho riconosciuto bene dalla voce: ripeti la "
                      "richiesta con una frase un po' più lunga.")
    return prof, ""


def _gia_fatto(ctx, compito: str, nome: str, gia_fatto_da: str, come_chiederlo: str) -> dict:
    """«Questo lo so già fare»: il modello ha indicato un tool che fa già il compito (06/10,
    richiesta di Dario: «somma due numeri» è calcola). Non parte niente: la domanda (azione in
    sospeso), e il «sì» a lei, per la stessa estensione, la crea (politica.accettata)."""
    from .. import politica, provenienza
    esempio = str(come_chiederlo or "").strip().strip("«»\"' .?")
    # Con dati non fidati di mezzo questa è anche la domanda della politica (una sola, 06/10):
    # dice la fonte e cosa si crea, e il «sì» con la voce vale per tutte e due
    t = getattr(ctx, "politica", None)
    fonti = sorted(getattr(t, "contaminazione", None) or ())
    cosa = politica.da_confermare("estensione_crea", {"compito": compito})
    cosa = cosa[len("creare "):] if cosa.startswith("creare ") else cosa
    frase = "Questo lo so già fare" + (f": chiedimi pure «{esempio}»." if esempio else ".")
    if fonti:
        frase += f" C'è di mezzo {provenienza.detta(fonti[0])}, quindi chiedo a te: vuoi"
    else:
        frase += " Vuoi"
    frase += f" comunque {cosa}?"
    args = {"compito": compito, **({"nome": nome} if nome else {})}
    return {"ok": True, "fatto": "NIENTE creato: c'è già un tool che lo fa ("
                                 f"{str(gia_fatto_da).strip()})",
            "conferma": frase, "risposta_finale": frase,
            "in_sospeso": {"domanda": frase, "cosa": "creare comunque l'estensione",
                           "tool": "estensione_crea", "argomenti": args}}


def funzioni_di_calliope() -> str:
    """Le funzioni che Calliope ha già (i nomi dei suoi tool che non agiscono fuori), per il
    piano dell'agente di un'estensione: un doppione si chiede prima di scriverlo."""
    from .. import politica
    nomi = sorted(n for n, c in politica.CLASSI.items()
                  if c.classe in (politica.SICURO, politica.AZIONE))
    return "Funzioni che Calliope ha già (nomi dei suoi tool): " + ", ".join(nomi) + "."


def _estensione_crea(ctx: ToolContext, compito: str = "", nome: str = "", proposta: str = "",
                     gia_fatto_da: str = "", come_chiederlo: str = "", gioco=False,
                     **altro) -> dict:
    from . import agenti as ta
    from .. import politica
    est = getattr(ctx, "estensioni", None)
    svc = getattr(ctx, "lavori", None)
    if est is None or svc is None:
        return _final("Qui non posso creare estensioni: servono l'agente e il contenitore "
                      "isolato.", ok=False, fatto=NIENTE)
    # Solo un id di lavoro proposto («L3») conferma (06/10: gemma4 inventava «E1» già alla
    # prima richiesta, e il lavoro partiva come un generico «altro»); il resto si ignora
    if re.fullmatch(r"L\d+", str(proposta or "").strip()) and (
            not politica.accettata(ctx) or ta._offerta_di(ctx, svc, proposta)):
        return ta._delega_lavoro(ctx, proposta=str(proposta).strip())
    if str(proposta or "").strip():
        ta.note_rule(ctx, "lavori_proposta_non_id")
    # Un doppione di una capacità che c'è già: lo decide il modello (gia_fatto_da), il codice
    # controlla solo che il tool esista (06/10). Il «sì» alla domanda del doppione, per la
    # stessa estensione, la crea: politica.accettata (niente parametro «comunque»: gemma4 lo
    # metteva già alla prima richiesta, o scriveva «comune»)
    gia = str(gia_fatto_da or "").strip()
    if politica.gia_fatto({"gia_fatto_da": gia}) and not politica.accettata(ctx):
        ta.note_rule(ctx, "estensione_doppione")
        return _gia_fatto(ctx, str(compito or ""), str(nome or ""), gia, come_chiederlo)
    gioco = gioco in (True, "true", "sì", "si", 1)
    prof, why = ta._permesso(ctx, "estensione", rigido=True,
                             args={"compito": compito, "nome": nome})
    if prof is None and gioco and not isinstance(why, dict):
        prof, why = _permesso_gioco(ctx)
    if prof is None:
        return ta._no(ctx, why, "lavori_permesso")
    if not est.pronto():
        return ta._guasto(ctx, "Adesso non posso crearla: le estensioni girano solo in un "
                               "contenitore isolato, e qui adesso non è pronto.",
                          "estensione_senza_container")
    guasto = svc.collegamento_guasto()
    if guasto is not None:
        svc.verifica_in_secondo_piano()
        return ta._guasto(ctx, f"Adesso non posso: {guasto['motivo']}. "
                               f"{guasto['passo']}".strip())
    compito = str(compito or "").strip() or (getattr(ctx, "user_text", "") or "").strip()
    if not compito:
        return {"ok": False, "fatto": NIENTE, "errore": "manca il compito",
                "cosa_fare": "chiedi in breve cosa deve fare la funzione"}
    from ..estensioni.servizio import _nome, runtime_testo
    esistente = _nome(nome, est.archivio) if str(nome or "").strip() else ""
    file = {}
    vincoli = ""
    if esistente and est.archivio.voce(esistente):
        file = est.file_per_modifica(esistente)
        vincoli = (f"È la modifica dell'estensione esistente «{esistente}»: i suoi file sono "
                   f"già nella cartella; tieni lo stesso nome nel manifesto.")
    else:
        esistente = ""
    # Le funzioni che Calliope ha già, per il piano dell'agente (doppioni, 06/10)
    vincoli = (vincoli + " " + funzioni_di_calliope()).strip()
    gia_detto = politica.accettata(ctx) and politica.gia_fatto({"gia_fatto_da": gia})
    if gia_detto:
        vincoli += (f" La persona sa che Calliope lo fa già con {gia} e vuole comunque "
                    "l'estensione: nel piano gia_fatto_da resta vuoto.")
    lav = svc.nuovo("estensione", compito, prof.id, prof.name, ta._level(ctx), "", "", vincoli,
                    list(getattr(ctx, "storia", None) or []))
    lav.doppione_chiesto = gia_detto
    lav.estensione = esistente or None
    lav.gioco = bool(gioco)
    if gioco:
        lav.vincoli = ((lav.vincoli + " ") if lav.vincoli else "") + (
            "È un GIOCO sullo schermo: scheda interattiva (§5 del contratto), gioco puro, "
            "senza estensione.py.")
    lav.file_iniziali = {"calliope_estensione.py": runtime_testo(), **file}
    turno = int(getattr(ctx, "turno", 0) or 0)
    # Già confermata alla domanda della politica (06/10): niente secondo «Procedo?»
    if politica.accettata(ctx):          # regola `politica_conferma_unica`, dalla politica
        return ta._avvia(ctx, svc, lav)
    return ta._proponi(ctx, svc, lav, turno)


def _estensioni_gestisci(ctx: ToolContext, azione: str = "elenca", nome: str = "",
                         esecuzione: str = "", sempre=False) -> dict:
    est = getattr(ctx, "estensioni", None)
    if est is None:
        return _final("Qui le estensioni non ci sono.", ok=False, fatto=NIENTE)
    return est.gestisci(ctx, azione, nome, esecuzione, sempre)


AZIONI = ["elenca", "approva", "rifiuta", "disattiva", "riattiva", "indietro", "revoca",
          "rimuovi", "consenti", "nega"]


def estensioni_specs(crea: bool = True) -> list[ToolSpec]:
    out = []
    if crea:
        out.append(ToolSpec(
            name="estensione_crea",
            description=("Crea una funzione permanente nuova di Calliope (un'estensione: un "
                         "piccolo programma che resta e si usa a voce, per esempio «fammi una "
                         "funzione che converte le unità di misura»), oppure modifica una "
                         "estensione esistente (nome). Quelle che ci sono sono i tuoi tool est_: "
                         "un programma fatto da delega_lavoro non è un'estensione e si riusa con "
                         "lavori_esegui. NON per un programma da usare una volta "
                         "sola: quello è delega_lavoro tipo codice. compito: cosa deve fare, con "
                         "i dati come detti. gia_fatto_da: se uno dei tuoi tool fa già la stessa "
                         "cosa (sommare due numeri o fare conti = calcola), il suo nome, e "
                         "come_chiederlo: la frase con cui chiederlo a voce (es. «quanto fa 3 "
                         "più 5»); vuoto se nessuno: chiedo io se la vuole comunque, e al sì "
                         "richiamalo uguale. gioco=true per un gioco nuovo da fare sullo "
                         "schermo (tris, memory, quiz…). Se finisce con «Procedo?», dopo il sì "
                         "richiama delega_lavoro con proposta = l'id proposto."),
            parameters={"type": "object", "properties": {
                "compito": {"type": "string"}, "nome": {"type": "string"},
                "gia_fatto_da": {"type": "string"}, "come_chiederlo": {"type": "string"},
                "proposta": {"type": "string"}, "gioco": {"type": "boolean"}},
                "required": ["compito"]},
            func=_estensione_crea, risk="azione", levels=FAMILY))
    out.append(ToolSpec(
        name="estensioni_gestisci",
        description=("Le estensioni di Calliope (funzioni aggiunte dalla famiglia): elenca "
                     "(quali ci sono davvero e come si chiedono: prima di dire come usarne una); "
                     "approva una versione nuova, rifiuta, disattiva, riattiva, indietro (torna "
                     "alla versione precedente), revoca (i permessi «sempre»), rimuovi; "
                     "consenti o nega un'azione che un'estensione ha chiesto (esecuzione = l'id, "
                     "es. «E3»; sempre=true se la persona dice «sì, sempre»)."),
        parameters={"type": "object", "properties": {
            "azione": {"type": "string", "enum": AZIONI}, "nome": {"type": "string"},
            "esecuzione": {"type": "string"}, "sempre": {"type": "boolean"}},
            "required": ["azione"]},
        func=_estensioni_gestisci, risk="azione", levels=FAMILY))
    return out
