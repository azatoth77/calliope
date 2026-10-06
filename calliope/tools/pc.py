"""
I tool pc_*: il PC comandato a voce (calliope/pc/, docs/ricerche/2026-09-26-controllo-pc.md).

Otto tool deterministici, ognuno con un verbo in un enum piccolo (la ricerca del 26/09:
un meta-tool generico scendeva al 90 %). I valori arrivano come detti a voce e si
convertono qui («un po' più alto» = +passo, «la settimana scorsa» con tempi.py). Ogni
risultato ha una `conferma` già pronta.

Permessi (sezione 3 della ricerca), oltre al filtro per livello del registro:
- letture e azioni reversibili: familiare (volume e musica anche l'ospite, se
  `pc_ospite_volume_media`);
- programmi aperti, ricerca e apertura di file: solo il proprietario del PC
  (`pc_proprietari`) o chi amministra, con la voce riconosciuta in questo turno (non
  nella zona grigia della conversazione): rivelano cosa fa una persona;
- a schermo bloccato: niente app, file, ricerca, programmi aperti (lo fa l'esecutore).
I rifiuti dicono «NON è stata eseguita», come quelli del registro: con un semplice «non
permesso» il modello diceva comunque «fatto».

Con l'esecutore remoto (calliope/pc/remoto.py, Calliope sulla DGX e il portatile come
satellite, 03/10) i tool ci sono sempre, con tutte le capacità: se il satellite non è
collegato, è vecchio o non ha quella capacità, il tool lo dice (`_fuori`) invece di sparire.
"""

import re

from ..pc import COMANDI_MEDIA, TIPI_FILE
from ..tempi import parse_past_range, word_number
from .spec import ToolSpec, ToolContext, note_rule
from ..testi import ALL, FAMILY, MESI, NIENTE


def _rifiuto(motivo: str, cosa_dire: str) -> dict:
    return {"ok": False, "fatto": NIENTE, "motivo": motivo, "cosa_dire": cosa_dire}


def _pc(ctx: ToolContext, pc: str | None):
    """(nome, esecutore) del PC chiesto; il primo se non è detto (oggi ce n'è uno)."""
    pcs = getattr(ctx, "pc", None) or {}
    if not pcs:
        return None, None
    if pc:
        key = str(pc).strip().lower()
        for name, ex in pcs.items():
            if name.lower() == key:
                return name, ex
    name = next(iter(pcs))
    return name, pcs[name]


def _call(name: str, fn, *args, **kwargs) -> dict:
    """Chiama l'esecutore: un guasto (libreria, timeout, la rete verso il satellite) diventa
    un errore leggibile, non un'eccezione."""
    try:
        return fn(*args, **kwargs)
    except TimeoutError:
        return {"ok": False, "errore": f"il {name} non ha risposto in tempo",
                "cosa_dire": f"di' in breve che il {name} non ha risposto in tempo: non sai "
                             f"se l'ha fatto, quindi non dire che è fatto"}
    except ConnectionError as e:          # esecutore remoto: satellite scollegato a metà
        return _scollegato(name, str(e))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "errore": f"sul {name} non ha funzionato: {e}"}


def _scollegato(name: str, motivo: str) -> dict:
    return {"ok": False, "fatto": NIENTE, "errore": motivo or f"il {name} non è collegato",
            "cosa_dire": f"di' in breve che adesso non raggiungi il {name}: {motivo}"}


_CAP_DETTA = {"volume": "regolare il volume", "media": "comandare la musica",
              "luminosita": "regolare la luminosità", "app": "aprire programmi",
              "blocco": "bloccare lo schermo", "ricerca": "cercare file"}


def _fuori(name, ex, cap: str | None = None) -> dict | None:
    """None se il PC c'è e sa fare `cap`; altrimenti il rifiuto da dire. Serve all'esecutore
    remoto, i cui tool restano anche senza satellite (prefisso del prompt stabile)."""
    if ex is None:
        return {"ok": False, "errore": "nessun PC collegato"}
    collegato = getattr(ex, "collegato", None)
    if collegato is not None and not collegato():
        return _scollegato(name, ex.motivo_non_collegato())
    if cap and cap not in ex.capacita():
        return _rifiuto(f"sul {name} non posso {_CAP_DETTA.get(cap, cap)}: manca la libreria "
                        f"o il dispositivo", "dillo in breve, senza dire che è fatto")
    return None


def _profile(ctx: ToolContext):
    name = getattr(ctx.speaker_ctx, "current_speaker", None)
    return ctx.speakers.get(name) if name and ctx.speakers else None


def _owner(ctx: ToolContext) -> bool:
    """Chi parla può vedere i programmi e i file di questo PC? Chi amministra sì; gli
    altri solo se sono tra i proprietari e la voce è stata riconosciuta in questo turno
    (nella zona grigia vale la conversazione, e per i file non basta)."""
    sc = ctx.speaker_ctx
    if getattr(sc, "current_level", "ospite") == "amministra":
        return True
    prof = _profile(ctx)
    if prof is None or getattr(sc, "from_session", False):
        return False
    owners = {str(o).strip().lower() for o in (getattr(ctx.cfg, "pc_proprietari", None) or [])}
    return prof.id.lower() in owners or prof.name.lower() in owners


def _not_owner(name: str) -> dict:
    return _rifiuto(f"solo chi usa il {name} (il proprietario) o chi amministra può vedere "
                    f"i suoi programmi e i suoi file",
                    "spiega in breve che non puoi farlo per questa persona")


def _locked(name: str) -> dict:
    return _rifiuto(f"lo schermo del {name} è bloccato",
                    f"di' che il {name} è bloccato: va sbloccato a mano")


def _percent(n: int) -> str:
    return f"{n} per cento"


# ─────────────────────────── valori detti a voce ───────────────────────────

_ABSOLUTE = re.compile(r"\b(?:a|al|fino a|fino al|sul|sullo)\s+(\d{1,3}|\w+)\b", re.I)


def _number(text: str) -> int | None:
    m = re.search(r"\d{1,3}", text)
    if m:
        return int(m.group())
    for w in re.findall(r"\w+", text):
        n = word_number(w)
        if n is not None and w not in ("un", "uno", "una"):
            return n
    return None


def parse_amount(valore, passo: int, user_text: str = "",
                 ctx=None) -> tuple[str, int] | None:
    """Quanto alzare o abbassare, come detto → ("delta" | "assoluto", n).

    «un po'» = passo, «un pochino» = metà, «molto» = doppio, «20» = 20 in più o in meno,
    «a 20» / «al massimo» / «a metà» = valore assoluto. None = niente di detto (passo).
    La frase dell'utente serve quando il modello perde la preposizione: per «alza il
    volume a 50» manda a volte azione=alza, valore=50.
    """
    s = str(valore if valore is not None else "").strip().lower()
    if s in ("", "none", "null"):
        s = ""
    if re.search(r"\bmassim", s):
        return "assoluto", 100
    if re.search(r"\bminim", s):
        return "assoluto", 0
    if re.search(r"\bmet[àa]\b", s):
        return "assoluto", 50
    n = _number(s) if s else None
    if n is not None:
        absolute = bool(re.match(r"(a|al|fino a|fino al)\b", s))
        hint = _ABSOLUTE.search(user_text or "")
        # Solo se nella frase c'è un numero solo: «metti il volume a 30 e alza la
        # luminosità di 30» portava la luminosità a 30 invece di +30 (rapporto del 01/10)
        if hint and len(re.findall(r"\d+", user_text or "")) > 1:
            hint = None
        if hint and not absolute:
            h = hint.group(1)
            absolute = (int(h) if h.isdigit() else word_number(h)) == n
            if absolute:
                note_rule(ctx, "valore_assoluto_detto")
        return ("assoluto" if absolute else "delta"), n
    if re.search(r"pochin|poco poco|leggerment|appena", s):
        return "delta", max(1, passo // 2)
    if re.search(r"\b(molto|tanto|parecchio|decisamente)\b", s):
        return "delta", passo * 2
    return ("delta", passo) if s else None


def _target(azione: str, current: int, amount: tuple[str, int] | None, passo: int) -> int:
    kind, n = amount or ("delta", passo)
    if kind == "assoluto" or azione == "imposta":
        value = n
    else:
        value = current + n if azione == "alza" else current - n
    return max(0, min(100, int(value)))


_VOLUME_SYN = {"alza": "alza", "aumenta": "alza", "su": "alza", "più": "alza",
               "abbassa": "abbassa", "diminuisci": "abbassa", "riduci": "abbassa",
               "giù": "abbassa", "meno": "abbassa", "imposta": "imposta", "metti": "imposta",
               "muto": "muto", "silenzia": "muto", "silenzio": "muto", "disattiva": "muto",
               "riattiva": "riattiva", "attiva": "riattiva", "smuta": "riattiva",
               "togli muto": "riattiva", "togli il muto": "riattiva",
               "ripristina": "riattiva"}
_MEDIA_SYN = {"riproduci": "riproduci", "play": "riproduci", "riprendi": "riproduci",
              "continua": "riproduci", "suona": "riproduci", "avvia": "riproduci",
              "pausa": "pausa", "ferma": "pausa", "stop": "pausa", "metti in pausa": "pausa",
              "avanti": "avanti", "prossima": "avanti", "prossimo": "avanti",
              "successiva": "avanti", "successivo": "avanti", "salta": "avanti",
              "indietro": "indietro", "precedente": "indietro"}
_ORDINALS = {"primo": 1, "prima": 1, "secondo": 2, "seconda": 2, "terzo": 3, "terza": 3,
             "quarto": 4, "quarta": 4, "quinto": 5, "quinta": 5, "ultimo": -1, "ultima": -1}


def _norm(value, synonyms: dict) -> str:
    s = str(value or "").strip().lower()
    # Le chiavi più lunghe prima: «togli il muto» non deve fermarsi a «muto»
    return synonyms.get(s) or next((synonyms[k] for k in sorted(synonyms, key=len, reverse=True)
                                    if k in s), s)


# ─────────────────────────── tool ───────────────────────────

def _pc_stato(ctx: ToolContext, cosa: str = "", pc: str | None = None) -> dict:
    name, ex = _pc(ctx, pc)
    fuori = _fuori(name, ex)
    if fuori:
        return fuori
    cosa = (cosa or "").strip().lower().replace("à", "a").replace(" ", "_")
    caps = ex.capacita()
    wanted = [cosa] if cosa else [c for c, cap in (("volume", "volume"), ("musica", "media"))
                                    if cap in caps] or ["bloccato"]
    out, parts = {"ok": True, "pc": name}, []
    for what in wanted:
        if what == "volume" and "volume" in caps:
            v = _call(name, ex.volume_leggi)
            if not v.get("ok"):
                return v
            out["volume"], out["muto"] = v["livello"], v["muto"]
            parts.append(f"sul {name} il volume è al {_percent(v['livello'])}"
                         + (", ma l'audio è disattivato" if v["muto"] else ""))
        elif what in ("musica", "media") and "media" in caps:
            m = _call(name, ex.media_info)
            if not m.get("ok"):
                return m
            out["musica"] = m
            if not m.get("sessione"):
                parts.append("non suona niente" if parts else f"sul {name} non suona niente")
            else:
                title = (f"«{m['titolo']}»" + (f" di {m['artista']}" if m.get("artista") else "")
                         if m.get("titolo") else "qualcosa")
                app = f" su {m['app']}" if m.get("app") else ""
                if m.get("in_riproduzione"):
                    parts.append(f"sta suonando {title}{app}")
                else:
                    parts.append(f"{title}{app} è in pausa")
        elif what == "luminosita" and "luminosita" in caps:
            b = _call(name, ex.luminosita_leggi)
            if not b.get("ok"):
                return b
            out["luminosita"] = b["livello"]
            parts.append(f"la luminosità dello schermo è al {_percent(b['livello'])}")
        elif what == "batteria" and "batteria" in caps:
            b = _call(name, ex.batteria)
            if not b.get("ok"):
                return b
            out["batteria"] = b
            if not b.get("batteria"):
                parts.append(f"il {name} non ha una batteria")
            else:
                parts.append(f"la batteria del {name} è al {_percent(b['percento'])}"
                             + (", in carica" if b.get("in_carica") else ""))
        elif what == "bloccato":
            s = _call(name, ex.schermo)
            if not s.get("ok"):
                return s
            out["bloccato"] = s["bloccato"]
            if s["bloccato"]:
                parts.append(f"il {name} è bloccato")
            elif (s.get("inattivo_s") or 0) < 60:
                parts.append(f"il {name} non è bloccato ed è in uso")
            else:
                minutes = int(s["inattivo_s"] // 60)
                parts.append(f"il {name} non è bloccato; nessuno lo tocca da "
                             + ("1 minuto" if minutes == 1 else f"{minutes} minuti"))
        elif what == "programmi_aperti" and "programmi" in caps:
            if not _owner(ctx):
                return _not_owner(name)
            p = _call(name, ex.programmi_aperti)
            if p.get("bloccato"):
                return _locked(name)
            if not p.get("ok"):
                return p
            progs = p["programmi"]
            out["programmi"] = progs
            if not progs:
                parts.append(f"sul {name} non ci sono programmi aperti")
            else:
                shown = progs[:8]
                more = f" e altri {len(progs) - 8}" if len(progs) > 8 else ""
                listed = (shown[0] if len(shown) == 1
                          else ", ".join(shown[:-1]) + (" e " if not more else ", ") + shown[-1])
                parts.append(f"sul {name} sono aperti {listed}{more}")
        else:
            return {"ok": False, "errore": f"non so leggere «{cosa}» sul {name}",
                    "cosa_si_puo": _stato_enum(caps)}
    text = "; ".join(parts)
    out["conferma"] = text[0].upper() + text[1:] + "."
    return out


def _pc_volume(ctx: ToolContext, azione: str, valore=None, pc: str | None = None) -> dict:
    name, ex = _pc(ctx, pc)
    fuori = _fuori(name, ex, "volume")
    if fuori:
        return fuori
    azione = _norm(azione, _VOLUME_SYN)
    if azione == "muto":
        r = _call(name, ex.volume_muto, True)
        return r if not r.get("ok") else {**r, "conferma": f"Fatto, audio del {name} disattivato."}
    if azione == "riattiva":
        r = _call(name, ex.volume_muto, False)
        return r if not r.get("ok") else {
            **r, "conferma": f"Fatto, audio riattivato: volume al {_percent(r['livello'])}."}
    if azione not in ("alza", "abbassa", "imposta"):
        return {"ok": False, "errore": f"azione «{azione}» sconosciuta",
                "azioni": ["alza", "abbassa", "imposta", "muto", "riattiva"]}
    passo = int(getattr(ctx.cfg, "pc_passo", 10) or 10)
    amount = parse_amount(valore, passo, getattr(ctx, "user_text", ""), ctx)
    if azione == "imposta" and amount is None:
        return {"ok": False, "errore": "manca il valore", "cosa_fare": "chiedi a quanto metterlo"}
    now = _call(name, ex.volume_leggi)
    if not now.get("ok"):
        return now
    target = _target(azione, now["livello"], amount, passo)
    if target == now["livello"] and not now["muto"]:
        edge = {100: "già al massimo", 0: "già a zero"}.get(target)
        return {"ok": True, "livello": target, "conferma":
                f"Il volume è {edge}." if edge and azione != "imposta"
                else f"Il volume è già al {_percent(target)}."}
    r = _call(name, ex.volume_imposta, target)
    if not r.get("ok"):
        return r
    return {**r, "prima": now["livello"], "conferma": f"Fatto, volume al {_percent(r['livello'])}."}


def _pc_media(ctx: ToolContext, comando: str, pc: str | None = None) -> dict:
    name, ex = _pc(ctx, pc)
    fuori = _fuori(name, ex, "media")
    if fuori:
        return fuori
    comando = _norm(comando, _MEDIA_SYN)
    if comando not in COMANDI_MEDIA:
        return {"ok": False, "errore": f"comando «{comando}» sconosciuto",
                "comandi": list(COMANDI_MEDIA)}
    r = _call(name, ex.media_comando, comando)
    if not r.get("ok"):
        return {**r, "fatto": NIENTE,
                "cosa_dire": "dillo in breve, senza inventare cosa sta suonando"}
    return {**r, "conferma": {"riproduci": "Fatto, riparte.", "pausa": "Fatto, in pausa.",
                              "avanti": "Fatto, passo al brano successivo.",
                              "indietro": "Fatto, torno al brano precedente."}[comando]}


def _pc_luminosita(ctx: ToolContext, azione: str, valore=None, pc: str | None = None) -> dict:
    name, ex = _pc(ctx, pc)
    fuori = _fuori(name, ex, "luminosita")
    if fuori:
        return fuori
    azione = _norm(azione, _VOLUME_SYN)
    if azione not in ("alza", "abbassa", "imposta"):
        return {"ok": False, "errore": f"azione «{azione}» sconosciuta",
                "azioni": ["alza", "abbassa", "imposta"]}
    passo = int(getattr(ctx.cfg, "pc_passo", 10) or 10)
    amount = parse_amount(valore, passo, getattr(ctx, "user_text", ""), ctx)
    if azione == "imposta" and amount is None:
        return {"ok": False, "errore": "manca il valore", "cosa_fare": "chiedi a quanto metterla"}
    now = _call(name, ex.luminosita_leggi)
    if not now.get("ok"):
        return now
    target = _target(azione, now["livello"], amount, passo)
    if target == now["livello"]:
        edge = {100: "già al massimo", 0: "già al minimo"}.get(target)
        return {"ok": True, "livello": target, "conferma":
                f"La luminosità è {edge}." if edge and azione != "imposta"
                else f"La luminosità è già al {_percent(target)}."}
    r = _call(name, ex.luminosita_imposta, target)
    if not r.get("ok"):
        return r
    return {**r, "prima": now["livello"],
            "conferma": f"Fatto, luminosità al {_percent(r['livello'])}."}


# Articoli per le app del catalogo predefinito: «Apro la calcolatrice», non «Apro calcolatrice»
_ARTICLES = {"calcolatrice": "la ", "blocco note": "il ", "impostazioni": "le ",
             "browser": "il ", "esplora file": "", "posta": "la ", "terminale": "il "}


def _pc_apri_app(ctx: ToolContext, app: str, pc: str | None = None) -> dict:
    name, ex = _pc(ctx, pc)
    fuori = _fuori(name, ex, "app")
    if fuori:
        return fuori
    r = _call(name, ex.apri_app, app)
    if r.get("bloccato"):
        return _locked(name)
    if not r.get("ok"):
        return {**r, "fatto": NIENTE}
    key = r["app"]
    article = _ARTICLES.get(key)
    said = f"{article}{key}" if article is not None else key[:1].upper() + key[1:]
    return {**r, "conferma": f"Apro {said} sul {name}."}


def _pc_blocca(ctx: ToolContext, pc: str | None = None) -> dict:
    name, ex = _pc(ctx, pc)
    fuori = _fuori(name, ex, "blocco")
    if fuori:
        return fuori
    stato = _call(name, ex.schermo)
    if not stato.get("ok") and "bloccato" not in stato:
        return stato
    if stato.get("bloccato"):
        return {"ok": True, "conferma": f"Il {name} è già bloccato."}
    r = _call(name, ex.blocca)
    return r if not r.get("ok") else {**r, "conferma": f"Fatto, {name} bloccato."}


_KIND_WORDS = {"qualsiasi": ("file", "file"), "documento": ("documento", "documenti"),
               "pdf": ("PDF", "PDF"), "foto": ("foto", "foto"), "musica": ("brano", "brani"),
               "video": ("video", "video")}


def _items(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " e " + names[-1]


def _spoken_names(found: list[dict]) -> list[str]:
    """Come dire i risultati perché si distinguano. Il 27/09 «Ho trovato 5 documenti:
    timelog, timelog e timelog»: ai nomi uguali si aggiunge il tipo («timelog xlsx»), poi
    la data («del 6 agosto»), poi l'ora («delle 10:31»)."""
    def stamp(f):
        return re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d:\d\d)", str(f.get("modificato") or ""))

    def day(f):
        m = stamp(f)
        return f" del {int(m[3])} {MESI[int(m[2]) - 1]}" if m else ""

    def hour(f):
        m = stamp(f)
        return f" delle {m[4]}" if m else ""

    names = [f["nome"] for f in found]
    for extra in (lambda f: f" {f.get('estensione', '')}".rstrip(), day, hour):
        dup = {n for n in names if names.count(n) > 1}
        if not dup:
            break
        names = [n + extra(f) if n in dup else n for n, f in zip(names, found)]
    return names


def _pc_cerca_file(ctx: ToolContext, testo: str = "", tipo: str = "qualsiasi",
                   periodo: str = "", pc: str | None = None) -> dict:
    name, ex = _pc(ctx, pc)
    fuori = _fuori(name, ex, "ricerca")
    if fuori:
        return fuori
    if not _owner(ctx):
        return _not_owner(name)
    tipo = (tipo or "qualsiasi").strip().lower()
    tipo = {"documenti": "documento", "immagine": "foto", "immagini": "foto",
            "fotografie": "foto", "canzone": "musica", "audio": "musica",
            "film": "video"}.get(tipo, tipo)
    if tipo not in TIPI_FILE:
        tipo = "qualsiasi"
    dal, al, label = parse_past_range(str(periodo or ""))
    if not str(testo or "").strip() and tipo == "qualsiasi" and not dal and not al:
        # Una ricerca senza niente elencava gli ultimi file modificati, di sistema
        # compresi (27/09): non serve a nessuno e mostra cose che non sono state chieste
        return {"ok": False, "fatto": NIENTE, "errore": "manca cosa cercare",
                "cosa_fare": "chiama pc_cerca_file con le parole del nome del file dette "
                             "dalla persona; se non le ha dette, chiedi quale file cerca"}
    prof = _profile(ctx)
    r = _call(name, ex.cerca_file, prof.id if prof else "amministra", str(testo or ""), tipo,
              dal.isoformat() if dal else None, al.isoformat() if al else None)
    if r.get("bloccato"):
        return _locked(name)
    if not r.get("ok"):
        return r
    found = r["risultati"]
    one, many = _KIND_WORDS[tipo]
    what = f" «{testo}»" if (testo or "").strip() else ""
    when = f", {label}" if label else ""
    if not found:
        return {**r, "conferma": f"Sul {name} non ho trovato {one}{what}{when}.",
                "cosa_fare": "dillo in breve; se vuole, può riprovare con altre parole"}
    names = _spoken_names(found)[:3]
    more = len(found) - len(names)
    # La domanda finale diventa un'azione in sospeso per il turno dopo (Brain): «sì», «il
    # secondo» li capisce il modello, con la proposta davanti
    if len(found) == 1:
        conferma = f"Ho trovato {names[0]}. Lo apro?"
        pending = {"domanda": "Lo apro?", "cosa": f"il file {names[0]}",
                   "tool": "pc_apri_file", "argomenti": {"risultato": 1}}
    else:
        conferma = (f"Ho trovato {len(found)} {many}: {_items(names)}"
                    + (f" e altri {more}" if more else "") + ". Quale apro?")
        pending = {"domanda": "Quale apro?",
                   "cosa": "i file trovati: " + ", ".join(
                       f"{i} = {n}" for i, n in enumerate(names, 1)),
                   "tool": "pc_apri_file",
                   "argomenti": "risultato = il numero del file scelto"}
    return {**r, "periodo": label or "sempre", "conferma": conferma, "in_sospeso": pending,
            "cosa_fare": "Dillo con la conferma. Se poi chiede di aprirne uno («il secondo», "
                         "«apri la bolletta», «sì»), chiama pc_apri_file con il suo numero n."}


def _pc_apri_file(ctx: ToolContext, risultato=1, pc: str | None = None) -> dict:
    name, ex = _pc(ctx, pc)
    fuori = _fuori(name, ex)
    if fuori:
        return fuori
    # Un documento appena creato da chi parla (calliope/documenti/) si apre anche se non è
    # proprietario del PC: è suo, e l'esecutore lo tiene come sua «ultima ricerca»
    prof = _profile(ctx)
    own = prof is not None and getattr(ex, "ultimo_proprio", lambda _: False)(prof.id)
    if not own and not _owner(ctx):
        return _not_owner(name)
    # Solo un numero o un ordinale («2», «il secondo», «l'ultimo»): un percorso o un nome
    # di file dal modello non si apre mai
    s = str(risultato if risultato is not None else "1").strip().lower()
    m = re.fullmatch(r"(?:il |lo |la |l'|numero |n\.? ?)?(\d{1,2})[°º]?|"
                     r"(?:il |lo |la |l')?(\w+)", s)
    n = None
    if m and m.group(1):
        n = int(m.group(1))
    elif m and m.group(2):
        n = _ORDINALS.get(m.group(2))
    if n is None:
        return {"ok": False, "fatto": NIENTE, "errore": f"«{risultato}» non è un numero",
                "cosa_fare": "chiama pc_apri_file con il numero n del risultato"}
    r = _call(name, ex.apri_file, prof.id if prof else "amministra", n)
    if r.get("bloccato"):
        return _locked(name)
    if not r.get("ok") and r.get("tipo_vietato"):
        frase = (f"Questo file non lo apro: {r.get('errore')}.")
        return {**r, "fatto": NIENTE, "conferma": frase, "risposta_finale": frase}
    if not r.get("ok"):
        out = {**r, "fatto": NIENTE}
        if r.get("serve_ricerca"):
            # Il 27/09 «aprimi il file chiavi.csv.xlsx» → pc_apri_file senza ricerca, poi
            # «non ho informazioni su quale file cercare» anche se il nome era stato detto
            out["cosa_fare"] = ("se la persona ha detto il nome del file, chiama subito "
                                "pc_cerca_file con quelle parole; se no chiedi quale file")
        return out
    if r.get("come_testo"):
        # Script e pagine si mostrano, non si eseguono (base.modo_apertura, 03/10)
        return {**r, "conferma": f"Apro {r['nome']} come testo nel Blocco note: gli script "
                                 f"non li eseguo."}
    return {**r, "conferma": f"Apro {r['nome']}."}


# ─────────────────────────── registro ───────────────────────────

def _stato_enum(caps) -> list[str]:
    return ([c for c, cap in (("volume", "volume"), ("musica", "media"),
                              ("luminosita", "luminosita"), ("batteria", "batteria"),
                              ("programmi_aperti", "programmi")) if cap in caps]
            + ["bloccato"])


def pc_specs(executors: dict, ospite_volume_media: bool = False,
             documenti: bool = False) -> list[ToolSpec]:
    """Gli schemi dei tool pc_* per i PC collegati. Un tool c'è solo se almeno un PC ha
    la capacità; gli enum (cosa leggere, app) vengono da ciò che i PC dichiarano, così un
    PC senza batteria non offre «batteria» e l'elenco delle app è quello installato.

    Il parametro `pc` c'è solo con più di un PC: oggi c'è solo il portatile, e un
    parametro in più è un'occasione di errore per il modello. Con `documenti` la
    descrizione di pc_apri_file dice che «aprilo» dopo documento_crea è il risultato 1.
    """
    if not executors:
        return []
    # L'esecutore remoto dichiara tutte le capacità possibili: i tool non cambiano quando il
    # satellite si collega o cade (prefisso del prompt in cache)
    caps = {c for ex in executors.values()
            for c in getattr(ex, "capacita_possibili", ex.capacita)()}
    first = next(iter(executors))
    where = f"del {first}" if len(executors) == 1 else "di un PC di casa"

    def params(props: dict, required: list[str]) -> dict:
        props = dict(props)
        if len(executors) > 1:
            props["pc"] = {"type": "string", "enum": list(executors),
                           "description": f"quale PC; se non è detto, {first}"}
        return {"type": "object", "properties": props, "required": required}

    reversible = ALL if ospite_volume_media else FAMILY
    specs = [ToolSpec(
        name="pc_stato",
        description=(f"Legge lo stato {where}: volume, musica (cosa sta suonando), "
                     f"luminosita, batteria, programmi_aperti, bloccato. Senza cosa: volume "
                     f"e musica. Nella risposta usa la conferma."),
        parameters=params({"cosa": {"type": "string", "enum": _stato_enum(caps)}}, []),
        func=_pc_stato, risk="lettura", levels=FAMILY)]
    if "volume" in caps:
        specs.append(ToolSpec(
            name="pc_volume",
            description=(f"Cambia il volume {where}. azione: alza, abbassa, imposta, muto, "
                         f"riattiva. valore come detto a voce: «un po'», «molto», «20», «al "
                         f"massimo»; vuoto per alza/abbassa senza quantità. «Alza a 50» è "
                         f"imposta con valore 50. Per sapere il volume usa pc_stato."),
            parameters=params({"azione": {"type": "string",
                                          "enum": ["alza", "abbassa", "imposta", "muto",
                                                   "riattiva"]},
                               "valore": {"type": "string"}}, ["azione"]),
            func=_pc_volume, risk="azione", levels=reversible))
    if "media" in caps:
        specs.append(ToolSpec(
            name="pc_media",
            description=(f"Comanda la musica o il video che suona {where} (Spotify, YouTube, "
                         f"lettore): riproduci, pausa, avanti (brano successivo), indietro "
                         f"(brano precedente). Per sapere cosa suona usa pc_stato."),
            parameters=params({"comando": {"type": "string", "enum": list(COMANDI_MEDIA)}},
                              ["comando"]),
            func=_pc_media, risk="azione", levels=reversible))
    if "luminosita" in caps:
        specs.append(ToolSpec(
            name="pc_luminosita",
            description=(f"Cambia la luminosità dello schermo {where}. azione: alza, "
                         f"abbassa, imposta; valore come detto: «un po'», «molto», «70», «al "
                         f"massimo»; vuoto per alza/abbassa senza quantità."),
            parameters=params({"azione": {"type": "string",
                                          "enum": ["alza", "abbassa", "imposta"]},
                               "valore": {"type": "string"}}, ["azione"]),
            func=_pc_luminosita, risk="azione", levels=FAMILY))
    if "app" in caps:
        apps = sorted({a for ex in executors.values()
                       for a in getattr(ex, "app_catalogo", ex.app_disponibili)()})
        specs.append(ToolSpec(
            name="pc_apri_app",
            description=(f"Apre un programma {where}. Solo quelli dell'elenco: per gli altri "
                         f"di' che non puoi."),
            parameters=params({"app": {"type": "string", "enum": apps}}, ["app"]),
            func=_pc_apri_app, risk="azione", levels=FAMILY))
    if "blocco" in caps:
        specs.append(ToolSpec(
            name="pc_blocca",
            description=f"Blocca lo schermo {where}, come Windows+L.",
            parameters=params({}, []),
            func=_pc_blocca, risk="azione", levels=FAMILY))
    if "ricerca" in caps:
        specs.append(ToolSpec(
            name="pc_cerca_file",
            description=(f"Cerca file {where}: testo sono le parole del nome («bolletta "
                         f"luce»), tipo il genere di file, periodo quando è stato modificato, "
                         f"come detto a voce («la settimana scorsa», «ad agosto»; vuoto = "
                         f"sempre). Basta una parola: «apri il file chiavi» è testo «chiavi», "
                         f"senza chiedere il nome completo. Per aprirne uno poi usa "
                         f"pc_apri_file."),
            parameters=params({"testo": {"type": "string"},
                               "tipo": {"type": "string", "enum": list(TIPI_FILE)},
                               "periodo": {"type": "string"}}, []),
            func=_pc_cerca_file, risk="lettura", levels=FAMILY))
        specs.append(ToolSpec(
            name="pc_apri_file",
            description=(f"Apre uno dei file trovati dall'ultima pc_cerca_file: risultato è "
                         f"il suo numero n (1 = il primo). "
                         + ("Dopo documento_crea o documento_modifica, «aprilo» è risultato "
                            "1. " if documenti else "")
                         + "Non apre altro: se chiede di aprire un file per nome («apri la "
                           "bolletta»), prima chiama pc_cerca_file con quel nome."),
            parameters=params({"risultato": {"type": "integer"}}, ["risultato"]),
            func=_pc_apri_file, risk="azione", levels=FAMILY))
    return specs
