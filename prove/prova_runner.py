"""
Il runner delle prove controlla sé stesso (06/10, Q7 della seconda analisi,
docs/ricerche/2026-10-06-analisi-2.md § 3.4). A secco, < 1 s:

- ogni `prove/prova_*.py` è registrata (A_SECCO, CON_OLLAMA) oppure nell'elenco esplicito
  delle prove manuali (MANUALI, con il perché): una prova nuova dimenticata fallisce qui;
- i nomi di LEGAMI, LIVELLO_2 e LIVELLO_3 sono prove registrate che esistono;
- ogni tool d'area (`calliope/tools/<area>.py`) sceglie nel hook almeno una prova della sua
  area del livello 2 o una del livello 1; brain, ciclo, main e config scelgono
  prova_linux_import (gli import di tutto il pacchetto su Linux);
- una prova registrata che salta una parte lo dice con «SALTATA IN PARTE:» in testa alla riga
  (il runner la conta); un salto senza il segnale e senza uscire con 77 fallisce;
- (16/10, #82) ogni prova registrata o manuale e ogni script di `prove/manuali/` compare nella
  prima colonna di `prove/elenco.md`, e l'elenco per area di `prove/LEGGIMI.md` è quello generato
  da `elenco.md` (`python -m prove --leggimi`, `prove/leggimi.py`); con i contrari.

    python prove/prova_runner.py
"""

import importlib.util
import re
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    if not ok:
        errori += 1
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio and not ok
                                               else ""), flush=True)


def runner():
    spec = importlib.util.spec_from_file_location("prove_runner", RADICE / "prove" / "__main__.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# Moduli di tools/ che servono a tutti i tool: restano trasversali (livello 1 e 3)
TRASVERSALI_TOOLS = {"__init__.py", "registry.py", "spec.py", "builtin.py"}
# Un salto detto a parole: «salto…», «saltata», «SALTO:»
SALTO = re.compile(r"\bsalt[oaie]\w*|\bSALTO\b", re.I)
FINE_INTERA = re.compile(r"return\s+(SALTATA|77)\b|exit\(\s*77\s*\)|return\s+SALTATA\b")


def salti_senza_segnale(path: Path) -> list[str]:
    """Le righe con un print che dice di aver saltato qualcosa, senza «SALTATA IN PARTE:» in
    testa e senza uscire subito con 77 (salto intero)."""
    righe = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for i, r in enumerate(righe):
        if "print(" not in r or not SALTO.search(r):
            continue
        if re.search(r'print\(f?["\']SALTATA IN PARTE:', r):
            continue
        dopo = "\n".join(righe[i:i + 4])
        if FINE_INTERA.search(dopo):
            continue
        out.append(f"{path.name}:{i + 1}: {r.strip()[:90]}")
    return out


def elenco_e_leggimi(registrate: set[str], manuali: dict) -> None:
    """Le prove in elenco.md e l'elenco generato di LEGGIMI.md (16/10, #82: fino al 15/10
    l'elenco di LEGGIMI.md era scritto a mano e ne mancavano 126 voci)."""
    sys.path.insert(0, str(RADICE / "prove"))
    import leggimi

    elenco = leggimi.ELENCO.read_text(encoding="utf-8")
    nomi = sorted(registrate | set(manuali)
                  | {p.name for p in (RADICE / "prove").glob("prova_*.py")}
                  | {f"manuali/{p.name}" for p in (RADICE / "prove" / "manuali").glob("*.py")})
    manca = leggimi.mancanti(elenco, nomi)
    verifica(f"ogni prova registrata o manuale e ogni manuali/*.py è in elenco.md ({len(nomi)})",
             not manca, "da aggiungere nella prima colonna di prove/elenco.md, nella sezione "
             "della sua area (poi python -m prove --leggimi): " + ", ".join(manca))
    verifica("l'elenco per area di LEGGIMI.md è quello generato da elenco.md",
             leggimi.allineato(leggimi.LEGGIMI.read_text(encoding="utf-8"), elenco),
             "LEGGIMI.md non è allineato a elenco.md: python -m prove --leggimi "
             "(l'elenco tra i segni <!-- … --> non si scrive a mano)")

    # Contrari, su testi finti
    finto = ("# Elenco\n\n## Casa (Home Assistant)\n\nDocumento d'area: [`docs/aree/casa.md`]"
             "(../docs/aree/casa.md)\n\n| File | Cosa fa | Serve Ollama? |\n|---|---|---|\n"
             "| `prova_casa_ha.py` | Casa, cita `prova_solo_citata.py` | No |\n"
             "| `misura_x.py`, `riferimenti_x.tsv` | Misura (`--solo y.py`) | Sì |\n"
             "| `manuali/banco_y.py` | Banco con una descrizione\nlunga a capo | Sì |\n\n"
             "## Capacità e installazioni\n\n| File | Cosa fa | Serve Ollama? |\n|---|---|---|\n"
             "| `prova_piano.py` | Piano | No |\n")
    trovate = leggimi.mancanti(finto, ["prova_casa_ha.py", "manuali/banco_y.py",
                                       "prova_finta_non_elencata.py", "prova_solo_citata.py",
                                       "banco_y.py", "riferimenti_x.tsv"])
    verifica("contrario: una prova finta non elencata (o solo citata in una descrizione, o "
             "senza manuali/) manca da elenco.md",
             trovate == ["banco_y.py", "prova_finta_non_elencata.py", "prova_solo_citata.py"],
             str(trovate))
    gen = leggimi.genera(finto)
    verifica("l'elenco generato: sezioni, ancore, area, niente file di dati né argomenti",
             gen == "- **Casa (Home Assistant)** ([elenco](elenco.md#casa-home-assistant), "
                    "[area](../docs/aree/casa.md)): `prova_casa_ha.py`, `misura_x.py`, "
                    "`manuali/banco_y.py`\n- **Capacità e installazioni** "
                    "([elenco](elenco.md#capacità-e-installazioni)): `prova_piano.py`", gen)
    leggi = (f"# Prove\n\nTesta.\n\n{leggimi.SEGNO_INIZIO}\n{gen}\n{leggimi.SEGNO_FINE}\n\n"
             "Coda.\n")
    con_riga = finto + "| `prova_nuova.py` | Una prova nuova | No |\n"
    rigenerato = leggimi.sostituisci(leggi, con_riga)
    verifica("contrario: una riga nuova in elenco.md rende LEGGIMI.md non allineato, e "
             "rigenerare basta (testa e coda restano)",
             leggimi.allineato(leggi, finto) and not leggimi.allineato(leggi, con_riga)
             and leggimi.allineato(rigenerato, con_riga) and "`prova_nuova.py`" in rigenerato
             and rigenerato.startswith("# Prove\n\nTesta.\n") and rigenerato.endswith("Coda.\n"))
    a_mano = leggi.replace("`prova_piano.py`", "`prova_piano.py`, `prova_a_mano.py`")
    verifica("contrari: un nome aggiunto a mano o i segni tolti non sono allineati",
             not leggimi.allineato(a_mano, finto)
             and not leggimi.allineato(leggi.replace(leggimi.SEGNO_INIZIO, ""), finto))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    m = runner()
    registrate = {p[0] for p in m.A_SECCO} | {p[0] for p in m.CON_OLLAMA}
    manuali = dict(getattr(m, "MANUALI", {}) or {})
    tutte = {p.name for p in (RADICE / "prove").glob("prova_*.py")}

    fuori = sorted(tutte - registrate - set(manuali))
    verifica("ogni prove/prova_*.py è nel runner o tra le manuali (MANUALI)", not fuori,
             f"da registrare o da mettere in MANUALI con il perché: {fuori}")
    verifica("le manuali esistono, hanno un perché e non sono anche registrate",
             all(n in tutte and str(v).strip() for n, v in manuali.items())
             and not (set(manuali) & registrate),
             str(sorted(n for n in manuali if n not in tutte or n in registrate)))

    a_secco = {p[0] for p in m.A_SECCO}
    nomi_legami = {p for _, prove in m.LEGAMI for p in prove}
    for nome, insieme in (("LEGAMI", nomi_legami), ("LIVELLO_2", m.LIVELLO_2),
                          ("LIVELLO_3", m.LIVELLO_3)):
        manca = sorted(n for n in insieme if n not in a_secco or n not in tutte)
        verifica(f"{nome}: solo prove a secco registrate che esistono", not manca, str(manca))

    tools = sorted(p.name for p in (RADICE / "calliope" / "tools").glob("*.py")
                   if p.name not in TRASVERSALI_TOOLS)
    senza = [t for t in tools if not m.scelte_dai_file([f"calliope/tools/{t}"])]
    verifica(f"ogni tool d'area sceglie le prove della sua area ({len(tools)} file)", not senza,
             str(senza))
    for f, attesa in (("calliope/tools/casa.py", "prova_casa_ha.py"),
                      ("calliope/tools/agenti.py", "prova_agenti.py"),
                      ("calliope/tools/schermi.py", "prova_schermi.py"),
                      ("calliope/tools/estensioni.py", "prova_estensioni.py"),
                      ("calliope/tools/pc.py", "prova_esecutore.py"),
                      ("calliope/tools/stato.py", "prova_capacita.py"),
                      ("calliope/tools/stato.py", "prova_installa.py")):
        verifica(f"{f} sceglie {attesa} (livello {m.livello(attesa)})",
                 attesa in m.scelte_dai_file([f]))
    for f in ("calliope/brain.py", "calliope/ciclo.py", "calliope/main.py",
              "calliope/config.py"):
        verifica(f"{f} sceglie prova_linux_import (import solo-Windows)",
                 "prova_linux_import.py" in m.scelte_dai_file([f])
                 and m.livello("prova_linux_import.py") == 2)
    verifica("contrario: un file qualsiasi non sceglie i tool d'area",
             not m.scelte_dai_file(["docs/roadmap.md"]))

    salti = [x for n in sorted(a_secco - {"prova_runner.py"})
             if (RADICE / "prove" / n).is_file()
             for x in salti_senza_segnale(RADICE / "prove" / n)]
    verifica("salti parziali con «SALTATA IN PARTE:» (o salto intero con 77)", not salti,
             "\n    " + "\n    ".join(salti))
    finto = RADICE / "prove" / "__salto_finto__.txt"
    try:
        finto.write_text('    print("   (openssl non c\'è: salto la parte TLS)")\n    return\n'
                         '    print("SALTATA IN PARTE: openssl non c\'è")\n'
                         '    print("Nessun Edge: prova saltata.")\n    return SALTATA\n',
                         encoding="utf-8")
        trovati = salti_senza_segnale(finto)
    finally:
        finto.unlink(missing_ok=True)
    verifica("il controllo dei salti trova solo il salto senza segnale", len(trovati) == 1
             and ":1:" in trovati[0], str(trovati))
    elenco_e_leggimi(registrate, manuali)
    print(f"\n{errori} errori" if errori else "\nTutto a posto.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
