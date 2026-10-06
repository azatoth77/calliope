import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Prova a secco dei tool pc_* (calliope/tools/pc.py) con un PC finto (prove/pc_finto.py).

Niente librerie native e niente effetti sul PC vero: livelli e rifiuti espliciti, valori
detti a voce («un po' più alto»), limiti 0–100, schermo bloccato, catalogo delle app,
apertura di file solo dall'ultima ricerca della stessa persona, periodi passati
(tempi.parse_past_range), prompt e configurazione.
"""

import contextlib
import datetime
import io
import json
import tempfile
from pathlib import Path

from calliope.config import Config, load_config
from calliope.tempi import parse_past_range
from calliope.tools.builtin import build_registry
from calliope.tools.pc import parse_amount
from calliope.tools.spec import ToolContext
from prove.pc_finto import FILE, FakePC

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  {dettaglio}" if dettaglio else ""))


class Prof:
    def __init__(self, pid, name, admin=False):
        self.id, self.name, self.admin = pid, name, admin


class Speakers:
    def __init__(self):
        self.p = {"Dario": Prof("dario-id", "Dario", admin=True), "Bianca": Prof("bianca-id", "Bianca"),
                  "Marco": Prof("marco-id", "Marco")}

    def get(self, n):
        return self.p.get(n)

    def known_speakers(self):
        return list(self.p)


class SpeakerCtx:
    def __init__(self, name, from_session=False):
        self.current_speaker, self.from_session = name, from_session
        prof = Speakers().get(name) if name else None
        self.current_level = ("ospite" if name is None else
                              "amministra" if prof and prof.admin and not from_session else "familiare")


cfg = Config()
cfg.pc_proprietari = ["Marco"]          # Marco è proprietario per nome; Dario amministra


def chiama(pc, nome, args, chi="Dario", from_session=False, user_text="", reg=None,
           livello=None, config=None):
    reg = reg or build_registry(pc={"portatile": pc})
    sc = SpeakerCtx(chi, from_session)
    ctx = ToolContext(cfg=config or cfg, speakers=Speakers(), speaker_ctx=sc, speaker=None,
                      pc={"portatile": pc}, user_text=user_text)
    return json.loads(reg.call(nome, args, ctx, livello or sc.current_level))


def nomi(reg, livello):
    """I tool ammessi a quel livello (i permessi): il modello li vede tutti (03/10)."""
    return {s["function"]["name"] for s in reg.schemas_for(livello)}


def rifiutato(r):
    return r.get("ok") is False and "NON" in r.get("fatto", "")


PC_TOOLS = {"pc_stato", "pc_volume", "pc_media", "pc_luminosita", "pc_apri_app", "pc_blocca",
            "pc_cerca_file", "pc_apri_file"}

# ── registro e livelli ──
reg = build_registry(pc={"portatile": FakePC()})
verifica("senza PC: nessun tool pc_*", not any(n.startswith("pc_") for n in nomi(build_registry(), "amministra")))
verifica("familiare: tutti gli 8 tool pc_*", PC_TOOLS <= nomi(reg, "familiare"))
verifica("ospite: nessun tool pc_* ammesso (predefinito)", not any(n.startswith("pc_") for n in nomi(reg, "ospite")))
reg_osp = build_registry(pc={"portatile": FakePC()}, pc_ospite=True)
verifica("ospite con pc_ospite: solo volume e musica",
         {n for n in nomi(reg_osp, "ospite") if n.startswith("pc_")} == {"pc_volume", "pc_media"})
schemi = {s["function"]["name"]: s["function"]["parameters"] for s in reg.all_schemas()}
verifica("un solo PC: niente parametro pc", not any("pc" in p["properties"] for p in schemi.values()
                                                     if p is not None))
reg2 = build_registry(pc={"portatile": FakePC(), "studio": FakePC("studio")})
verifica("due PC: parametro pc con enum",
         reg2.get("pc_volume").parameters["properties"]["pc"]["enum"] == ["portatile", "studio"])
reg_poco = build_registry(pc={"portatile": FakePC(caps=("volume", "blocco"))})
verifica("capacità parziali: solo i tool che servono",
         {n for n in nomi(reg_poco, "familiare") if n.startswith("pc_")} == {"pc_stato", "pc_volume", "pc_blocca"})
verifica("capacità parziali: enum di pc_stato ridotto",
         reg_poco.get("pc_stato").parameters["properties"]["cosa"]["enum"] == ["volume", "bloccato"])
verifica("enum delle app = catalogo", set(schemi["pc_apri_app"]["properties"]["app"]["enum"])
         == {"calcolatrice", "blocco note", "esplora file", "impostazioni", "browser", "word"})

# ── prompt ──
base = cfg.prompt_for(biblioteca=False)
con = cfg.prompt_for(biblioteca=False, pc=sorted(PC_TOOLS))
verifica("prompt senza PC invariato e senza pc_", base == cfg.system_prompt and "pc_" not in base)
verifica("prompt con PC: nomina tutti i tool pc_*", all(n in con for n in PC_TOOLS))
verifica("prompt con PC: non dice più «non usi… file»", "o file" not in con and "o file" in base)

# ── valori detti a voce ──
for valore, testo, atteso in [(None, "", None), ("un po'", "", ("delta", 10)),
                              ("un pochino", "", ("delta", 5)), ("molto", "", ("delta", 20)),
                              ("20", "alza di 20", ("delta", 20)), ("venti", "", ("delta", 20)),
                              ("50", "alza il volume a 50", ("assoluto", 50)),
                              ("al 30%", "", ("assoluto", 30)), ("al massimo", "", ("assoluto", 100)),
                              ("a metà", "", ("assoluto", 50)), ("al minimo", "", ("assoluto", 0)),
                              # 01/10: due numeri nella frase, l'indizio «a 30» non vale
                              ("30", "metti il volume a 30 e alza la luminosità di 30",
                               ("delta", 30)),
                              ("50", "alza il volume a 50 e poi la luminosità a 20", ("delta", 50))]:
    got = parse_amount(valore, 10, testo)
    verifica(f"parse_amount({valore!r}, «{testo}») = {atteso}", got == atteso, str(got))

# ── volume ──
pc = FakePC(volume=40)
r = chiama(pc, "pc_volume", {"azione": "alza"})
verifica("alza senza valore: +10", pc.volume == 50 and "50 per cento" in r.get("conferma", ""), str(r))
chiama(pc, "pc_volume", {"azione": "alza", "valore": "un po'"}, user_text="alzalo un po' più")
verifica("«un po' più alto»: +10", pc.volume == 60, str(pc.volume))
chiama(pc, "pc_volume", {"azione": "abbassa", "valore": "un pochino"})
verifica("«un pochino» più basso: −5", pc.volume == 55, str(pc.volume))
chiama(pc, "pc_volume", {"azione": "alza", "valore": "50"}, user_text="Alza il volume a 50")
verifica("«alza a 50» con azione=alza: assoluto", pc.volume == 50, str(pc.volume))
chiama(pc, "pc_volume", {"azione": "imposta", "valore": 150})
verifica("imposta 150: limite 100", pc.volume == 100, str(pc.volume))
r = chiama(pc, "pc_volume", {"azione": "alza", "valore": "molto"})
verifica("alza già al massimo: niente azione, conferma chiara",
         pc.volume == 100 and "massimo" in r.get("conferma", "") and pc.azioni[-1] == ("volume", 100), str(r))
chiama(pc, "pc_volume", {"azione": "imposta", "valore": "20"})
chiama(pc, "pc_volume", {"azione": "abbassa", "valore": "30"})
verifica("abbassa 30 da 20: limite 0", pc.volume == 0, str(pc.volume))
r = chiama(pc, "pc_volume", {"azione": "imposta"})
verifica("imposta senza valore: errore, niente azione", r.get("ok") is False and pc.volume == 0, str(r))
chiama(pc, "pc_volume", {"azione": "imposta", "valore": "40"})
r = chiama(pc, "pc_volume", {"azione": "muto"})
verifica("muto", pc.muto and "disattivato" in r.get("conferma", ""), str(r))
r = chiama(pc, "pc_volume", {"azione": "togli il muto"})
verifica("«togli il muto» → riattiva", not pc.muto and "40 per cento" in r.get("conferma", ""), str(r))
r = chiama(pc, "pc_volume", {"azione": "alza"}, chi=None)
verifica("ospite: pc_volume rifiutato in modo esplicito", rifiutato(r) and pc.volume == 40, str(r))
r = chiama(pc, "pc_volume", {"azione": "alza"}, chi=None, reg=reg_osp)
verifica("ospite con pc_ospite: pc_volume ammesso", r.get("ok") is True and pc.volume == 50, str(r))
r = chiama(pc, "pc_luminosita", {"azione": "alza"}, chi=None, reg=reg_osp)
verifica("ospite con pc_ospite: luminosità rifiutata", rifiutato(r), str(r))

# ── musica ──
pc = FakePC()
r = chiama(pc, "pc_media", {"comando": "pausa"})
verifica("pausa senza niente che suona: errore con NON, niente azione",
         r.get("ok") is False and "NON" in r.get("fatto", "") and not pc.azioni, str(r))
pc = FakePC(media={"titolo": "Bohemian Rhapsody", "artista": "Queen", "app": "Spotify",
                   "in_riproduzione": True})
r = chiama(pc, "pc_stato", {"cosa": "musica"})
verifica("cosa sta suonando", "Bohemian Rhapsody" in r.get("conferma", "") and "Spotify" in r["conferma"], str(r))
r = chiama(pc, "pc_media", {"comando": "stop"})
verifica("«stop» → pausa", pc.azioni[-1] == ("media", "pausa") and r.get("conferma") == "Fatto, in pausa.", str(r))
chiama(pc, "pc_media", {"comando": "avanti"})
verifica("avanti", pc.azioni[-1] == ("media", "avanti"))
r = chiama(pc, "pc_stato", {})
verifica("stato senza cosa: volume e musica",
         "volume è al 40 per cento" in r.get("conferma", "") and "in pausa" in r["conferma"], str(r))

# ── luminosità ──
pc = FakePC(luminosita=80)
chiama(pc, "pc_luminosita", {"azione": "abbassa", "valore": "un po'"})
verifica("luminosità un po' più bassa: 70", pc.lum == 70, str(pc.lum))
chiama(pc, "pc_luminosita", {"azione": "imposta", "valore": "al massimo"})
verifica("luminosità al massimo", pc.lum == 100, str(pc.lum))

# ── stato, programmi aperti ──
pc = FakePC()
r = chiama(pc, "pc_stato", {"cosa": "batteria"})
verifica("batteria", "76 per cento" in r.get("conferma", ""), str(r))
r = chiama(pc, "pc_stato", {"cosa": "programmi_aperti"})
verifica("programmi aperti: chi amministra sì", "Visual Studio Code" in r.get("conferma", ""), str(r))
r = chiama(pc, "pc_stato", {"cosa": "programmi_aperti"}, chi="Marco")
verifica("programmi aperti: proprietario per nome sì", r.get("ok") is True, str(r))
r = chiama(pc, "pc_stato", {"cosa": "programmi_aperti"}, chi="Bianca")
verifica("programmi aperti: altra familiare rifiutata con NON", rifiutato(r), str(r))
r = chiama(pc, "pc_stato", {"cosa": "programmi_aperti"}, chi="Marco", from_session=True)
verifica("programmi aperti: proprietario solo dalla conversazione (zona grigia) rifiutato", rifiutato(r), str(r))
pc.locked = True
r = chiama(pc, "pc_stato", {"cosa": "programmi_aperti"})
verifica("programmi aperti a schermo bloccato: rifiutato", rifiutato(r) and "bloccato" in r["motivo"], str(r))
r = chiama(pc, "pc_stato", {"cosa": "volume"})
verifica("volume a schermo bloccato: si legge", r.get("ok") is True, str(r))
r = chiama(pc, "pc_stato", {"cosa": "bloccato"})
verifica("stato bloccato", "è bloccato" in r.get("conferma", ""), str(r))

# ── app ──
pc = FakePC()
r = chiama(pc, "pc_apri_app", {"app": "calcolatrice"}, chi="Bianca")
verifica("apri la calcolatrice (familiare)", pc.azioni == [("avvia", "calc.exe")]
         and r.get("conferma") == "Apro la calcolatrice sul portatile.", str(r))
r = chiama(pc, "pc_apri_app", {"app": "Word"})
verifica("apri Word", pc.azioni[-1] == ("avvia", "winword.exe") and "Word" in r.get("conferma", ""), str(r))
r = chiama(pc, "pc_apri_app", {"app": "cmd.exe /c del *"})
verifica("app fuori catalogo: rifiutata, niente avviato", r.get("ok") is False and len(pc.azioni) == 2, str(r))
r = chiama(pc, "pc_apri_app", {"app": "calcolatrice"}, chi=None)
verifica("ospite: apri_app rifiutato", rifiutato(r) and len(pc.azioni) == 2, str(r))
pc.locked = True
r = chiama(pc, "pc_apri_app", {"app": "calcolatrice"})
verifica("schermo bloccato: apri_app rifiutato", rifiutato(r) and len(pc.azioni) == 2, str(r))

# ── blocco ──
pc = FakePC()
r = chiama(pc, "pc_blocca", {}, chi="Bianca")
verifica("blocca", pc.locked and r.get("conferma") == "Fatto, portatile bloccato.", str(r))
r = chiama(pc, "pc_blocca", {})
verifica("già bloccato", "già bloccato" in r.get("conferma", "") and pc.azioni == [("blocca",)], str(r))

# ── ricerca e apertura di file ──
pc = FakePC()
r = chiama(pc, "pc_apri_file", {"risultato": 1})
verifica("apri_file senza ricerca: errore, niente aperto", r.get("ok") is False
         and "NON" in r.get("fatto", "") and not pc.azioni, str(r))
r = chiama(pc, "pc_cerca_file", {"testo": "bolletta"}, chi="Bianca")
verifica("cerca_file: familiare non proprietaria rifiutata", rifiutato(r) and pc.ultima_ricerca is None, str(r))
r = chiama(pc, "pc_cerca_file", {"testo": "bolletta", "tipo": "pdf"})
verifica("cerca bollette PDF: 3, la più recente prima",
         [f["nome"] for f in r.get("risultati", [])] == ["Bolletta acqua", "Bolletta luce agosto",
                                                         "Bolletta gas luglio"]
         and "Quale apro?" in r.get("conferma", ""), str(r.get("conferma")))
verifica("i percorsi non escono dall'esecutore", "percorso" not in json.dumps(r))
verifica("«Quale apro?»: azione in sospeso con i file numerati (per Brain)",
         r.get("in_sospeso", {}).get("tool") == "pc_apri_file"
         and "2 = Bolletta luce agosto" in r["in_sospeso"].get("cosa", ""), str(r.get("in_sospeso")))
r = chiama(pc, "pc_apri_file", {"risultato": 2})
verifica("apri il secondo", pc.azioni[-1] == ("apri", FILE[0]["percorso"])
         and r.get("conferma") == "Apro Bolletta luce agosto.", str(r))
r = chiama(pc, "pc_apri_file", {"risultato": "ultimo"})
verifica("apri l'ultimo", pc.azioni[-1] == ("apri", FILE[1]["percorso"]), str(r))
r = chiama(pc, "pc_apri_file", {"risultato": 7})
verifica("risultato fuori elenco: errore", r.get("ok") is False and len(pc.azioni) == 2, str(r))
r = chiama(pc, "pc_apri_file", {"risultato": 1}, chi="Marco")
verifica("apri_file: la ricerca di un'altra persona non vale", r.get("ok") is False
         and len(pc.azioni) == 2, str(r))
r = chiama(pc, "pc_apri_file", {"risultato": "C:\\Windows\\System32\\cmd.exe"})
verifica("apri_file con un percorso: rifiutato", r.get("ok") is False and len(pc.azioni) == 2, str(r))
chiama(pc, "pc_cerca_file", {"testo": "bolletta", "periodo": "la settimana scorsa"})
oggi = datetime.datetime.combine(datetime.date.today(), datetime.time())
lun = oggi - datetime.timedelta(days=oggi.weekday())
verifica("periodo «la settimana scorsa» passato all'esecutore",
         pc.ultima_ricerca[2:] == ((lun - datetime.timedelta(days=7)).isoformat(), lun.isoformat()),
         str(pc.ultima_ricerca))
r = chiama(pc, "pc_cerca_file", {"testo": "fattura introvabile"})
verifica("nessun risultato: conferma chiara", r.get("risultati") == [] and "non ho trovato" in r.get("conferma", ""), str(r))
r = chiama(pc, "pc_cerca_file", {})
verifica("ricerca vuota: errore, nessun elenco", r.get("ok") is False and "risultati" not in r, str(r))
pc.locked = True
r = chiama(pc, "pc_cerca_file", {"testo": "bolletta"})
verifica("schermo bloccato: cerca_file rifiutato", rifiutato(r), str(r))
r = chiama(pc, "pc_apri_file", {"risultato": 1})
verifica("schermo bloccato: apri_file rifiutato", rifiutato(r), str(r))

# ── periodi passati ──
adesso = datetime.datetime(2026, 9, 26, 15, 0)          # sabato
for testo, atteso in [
        ("", (None, None)), ("boh", (None, None)),
        ("ieri", ("2026-09-25T00:00", "2026-09-26T00:00")),
        ("l'altro ieri", ("2026-09-24T00:00", "2026-09-25T00:00")),
        ("oggi", ("2026-09-26T00:00", None)),
        ("la settimana scorsa", ("2026-09-14T00:00", "2026-09-21T00:00")),
        ("questa settimana", ("2026-09-21T00:00", None)),
        ("il mese scorso", ("2026-08-01T00:00", "2026-09-01T00:00")),
        ("ad agosto", ("2026-08-01T00:00", "2026-09-01T00:00")),
        ("a dicembre", ("2025-12-01T00:00", "2026-01-01T00:00")),
        ("lunedì", ("2026-09-21T00:00", "2026-09-22T00:00")),
        ("sabato scorso", ("2026-09-19T00:00", "2026-09-20T00:00")),
        ("negli ultimi 3 giorni", ("2026-09-23T15:00", None)),
        ("3 giorni fa", ("2026-09-23T00:00", "2026-09-24T00:00")),
        ("l'anno scorso", ("2025-01-01T00:00", "2026-01-01T00:00"))]:
    dal, al, _ = parse_past_range(testo, adesso)
    got = (dal and dal.isoformat(timespec="minutes"), al and al.isoformat(timespec="minutes"))
    verifica(f"periodo «{testo}»", got == atteso, str(got))

# ── configurazione ──
tmp = Path(tempfile.mkdtemp()) / "pc.yaml"
tmp.write_text("pc:\n  pc_proprietari: [Bianca]\n  pc_app:\n    posta: olk.exe\n", encoding="utf-8")
with contextlib.redirect_stdout(io.StringIO()):
    c = load_config(str(tmp))
verifica("calliope.yaml: proprietari e catalogo", c.pc_proprietari == ["Bianca"] and c.pc_app == {"posta": "olk.exe"})
tmp.write_text("pc:\n  pc_proprietari: Bianca\n  pc_app: [calc.exe]\n", encoding="utf-8")
out = io.StringIO()
with contextlib.redirect_stdout(out):
    c = load_config(str(tmp))
verifica("tipi sbagliati segnalati, restano i predefiniti",
         "pc_proprietari" in out.getvalue() and "pc_app" in out.getvalue()
         and c.pc_proprietari == [] and "calcolatrice" in c.pc_app)

# ── chiamata scritta come testo con un valore solo (27/09: pc_cerca_file("chiavi") → {}) ──
from calliope.brain import _parse_args  # noqa: E402

verifica("valore senza nome → primo parametro",
         _parse_args('"chiavi"', ["testo", "tipo", "periodo"]) == {"testo": "chiavi"}
         and _parse_args("paola", ["voce"]) == {"voce": "paola"}
         and _parse_args('testo="chiavi", tipo="pdf"', ["testo", "tipo"])
         == {"testo": "chiavi", "tipo": "pdf"})

# ── nomi dei risultati detti a voce (27/09: «timelog, timelog e timelog») ──
from calliope.tools.pc import _spoken_names  # noqa: E402

nomi = _spoken_names([
    {"nome": "timelog", "estensione": "xlsx", "modificato": "2026-08-06T10:31"},
    {"nome": "timelog", "estensione": "xlsx", "modificato": "2026-08-06T10:30"},
    {"nome": "timelog", "estensione": "csv", "modificato": "2026-08-05T10:23"},
    {"nome": "timelog 2021", "estensione": "csv", "modificato": "2021-11-26T10:19"}])
verifica("nomi uguali distinti da tipo, data e ora", len(set(nomi)) == 4
         and nomi[2] == "timelog csv" and nomi[3] == "timelog 2021"
         and nomi[0] == "timelog xlsx del 6 agosto delle 10:31", str(nomi))

# ── percorso vero da System.ItemUrl (27/09: ItemPathDisplay non esiste sul disco) ──
if sys.platform == "win32":
    from calliope.pc.windows import _url_to_path  # noqa: E402
    from calliope.pc.windows import _is_system  # noqa: E402
    verifica("file di sistema e cartelle nascoste scartati",
             _is_system(r"C:\Users\x\.claude.json", ".claude.json", "json")
             and _is_system(r"C:\Users\x\Desktop\desktop.ini", "desktop.ini", "ini")
             and _is_system(r"C:\Users\x\AppData\Local\a.pdf", "a.pdf", "pdf")
             and _is_system(r"C:\Users\x\.vscode\b.txt", "b.txt", "txt")
             and not _is_system(r"C:\Users\x\Documents\chiavi.csv.xlsx", "chiavi.csv.xlsx", "xlsx"))
    verifica("ItemUrl → percorso",
             _url_to_path("file:C:/Users/x/Documenti%20vari/a.pdf")
             == r"C:\Users\x\Documenti vari\a.pdf" and _url_to_path("mapi://x") == "")

print(f"\n{errori} errori" if errori else "\nTutto a posto.")
sys.exit(1 if errori else 0)
