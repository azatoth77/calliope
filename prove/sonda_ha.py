import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Sonda di Home Assistant: SOLO LETTURE, da lanciare a mano a casa (non è nel runner).

Usa la stessa configurazione di Calliope (calliope.yaml + calliope.locale.yaml, o CALLIOPE_CONFIG) e lo stesso
token (CALLIOPE_HA_TOKEN o segreti.yaml). Non comanda niente: i comandi di prova passano
solo dalla verifica a secco dell'agente (conversation/agent/homeassistant/debug), che
riconosce la frase senza eseguirla; a conversation/process vanno solo domande (ora,
stato), e solo dopo che la verifica a secco ha confermato che sono letture.

Stampa: certificato (nomi mascherati e impronta), versione di HA, agente integrato,
entità esposte per tipo e per stanza (solo conteggi e nomi delle stanze), quante sono
delicate (Calliope le leggerà soltanto), tempi di verifica ed esecuzione. Mai il token,
mai nomi di dispositivi o stati.

    .venv\\Scripts\\python prove\\sonda_ha.py
    .venv\\Scripts\\python prove\\sonda_ha.py --nome casa-mia.duckdns.org   # prova casa_tls_nome
    .venv\\Scripts\\python prove\\sonda_ha.py --impronta AB:CD:...          # prova casa_tls_impronta
"""

import argparse
import ipaddress
import socket
import ssl
import statistics
import time

from calliope.casa import diagnose, load_casa, read_token
from calliope.casa.homeassistant import (INTENTI_LETTURA, HomeAssistantBackend, cert_names,
                                         fingerprint)
from calliope.casa.regole import Regole
from calliope.config import load_config

LETTURE_SICURE = INTENTI_LETTURA | {"HassGetCurrentTime", "HassGetCurrentDate"}


def maschera(nome: str) -> str:
    """«casa-mia.duckdns.org» → «c******a.duckdns.org»: basta a riconoscerlo."""
    head, _, tail = nome.partition(".")
    if len(head) <= 2:
        return "*" * len(head) + ("." + tail if tail else "")
    return head[0] + "*" * (len(head) - 2) + head[-1] + ("." + tail if tail else "")


def _e_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def maschera_url(url: str | None) -> str:
    """casa_url senza l'indirizzo (04/10: la sonda lo stampava intero): «https://<IP privato>:8123»,
    «https://c******a.duckdns.org:8123». Schema e porta restano: servono a capire."""
    if not url:
        return "(manca)"
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url)
        host, porta = u.hostname or "", u.port
    except ValueError:
        return "(non valido)"
    if _e_ip(host):
        ip = ipaddress.ip_address(host)
        h = "<IP privato>" if ip.is_private else "<IP>"
    else:
        h = maschera(host) if host else "(senza host)"
    return f"{u.scheme}://{h}" + (f":{porta}" if porta else "")


def consiglio_tls(host: str, nomi: list[str], nome_tls: str | None = None) -> str | None:
    """Il consiglio sul certificato DuckDNS: casa_tls_nome serve solo se ci si collega a un
    IP (04/10: lo diceva anche con l'indirizzo che era già un nome) e se non c'è già."""
    if nome_tls or not _e_ip(host) or not any("duckdns" in n.lower() for n in nomi):
        return None
    return ("è il certificato DuckDNS e ti colleghi a un IP: in calliope.locale.yaml metti "
            "casa_tls_nome con il tuo nome DuckDNS")


def sonda_tls(host: str, port: int, nome: str | None):
    print("\n— Certificato (letto senza verificarlo)")
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        with socket.create_connection((host, port), 5) as raw:
            with ctx.wrap_socket(raw, server_hostname=nome or host) as s:
                der = s.getpeercert(binary_form=True) or b""
                proto = s.version()
    except OSError as e:
        print(f"  non raggiungibile: {type(e).__name__}: {e}")
        return
    names = cert_names(der)
    print(f"  protocollo {proto}")
    print(f"  intestato a: {', '.join(maschera(n) for n in names) or '(nomi non leggibili)'}")
    consiglio = consiglio_tls(host, names, nome)
    if consiglio:
        print(f"  → {consiglio}")
    print(f"  impronta SHA-256 (per casa_tls_impronta): {fingerprint(der)}")


def misura(be, frasi, ripetizioni=3):
    print("\n— Verifica a secco (non esegue niente)")
    for frase in frasi:
        tempi, res = [], None
        for _ in range(ripetizioni):
            t0 = time.perf_counter()
            dbg = be._richiesta({"type": "conversation/agent/homeassistant/debug",  # noqa: SLF001
                                 "sentences": [frase], "language": be.lingua})
            tempi.append(time.perf_counter() - t0)
            res = ((dbg or {}).get("results") or [None])[0]
        interp = be._interpreta(res)  # noqa: SLF001
        esito = (f"capita: {interp.intento}, {len(interp.bersagli)} dispositivi"
                 if interp.capito else "non capita")
        print(f"  «{frase}»: {esito}; {statistics.median(tempi) * 1000:.0f} ms "
              f"(massimo {max(tempi) * 1000:.0f})")
        yield frase, interp, tempi


def main() -> int:
    ap = argparse.ArgumentParser(description="Sonda di Home Assistant: solo letture")
    ap.add_argument("--url", help="al posto di casa_url")
    ap.add_argument("--nome", help="al posto di casa_tls_nome")
    ap.add_argument("--impronta", help="al posto di casa_tls_impronta")
    ap.add_argument("--insicuro", action="store_true", help="nessuna verifica del certificato")
    a = ap.parse_args()
    cfg = load_config()
    cfg.casa_url = a.url or cfg.casa_url
    cfg.casa_tls_nome = a.nome or cfg.casa_tls_nome
    cfg.casa_tls_impronta = a.impronta or cfg.casa_tls_impronta
    if a.insicuro:
        cfg.casa_tls_verifica = False
    cfg.casa_enabled = True

    print("— Configurazione")
    print(f"  casa_url: {maschera_url(cfg.casa_url)}")
    mode = ("impronta fissata" if cfg.casa_tls_impronta else
            f"nome {maschera(cfg.casa_tls_nome)}" if cfg.casa_tls_nome else
            "nessuna verifica" if not cfg.casa_tls_verifica else "nome = indirizzo")
    print(f"  verifica del certificato: {mode}")
    token, where, err = read_token(cfg)
    print(f"  token: {'trovato in ' + where if token else 'NON trovato (' + where + ')'}"
          + (" — file illeggibile" if err else ""))
    if not cfg.casa_url or not token:
        d = diagnose(cfg)
        print(f"\nProssimo passo: {d['prossimo_passo']}")
        return 1

    probe = HomeAssistantBackend(cfg.casa_url, "x", log=lambda m: None)
    if probe.tls:
        sonda_tls(probe.host, probe.port, cfg.casa_tls_nome)

    print("\n— Collegamento")
    t0 = time.perf_counter()
    be, _ = load_casa(cfg, log=lambda m: None)
    d = diagnose(cfg, be, riprova=True)
    print(f"  {d['motivo']} in {time.perf_counter() - t0:.2f} s (stato: {d['stato']})")
    if d["codice"] not in ("ok", "nessuna_entita", "agente_assente"):
        print(f"\nProssimo passo: {d['prossimo_passo']}")
        be.close()
        return 1
    print(f"  Home Assistant {be.versione}; agente integrato "
          f"{'presente' if be.agente_ok else 'ASSENTE'} ({be.agente})")

    ents = be.entita()
    rules = Regole(cfg)
    print(f"\n— Entità esposte ad Assist: {len(ents)}")
    per_dom: dict[str, int] = {}
    per_area: dict[str, int] = {}
    for e in ents:
        per_dom[e.dominio] = per_dom.get(e.dominio, 0) + 1
        per_area[e.area or "(senza stanza)"] = per_area.get(e.area or "(senza stanza)", 0) + 1
    print("  per tipo: " + ", ".join(f"{k} {v}" for k, v in sorted(per_dom.items(),
                                                                  key=lambda x: -x[1])))
    print("  per stanza: " + ", ".join(f"{k} {v}" for k, v in sorted(per_area.items())))
    delicate = [e for e in ents if rules.delicata(e)]
    elenco = [e for e in ents if rules.da_elenco(e)]
    print(f"  delicate (Calliope le legge soltanto): {len(delicate)}"
          + (f" ({', '.join(sorted({e.dominio + '/' + (e.classe or '-') for e in delicate}))})"
             if delicate else ""))
    print(f"  scene, script, automazioni fuori da casa_consentiti: {len(elenco)}")
    if len(ents) > 40:
        print("  ATTENZIONE: più di 40 entità; per i modelli locali HA ne consiglia meno di 25")
    if not ents:
        print(f"\nProssimo passo: {d['prossimo_passo']}")

    area = next((e.area for e in ents if e.dominio == "light" and e.area), None)
    frasi = ["che ore sono", "quali luci sono accese"]
    if area:
        frasi.insert(0, f"accendi le luci in {area.lower()}")
    risultati = list(misura(be, frasi)) if be.agente_ok else []

    print("\n— Esecuzione di sole domande (conversation/process)")
    for frase, interp, _ in risultati:
        if not (interp.capito and interp.intento in LETTURE_SICURE):
            continue                     # i comandi NON si eseguono, mai
        tempi, kind = [], "?"
        for _ in range(3):
            t0 = time.perf_counter()
            r = be._richiesta({"type": "conversation/process", "text": frase,  # noqa: SLF001
                               "language": be.lingua, "agent_id": be.agente})
            tempi.append(time.perf_counter() - t0)
            kind = ((r or {}).get("response") or {}).get("response_type")
        print(f"  «{frase}»: {kind}; {statistics.median(tempi) * 1000:.0f} ms "
              f"(massimo {max(tempi) * 1000:.0f})")
    tutti = [t for _, _, ts in risultati for t in ts]
    if tutti:
        p = max(tutti)
        print(f"\nTempo massimo misurato {p * 1000:.0f} ms: casa_timeout_s "
              f"{cfg.casa_timeout_s:g} s " + ("va bene." if cfg.casa_timeout_s >= 3 * p
                                              else "è stretto: alzalo."))
    print("\nNessun comando eseguito. Il token non è stato stampato.")
    be.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
