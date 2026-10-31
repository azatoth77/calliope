import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Il ripasso da ascoltare nella pagina vera (31/10, passo 9, issue #249, epic #251;
schermi/pagina/studio.js «Ascolta», POST /api/studio/ascolta).

Nel browser vero (Edge o Chromium senza finestra; senza si salta), il server degli schermi vero su
127.0.0.1, Leo (di fantasia) con la verifica di storia di `prova_studio_mappa_pagina.py`, tre carte
e un argomento col titolo in HTML; l'audio con una voce di Piper finta (un tono, niente Piper):
- telefono a 390×844: la sezione «Ascolta» nella home, «Ripasso da ascoltare» apre le parti (il
  titolo con textContent: l'HTML resta testo); «Ascolta» prepara l'audio (202) e lo suona dal blob:
  la pagina dice che suona e il telefono tratta la stanza come «Calliope parla» (half-duplex);
  «Pausa», la velocità, −15 s; la voce che ascolta lo ferma e quando torna a dormire riparte da sola;
  a 320×693, anche col testo al 125 %, niente di lato e tocchi ≥ 44 px; una prova aperta: la
  parte dopo non arriva, l'audio in memoria si butta e la pagina lo dice;
- il PC personale (legato a un satellite): la sezione, l'audio che suona (la CSP del PC ammette
  il blob) e la stanza del satellite in pausa col motivo «ripasso», ripresa alla pausa;
- nessun errore JavaScript né violazione della CSP.
Con CALLIOPE_FOTO=<cartella> gli screenshot. ~25 s.

    python prove/prova_studio_ascolta_pagina.py
"""

import json
import math
import shutil
import tempfile
import time
import types
from pathlib import Path

import prova_studio_mappa_pagina as PMP

B = PMP.B
TMP = Path(tempfile.mkdtemp(prefix="calliope-studio-ascolta-pagina-"))
LEO, ANDREA, REG = PMP.LEO, PMP.ANDREA, PMP.REG
verifica, aspetta, misure = B.verifica, B.aspetta, PMP.misure
SALTATA = B.SALTATA
HTML = "<b>Le</b> spezie"


class _Pezzo:
    def __init__(self, pcm):
        self.audio_int16_bytes = pcm


class VoceTono:
    """Una voce di Piper finta: un tono di 0,05 s a carattere (si sente, il browser lo suona)."""

    def __init__(self, freq):
        self.config = types.SimpleNamespace(sample_rate=22050)
        self.freq = freq

    def synthesize(self, text):
        import array
        n = int(22050 * 0.05 * max(1, len(text)))
        a = array.array("h", (int(3000 * math.sin(2 * math.pi * self.freq * i / 22050))
                              for i in range(n)))
        yield _Pezzo(a.tobytes())


class StanzaFinta:
    def __init__(self):
        self.pause, self.storia = {}, []

    def stato_pausa(self, sat):
        return self.pause.get(sat)

    def pausa(self, sat, motivo="pausa", minuti=None):
        self.pause[sat] = {"motivo": motivo, "fino": time.time() + (minuti or 1) * 60}
        self.storia.append(("pausa", sat, motivo))

    def riprendi(self, sat):
        self.storia.append(("riprendi", sat))
        return self.pause.pop(sat, None) is not None


class TA(B.T):
    def tocca(self, sel):
        aspetta(lambda: not self.v("!!document.querySelector('.studio-h-ascolta button:disabled')"), 6)
        return super().tocca(sel)


def testo(t) -> str:
    return t.v("(document.querySelector('.studio-h-ascolta') || {}).innerText || ''") or ""


def stato(t) -> dict:
    return (t.v("window.CalliopeStudio && window.CalliopeStudio.stato ? "
                "window.CalliopeStudio.stato().ascolta : null") or {})


def prepara(st):
    vid, _sk = PMP.prepara(st)
    a = [x["id"] for x in st.argomenti(LEO, vid)]
    st.rinomina_argomento(LEO, a[0], HTML)
    for k in range(3):
        st.aggiungi_carta(LEO, vid, f"Domanda {k}?", f"Risposta {k}", argomento=a[0])
    return vid


def apri(t):
    t.v("location.hash = '#/cose'; 1")
    aspetta(lambda: t.v("!!document.querySelector('#tessere [data-tessera=\"studio\"]:not(.presto)')"), 10)
    t.tocca('#tessere [data-tessera="studio"]')
    return aspetta(lambda: t.v("!!document.querySelector('.studio-h-ascolta button[data-ascolta=\"apri\"]')"), 8)


def suona(t):
    return aspetta(lambda: (stato(t) or {}).get("suona"), 15)


def scenario_telefono(t, st, vid):
    T_ = "window.calliopeTelefono"
    verifica("pagina caricata e collegata", bool(aspetta(lambda: t.v(f"!!{T_} && {T_}.st.collegato"), 15)))
    verifica("la home: la sezione «Ascolta»", bool(apri(t)), testo(t))
    t.tocca('.studio-h-ascolta button[data-ascolta="apri"]')
    ok = aspetta(lambda: t.v("document.querySelectorAll('.studio-a-parte').length") >= 2, 8)
    el = testo(t)
    verifica("le parti: «Parte 1 · Argomento 1», il titolo come testo (l'HTML resta testo), le carte",
             bool(ok) and "Parte 1 · Argomento 1" in el and HTML in el and "Le carte" in el
             and not t.v("!!document.querySelector('.studio-h-ascolta .studio-a-dato b')"), el[:400])
    misure(t, "390×844 con le parti del ripasso")
    B.foto(t, "studio-ascolta-390x844.png")
    t.tocca('.studio-h-ascolta .studio-a .studio-h-primo[data-ascolta="parte"]')
    ok = suona(t)
    s = stato(t)
    verifica("«Ascolta»: l'audio preparato (202) e suonato dal blob", bool(ok) and s.get("url")
             and s.get("parte") == 1, s)
    verifica("mentre suona il telefono tratta la stanza come «Calliope parla» (half-duplex)",
             bool(aspetta(lambda: t.v(f"{T_}.st.ripasso === true"), 4)))
    misure(t, "390×844 col lettore")
    B.foto(t, "studio-ascolta-lettore-390x844.png")
    t.tocca('.studio-h-ascolta button[data-ascolta="velocita"]')
    verifica("la velocità: 1,25×", bool(aspetta(lambda: (stato(t) or {}).get("velocita") == 1.25, 4)))
    t.tocca('.studio-h-ascolta button[data-ascolta="pausa"]')
    ok = aspetta(lambda: not (stato(t) or {}).get("suona"), 4)
    verifica("«Pausa»: si ferma, e la stanza torna normale", bool(ok)
             and bool(aspetta(lambda: t.v(f"{T_}.st.ripasso === false"), 4)))
    t.tocca('.studio-h-ascolta button[data-ascolta="riprendi"]')
    verifica("…e riparte", bool(suona(t)))
    t.tocca('.studio-h-ascolta button[data-ascolta="indietro"]')
    t.v("document.dispatchEvent(new CustomEvent('calliope:voce', {detail: {stato: 'ascolta'}})); 1")
    ok = aspetta(lambda: not (stato(t) or {}).get("suona") and (stato(t) or {}).get("perVoce"), 4)
    verifica("Calliope ascolta (il nome): il ripasso si ferma da solo", bool(ok), stato(t))
    t.v("document.dispatchEvent(new CustomEvent('calliope:voce', {detail: {stato: 'dorme'}})); 1")
    verifica("…torna a dormire: riparte da solo", bool(suona(t)), stato(t))
    B.dimensione(t, 320, 693)
    t.v("document.querySelector('.studio-h-ascolta').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 col lettore")
    B.foto(t, "studio-ascolta-320x693.png")
    t.v("document.documentElement.style.fontSize = '125%'; 1")
    t.v("document.querySelector('.studio-h-ascolta').scrollIntoView({block: 'start'}); 1")
    misure(t, "320×693 col lettore e il testo grande")
    t.v("document.documentElement.style.fontSize = ''; 1")
    B.dimensione(t, 390, 844)
    # Una prova aperta: la parte dopo non arriva, l'audio si butta
    st.inizia_prova(LEO, vid)
    t.tocca('.studio-h-ascolta button[data-ascolta="parte"][data-dati*="\\"n\\":2"]')
    ok = aspetta(lambda: (stato(t) or {}).get("prova"), 8)
    verifica("una prova aperta: la pagina lo dice, niente suona, l'audio in memoria via",
             bool(ok) and "prova in corso" in testo(t) and not (stato(t) or {}).get("suona")
             and not (stato(t) or {}).get("url"), stato(t))
    verifica("…e la stanza torna normale", bool(aspetta(lambda: t.v(f"{T_}.st.ripasso === false"), 4)))


def scenario_pc(t, stanza):
    B.dimensione(t, 1440, 900)
    aspetta(lambda: t.v("!!window.calliopeSchermo"), 10)
    verifica("PC: la sezione «Ascolta»", bool(apri(t)), testo(t)[:300])
    t.tocca('.studio-h-ascolta button[data-ascolta="apri"]')
    aspetta(lambda: t.v("document.querySelectorAll('.studio-a-parte').length") >= 2, 8)
    t.tocca('.studio-h-ascolta .studio-a .studio-h-primo[data-ascolta="parte"]')
    verifica("PC: l'audio suona dal blob (media-src blob: nella CSP)", bool(suona(t)), stato(t))
    ok = aspetta(lambda: stanza.pause.get(5, {}).get("motivo") == "ripasso", 6)
    verifica("PC legato al satellite: la stanza in pausa col motivo «ripasso»", bool(ok), stanza.storia)
    t.tocca('.studio-h-ascolta button[data-ascolta="pausa"]')
    ok = aspetta(lambda: 5 not in stanza.pause, 6)
    verifica("…alla pausa la stanza si riprende (era sua)", bool(ok), stanza.storia)
    stanza.pausa(5, "pausa")
    t.tocca('.studio-h-ascolta button[data-ascolta="riprendi"]')
    suona(t)
    t.tocca('.studio-h-ascolta button[data-ascolta="pausa"]')
    time.sleep(1.0)
    verifica("contrario: la pausa scelta da una persona non si tocca",
             stanza.pause.get(5, {}).get("motivo") == "pausa", stanza.storia)
    t.v("document.querySelector('.studio-h-ascolta').scrollIntoView({block: 'start'}); 1")
    B.foto(t, "studio-ascolta-pc.png")


def main() -> int:
    import prova_telefono_pagina as PTP
    import prova_telefono_schermo as PTS
    shutil.rmtree(PTP.TMP, ignore_errors=True)
    PTP.TMP = TMP
    try:
        exe = PTP.browser()
        if exe is None:
            print("Nessun Edge né Chromium: prova saltata.")
            return SALTATA
        cfg, srv, hub, web = PTS.avvia(TMP / "server")
        from calliope import minori
        from calliope import studio as S
        from calliope.studio import ascolta as A
        cfg.studio_modo, cfg.studio_cartella, cfg.studio_lettura = "attivo", "studio", False
        minori.prepara(cfg, registry=REG)
        st = S.Studio(cfg, registry=REG, log=lambda m: None)
        st.avvia_lettura(None, avvia=False)
        voci = {"cal.onnx": VoceTono(440), "lib.onnx": VoceTono(330)}
        st.sintesi = A.Sintesi(voci.__getitem__, "cal.onnx", "lib.onnx", log=lambda m: None)
        serv = B.Servizi()
        serv.studio = st
        stanza = StanzaFinta()
        serv.stanza = stanza
        hub.servizi = serv
        hub.profilo = REG.by_id
        hub.tool_ctx = types.SimpleNamespace(studio=st)
        vid = prepara(st)
        _, token = srv.archivio.crea_con_token("telefono", proprietario="l1", proprietario_nome="Leo")
        from prova_parla_pc import CollFinto
        cfg.schermi_sezioni = True
        srv.collegati.append(CollFinto(5, "cameretta"))
        s_pc, t_pc = hub.archivio.crea_con_token("cameretta", proprietario="l1", proprietario_nome="Leo")
        hub.archivio.lega_satellite(s_pc["id"], 5)
        hub._rinfresca()
        opz = ("--autoplay-policy=no-user-gesture-required",)
        pagina = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/telefono/", profilo="profilo-studio-ascolta",
                            opzioni=("--window-size=390,844",) + opz)
        t = TA(pagina)
        try:
            pagina._chiama("DOM.enable")
            aspetta(lambda: pagina.valuta("document.readyState") == "complete", 10)
            pagina.valuta(f"localStorage.setItem('calliope.telefono.token', {json.dumps(token)}); 1")
            pagina._chiama("Page.reload")
            time.sleep(0.5)
            B.dimensione(t, 390, 844)
            scenario_telefono(t, st, vid)
            pagina.pompa(0.3)
            errori = [r for r in pagina.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
            verifica("telefono: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pagina.chiudi()
        # Per il PC una verifica nuova, senza la prova aperta
        st.dati.scrivi("UPDATE studio_prove SET stato = 'annullata'")
        pc = PTP.Pagina(exe, f"http://127.0.0.1:{web.port}/#t={t_pc}", profilo="profilo-studio-ascolta-pc",
                        opzioni=("--window-size=1440,900",) + opz)
        tp = TA(pc)
        try:
            pc._chiama("DOM.enable")
            scenario_pc(tp, stanza)
            pc.pompa(0.3)
            errori = [r for r in pc.log if r.startswith(("ECCEZIONE", "ERROR")) or "Content Security" in r]
            verifica("PC: nessun errore JavaScript né violazione della CSP", not errori, "; ".join(errori)[:300])
        finally:
            pc.chiudi()
            web.ferma()
            srv.ferma()
            st.close()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\nTutto bene." if not B.ERRORI else f"\n{len(B.ERRORI)} prove non riuscite.")
    return 1 if B.ERRORI else 0


if __name__ == "__main__":
    sys.exit(main())
