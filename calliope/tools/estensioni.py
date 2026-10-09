"""
I tool delle estensioni (04/10/2026, calliope/estensioni/).

- _estensione_crea (il tool sviluppo_apri tipo estensione, tools/sviluppo.py; fino al 08/10 il
  tool estensione_crea): chi amministra chiede una funzione permanente nuova (`nome`) o la
  modifica di una che c'è (`modifica`, dal 08/10: una versione nuova). È un lavoro di codice
  per l'agente, con proposta e «sì» (sviluppo_apri proposta=id). A lavoro finito la versione
  è «da approvare» e si annuncia.
- estensione_gestisci (fino al 08/10 estensioni_gestisci)(azione, nome, esecuzione, sempre): elenca; approva, indietro (sempre
  con la frase di sfida); rifiuta, disattiva, riattiva, revoca, rimuovi (con «Procedo?»; dal
  09/10 l'eliminazione definitiva di una disattivata: un'attiva prima si disattiva);
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
    cosa = politica.da_confermare("sviluppo_apri", {"compito": compito})
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
                           "tool": "sviluppo_apri", "argomenti": {"tipo": "estensione", **args}}}


def funzioni_di_calliope() -> str:
    """Le funzioni che Calliope ha già (i nomi dei suoi tool che non agiscono fuori), per il
    piano dell'agente di un'estensione: un doppione si chiede prima di scriverlo."""
    from .. import politica
    nomi = sorted(n for n, c in politica.CLASSI.items()
                  if c.classe in (politica.SICURO, politica.AZIONE))
    return "Funzioni che Calliope ha già (nomi dei suoi tool): " + ", ".join(nomi) + "."


def _estensione_crea(ctx: ToolContext, compito: str = "", nome: str = "", proposta: str = "",
                     gia_fatto_da: str = "", come_chiederlo: str = "", gioco=False,
                     modifica: str = "", accanto: bool = False, **altro) -> dict:
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
    # Quale estensione si cambia, PRIMA dei permessi e della frase di sfida (08/10, DGX delle
    # 16:45: sfida chiesta e superata per una chiamata che poi rifiutava «c'è già l'estensione»)
    esistente, rifiuto = _da_cambiare(ctx, est, modifica, nome, compito)
    if rifiuto is not None:
        return rifiuto
    simile = "" if esistente else _simile(nome, est)
    if simile and not accanto and not _scelta_gia_detta(ctx, est, simile):
        # Un nome simile a un'estensione che c'è, senza `modifica` (08/10, caso vero della DGX
        # delle 15:36: «Modifica l'estensione Meteocittà: fai codificare il nome…» → il 26B
        # senza modifica, ed è nata un'estensione NUOVA accanto, riscritta da zero, anche dopo
        # «vorrei che tu modificassi l'estensione»). Niente lavoro né sviluppo: la scelta torna
        # al modello (correzione della forma della sua chiamata, principio 10; regola
        # `estensione_simile_scelta`). Se la richiama uguale nella stessa risposta, è nuova
        ta.note_rule(ctx, "estensione_simile_scelta")
        est._simile_detto = (int(getattr(ctx, "turno", 0) or 0), simile)
        tit = _titolo(est, simile)
        return {"ok": False, "fatto": NIENTE,
                "errore": f"c'è già l'estensione «{tit}» ({simile}): niente creato",
                "cosa_fare": (f"se la persona vuole CAMBIARE «{tit}» (modificala, correggila, "
                              f"aggiungi…), richiama sviluppo_apri con modifica = \"{simile}\" e "
                              "compito = cosa cambiare; per un'estensione NUOVA accanto, "
                              "richiama con un nome diverso; se non si capisce, chiedi: «Vuoi "
                              f"cambiare «{tit}» o farne una nuova accanto?»")}
    # La chiamata intera nella frase di sfida, se serve: rifatta dopo la sfida è la stessa
    # (16:45 sulla DGX: senza `modifica` e `tipo` la chiamata rifatta era un'estensione nuova)
    tutti = {k: v for k, v in {"tipo": "estensione", "compito": compito, "nome": nome,
                               "modifica": esistente or modifica,
                               "gioco": True if gioco else None}.items() if v}
    prof, why = ta._permesso(ctx, "estensione", rigido=True, args=tutti)
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
    from ..estensioni.servizio import runtime_testo
    # Uno sviluppo aperto (08/10, modalità sviluppo, calliope/sviluppo.py): un'estensione
    # diversa non parte finché non è chiuso o sospeso; le risposte all'analisi e la modifica
    # della sua estensione sì
    from .sviluppo import apri_se_serve, controlla_nuovo
    blocco = controlla_nuovo(ctx, "sviluppo_apri", {"modifica": modifica, "gioco": gioco})
    if blocco is not None:
        return blocco
    # Una richiesta nuova di chi amministra apre lo sviluppo, in analisi (08/10). Per una
    # modifica il titolo è quello dell'estensione (dato dalla persona, se l'ha rinominata)
    apri_se_serve(ctx, "estensione", compito,
                  titolo=(_titolo(est, esistente) if esistente else str(nome or "").strip()),
                  gioco=bool(gioco in (True, "true", "sì", "si", 1)),
                  estensione=esistente or None)
    if simile:
        ta.note_rule(ctx, "estensione_nuova_accanto")
    file = {}
    vincoli = ""
    if esistente:
        file = est.file_per_modifica(esistente)
        vincoli = (f"È la modifica dell'estensione esistente «{esistente}»: i suoi file sono "
                   f"già nella cartella; tieni lo stesso nome nel manifesto (la descrizione "
                   f"cambia se cambia quello che fa). " + titolo_vincolo(est, esistente)).strip()
    # Le funzioni che Calliope ha già, per il piano dell'agente (doppioni, 06/10)
    vincoli = (vincoli + " " + funzioni_di_calliope()).strip()
    gia_detto = politica.accettata(ctx) and politica.gia_fatto({"gia_fatto_da": gia})
    level = ta._level(ctx)
    storia = list(getattr(ctx, "storia", None) or [])

    def crea(compito_agente: str, esito=None, gia_detto: bool = False, gia: str = ""):
        v = vincoli
        if gia_detto:
            v += (f" La persona sa che Calliope lo fa già con {gia} e vuole comunque "
                  "l'estensione: nel piano gia_fatto_da resta vuoto.")
        if esito is not None and esito.esito == "raffinabile":
            v += f" Richiesta come detta dalla persona: «{compito}»."
        if esito is not None and esito.fonte_ok and esito.fonte_url:
            # La fonte che l'analisi ha già verificato (06/10): l'agente parte da lì
            v += f" Fonte pubblica verificata (risponde): {esito.fonte_url}"

        lav = svc.nuovo("estensione", compito_agente, prof.id, prof.name, level, "", "", v,
                        storia)
        # Il nome del lavoro: quello dell'estensione (06/10: L1 si chiamava «estensione che»)
        titolo = ta._titolo_estensione(_titolo(est, esistente) if esistente else nome, esito)
        if titolo:
            lav.titolo = titolo
        elif compito_agente != compito:
            from ..agenti.servizio import titolo_da
            lav.titolo = titolo_da(compito)
        if esito is not None and esito.esito == "raffinabile":
            lav.specifica = esito.specifica
        lav.doppione_chiesto = gia_detto
        lav.estensione = esistente or None
        lav.gioco = bool(gioco)
        if gioco:
            lav.vincoli = ((lav.vincoli + " ") if lav.vincoli else "") + (
                "È un GIOCO sullo schermo: scheda interattiva (§5 del contratto), gioco puro, "
                "senza estensione.py.")
        lav.file_iniziali = {"calliope_estensione.py": runtime_testo(), **file}
        return lav

    # L'analisi della richiesta prima della proposta (06/10, calliope/agenti/richiesta.py): non
    # per un gioco né per la modifica di un'estensione che c'è già
    esito = None
    if not esistente and not gioco and not gia_detto:
        ris, esito, gia_an = ta._analisi(ctx, svc, prof, "estensione", compito, crea,
                                         "sviluppo_apri")
        if ris is not None:
            if esito is not None and esito.esito in ("impossibile", "gia_fatto"):
                from .sviluppo import chiudi_se_vuoto
                chiudi_se_vuoto(ctx, esito.esito)
            return ris
        if gia_an:                       # «sì, comunque» dopo il «c'è già» dell'analisi
            gia, gia_detto = gia_an, True
    raffinata = esito is not None and esito.esito == "raffinabile"
    lav = crea(esito.specifica if raffinata else compito, esito, gia_detto, gia)
    turno = int(getattr(ctx, "turno", 0) or 0)
    # Già confermata alla domanda della politica (06/10): niente secondo «Procedo?» (salvo una
    # specifica raffinata dall'analisi, che la persona non ha ancora sentito)
    if politica.accettata(ctx) and not raffinata:   # regola `politica_conferma_unica`
        out = ta._avvia(ctx, svc, lav)
    else:
        out = ta._proponi(ctx, svc, lav, turno)
    return _con_avviso(out, esistente, simile, est)


def _da_cambiare(ctx, est, modifica, nome, compito) -> tuple[str, dict | None]:
    """(nome interno dell'estensione da cambiare, None), ("", None) per una nuova, o ("", il
    rifiuto da dare al modello). Una versione nuova solo se il modello lo dice (`modifica`,
    08/10). Prima `nome` valeva per tutte e due e si cercava con un confronto approssimato: il
    07/10 sulla DGX «Meteo Città», il nome di un'estensione NUOVA (una città qualunque), è
    diventato la versione 2 di «meteo_citta» (Borgoverde e Valfiorita).

    `modifica` che non è un'estensione (08/10, DGX delle 16:43: «modifica: "aggiungi la
    possibilità di scegliere quanti giorni…"», la cosa da cambiare al posto del nome): se il
    modello l'ha nominata in `nome`, o se la frase o il compito ne nominano una sola, è quella.
    Correzione della forma di una scelta già fatta dal modello (cambiare un'estensione,
    principio 10; regola `estensione_modifica_dal_nome`); con due nominate o nessuna, la
    scelta torna al modello con l'elenco e gli stati."""
    from ..estensioni.servizio import _nome
    detto = str(modifica or "").strip()
    if not detto:
        return "", None
    esistente = _nome(detto, est.archivio)
    if est.archivio.voce(esistente):
        return esistente, None
    trovata = _nominata(ctx, est, nome, compito)
    if trovata:
        from .spec import note_rule
        note_rule(ctx, "estensione_modifica_dal_nome")
        return trovata, None
    ci_sono = elenco_breve(est)
    return "", {"ok": False, "fatto": NIENTE,
                "errore": f"non ho un'estensione «{detto[:80]}» da cambiare",
                "cosa_fare": ("modifica = il NOME di un'estensione (cosa cambiare va in "
                              "compito): richiama con modifica = una di queste: " + ci_sono
                              if ci_sono else "non ci sono estensioni: per farne una nuova "
                                              "togli modifica")}


def _nominata(ctx, est, nome, compito) -> str:
    """L'unica estensione nominata: in `nome` dal modello, oppure nella frase della persona o
    nel compito (una disattivata conta solo se non c'è un'attiva). "" se nessuna o più d'una."""
    from ..estensioni.servizio import _nome
    if str(nome or "").strip():
        n = _nome(nome, est.archivio)
        if est.archivio.voce(n):
            return n
    testo = " ".join(str(x or "") for x in (getattr(ctx, "user_text", ""), compito))
    try:
        trovate = est.nominate(testo, tutte=True)
    except Exception:  # noqa: BLE001 — nel dubbio, la scelta torna al modello
        return ""
    nomi = sorted({t["nome"] for t in trovate})
    if len(nomi) > 1:
        nomi = [n for n in nomi if (est.archivio.voce(n) or {}).get("stato") == "attiva"]
    return nomi[0] if len(nomi) == 1 else ""


def titolo_vincolo(est, nome: str) -> str:
    """Per l'agente che scrive una versione nuova: il titolo dato dalla persona resta (08/10)."""
    titolo = str((est.archivio.voce(nome) or {}).get("titolo") or "").strip()
    if not titolo:
        return ""
    return (f"Il titolo «{titolo}» l'ha scelto la persona: nel manifesto usa proprio questo "
            "titolo.")


def _scelta_gia_detta(ctx, est, simile: str) -> bool:
    """La scelta «cambiare o nuova accanto» è già tornata al modello in questo turno per la
    stessa estensione: se richiama ancora senza `modifica`, vuole una nuova."""
    return getattr(est, "_simile_detto", None) == (int(getattr(ctx, "turno", 0) or 0), simile)


def _titolo(est, nome: str) -> str:
    m = est.archivio.manifesto(nome) or est.archivio.manifesto(
        nome, est.archivio.candidata(nome)) or {}
    return str(m.get("titolo") or nome)


def elenco_breve(est) -> str:
    """«Meteo per città» (meteo_citta, attiva), «Tris» (tris, disattivata): le estensioni che ci
    sono, per il modello, con lo stato (08/10: due titoli quasi uguali, uno disattivato, e il
    modello chiedeva «Meteo città o Meteocittà?»)."""
    def stato(n):
        st = (est.archivio.voce(n) or {}).get("stato") or "?"
        return {"da_approvare": "da approvare"}.get(st, st)
    return ", ".join(f"«{_titolo(est, n)}» ({n}, {stato(n)})" for n in est.archivio.nomi())


def _simile(nome: str, est) -> str:
    """Il nome interno di un'estensione che c'è con un nome simile a quello dato a una nuova
    («Meteo Città» e meteo_citta), o ""."""
    from ..estensioni.servizio import _nome
    if not str(nome or "").strip():
        return ""
    vero = _nome(nome, est.archivio)
    return vero if est.archivio.voce(vero) else ""


def _con_avviso(out: dict, esistente: str, simile: str, est) -> dict:
    """La frase della proposta o dell'avvio dice se è una versione nuova di un'estensione che
    c'è o un'estensione nuova accanto a una simile (08/10, caso della DGX del 07/10)."""
    if not isinstance(out, dict) or not out.get("ok") or not (esistente or simile):
        return out
    if esistente:
        avviso = (f"Sarà una versione nuova di «{_titolo(est, esistente)}»: quella di adesso "
                  f"resta in uso finché non approvi la nuova.")
    else:
        avviso = (f"Sarà un'estensione nuova: «{_titolo(est, simile)}», che c'è già, resta "
                  f"com'è.")
    for k in ("conferma", "risposta_finale"):
        if isinstance(out.get(k), str) and out[k].strip():
            out[k] = f"{avviso} {out[k]}"
    sosp = out.get("in_sospeso")
    if isinstance(sosp, dict) and isinstance(sosp.get("domanda"), str) \
            and not sosp["domanda"].startswith(avviso) and len(sosp["domanda"]) > 20:
        sosp["domanda"] = f"{avviso} {sosp['domanda']}"
    return out



def _estensioni_gestisci(ctx: ToolContext, azione: str = "elenca", nome: str = "",
                         esecuzione: str = "", sempre=False, titolo: str = "") -> dict:
    est = getattr(ctx, "estensioni", None)
    if est is None:
        return _final("Qui le estensioni non ci sono.", ok=False, fatto=NIENTE)
    return est.gestisci(ctx, azione, nome, esecuzione, sempre, titolo)


def _prepara_gestisci(ctx, argomenti: dict) -> dict:
    from ..estensioni.servizio import prepara_gestisci
    return prepara_gestisci(ctx, argomenti)


AZIONI = ["elenca", "approva", "rifiuta", "disattiva", "riattiva", "indietro", "revoca",
          "rimuovi", "rinomina", "consenti", "nega"]


def estensioni_specs(crea: bool = True) -> list[ToolSpec]:
    out = []
    if crea:
        # Dal 08/10 (versione 2) un'estensione nuova o cambiata si apre con sviluppo_apri
        # (tools/sviluppo.py), lo stesso tool dei programmi
        from .sviluppo import sviluppo_apri_spec
        out.append(sviluppo_apri_spec())
    out.append(ToolSpec(
        name="estensione_gestisci",
        description=("Le estensioni di Calliope (funzioni aggiunte dalla famiglia): elenca "
                     "(quali e quante ci sono davvero, attive o no, con le versioni nuove da "
                     "approvare: chiamalo prima di rispondere a una domanda sulle estensioni o "
                     "di dire come usarne una); approva una versione nuova («attiva la versione nuova», "
                     "«usa la nuova»), rifiuta, disattiva, riattiva (una disattivata), indietro "
                     "(torna alla versione precedente), revoca (i permessi «sempre»), rimuovi "
                     "(elimina per sempre una disattivata: file e versioni; un'attiva va prima "
                     "disattivata), rinomina (titolo = il nome nuovo detto: cambia solo come si chiama, "
                     "senza agente); "
                     "consenti o nega un'azione che un'estensione ha chiesto (esecuzione = l'id, "
                     "es. «E3»; sempre=true se la persona dice «sì, sempre»). Per USARE "
                     "un'estensione chiama il suo tool est_, non questo."),
        parameters={"type": "object", "properties": {
            "azione": {"type": "string", "enum": AZIONI}, "nome": {"type": "string"},
            "esecuzione": {"type": "string"}, "sempre": {"type": "boolean"},
            "titolo": {"type": "string"}},
            "required": ["azione"]},
        func=_estensioni_gestisci, risk="azione", levels=FAMILY,
        prepara=_prepara_gestisci, nomi={"nome": "estensione"}))
    return out
