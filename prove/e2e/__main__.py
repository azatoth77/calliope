"""
Il runner della prova end-to-end, sulla DGX (06/10/2026). Di solito lo lancia
`python -m prove.e2e.lancia` dal portatile; a mano, dalla cartella di una versione:

    PYTHONPATH=. .venv/bin/python -m prove.e2e [--aree casa,minori] [--copioni id,…]
        [--senza-lenti] [--dati ~/calliope-e2e] [--guardia 180] [--tieni]

Prepara l'istanza (istanza.py), l'HA finto, il PC finto e due satelliti veri con microfono e
casse finti (studio, cucina), poi esegue i copioni (copioni.py) solo quando la Calliope vera
tace da `--guardia` secondi; a fine lavoro ferma tutto e cancella la cartella dell'istanza,
lasciando solo `risultati/<data>/` (rapporto.txt, passi.jsonl, riassunto.json: niente audio).
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import quote

import numpy as np

QUI = Path(__file__).resolve().parent
RADICE = QUI.parent.parent
for p in (str(RADICE), str(RADICE / "prove")):
    if p not in sys.path:
        sys.path.insert(0, p)

from prove.e2e import copioni as C  # noqa: E402
from prove.e2e import verifica as V  # noqa: E402
from prove.e2e.istanza import Istanza, pulisci  # noqa: E402
from prove.e2e.satelliti import SatelliteE2E  # noqa: E402
from prove.e2e.voci import PERSONE, Voci, wav_bytes, ricampiona  # noqa: E402

FOLLOWUP_PAUSA_S = 9.5           # oltre la finestra di ascolto (8 s): il copione dopo è nuovo


class Runner:
    def __init__(self, a):
        self.a = a
        self.dati = Path(a.dati).expanduser()
        self.vera = Path(a.vera).expanduser()
        self.codice = Path(a.codice).expanduser() if a.codice else RADICE
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        self.out = self.dati / "risultati" / stamp
        self.out.mkdir(parents=True, exist_ok=True)
        self._log = open(self.out / "runner.log", "a", encoding="utf-8")
        self.passi: list[dict] = []
        self.sat: dict[str, SatelliteE2E] = {}
        self.ha = self.pc = None
        self.sessione = None
        self.ultima_fine = 0.0
        self.attese_guardia = 0.0

    def log(self, m: str):
        riga = f"{datetime.datetime.now():%H:%M:%S} {m}"
        print(riga, flush=True)
        self._log.write(riga + "\n")
        self._log.flush()

    # ───────────── preparazione ─────────────
    def prepara(self):
        import ha_finto
        from pc_finto import FakePC
        from calliope.documenti.consegna import LocalDelivery
        from calliope.satellite.esecutore import EsecutoreSatellite
        ha_finto.AREE["taverna"] = {"name": "Taverna", "aliases": [], "floor_id": "terra"}
        entita = ha_finto.entita_casa() + [ha_finto._e("light.taverna", "Taverna", "taverna",
                                                       "off")]
        self.ha = ha_finto.FakeHA(token=__import__("prove.e2e.istanza", fromlist=["x"]).TOKEN_HA,
                                  entita=entita).avvia()
        reale = self.dati / "voce-reale"
        self.voci = Voci(self.vera / "voices", reale if reale.is_dir() else None)
        self.ist = Istanza(self.dati, self.codice, self.vera, log=self.log,
                           sorgente=(Path(self.a.calliope).expanduser()
                                     if getattr(self.a, "calliope", None) else None),
                           stt=getattr(self.a, "stt", None))
        self.ist.aspetta_silenzio(self.a.guardia, motivo="prima di preparare l'istanza")
        from prove.e2e.istanza import modelli_ollama
        self.ollama_prima = modelli_ollama()
        self.log(f"[e2e] modelli in Ollama prima della prova: {sorted(self.ollama_prima)}")
        self.ist.prepara(self.voci, self.ha.url)
        self.cfg = self.ist.cfg()
        self.ist.avvia()
        url = f"ws://127.0.0.1:{self.ist.porta_satelliti}"
        wake = self.cfg.wake_model
        self.pc = FakePC(volume=40)
        ese = EsecutoreSatellite(self.pc, LocalDelivery(self.dati / "istanza" / "portatile"),
                                 "portatile", log=lambda m: None)
        for stanza, e in (("studio", ese), ("cucina", None)):
            s = SatelliteE2E(stanza, url, self.ist.token_sat[stanza],
                             self.dati / "istanza" / f"sat-{stanza}", wake, esecutore=e)
            self.sat[stanza] = s
        t0 = time.monotonic()
        for s in self.sat.values():
            if not s.avvia(timeout=900):
                raise RuntimeError(f"il satellite {s.stanza} non si collega: "
                                   + self.ist.log_testo()[-2000:])
        self.log(f"[e2e] satelliti collegati in {time.monotonic() - t0:.0f} s")
        for s in self.sat.values():
            s.aspetta_zitta(120)
        self._accedi_schermo()

    def _accedi_schermo(self):
        import httpx
        r = self.ist.richiesta_schermo.get("studio")
        if not r:
            return
        self.http = httpx.Client(base_url=f"http://127.0.0.1:{self.ist.porta_schermi}",
                                 timeout=20)
        try:
            a = self.http.post("/api/accedi", headers={"Authorization": f"Bearer {r}"})
            self.sessione = a.json().get("sessione")
        except Exception as e:  # noqa: BLE001
            self.log(f"[e2e] schermo: accesso non riuscito ({e})")
            return
        # Gli eventi della pagina dello studio (stato della voce per stanza, schede)
        self.eventi_schermo: list[tuple[float, str, dict]] = []
        base = f"http://127.0.0.1:{self.ist.porta_schermi}"

        def ascolta():
            while True:
                ev = None
                try:
                    with httpx.stream("GET", f"{base}/eventi?sessione={self.sessione}",
                                      timeout=None) as rr:
                        for line in rr.iter_lines():
                            if line.startswith("event: "):
                                ev = line[7:]
                            elif line.startswith("data: "):
                                try:
                                    d = json.loads(line[6:])
                                except ValueError:
                                    d = {}
                                self.eventi_schermo.append((time.monotonic(), ev, d))
                except Exception:  # noqa: BLE001
                    time.sleep(2)
        threading.Thread(target=ascolta, daemon=True, name="sse-studio").start()

    def voce_studio(self, t0: float, t1: float) -> list[str]:
        return [d.get("stato") for x, ev, d in getattr(self, "eventi_schermo", [])
                if ev == "voce" and t0 <= x <= t1 and isinstance(d, dict)]

    def disponibili(self) -> set:
        """Cosa c'è per i copioni: registrazioni vere, agente, web, biblioteca, schermo."""
        import httpx
        ok = set()
        if self.voci.cartella_reale and self.voci.ha_reale("ore"):
            ok.add("reale")
        if self.sessione:
            ok.add("schermo")
        if getattr(self.cfg, "biblioteca_mini", None) and Path(self.cfg.biblioteca_mini).is_file():
            ok.add("biblioteca")
        if getattr(self.cfg, "web_searxng_url", None):
            ok.add("web")
        if getattr(self.cfg, "agenti_url", None):
            try:
                httpx.get(self.cfg.agenti_url.rstrip("/") + "/models", timeout=5)
                ok.add("agente")
            except Exception:  # noqa: BLE001
                pass
        return ok

    # ───────────── un passo ─────────────
    def audio(self, passo: C.Passo, testo: str | None = None):
        if testo is not None:
            return self.voci.frase(passo.chi, testo)
        if passo.reale:
            return self.voci.frase("Carlo", reale=passo.reale)
        return self.voci.frase(passo.chi, passo.testo)

    def di(self, sat: SatelliteE2E, audio: np.ndarray, passo: C.Passo, testo: str):
        """Dice la frase; se la wake word non scatta la ridice (Piper: un'altra pronuncia;
        registrazione: un po' più piano). (fine del parlato, mandata?, tentativi)"""
        t, mandata = sat.di(audio)
        tentativi = 1
        while not mandata and tentativi < 3:
            self.log(f"    (frase non mandata: wake word o VAD; la ridico) {testo!r}")
            tentativi += 1
            if passo.reale:
                audio = audio * 0.8
            elif passo.tipo == "voce":
                audio, _ = self.audio(passo, testo)
            t, mandata = sat.di(audio)
        return t, mandata, tentativi

    def turni_nuovi(self, n0: int, attesa: float = 10.0) -> list[dict]:
        fine = time.monotonic() + attesa
        while time.monotonic() < fine:
            t = self.ist.turni()
            if len(t) > n0:
                time.sleep(0.3)
                return self.ist.turni()[n0:]
            time.sleep(0.2)
        return self.ist.turni()[n0:]

    def esegui_passo(self, cop: C.Copione, i: int, passo: C.Passo, prec: dict | None) -> dict:
        sat = self.sat[passo.stanza]
        n0 = len(self.ist.turni())
        ha0, pc0 = len(self.ha.servizi), len(self.pc.azioni)
        rec = {"copione": cop.id, "area": cop.area, "passo": i, "chi": passo.chi,
               "stanza": passo.stanza, "tipo": passo.tipo}
        testo_detto = passo.testo
        t_fine = None
        altro = None
        if passo.dati.get("se_non_sfida") and V.parole_sfida((prec or {}).get("risposta", "")):
            rec.update(esito_passo="ok", detto=None, nota="sfida già chiesta: «sì» non serve")
            rec["risposta"] = (prec or {}).get("risposta", "")
            return rec
        if passo.tipo in ("voce", "sfida"):
            if passo.tipo == "sfida":
                parole = V.parole_sfida((prec or {}).get("risposta", ""))
                if not parole:
                    rec.update(esito_passo="saltato", errori=["nessuna frase di sfida da ripetere"])
                    return rec
                # Le parole staccate, come le direbbe una persona che le ripete
                testo_detto = ". ".join(w.strip().capitalize() for w in parole.split(",")) + "."
                audio, testo_detto = self.audio(passo, testo_detto)
            else:
                audio, testo_detto = self.audio(passo)
            if passo.dati.get("insieme"):
                chi2, frase2, stanza2 = passo.dati["insieme"].split("|")
                a2, _ = self.voci.frase(chi2, frase2)
                altro = {"chi": chi2, "frase": frase2, "stanza": stanza2}

                def secondo():
                    time.sleep(0.3)
                    t2, m2 = self.sat[stanza2].di(a2)
                    altro.update(t=t2, mandata=m2)
                    if t2:
                        altro["risposta"] = self.sat[stanza2].risposta(t2, passo.max_s)
                th = threading.Thread(target=secondo, daemon=True)
                th.start()
            t_fine, mandata, tentativi = self.di(sat, audio, passo, testo_detto)
            rec.update(detto=testo_detto, mandata=mandata, tentativi=tentativi,
                       reale=bool(passo.reale), durata_s=round(len(audio) / 16000, 2))
            if not mandata:
                rec.update(esito_passo="fallito", errori=["la frase non è arrivata al server "
                                                          "(wake word o VAD)"])
                return rec
        else:
            t_fine = self._schermo(passo, rec)
            if t_fine is None:
                return rec
        r = sat.risposta(t_fine, passo.max_s)
        if altro is not None:
            th.join(passo.max_s + 10)
        turni = self.turni_nuovi(n0)
        turno = self._scegli_turno(turni, passo)
        annuncio = None
        if "annuncio" in passo.attese:
            regex, secondi = passo.attese["annuncio"]
            annuncio = self._aspetta_annuncio(t_fine, regex, secondi)
        extra = {"suoni": r["suoni"], "ha": [f"{s}:{e}" for s, e, _ in self.ha.servizi[ha0:]],
                 "voce_studio": self.voce_studio(t_fine - 1.0, (r["fine_audio"] or t_fine) + 1),
                 "pc": [a[0] for a in self.pc.azioni[pc0:]], "annuncio": annuncio}
        risposta = r["testo"] or (turno or {}).get("risposta") or ""
        errori = V.controlla(passo.attese, turno, risposta, extra)
        if altro is not None:
            r2 = (altro.get("risposta") or {})
            if not r2.get("testo"):
                errori.append(f"{altro['chi']} in {altro['stanza']}: nessuna risposta")
            rec["insieme"] = {"chi": altro["chi"], "risposta": r2.get("testo", ""),
                              "lat_s": (round(r2["prima_voce"] - altro["t"], 2)
                                        if r2.get("prima_voce") and altro.get("t") else None),
                              "regole": sorted({x for t in turni for x in t.get("regole") or []})}
        lat = (round(r["prima_voce"] - t_fine, 2) if r["prima_voce"] and t_fine else None)
        rec.update(
            risposta=risposta, frasi=len(r["frasi"]), lat_s=lat,
            trascritto=(turno or {}).get("testo") or (turno or {}).get("richiesta"),
            tool=[t.get("nome") for t in (turno or {}).get("tool") or []],
            regole=(turno or {}).get("regole") or [], esito=(turno or {}).get("esito"),
            livello=(turno or {}).get("livello"), voce=(turno or {}).get("voce"),
            prima_frase_s=(turno or {}).get("prima_frase_s"),
            fine_parlato_s=(turno or {}).get("fine_parlato_s"),
            stt_s=(turno or {}).get("stt_s"), contesto=(turno or {}).get("contesto"),
            # Trascrizione (07/10, confronto A/B/C): confidenza, correzione e quanto è costata
            stt={k: (turno or {}).get(k) for k in ("stt_confidenza", "stt_correzione_ms",
                                                   "stt_correzione_scaduta", "stt_corretta",
                                                   "stt_capito")
                 if (turno or {}).get(k) is not None},
            annuncio=annuncio, extra={k: v for k, v in extra.items() if k != "annuncio"},
            errori=errori, giudizio=passo.attese.get("giudizio"),
            esito_passo="ok" if not errori else "fallito")
        from prove.e2e.istanza import modelli_ollama
        rec["ollama"] = sorted(modelli_ollama())
        if risposta and r["fine"]:
            rec["whisper"] = self._ritrascrivi(sat, t_fine, max(r["fine"], r["fine_audio"]),
                                               risposta)
        if r["fine"]:
            self.ultima_fine = r["fine"]
        return rec

    def _scegli_turno(self, turni: list[dict], passo: C.Passo) -> dict | None:
        cand = [t for t in turni if t.get("esito") not in ("lavoro",)]
        stessi = [t for t in cand if t.get("satellite") in (passo.stanza, None)]
        return (stessi or cand or [None])[-1]

    def _aspetta_annuncio(self, t: float, regex: str, secondi: float) -> str | None:
        import re
        fine = time.monotonic() + secondi
        while time.monotonic() < fine:
            for s in self.sat.values():
                for _, _, testo in s.eventi_dopo(t, "frase"):
                    if testo and re.search(regex, testo, re.I) and _dopo_risposta(s, t, testo):
                        s.aspetta_zitta(60)
                        return testo
            time.sleep(1.0)
        return None

    def _schermo(self, passo: C.Passo, rec: dict) -> float | None:
        """Scritto, foto o allegato dallo schermo personale dello studio."""
        if not self.sessione:
            rec.update(esito_passo="saltato", errori=["schermo personale non disponibile"])
            return None
        h = {"X-Calliope-Sessione": self.sessione}
        d = passo.dati
        t0 = time.monotonic()
        try:
            if passo.tipo == "scrivi":
                rr = self.http.post("/api/scrivi", headers=h, json={"testo": d["testo"]})
                rec["detto"] = d["testo"]
            elif passo.tipo == "foto":
                import base64
                import immagini_finte as F
                img = getattr(F, d["immagine"])()
                url = "data:image/jpeg;base64," + base64.b64encode(F.jpeg(img)).decode()
                rr = self.http.post("/api/immagine", headers=h,
                                    json={"immagine": url, "testo": d["domanda"]})
                rec["detto"] = f"[foto {d['immagine']}] {d['domanda']}"
            elif passo.tipo == "allegato":
                import allegati_finti as A
                nome = d["file"]
                dati = (A.pdf([A.BOLLETTA]) if nome.endswith(".pdf")
                        else A.ISTRUZIONE.encode("utf-8"))
                rr = self.http.post("/api/allegato", content=dati, headers={
                    **h, "Content-Type": "application/octet-stream",
                    "X-Calliope-Nome": quote(nome), "X-Calliope-Testo": quote(d["domanda"])})
                rec["detto"] = f"[allegato {nome}] {d['domanda']}"
            else:
                rec.update(esito_passo="saltato", errori=[f"tipo {passo.tipo} sconosciuto"])
                return None
        except Exception as e:  # noqa: BLE001
            rec.update(esito_passo="fallito", errori=[f"schermo: {e}"])
            return None
        if rr.status_code != 200:
            rec.update(esito_passo="fallito", errori=[f"schermo: {rr.status_code} {rr.text[:200]}"])
            return None
        return t0

    def _ritrascrivi(self, sat, t0, t1, testo) -> dict | None:
        """La voce di Calliope ritrascritta con il Whisper vero: quanto somiglia al testo."""
        import httpx
        x, rate = sat.casse.audio_tra(t0, t1 + 0.5)
        if len(x) < rate * 0.5 or not self.cfg.stt_url:
            return None
        try:
            r = httpx.post(self.cfg.stt_url.rstrip("/") + "/audio/transcriptions",
                           files={"file": ("f.wav", wav_bytes(ricampiona(x, rate)), "audio/wav")},
                           data={"model": self.cfg.stt_modello, "language": "it",
                                 "response_format": "json"}, timeout=30)
            sentito = r.json().get("text", "")
        except Exception as e:  # noqa: BLE001
            return {"errore": str(e)[:100]}
        return {"sentito": sentito, "somiglianza": round(V.somiglianza(testo, sentito), 2)}

    # ───────────── copioni ─────────────
    def pausa_tra_copioni(self):
        for s in self.sat.values():
            s.aspetta_zitta(300)
        resto = FOLLOWUP_PAUSA_S - (time.monotonic() - self.ultima_fine)
        if resto > 0:
            time.sleep(resto)
        self.attese_guardia += self.ist.aspetta_silenzio(self.a.guardia,
                                                        motivo="prima del copione")

    def esegui(self, scelti: list[C.Copione]):
        for cop in scelti:
            if not self.ist.viva():
                self.log("[e2e] l'istanza non è più viva: mi fermo")
                break
            self.pausa_tra_copioni()
            self.log(f"── {cop.id} ({cop.area}): {cop.titolo}")
            # Ogni copione comincia con il portatile sbloccato: «Blocca il PC» di reale-pc lo
            # lasciava bloccato, il «Sì» di reale-conferma-breve sentiva «il portatile è
            # bloccato» (giusto) e la proposta rimasta aperta mandava al modello il «Grazie.»
            # di reale-cortesia (giri 1 e 4 del 06/10)
            if self.pc is not None:
                self.pc.locked = False
            prec = None
            for i, passo in enumerate(cop.passi):
                if i:
                    self.sat[passo.stanza].aspetta_zitta(120)
                    # Nella finestra d'ascolto: niente pausa lunga (è la stessa conversazione)
                    time.sleep(0.6)
                try:
                    rec = self.esegui_passo(cop, i, passo, prec)
                except Exception as e:  # noqa: BLE001
                    rec = {"copione": cop.id, "area": cop.area, "passo": i, "chi": passo.chi,
                           "esito_passo": "errore", "errori": [f"{type(e).__name__}: {e}"],
                           "traccia": traceback.format_exc()[-1500:]}
                self.passi.append(rec)
                with open(self.out / "passi.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                stato = rec.get("esito_passo")
                self.log(f"   {i}. {passo.chi}: {rec.get('detto')!r} → {stato}"
                         f" [{','.join(rec.get('tool') or [])}] {rec.get('lat_s')} s"
                         f" | {(rec.get('risposta') or '')[:110]!r}")
                for e in rec.get("errori") or []:
                    self.log(f"      ✗ {e}")
                prec = rec
                if passo.dopo_s:
                    time.sleep(passo.dopo_s)
                if stato in ("errore",) or (stato == "fallito" and not rec.get("mandata", True)):
                    break                       # la conversazione non può continuare

    def telefono(self, secondi: float):
        """Fase del telefono (06/10): la pagina vera in Edge sul portatile, attraverso un
        tunnel SSH verso la porta degli schermi dell'istanza (prove/e2e/telefono.py, lanciato
        da lancia.py). Qui: il codice d'abbinamento scritto dal portatile in
        `telefono.codice` si abbina come «telefono» personale di Andrea; l'esito della pagina
        arriva in `telefono.fatto`; i turni del satellite «telefono» si controllano dal
        registro dell'istanza."""
        import os
        from calliope.satellite.__main__ import gestione
        codice_f, fatto_f = self.dati / "telefono.codice", self.dati / "telefono.fatto"
        for f in (codice_f, fatto_f):
            f.unlink(missing_ok=True)
        self.pausa_tra_copioni()
        n0 = len(self.ist.turni())
        self.log(f"[e2e] TELEFONO PRONTO porta {self.ist.porta_schermi}")
        fine = time.monotonic() + secondi
        abbinato = False
        esito = None
        while time.monotonic() < fine and self.ist.viva():
            if not abbinato and codice_f.is_file():
                codice = codice_f.read_text().strip()
                righe = []
                cwd = os.getcwd()
                try:
                    os.chdir(self.ist.ist)
                    rc = gestione(["--abbina", codice, "--stanza", "telefono", "--personale",
                                   "Andrea"], out=righe.append, cfg=self.cfg)
                finally:
                    os.chdir(cwd)
                abbinato = True
                self.log(f"[e2e] telefono abbinato (rc {rc}): {' '.join(righe)[:200]}")
            if fatto_f.is_file():
                try:
                    esito = json.loads(fatto_f.read_text(encoding="utf-8"))
                except ValueError:
                    esito = {"errore": "telefono.fatto illeggibile"}
                break
            time.sleep(1.0)
        turni = [t for t in self.ist.turni()[n0:]
                 if str(t.get("satellite") or "").startswith("telefono")]
        risp = [t for t in turni if t.get("esito") == "risposta"]
        errori = list((esito or {}).get("errori") or ([] if esito else
                                                     ["il portatile non ha risposto"]))
        if not any("ora_attuale" in [x.get("nome") for x in t.get("tool") or []]
                   or "sono le" in (t.get("risposta") or "").lower() for t in risp):
            errori.append(f"nessuna risposta all'ora dal satellite «telefono» ({len(turni)} turni)")
        t = (risp or turni or [{}])[-1]
        rec = {"copione": "telefono", "area": "telefono", "passo": 0, "chi": "Andrea",
               "tipo": "telefono", "detto": "Calliope, che ore sono? (microfono finto di Edge)",
               "risposta": t.get("risposta"), "trascritto": t.get("testo"),
               "tool": [x.get("nome") for x in t.get("tool") or []], "regole": t.get("regole"),
               "esito": t.get("esito"), "voce": t.get("voce"),
               "prima_frase_s": t.get("prima_frase_s"), "fine_parlato_s": t.get("fine_parlato_s"),
               "pagina": esito, "errori": errori,
               "esito_passo": "ok" if not errori else "fallito"}
        self.passi.append(rec)
        with open(self.out / "passi.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.log(f"[e2e] telefono: {rec['esito_passo']} {errori} | {rec['risposta']!r}")

    def chiudi(self):
        for s in self.sat.values():
            s.ferma()
        if getattr(self, "ist", None):
            self.ist.ferma()
        if self.ha:
            try:
                self.ha.ferma()
            except Exception:  # noqa: BLE001
                pass
        if getattr(self, "ollama_prima", None):
            from prove.e2e.istanza import modelli_ollama, ripristina_ollama
            dopo = modelli_ollama()
            self.ollama_dopo = sorted(dopo)
            if set(dopo) != set(self.ollama_prima):
                self.log(f"[e2e] modelli in Ollama dopo la prova: {sorted(dopo)}: rimetto "
                         f"quelli di prima")
                self.ollama_ripristino = ripristina_ollama(self.ollama_prima, log=self.log)


def _dopo_risposta(sat, t, testo) -> bool:
    """Un annuncio è una frase arrivata dopo la fine del turno del passo."""
    fini = sat.eventi_dopo(t, "fine_turno")
    if not fini:
        return False
    primo_fine = fini[0][0]
    return any(x > primo_fine and d == testo for x, _, d in sat.eventi_dopo(t, "frase"))


# ───────────── rapporto ─────────────
def riga_stt(run: Runner, passi: list[dict]) -> str:
    """La trascrizione del giro (07/10, confronto A/B/C): variante, frasi con la confidenza,
    al secondo passaggio, cambiate, tempo della correzione, frasi con parole incerte al
    modello della voce."""
    st = [p.get("stt") or {} for p in passi]
    capito = [x["stt_capito"] for x in st if x.get("stt_capito")]
    conf = [x for x in st if x.get("stt_confidenza")]
    corr = [x["stt_correzione_ms"] for x in st if x.get("stt_correzione_ms") is not None]
    corr.sort()
    al_modello = sum(1 for x in conf if (x["stt_confidenza"] or {}).get("al_modello"))
    med = corr[len(corr) // 2] if corr else None
    return (f"Trascrizione: variante {getattr(run.a, 'stt', None) or 'come la vera'}; frasi "
            f"con la confidenza {len(conf)}, al secondo passaggio {len(corr)}"
            f"{f' (mediana {med:.0f} ms, massimo {corr[-1]:.0f})' if corr else ''}, scadute "
            f"{sum(1 for x in st if x.get('stt_correzione_scaduta'))}, cambiate "
            f"{sum(1 for x in st if x.get('stt_corretta'))}, con parole incerte al modello "
            f"{al_modello}; frasi capite dal modello {len(capito)} (valse "
            f"{sum(1 for c in capito if c.get('accettata'))})")


def rapporto(run: Runner, scelti, disponibili, durata) -> str:
    from calliope import latenza
    passi = run.passi
    righe = [f"Prova end-to-end sulla DGX, {datetime.datetime.now():%d/%m/%Y %H:%M}",
             f"Durata {durata / 60:.0f} min, attesa per la Calliope vera {run.attese_guardia:.0f} s",
             f"Modello della voce: {run.ist.modello}, num_ctx {run.ist.num_ctx}",
             f"Disponibili: {', '.join(sorted(disponibili)) or '-'}"]
    from prove.e2e.istanza import modelli_ollama
    righe.append(f"Modelli in Ollama prima: {sorted(getattr(run, 'ollama_prima', {}) or {})}, "
                 f"alla fine: {sorted(modelli_ollama())} (si rimettono quelli di prima)")
    righe.append(riga_stt(run, passi))
    righe.append("")
    aree: dict[str, list] = {}
    for p in passi:
        aree.setdefault(p["area"], []).append(p)
    righe.append("Per area (passi riusciti / provati):")
    for a, ps in sorted(aree.items()):
        ok = sum(p.get("esito_passo") == "ok" for p in ps)
        righe.append(f"  {a:14s} {ok}/{len(ps)}")
    tot = sum(p.get("esito_passo") == "ok" for p in passi)
    righe.append(f"  {'TOTALE':14s} {tot}/{len(passi)}")
    saltati = [c.id for c in scelti if not any(p["copione"] == c.id for p in passi)]
    if saltati:
        righe.append(f"Copioni non eseguiti: {', '.join(saltati)}")
    righe += ["", "Passi falliti:"]
    for p in passi:
        if p.get("esito_passo") != "ok":
            righe.append(f"  [{p['copione']}#{p['passo']}] {p.get('chi')}: {p.get('detto')!r}")
            righe.append(f"     trascritto: {p.get('trascritto')!r}")
            righe.append(f"     risposta:   {(p.get('risposta') or '')[:300]!r}")
            righe.append(f"     tool {p.get('tool')} regole {p.get('regole')} esito {p.get('esito')}"
                         f" voce {p.get('voce')}")
            for e in p.get("errori") or []:
                righe.append(f"     ✗ {e}")
    giud = [p for p in passi if p.get("giudizio")]
    if giud:
        righe += ["", "Da giudicare a mano:"]
        for p in giud:
            righe.append(f"  [{p['copione']}#{p['passo']}] {p['giudizio']}: "
                         f"{(p.get('risposta') or '')[:300]!r}")
    lat = [p["lat_s"] for p in passi if p.get("lat_s") is not None and p.get("tipo") == "voce"]
    lat_base = [p["lat_s"] for p in passi if p.get("lat_s") is not None
                and p.get("tipo") == "voce" and not p.get("tool")]
    pf = [p["prima_frase_s"] for p in passi if p.get("prima_frase_s") is not None]
    fp = [p["fine_parlato_s"] for p in passi if p.get("fine_parlato_s") is not None]
    righe += ["", "Latenza (s):",
              f"  fine del parlato → prima voce sentita dal satellite: {V.quantili(lat)}",
              f"     senza tool: {V.quantili(lat_base)}",
              f"  registro dell'istanza, prima_frase_s: {V.quantili(pf)}",
              f"  registro dell'istanza, fine_parlato_s: {V.quantili(fp)}"]
    gap = [p["lat_s"] - p["fine_parlato_s"] for p in passi
           if p.get("lat_s") is not None and p.get("fine_parlato_s") is not None]
    righe.append(f"  differenza tra la voce sentita e fine_parlato_s (sintesi, rete, "
                 f"riproduzione): {V.quantili(gap)}")
    try:
        g = latenza.giorno(run.ist.turni())
        righe.append(f"  istanza come calliope stato: prima frase {g['prima_frase']}, base "
                     f"{g['base']}, con tool {g['tool']}, guardiano {g['guardiano']}")
    except Exception as e:  # noqa: BLE001
        righe.append(f"  (latenza dell'istanza non calcolata: {e})")
    try:
        vere = latenza.per_giorno(latenza.leggi(run.vera / "registro", giorni=5))
        righe.append("  Calliope vera, giorni scorsi (prima_frase mediana / p90, risposte):")
        for g, d in sorted(vere.items())[-5:]:
            pfv = d.get("prima_frase") or {}
            righe.append(f"     {g}: {pfv.get('mediana')} / {pfv.get('p90')} "
                         f"({d.get('risposte')})")
    except Exception as e:  # noqa: BLE001
        righe.append(f"  (registro vero non letto: {e})")
    wh = [p["whisper"]["somiglianza"] for p in passi
          if isinstance(p.get("whisper"), dict) and "somiglianza" in p["whisper"]]
    righe += ["", f"Voce di Calliope ritrascritta con Whisper (somiglianza al testo): "
                  f"{V.quantili(wh)}"]
    basse = [p for p in passi if isinstance(p.get("whisper"), dict)
             and p["whisper"].get("somiglianza", 1) < 0.6]
    for p in basse[:10]:
        righe.append(f"  bassa [{p['copione']}#{p['passo']}]: detto {p['risposta'][:120]!r} → "
                     f"sentito {p['whisper']['sentito'][:120]!r}")
    tent = [p for p in passi if p.get("tentativi", 1) > 1 or p.get("mandata") is False]
    reali = [p for p in passi if p.get("reale")]
    righe += ["", f"Wake word/VAD: {len(tent)} frasi ridette o perse su "
                  f"{sum(1 for p in passi if p.get('tipo') == 'voce')}; voce vera: "
                  f"{sum(1 for p in reali if p.get('tentativi', 1) == 1 and p.get('mandata'))}"
                  f"/{len(reali)} al primo colpo"]
    ric = [(p["chi"], (p.get("voce") or {}).get("nome"), (p.get("voce") or {}).get("punteggio"),
            (p.get("voce") or {}).get("modo")) for p in passi if p.get("tipo") == "voce"]
    giusti = sum(1 for chi, nome, _, _ in ric if (nome == chi) or (chi == "ospite" and not nome))
    righe.append(f"Chi parla: {giusti}/{len(ric)} riconosciuti giusti")
    for chi in PERSONE:
        pt = [s for c, n, s, m in ric if c == chi and isinstance(s, (int, float))]
        if pt:
            righe.append(f"  {chi}: punteggi {V.quantili(pt)}")
    log = run.ist.log_testo().splitlines()
    err = [r for r in log if any(k in r for k in ("Traceback", "ERRORE", "Errore", "Exception"))]
    righe += ["", f"Log dell'istanza: {len(log)} righe, {len(err)} con errori"]
    righe += [f"  {r[:200]}" for r in err[:30]]
    return "\n".join(righe)


def anonimo(s: str) -> str:
    """Niente percorsi con il nome dell'utente nei risultati."""
    return s.replace(str(Path.home()), "~")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dati", default="~/calliope-e2e")
    ap.add_argument("--vera", default="~/calliope")
    ap.add_argument("--codice", default=None)
    ap.add_argument("--aree", default="")
    ap.add_argument("--copioni", default="")
    ap.add_argument("--senza-lenti", action="store_true")
    ap.add_argument("--guardia", type=float, default=180.0)
    ap.add_argument("--telefono", type=float, default=0.0,
                    help="secondi d'attesa della prova del telefono dal portatile (0: niente)")
    ap.add_argument("--tieni", action="store_true", help="non cancellare l'istanza alla fine")
    ap.add_argument("--stt", choices=["A", "B", "B2", "C"], default=None,
                    help="variante della trascrizione (istanza.VARIANTI_STT)")
    ap.add_argument("--calliope", default=None,
                    help="cartella con calliope/ e calliope.yaml da provare (lancia --codice-qui)")
    a = ap.parse_args(argv)
    import os
    pidf = Path(a.dati).expanduser() / "runner.pid"
    pidf.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    pidf.write_text(str(os.getpid()))
    run = Runner(a)
    t0 = time.monotonic()
    scelti, disp = [], set()
    try:
        run.prepara()
        disp = run.disponibili()
        run.log(f"[e2e] disponibili: {sorted(disp)}")
        tutti = C.scegli(set(filter(None, a.aree.split(","))) or None,
                         set(filter(None, a.copioni.split(","))) or None,
                         lenti=not a.senza_lenti)
        scelti = [c for c in tutti if set(c.richiede) <= disp]
        for c in tutti:
            if c not in scelti:
                run.log(f"[e2e] salto {c.id}: manca {sorted(set(c.richiede) - disp)}")
        # I lenti (agente vero) per primi: mentre l'agente lavora i copioni aspettano
        run.esegui(scelti)
        if a.telefono:
            run.telefono(a.telefono)
    except Exception as e:  # noqa: BLE001
        run.log(f"[e2e] errore: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        testo = ""
        try:
            testo = anonimo(rapporto(run, scelti, disp, time.monotonic() - t0))
            (run.out / "rapporto.txt").write_text(testo, encoding="utf-8")
            (run.out / "riassunto.json").write_text(json.dumps({
                "passi": len(run.passi),
                "ok": sum(p.get("esito_passo") == "ok" for p in run.passi)}), encoding="utf-8")
            log = run.ist.log_testo() if getattr(run, "ist", None) else ""
            (run.out / "istanza.log").write_text(anonimo(log[-400000:]), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            run.log(f"[e2e] rapporto non scritto: {e}\n{traceback.format_exc()}")
        run.chiudi()
        if not a.tieni:
            pulisci(run.dati)
        pidf.unlink(missing_ok=True)
        print(testo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
