"""Le impronte della voce per satellite misurate sulle registrazioni vere (15/10/2026,
calliope/impronte_satellite.py; docs/aree/stt-tts.md, «Impronte della voce per satellite»).

NON fa parte del runner. Si lancia **sulla DGX**, dalla cartella dei dati di Calliope:

    V=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)
    cd ~/calliope && $V/.venv/bin/python $V/prove/manuali/misura_impronte_satellite.py

Rigioca **in ordine di tempo**:

- la voce conservata degli adulti (decisione 0028 T1, calliope/conserva.py:
  `<turn_log_dir>/voce/<id>/<giorno>/<ora>.wav`), con chi parlava, il satellite e il canale dal
  registro dei turni (`voce.id`, `ascolto.satellite`, `ascolto.canale`), conoscenti compresi;
- l'audio del banco della stanza (calliope/stanza/banco.py, `<turn_log_dir>/stanza_banco/`: voci
  di casa riconosciute, minori compresi, finché vale l'eccezione), solo i segmenti con **una**
  persona; il canale del satellite dal registro dei turni (se non c'è: «satellite»).

Per ogni frase calcola l'impronta CAM++ (la stessa di Calliope) e la decisione **senza** e
**con** le impronte per satellite, imparate frase dopo frase come farebbe Calliope (solo dalle
frasi sicure, `impronte_satellite.sicura`, sulla persona **decisa**, non su quella vera: così un
errore che insegna l'impronta sbagliata si vede). Due regimi: «ombra» (si impara dalla decisione
di oggi) e «attivo» (dalla decisione con le impronte). La decisione è quella della voce in
`ciclo._confronta_voce` semplificata: soglia e margine (`speaker_id_margine`), il profilo più
protetto (`minori.piu_protetto` senza la frase breve) e chi amministra con un minore vicino
(`minori_margine_amministra`: vale «chi amministra, al più familiare»). Non ci sono la zona
grigia (vuole la conversazione), la continuità e la compagnia del momento (la frase con
`voce.compagnia` nel registro non insegna). Le frasi sotto `speaker_min_voice_s` non le decide la
voce: contate a parte.

Stampa **solo numeri**, per persona («chi amministra 1», «adulto 1», «minore 1», «conoscente 1»)
e satellite («satellite 1 (telefono)»): frasi, rifiutate senza e con, rifiutate → riconosciute,
scambi fra persone nei due versi (soprattutto minore → chi amministra), margini sul secondo
(mediana e 5° percentile). Niente nomi, niente parole, niente file scritti: le impronte imparate
stanno in una copia in memoria (speakers.json e i conoscenti si leggono soltanto).

Opzioni (valori di serie dalla configurazione):
    --giorni N            solo gli ultimi N giorni del registro dei turni
    --max N               al più N frasi
    --senza-banco         solo la voce conservata
    --senza-conservati    solo il banco della stanza
    --seme N              speaker_impronte_seme_frasi
    --margine M           speaker_impronte_margine
    --min-voce S          speaker_impronte_min_voce_s
    --deriva-arr X        speaker_impronte_deriva_arruolamento
    --deriva-seme Y       speaker_impronte_deriva_seme
    --alpha A             speaker_impronte_alpha
    --json                il risultato in JSON (stessi numeri)
"""
import datetime
import json
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RADICE))
SALTA = 77


def opzioni(argv):
    o, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            k = a[2:].replace("-", "_")
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                o[k] = argv[i + 1]
                i += 2
            else:
                o[k] = True
                i += 1
        else:
            i += 1
    return o


def _epoch(iso) -> float | None:
    try:
        return datetime.datetime.fromisoformat(str(iso)[:26]).timestamp()
    except ValueError:
        return None


def persone(cfg, reg):
    """{id: persona} dalla famiglia (speakers.json) e dai conoscenti, in sola lettura."""
    import numpy as np
    from calliope import minori
    out = {}
    for p in reg.users.values():
        if p.voiceprint is None:
            continue
        ini = p.initial_voiceprint if p.initial_voiceprint is not None else p.voiceprint
        tipo = ("amministra" if p.admin else "minore" if minori.e_minore(p) else "adulto")
        out[str(p.id)] = {"id": str(p.id), "tipo": tipo, "base": np.asarray(p.voiceprint),
                          "ini": np.asarray(ini), "imp": {}}
    try:
        from calliope.stanza.conoscenti import Conoscente, percorso
        f = percorso(cfg)
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            for x in d.get("conoscenti") or ():
                c = Conoscente.da_dict(x)
                if c.impronta is not None and str(c.id) not in out:
                    out[str(c.id)] = {"id": str(c.id), "tipo": "conoscente",
                                      "base": c.impronta, "ini": c.impronta, "imp": {}}
    except Exception as e:  # noqa: BLE001
        print(f"(conoscenti non letti: {type(e).__name__})")
    return out


def frasi_conservate(cfg, turni, voce_dir):
    out = []
    for r in turni:
        v = r.get("voce") if isinstance(r.get("voce"), dict) else {}
        if not r.get("voce_file") or not v.get("id"):
            continue
        a = r.get("ascolto") if isinstance(r.get("ascolto"), dict) else {}
        out.append({"t": _epoch(r.get("inizio")), "chi": str(v["id"]),
                    "sat": a.get("satellite") or ("locale" if a.get("canale") == "locale"
                                                  else a.get("canale") or "locale"),
                    "canale": a.get("canale") or "locale",
                    "voce_s": float(v.get("voce_s") or 0.0),
                    "compagnia": bool(v.get("compagnia")),
                    "file": voce_dir / str(r["voce_file"]), "fonte": "conservata"})
    return [x for x in out if x["t"] is not None]


def frasi_banco(cfg, canali: dict):
    from calliope.stanza import banco
    d = banco.cartella(cfg)
    out, piu = [], 0
    if d is None or not d.exists():
        return out, piu
    for j in sorted(d.rglob("*.json")):
        if j.name == banco.ACCESO:
            continue
        try:
            m = json.loads(j.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pp = [str(x) for x in (m.get("persone") or []) if x]
        if len(pp) != 1:
            piu += 1
            continue
        nome = m.get("satellite") or str(m.get("sat") or "")
        out.append({"t": float(m.get("inizio") or 0.0), "chi": pp[0], "sat": nome,
                    "canale": canali.get(nome, "satellite"),
                    "voce_s": float(m.get("voce_s") or 0.0), "compagnia": False,
                    "file": j.with_suffix(".wav"), "fonte": "banco"})
    return out, piu


def decidi(cfg, cl, tipi):
    """La decisione della voce semplificata: (chi, come) con come «voce», «amministra_vicino»,
    «protetto» o None (ospite)."""
    thr = float(cfg.speaker_id_threshold)
    grigia = thr - float(cfg.speaker_id_session_margin)
    mar = float(cfg.speaker_id_margine)
    amb = float(getattr(cfg, "minori_margine_ambiguo", 0.05))
    vic = float(getattr(cfg, "minori_margine_amministra", 0.12))
    if not cl:
        return None, None
    best, s1 = cl[0]
    s2 = cl[1][1] if len(cl) > 1 else None
    nome = best if s1 >= thr and (s2 is None or s1 - s2 >= mar) else None
    minori = [(n, s) for n, s in cl if tipi.get(n) == "minore"]
    if nome is not None and tipi.get(nome) == "minore":
        return nome, "voce"
    if nome is not None:
        vicini = [(n, s) for n, s in minori if s >= grigia and s1 - s < amb]
    else:
        vicini = [(n, s) for n, s in minori if s >= grigia]
    if vicini:
        return max(vicini, key=lambda x: x[1])[0], "protetto"
    if nome is not None and tipi.get(nome) == "amministra":
        if any(s1 - s < vic for n, s in minori):
            return nome, "amministra_vicino"
    return nome, ("voce" if nome is not None else None)


def classifica(emb, pp, chiavi):
    import numpy as np
    from calliope import impronte_satellite as IS
    out = []
    for pid, p in pp.items():
        if chiavi:
            s = IS.punteggio(emb, p["base"], p["imp"], chiavi)[0]
        else:
            s = float(np.dot(emb, p["base"]))
        out.append((pid, s))
    return sorted(out, key=lambda x: -x[1])


def _pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))], 3)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    o = opzioni(sys.argv[1:])
    import copy

    import numpy as np
    from calliope import impronte_satellite as IS
    from calliope.config import load_config
    from calliope.conserva import CARTELLA_VOCE, leggi_wav
    from calliope.latenza import leggi
    from calliope.speaker_id import SpeakerRegistry

    cfg = load_config()
    for opz, campo, tipo in (("seme", "speaker_impronte_seme_frasi", int),
                             ("margine", "speaker_impronte_margine", float),
                             ("min_voce", "speaker_impronte_min_voce_s", float),
                             ("deriva_arr", "speaker_impronte_deriva_arruolamento", float),
                             ("deriva_seme", "speaker_impronte_deriva_seme", float),
                             ("alpha", "speaker_impronte_alpha", float)):
        if o.get(opz):
            setattr(cfg, campo, tipo(o[opz]))

    class SolaLettura(SpeakerRegistry):
        def save(self):                       # mai scrivere speakers.json
            pass

        def flush(self):
            pass

    reg = SolaLettura(cfg)
    if reg.illeggibile or not reg.users:
        print("Nessun profilo leggibile in speakers.json: niente da misurare.")
        return SALTA
    pp0 = persone(cfg, reg)
    tipi = {pid: p["tipo"] for pid, p in pp0.items()}
    cartella = Path(cfg.turn_log_dir or "")
    giorni = int(o["giorni"]) if o.get("giorni") else None
    turni = leggi(str(cartella), giorni)
    canali = {}
    for r in turni:
        a = r.get("ascolto") if isinstance(r.get("ascolto"), dict) else {}
        if a.get("satellite") and a.get("canale"):
            canali[a["satellite"]] = a["canale"]
    eventi = []
    if not o.get("senza_conservati"):
        eventi += frasi_conservate(cfg, turni, cartella / CARTELLA_VOCE)
    banco_piu = 0
    if not o.get("senza_banco"):
        b, banco_piu = frasi_banco(cfg, canali)
        eventi += b
    eventi = [e for e in eventi if e["chi"] in pp0 and e["file"].exists()]
    eventi.sort(key=lambda e: e["t"])
    if o.get("max"):
        eventi = eventi[:int(o["max"])]
    # Le frasi rifiutate vere (senza audio: la voce di un ospite non si conserva), per satellite
    rifiutate_vere: dict = {}
    for r in turni:
        v = r.get("voce") if isinstance(r.get("voce"), dict) else None
        if v and v.get("nome") is None and not v.get("conoscente") and v.get("punteggio"):
            a = r.get("ascolto") if isinstance(r.get("ascolto"), dict) else {}
            k = a.get("satellite") or a.get("canale") or "locale"
            rifiutate_vere[k] = rifiutate_vere.get(k, 0) + 1
    if not eventi:
        print("Nessuna frase con l'audio (voce conservata o banco della stanza): niente da fare.")
        return SALTA

    # Etichette senza nomi
    etich, cont = {}, {}
    ord_tipo = {"amministra": "chi amministra", "adulto": "adulto", "minore": "minore",
                "conoscente": "conoscente"}
    for pid in sorted(pp0, key=lambda x: (list(ord_tipo).index(tipi[x]), x)):
        n = cont[tipi[pid]] = cont.get(tipi[pid], 0) + 1
        etich[pid] = f"{ord_tipo[tipi[pid]]} {n}"
    sat_et = {}
    for e in eventi:
        if e["sat"] not in sat_et:
            sat_et[e["sat"]] = f"satellite {len(sat_et) + 1} ({e['canale']})"
    for k in list(rifiutate_vere):
        if k not in sat_et:
            sat_et[k] = f"satellite {len(sat_et) + 1} (solo nel registro)"

    print(f"{len(eventi)} frasi con l'audio ({sum(e['fonte'] == 'conservata' for e in eventi)} "
          f"conservate, {sum(e['fonte'] == 'banco' for e in eventi)} del banco; segmenti del "
          f"banco con più persone saltati: {banco_piu}); {len(pp0)} persone; calcolo le impronte…")
    embs, errori = [], 0
    for i, e in enumerate(eventi, 1):
        try:
            audio, sr = leggi_wav(e["file"])
            if sr != 16000:
                n = int(len(audio) * 16000 / sr)
                audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)),
                                  audio).astype("float32")
            embs.append(reg.embed(audio, 16000))
            if not e["voce_s"]:
                e["voce_s"] = len(audio) / 16000
        except Exception:  # noqa: BLE001
            embs.append(None)
            errori += 1
        if i % 200 == 0:
            print(f"  {i}/{len(eventi)}")

    risultati = {}
    min_s = float(cfg.speaker_min_voice_s)
    for regime in ("ombra", "attivo"):
        pp = copy.deepcopy(pp0)
        stat: dict = {}
        imparate = 0
        for e, emb in zip(eventi, embs):
            if emb is None:
                continue
            ch = IS.chiavi(e["sat"], e["canale"])
            k = (etich[e["chi"]], sat_et[e["sat"]])
            d = stat.setdefault(k, {"frasi": 0, "corte": 0, "rifiutate_senza": 0,
                                    "rifiutate_con": 0, "recuperate": 0, "perse": 0,
                                    "scambi_senza": 0, "scambi_con": 0,
                                    "minore_ad_amministra_senza": 0,
                                    "minore_ad_amministra_con": 0,
                                    "amministra_a_minore_senza": 0,
                                    "amministra_a_minore_con": 0,
                                    "amministra_vicino_senza": 0, "amministra_vicino_con": 0,
                                    "margini_senza": [], "margini_con": [], "dal_satellite": 0})
            cl_s = classifica(emb, pp, None)
            cl_c = classifica(emb, pp, ch)
            if e["voce_s"] < min_s:
                d["corte"] += 1
            else:
                d["frasi"] += 1
                for nome_v, cl in (("senza", cl_s), ("con", cl_c)):
                    chi, come = decidi(cfg, cl, tipi)
                    vero = e["chi"]
                    sv = dict(cl).get(vero, 0.0)
                    altri = [s for n, s in cl if n != vero]
                    d[f"margini_{nome_v}"].append(sv - (max(altri) if altri else 0.0))
                    if chi is None:
                        d[f"rifiutate_{nome_v}"] += 1
                    elif chi != vero:
                        d[f"scambi_{nome_v}"] += 1
                        if tipi[vero] == "minore" and tipi[chi] == "amministra":
                            d[f"minore_ad_amministra_{nome_v}"] += 1
                        if tipi[vero] == "amministra" and tipi[chi] == "minore":
                            d[f"amministra_a_minore_{nome_v}"] += 1
                    if come == "amministra_vicino":
                        d[f"amministra_vicino_{nome_v}"] += 1
                    if nome_v == "senza":
                        senza = chi
                    else:
                        if senza is None and chi == vero:
                            d["recuperate"] += 1
                        if senza == vero and chi is None:
                            d["perse"] += 1
                if IS.punteggio(emb, pp[e["chi"]]["base"], pp[e["chi"]]["imp"], ch)[1] != "base":
                    d["dal_satellite"] += 1
            # L'apprendimento, come Calliope: sulla persona decisa dal regime
            cl = cl_s if regime == "ombra" else cl_c
            chi, come = decidi(cfg, cl, tipi)
            s1 = cl[0][1] if cl else None
            s2 = cl[1][1] if len(cl) > 1 else None
            if (chi is not None and chi == cl[0][0] and come == "voce"
                    and IS.sicura(cfg, "voce", s1, s2, e["voce_s"], compagnia=e["compagnia"])):
                p = pp[chi]
                if IS.impara(p["imp"], emb, ch, p["ini"], cfg):
                    imparate += 1
                    if chi != e["chi"]:
                        d["insegnate_sbagliate"] = d.get("insegnate_sbagliate", 0) + 1
        risultati[regime] = {"per": stat, "imparate": imparate}

    out = {"frasi": len(eventi), "errori": errori, "banco_piu_persone": banco_piu,
           "parametri": {k: getattr(cfg, k) for k in (
               "speaker_id_threshold", "speaker_id_margine", "speaker_adapt_threshold",
               "speaker_impronte_seme_frasi", "speaker_impronte_margine",
               "speaker_impronte_min_voce_s", "speaker_impronte_alpha",
               "speaker_impronte_deriva_arruolamento", "speaker_impronte_deriva_seme",
               "minori_margine_ambiguo", "minori_margine_amministra")},
           "rifiutate_nel_registro": {sat_et[k]: n for k, n in rifiutate_vere.items()},
           "regimi": {}}
    for regime, r in risultati.items():
        righe = []
        for (pers, sat), d in sorted(r["per"].items()):
            ms, mc = d.pop("margini_senza"), d.pop("margini_con")
            d.update(margine_senza_mediana=_pct(ms, 0.5), margine_senza_p05=_pct(ms, 0.05),
                     margine_con_mediana=_pct(mc, 0.5), margine_con_p05=_pct(mc, 0.05))
            righe.append({"persona": pers, "satellite": sat, **d})
        out["regimi"][regime] = {"imparate": r["imparate"], "righe": righe}
    if o.get("json"):
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"\nParametri: {out['parametri']}")
    print(f"Frasi rifiutate nel registro dei turni (senza audio, solo contate): "
          f"{out['rifiutate_nel_registro']}")
    for regime, r in out["regimi"].items():
        print(f"\n── regime «{regime}» (frasi che hanno insegnato un'impronta: {r['imparate']}) ──")
        for x in r["righe"]:
            print(f"  {x['persona']} · {x['satellite']}: {x['frasi']} frasi (+{x['corte']} "
                  f"corte); rifiutate {x['rifiutate_senza']} → {x['rifiutate_con']} "
                  f"(riconosciute in più {x['recuperate']}, perse {x['perse']}); scambi "
                  f"{x['scambi_senza']} → {x['scambi_con']} (minore → chi amministra "
                  f"{x['minore_ad_amministra_senza']} → {x['minore_ad_amministra_con']}, chi "
                  f"amministra → minore {x['amministra_a_minore_senza']} → "
                  f"{x['amministra_a_minore_con']}); chi amministra col minore vicino "
                  f"{x['amministra_vicino_senza']} → {x['amministra_vicino_con']}; margine sul "
                  f"secondo mediana {x['margine_senza_mediana']} → {x['margine_con_mediana']}, "
                  f"p05 {x['margine_senza_p05']} → {x['margine_con_p05']}; punteggio dal "
                  f"satellite {x['dal_satellite']}"
                  + (f"; ATTENZIONE: impronte insegnate alla persona sbagliata "
                     f"{x['insegnate_sbagliate']}" if x.get("insegnate_sbagliate") else ""))
    print("\nNiente è stato scritto: speakers.json e i conoscenti sono stati solo letti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
