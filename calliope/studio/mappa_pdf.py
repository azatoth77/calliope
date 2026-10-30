"""
Il PDF della mappa dello studente (30/10, passo 7, issue #247; progetto del 27/10, § 5.4 e
decisione 5): **un formato solo** (il formato chiesto dalla scuola per il PDP lo decidono i tutori,
fuori da questa implementazione). Pagina 1, A4 orizzontale: il titolo con la materia, il nome, la
data della verifica e «controllata il …», la mappa (i concetti nei riquadri, le frecce col verbo);
dalla pagina 2 lo schema a elenco (ogni concetto con le pagine e i suoi collegamenti), **su quante
pagine servono**, con la testata ripetuta e «pagina x di N» (revisione della PR #326: prima l'elenco
perdeva in silenzio i concetti che non stavano in una pagina).

fpdf2 (puro Python, già nell'extra `documenti`) e i font di `documenti/render.py` (`find_font`):
niente dipendenze native nuove (principio 4). Senza un TrueType tutto il testo passa dal latin-1
(`_latin1`), anche i puntini e le frecce, **prima** di misurarlo e scriverlo. Il testo dei concetti è
un dato: qui si stampa e basta.
"""

from __future__ import annotations

import datetime
import math

# La pagina (mm) e la mappa dentro
LARGO, ALTO = 297.0, 210.0
MARGINE = 12.0
TESTA = 30.0
NODO_W = 46.0
RIGA = 4.4
FONT_NODO = 9
# Lo spazio in fondo alla pagina che resta libero (il piede)
PIEDE = 10.0


def _data(iso) -> str:
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day}/{d.month}/{d.year}"


def _corta(pdf, t: str, largo: float, puntini: str) -> str:
    while t and pdf.get_string_width(t + puntini) > largo:
        t = t[:-1]
    return t.rstrip() + puntini


def _taglia(pdf, testo: str, largo: float, righe: int, puntini: str) -> list[str]:
    """Il testo (già pulito) in righe che stanno in `largo` mm, al più `righe` (l'ultima coi
    puntini, anch'essi già puliti)."""
    out, cur = [], ""
    for w in str(testo).split():
        prova = (cur + " " + w).strip()
        if pdf.get_string_width(prova) <= largo or not cur:
            cur = prova
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    out = [r if pdf.get_string_width(r) <= largo else _corta(pdf, r, largo, puntini) for r in out]
    if len(out) > righe:
        out = out[:righe]
        out[-1] = _corta(pdf, out[-1], largo, puntini)
    return out or [""]


def _bordo(cx, cy, w, h, tx, ty) -> tuple[float, float]:
    """Il punto sul bordo del riquadro (centro cx, cy) verso (tx, ty)."""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    s = min((w / 2) / abs(dx) if dx else float("inf"), (h / 2) / abs(dy) if dy else float("inf"))
    return cx + dx * s, cy + dy * s


def render(mappa: dict, nome: str, materia: str, data_verifica: str, pagine: dict | None = None,
           font=None) -> bytes:
    from fpdf import FPDF

    from ..documenti.render import _latin1, find_font
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(MARGINE, MARGINE, MARGINE)
    trovato = find_font(font or ["arial", "segoeui", "DejaVuSans", "LiberationSans"])
    if trovato:
        pdf.add_font("Testo", "", trovato[0])
        if trovato[1]:
            pdf.add_font("Testo", "B", trovato[1])
        fam, gr, pulito = "Testo", ("B" if trovato[1] else ""), (lambda s: str(s))
    else:
        fam, gr, pulito = "Helvetica", "B", (lambda s: _latin1(str(s)))
    freccia = pulito("→") if trovato else "->"
    puntini = pulito("…")
    vuota = pulito("…………")
    pagine = pagine or {}
    nodi = [n for n in mappa.get("nodi") or () if isinstance(n, dict)]
    coll = [c for c in mappa.get("collegamenti") or () if isinstance(c, dict)]
    per_id = {int(n["id"]): n for n in nodi}
    pdf.set_title(pulito(f"Mappa di {materia}"))
    pdf.set_author(pulito(nome or "Studio"))
    pdf.set_creator("Calliope")
    # «pagina x di N»: N lo scrive fpdf alla fine, al posto di {nb}
    pdf.alias_nb_pages()

    def testo_di(n) -> str:
        return pulito(str(n.get("testo") or "").strip()) or vuota

    def testa(sotto: str):
        pdf.set_xy(MARGINE, MARGINE)
        pdf.set_font(fam, gr, 15)
        pdf.cell(0, 8, pulito(f"Mappa di {materia}" + (f" · {nome}" if nome else "")),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 10)
        quando = mappa.get("controllata")
        ctrl = (f"controllata il {_data(quando)}" if quando else "non ancora controllata")
        if quando and str(mappa.get("modificata") or "") > str(quando):
            ctrl += " (cambiata dopo)"
        pdf.cell(0, 5, pulito(f"Verifica del {_data(data_verifica)} · {ctrl} · pagina "
                              f"{pdf.page_no()} di ") + "{nb}" + pulito(f" · {sotto}"),
                 new_x="LMARGIN", new_y="NEXT")

    # ── pagina 1: la mappa ──
    pdf.add_page()
    testa("la mappa")
    x0, y0 = MARGINE + NODO_W / 2, TESTA + 10
    larga, alta = LARGO - 2 * MARGINE - NODO_W, ALTO - TESTA - MARGINE - 20
    pdf.set_font(fam, "", FONT_NODO)
    box = {}
    for n in nodi:
        righe = _taglia(pdf, testo_di(n), NODO_W - 4, 3, puntini)
        h = len(righe) * RIGA + 4
        cx = x0 + float(n.get("x") or 0.5) * larga
        cy = y0 + float(n.get("y") or 0.5) * alta
        box[int(n["id"])] = (cx, cy, NODO_W, h, righe)
    # Prima le frecce (sotto), poi i riquadri
    pdf.set_draw_color(60, 60, 60)
    pdf.set_line_width(0.35)
    for c in coll:
        a, b = box.get(int(c["da"])), box.get(int(c["a"]))
        if a is None or b is None:
            continue
        sx, sy = _bordo(a[0], a[1], a[2] + 2, a[3] + 2, b[0], b[1])
        ex, ey = _bordo(b[0], b[1], b[2] + 2, b[3] + 2, a[0], a[1])
        pdf.line(sx, sy, ex, ey)
        ang = math.atan2(ey - sy, ex - sx)
        p1 = (ex - 3 * math.cos(ang - 0.4), ey - 3 * math.sin(ang - 0.4))
        p2 = (ex - 3 * math.cos(ang + 0.4), ey - 3 * math.sin(ang + 0.4))
        pdf.set_fill_color(60, 60, 60)
        pdf.polygon([(ex, ey), p1, p2], style="F")
        vb = pulito(str(c.get("verbo") or ""))
        if vb:
            pdf.set_font(fam, "", 8)
            w = min(40, pdf.get_string_width(vb) + 3)
            if pdf.get_string_width(vb) > w - 1:
                vb = _corta(pdf, vb, w - 1, puntini)
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            pdf.set_fill_color(255, 255, 255)
            pdf.set_xy(mx - w / 2, my - 2.4)
            pdf.cell(w, 4.8, vb, align="C", fill=True)
    pdf.set_font(fam, "", FONT_NODO)
    for nid, (cx, cy, w, h, righe) in box.items():
        n = per_id[nid]
        pdf.set_fill_color(234, 240, 250) if n.get("da") is not None else pdf.set_fill_color(
            253, 243, 224)
        pdf.set_draw_color(40, 70, 140)
        pdf.rect(cx - w / 2, cy - h / 2, w, h, style="DF", round_corners=True, corner_radius=2)
        for i, r in enumerate(righe):
            pdf.set_xy(cx - w / 2 + 2, cy - h / 2 + 2 + i * RIGA)
            pdf.cell(w - 4, RIGA, r, align="C")
    pdf.set_xy(MARGINE, ALTO - MARGINE - 5)
    pdf.set_font(fam, "", 8)
    pdf.cell(0, 5, pulito("Azzurro: i concetti del quadro · arancio chiaro: i concetti aggiunti. "
                          "Lo schema a elenco è nelle pagine dopo."))

    # ── dalla pagina 2: l'elenco, su quante pagine servono ──
    fondo = ALTO - MARGINE - PIEDE

    def nuova():
        pdf.add_page()
        testa("lo schema a elenco")
        pdf.set_y(TESTA + 6)

    def riga(testo: str, alto: float, rientro: float, stile: str, corpo: int):
        """Una voce dell'elenco: se non ci sta, prima una pagina nuova (mai tagliata a metà)."""
        pdf.set_font(fam, stile, corpo)
        largo = LARGO - 2 * MARGINE - rientro
        n_righe = max(1, len(pdf.multi_cell(largo, alto, testo, dry_run=True, output="LINES")))
        if pdf.get_y() + n_righe * alto > fondo:
            nuova()
            pdf.set_font(fam, stile, corpo)
        pdf.set_x(MARGINE + rientro)
        pdf.multi_cell(largo, alto, testo, new_x="LMARGIN", new_y="NEXT")

    nuova()
    for n in nodi:
        pag = [pagine.get(int(p)) for p in n.get("pagine") or () if pagine.get(int(p))]
        riga(testo_di(n) + (pulito(f"  ({', '.join(pag)})") if pag else ""), 5.5, 0, gr, 11)
        for c in coll:
            if int(c["da"]) != int(n["id"]):
                continue
            altro = per_id.get(int(c["a"]))
            if altro is None:
                continue
            riga(f"{freccia} {pulito(c.get('verbo') or '')} {freccia} {testo_di(altro)}", 5, 6,
                 "", 10)
        pdf.ln(1.5)
    return bytes(pdf.output())
