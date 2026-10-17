"""
L'elenco per area di `prove/LEGGIMI.md` si genera da `prove/elenco.md` (16/10, #82, scelta di
chi amministra): fino al 15/10 era scritto a mano, «rifatto il 09/10», e ne mancavano 126 voci.
La sezione sta tra due segni (SEGNO_INIZIO e SEGNO_FINE) ed è la prima colonna delle tabelle di
`elenco.md`, sezione per sezione, con il link alla sezione e al documento d'area. Chi aggiunge
una prova la scrive solo in `elenco.md` e rigenera:

    python -m prove --leggimi        # riscrive la sezione di LEGGIMI.md
    python prove/leggimi.py --controlla   # 1 se LEGGIMI.md non è allineato

`prova_runner` controlla che la sezione sia quella generata e che ogni prova registrata (e ogni
script di `prove/manuali/`) compaia in `elenco.md`.
"""

import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
ELENCO = RADICE / "prove" / "elenco.md"
LEGGIMI = RADICE / "prove" / "LEGGIMI.md"

SEGNO_INIZIO = ("<!-- elenco generato da elenco.md con `python -m prove --leggimi`: "
                "non scriverlo a mano -->")
SEGNO_FINE = "<!-- fine dell'elenco generato -->"
# Un nome di file tra backtick nella prima colonna (non gli argomenti come `--solo x`)
FILE = re.compile(r"^[\w./-]+\.\w+$")
# I file di dati accanto a una prova (riferimenti_nomi.tsv…): non sono prove
DATI = (".tsv", ".txt", ".json", ".npz", ".yaml")
AREA = re.compile(r"Documento d'area: \[[^\]]*\]\(([^)]+)\)")


def ancora(titolo: str) -> str:
    """L'ancora di GitHub di un titolo: minuscole, via la punteggiatura (non le lettere
    accentate né «-» e «_»), spazi in trattini."""
    t = re.sub(r"[^\w\- ]", "", titolo.strip().lower())
    return t.replace(" ", "-")


def nomi_della_cella(cella: str) -> list[str]:
    return [n for n in re.findall(r"`([^`]+)`", cella) if FILE.match(n)]


def sezioni(testo: str) -> list[tuple[str, str | None, list[str]]]:
    """(titolo, link al documento d'area, nomi della prima colonna) per ogni sezione «## » di
    elenco.md, nell'ordine del file. Una riga di tabella è quella che comincia con «| `»; le
    righe che la continuano (descrizioni lunghe a capo) non contano."""
    out: list[tuple[str, str | None, list[str]]] = []
    for riga in testo.splitlines():
        if riga.startswith("## "):
            out.append((riga[3:].strip(), None, []))
        elif not out:
            continue
        elif (m := AREA.search(riga)) and out[-1][1] is None:
            out[-1] = (out[-1][0], m.group(1), out[-1][2])
        elif riga.startswith("| `"):
            cella = riga[1:].split(" | ", 1)[0] if " | " in riga[1:] else riga[1:]
            for n in nomi_della_cella(cella):
                if not n.endswith(DATI) and n not in out[-1][2]:
                    out[-1][2].append(n)
    return out


def nomi_elencati(testo: str) -> dict[str, str]:
    """Ogni nome della prima colonna con la sua sezione (anche i file di dati)."""
    out: dict[str, str] = {}
    titolo = ""
    for riga in testo.splitlines():
        if riga.startswith("## "):
            titolo = riga[3:].strip()
        elif riga.startswith("| `"):
            cella = riga[1:].split(" | ", 1)[0]
            for n in nomi_della_cella(cella):
                out.setdefault(n, titolo)
    return out


def genera(testo_elenco: str) -> str:
    righe = []
    for titolo, area, nomi in sezioni(testo_elenco):
        link = f"[elenco](elenco.md#{ancora(titolo)})"
        if area:
            link += f", [area]({area})"
        righe.append(f"- **{titolo}** ({link}): " + ", ".join(f"`{n}`" for n in nomi))
    return "\n".join(righe)


def sostituisci(testo_leggimi: str, testo_elenco: str) -> str:
    """LEGGIMI.md con la sezione tra i segni rigenerata. ValueError se mancano i segni."""
    i = testo_leggimi.find(SEGNO_INIZIO)
    j = testo_leggimi.find(SEGNO_FINE)
    if i < 0 or j < i:
        raise ValueError(f"in LEGGIMI.md mancano i segni {SEGNO_INIZIO!r} … {SEGNO_FINE!r}")
    return (testo_leggimi[:i + len(SEGNO_INIZIO)] + "\n" + genera(testo_elenco) + "\n"
            + testo_leggimi[j:])


def allineato(testo_leggimi: str, testo_elenco: str) -> bool:
    try:
        return sostituisci(testo_leggimi, testo_elenco) == testo_leggimi
    except ValueError:
        return False


def mancanti(testo_elenco: str, nomi: list[str]) -> list[str]:
    """I nomi che non compaiono nella prima colonna di elenco.md."""
    elencati = nomi_elencati(testo_elenco)
    return sorted(n for n in set(nomi) if n not in elencati)


def scrivi() -> int:
    vecchio = LEGGIMI.read_text(encoding="utf-8")
    nuovo = sostituisci(vecchio, ELENCO.read_text(encoding="utf-8"))
    if nuovo == vecchio:
        print("LEGGIMI.md è già allineato a elenco.md")
        return 0
    LEGGIMI.write_bytes(nuovo.encode("utf-8"))      # LF come nel repository
    print("LEGGIMI.md: elenco per area rigenerato da elenco.md")
    return 0


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if "--controlla" in argv:
        ok = allineato(LEGGIMI.read_text(encoding="utf-8"), ELENCO.read_text(encoding="utf-8"))
        print("LEGGIMI.md allineato a elenco.md" if ok else
              "LEGGIMI.md non è allineato a elenco.md: python -m prove --leggimi")
        return 0 if ok else 1
    return scrivi()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
