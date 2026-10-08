"""
I tool dei lavori in secondo piano (calliope/agenti/, 02/10/2026): «gemma davanti, agenti
dietro».

Nomi dal 08/10 (modalità sviluppo, versione 2: nome singolare + verbo, prefisso per famiglia):
delega_lavoro → lavoro_affida (senza il codice: i programmi passano da sviluppo_apri, in
tools/sviluppo.py), lavori_stato → lavoro_stato, lavori_annulla → lavoro_annulla,
lavori_rispondi → lavoro_rispondi, risultato_lavoro → lavoro_risultato, lavori_esegui →
programma_esegui. I nomi vecchi valgono ancora nel registro (ToolRegistry.NOMI_VECCHI).

- lavoro_affida(tipo, compito, …): un lavoro lungo il cui risultato è un file complesso (una
  relazione, una ricerca a più passi) va all'agente (modello grande, in secondo piano). Il
  codice no: un programma è uno sviluppo (sviluppo_apri tipo programma; qui un tipo codice ci
  passa da sé, regola `lavoro_codice_sviluppo`). Il criterio è nella
  descrizione e nel prompt, non in una regola: la ricerca del 02/10 aveva visto delegare
  «come si scrive un ciclo for?» (2 su 2), e una regola sulle parole sbaglierebbe al
  contrario. I lavori costosi chiedono conferma («Procedo?», azione in sospeso); la
  conferma (`conferma` = l'id del lavoro proposto) vale solo nella risposta dopo, della
  stessa persona, come le installazioni.
- lavoro_stato: a che punto è, con il passo dell'agente.
- lavoro_annulla: ferma il lavoro (subito: lo stream si chiude, la sandbox si ferma).
- lavoro_rispondi(lavoro, risposta) (03/10): la risposta a una domanda dell'agente a metà
  lavoro; solo chi l'ha chiesto o chi amministra. La domanda annunciata è un'azione in
  sospeso, ma la persona può rispondere anche più tardi («per il lavoro della relazione: il
  cliente è Rossi»).
- programma_esegui(lavoro, dati) (04/10): esegue di nuovo il programma di un lavoro di codice
  finito, nella stessa sandbox, e ne mostra l'uscita in diretta sullo schermo personale («fammelo
  vedere», «eseguilo di nuovo», «eseguilo con 3 e 5»); «fermalo» è lavoro_annulla, che ferma
  prima il programma in esecuzione. Solo chi ha chiesto il lavoro o chi amministra.
- lavoro_affida(file=…) (03/10): un lavoro su un file della persona che sta sul PC. Il file si
  cerca come pc_cerca_file, con gli stessi permessi (proprietari del PC o chi amministra, o un
  documento appena scritto per chi parla), e prima di mandarne la copia la conferma è sempre
  esplicita: il file lascia il PC.

Permessi nel codice, non nel prompt: delegare solo dai familiari in su (`agenti_livello`), il
codice solo chi amministra (`agenti_livello_codice`), riconosciuto dalla voce nella frase della
richiesta; gli ospiti non vedono questi tool. La frase da dire è sempre pronta
(`risposta_finale`): il modello non la riformula e il turno non aspetta un'altra passata.
"""

import difflib
import re

from .. import politica

from ..conferme import admin_confermato, chiedi_conferma, e_admin, serve_conferma
from .spec import ToolContext, ToolSpec, note_rule, serve_la_voce
from ..testi import FAMILY, NIENTE, RANK

TIPI = ("codice", "documento", "ricerca", "altro")
# I tipi che il modello vede in lavoro_affida (08/10, versione 2): il codice è di sviluppo_apri
TIPI_AFFIDA = ("documento", "ricerca", "altro")


def tool_di(lav) -> str:
    """Il tool che conferma o richiama un lavoro proposto: i programmi e le estensioni sono
    sviluppi (sviluppo_apri), il resto lavoro_affida."""
    return "sviluppo_apri" if getattr(lav, "tipo", "") in ("codice", "estensione") \
        else "lavoro_affida"


def _final(text: str, **extra) -> dict:
    return {"ok": True, **extra, "conferma": text, "risposta_finale": text}


def _rifiuto(ctx, frase: str, regola: str) -> dict:
    note_rule(ctx, regola)
    return _final(frase, ok=False, fatto=NIENTE)


# Un guasto di adesso (contenitore non pronto, agente irraggiungibile) non è un limite di
# Calliope: detto così, e con questa nota nel risultato che resta nella storia (06/10, DGX: dopo
# «non posso crearne» il 26B rispondeva «non posso creare estensioni» anche un'ora dopo)
GUASTO = ("è un guasto di adesso, non una cosa che non sai fare: se la persona lo chiede di "
          "nuovo, richiama il tool")


def _guasto(ctx, frase: str, regola: str = "") -> dict:
    if regola:
        note_rule(ctx, regola)
    return _final(frase, ok=False, fatto=NIENTE, guasto=GUASTO)


def _level(ctx) -> str:
    return getattr(ctx.speaker_ctx, "current_level", "ospite") or "ospite"


def _person(ctx):
    name = getattr(ctx.speaker_ctx, "current_speaker", None)
    return ctx.speakers.get(name) if name and ctx.speakers else None


def _permesso(ctx, tipo: str, rigido: bool, args: dict | None = None):
    """(profilo, "") se chi parla può delegare questo tipo di lavoro; altrimenti (None, frase)
    o (None, risultato con la frase di sfida). `rigido`: una richiesta nuova di codice va
    detta con una frase riconosciuta dalla voce; per la conferma basta anche il «sì» breve di
    chi amministra in una conversazione sicura (conferme.admin_confermato). A chi amministra
    con una frase che non basta non si dice mai «chiedi a chi amministra» (04/10): si chiede
    la frase di sfida."""
    cfg = ctx.cfg
    level = "amministra" if admin_confermato(ctx) else _level(ctx)
    need = (getattr(cfg, "agenti_livello_codice", "amministra")
            if tipo in ("codice", "estensione") else getattr(cfg, "agenti_livello", "familiare"))
    # Le estensioni (04/10) come il codice: solo chi amministra, con la voce nella frase
    tool = "sviluppo_apri" if tipo in ("estensione", "codice") else "lavoro_affida"
    cosa = ("creare una funzione nuova di Calliope" if tipo == "estensione"
            else "affidare un programma all'agente")
    if RANK.get(level, 0) < max(1, RANK.get(need, 2)):
        sfida = serve_conferma(ctx, tool, args, cosa)
        if sfida is not None:
            return None, sfida
        if tipo == "estensione":
            return None, ("Le funzioni nuove di Calliope le può chiedere solo chi amministra: "
                          "chiedi a chi amministra.")
        if tipo == "codice":
            return None, ("I lavori di programmazione li può affidare solo chi amministra: "
                          "chiedi a chi amministra.")
        return None, "Non posso affidare lavori per te: chiedi a qualcuno di casa."
    prof = _person(ctx)
    if prof is None:
        return None, "Non so chi sei: i lavori li affido solo per le persone registrate."
    if rigido and tipo in ("codice", "estensione") and getattr(
            ctx.speaker_ctx, "identified_by", "voce") not in ("voce", None) \
            and not getattr(ctx.speaker_ctx, "sfida_superata", False):
        # Un'estensione (08/10, DGX delle 16:45: «Sì, te lo confermo» dopo la richiesta detta
        # con la voce → frase di sfida «per creare una funzione nuova», poi sprecata): aprire
        # lo sviluppo è solo l'analisi e la proposta, e niente diventa attivo senza
        # l'approvazione, che vuole sempre la frase di sfida. Basta il «sì» breve compatibile di
        # chi amministra in una conversazione sicura (regola `sviluppo_apri_breve`)
        if (tipo == "estensione" and getattr(ctx.speaker_ctx, "identified_by", None) == "breve"
                and admin_confermato(ctx)):
            note_rule(ctx, "sviluppo_apri_breve")
            return prof, ""
        # Una richiesta nuova di codice: il «sì» breve non basta mai, nemmeno in una
        # conversazione sicura
        if e_admin(ctx):
            return None, chiedi_conferma(ctx, tool, args, cosa)
        return None, ("In questa frase non ti ho riconosciuto bene dalla voce: ripeti la "
                      "richiesta con una frase un po' più lunga.")
    return prof, ""


def _no(ctx, why, regola: str) -> dict:
    """Il rifiuto di _permesso: la frase, oppure il risultato della sfida così com'è."""
    return why if isinstance(why, dict) else _rifiuto(ctx, why, regola)


def _schermo(ctx, lav):
    """La scheda del lavoro va agli schermi personali di chi l'ha chiesto adesso: in diretta
    mentre l'agente lavora (03/10) e a lavoro finito."""
    hub = getattr(ctx, "schermi", None)
    if hub is None:
        return
    sender = hub.mittente(ctx)
    lav.on_scheda = lambda card: hub.invia(card, sender)
    # L'avanzamento in diretta (agenti/avanzamento.py) solo con le schede automatiche accese
    lav.segui_schermi = bool(getattr(hub, "automatiche", True))


_FORMATO_DA_EST = {"docx": "word", "xlsx": "excel", "pdf": "pdf"}


def _trova_file(ctx, prof, file: str):
    """(candidati, None) per il file detto (nome o numero di un risultato dell'ultima
    ricerca), oppure (None, risultato da dire). Stesse regole di pc_cerca_file e pc_apri_file:
    la ricerca la fa l'esecutore del PC, i percorsi non passano mai dal modello."""
    from ..agenti.file_utente import ESTENSIONI, detto, estensione
    from .pc import _ORDINALS, _call, _fuori, _locked, _not_owner, _owner, _pc, _spoken_names
    name, ex = _pc(ctx, None)
    if ex is None:
        return None, _final("Qui non vedo i file del PC: non posso mandarne uno all'agente.",
                            ok=False, fatto=NIENTE)
    s = str(file).strip()
    m = re.fullmatch(r"(?:il |lo |la |l'|numero |n\.? ?)?(\d{1,2})[°º]?|(?:il |lo |la |l')?(\w+)",
                     s.lower())
    n = int(m[1]) if m and m[1] else (_ORDINALS.get(m[2]) if m and m[2] else None)
    if n is not None:
        fuori = _fuori(name, ex)
        if fuori:
            return None, fuori
        own = getattr(ex, "ultimo_proprio", lambda _: False)(prof.id)
        if not own and not _owner(ctx):
            return None, _not_owner(name)
        r = _call(name, ex.risultato, prof.id, n)
        if not r.get("ok"):
            return None, {**r, "fatto": NIENTE,
                          "cosa_fare": "richiama il tool con file = il nome del file detto "
                                       "dalla persona"}
        items = [r["item"]]
    else:
        fuori = _fuori(name, ex, "ricerca")
        if fuori:
            return None, fuori
        if not _owner(ctx):
            return None, _not_owner(name)
        ext = estensione(s)
        ext = ext if re.fullmatch(r"[a-z0-9]{2,5}", ext or "") else ""
        testo = s[:-(len(ext) + 1)] if ext else s
        if ext and ext not in ESTENSIONI:
            return None, _final(f"Non posso mandare all'agente un file .{ext}: solo testo, codice, "
                                f"Word, Excel e PDF.", ok=False, fatto=NIENTE)
        r = _call(name, ex.cerca_file, prof.id, testo, "qualsiasi", None, None)
        if r.get("bloccato"):
            return None, _locked(name)
        if not r.get("ok"):
            return None, r
        items = []
        for x in r.get("risultati") or []:
            rr = ex.risultato(prof.id, x["n"])
            if rr.get("ok"):
                items.append(rr["item"])
        if ext:
            items = [i for i in items if str(i.get("estensione")).lower() == ext] or items
        if not items:
            return None, _final(f"Sul {name} non ho trovato «{s}».", ok=False, fatto=NIENTE)
    ammessi = [i for i in items if str(i.get("estensione")).lower() in ESTENSIONI]
    if not ammessi:
        e0 = str(items[0].get("estensione") or "?").lower()
        return None, _final(f"Non posso mandare all'agente un file .{e0}: solo testo, codice, "
                            f"Word, Excel e PDF.", ok=False, fatto=NIENTE)
    ammessi = ammessi[:5]
    nomi = _spoken_names(ammessi)
    return [{"item": i, "detto": detto(nm, str(i.get("estensione") or "")),
             "detto_di": detto(nm, str(i.get("estensione") or ""), di=True), "pc": name,
             "ex": ex} for i, nm in zip(ammessi, nomi)], None


class _DaAllegato:
    """Un file allegato alla conversazione (calliope/allegati.py, 05/10) come «esecutore» per
    _prendi_file di agenti/servizio.py: la copia è già in memoria, niente PC né satellite."""

    def __init__(self, att, nome: str, ext: str):
        self.att, self.nome, self.ext = att, nome, ext

    def copia_file(self, item, max_byte, estensioni):
        dati = self.att.dati
        if dati is None:
            return {"ok": False, "errore": "del file ho solo il nome"}
        if len(dati) > max_byte:
            return {"ok": False, "errore": "il file è troppo grande per l'agente"}
        if self.ext not in estensioni:
            return {"ok": False, "errore": f"l'agente non lavora sui file .{self.ext}"}
        return {"ok": True, "nome": self.nome, "estensione": self.ext, "dati": dati}


def _da_allegato(ctx, prof, allegato):
    """(candidati, None) per un file allegato alla conversazione, oppure (None, risultato).
    Solo i file mandati da chi parla; il tipo è quello vero (dai byte), e uno script che
    l'agente non conosce arriva come testo .txt."""
    from ..agenti.file_utente import ESTENSIONI_TESTO, detto
    from .allegati import prendi
    att, err = prendi(ctx, allegato)
    if err:
        return None, {**err, "fatto": NIENTE}
    if att.persona is not None and getattr(prof, "id", None) != att.persona:
        return None, _final("Posso mandare all'agente solo i file che mi hai mandato tu.",
                            ok=False, fatto=NIENTE)
    ext = {"pdf": "pdf", "word": "docx", "excel": "xlsx"}.get(att.categoria)
    if ext is None and att.categoria in ("testo", "script"):
        ext = att.estensione if att.estensione in ESTENSIONI_TESTO else "txt"
    if ext is None or att.dati is None:
        return None, _final(f"All'agente mando solo testo, codice, Word, Excel e PDF; questo è "
                            f"{att.detto()}.", ok=False, fatto=NIENTE)
    from ..agenti.file_utente import nome_sicuro
    from pathlib import PurePath
    stem = PurePath(nome_sicuro(att.nome)).stem or "file"
    nome = f"{stem}.{ext}"
    return [{"item": {"nome": nome, "estensione": ext}, "detto": detto(stem, ext),
             "detto_di": detto(stem, ext, di=True), "pc": "conversazione",
             "ex": _DaAllegato(att, nome, ext)}], None


def _scegli(lav, file) -> bool:
    """Tra più file trovati, quello scelto (numero, ordinale o parte del nome). True se il
    lavoro ha il suo file."""
    if lav.file_utente is not None:
        return True
    from .pc import _ORDINALS
    s = str(file or "").strip().lower()
    if not s:
        return False
    m = re.fullmatch(r"(?:il |lo |la |l'|numero |n\.? ?)?(\d{1,2})[°º]?|(?:il |lo |la |l')?(\w+)",
                     s)
    n = int(m[1]) if m and m[1] else (_ORDINALS.get(m[2]) if m and m[2] else None)
    cand = lav.file_candidati
    if n == -1:
        n = len(cand)
    if n is not None and 1 <= n <= len(cand):
        lav.file_utente = cand[n - 1]
    else:
        trovati = [c for c in cand if s in c["detto"].lower() or s in
                   str(c["item"].get("nome", "")).lower()]
        if len(trovati) != 1:
            return False
        lav.file_utente = trovati[0]
    ext = str(lav.file_utente["item"].get("estensione") or "").lower()
    if lav.tipo == "documento" and not lav.formato:
        lav.formato = _FORMATO_DA_EST.get(ext, "")
    return True


def _offerta_di(ctx, svc, ident: str) -> bool:
    """C'è un'offerta del tool ancora valida, per chi parla, con questo id."""
    prof = _person(ctx)
    off = (svc.offerta(getattr(prof, "id", None), int(getattr(ctx, "turno", 0) or 0))
           if hasattr(svc, "offerta") else None)
    return off is not None and off["lavoro"].id == str(ident or "").strip()


def _proponi(ctx, svc, lav, turno) -> dict:
    frase = svc.proponi(lav, turno)
    # La modalità sviluppo (08/10, calliope/sviluppo.py): la specifica proposta
    from .sviluppo import su_proposta
    sv = su_proposta(svc, lav)
    tool = tool_di(lav)
    if lav.file_utente is None and len(lav.file_candidati) > 1:
        cosa = "i file trovati: " + ", ".join(f"{i} = {c['detto']}" for i, c in
                                              enumerate(lav.file_candidati, 1))
        return _final(frase, fatto="domanda: il lavoro NON è ancora cominciato",
                      in_sospeso={"domanda": "Quale mando all'agente?", "cosa": cosa,
                                  "tool": tool,
                                  "argomenti": f'proposta="{lav.id}", file = il numero del '
                                               f'file scelto, tipo e compito come prima'})
    domanda = "Procedo?"
    if sv is not None and sv.fase == "analisi" and lav.file_utente is None:
        # Versione 2 (08/10): l'apertura esplicita e la specifica letta sempre, che chiude
        # l'analisi («Entriamo in modalità sviluppo per «…». Ho capito così: … Va bene così, o
        # la cambiamo?»). Prima la modalità non si vedeva (DGX, 08/10 11:06)
        frase = svc.sviluppi.frase_proposta(sv, lav)
        domanda = "Va bene così, o la cambiamo?"
        if ctx is not None:
            note_rule(ctx, "sviluppo_apertura")
    return _final(frase, fatto="proposta: il lavoro NON è ancora cominciato",
                  in_sospeso={"domanda": domanda, "cosa": f"affidare all'agente "
                              f"«{lav.titolo}»", "tool": tool,
                              "argomenti": {"proposta": lav.id}})


def _analisi(ctx, svc, prof, tipo: str, compito: str, crea, tool: str, nota: str = ""):
    """L'analisi della richiesta prima della proposta (06/10, calliope/agenti/richiesta.py).
    Restituisce (risultato, esito, gia_fatto_da):
    - risultato: da dare subito (domande, «c'è già», «impossibile qui»), o None per continuare;
    - esito: l'Esito (specifica e nome per la proposta), o None;
    - gia_fatto_da: il tool di un «c'è già» a cui la persona ha detto «sì, comunque».
    `crea(compito, esito)` crea il lavoro (per le risposte scritte nel modulo dello schermo)."""
    an = getattr(svc, "analizzatore", None)
    if an is None or not getattr(ctx.cfg, "agenti_analisi", True) or prof is None:
        return None, None, ""
    from ..agenti import richiesta as ar
    turno = int(getattr(ctx, "turno", 0) or 0)
    detto = (getattr(ctx, "user_text", "") or "").strip()
    rec = an.recente(prof.id, tipo, turno)
    senza = False
    if rec is not None:
        if rec["esito"] != "vaga":
            # Il «sì, comunque» dopo «c'è già» o «impossibile qui»: si procede come oggi
            note_rule(ctx, "analisi_gia_fatta")
            return None, None, (rec.get("tool") or "") if rec["esito"] == "gia_fatto" else ""
        # La risposta alle domande: si analizza di nuovo, senza altre domande
        senza = True
        try:
            from ..schermi.moduli import chiudi_per_voce
            chiudi_per_voce(ctx, tool)
        except Exception:  # noqa: BLE001 — lo schermo non deve fermare il tool
            pass
        nota = ((nota + " ") if nota else "") + (
            f"Prima richiesta: «{rec['compito']}». Domande fatte: {' '.join(rec['domande'])} "
            f"Risposta della persona: «{detto}».")
    e = an.analizza(tipo, compito, list(getattr(ctx, "storia", None) or []), detto,
                    getattr(ctx, "strumenti", None), nota, senza,
                    attesa=getattr(ctx, "attesa", None))
    note_rule(ctx, f"analisi_{e.esito}")
    an.log(f"[AGENTI] analisi della richiesta ({tipo}): {e.per_registro()}")
    if e.esito == "gia_fatto":
        reg = getattr(ctx, "strumenti", None)
        esiste = (reg.get(e.tool) is not None) if reg is not None and hasattr(reg, "get") \
            else e.tool in politica.CLASSI
        if not esiste or e.tool in ar.NON_FUNZIONI:
            e.esito = "chiara"          # un nome inventato non vale: si procede
        else:
            an.ricorda(prof.id, tipo, turno, compito, e)
            if tipo == "estensione":
                from .estensioni import _gia_fatto
                return _gia_fatto(ctx, compito, "", e.tool, e.come_chiederlo), e, ""
            esempio = e.come_chiederlo.strip().strip("«»\"' .?")
            frase = ("Questo lo so già fare" + (f": chiedimi pure «{esempio}»." if esempio
                                                else ".")
                     + " Vuoi comunque che lo affidi all'agente?")
            return {"ok": True, "fatto": f"NIENTE affidato: c'è già un tool che lo fa ({e.tool})",
                    "conferma": frase, "risposta_finale": frase,
                    "in_sospeso": {"domanda": frase, "cosa": "affidare comunque il lavoro",
                                   "tool": tool,
                                   "argomenti": {"tipo": "programma" if tipo == "codice"
                                                 else tipo, "compito": compito}}}, e, ""
    if e.esito == "estensione":
        # Cambiare o creare un'estensione non è un lavoro di codice (08/10): il modello richiama
        # sviluppo_apri (con modifica per una che c'è). Niente frase detta: continua lui
        from .estensioni import elenco_breve
        est = getattr(ctx, "estensioni", None)
        ci_sono = elenco_breve(est) if est is not None else ""
        return {"ok": False, "fatto": f"{NIENTE}: il lavoro NON è stato affidato",
                "errore": "è un'estensione: si crea o si cambia con sviluppo_apri",
                "cosa_fare": ("richiama sviluppo_apri con lo stesso compito"
                              + (f"; per cambiarne una che c'è, modifica = il suo nome tra "
                                 f"questi: {ci_sono}" if ci_sono else ""))}, e, ""
    if e.esito == "impossibile":
        an.ricorda(prof.id, tipo, turno, compito, e)
        return _final(ar.frase_impossibile(e.motivo), ok=False,
                      fatto=f"{NIENTE}: impossibile qui, il lavoro NON è stato affidato"), e, ""
    if e.esito == "vaga":
        an.ricorda(prof.id, tipo, turno, compito, e)
        frase = ar.frase_domande(e.domande)
        res = {"ok": True, "fatto": "domande: il lavoro NON è ancora cominciato",
               "conferma": frase, "risposta_finale": frase,
               "in_sospeso": {"domanda": frase, "cosa": "le risposte per la richiesta di lavoro",
                              "tool": tool,
                              "argomenti": ("compito = la richiesta di prima con le risposte "
                                            "della persona" + {"codice": ", tipo = programma",
                                                               "estensione": ", tipo = estensione"}
                                            .get(tipo, ""))}}
        # Tutte le domande anche sul modulo dello schermo personale, se c'è (moduli.offri)
        from ..schermi.moduli import campo
        frase_schermo = None
        if len(e.domande) > ar.MAX_DOMANDE_VOCE:
            frase_schermo = (ar.frase_domande(e.domande, schermo=True)
                             + " Puoi rispondere a voce o scrivere sullo schermo.")
        res["modulo"] = {"chiave": f"richiesta:{tipo}", "titolo": "Prima di cominciare",
                         "domanda": "Le risposte per il lavoro che hai chiesto",
                         "campi": [campo(f"d{i}", q, "testo") for i, q in
                                   enumerate(e.domande)],
                         **({"frase_schermo": frase_schermo} if frase_schermo else {})}
        domande = list(e.domande)

        def riprendi(valori, turno, pid=prof.id, domande=domande):
            # Le risposte scritte sullo schermo, senza il modello (schermi/moduli.py)
            an.dimentica(pid)
            dati = "; ".join(f"{q} {str(valori.get(f'd{i}') or '').strip()}"
                             for i, q in enumerate(domande) if valori.get(f"d{i}"))
            lav = crea(f"{compito}. Risposte di chi l'ha chiesto: {dati}", None)
            return _proponi(None, svc, lav, int(turno))
        from ..schermi.moduli import offri

        return offri(ctx, res, tool, riprendi), e, ""
    return None, e, ""


def _a_estensione(ctx, compito: str):
    """Il risultato di sviluppo_apri con modifica = l'estensione che il compito di un lavoro
    di codice nomina («…dell'estensione 'Meteo per città'…»), o None. Solo con la parola
    «estensione» e il titolo (o il nome) di un'estensione che c'è: «un programma che legge il
    meteo per città» resta un programma."""
    est = getattr(ctx, "estensioni", None)
    if est is None or not re.search(r"(?<![a-zà-ù])estension[ei]", compito or "", re.I):
        return None
    try:
        nomi = est.nominate(compito, tutte=True)
    except Exception:  # noqa: BLE001 — nel dubbio, il lavoro di codice come prima
        return None
    if len(nomi) != 1:
        return None
    note_rule(ctx, "delega_estensione")
    from .estensioni import _estensione_crea
    return _estensione_crea(ctx, compito=compito, modifica=nomi[0]["nome"])


def _titolo_estensione(nome: str, esito) -> str:
    """Il nome del lavoro di un'estensione (06/10: «estensione che» per L1): il nome detto,
    o quello dell'analisi; vuoto per il titolo di sempre."""
    for t in (nome, getattr(esito, "nome", "") if esito is not None else ""):
        t = re.sub(r"\s+", " ", str(t or "")).strip(" .«»\"'")
        if t:
            return " ".join(t.split()[:6])
    return ""


def _avvia(ctx, svc, lav) -> dict:

    _schermo(ctx, lav)
    frase = svc.avvia(lav)
    # La modalità sviluppo (08/10): il «sì» alla specifica, si passa allo sviluppo
    from .sviluppo import su_avvio
    su_avvio(ctx, svc, lav)
    return _final(frase, fatto="avviato in secondo piano: NON è ancora finito",
                  lavoro=lav.id, titolo=lav.titolo)


def _delega_lavoro(ctx: ToolContext, tipo: str = "", compito: str = "", formato: str = "",
                   modello: str = "", vincoli: str = "", proposta: str = "", file: str = "",
                   allegato=None, **altro) -> dict:
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _final("Qui non posso affidare lavori a un agente: non è configurato.", ok=False,
                      fatto=NIENTE)
    turno = int(getattr(ctx, "turno", 0) or 0)
    serve = getattr(ctx.cfg, "agenti_livello_codice", "amministra")
    if str(tipo or "").strip().lower() == "codice" and RANK.get(_level(ctx), 0) < RANK.get(
            serve, 2):
        # Scritto da uno schermo personale: il codice all'agente vuole la voce (03/10)
        voce = serve_la_voce(ctx, "sviluppo_apri", {"tipo": "programma", "compito": compito},
                             "affidare un programma all'agente", serve)
        if voce is not None:
            return voce
    detto = getattr(ctx, "user_text", "") or ""
    level = _level(ctx)
    prof = _person(ctx)
    # Solo un id di lavoro proposto («L3») avvia una proposta: il 02/10 gemma4 metteva «Sì»
    # in un parametro che si chiamava «conferma» già alla prima richiesta. Un valore che
    # non è un id si ignora e la richiesta vale come nuova
    proposta = str(proposta or "").strip()
    if proposta and not re.fullmatch(r"L\d+", proposta):
        note_rule(ctx, "lavori_proposta_non_id")
        proposta = ""
    # Confermata alla domanda della politica (06/10): è la richiesta nuova di quella domanda,
    # anche se il modello ci aggiunge un id che non è di un'offerta del tool
    if proposta and politica.accettata(ctx) and not _offerta_di(ctx, svc, proposta):
        proposta = ""
    if proposta:
        chi = getattr(prof, "id", None)
        off = svc.offerta(chi, turno) if hasattr(svc, "offerta") else None
        if off is None or off["lavoro"].id != proposta:
            return _rifiuto(ctx, "Prima devo dirti cosa affido all'agente e avere il tuo sì: "
                                 "chiedimelo di nuovo.", "lavori_senza_offerta")
        # Il permesso prima di consumare la proposta: un «sì» che non basta non la perde
        # (04/10: la perdeva, e il «sì» successivo riceveva «chiedimelo di nuovo»)
        prof, why = _permesso(ctx, off["lavoro"].tipo, rigido=False,
                              args={"proposta": proposta, **({"file": file} if file else {})})
        if prof is None and getattr(off["lavoro"], "gioco", False) and not isinstance(why, dict):
            # Un gioco nuovo (05/10): anche un familiare adulto (tools/estensioni.py)
            from .estensioni import _permesso_gioco
            prof, why = _permesso_gioco(ctx, rigido=False)
        if prof is None:
            return _no(ctx, why, "lavori_permesso")
        lav = svc.conferma(chi, proposta, turno)
        if lav is None:
            return _rifiuto(ctx, "Prima devo dirti cosa affido all'agente e avere il tuo sì: "
                                 "chiedimelo di nuovo.", "lavori_senza_offerta")
        if lav.file_candidati and not _scegli(lav, file):
            return _proponi(ctx, svc, lav, turno)     # quale file? si richiede
        return _avvia(ctx, svc, lav)
    tipo = str(tipo or "").strip().lower()
    tipo = tipo if tipo in TIPI else "altro"
    compito = str(compito or "").strip() or detto.strip()
    if not compito:
        return {"ok": False, "fatto": NIENTE, "errore": "manca il compito",
                "cosa_fare": "chiedi in breve cosa deve fare l'agente"}
    # Un minore (05/10): un tema o un compito diventa una scaletta (lo decide l'agente)
    from .. import minori
    compito = compito + minori.nota_documento(ctx)
    richiesta = {k: v for k, v in {"tipo": tipo, "compito": compito, "formato": formato,
                                   "modello": modello, "vincoli": vincoli,
                                   "file": file}.items() if v}
    # Il modello richiama lavoro_affida (senza conferma) dopo il «sì» alla proposta: è la
    # stessa scelta in un'altra forma, e vale come conferma (stesso tipo, compito simile)
    off = svc.offerta(getattr(prof, "id", None), turno) if hasattr(svc, "offerta") else None
    implicita = (off is not None and off["lavoro"].tipo == tipo and difflib.SequenceMatcher(
        None, off["lavoro"].compito.lower(), compito.lower()).ratio() >= 0.6)
    # Prima senza la voce: un «sì» breve dopo la proposta (conferma implicita, qui sotto) vale
    # come il «sì» con proposta=id, che non la chiede. Fino al 03/10 il controllo rigido
    # veniva prima e «Sì, vai.» riceveva «non ti ho riconosciuto bene dalla voce»
    # (prova_agenti_ollama sulla DGX, 4B)
    prof, why = _permesso(ctx, tipo, rigido=False,
                          args={"proposta": off["lavoro"].id} if implicita else richiesta)
    if prof is None:
        return _no(ctx, why, "lavori_permesso")
    # Senza un container il codice dell'agente non si esegue (03/10, analisi di sicurezza):
    # meglio dirlo subito che dopo minuti di lavoro
    iso = getattr(svc, "isolamento", None)
    if tipo == "codice" and iso is not None and not getattr(iso, "pronto", True):
        return _guasto(ctx, "Adesso non posso fare lavori di programmazione: il codice "
                            "dell'agente lo eseguo solo in un ambiente isolato, e qui adesso "
                            "non è pronto.", "lavori_codice_senza_sandbox")
    if implicita:
        lav = svc.conferma(prof.id, off["lavoro"].id, turno)
        if lav is not None:
            note_rule(ctx, "lavori_conferma_implicita")
            if lav.file_candidati and not _scegli(lav, file):
                return _proponi(ctx, svc, lav, turno)
            return _avvia(ctx, svc, lav)
    # Uno sviluppo aperto (08/10, modalità sviluppo): niente lavori nuovi dell'agente finché
    # non è chiuso o sospeso (decisione di Dario), salvo il programma di quello sviluppo
    from .sviluppo import apri_se_serve, controlla_nuovo
    blocco = controlla_nuovo(ctx, "lavoro_affida", {"tipo": tipo})
    if blocco is not None:
        return blocco
    # Una richiesta nuova di codice vuole la voce riconosciuta in questa frase
    prof, why = _permesso(ctx, tipo, rigido=True, args=richiesta)
    if prof is None:
        return _no(ctx, why, "lavori_permesso")
    guasto = svc.collegamento_guasto()
    if guasto is not None:
        svc.verifica_in_secondo_piano()
        return _guasto(ctx, f"Adesso non posso: {guasto['motivo']}. "
                            f"{guasto['passo']}".strip(), "lavori_agente_irraggiungibile")
    modello = str(modello or "").strip()
    if modello and modello not in svc.modelli:
        modello = ""
    if modello:
        tipo = "documento"
    fmt = str(formato or "").strip().lower()
    fmt = fmt if fmt in ("word", "excel", "pdf") else ""
    # Un file della persona (03/10): si cerca ora, con le regole dei file del PC; la copia
    # parte solo dopo il «sì», in secondo piano
    candidati = []
    if allegato not in (None, ""):
        # Un file allegato alla conversazione (05/10): già in memoria, niente ricerca sul PC
        candidati, rifiuto = _da_allegato(ctx, prof, allegato)
        if rifiuto is not None:
            return rifiuto
    elif str(file or "").strip():
        candidati, rifiuto = _trova_file(ctx, prof, str(file))
        if rifiuto is not None:
            if "NON" in str(rifiuto.get("fatto", "")) and "proprietario" in str(
                    rifiuto.get("motivo", "")):
                note_rule(ctx, "lavori_file_permesso")
            return rifiuto
    dati = list(getattr(ctx, "storia", None) or [])
    if detto and detto.strip() != compito:
        dati.append(("user", detto.strip()))

    def crea(compito_agente: str, esito=None):
        v = str(vincoli or "")
        if esito is not None and esito.esito == "raffinabile":
            v = (v + " " if v else "") + f"Richiesta come detta dalla persona: «{compito}»."
        lv = svc.nuovo(tipo, compito_agente, prof.id, prof.name, level, fmt, modello, v, dati)
        if compito_agente != compito and not modello:
            from ..agenti.servizio import senza_estensione, titolo_da
            lv.titolo = titolo_da(compito)
            if tipo == "codice":
                lv.titolo = senza_estensione(lv.titolo)
        if esito is not None and esito.esito == "raffinabile":
            lv.specifica = esito.specifica
        if candidati:
            lv.file_candidati = candidati
            if len(candidati) == 1:
                _scegli(lv, "1")
        return lv

    # Un lavoro di codice che cambia un'estensione che c'è (08/10, DGX del 07/10: «Modifica la
    # logica dell'estensione 'Meteo per città'…» con lavoro_affida → l'analisi diceva
    # «impossibile: non posso modificare le estensioni»). Le estensioni si cambiano con
    # sviluppo_apri (una versione nuova da approvare): la stessa richiesta, già confermata
    # alla domanda della politica, passa a lei. Regola `delega_estensione`
    if tipo == "codice" and not modello and not candidati:
        da_estensione = _a_estensione(ctx, compito)
        if da_estensione is not None:
            return da_estensione
    if tipo == "codice" and not modello:
        # Un programma di chi amministra è uno sviluppo (08/10): si apre qui, in analisi
        from ..agenti.servizio import senza_estensione, titolo_da
        apri_se_serve(ctx, "codice", compito, titolo=senza_estensione(titolo_da(compito)))
    # L'analisi della richiesta prima della proposta (06/10): solo i lavori di codice
    esito = None
    if tipo == "codice" and not modello:
        nota = ""
        if candidati:
            nota = ("La persona dà all'agente il file " + ", ".join(
                c["detto"] for c in candidati[:3]) + ": è l'input del programma.")
        ris, esito, _ = _analisi(ctx, svc, prof, tipo, compito, crea, "sviluppo_apri", nota)

        if ris is not None:
            if esito is not None and esito.esito in ("impossibile", "gia_fatto", "estensione"):
                from .sviluppo import chiudi_se_vuoto
                chiudi_se_vuoto(ctx, esito.esito)
            return ris
    compito_agente = esito.specifica if esito is not None and esito.esito == "raffinabile" \
        else compito
    lav = crea(compito_agente, esito)
    raffinata = bool(getattr(lav, "specifica", ""))


    # Una conferma per azione (06/10, caso vero della DGX: conferma della politica per la foto,
    # sfida, poi ancora «Procedo?»): se la persona ha già confermato proprio questa richiesta
    # alla domanda della politica, la proposta vale come accettata. Non con un file della
    # persona: lì la domanda dice anche che il file lascia il PC
    if svc.serve_conferma(lav):
        # (né con una specifica raffinata dall'analisi: la persona non l'ha ancora sentita)
        if not politica.accettata(ctx) or candidati or raffinata:
            return _proponi(ctx, svc, lav, turno)
        # (nel registro basta `politica_conferma_unica`, scritta dalla politica)
    return _avvia(ctx, svc, lav)


def _lavoro_affida(ctx: ToolContext, tipo: str = "", **altro) -> dict:
    """lavoro_affida (08/10, versione 2): i lavori che non sono codice. Un tipo codice (il
    modello che sbaglia tool, una conversazione di prima del 08/10) va a sviluppo_apri come
    programma: una conversione della forma di una scelta già fatta (principio 10), regola
    `lavoro_codice_sviluppo`. Una proposta («sì» a «Procedo?») vale com'è."""
    t = str(tipo or "").strip().lower()
    if t in ("codice", "programma", "script") and not str(altro.get("proposta") or "").strip() \
            and not str(altro.get("modello") or "").strip():
        note_rule(ctx, "lavoro_codice_sviluppo")
        from .sviluppo import _sviluppo_apri
        return _sviluppo_apri(ctx, tipo="programma", **{k: v for k, v in altro.items()
                                                       if k not in ("formato", "modello")})
    return _delega_lavoro(ctx, tipo=tipo, **altro)


def _lavori_stato(ctx: ToolContext) -> dict:
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _final("Qui non ci sono lavori affidati a un agente.", ok=False)
    prof = _person(ctx)
    admin = _level(ctx) == "amministra"
    frase = svc.stato(getattr(prof, "id", None), tutti=admin)
    att = svc.in_attesa(None if admin else getattr(prof, "id", None))
    if att and frase.endswith("?"):
        # «A che punto è?» → «aspetta una risposta: …?»: la risposta nel turno dopo vale
        return _final(frase, in_sospeso=svc.offerta_risposta(att[-1]))
    # Un lavoro interrotto da un riavvio (06/10, agenti/ripresa.py): «… lo rifaccio?»
    rip = (svc.offerta_ripresa(getattr(prof, "id", None)) if hasattr(svc, "offerta_ripresa")
           else None)
    if rip is not None and frase.endswith("?"):
        return _final(frase, in_sospeso=rip)
    if prof is None or not frase.endswith("."):
        return _final(frase)
    # Gli ultimi lavori finiti di chi parla, anche di prima di un riavvio (07/10, DGX: «e di
    # quelli che hai già fatto?» → «Non ho lavori in corso.» due volte, e la ricerca del giorno
    # prima c'era nella cartella dei risultati), e il risultato del più recente: «Vuoi sentire
    # il risultato?», il «sì» va a lavoro_risultato (prima: «E il risultato?» dopo lo stato
    # finiva in lavoro_rispondi)
    from ..agenti import risultato as ar
    try:
        fin = ar.recenti(svc, prof.id, prof.name, 3)
    except Exception:  # noqa: BLE001 — lo stato si dice comunque
        fin = []
    if not fin:
        return _final(frase)
    elenco = ar.elenco_detto(fin)
    attivi = svc.attivi(None if admin else prof.id, attesa=True)
    if attivi:
        return _final(f"{frase} {'Finito di recente' if len(fin) == 1 else 'Finiti di recente'}"
                      f": {elenco}.")
    if frase == "Non ho lavori in corso." or frase.startswith("Non ho lavori in corso. L'ultimo"):
        frase = "Non ho lavori in corso."
    note_rule(ctx, "lavori_stato_finiti")
    frase += (f" L'ultimo lavoro: {elenco}." if len(fin) == 1
              else f" Gli ultimi finiti: {elenco}.")
    fatto = next((lv for lv in fin if lv.stato == "fatto"), None)
    if fatto is None:
        return _final(frase)
    if fatto is fin[0] and getattr(fatto, "tipo", "") == "estensione":
        # «Com'è andata l'estensione?» (08/10, DGX del 07/10: «Vuoi sentire il risultato?»):
        # il risultato di un lavoro d'estensione è la versione da approvare
        est = _estensione_del_lavoro(ctx, fatto)
        if est is not None:
            return _final(f"{frase} {est[0]}", **({"in_sospeso": est[1]} if est[1] else {}))
    domanda = ("Vuoi sentire il risultato?" if fatto is fin[0]
               else f"Vuoi sentire il risultato di «{_titolo_detto(fatto.titolo)}»?")
    return _final(f"{frase} {domanda}", in_sospeso={
        "domanda": domanda, "tool": "lavoro_risultato",
        "cosa": f"il risultato di «{fatto.titolo}»", "argomenti": {"lavoro": ar.chiave(fatto)}})


def _estensione_del_lavoro(ctx, lav):
    """(frase, in_sospeso o None) per l'estensione preparata da un lavoro finito, o None."""
    r = (getattr(lav, "risultato", None) or {}).get("estensione") or {}
    est = getattr(ctx, "estensioni", None)
    nome, n = r.get("nome"), r.get("versione")
    if est is None or not nome or not n or est.archivio.voce(nome) is None:
        return None
    from ..estensioni.servizio import chi_e
    m = est.archivio.manifesto(nome, n) or {}
    voce = est.archivio.voce(nome) or {}
    if est.archivio.candidata(nome) == n:
        prima = est.archivio.manifesto(nome) if voce.get("attiva") else None
        cosa = chi_e(m, n, prima)
        return (f"Ha preparato {cosa}: è da approvare. Vuoi approvarla?",
                {"domanda": "Vuoi approvarla?", "cosa": f"approvare {cosa}",
                 "tool": "estensione_gestisci",
                 "argomenti": {"azione": "approva", "nome": nome}})
    if voce.get("attiva") == n and voce.get("stato") == "attiva":
        return (f"«{m.get('titolo', nome)}» è attiva, versione {n}.", None)
    return None


def _lavori_rispondi(ctx: ToolContext, lavoro: str = "", risposta: str = "") -> dict:
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _final("Qui non ci sono lavori affidati a un agente.", ok=False, fatto=NIENTE)
    prof = _person(ctx)
    if prof is None:
        return _rifiuto(ctx, "Non so chi sei: alle domande di un lavoro risponde solo chi l'ha "
                             "chiesto.", "lavori_permesso")
    testo = str(risposta or "").strip() or (getattr(ctx, "user_text", "") or "").strip()
    if not testo:
        return {"ok": False, "fatto": NIENTE, "errore": "manca la risposta",
                "cosa_fare": "chiedi la risposta alla domanda dell'agente"}
    lav, frase, altrui = svc.trova_in_attesa(prof.id, str(lavoro or ""),
                                             admin=_level(ctx) == "amministra")
    if lav is None:
        if altrui:
            return _rifiuto(ctx, frase, "lavori_risposta_altrui")
        if not svc.in_attesa():
            return _offri_risultato(ctx, svc, prof, frase)
        return _final(frase, ok=False, fatto=NIENTE)
    # Risposta arrivata a voce: il modulo della domanda sullo schermo si chiude (03/10)
    from ..schermi.moduli import chiudi_per_voce
    chiudi_per_voce(ctx, "lavoro_rispondi", f"lavoro:{lav.id}")
    frase = svc.rispondi(lav, testo)
    if frase is None:
        return _final("Quel lavoro non aspetta più una risposta.", ok=False, fatto=NIENTE)
    return _final(frase, fatto="risposta passata all'agente: il lavoro riprende, NON è ancora "
                               "finito", lavoro=lav.id)


# pdf e word (07/10): «fammene un PDF», il testo in Markdown convertito (agenti/risultato.converti)
MODI_RISULTATO = ("riassunto", "leggi", "mostra", "pdf", "word")


def _risultato_lavoro(ctx: ToolContext, lavoro: str = "", modo: str = "riassunto") -> dict:
    """Il risultato di un lavoro finito (07/10, agenti/risultato.py): riassunto a voce, più
    dettaglio col modello dell'agente, il testo intero sullo schermo personale."""
    from ..agenti import risultato as ar
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _final("Qui non ci sono lavori affidati a un agente.", ok=False, fatto=NIENTE)
    prof = _person(ctx)
    if prof is None:
        return _rifiuto(ctx, "Non so chi sei: il risultato di un lavoro lo sente solo chi l'ha "
                             "chiesto.", "lavori_permesso")
    modo = str(modo or "riassunto").strip().lower()
    modo = modo if modo in MODI_RISULTATO else "riassunto"
    admin = _level(ctx) == "amministra"
    lav, frase, altrui = ar.trova(svc, prof.id, prof.name, str(lavoro or ""), admin=admin)
    if lav is None:
        if altrui:
            return _rifiuto(ctx, frase, "risultato_lavoro_altrui")
        return _final(frase, ok=False, fatto=NIENTE)
    titolo = _titolo_detto(lav.titolo)
    testo = ar.testo_intero(lav)
    if modo in ("pdf", "word"):
        # «Fammene un PDF / un Word» (07/10): Markdown → blocchi → render, poi come un documento
        # di Calliope (al portatile con «Lo apro?», o nella cartella del lavoro)
        if lav.tipo in ("codice", "estensione"):
            return _final(f"«{titolo}» è un programma: il codice non lo converto in "
                          f"{'PDF' if modo == 'pdf' else 'Word'}.", ok=False, fatto=NIENTE)
        note_rule(ctx, f"risultato_{modo}")
        out = ar.converti(svc, lav, testo, modo,
                          attesa_s=float(getattr(ctx.cfg, "documenti_attesa_s", 8.0) or 8.0))
        extra = {"in_sospeso": out["in_sospeso"]} if out.get("in_sospeso") else {}
        return _final(out["frase"], ok=bool(out.get("ok")),
                      fatto=out.get("fatto") or NIENTE, lavoro=lav.id, **extra)
    # Sullo schermo personale di chi chiede, se c'è: sempre il testo intero
    sullo_schermo = False
    hub = getattr(ctx, "schermi", None)
    card = ar.scheda(svc, lav, testo) if hub is not None else None
    if card:
        try:
            sender = hub.mittente(ctx)
            # Il risultato è di chi l'ha chiesto e va solo sui suoi schermi personali: anche
            # quando la voce di questa frase è nella zona grigia («Entrambe le cose.», frase
            # breve che vale per la conversazione, DGX del 07/10: il riassunto si diceva a
            # voce e la scheda no). Nessuno schermo d'altri, nessuna scheda di un altro
            if (getattr(sender, "persona", None) is not None
                    and sender.persona == getattr(lav, "persona", None)
                    and getattr(sender, "certo", True) is False):
                sender.certo = True
                note_rule(ctx, "risultato_schermo_proprio")
                # Ma senza «Scarica» (07/10): dalla zona grigia non si scarica mai
                card = {k: v for k, v in card.items() if k not in ("scarica", "_scarica")}
            esito = hub.invia(card, sender, forza=True)
            sullo_schermo = bool(esito.get("schermi") or esito.get("destinatari"))
            if sullo_schermo:
                ctx.scheda_risultato = (getattr(ctx, "turno", 0),
                                        getattr(ctx, "user_text", ""), card, sender)
        except Exception:  # noqa: BLE001 — lo schermo non ferma la voce
            sullo_schermo = False
    dove = ("Il testo intero è sul tuo schermo." if sullo_schermo
            else "Il testo intero è nella cartella Lavori dei Documenti.")
    if modo == "mostra" and sullo_schermo:
        note_rule(ctx, "risultato_mostra")
        return _final(f"Te l'ho mandato sullo schermo: «{titolo}».", fatto="mostrato sullo "
                      "schermo", lavoro=lav.id)
    salvato = ar.riassunto_salvato(lav)
    if lav.tipo in ("codice", "estensione"):
        # Il codice non si legge mai a voce
        frase = (f"«{titolo}»: {salvato.rstrip('.')}." if salvato else f"«{titolo}» è finito.")
        frase += (" Il codice è sul tuo schermo." if sullo_schermo else
                  " Il codice non lo leggo a voce: è nella cartella Lavori dei Documenti.")
        return _final(frase, fatto="letto il riassunto", lavoro=lav.id)
    sintesi, come = salvato, "salvato"
    # Il riassunto salvato già sentito (l'annuncio del lavoro finito lo dice, e così una
    # risposta di prima): ripeterlo non è una risposta a «dammi un bel riassunto» (07/10)
    gia = _gia_detto(ctx, salvato)
    if gia:
        note_rule(ctx, "risultato_gia_detto")
    if testo and (modo != "riassunto" or len(salvato) < 80 or gia):
        detta, esito = ar.riassunto_voce(
            svc, lav, testo, getattr(ctx, "user_text", "") or "",
            frasi="da quattro a sei" if modo == "leggi" else "due o tre",
            tempo_s=float(getattr(ctx.cfg, "agenti_risultato_s", 15.0) or 15.0),
            attesa=getattr(ctx, "attesa", None))
        if detta:
            sintesi, come = detta, "modello"
        else:
            note_rule(ctx, "risultato_ripiego")
            getattr(svc, "log", print)(f"[AGENTI] riassunto di {lav.id} per la voce: {esito}")
    if not sintesi:
        return _final(f"«{titolo}» è finito, ma l'agente non ha lasciato un riassunto. {dove}",
                      fatto="niente riassunto", lavoro=lav.id)
    pre = "Non vedo un tuo schermo, quindi te lo dico: " if modo == "mostra" else ""
    frase = f"{pre}«{titolo}»: {sintesi.rstrip()}"
    if not frase.endswith((".", "!", "?")):
        frase += "."
    frase += " " + dove
    if come == "salvato" and testo and modo == "riassunto":
        from ..riferire import FRASE_PIU_DETTAGLI
        frase += " " + FRASE_PIU_DETTAGLI
    # Il testo è dell'agente (dato non fidato): numeri a pagamento, codici, soldi e indicazioni
    # sulla casa non si ripetono (come l'annuncio, calliope/riferire.py)
    try:
        from .. import riferire
        frase, regole = riferire.controlla_testo(frase, "agente", getattr(ctx, "user_text", "")
                                                 or "", str(lav.titolo))
        for r in regole:
            note_rule(ctx, r)
    except Exception:  # noqa: BLE001 — il controllo dell'uscita resta anche nel ciclo
        pass
    note_rule(ctx, f"risultato_{come}")
    return _final(frase, fatto="detto il risultato", lavoro=lav.id)


def _gia_detto(ctx, frase: str) -> bool:
    """La frase (il riassunto salvato) è già in una risposta della conversazione recente."""
    def norm(t):
        return re.sub(r"[^a-z0-9à-ù]+", "", str(t or "").lower())
    n = norm(frase)[:80]
    if len(n) < 30:
        return False
    return any(r == "assistant" and n in norm(c) for r, c in getattr(ctx, "storia", None) or ())


def _titolo_detto(titolo: str) -> str:
    from ..agenti.servizio import titolo_detto
    return titolo_detto(titolo)


def _offri_risultato(ctx, svc, prof, frase: str) -> dict:
    """La frase di un rifiuto di programma_esegui o lavoro_rispondi quando il lavoro finito è una
    ricerca o un documento (07/10, caso vero della DGX: «leggili e dammi un riassunto» →
    programma_esegui «Non ho programmi finiti da eseguire», due volte): si dice cos'è e si
    propone il risultato, con l'azione in sospeso per il «sì»."""
    from ..agenti import risultato as ar
    lav, _, _ = ar.trova(svc, getattr(prof, "id", None), getattr(prof, "name", None), "",
                         admin=_level(ctx) == "amministra")
    if lav is None or lav.tipo in ("codice", "estensione"):
        return _final(frase, ok=False, fatto=NIENTE)
    note_rule(ctx, "lavori_offri_risultato")
    tipo = {"ricerca": "una ricerca", "documento": "un documento"}.get(lav.tipo, "un lavoro")
    domanda = f"«{_titolo_detto(lav.titolo)}» è {tipo}, non un programma: vuoi il risultato?"
    return _final(domanda, ok=False, fatto=NIENTE,
                  in_sospeso={"domanda": domanda, "tool": "lavoro_risultato",
                              "cosa": f"il risultato di «{lav.titolo}»",
                              "argomenti": {"lavoro": lav.id}})


def _dati(dati) -> list[str]:
    """I dati per il programma come li passa il modello: un elenco, o una frase («3 e 5»,
    «3, 5»): si separano a spazi, virgole e punti e virgola (una conversione di forma)."""
    if isinstance(dati, (int, float)):
        return [str(dati)]
    if isinstance(dati, str):
        # Una frase sola: i valori separati come detti. Un elenco resta com'è (un elemento
        # può essere una frase con gli spazi)
        return [x for x in re.split(r"\s*[;,]\s*|\s+e\s+|\s+", dati.strip()) if x][:20]
    return [str(d).strip() for d in (dati or []) if str(d).strip()][:20]


def _lavori_esegui(ctx: ToolContext, lavoro: str = "", dati=None) -> dict:
    svc = getattr(ctx, "lavori", None)
    esec = getattr(svc, "esecuzioni", None)
    if svc is None or esec is None:
        return _final("Qui non ci sono lavori affidati a un agente.", ok=False, fatto=NIENTE)
    prof = _person(ctx)
    if prof is None:
        return _rifiuto(ctx, "Non so chi sei: un programma lo esegue solo chi l'ha chiesto.",
                        "lavori_permesso")
    admin = _level(ctx) == "amministra"
    lav = esec.ultimo_lavoro(prof.id, admin=admin, quale=str(lavoro or ""))
    if lav is None:
        altri = esec.ultimo_lavoro(None, admin=True, quale=str(lavoro or ""))
        if altri is not None and altri.persona != prof.id:
            return _rifiuto(ctx, "Quel programma l'ha chiesto un altro: può eseguirlo solo lui o "
                                 "chi amministra.", "lavori_permesso")
        return _offri_risultato(ctx, svc, prof, "Non ho programmi finiti da eseguire: prima "
                                                "chiedimi di scriverne uno.")
    hub = getattr(ctx, "schermi", None)
    on_scheda = None
    if hub is not None:
        sender = hub.mittente(ctx)
        # Chiesto a voce: la scheda va anche con le schede automatiche spente
        on_scheda = lambda card: hub.invia(card, sender, forza=True)  # noqa: E731
    es, frase = esec.avvia(lav, _dati(dati), on_scheda=on_scheda, persona=prof.id,
                           persona_nome=prof.name)
    if es is None:
        return _final(frase, ok=False, fatto=NIENTE)
    finita = esec.attendi(es, float(getattr(ctx.cfg, "agenti_esecuzione_attesa_s", 4.0)))
    if finita:
        return _final(esec.frase(es), fatto="eseguito", lavoro=lav.id, esecuzione=es.id)
    frase = ("Lo sto eseguendo: guardalo sullo schermo, ti dico come finisce."
             if es.sullo_schermo else "Lo sto eseguendo: ti dico come finisce.")
    return _final(frase, fatto="in esecuzione: NON è ancora finito", lavoro=lav.id,
                  esecuzione=es.id)


def _lavori_annulla(ctx: ToolContext, quale: str = "ultimo") -> dict:
    svc = getattr(ctx, "lavori", None)
    if svc is None:
        return _final("Qui non ci sono lavori affidati a un agente.", ok=False, fatto=NIENTE)
    prof = _person(ctx)
    if prof is None:
        return _rifiuto(ctx, "Non so chi sei: un lavoro lo può fermare solo chi l'ha chiesto.",
                        "lavori_permesso")
    # «Fermalo» mentre un programma gira sullo schermo (04/10): prima il programma, che è la
    # cosa che si vede; il lavoro dell'agente con «ferma il lavoro» quando il programma non c'è
    esec = getattr(svc, "esecuzioni", None)
    if esec is not None and str(quale or "").lower() != "tutti":
        fermate = esec.ferma(prof.id, admin=_level(ctx) == "amministra")
        if fermate:
            note_rule(ctx, "lavori_ferma_esecuzione")
            return _final("Ho fermato il programma.", fatto="programma fermato")
    res = svc.annulla(prof.id, tutti_di_tutti=_level(ctx) == "amministra",
                      quale="tutti" if str(quale or "").lower() == "tutti" else "ultimo")
    return _final(res["frase"], ok=res["ok"], **({} if res["ok"] else {"fatto": NIENTE}))


def agenti_specs(formati=("word", "excel", "pdf"), modelli=(),
                 file_pc: bool = False, archivio: bool = False,
                 allegati: bool = False) -> list[ToolSpec]:
    """I sei tool; `modelli`: i nomi dei modelli di documento (template) che ci sono;
    `file_pc`: c'è un PC con la ricerca dei file (il parametro `file` di lavoro_affida);
    `archivio`: le ricerche possono interrogare il grafo dei documenti di casa."""
    props = {"tipo": {"type": "string", "enum": list(TIPI_AFFIDA)},
             "compito": {"type": "string"},
             "vincoli": {"type": "string"},
             "proposta": {"type": "string"}}
    if file_pc:
        props["file"] = {"type": "string"}
    if allegati:
        props["allegato"] = {"type": "integer"}
    formati = [f for f in ("word", "excel", "pdf") if f in set(formati or ())]
    if formati:
        props["formato"] = {"type": "string", "enum": formati}
    modelli = sorted(modelli or ())
    if modelli:
        props["modello"] = {"type": "string", "enum": modelli}
    mod_txt = (f" Modelli di documento che ci sono: {', '.join(modelli)} (modello)."
               if modelli else "")
    # Le domande sui documenti di casa che archivio_cerca e archivio_somma non coprono
    # (confronti, più documenti insieme) vanno all'agente come ricerca
    arch_txt = (" Anche le domande complesse sui documenti di casa archiviati, che mettono "
                "insieme più documenti o confrontano periodi (tipo ricerca)." if archivio else "")
    return [
        ToolSpec(
            name="lavoro_affida",
            description=(
                "Affida a un agente in secondo piano un lavoro lungo il cui risultato è un "
                "file complesso: relazioni, presentazioni o documenti di più pagine o da un "
                "modello (tipo documento), ricerche a più passi (tipo ricerca). NON per il "
                "codice (script, programmi) né per le funzioni permanenti di Calliope "
                "(estensioni): quelli sono sviluppo_apri, anche se è stato rifiutato. NON per "
                "domande brevi e spiegazioni "
                "(«come si scrive un ciclo for?»): rispondi tu. NON per lettere, tabelle ed "
                "elenchi semplici: documento_crea. compito: tutto quello che serve, con i dati "
                "come detti. vincoli: facoltativo. Se il risultato finisce con «Procedo?», "
                "solo dopo il sì richiamalo con proposta = l'id proposto (es. «L3»)."
                + (" file: solo se il lavoro è su un file della persona che sta sul PC "
                   "(«riassumimi il PDF del contratto», "
                   "«aggiungi una colonna al foglio spese.xlsx»): il nome del file come detto, "
                   "o il numero di un risultato dell'ultima pc_cerca_file. Ne mando una copia "
                   "all'agente solo dopo il sì." if file_pc else "")
                + (" allegato: il numero di un file allegato in questa conversazione, se il "
                   "lavoro è su quel file («dallo all'agente», «riassumilo»)."
                   if allegati else "")
                + " NON per leggere o riassumere il risultato di un lavoro già finito: "
                  "lavoro_risultato."
                + mod_txt + arch_txt),
            parameters={"type": "object", "properties": props,
                        "required": ["tipo", "compito"]},
            func=_lavoro_affida, risk="azione", levels=FAMILY),
        ToolSpec(
            name="lavoro_stato",
            description=("Dice a che punto sono i lavori affidati all'agente "
                         "(«a che punto è il programma?», «hai finito la relazione?») e quali "
                         "sono finiti di recente, anche nei giorni prima («e quelli che hai già "
                         "fatto?», «quali lavori hai finito?»). NON quando chiede il risultato "
                         "o il contenuto di un lavoro finito, anche nominato («e il risultato "
                         "della ricerca sulle pompe di calore?», «cosa ha trovato?»): quello è "
                         "lavoro_risultato, con lavoro = le parole del titolo."),
            parameters={"type": "object", "properties": {}, "required": []},
            func=_lavori_stato, risk="lettura", levels=FAMILY),
        ToolSpec(
            name="lavoro_annulla",
            description=("Ferma un lavoro affidato all'agente («ferma il "
                         "lavoro», «annulla il programma»), o il programma che sto eseguendo "
                         "sullo schermo («fermalo»). quale: ultimo (predefinito) o tutti."),
            parameters={"type": "object",
                        "properties": {"quale": {"type": "string", "enum": ["ultimo", "tutti"]}},
                        "required": []},
            func=_lavori_annulla, risk="azione", levels=FAMILY),
        ToolSpec(
            name="programma_esegui",
            description=("Solo per i programmi: esegue di nuovo il programma scritto "
                         "dall'agente in un lavoro di codice finito e ne mostra l'uscita sullo "
                         "schermo («fammelo vedere», "
                         "«eseguilo di nuovo», «eseguilo con 3 e 5»). dati: i valori detti o "
                         "scritti, uno per elemento (vuoto = senza dati); lavoro: id (es. «L3») "
                         "o vuoto per l'ultimo. «Fermalo» è lavoro_annulla. È anche il modo di "
                         "usare di nuovo un programma dell'agente: non ha un comando a voce "
                         "suo. NON per ricerche e documenti: il loro risultato è "
                         "lavoro_risultato."),
            parameters={"type": "object",
                        "properties": {"lavoro": {"type": "string"},
                                       "dati": {"type": "array", "items": {"type": "string"}}},
                        "required": []},
            func=_lavori_esegui, risk="azione", levels=FAMILY),
        ToolSpec(
            name="lavoro_rispondi",
            description=("Solo quando l'agente ha fatto una domanda e il lavoro la aspetta: "
                         "gli dà la risposta («il cliente è Rossi», anche solo «Rossi»). lavoro: "
                         "id (es. «L3») o vuoto se ce n'è uno solo; risposta: quello che ha "
                         "detto chi parla, con i dati come detti. NON per avere il risultato di "
                         "un lavoro finito: lavoro_risultato."),
            parameters={"type": "object",
                        "properties": {"lavoro": {"type": "string"},
                                       "risposta": {"type": "string"}},
                        "required": ["risposta"]},
            func=_lavori_rispondi, risk="azione", levels=FAMILY),
        ToolSpec(
            name="lavoro_risultato",
            description=("Il risultato di un lavoro dell'agente già finito: cosa ha trovato o "
                         "scritto («e il risultato?», «cosa ha trovato?», «e il risultato "
                         "della ricerca sulle pompe di calore?», «leggimelo», "
                         "«fammi un riassunto della ricerca», «mostramelo sullo schermo»). "
                         "modo: riassunto (predefinito), leggi (più dettagliato, a voce), "
                         "mostra (il testo intero sullo schermo), pdf o word (ne fa un file: "
                         "«fammene un PDF», «lo voglio in Word»). lavoro: id (es. «L3») o "
                         "parole del titolo, vuoto per l'ultimo."),
            parameters={"type": "object",
                        "properties": {"lavoro": {"type": "string"},
                                       "modo": {"type": "string", "enum": list(MODI_RISULTATO)}},
                        "required": []},
            func=_risultato_lavoro, risk="lettura", levels=FAMILY),
    ]
