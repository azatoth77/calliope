"""
Prova a secco del «sì» breve per le azioni importanti, in ombra (15/10/2026, roadmap 2.6, voce
E6; calliope/si_breve.py).

Solo la misura, nessun effetto: per ogni chiamata eseguita dal registro dei tool, se è un'azione
importante (E3–E4, sfida nella classe, pericolosa) o la conferma di una proposta, una riga nel
turno con il modo (voce, sì breve compatibile, sì breve, zona grigia, sfida, scritto) e i rischi
(compagnia, voci sconosciute, voce incerta, senza il nome). Casi: il «sì» breve di chi amministra
(il caso vero del 04/10), il «sì» breve di un familiare con la politica, la sfida superata, la
richiesta nuova con la voce. Contrari: azione E1 senza proposta, lettura, chiamata rifiutata,
righe di una risposta vecchia, misura che si rompe (il tool parte lo stesso). Poi il riassunto
(sfide accoppiate sullo stesso satellite entro 120 s, contrari: altro satellite, troppo tardi),
il costo dell'alternativa e la sezione di `calliope stato --turni` (testo e JSON). ~1 s.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# La cartella del registro per `calliope stato --turni` (punto 11): la configurazione la legge
# all'import, quindi prima di importare calliope
TMP = Path(tempfile.mkdtemp(prefix="calliope-si-breve-"))
os.environ["CALLIOPE_TURN_LOG"] = str(TMP)

from calliope import politica, si_breve as S, valore
from calliope.config import Config
from calliope.speaker_id import SpeakerContext
from calliope.tools.registry import ToolRegistry
from calliope.tools.spec import ToolContext, ToolSpec

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + ("" if ok else f"  → {dettaglio}"))


class Prof:
    def __init__(self, nome, admin=False):
        self.name, self.id, self.admin = nome, nome.lower() + "-id", admin


class Persone:
    def __init__(self):
        self.cfg = Config()
        self.users = {"Ada": Prof("Ada", True), "Bruno": Prof("Bruno")}

    def get(self, n):
        return self.users.get(n)


def frase(sc, nome, come, punteggio=0.7, in_session=True):
    sc.identified_by = come
    sc.from_session = come in ("breve", "conversazione")
    sc.current_speaker = nome
    sc.aggiorna_conversazione(nome, come, in_session, punteggio)


def registro():
    reg, fatti = ToolRegistry(), []

    def fa(ctx, **a):
        fatti.append(a)
        return {"ok": True, "conferma": "Fatto."}

    # un'azione di chi amministra senza classe dichiarata: vale pericolosa (importante)
    reg.register(ToolSpec(name="azione_admin", description="", parameters={}, func=fa,
                          risk="azione", levels=frozenset({"amministra"})))
    # un'azione di famiglia E3 e una E1 (luce), con la classe «azione»
    e3 = ToolSpec(name="azione_casa", description="", parameters={}, func=fa, risk="azione",
                  levels=frozenset({"familiare", "amministra"}), classe="azione")
    e1 = ToolSpec(name="luce_prova", description="", parameters={}, func=fa, risk="azione",
                  levels=frozenset({"familiare", "amministra"}), classe="azione")
    e1.effetto = valore.E1
    e3.effetto = valore.E3
    reg.register(e3)
    reg.register(e1)
    reg.register(ToolSpec(name="leggi_prova", description="", parameters={}, func=fa,
                          levels=frozenset({"ospite", "familiare", "amministra"}),
                          classe="sicuro"))
    return reg, fatti


p = Persone()
sc = SpeakerContext(p)
ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=sc, speaker=None)
reg, fatti = registro()


def chiama(nome, testo="", sospeso=None, politica_turno=None, turno=1):
    ctx.turno, ctx.user_text, ctx.tool_in_sospeso = turno, testo, sospeso
    ctx.politica, ctx.regole = politica_turno, []
    ctx.si_breve.clear()
    out = json.loads(reg.call(nome, {}, ctx, sc.current_level))
    return out, S.del_turno(ctx)


# 1. Il caso vero del 04/10: «Sì, procedi pure.» (0,9 s, 0,515) di chi amministra al tool proposto
frase(sc, "Ada", "voce", 0.71, in_session=False)
frase(sc, "Ada", "breve", 0.515)
out, righe = chiama("azione_admin", "Sì, procedi pure.", sospeso="azione_admin")
r = righe[0] if righe else {}
verifica("sì breve compatibile di chi amministra: eseguito come prima",
         out.get("ok") is True and "conferma_breve" in ctx.regole and len(fatti) == 1, out)
verifica("… e misurato: importante, conferma, modo breve_compatibile, punteggio, 3 parole",
         r.get("importante") and r.get("conferma") and r.get("modo") == "breve_compatibile"
         and r.get("punteggio") == 0.515 and r.get("parole") == 3
         and r.get("solo_amministra") is True and "_turno" not in r, righe)
verifica("… la frase resta «breve» dopo la chiamata (la misura non cambia niente)",
         sc.identified_by == "breve" and sc.current_level == "familiare")

# 2. Contrario: la stessa frase breve per un tool non proposto → sfida, nessuna riga
fatti.clear()
out, righe = chiama("azione_admin", "Sì.", sospeso=None)
verifica("contrario: sì breve per un tool non proposto → sfida come prima, nessuna riga",
         not fatti and "ripeti:" in str(out.get("risposta_finale")) and righe == [], (out, righe))
sc.sfida = None

# 3. La sfida superata (la frase intera dopo «ripeti: …»)
frase(sc, "Ada", "voce", 0.72)
sc.sfida_superata = True
out, righe = chiama("azione_admin", "girasole castello foresta quarantadue",
                    sospeso="azione_admin")
verifica("sfida superata: modo sfida, conferma", out.get("ok") and righe
         and righe[0]["modo"] == "sfida" and righe[0]["conferma"]
         and righe[0]["forma_chiusa"] is False, righe)
sc.sfida_superata = False

# 4. Richiesta nuova con la voce piena: importante, non una conferma
frase(sc, "Ada", "voce", 0.72)
out, righe = chiama("azione_admin", "Esegui il lavoro di pulizia dei file vecchi adesso")
verifica("richiesta nuova con la voce: importante, conferma no, modo voce",
         out.get("ok") and righe and righe[0]["modo"] == "voce"
         and righe[0]["conferma"] is False, righe)

# 5. Il «sì» breve di un familiare a un'azione E3 proposta dal modello (politica con il turno)
frase(sc, "Bruno", "voce", 0.7, in_session=False)
frase(sc, "Bruno", "breve", 0.5)
t = politica.Turno(testo="Sì.", in_sospeso="azione_casa")
fatti.clear()
out, righe = chiama("azione_casa", "Sì.", sospeso="azione_casa", politica_turno=t)
verifica("familiare, sì breve a un'azione E3: eseguita come prima e misurata (breve, forma chiusa)",
         out.get("ok") and fatti and righe and righe[0]["modo"] == "breve"
         and righe[0]["effetto"] == "E3" and righe[0]["conferma"]
         and righe[0]["forma_chiusa"] is True and righe[0]["solo_amministra"] is False,
         (out, righe))

# 6. Contrari: E1 senza proposta, lettura → nessuna riga; E1 confermata → riga non importante
frase(sc, "Bruno", "voce", 0.7)
out, righe = chiama("luce_prova", "accendi la luce della prova")
verifica("contrario: azione E1 chiesta, senza proposta → nessuna riga", out.get("ok") and righe == [],
         righe)
out, righe = chiama("leggi_prova", "che ore sono")
verifica("contrario: una lettura → nessuna riga", out.get("ok") and righe == [], righe)
frase(sc, "Bruno", "breve", 0.5)
t = politica.Turno(testo="Sì, grazie.", in_sospeso="luce_prova")
out, righe = chiama("luce_prova", "Sì, grazie.", sospeso="luce_prova", politica_turno=t)
verifica("E1 confermata con un sì breve: riga con importante falso (il denominatore)",
         righe and righe[0]["importante"] is False and righe[0]["conferma"]
         and righe[0]["effetto"] == "E1", righe)

# 7. Contrario: chiamata rifiutata per permessi (un ospite) → nessuna riga
frase(sc, None, None, 0.1, in_session=False)
out, righe = chiama("azione_casa", "Sì.", sospeso="azione_casa")
verifica("contrario: chiamata rifiutata (ospite) → nessuna riga", out.get("ok") is False
         and righe == [], (out, righe))

# 8. I rischi: senza il nome con la proposta (eccezione della compagnia), e misura diretta
frase(sc, "Bruno", "voce", 0.7, in_session=False)
frase(sc, "Bruno", "breve", 0.5)
sc.senza_nome = True
t = politica.Turno(testo="Va bene.", in_sospeso="azione_casa")
out, righe = chiama("azione_casa", "Va bene.", sospeso="azione_casa", politica_turno=t)
verifica("rischio senza_nome nella riga", righe and righe[0].get("rischi") == ["senza_nome"],
         righe)
sc.senza_nome = False


class Finto:
    identified_by, from_session, current_speaker = "conversazione", True, "Ada"
    compagnia, compagnia_sconosciute, incerta, minore_vicino = True, True, ("Ada", "Cleo"), None
    senza_nome, sfida_superata, punteggio = False, False, 0.33


c2 = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=Finto(), speaker=None)
c2.user_text = "sì"
r = S.misura(reg._tools["azione_admin"], "azione_admin", {}, c2, breve=False)
verifica("zona grigia in compagnia con voci sconosciute e voce incerta: tutti i rischi",
         r and r["modo"] == "zona_grigia"
         and r["rischi"] == ["compagnia", "voci_sconosciute", "incerta"], r)
verifica("modo: scritto, nessuno", S.modo(type("X", (), {"identified_by": "schermo",
                                                          "current_speaker": None})(), False)
         == "scritto" and S.modo(None, False) == "nessuno")

# 9. Le righe di una risposta vecchia non passano alla dopo; una misura rotta non ferma il tool
ctx.si_breve[:] = [{"tool": "x", "_turno": 7}]
ctx.turno = 8
verifica("contrario: righe di un'altra risposta scartate e lista svuotata",
         S.del_turno(ctx) == [] and ctx.si_breve == [])
vero = valore.effetto
valore.effetto = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rotta"))
try:
    frase(sc, "Ada", "voce", 0.72, in_session=False)
    fatti.clear()
    out, righe = chiama("azione_admin", "Esegui il lavoro adesso")
finally:
    valore.effetto = vero
verifica("misura rotta: il tool parte lo stesso, nessuna riga", out.get("ok") and fatti
         and righe == [], (out, righe))

# 9 bis. Con Brain: la sfida superata passa dal registro e la riga è della risposta in corso
import time

from calliope import conferme as C
from calliope.brain import Brain

b = Brain.__new__(Brain)
reg_b, fatti_b = registro()
b.cfg, b.tools, b.history = p.cfg, reg_b, []
b.tool_ctx = ToolContext(cfg=p.cfg, speakers=p, speaker_ctx=SpeakerContext(p), speaker=None)
b.backend = None
frase(b.tool_ctx.speaker_ctx, "Ada", "voce", 0.68)
s = C.nuova_sfida(p.cfg, "ada-id", "azione_admin", {})
s.parole, s.numero, s.scade = ("girasole", "castello", "foresta"), 42, time.monotonic() + 60
b.tool_ctx.speaker_ctx.sfida = s
detto = "".join(b.stream_reply("Girasole, castello, foresta, quarantadue.", "amministra"))
righe = S.del_turno(b.tool_ctx)
verifica("Brain: sfida superata eseguita come prima, una riga «sfida» per il registro",
         fatti_b == [{}] and detto == "Fatto." and len(righe) == 1
         and righe[0]["modo"] == "sfida" and righe[0]["conferma"], (detto, righe))

# 10. Riassunto e testo
G = "2026-10-15"


def tr(ora, sat="studio", regole=(), righe=None):
    d = {"inizio": f"{G}T{ora}", "esito": "risposta", "satellite": sat, "regole": list(regole)}
    if righe is not None:
        d[S.CAMPO] = righe
    return d


def rg(modo, importante=True, conferma=True, rischi=(), chiusa=True, tool="azione_admin"):
    x = {"tool": tool, "effetto": "E3", "importante": importante, "conferma": conferma,
         "modo": modo, "parole": 1, "forma_chiusa": chiusa}
    if rischi:
        x["rischi"] = list(rischi)
    return x


turni = [
    tr("10:00:00", righe=[rg("breve_compatibile")]),
    tr("10:01:00", righe=[rg("breve", rischi=["compagnia", "voci_sconosciute"], chiusa=False,
                             tool="azione_casa")]),
    tr("10:02:00", righe=[rg("zona_grigia", rischi=["incerta"])]),
    tr("10:03:00", righe=[rg("voce"), rg("voce", conferma=False)]),
    tr("10:04:00", righe=[rg("breve", importante=False)]),
    # una sfida vera: chiesta alle 10:10:00, risposta alle 10:10:12 sullo stesso satellite
    tr("10:10:00", regole=["sfida_voce"]),
    tr("10:10:05", sat="cucina"),                        # contrario: altro satellite in mezzo
    tr("10:10:12", regole=["sfida_risposta"], righe=[rg("sfida")]),
    # contrario: risposta troppo tardi (oltre 120 s)
    tr("10:20:00", regole=["sfida_voce"]),
    tr("10:23:00", regole=["sfida_risposta"]),
    tr("10:30:00"),                                       # un turno senza la misura
]
R = S.riassunto(turni)
verifica("riassunto: conferme importanti per modo",
         R["conferme_importanti"] == 5 and R["per_modo"]["breve_compatibile"] == 1
         and R["per_modo"]["breve"] == 1 and R["per_modo"]["zona_grigia"] == 1
         and R["per_modo"]["voce"] == 1 and R["per_modo"]["sfida"] == 1, R)
verifica("riassunto: brevi, forma chiusa e rischi",
         R["brevi"] == 3 and R["brevi_forma_chiusa"] == 2 and R["brevi_con_rischio"] == 2
         and R["brevi_rischi"]["compagnia"] == 1 and R["brevi_rischi"]["incerta"] == 1
         and R["brevi_tool"] == {"azione_admin": 2, "azione_casa": 1}, R)
verifica("sfide: una sola accoppiata (12 s), contrari altro satellite e troppo tardi",
         S.tempi_sfida(turni) == [12.0] and R["sfide_chieste"] == 2
         and R["sfida_s_mediana"] == 12.0, S.tempi_sfida(turni))
verifica("alternativa: 3 domande in più, 36 s", R["alternativa_domande"] == 3
         and R["alternativa_s"] == 36.0, R)
txt = S.testo(R)
verifica("testo: le righe per lo stato", "«Sì» breve per le azioni importanti" in txt
         and "sì breve compatibile 1" in txt and "domande in più" in txt
         and "circa 36 s" in txt and "voci sconosciute 1" in txt, txt)
verifica("contrario: registro senza la misura → una riga",
         "nessun turno con la misura" in S.testo(S.riassunto([tr("09:00:00")])))
verifica("senza sfide misurate: il tempo non si inventa",
         S.riassunto([tr("09:00:00", righe=[rg("breve")])])["alternativa_s"] is None
         and "non ancora misurato" in S.testo(S.riassunto([tr("09:00:00", righe=[rg("breve")])])))

# 11. In `calliope stato --turni`
try:
    (TMP / f"turni-{G}.jsonl").write_text("\n".join(json.dumps(x) for x in turni) + "\n",
                                          encoding="utf-8")
    from calliope import stato
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = stato.main(["--turni"])
    verifica("calliope stato --turni: la sezione del sì breve",
             rc == 0 and "«Sì» breve per le azioni importanti" in out.getvalue()
             and "domande in più" in out.getvalue(), out.getvalue()[-800:])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        stato.main(["--turni", "--json"])
    j = json.loads(out.getvalue()[out.getvalue().index("{"):])
    verifica("--json: si_breve", j["si_breve"]["conferme_importanti"] == 5, j.get("si_breve"))
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n{'Tutto ok' if not errori else f'{errori} errori'}")
sys.exit(1 if errori else 0)
