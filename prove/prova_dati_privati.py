"""
Nessun dato privato nei file tracciati (06/10, pubblicazione del sorgente: docs/pubblicazione.md).

Il repository è pubblico: questa prova, nell'hook (livello 1, sulla copia dell'indice), ferma
il commit se un file tracciato contiene
- un file che non va mai in git: database, audio, chiavi e certificati, modelli, file ZIM,
  configurazioni di questa installazione (segreti.yaml, dgx.yaml, satellite.json…);
- un segreto riconoscibile: chiave privata PEM, JWT, token di GitHub, Hugging Face, OpenAI,
  AWS, Slack, Google, chiave SSH pubblica;
- un indirizzo IP privato che non è tra quelli d'esempio (ESEMPI_IP, con il perché);
- un nome DuckDNS che non è un segnaposto;
- un percorso con il nome di un utente (`C:\\Users\\<nome>`, `/home/<nome>`);
- un termine privato di `privato/termini.txt` (fuori da git: nomi veri della famiglia,
  dominio e nome dell'azienda, indirizzi veri…). Senza il file questa parte si salta e la
  prova lo dice.

Formato di `privato/termini.txt`, una riga per termine:
    # commento
    Parola                 parola intera, maiuscole come scritte
    i:parola               parola intera, maiuscole e minuscole uguali
    re:espressione         espressione regolare (Python)
    Termine || eccezione || altra eccezione
                           una riga del file che contiene un'eccezione non conta
                           (per esempio una voce di Piper con lo stesso nome)
Il file si cerca in CALLIOPE_TERMINI_PRIVATI, poi in `privato/` del repository da cui parte la
prova (PROVE_ORIGINE, messa dal runner per la copia dell'indice) e del repository principale
(un worktree usa quello della cartella principale).

Prima del controllo vero, la prova controlla sé stessa su un albero finto (un segreto, un IP
privato, un termine, un database, i casi contrari). ~1 s.

    python prove/prova_dati_privati.py
"""
from __future__ import annotations

import fnmatch
import ipaddress
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def verifica(nome: str, ok: bool, dettaglio: str = ""):
    global errori
    print(("ok  " if ok else "ERR ") + nome + ("" if ok or not dettaglio else f"\n    {dettaglio}"))
    if not ok:
        errori += 1


# File che non vanno mai in git, ovunque stiano
ESTENSIONI_VIETATE = {".db", ".sqlite", ".sqlite3", ".wav", ".flac", ".mp3", ".ogg", ".m4a",
                      ".pem", ".key", ".crt", ".p12", ".pfx", ".onnx", ".pt", ".pth", ".gguf",
                      ".safetensors", ".ckpt", ".zim", ".bundle"}
NOMI_VIETATI = {"segreti.yaml", "dgx.yaml", "satellite.json", "speakers.json",
                "calliope.locale.yaml", "personalita.json", "contesto.json", "termini.txt"}

SEGRETI = [
    ("chiave privata", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")),
    ("token", re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
                         r"|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
                         r"|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})")),
    ("chiave SSH", re.compile(r"\bssh-(rsa|ed25519|dss) AAAA[0-9A-Za-z+/]{20,}")),
]

# Indirizzi privati ammessi: tutti d'esempio, scelti per le prove (SSRF, reti ammesse
# dell'inoltro, indirizzi di configurazione), nessuno di una rete vera. Uno nuovo si aggiunge
# qui solo se è inventato.
ESEMPI_IP = {
    # reti intere (CIDR) nelle regole e nei documenti
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "192.168.1.0/24",
    "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
    "240.0.0.0/4", "255.255.255.255/32",
    # predefiniti dei prodotti: WireGuard dell'add-on di Home Assistant e PiVPN
    # (satellite_inoltro_reti), con indirizzi di prova dentro
    "172.27.66.0/24", "172.27.66.2", "10.6.0.0/24", "10.6.0.2", "10.6.0.3",
    # indirizzi inventati delle prove e degli esempi
    "10.0.0.1", "10.0.0.2", "10.0.0.5", "10.0.0.9", "10.1.2.3", "10.255.255.255", "10.8.0.2",
    "10.9.8.6", "10.9.8.7", "169.254.1.1", "169.254.169.254", "169.254.3.4", "172.16.0.5",
    "172.16.5.4", "172.17.0.1", "172.31.255.1", "192.0.2.1", "203.0.113.7",
    "192.168.0.10", "192.168.1.1", "192.168.1.5", "192.168.1.10", "192.168.1.20",
    "192.168.1.23", "192.168.1.30", "192.168.1.40", "192.168.1.50", "192.168.1.60",
    "192.168.10.1", "192.168.10.5", "192.168.10.20", "192.168.7.21",
    "255.255.255.255",
}
# File dove i numeri a quattro parti sono versioni, non indirizzi
SENZA_IP = {"uv.lock"}
IP = re.compile(r"(?<![\d.])((?:\d{1,3}\.){3}\d{1,3})(/\d{1,2})?(?![\d.])")

DUCKDNS = re.compile(r"\b([A-Za-z0-9-]+)\.duckdns\.org\b", re.I)
DUCKDNS_ESEMPI = {"casa-mia", "casa-finta", "a", "nome", "esempio"}

UTENTE_WIN = re.compile(r"\b[A-Za-z]:[\\/]+Users[\\/]+([A-Za-z0-9._~-]+)", re.I)
UTENTE_UNIX = re.compile(r"(?<![\w.])/(?:home|Users)/([A-Za-z0-9._-]+)")
UTENTI_ESEMPIO = {"x", "public", "default", "utente", "nome", "user", "runner", "<nome>"}

# Copia dell'indice: i file grossi fuori da git entrano come hard link (prove/__main__.py,
# RISORSE): non sono file tracciati
RISORSE = ("voices/*", "models/*", "wakeword/modelli/*", "biblioteca/*.zim",
           "biblioteca/*.sha256", "biblioteca/*.verificato", "biblioteca/indici/*")


def file_tracciati(radice: Path) -> list[str]:
    if (radice / ".git").exists():
        r = subprocess.run(["git", "-C", str(radice), "ls-files", "-z"], capture_output=True,
                           timeout=60)
        if r.returncode == 0:
            return [x for x in r.stdout.decode("utf-8", "replace").split("\0") if x]
    out = []
    for p in radice.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(radice).as_posix()
        if any(x in p.parts for x in (".venv", "__pycache__", ".git", "privato")):
            continue
        if any(fnmatch.fnmatch(rel, pat) for pat in RISORSE):
            continue
        out.append(rel)
    return out


def leggi_termini(f: Path) -> list[tuple[str, re.Pattern, list[str]]]:
    termini = []
    for riga in f.read_text(encoding="utf-8").splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#"):
            continue
        pezzi = [x.strip() for x in riga.split("||")]
        t, eccezioni = pezzi[0], [x for x in pezzi[1:] if x]
        if t.startswith("re:"):
            rx = re.compile(t[3:])
        elif t.startswith("i:"):
            rx = re.compile(r"(?<!\w)" + re.escape(t[2:]) + r"(?!\w)", re.I)
        else:
            rx = re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)")
        termini.append((t, rx, eccezioni))
    return termini


def trova_termini() -> Path | None:
    if os.environ.get("CALLIOPE_TERMINI_PRIVATI"):
        p = Path(os.environ["CALLIOPE_TERMINI_PRIVATI"])
        return p if p.is_file() else None
    origini = [Path(os.environ["PROVE_ORIGINE"])] if os.environ.get("PROVE_ORIGINE") else []
    origini.append(RADICE)
    for o in origini:
        if (o / "privato" / "termini.txt").is_file():
            return o / "privato" / "termini.txt"
        try:
            r = subprocess.run(["git", "-C", str(o), "rev-parse", "--git-common-dir"],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0 and r.stdout.strip():
            comune = Path(r.stdout.strip())
            if not comune.is_absolute():
                comune = o / comune
            p = comune.resolve().parent / "privato" / "termini.txt"
            if p.is_file():
                return p
    return None


def maschera(s: str) -> str:
    return s[:2] + "…" if len(s) > 3 else "…"


def controlla(radice: Path, termini) -> list[str]:
    """Le violazioni, come «file:riga: tipo (valore mascherato)»: mai il valore intero."""
    trovati = []
    for rel in file_tracciati(radice):
        nome = rel.rsplit("/", 1)[-1]
        est = os.path.splitext(nome)[1].lower()
        if est in ESTENSIONI_VIETATE or nome in NOMI_VIETATI:
            trovati.append(f"{rel}: file da non tracciare ({est or nome})")
            continue
        p = radice / rel
        try:
            dati = p.read_bytes()
        except OSError:
            continue
        if b"\0" in dati[:8000]:
            continue                                   # binari ammessi (icone): solo il nome
        testo = dati.decode("utf-8", "replace")
        for i, riga in enumerate(testo.splitlines(), 1):
            for tipo, rx in SEGRETI:
                if rx.search(riga):
                    trovati.append(f"{rel}:{i}: {tipo}")
            if rel not in SENZA_IP:
                for m in IP.finditer(riga):
                    try:
                        ip = ipaddress.ip_address(m.group(1))
                    except ValueError:
                        continue
                    if (ip.is_private and not ip.is_loopback and not ip.is_unspecified
                            and m.group(0) not in ESEMPI_IP and m.group(1) not in ESEMPI_IP):
                        trovati.append(f"{rel}:{i}: IP privato non d'esempio ({maschera(m.group(0))})")
            for m in DUCKDNS.finditer(riga):
                if m.group(1).lower() not in DUCKDNS_ESEMPI:
                    trovati.append(f"{rel}:{i}: nome DuckDNS ({maschera(m.group(1))})")
            for rx in (UTENTE_WIN, UTENTE_UNIX):
                for m in rx.finditer(riga):
                    if m.group(1).lower() not in UTENTI_ESEMPIO:
                        trovati.append(f"{rel}:{i}: percorso con un nome utente ({maschera(m.group(1))})")
            for t, rx, eccezioni in termini:
                if rx.search(riga) and not any(e in riga for e in eccezioni):
                    trovati.append(f"{rel}:{i}: termine privato ({maschera(t.split(':', 1)[-1])})")
    return trovati


def prova_su_albero_finto():
    """Il controllo trova ciò che deve (e non i casi contrari) in un albero finto."""
    with tempfile.TemporaryDirectory(prefix="dati-privati-") as d:
        r = Path(d)
        (r / "docs").mkdir()
        # i valori «veri» scritti a pezzi, così questo file non li contiene
        chiave = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"
        ip_vero = "192.168." + "77.4"
        dns_vero = "mio-vero" + ".duckdns.org"
        utente_vero = "C:" + "\\Users\\" + "mario.bianchi" + "\\Desktop"
        (r / "a.py").write_text(f'K = """{chiave}"""\nURL = "http://{ip_vero}:8123"\n'
                                "nome = 'Zebedeo'\n", encoding="utf-8")
        (r / "docs" / "b.md").write_text(
            "esempio: 192.168.1.10, rete 10.0.0.0/8, loopback 127.0.0.1, pubblico 8.8.8.8\n"
            "il vestito zebedeo (minuscolo), la voce Zebedeo di Piper\n"
            f"casa-mia.duckdns.org e {dns_vero}\n"
            f"C:\\Users\\x\\Documenti e {utente_vero}\n", encoding="utf-8")
        (r / "memoria.db").write_bytes(b"SQLite format 3\0")
        termini_f = r / "termini.txt"
        termini_f.write_text("# prova\nZebedeo || voce Zebedeo\n", encoding="utf-8")
        trovati = controlla(r, leggi_termini(termini_f))
        tipi = {t.split(": ", 1)[1].split(" (")[0] for t in trovati}
        verifica("albero finto: chiave privata, IP privato, termine, database, DuckDNS, "
                 "utente trovati",
                 {"chiave privata", "IP privato non d'esempio", "termine privato",
                  "file da non tracciare", "nome DuckDNS", "percorso con un nome utente"} <= tipi,
                 str(trovati))
        verifica("albero finto: i casi contrari no (IP d'esempio, loopback, pubblico, "
                 "minuscolo, eccezione, segnaposto)",
                 sum("termine privato" in t for t in trovati) == 1
                 and sum("IP privato" in t for t in trovati) == 1
                 and sum("DuckDNS" in t for t in trovati) == 1
                 and sum("nome utente" in t for t in trovati) == 1, str(trovati))
        verifica("albero finto: il valore non compare nel messaggio",
                 not any("77.4" in t or "mario.bianchi" in t or "Zebedeo" in t for t in trovati),
                 str(trovati))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    prova_su_albero_finto()
    f = trova_termini()
    if f is None:
        print("SALTATA IN PARTE: privato/termini.txt non c'è: controllo dei termini privati "
              "saltato, gli altri controlli sì")
        termini = []
    else:
        termini = leggi_termini(f)
        print(f"   termini privati: {len(termini)}")
    trovati = controlla(RADICE, termini)
    verifica(f"nessun dato privato nei file tracciati ({len(file_tracciati(RADICE))} file)",
             not trovati, "\n    ".join(trovati[:40]) + (f"\n    … e altri {len(trovati) - 40}"
                                                         if len(trovati) > 40 else ""))
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
