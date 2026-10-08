import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""La scheda del cassetto dei file nella pagina vera (08/10/2026, calliope/cassetto.py): Edge o
Chromium senza finestra comandato con DevTools (senza browser si salta), server degli schermi
vero su 127.0.0.1, cassetto in una cartella temporanea.

- schermo personale di Dario: la scheda «File in scadenza» col carosello (foto con la
  miniatura, PDF e zip con la sigla; nome, quando e da dove, scadenza), «Tieni» solo dove si
  può (non sullo zip), pulsanti di almeno 44 px;
- «Tieni ancora 7 giorni» → la frase nella scheda e la scadenza spostata; «Tieni» sul PDF →
  nella cartella personale dell'archivio, la scheda aggiornata al suo posto senza quel file;
  «Elimina» sulla foto; «Elimina tutti» al primo tocco chiede il secondo e non elimina, al
  secondo sì, e la scheda resta con la frase;
- lo schermo personale di Teodora non riceve niente, e i suoi file restano;
- nessun errore JavaScript né violazione della CSP. ~15 s.
"""

import json
import shutil
import tempfile
from pathlib import Path

import prova_cruscotto_pagina as PCP
import prova_telefono_pagina as PTP

TMP = Path(tempfile.mkdtemp(prefix="calliope-cassetto-pagina-"))
ERRORI = []
SALTATA = 77
aspetta = PCP.aspetta
SEL = '#principale article.scheda.tipo-cassetto'


def verifica(nome, ok, dettaglio=""):
    print(("ok  " if ok else "NO  ") + nome + (f"  ({str(dettaglio)[:300]})" if dettaglio else ""),
          flush=True)
    if not ok:
        ERRORI.append(nome)


STATO = f"""(() => {{
  const s = document.querySelector({json.dumps(SEL)});
  if (!s) return null;
  const voci = [...s.querySelectorAll('.cassetto-voce')].map(v => ({{
    nome: v.querySelector('.cassetto-nome').textContent,
    img: !!v.querySelector('.cassetto-anteprima img[src^="data:image/jpeg;base64,"]'),
    sigla: (v.querySelector('.cassetto-sigla') || {{}}).textContent || null,
    pulsanti: [...v.querySelectorAll('button')].map(b => b.textContent),
    testo: v.innerText,
  }}));
  const bott = [...s.querySelectorAll('button')].map(b => b.getBoundingClientRect().height);
  return {{voci, tutti: [...s.querySelectorAll('.cassetto-tutti button')].map(b => b.textContent),
          esito: (s.querySelector('.esito-cassetto') || {{}}).textContent || '',
          nota: [...s.querySelectorAll('.corpo > p.sotto')].map(p => p.textContent),
          altezza: Math.min(...bott)}};
}})()"""


def stato(p):
    return p.valuta(STATO) or {}


def clic(p, testo, voce=None):
    """Tocco sul pulsante con quel testo (nella voce col nome `voce`, o in alto)."""
    js = (f"(() => {{ const s = document.querySelector({json.dumps(SEL)});"
          f" const box = {json.dumps(voce)} === null ? s.querySelector('.cassetto-tutti') :"
          f" [...s.querySelectorAll('.cassetto-voce')].find(v => v.querySelector('.cassetto-nome')"
          f".textContent === {json.dumps(voce)});"
          f" const b = box && [...box.querySelectorAll('button')].find(b => b.textContent === "
          f"{json.dumps(testo)}); if (!b) return null; b.dataset.provaTocco = '1'; return 1; }})()")
    if not p.valuta(js):
        return False
    ok = PCP.tocca(p, 'button[data-prova-tocco="1"]')
    p.valuta("document.querySelectorAll('[data-prova-tocco]').forEach(b => delete "
             "b.dataset.provaTocco); 1")
    return ok


def prova(exe, hub, web, cas):
    from prova_immagini import foto
    import allegati_finti as A
    from calliope.allegati import prepara
    arch = hub.archivio
    _, t_dario = arch.crea_con_token("studio", proprietario="dario", proprietario_nome="Dario")
    _, t_anna = arch.crea_con_token("cucina", proprietario="teodora", proprietario_nome="Teodora")
    hub._rinfresca()
    f = cas.metti_foto(foto(persona="dario"), "dario")
    pdf = cas.metti_allegato(prepara(A.pdf([A.BOLLETTA]), "bolletta luce.pdf", persona="dario"),
                             "dario")
    z = cas.metti("dario", A.zip_percorsi(), "archivio.zip", "zip")
    a = cas.metti("teodora", b"suo", "suo.txt", "testo")
    cas.ora.avanti(6)
    base = f"http://127.0.0.1:{web.port}/"
    dario = PTP.Pagina(exe, base + f"#t={t_dario}", profilo="profilo-cassetto-dario",
                       opzioni=("--window-size=1280,800",))
    teodora = PTP.Pagina(exe, base + f"#t={t_anna}", profilo="profilo-cassetto-teodora",
                      opzioni=("--window-size=1280,800",))
    try:
        for p in (dario, teodora):
            aspetta(lambda p=p: p.valuta("document.getElementById('stato-testo').textContent")
                    == "collegato", 10)
        aspetta(lambda: len(hub.collegati()) >= 2, 10)
        righe = cas.elenco("dario", cas.avviso_giorni * 86400)
        verifica("tre file di Dario in scadenza", len(righe) == 3)
        n = cas.manda_scheda(hub, "dario", cas.scheda("dario", righe))
        cas.schede_aperte["dario"] = {r["id"] for r in righe}
        verifica("la scheda va allo schermo personale di Dario (aperto)", n == 1, n)
        ok = aspetta(lambda: len(stato(dario).get("voci", [])) == 3, 10)
        st = stato(dario)
        verifica("carosello con tre file: la foto con la miniatura, PDF e zip con la sigla",
                 bool(ok) and [v["img"] for v in st["voci"]].count(True) == 1
                 and {v["sigla"] for v in st["voci"]} == {None, "PDF", "ZIP"}, st)
        pdf_v = next((v for v in st.get("voci", []) if v["sigla"] == "PDF"), {})
        zip_v = next((v for v in st.get("voci", []) if v["sigla"] == "ZIP"), {})
        verifica("nome, quando e da dove, scadenza", "bolletta luce.pdf" == pdf_v.get("nome")
                 and "Arrivato" in pdf_v.get("testo", "") and "dal telefono" in pdf_v.get(
                     "testo", "") and "Scade domani" in pdf_v.get("testo", ""), pdf_v)
        verifica("«Tieni» solo dove si può (non sullo zip); Tieni ancora ed Elimina sempre",
                 pdf_v.get("pulsanti") == ["Tieni", "Elimina", "Tieni ancora 7 giorni"]
                 and zip_v.get("pulsanti") == ["Elimina", "Tieni ancora 7 giorni"],
                 (pdf_v.get("pulsanti"), zip_v.get("pulsanti")))
        verifica("in alto «Elimina tutti» e «Tieni tutti»",
                 st.get("tutti") == ["Elimina tutti", "Tieni tutti"], st.get("tutti"))
        verifica("pulsanti di almeno 44 px", (st.get("altezza") or 0) >= 44, st.get("altezza"))
        dario.pompa(1.2)
        PCP.foto(dario, "cassetto-1280x800.png")
        verifica("lo schermo di Teodora non riceve niente",
                 not teodora.valuta(f"!!document.querySelector({json.dumps(SEL)})"))
        # Tieni ancora
        prima = cas.prendi("dario", z)["scade"]
        clic(dario, "Tieni ancora 7 giorni", "archivio.zip")
        ok = aspetta(lambda: stato(dario).get("esito", "").startswith("Lo tengo fino a"), 8)
        verifica("«Tieni ancora 7 giorni»: la frase nella scheda e la scadenza spostata",
                 bool(ok) and cas.prendi("dario", z)["scade"] > prima + 5 * 86400,
                 stato(dario).get("esito"))
        # Tieni sul PDF
        clic(dario, "Tieni", "bolletta luce.pdf")
        ok = aspetta(lambda: len(stato(dario).get("voci", [])) == 2, 8)
        salvati = list(cas.archivio.cartella.rglob("*.pdf"))
        verifica("«Tieni» sul PDF: nella cartella personale dell'archivio, la scheda senza",
                 bool(ok) and len(salvati) == 1 and salvati[0].parent.name == "Dario"
                 and cas.prendi("dario", pdf) is None, (salvati, stato(dario).get("voci")))
        # Elimina tutti: due tocchi
        clic(dario, "Elimina tutti")
        dario.pompa(0.3)
        st = stato(dario)
        verifica("«Elimina tutti» al primo tocco chiede il secondo e non elimina",
                 "Tocca di nuovo per eliminarli tutti" in st.get("tutti", [])
                 and len(cas.elenco("dario")) == 2, st.get("tutti"))
        clic(dario, "Tocca di nuovo per eliminarli tutti")
        ok = aspetta(lambda: stato(dario).get("voci") == [], 8)
        st = stato(dario)
        verifica("al secondo tocco: eliminati, la scheda resta con la frase",
                 bool(ok) and not cas.elenco("dario") and cas.prendi("dario", f) is None
                 and "Eliminati 2 file." in st.get("nota", []), st)
        verifica("i file di Teodora restano", cas.prendi("teodora", a) is not None)
        for p, nome in ((dario, "Dario"), (teodora, "Teodora")):
            p.pompa(0.3)
            errori = [x for x in p.log if x.startswith("ECCEZIONE") or "Content Security" in x]
            verifica(f"{nome}: nessun errore JavaScript né violazione della CSP", not errori,
                     "; ".join(errori)[:300])
    finally:
        for p in (dario, teodora):
            p.chiudi()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    exe = PTP.browser()
    if exe is None:
        print("Nessun Edge né Chromium: prova saltata.")
        return SALTATA
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    from calliope.config import Config
    from calliope.schermi import ArchivioSchermi, Schermi
    from calliope.schermi.server import ServerSchermi
    import prova_cassetto as PCAS
    cfg = Config()
    cfg.config_dir = str(TMP)
    cfg.memory_db = str(TMP / "memoria.db")
    hub = Schermi(cfg, ArchivioSchermi(cfg.memory_db), log=lambda m: None)
    web = ServerSchermi(hub, "127.0.0.1", PTP.porta_libera(), attesa_porta_s=5).avvia()
    hub.server = web
    cas, _ = PCAS.nuovo(TMP / "cassetto")
    hub.cassetto = cas
    try:
        prova(exe, hub, web, cas)
    finally:
        web.ferma()
        cas.close()
        hub.archivio.close()
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not ERRORI else f"\n{len(ERRORI)} prove non riuscite.")
    return 1 if ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
