"""
Il dispositivo da cui si parla, come dato del turno (16/10/2026, issue #100).

Caso vero del 15/10 sera, dal telefono: a «sei un computer?» Calliope rispondeva di sì e che
poteva usare la webcam «se me lo chiedi»; chiesta la foto, pc_guarda falliva («il satellite
collegato non offre il controllo del portatile») e la spinta `foto_spinta_pc` era scattata in
4 turni. Il modello non sapeva da dove gli si parlava, e la spinta guardava solo se il tool
pc_guarda era registrato (con i satelliti lo è sempre: il prefisso del prompt non cambia).

Qui due cose, lette al turno (mai all'avvio: un satellite va e viene):
- `descrivi` (dal ciclo): il canale della frase (telefono, satellite, audio di questo computer,
  scritto da uno schermo) e se il dispositivo stesso è il PC comandato;
- `pc_raggiungibile` (dal Brain): il PC che pc_guarda raggiungerebbe adesso, con la capacità
  che serve, con la stessa logica dei tool (tools/pc.py `_fuori`: collegato e capace).

`nota` mette insieme le due in una riga corta per i dati del turno (TURN_CONTEXT_MSG), stabile
tra i turni dallo stesso satellite. Un dato, non un ordine: decide il modello (principio 10).

Dal 28/10 (issue #288) anche lo **schermo personale** di chi parla (`schermo_di`): aperto, chiuso
o assente, e le sezioni che lì non ci sono (Casa per età, Ufficio per chi non amministra). Due
casi veri dalla DGX del 28/10, dal telefono: «Apri lo schermo dei documenti su questo
dispositivo» → «non posso aprire uno schermo perché non è un computer», e «la scheda documenti
del tab Le mie cose» → «non ho una scheda Le mie cose su questo dispositivo». La nota diceva
«il telefono, non un computer» e «niente webcam né schermo del computer», e il modello ne
deduceva che il telefono non ha uno schermo. Ora il «niente» vale per la webcam e la schermata
del computer; com'è fatto lo schermo personale (sezioni e pagine) lo dice il prompt di sistema,
che resta uguale fra i turni (Config.prompt_for, `sezioni`).
"""

TELEFONO, SATELLITE, LOCALE, SCRITTO = "telefono", "satellite", "locale", "scritto"


# Lo schermo personale di chi parla (28/10, #288), per la nota e per il registro dei turni
APERTO, CHIUSO, NESSUNO = "aperto", "chiuso", "nessuno"


def descrivi(canale: str | None, pc_qui: bool = False, personale: bool = False) -> dict | None:
    """Il dispositivo di questa frase: {"canale", "pc_qui"} (con "personale": True per lo scritto
    da uno schermo personale, 28/10); None se il canale non si sa."""
    if canale not in (TELEFONO, SATELLITE, LOCALE, SCRITTO):
        return None
    out = {"canale": canale, "pc_qui": bool(pc_qui)}
    if personale and canale == SCRITTO:
        out["personale"] = True
    return out


def schermo_di(ctx, ufficio: bool = False) -> dict | None:
    """Lo schermo personale di chi parla (28/10, #288): {"stato": aperto | chiuso | nessuno,
    "nascoste": [nomi delle sezioni e delle pagine che lì non ci sono]}; None senza schermi.

    Aperto: un suo schermo personale ha la pagina aperta adesso; chiuso: ne ha uno abbinato;
    nessuno: non ne ha (gli ospiti e la zona grigia mai, come `Schermi.personale_abbinato`).
    `ufficio`: c'è l'Ufficio in questa installazione (il tool modello_compila): allora si dice
    se per chi parla non c'è. Solo lo stato che il server ha già, nessuna chiamata di rete."""
    hub = getattr(ctx, "schermi", None)
    if hub is None or not hasattr(hub, "abbinati"):
        return None
    try:
        m = hub.mittente(ctx)
        if not getattr(m, "certo", False) or not getattr(m, "persona", None):
            return {"stato": NESSUNO, "nascoste": []}
        suoi = [s for s in hub.abbinati() if s.get("proprietario") == m.persona]
        if not suoi:
            return {"stato": NESSUNO, "nascoste": []}
        aperto = any(hub.collegato(s["id"]) for s in suoi)
        nascoste = []
        sc = getattr(ctx, "speaker_ctx", None)
        name = getattr(sc, "current_speaker", None)
        speakers = getattr(ctx, "speakers", None)
        prof = speakers.get(name) if (name and speakers is not None) else None
        if prof is not None:
            from .schermi.aspetto import nascoste as nascoste_di
            n = nascoste_di(prof)
            if "casa" in n["sezioni"]:
                nascoste.append("Casa")
            if ufficio and ("ufficio" in n["raccolte"] or not getattr(prof, "admin", False)):
                nascoste.append("Ufficio")
        return {"stato": APERTO if aperto else CHIUSO, "nascoste": nascoste}
    except Exception:  # noqa: BLE001 — nel dubbio la nota non parla dello schermo
        return None


def _nota_schermo(schermo: dict | None) -> str:
    """Il pezzo della nota sullo schermo personale di chi parla, "" senza schermi."""
    if not isinstance(schermo, dict):
        return ""
    stato = schermo.get("stato")
    if stato == NESSUNO:
        return "chi parla non ha uno schermo personale"
    if stato not in (APERTO, CHIUSO):
        return ""
    out = ("lo schermo personale di chi parla è aperto adesso" if stato == APERTO
           else "lo schermo personale di chi parla è chiuso adesso")
    via = [str(x) for x in schermo.get("nascoste") or ()]
    if via:
        out += (f" e lì non c'è {via[0]}" if len(via) == 1
                else f" e lì non ci sono {', '.join(via[:-1])} e {via[-1]}")
    return out


def pc_raggiungibile(pcs, cap: str | None = None) -> str | None:
    """Il nome del PC che i tool pc_* raggiungono adesso (con la capacità `cap`, se data), o
    None. L'esecutore remoto c'è sempre con pc_enabled: conta `collegato()`, come in
    tools/pc.py. Nessuna chiamata di rete: solo lo stato che il server ha già."""
    for nome, ex in (pcs or {}).items():
        try:
            collegato = getattr(ex, "collegato", None)
            if collegato is not None and not collegato():
                continue
            if cap and cap not in ex.capacita():
                continue
        except Exception:  # noqa: BLE001 — un esecutore guasto vale «non raggiungibile»
            continue
        return nome
    return None


def pc_per_chi(ctx, cap: str | None = None) -> str | None:
    """Il PC che pc_guarda userebbe per chi parla adesso (revisione della PR #119): raggiungibile
    con la capacità, la voce riconosciuta in questa frase (né scritto, né zona grigia, né frase
    breve) e un proprietario del PC o chi amministra, come in tools/immagini._pc_guarda. None
    altrimenti: niente spinta né «collegato» per una chiamata destinata al rifiuto."""
    nome = pc_raggiungibile(getattr(ctx, "pc", None), cap)
    if nome is None:
        return None
    sc = getattr(ctx, "speaker_ctx", None)
    if getattr(sc, "identified_by", None) != "voce" or getattr(sc, "from_session", False):
        return None
    try:
        from .tools.pc import _owner
        return nome if _owner(ctx) else None
    except Exception:  # noqa: BLE001 — nel dubbio il PC non è per chi parla
        return None


def nota(disp: dict | None, pc: str | None, per_chi: bool = True,
         schermo: dict | None = None) -> str:
    """La riga dei dati del turno, "" senza dispositivo. `pc`: il nome del PC raggiungibile
    (pc_raggiungibile), come nel prompt (cfg.pc_nome), o None; `per_chi`: pc_guarda lo
    userebbe per chi parla (pc_per_chi); `schermo`: lo schermo personale di chi parla
    (schermo_di, 28/10), o None senza schermi."""
    if not isinstance(disp, dict):
        return ""
    canale = disp.get("canale")
    if canale == LOCALE or (canale == SATELLITE and disp.get("pc_qui")):
        if pc and per_chi:
            parti = [f"il {pc}, un computer"]
        elif pc:
            parti = [f"il {pc}, un computer", "la sua webcam e il suo schermo non sono per chi "
                                              "parla adesso"]
        else:
            parti = ["un computer che non comandi, quindi niente webcam né schermata del "
                     "computer"]
        sch = _nota_schermo(schermo)
        if sch:
            parti.insert(1, sch)
        return "dispositivo: " + "; ".join(parti) + "."
    # Lo scritto può venire anche dal browser del portatile (revisione della PR #119): lì
    # «non un computer» sarebbe falso. Dallo schermo personale (il telefono o il PC, 28/10):
    # lo schermo a sezioni, e la riga sullo schermo aperto non serve
    if canale == SCRITTO and disp.get("personale"):
        dove, sch = "lo schermo personale a sezioni di chi parla, per scritto", ""
    else:
        dove = {TELEFONO: "il telefono, non un computer",
                SATELLITE: "un satellite vocale (microfono e cassa), non un computer",
                SCRITTO: "uno schermo, per scritto"}.get(canale)
        sch = _nota_schermo(schermo)
    if dove is None:
        return ""
    parti = [dove] + ([sch] if sch else [])
    # «niente schermo» valeva anche per il telefono (28/10, #288): il niente è della webcam e
    # della schermata del computer, non dello schermo da cui si parla
    if pc and per_chi:
        parti.append(f"il {pc} è collegato a parte")
    elif pc:
        parti.append(f"webcam e schermata del {pc} non sono per chi parla adesso")
    else:
        parti.append("nessun computer collegato, quindi niente webcam né schermata del "
                     "computer")
    return "dispositivo: " + "; ".join(parti) + "."
