"""
Le misure della stanza (13/10, conversazione di stanza, passo 1: progetto § 6).

**Solo numeri**, mai parole: un file al giorno `stanza-AAAA-MM-GG.jsonl` accanto al registro
dei turni (`turn_log_dir`), con la stessa tenuta (`turn_log_days`). Una riga per fatto:

    segmento      sat, canale, voce_s, durata_s, byte, esito («riga», «scartata», «legato»),
                  motivo, attesa_s (dalla chiusura all'inizio di Whisper), ritardo_s (dalla
                  chiusura alla riga pronta), stt_s, recupero (passato davanti a un turno),
                  chiusura (dal 14/10: «silenzio», «pausa_breve» = taglio morbido vicino al
                  tetto, «lunga» = tetto duro senza pause);
                  dal passo 5 (14/10, `stanza_durante_voce`), per i segmenti detti durante la
                  voce di Calliope: durante, frasi (sue frasi confrontate), detto_nuove (loro
                  parole non ancora contate), parole (della riga trascritta), eco_tolte, residua
                  (parole rimaste che combaciano con lei), regole; motivo «eco» se tutta eco
    buttato       sat, motivo («voce»: è cominciata la voce di Calliope, «spenta», «coda_piena»,
                  «scollegato», «eco_cancello»: detto durante la voce su un satellite con l'eco
                  sul saluto oltre la soglia), voce_s
    presenza      persona (id del profilo), sat, durata_s
    cambio_stanza persona, da, a, dopo_s (dall'ultima volta sentita nell'altra stanza)
    pausa         sat, motivo, ore      ·  dimentica  sat, eventi
    cerca         (passo 4, 14/10: tool stanza_cerca) esito («trovato», «niente», «negato»,
                  «pausa», «stanza_ignota»), ms (tempo del tool), attesa (la frase d'attesa è
                  partita), attesa_ms (righe in coda aspettate), righe, caratteri, stanze,
                  tagliate, filtri (quali: parole, persona, stanza, quando, orari), chi
                  («adulto», «tutore», «minore», «ospite»): mai le parole né i nomi
    anticipo      (14/10: la ricerca anticipata di Brain, `stanza_cerca_anticipo`) esito
                  («trovato», «niente»), ms, righe, caratteri, stanze, tagliate, filtri, chi
    conoscenti    (14/10, decisione 0030, `stanza_conoscenti`) evento: gruppo_nuovo (una voce
                  sconosciuta nuova), proposta (con omonimo_famiglia, omonimo_conoscente, eta),
                  mandata (arrivata a uno schermo di chi amministra), conferma (nome_diverso,
                  cognome, nota, omonimo), rifiuto, discordi, minore, dimenticato, scaduto,
                  svuotati, promosso, declassato: mai nomi né parole
    lenta         (passo 3, 14/10, `stanza_lenta`) sat, esito («uguale», «cambiata», «divisa»,
                  «piu_voci», «tv», «allucinazione», «v2_vuota», «scaduto»: l'audio è uscito
                  dalla RAM prima del passo, «dimenticato», «errore»), testo_cambiato,
                  attribuzione (chi parla corretto), parti, motivo, tv (gli strati), stt_s
                  (tempo di Whisper), cam_ms, finestre, voce_s, attesa_s (dalla fine del
                  segmento), prompt, ritrascritto (false: senza ritrascrizione, 14/10 sera)
    lenta_riassunto  esito («fatto», «guasto»), ms, righe, caratteri
    banco         (eccezione del 14/10 sera, `stanza_audio_banco_giorni`) sat, salvato

Più, nel registro dei turni, `stanza.copertura` di ogni turno interpellato con la stanza accesa
(`dette`, `pronte`, `recupero_ms`, `oltre`): la «copertura all'interpellazione» (§ 3.11). Dal
passo 2 (14/10, `stanza_contesto`) anche `nel_contesto` (quante delle righe dette prima della
domanda sono nel blocco dei dati del turno), `scartate` (segmenti senza riga: vuoti,
allucinazioni) e `attesa_ms` (il recupero aspettato prima della risposta), e `stanza.contesto`
(`righe`, `sempre`, `tagliate`, `caratteri`, `mancano`): il blocco, in numeri. Dal 14/10 sera
(`stanza_contesto_in_storia`) anche `stanza.storia` (`nuove`, `nuove_caratteri`, `righe`,
`caratteri`, `pezzi`, `potati`, `nascosti`): le righe nuove del turno e quelle davanti al modello.

`riassunto` e `testo` fanno la sezione «Stanza» di `calliope stato --turni`: ore di parlato per
satellite, ritardo della coda (p90 < 10 s), banda (MB per ora di parlato), scartate per motivo,
presenze e cambi di stanza entro 10 minuti, copertura e `stt_s`/prima frase con e senza stanza.
"""

import datetime
import json
import threading
from pathlib import Path

PREFISSO = "stanza-"
CAMBIO_ENTRO_S = 600.0
RITARDO_P90_OBIETTIVO_S = 10.0
# Passo 5 (progetto § 6, riga 5): eco residua sotto 2 parole ogni 100 dette da Calliope
ECO_RESIDUA_OBIETTIVO = 2.0
# Passo 4 (progetto § 6, riga 4): la frase d'attesa in meno del 10 % dei turni in stanza, il
# tool sotto i 3 s al p90
ATTESA_QUOTA_OBIETTIVO = 0.10
CERCA_P90_OBIETTIVO_MS = 3000


class Misure:
    def __init__(self, cartella: str | None, giorni: int = 60):
        self.cartella = Path(cartella) if cartella else None
        self.giorni = int(giorni or 60)
        self._lock = threading.Lock()
        self._pulito = None
        self.errori = 0
        self.memoria: list[dict] = []        # le ultime righe (cruscotto, prove)

    def scrivi(self, tipo: str, **campi):
        r = {"t": datetime.datetime.now().isoformat(timespec="milliseconds"), "tipo": tipo,
             **campi}
        with self._lock:
            self.memoria.append(r)
            del self.memoria[:-2000]
        if self.cartella is None:
            return
        try:
            with self._lock:
                oggi = datetime.date.today()
                if self._pulito != oggi:
                    self.cartella.mkdir(parents=True, exist_ok=True)
                    self._pota(oggi)
                with open(self.cartella / f"{PREFISSO}{oggi.isoformat()}.jsonl", "a",
                          encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        except OSError as e:
            self.errori += 1
            if self.errori == 1 or self.errori % 100 == 0:
                print(f"   [STANZA] misura non scritta ({type(e).__name__}: {e})", flush=True)

    def _pota(self, oggi):
        self._pulito = oggi
        limite = oggi - datetime.timedelta(days=self.giorni)
        for f in self.cartella.glob(f"{PREFISSO}*.jsonl"):
            try:
                if datetime.date.fromisoformat(f.stem[len(PREFISSO):]) < limite:
                    f.unlink(missing_ok=True)
            except ValueError:
                continue


def leggi(cartella: str | None, giorni: int | None = None) -> list[dict]:
    if not cartella or not Path(cartella).is_dir():
        return []
    files = sorted(Path(cartella).glob(f"{PREFISSO}*.jsonl"))
    if giorni is not None:
        files = files[-giorni:]
    out = []
    for f in files:
        for riga in f.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(riga))
            except ValueError:
                continue
    return out


def _p(valori: list[float], q: float) -> float | None:
    if not valori:
        return None
    v = sorted(valori)
    return round(v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))], 3)


def riassunto(righe: list[dict], turni: list[dict] | None = None) -> dict:
    """Per giorno e satellite, più la copertura e i tempi dei turni con e senza la stanza."""
    giorni: dict = {}
    cerca = {"chiamate": 0, "attese": 0, "esiti": {}, "_ms": []}
    anticipo = {"ricerche": 0, "trovate": 0, "_car": []}
    conoscenti: dict = {}
    lenta = {"riviste": 0, "esiti": {}, "cambiate": 0, "attribuzioni": 0, "_stt": [],
             "_attese": [], "stt_tot_s": 0.0, "cam_tot_s": 0.0, "riassunti": 0,
             "riassunti_guasti": 0, "_riass_ms": [], "banco_salvati": 0, "banco_saltati": 0,
             "senza_ritrascrizione": 0}
    for r in righe:
        if r.get("tipo") == "lenta":
            e = str(r.get("esito") or "?")
            lenta["esiti"][e] = lenta["esiti"].get(e, 0) + 1
            if e in ("scaduto", "dimenticato", "errore"):
                continue
            lenta["riviste"] += 1
            lenta["senza_ritrascrizione"] += 1 if r.get("ritrascritto") is False else 0
            lenta["cambiate"] += 1 if r.get("testo_cambiato") else 0
            lenta["attribuzioni"] += 1 if r.get("attribuzione") else 0
            if r.get("stt_s") is not None:
                lenta["_stt"].append(float(r["stt_s"]))
                lenta["stt_tot_s"] += float(r["stt_s"])
            lenta["cam_tot_s"] += float(r.get("cam_ms") or 0) / 1000
            if r.get("attesa_s") is not None:
                lenta["_attese"].append(float(r["attesa_s"]))
            continue
        if r.get("tipo") == "lenta_riassunto":
            if r.get("esito") == "fatto":
                lenta["riassunti"] += 1
                lenta["_riass_ms"].append(float(r.get("ms") or 0))
            else:
                lenta["riassunti_guasti"] += 1
            continue
        if r.get("tipo") == "banco":
            lenta["banco_salvati" if r.get("salvato") else "banco_saltati"] += 1
            continue
        if r.get("tipo") == "conoscenti":
            e = str(r.get("evento") or "?")
            conoscenti[e] = conoscenti.get(e, 0) + 1
            if e == "proposta" and (r.get("omonimo_famiglia") or r.get("omonimo_conoscente")):
                conoscenti["proposte_omonimi"] = conoscenti.get("proposte_omonimi", 0) + 1
            continue
        if r.get("tipo") == "anticipo":
            anticipo["ricerche"] += 1
            if r.get("esito") == "trovato":
                anticipo["trovate"] += 1
                anticipo["_car"].append(float(r.get("caratteri") or 0))
            continue
        if r.get("tipo") == "cerca":
            # La ricerca (passo 4) non è di un satellite: conti di tutto il periodo
            cerca["chiamate"] += 1
            cerca["attese"] += 1 if r.get("attesa") else 0
            e = str(r.get("esito") or "?")
            cerca["esiti"][e] = cerca["esiti"].get(e, 0) + 1
            if r.get("ms") is not None:
                cerca["_ms"].append(float(r["ms"]))
            continue
        g = giorni.setdefault(str(r.get("t", ""))[:10], {"satelliti": {}, "presenze": 0,
                                                        "cambi_stanza": 0, "cambi_10min": 0,
                                                        "pause": {}, "dimentica": 0})
        tipo = r.get("tipo")
        if tipo in ("segmento", "buttato"):
            s = g["satelliti"].setdefault(str(r.get("sat") or "?"), {
                "canale": r.get("canale"), "segmenti": 0, "voce_s": 0.0, "byte": 0,
                "righe": 0, "legati": 0, "recuperati": 0, "scartate": {}, "buttati": {},
                "_ritardi": [], "chiusure": {}, "durante": {"segmenti": 0, "righe": 0, "eco": 0, "parole": 0,
                                            "tolte": 0, "recuperate": 0, "residua": 0,
                                            "detto": 0}})
            if tipo == "buttato":
                m = str(r.get("motivo") or "?")
                s["buttati"][m] = s["buttati"].get(m, 0) + 1
                continue
            s["segmenti"] += 1
            if r.get("chiusura"):
                ch = str(r["chiusura"])
                s["chiusure"][ch] = s["chiusure"].get(ch, 0) + 1
            s["voce_s"] += float(r.get("voce_s") or 0)
            s["byte"] += int(r.get("byte") or 0)
            esito = r.get("esito")
            if esito == "riga":
                s["righe"] += 1
            elif esito == "legato":
                s["legati"] += 1
            else:
                m = str(r.get("motivo") or "?")
                s["scartate"][m] = s["scartate"].get(m, 0) + 1
            if r.get("recupero"):
                s["recuperati"] += 1
            if r.get("durante"):
                d = s["durante"]
                d["segmenti"] += 1
                d["detto"] += int(r.get("detto_nuove") or 0)
                d["parole"] += int(r.get("parole") or 0)
                d["tolte"] += int(r.get("eco_tolte") or 0)
                d["residua"] += int(r.get("residua") or 0)
                if esito == "riga":
                    d["righe"] += 1
                    d["recuperate"] += max(0, int(r.get("parole") or 0)
                                           - int(r.get("eco_tolte") or 0))
                elif r.get("motivo") == "eco":
                    d["eco"] += 1
            if r.get("ritardo_s") is not None and esito != "legato":
                s["_ritardi"].append(float(r["ritardo_s"]))
        elif tipo == "presenza":
            g["presenze"] += 1
        elif tipo == "cambio_stanza":
            g["cambi_stanza"] += 1
            if float(r.get("dopo_s") or 0) <= CAMBIO_ENTRO_S:
                g["cambi_10min"] += 1
        elif tipo == "pausa":
            m = str(r.get("motivo") or "?")
            g["pause"][m] = g["pause"].get(m, 0) + 1
        elif tipo == "dimentica":
            g["dimentica"] += 1
    for g in giorni.values():
        for s in g["satelliti"].values():
            rit = s.pop("_ritardi")
            s["ore_parlato"] = round(s["voce_s"] / 3600, 3)
            s["voce_s"] = round(s["voce_s"], 1)
            s["ritardo_p50_s"], s["ritardo_p90_s"] = _p(rit, 0.5), _p(rit, 0.9)
            s["mb"] = round(s["byte"] / 2 ** 20, 2)
            s["mb_ora"] = round(s["mb"] / (s["voce_s"] / 3600), 1) if s["voce_s"] > 60 else None
            d = s["durante"]
            d["residua_100"] = (round(100 * d["residua"] / d["detto"], 2) if d["detto"]
                                else None)
    cop = {"turni": 0, "dette": 0, "pronte": 0, "complete": 0, "oltre": 0, "_rec": [],
           "col_blocco": 0, "nel_contesto": 0, "scartate": 0, "tutte": 0, "_attese": []}
    tempi = {k: {"stt": [], "prima": [], "riletti": []}
             for k in ("con", "senza", "blocco", "senza_blocco")}
    blocco = {"turni": 0, "vuoti": 0, "tagliati": 0, "mancano": 0, "_righe": [], "_car": []}
    # Le righe nella storia in sola aggiunta (14/10 sera)
    storia = {"turni": 0, "potature": 0, "_nuove": [], "_nuove_car": [], "_car": [],
              # Il pezzo in attesa (14/10 notte): turni che l'hanno trovato già in cache
              "attesa_turni": 0, "attesa_righe": 0}
    turni_stanza = 0
    for t in turni or ():
        st = t.get("stanza") if isinstance(t.get("stanza"), dict) else None
        turni_stanza += st is not None
        k = "con" if st is not None else "senza"
        ctx = (st or {}).get("contesto")
        # Con e senza blocco (passo 2): fra i turni con la stanza accesa
        kb = (("blocco" if int(ctx.get("righe") or 0) > 0 else "senza_blocco")
              if isinstance(ctx, dict) else None)
        riletti = (t.get("cache") or {}).get("riletti") if isinstance(t.get("cache"),
                                                                       dict) else None
        for chiave in (k, kb):
            if chiave is None:
                continue
            if t.get("stt_s") is not None and t.get("durata_s"):
                tempi[chiave]["stt"].append(float(t["stt_s"]))
            if t.get("prima_frase_s") is not None:
                tempi[chiave]["prima"].append(float(t["prima_frase_s"]))
            if isinstance(riletti, (int, float)):
                tempi[chiave]["riletti"].append(float(riletti))
        if isinstance(ctx, dict):
            if int(ctx.get("righe") or 0) > 0:
                blocco["turni"] += 1
                blocco["_righe"].append(float(ctx["righe"]))
                blocco["_car"].append(float(ctx.get("caratteri") or 0))
                blocco["tagliati"] += 1 if ctx.get("tagliate") else 0
                blocco["mancano"] += 1 if ctx.get("mancano") else 0
            else:
                blocco["vuoti"] += 1
        sto = (st or {}).get("storia")
        if isinstance(sto, dict):
            storia["turni"] += 1
            storia["potature"] += 1 if sto.get("potati") else 0
            storia["_nuove"].append(float(sto.get("nuove") or 0))
            storia["_nuove_car"].append(float(sto.get("nuove_caratteri") or 0))
            storia["_car"].append(float(sto.get("caratteri") or 0))
            if sto.get("attesa"):
                storia["attesa_turni"] += 1
                storia["attesa_righe"] += int(sto.get("attesa") or 0)
        c = (st or {}).get("copertura")
        if isinstance(c, dict):
            cop["turni"] += 1
            cop["dette"] += int(c.get("dette") or 0)
            cop["pronte"] += int(c.get("pronte") or 0)
            if c.get("dette") == c.get("pronte"):
                cop["complete"] += 1
            if c.get("oltre"):
                cop["oltre"] += 1
            if c.get("recupero_ms") is not None:
                cop["_rec"].append(float(c["recupero_ms"]))
            if c.get("nel_contesto") is not None:
                # La copertura del passo 2: righe dette prima della domanda finite nel blocco
                cop["col_blocco"] += 1
                cop["nel_contesto"] += int(c.get("nel_contesto") or 0)
                cop["scartate"] += int(c.get("scartate") or 0)
                if int(c.get("nel_contesto") or 0) + int(c.get("scartate") or 0) >= int(
                        c.get("dette") or 0):
                    cop["tutte"] += 1
                cop["_attese"].append(float(c.get("attesa_ms") or 0))
    rec = cop.pop("_rec")
    attese = cop.pop("_attese")
    cop["recupero_p50_ms"], cop["recupero_p90_ms"] = _p(rec, 0.5), _p(rec, 0.9)
    cop["attesa_p50_ms"], cop["attesa_p90_ms"] = _p(attese, 0.5), _p(attese, 0.9)
    ms = cerca.pop("_ms")
    cerca["ms_p50"], cerca["ms_p90"] = _p(ms, 0.5), _p(ms, 0.9)
    cerca["turni_stanza"] = turni_stanza
    car_a = anticipo.pop("_car")
    anticipo["caratteri_p50"] = _p(car_a, 0.5)
    cerca["anticipo"] = anticipo
    # La quota del § 6: turni con la frase d'attesa della ricerca sui turni interpellati con la
    # stanza accesa (gli stessi giorni del registro dei turni)
    cerca["quota_attesa"] = (round(cerca["attese"] / turni_stanza, 3) if turni_stanza
                             else None)
    righe_b, car_b = blocco.pop("_righe"), blocco.pop("_car")
    nuove_s, nuove_car_s, car_s = (storia.pop("_nuove"), storia.pop("_nuove_car"),
                                   storia.pop("_car"))
    storia["nuove_p50"], storia["nuove_caratteri_p50"] = _p(nuove_s, 0.5), _p(nuove_car_s, 0.5)
    storia["caratteri_p50"], storia["caratteri_p90"] = _p(car_s, 0.5), _p(car_s, 0.9)
    blocco["storia"] = storia
    blocco["righe_p50"], blocco["caratteri_p50"] = _p(righe_b, 0.5), _p(car_b, 0.5)
    blocco["caratteri_p90"] = _p(car_b, 0.9)
    st_l, att_l, rm_l = lenta.pop("_stt"), lenta.pop("_attese"), lenta.pop("_riass_ms")
    lenta["stt_p50_s"], lenta["stt_p90_s"] = _p(st_l, 0.5), _p(st_l, 0.9)
    lenta["attesa_p50_s"], lenta["attesa_p90_s"] = _p(att_l, 0.5), _p(att_l, 0.9)
    lenta["riassunto_p50_ms"] = _p(rm_l, 0.5)
    lenta["stt_tot_s"] = round(lenta["stt_tot_s"], 1)
    lenta["cam_tot_s"] = round(lenta["cam_tot_s"], 1)
    return {"giorni": giorni, "copertura": cop, "blocco": blocco, "cerca": cerca,
            "conoscenti": conoscenti, "lenta": lenta,
            "tempi": {k: {"turni": len(v["prima"]) or len(v["stt"]),
                          "stt_p50_s": _p(v["stt"], 0.5),
                          "stt_p90_s": _p(v["stt"], 0.9), "prima_p50_s": _p(v["prima"], 0.5),
                          "prima_p90_s": _p(v["prima"], 0.9),
                          "riletti_p50": _p(v["riletti"], 0.5)} for k, v in tempi.items()}}


def testo(r: dict) -> str:
    out = ["Stanza (conversazione di stanza: passo 1 in ombra, passo 2 con stanza_contesto, "
           "passo 3 con stanza_lenta, passo 4 con stanza_cerca, passo 5 con stanza_durante_voce)"]
    if r.get("tenuta"):
        # La tenuta su disco (14/10, stanza/tenuta.py): solo numeri, mai parole né nomi
        from .tenuta import testo_stato
        out.append(testo_stato(r["tenuta"]))
    if r.get("banco"):
        from .banco import testo_stato as testo_banco
        out.append(testo_banco(r["banco"]))
    kc = r.get("conoscenti") or {}
    if kc or r.get("conoscenti_salvati") is not None:
        out.append(testo_conoscenti(kc, r.get("conoscenti_salvati")))
    le = r.get("lenta") or {}
    if le.get("esiti") or le.get("riassunti") or le.get("riassunti_guasti"):
        out.append(testo_lenta(le))
    if not r.get("giorni") and not r["copertura"]["turni"] and not (
            r.get("cerca") or {}).get("chiamate") and not (
            (r.get("cerca") or {}).get("anticipo") or {}).get("ricerche") and not (
            (r.get("blocco") or {}).get("storia") or {}).get("turni"):
        out.append("  nessuna misura (stanza spenta, o mai partita)")
        return "\n".join(out)
    for giorno in sorted(r.get("giorni", {})):
        g = r["giorni"][giorno]
        out.append(f"  {giorno}: presenze chiuse {g['presenze']}, cambi di stanza "
                   f"{g['cambi_stanza']} (entro 10 min {g['cambi_10min']})"
                   + (f", pause {g['pause']}" if g["pause"] else "")
                   + (f", dimentica {g['dimentica']}" if g["dimentica"] else ""))
        for nome, s in sorted(g["satelliti"].items()):
            avviso = (" ⚠ oltre 10 s" if (s["ritardo_p90_s"] or 0) > RITARDO_P90_OBIETTIVO_S
                      else "")
            out.append(
                f"    {nome} ({s['canale'] or '?'}): parlato {s['ore_parlato']:.2f} h in "
                f"{s['segmenti']} segmenti, righe {s['righe']}, legati ai turni {s['legati']}, "
                f"recuperati {s['recuperati']}; coda p50 {s['ritardo_p50_s']} s, p90 "
                f"{s['ritardo_p90_s']} s{avviso}; banda {s['mb']} MB"
                + (f" ({s['mb_ora']} MB/h di parlato)" if s["mb_ora"] else ""))
            if s["scartate"] or s["buttati"]:
                out.append(f"      scartate {s['scartate'] or '{}'}, buttate dal satellite "
                           f"{s['buttati'] or '{}'}")
            ch = s.get("chiusure") or {}
            if ch.get("pausa_breve") or ch.get("lunga"):
                out.append(f"      chiusure: silenzio {ch.get('silenzio', 0)}, taglio morbido "
                           f"alla pausa breve {ch.get('pausa_breve', 0)}, tetto duro "
                           f"{ch.get('lunga', 0)}")
            d = s.get("durante") or {}
            if d.get("segmenti"):
                res = d.get("residua_100")
                avviso = (" ⚠ oltre 2" if res is not None and res >= ECO_RESIDUA_OBIETTIVO
                          else "")
                out.append(
                    f"      durante la voce (passo 5): {d['segmenti']} segmenti, righe tenute "
                    f"{d['righe']} (parole recuperate {d['recuperate']}), scartate per eco "
                    f"{d['eco']}, parole di Calliope tolte {d['tolte']}; eco residua stimata "
                    + (f"{res} ogni 100 parole dette ({d['residua']} su {d['detto']}, "
                       f"obiettivo < 2){avviso}" if res is not None else "non misurata"))
    c = r["copertura"]
    if c["turni"]:
        out.append(f"  Copertura all'interpellazione: {c['turni']} turni, {c['pronte']}/"
                   f"{c['dette']} righe già trascritte alla domanda, complete in "
                   f"{c['complete']} turni; recupero p50 {c['recupero_p50_ms']} ms, p90 "
                   f"{c['recupero_p90_ms']} ms; oltre 1,5 s: {c['oltre']}")
    if c.get("col_blocco"):
        out.append(f"  Copertura nel contesto (passo 2): {c['nel_contesto']}/{c['dette']} righe "
                   f"dette prima della domanda nel blocco (più {c['scartate']} senza testo), "
                   f"tutte in {c['tutte']}/{c['col_blocco']} turni; recupero aspettato p50 "
                   f"{c['attesa_p50_ms']} ms, p90 {c['attesa_p90_ms']} ms")
    b = r.get("blocco") or {}
    if b.get("turni") or b.get("vuoti"):
        out.append(f"  Blocco della stanza nei dati del turno: {b['turni']} turni (senza righe "
                   f"{b['vuoti']}), righe p50 {b['righe_p50']}, caratteri p50 "
                   f"{b['caratteri_p50']} (p90 {b['caratteri_p90']}); accorciato dal tetto in "
                   f"{b['tagliati']}, con righe non ancora trascritte in {b['mancano']}")
    sto = b.get("storia") or {}
    if sto.get("turni"):
        out.append(f"  Righe della stanza nella storia (in sola aggiunta): {sto['turni']} turni, "
                   f"nuove per turno p50 {sto['nuove_p50']} righe ({sto['nuove_caratteri_p50']} "
                   f"caratteri), davanti al modello p50 {sto['caratteri_p50']} caratteri (p90 "
                   f"{sto['caratteri_p90']}), potature {sto['potature']}"
                   + (f"; righe già in cache (pezzo in attesa) in {sto['attesa_turni']} turni, "
                      f"{sto['attesa_righe']} righe" if sto.get("attesa_turni") else ""))
    k = r.get("cerca") or {}
    if k.get("chiamate"):
        quota = k.get("quota_attesa")
        avvisi = []
        if quota is not None and quota >= ATTESA_QUOTA_OBIETTIVO:
            avvisi.append("frase d'attesa oltre il 10 %: il blocco caldo è troppo corto?")
        if (k.get("ms_p90") or 0) > CERCA_P90_OBIETTIVO_MS:
            avvisi.append("tool oltre 3 s al p90")
        out.append(f"  stanza_cerca (passo 4): {k['chiamate']} ricerche, esiti {k['esiti']}; "
                   f"tempo p50 {k['ms_p50']} ms, p90 {k['ms_p90']} ms; frase d'attesa "
                   f"{k['attese']} volte"
                   + (f", {quota * 100:.1f} % dei {k['turni_stanza']} turni in stanza "
                      "(obiettivo < 10 %)" if quota is not None else "")
                   + "".join(f" ⚠ {a}" for a in avvisi))
    an = k.get("anticipo") or {}
    if an.get("ricerche"):
        out.append(f"  Ricerca anticipata: {an['ricerche']} turni, righe aggiunte in "
                   f"{an['trovate']} (caratteri p50 {an['caratteri_p50']})")
    t = r["tempi"]
    if t["con"]["turni"]:
        out.append(f"  Turni con la stanza: stt p50 {t['con']['stt_p50_s']} s (senza "
                   f"{t['senza']['stt_p50_s']} s), prima frase p50 {t['con']['prima_p50_s']} s "
                   f"(senza {t['senza']['prima_p50_s']} s)")
    if t.get("blocco", {}).get("turni"):
        tb, ts = t["blocco"], t["senza_blocco"]
        out.append(f"  Con il blocco: prima frase p50 {tb['prima_p50_s']} s (senza blocco "
                   f"{ts['prima_p50_s']} s), token riletti p50 {tb['riletti_p50']} (senza "
                   f"{ts['riletti_p50']}); obiettivo +0,1 s al più")
    return "\n".join(out)


def testo_lenta(le: dict) -> str:
    """La riga della corsia lenta (passo 3): solo numeri."""
    es = le.get("esiti") or {}
    g = lambda e: int(es.get(e, 0))  # noqa: E731
    riv = int(le.get("riviste") or 0)
    quota = f" ({round(100 * le['cambiate'] / riv)} %)" if riv else ""
    return (f"  Corsia lenta (passo 3): {riv} segmenti rivisti, testo cambiato in "
            f"{le['cambiate']}{quota}, chi parla corretto in {le['attribuzioni']} (divisi in due "
            f"voci {g('divisa')}, più voci {g('piu_voci')}), uguali {g('uguale')}; TV "
            f"{g('tv')}, allucinazioni {g('allucinazione')}, ritrascrizione vuota tenuta "
            f"{g('v2_vuota')}"
            + (f", senza ritrascrizione {le['senza_ritrascrizione']}"
               if le.get("senza_ritrascrizione") else "")
            + f"; audio uscito dalla RAM prima del passo {g('scaduto')}; Whisper "
            f"{le['stt_tot_s']} s in tutto (p50 {le['stt_p50_s']} s a segmento), CAM++ "
            f"{le['cam_tot_s']} s; dalla fine del segmento p50 {le['attesa_p50_s']} s, p90 "
            f"{le['attesa_p90_s']} s; riassunti {le['riassunti']} (guasti "
            f"{le['riassunti_guasti']}, p50 {le['riassunto_p50_ms']} ms)"
            + (f"; banco: salvati {le['banco_salvati']}, saltati {le['banco_saltati']}"
               if le.get("banco_salvati") or le.get("banco_saltati") else ""))


def testo_conoscenti(k: dict, salvati: int | None = None) -> str:
    """La riga dei conoscenti (14/10, decisione 0030): solo conteggi."""
    g = lambda e: int(k.get(e, 0))  # noqa: E731
    proposte = g("proposta")
    risposte = g("conferma") + g("rifiuto")
    quota = f", confermate {round(100 * g('conferma') / risposte)} %" if risposte else ""
    return (f"  Conoscenti: {'?' if salvati is None else salvati} salvati; voci sconosciute "
            f"nuove {g('gruppo_nuovo')}, proposte {proposte} (con omonimi "
            f"{g('proposte_omonimi')}, arrivate a uno schermo {g('mandata')}), conferme "
            f"{g('conferma')}, rifiuti {g('rifiuto')}{quota}; indizi discordi {g('discordi')}, "
            f"voci di bambino {g('minore')}; dimenticati {g('dimenticato')}, scaduti "
            f"{g('scaduto')}, promossi {g('promosso')}, tornati conoscenti {g('declassato')}")
