"""La modalità sviluppo, versione 2, con il modello vero della voce (Ollama locale,
`llm_model`), il docker FINTO, un servizio dei lavori finto e un agente finto per
sviluppo_chiedi (08/10/2026). Il giro di prova vero della DGX dell'08/10 (11:06–11:32),
riscritto con nomi di fantasia: la città che il geocoder finto non trova è «Pratofiorito
Maggiore».

Dario, con la voce:
 1. «Voglio un'estensione che mi dica il meteo di una città qualunque, non solo di Borgoverde e
    Valfiorita.» → sviluppo_apri, «Entriamo in modalità sviluppo…»;
 2. «Sì, va bene così.» → il lavoro parte;
    … il lavoro finisce (finto): «… è pronto: siamo al collaudo. Con cosa provo?»;
 3. «Prova con Bergamo.» → sviluppo_collauda;
 4. «Prova con Pratofiorito Maggiore.» → sviluppo_collauda, non va: «Lo faccio correggere?»;
 5. «Perché?» → sviluppo_chiedi (mai la voce che improvvisa);
 6. «Sì, fallo correggere.» → sviluppo_correggi (non il ritorno all'analisi);
 7. «Ok, chiuso a long.» (storpiato, l'agente al lavoro) → MAI chiuso;
    … la correzione finisce a sviluppo sospeso: si riapre al collaudo;
 8. «Prova con Pratofiorito Maggiore.» → sviluppo_collauda, senza «C'è di mezzo…»;
 9. «Va bene, andiamo avanti.» → revisione;
10. «Attivala.» → la frase di sfida; detta → attiva e sviluppo chiuso.

Si contano i passi giusti e le chiamate scritte come testo o con un nome che non c'è (il caso
«lavoris_stato»). Fallisce se lo sviluppo si chiude al passo 7 o se «Perché?» non va mai a
sviluppo_chiedi.

    python prove\\prova_sviluppo_v2_ollama.py      # 2 giri
    python prove\\prova_sviluppo_v2_ollama.py 1    # 1 giro
"""

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RADICE)
sys.path.insert(0, os.path.join(_RADICE, "prove"))

import prova_estensioni as P  # noqa: E402
import prova_sviluppo as S  # noqa: E402
import prova_sviluppo_ollama as SO  # noqa: E402
import prova_sviluppo_v2 as V  # noqa: E402
from calliope.brain import Brain  # noqa: E402

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""), flush=True)


def finisci(est, svc, codice):
    sv = svc.sviluppi.corrente("u1") or next(
        (s for s in reversed(svc.sviluppi.sviluppi) if s.stato != "chiusa"), None)
    lav = next((lv for lv in reversed(svc.lavori) if lv.id == getattr(sv, "lavoro", None)),
               None)
    if sv is None or lav is None:
        return None
    nome = lav.estensione or "meteo_ovunque"
    mv = P.valida(dict(S.M2, nome=nome))
    n = est.archivio.nuova_candidata(mv, {"estensione.py": codice.encode()}, "Dario",
                                     {"eseguiti": 6, "falliti": 0},
                                     {"rischi": [], "sintassi": []}, lav.id, True)
    lav.estensione = nome
    V.contesto_finto(lav)
    svc.sviluppi.conserva(lav)
    return svc.finisci(lav, "fatto", estensione={"nome": nome, "versione": n},
                       test={"eseguiti": 6, "falliti": 0},
                       messaggio="ho preparato l'estensione «Meteo per città». Vuoi approvarla?")


def sessione(giro, tmp, iso, conteggi: dict, tempi: list, sbagli: list):
    web = []
    cfg, reg, ctx, est, svc = SO.ambiente(tmp, iso, web)
    svc.cfg, svc.imp = cfg, V.SimpleNamespace(modello="agente-finto")
    svc.cliente = V.AgenteFinto({
        "voce": "Il geocoder che ho usato non trova i nomi di due parole: va corretto.",
        "dettagli": "In estensione.py la città si cerca in un elenco con i nomi di una parola.",
        "serve_correzione": True, "cosa_correggere": "cercare il nome intero"})
    svs = svc.sviluppi
    dario = SO.Voce("Dario", "amministra")
    b = Brain(cfg, reg, ctx)
    b.conv_owner = "u1"

    def passo(n, frase, giusto, descr):
        r, tools, s = SO.parla(b, dario, frase)
        tempi.append(s)
        sv = svs.corrente("u1")
        tutti = svs.sviluppi[-1] if svs.sviluppi else None
        ok = bool(giusto(r, tools, sv, tutti))
        c = conteggi.setdefault(f"{n:02d} {descr}", [0, 0])
        c[0] += ok
        c[1] += 1
        regole = list(b.last_rules or [])
        if "textcallguard" in regole or "tool_nome_corretto" in regole or re.search(
                r"\b[a-z]+_[a-z_]+\b", r):
            sbagli.append((n, frase, tools, regole, r[:120]))
        print(f"{'ok ' if ok else '-- '} [{giro}] {n}. «{frase[:50]}» → {', '.join(tools) or '—'} "
              f"[{getattr(sv, 'fase', '—')}/{getattr(tutti, 'stato', '—')}] {s:.1f}s {r[:160]!r}",
              flush=True)
        return r, tools, sv

    def annuncia(codice):
        item = finisci(est, svc, codice)
        if item is not None:
            b.record_announcement(item["messaggio"], pending=item.get("in_sospeso"),
                                  fonte="agente")
        return item

    passo(1, "Voglio un'estensione che mi dica il meteo di una città qualunque, non solo di "
             "Borgoverde e Valfiorita.",
          lambda r, t, sv, x: "sviluppo_apri" in t and sv is not None and "Entriamo" in r,
          "richiesta → apertura detta")
    passo(2, "Sì, va bene così.", lambda r, t, sv, x: sv is not None and sv.fase == "sviluppo",
          "sì → sviluppo")
    sv = svs.corrente("u1")
    if sv is not None and sv.fase == "analisi" and sv.proposto:
        passo(2, "Sì.", lambda r, t, sv, x: sv is not None and sv.fase == "sviluppo",
              "sì → sviluppo (proposta arrivata tardi)")
    if annuncia(V.CODICE_GEO) is None:
        print(f"   [{giro}] nessun lavoro dello sviluppo: il giro finisce", flush=True)
        return
    passo(3, "Prova con Bergamo.", lambda r, t, sv, x: "sviluppo_collauda" in t
          and "Bergamo" in r, "collaudo Bergamo")
    passo(4, f"Prova con {V.CITTA_FINTA}.", lambda r, t, sv, x: "sviluppo_collauda" in t
          and "correggere" in r, "collaudo che non va → «Lo faccio correggere?»")
    passo(5, "Perché?", lambda r, t, sv, x: "sviluppo_chiedi" in t and "due parole" in r,
          "«Perché?» → sviluppo_chiedi")
    passo(6, "Sì, fallo correggere.", lambda r, t, sv, x: "sviluppo_correggi" in t
          and sv is not None and sv.fase == "sviluppo" and sv.correzioni >= 1,
          "correzione (non l'analisi)")
    passo(7, "Ok, chiuso a long.", lambda r, t, sv, x: x is not None and x.stato != "chiusa",
          "storpiato: mai chiuso")
    item = annuncia(S.CODICE2)
    passo(8, f"Prova con {V.CITTA_FINTA}.", lambda r, t, sv, x: "sviluppo_collauda" in t
          and "C'è di mezzo" not in r and V.CITTA_FINTA.split()[0] in r,
          "dopo la correzione, collaudo senza «C'è di mezzo»")
    passo(9, "Va bene, andiamo avanti.",
          lambda r, t, sv, x: sv is not None and sv.fase == "revisione", "avanti → revisione")
    r, t, sv = passo(10, "Attivala.", lambda r, t, sv, x: dario.sfida is not None
                     and "ripeti" in r.lower(), "attivala → sfida")
    if dario.sfida is not None:
        passo(11, dario.sfida.testo.replace(",", ""),
              lambda r, t, sv, x: sv is None and x is not None and x.motivo == "attivata",
              "sfida → attiva, chiuso")
    return item


def main():
    tmp0 = Path(tempfile.mkdtemp(prefix="calliope-sviluppo2-ollama-"))
    os.environ["DOCKER_FINTO_DIR"] = str(tmp0 / "docker")
    os.environ["DOCKER_FINTO_IMMAGINI"] = P.IMMAGINE
    os.environ["DOCKER_FINTO_MODO"] = "ok"
    iso = P.Isolamento("docker", "docker finto", True, "", P.IMMAGINE, P.FINTO)
    conteggi: dict = {}
    tempi: list = []
    sbagli: list = []
    for giro in range(1, GIRI + 1):
        sessione(giro, tmp0 / f"g{giro}", iso, conteggi, tempi, sbagli)
    print("\nRiepilogo (riusciti / casi):")
    for chiave, (k, n) in sorted(conteggi.items()):
        print(f"  {chiave:55} {k}/{n}")
    if tempi:
        t = sorted(tempi)
        print(f"  prima frase: mediana {t[len(t) // 2]:.2f} s, massimo {t[-1]:.2f} s "
              f"({len(t)} turni)")
    print(f"  chiamate scritte come testo, nomi corretti o nomi di tool detti: {len(sbagli)}")
    for s in sbagli:
        print(f"    {s}")
    k7, n7 = conteggi.get("07 storpiato: mai chiuso", [0, 0])
    k5, n5 = conteggi.get("05 «Perché?» → sviluppo_chiedi", [0, 0])
    verifica("«Ok, chiuso a long» non chiude mai lo sviluppo", k7 == n7, f"{k7}/{n7}")
    verifica("«Perché?» va a sviluppo_chiedi almeno una volta", k5 >= 1, f"{k5}/{n5}")
    print(json.dumps({k: v for k, v in conteggi.items()}, ensure_ascii=False))
    print("\nTutto bene." if not errori else f"\n{errori} errori.")
    sys.exit(1 if errori else 0)


if __name__ == "__main__":
    main()
