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
"""

TELEFONO, SATELLITE, LOCALE, SCRITTO = "telefono", "satellite", "locale", "scritto"


def descrivi(canale: str | None, pc_qui: bool = False) -> dict | None:
    """Il dispositivo di questa frase: {"canale", "pc_qui"}; None se il canale non si sa."""
    if canale not in (TELEFONO, SATELLITE, LOCALE, SCRITTO):
        return None
    return {"canale": canale, "pc_qui": bool(pc_qui)}


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


def nota(disp: dict | None, pc: str | None) -> str:
    """La riga dei dati del turno, "" senza dispositivo. `pc`: il nome del PC raggiungibile
    (pc_raggiungibile), come nel prompt (cfg.pc_nome), o None."""
    if not isinstance(disp, dict):
        return ""
    canale = disp.get("canale")
    if canale == LOCALE or (canale == SATELLITE and disp.get("pc_qui")):
        if pc:
            return f"dispositivo: il {pc}, un computer."
        return ("dispositivo: un computer che non comandi, quindi niente webcam né schermo "
                "del computer.")
    dove = {TELEFONO: "il telefono", SATELLITE: "un satellite vocale (microfono e cassa)",
            SCRITTO: "uno schermo, per scritto"}.get(canale)
    if dove is None:
        return ""
    if pc:
        return f"dispositivo: {dove}, non un computer; il {pc} è collegato a parte."
    return (f"dispositivo: {dove}, non un computer; nessun computer collegato, quindi "
            f"niente webcam né schermo del computer.")
