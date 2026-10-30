"""
Il PDF della mappa dello studente (30/10, passo 7, issue #247; progetto del 27/10, § 5.4 e
decisione 5): **un formato solo** (il formato chiesto dalla scuola per il PDP lo decidono i tutori,
fuori da questa implementazione). Pagina 1, A4 orizzontale: il titolo con la materia, il nome, la
data della verifica e «controllata il …», la mappa (i concetti nei riquadri, le frecce col verbo);
pagina 2: lo schema a elenco (ogni concetto con le pagine e i suoi collegamenti).

fpdf2 (puro Python, già nell'extra `documenti`) e i font di `documenti/render.py` (`find_font`):
niente dipendenze native nuove (principio 4). Senza un TrueType il testo passa dal latin-1, come i
documenti. Il testo dei concetti è un dato: qui si stampa e basta.
"""

from __future__ import annotations

import datetime

# La pagina (mm) e la mappa dentro
LARGO, ALTO = 297.0, 210.0
MARGINE = 12.0
TESTA = 30.0
NODO_W = 46.0
RIGA = 4.4
FONT_NODO = 9


def _data(iso) -> str:
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day}/{d.month}/{d.year}"


def _taglia(pdf, testo: str, largo: float, righe: int) -> list[str]:
    """Il testo in righe che stanno in `largo` mm, al più `righe` (l'ultima con «…»)."""
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
    if len(out) > righe:
        out = out[:righe]
        while out[-1] and pdf.get_string_width(out[-1] + "…") > largo:
            out[-1] = out[-1][:-1]
        out[-1] += "…"
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
        fam, gr, pulito = "Helvetica", "B", _latin1
    freccia = "→" if trovato else "->"
    pagine = pagine or {}
    nodi = [n for n in mappa.get("nodi") or () if isinstance(n, dict)]
    coll = [c for c in mappa.get("collegamenti") or () if isinstance(c, dict)]
    per_id = {int(n["id"]): n for n in nodi}
    pdf.set_title(pulito(f"Mappa di {materia}"))
    pdf.set_author(pulito(nome or "Studio"))
    pdf.set_creator("Calliope")

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
        pdf.cell(0, 5, pulito(f"Verifica del {_data(data_verifica)} · {ctrl} · {sotto}"),
                 new_x="LMARGIN", new_y="NEXT")

    # ── pagina 1: la mappa ──
    pdf.add_page()
    testa("pagina 1 di 2: la mappa")
    x0, y0 = MARGINE + NODO_W / 2, TESTA + 10
    larga, alta = LARGO - 2 * MARGINE - NODO_W, ALTO - TESTA - MARGINE - 20
    pdf.set_font(fam, "", FONT_NODO)
    box = {}
    for n in nodi:
        t = str(n.get("testo") or "").strip() or "…………"
        righe = _taglia(pdf, t, NODO_W - 4, 3)
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
        # la punta della freccia
        import math
        ang = math.atan2(ey - sy, ex - sx)
        p1 = (ex - 3 * math.cos(ang - 0.4), ey - 3 * math.sin(ang - 0.4))
        p2 = (ex - 3 * math.cos(ang + 0.4), ey - 3 * math.sin(ang + 0.4))
        pdf.set_fill_color(60, 60, 60)
        pdf.polygon([(ex, ey), p1, p2], style="F")
        vb = pulito(str(c.get("verbo") or ""))
        if vb:
            pdf.set_font(fam, "", 8)
            w = min(40, pdf.get_string_width(vb) + 3)
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            pdf.set_fill_color(255, 255, 255)
            pdf.set_xy(mx - w / 2, my - 2.4)
            pdf.cell(w, 4.8, vb if pdf.get_string_width(vb) <= w else vb[:30] + "…", align="C",
                     fill=True)
    pdf.set_font(fam, "", FONT_NODO)
    for nid, (cx, cy, w, h, righe) in box.items():
        n = per_id[nid]
        pdf.set_fill_color(234, 240, 250) if n.get("da") is not None else pdf.set_fill_color(
            253, 243, 224)
        pdf.set_draw_color(40, 70, 140)
        pdf.rect(cx - w / 2, cy - h / 2, w, h, style="DF", round_corners=True, corner_radius=2)
        for i, r in enumerate(righe):
            pdf.set_xy(cx - w / 2 + 2, cy - h / 2 + 2 + i * RIGA)
            pdf.cell(w - 4, RIGA, pulito(r), align="C")
    pdf.set_xy(MARGINE, ALTO - MARGINE - 5)
    pdf.set_font(fam, "", 8)
    pdf.cell(0, 5, pulito("Azzurro: i concetti del quadro · arancio chiaro: i concetti aggiunti. "
                          "Lo schema a elenco è nella pagina 2."))

    # ── pagina 2: l'elenco ──
    pdf.add_page()
    testa("pagina 2 di 2: lo schema a elenco")
    pdf.set_y(TESTA + 6)
    for n in nodi:
        if pdf.get_y() > ALTO - MARGINE - 12:
            break
        t = str(n.get("testo") or "").strip() or "…………"
        pag = [pagine.get(int(p)) for p in n.get("pagine") or () if pagine.get(int(p))]
        pdf.set_font(fam, gr, 11)
        pdf.multi_cell(0, 5.5, pulito(t + (f"  ({', '.join(pag)})" if pag else "")),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 10)
        for c in coll:
            if int(c["da"]) != int(n["id"]):
                continue
            altro = per_id.get(int(c["a"]))
            if altro is None:
                continue
            pdf.set_x(MARGINE + 6)
            pdf.multi_cell(0, 5, pulito(f"{freccia} {c.get('verbo') or ''} {freccia} "
                                        f"{str(altro.get('testo') or '').strip() or '…………'}"),
                           new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)
    return bytes(pdf.output())
