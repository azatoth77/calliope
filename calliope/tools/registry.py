"""
Registro dei tool nativi: elenco per il modello, permessi per livello, esecuzione.

Dal 03/10 il modello vede **lo stesso elenco di tool per tutti i livelli** (`schemas`): con
un elenco per livello, quando cambiava chi parla Ollama doveva rileggere ~6000 token di
prefisso (+1,5 s col 4B, +2 s col 26B; docs/ricerche/2026-10-03-modello-davanti.md). I
permessi restano nel codice: `call` ricontrolla il livello a ogni esecuzione e rifiuta con
una frase pronta (`risposta_finale`), senza un'altra passata del modello.
Senza rete i tool con requires_internet spariscono dall'elenco (principio 5).
"""

import json

from .. import politica
from ..conferme import admin_confermato, chiedi_conferma, e_admin, incerta_con_admin
from . import dialogo
from .spec import ToolSpec, ToolContext, note_rule, serve_la_voce
from ..testi import NIENTE

# Rifiuto per permessi, detto così com'è (risposta_finale): gentile, e senza un'altra
# passata del modello che potrebbe dire «ho registrato…» lo stesso (prova del 26/09)
REFUSAL = {
    "ospite": "Mi dispiace, questo posso farlo solo per chi vive in casa, e la tua voce non "
              "la riconosco.",
    "familiare": "Mi dispiace, questo può chiederlo solo chi amministra Calliope.",
}
# In compagnia (09/10, calliope/compagnia.py) un'azione vuole la voce riconosciuta nella frase
COMPAGNIA_RIPETI = ("Ci sono altre voci qui vicino e non sono sicura di chi parla: ripetimelo "
                    "con una frase un po' più lunga, cominciando con il mio nome.")
# Una frase breve (meno di un secondo di voce) vale al più come familiare. Per chi amministra
# con una frase che non basta, dal 04/10 la frase di sfida (conferme.chiedi_conferma), non più
# «dimmelo con una frase un po' più lunga» del 03/10

# Nome di un tool storpiato dal modello (prova e2e del 06/10, variante B2: «richesta_tutore»
# per «richiesta_tutore», la richiesta del minore non partiva e il modello diceva lo stesso
# «glielo chiedo»). Entro questa distanza, con un solo tool così vicino, vale quel tool
# (regola `tool_nome_corretto`); oltre, l'errore dice i nomi più vicini
# I nomi di prima del 08/10 (modalità sviluppo, versione 2: nome singolare + verbo, prefisso per
# famiglia): una conversazione o un'azione in sospeso di prima, o il modello che li ripesca dalla
# storia, valgono come il tool nuovo, con tutti i controlli (regola `tool_nome_vecchio`)
NOMI_VECCHI = {
    "delega_lavoro": "lavoro_affida", "lavori_stato": "lavoro_stato",
    "lavori_annulla": "lavoro_annulla", "lavori_rispondi": "lavoro_rispondi",
    "risultato_lavoro": "lavoro_risultato", "lavori_esegui": "programma_esegui",
    "estensione_crea": "sviluppo_apri", "estensioni_gestisci": "estensione_gestisci",
    "sviluppo": "sviluppo_passo", "sviluppo_prova": "sviluppo_collauda",
}
NOME_DISTANZA_MAX = 2
NOME_LUNGHEZZA_MIN = 6
NOME_SUGGERIMENTI_MAX = 4


def distanza(a: str, b: str, limite: int = 99) -> int:
    """Distanza di edit (inserzioni, cancellazioni, sostituzioni e scambi di due lettere
    vicine, Damerau ristretta), troncata a `limite` + 1 per i nomi molto diversi."""
    if abs(len(a) - len(b)) > limite:
        return limite + 1
    prima, riga = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        nuova = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            nuova[j] = min(riga[j] + 1, nuova[j - 1] + 1, riga[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                nuova[j] = min(nuova[j], prima[j - 2] + 1)
        prima, riga = riga, nuova
        if min(riga) > limite:
            return limite + 1
    return riga[-1]


def _segna_registro(ctx):
    """L'errore viene dal codice di Calliope (validazione o eccezione), non dal tool: Brain non
    lo mette nella busta dei dati non fidati (ToolContext.errore_registro, 09/10)."""
    try:
        ctx.errore_registro = True
    except AttributeError:
        pass


def _contratto(spec) -> bool:
    """Lo schema è il contratto del tool (le estensioni: il manifesto), anche se la funzione
    prende soli **kw: gli obbligatori mancano davvero se assenti (09/10)."""
    return getattr(spec, "fonte", None) == "estensione"


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        # Cresce a ogni registrazione o rimozione: chi tiene i nomi dei tool in memoria
        # (Brain.mentions_tool, uno per satellite dal 06/10) sa quando rileggerli
        self.versione = 0

    def register(self, spec: ToolSpec):
        self._tools[spec.name] = spec
        self.versione += 1

    def unregister(self, name: str):
        """Toglie un tool (un'estensione disattivata o rimossa, 04/10)."""
        self._tools.pop(name, None)
        self.versione += 1

    def schemas(self, online: bool = True) -> list[dict]:
        """Gli schemi che vede il modello: tutti i tool, uguali per ogni livello, in ordine
        di registrazione. Così il prefisso (prompt di sistema + tool) resta in cache anche
        quando cambia chi parla; i permessi li controlla `call`."""
        return [t.schema() for t in self._tools.values()
                if online or not t.requires_internet]

    def allowed(self, name: str, level: str) -> bool:
        """`level` può usare il tool `name`?"""
        spec = self._tools.get(name)
        return spec is not None and level in spec.levels

    def schemas_for(self, level: str, online: bool = True) -> list[dict]:
        """Gli schemi dei tool **ammessi** a quel livello (i permessi, per le prove e gli
        script di misura). Non è l'elenco del modello: quello è `schemas`, uguale per tutti."""
        return [t.schema() for t in self._tools.values()
                if level in t.levels and (online or not t.requires_internet)]

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def vicini(self, name: str, limite: int = NOME_DISTANZA_MAX + 2) -> list[tuple[int, str]]:
        """I tool con un nome entro `limite` da `name` (distanza, nome), i più vicini prima."""
        n = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
        out = []
        for vero in self._tools:
            d = distanza(n, vero, limite)
            if d <= limite:
                out.append((d, vero))
        return sorted(out)

    def nome_vicino(self, name: str) -> str | None:
        """Il tool che il modello intendeva con un nome che non esiste, se non ci sono dubbi:
        a distanza 1–2 (maiuscole, trattini e spazi a parte), l'unico così vicino, nomi di
        almeno `NOME_LUNGHEZZA_MIN` lettere. Altrimenti None (anche per un nome esatto)."""
        if not name or name in self._tools or len(str(name)) < NOME_LUNGHEZZA_MIN:
            return None
        entro = [(d, v) for d, v in self.vicini(name, NOME_DISTANZA_MAX)
                 if len(v) >= NOME_LUNGHEZZA_MIN]
        return entro[0][1] if len(entro) == 1 else None

    def sconosciuto(self, name: str) -> str:
        """L'errore per un tool che non c'è: niente è stato eseguito e, se ci sono, i nomi
        giusti più vicini (con un solo nome vicino il modello riprova con quello)."""
        vicini = [v for _, v in self.vicini(name)][:NOME_SUGGERIMENTI_MAX]
        out = {"errore": f"tool sconosciuto: {name}", "ok": False, "fatto": NIENTE}
        if vicini:
            out["nomi_giusti"] = vicini
            out["cosa_fare"] = ("se intendevi uno di questi, chiamalo con il nome esatto; "
                                "per le altre richieste chiama i tool come sempre")
        return json.dumps(out, ensure_ascii=False)

    def mancanti(self, name: str, arguments) -> list[str]:
        """Gli argomenti che impediscono la chiamata (Brain non dice la frase d'attesa di un
        tool che non parte; `call` risponde subito con l'errore). Dal 06/10: una chiamata
        senza nessun argomento (`conversazione_cerca({})`) ha tutti i `required` mancanti.
        Dal 09/10 (tools/dialogo.py) anche un obbligatorio assente o vuoto che la funzione non
        sa completare da sola (`web_cerca({'tipo': 'notizie'})`), un valore fuori dai valori
        ammessi o del tipo sbagliato, un argomento che la funzione non conosce. Gli
        obbligatori con un valore predefinito nella funzione restano ai tool, che li
        completano (la proposta in sospeso di lavoro_affida, l'esercizio di compiti_aiuto)."""
        spec = self._tools.get(name)
        if spec is None:
            vero = NOMI_VECCHI.get(name) or self.nome_vicino(name)
            spec = self._tools.get(vero) if vero else None
        if spec is None:
            return []
        _, _, err = dialogo.controlla(spec.name, spec.parameters, arguments, spec.func,
                                      spec.description, _contratto(spec))
        if err is None:
            return []
        return list(err.get("argomenti") or ()) or ["argomenti"]

    def controlla(self, spec: ToolSpec, arguments, ctx=None):
        """(argomenti in forma, errore o None) di una chiamata a `spec` (tools/dialogo.py):
        le conversioni di forma restano nel registro dei turni (`tool_argomento_forma`)."""
        args, convertiti, err = dialogo.controlla(
            spec.name, spec.parameters, arguments, spec.func, spec.description,
            _contratto(spec), frase=str(getattr(ctx, "user_text", "") or ""))
        if convertiti and ctx is not None:
            note_rule(ctx, "tool_argomento_forma")
        return args, err

    def announcements(self) -> list[str]:
        """Tutte le frasi di annuncio dei tool, da sintetizzare in anticipo, con quelle dei
        giri di correzione (dialogo.FRASI_CORREZIONE, 09/10)."""
        return ([p for t in self._tools.values() for p in t.announce]
                + list(dialogo.FRASI_CORREZIONE))

    def all_schemas(self) -> list[dict]:
        """Gli schemi di tutti i tool, senza filtro: servono a riconoscerne i nomi."""
        return [t.schema() for t in self._tools.values()]

    def call(self, name: str, arguments: dict, ctx: ToolContext,
             level: str | None = None) -> str:
        """Esegue un tool e restituisce JSON. Un errore non solleva eccezioni verso
        il modello: torna come risultato che il modello può leggere.

        Con `level` il permesso si controlla qui, a ogni esecuzione: dal 03/10 il modello
        vede tutti i tool a ogni livello (e potrebbe comunque ripescarne il nome dalla
        storia o scriverlo come testo). Il rifiuto ha una frase pronta e chiude il turno.
        """
        spec = self._tools.get(name)
        if spec is None and self._tools.get(NOMI_VECCHI.get(name, "")) is not None:
            note_rule(ctx, "tool_nome_vecchio")
            name = NOMI_VECCHI[name]
            spec = self._tools[name]
        if spec is None:
            # Nome storpiato ma senza dubbi: vale il tool giusto, con tutti i controlli qui
            # sotto (politica, livello, minori) come se il modello l'avesse scritto bene
            vero = self.nome_vicino(name)
            if vero is None:
                return self.sconosciuto(name)
            note_rule(ctx, "tool_nome_corretto")
            name, spec = vero, self._tools[vero]
        if getattr(spec, "prepara", None) is not None:
            # La forma degli argomenti (ToolSpec.prepara), prima di permessi e politica
            try:
                arguments = spec.prepara(ctx, dict(arguments or {})) or arguments
            except Exception:  # noqa: BLE001 — nel dubbio, gli argomenti come sono
                pass
        sc = getattr(ctx, "speaker_ctx", None)
        # Dopo un dato non fidato letto in questa risposta, solo letture (politica.DOPO_DATO)
        fermo = politica.bloccata(name, ctx, arguments)
        if fermo is not None:
            return json.dumps(fermo, ensure_ascii=False)
        # Un'azione su un bersaglio che non c'è («scollega lo schermo della cucina» senza
        # schermi in cucina): lo si dice, senza domande né sfide (06/10, e2e)
        fermo = politica.bersaglio_assente(spec, name, arguments or {}, ctx)
        if fermo is not None:
            return json.dumps(fermo, ensure_ascii=False)
        # Un'azione distruttiva incoerente con la frase («ripristina lo schermo» → scollega):
        # prima di tutto, anche della sfida (politica.incoerente, 05/10)
        fermo = politica.incoerente(spec, name, arguments or {}, ctx)
        if fermo is not None:
            return json.dumps(fermo, ensure_ascii=False)
        # «Sì» breve di chi amministra al tool proposto, in una conversazione in cui la sua
        # voce era già stata riconosciuta e con l'impronta compatibile (conferme.py): per
        # questo tool, e solo per lui, vale come la sua voce
        breve = (level is not None and getattr(sc, "identified_by", None) == "breve"
                 and name == getattr(ctx, "tool_in_sospeso", None) and admin_confermato(ctx))
        if breve:
            note_rule(ctx, "conferma_breve")
            level = "amministra"
        # In compagnia (09/10, calliope/compagnia.py): altre voci vicino al satellite, e la voce
        # di questa frase è solo nella zona grigia (o vale il profilo più protetto). Le azioni
        # che vogliono un livello vogliono la voce riconosciuta nella frase: qui vale ospite
        # (chi amministra riceve la frase di sfida, gli altri la richiesta di ripetere)
        compagnia = (level not in (None, "ospite") and "ospite" not in spec.levels
                     and getattr(sc, "compagnia", False)
                     and getattr(sc, "identified_by", None) in ("breve", "conversazione"))
        if compagnia:
            note_rule(ctx, "compagnia_voce_nella_frase")
            if (not ("amministra" in spec.levels and e_admin(ctx))
                    and incerta_con_admin(ctx) is None):
                return json.dumps({"ok": False, "fatto": NIENTE,
                                   "motivo": "in compagnia la voce di questa frase non basta",
                                   "per_il_resto": "per le altre richieste chiama i tool come "
                                                   "sempre",
                                   "conferma": COMPAGNIA_RIPETI,
                                   "risposta_finale": COMPAGNIA_RIPETI}, ensure_ascii=False)
            level = "ospite"
        if level is not None and level not in spec.levels:
            # Chi amministra, ma questa frase non basta (breve incerta, zona grigia): la frase
            # di sfida, mai «chiedi a chi amministra» (04/10)
            if ("amministra" in spec.levels and e_admin(ctx)
                    and getattr(sc, "identified_by", None) in ("breve", "conversazione")):
                return json.dumps(chiedi_conferma(ctx, name, arguments, politica.da_confermare(
                    name, arguments or {}, spec)), ensure_ascii=False)
            # Voce incerta tra chi amministra e un minore (07/10, vale il minore): la sfida per
            # chi amministra, con la frase che chiede chi parla, invece del rifiuto secco
            incerta = incerta_con_admin(ctx) if "amministra" in spec.levels else None
            if incerta is not None and not e_admin(ctx):
                return json.dumps(chiedi_conferma(ctx, name, arguments, politica.da_confermare(
                    name, arguments or {}, spec), incerta=incerta), ensure_ascii=False)
            # Scritto da uno schermo personale di chi, a voce, avrebbe il permesso: si chiede
            # la conferma a voce invece del rifiuto (03/10)
            sc = getattr(ctx, "speaker_ctx", None)
            if getattr(sc, "profile_level", None) in spec.levels:
                voce = serve_la_voce(ctx, name, arguments, "questa richiesta",
                                     getattr(sc, "profile_level", "amministra"))
                if voce is not None:
                    return json.dumps(voce, ensure_ascii=False)
            note_rule(ctx, "permesso_livello")
            said = REFUSAL.get(level, REFUSAL["familiare"])
            # «fatto» formulato perché il modello non possa fraintenderlo, e il resto in
            # positivo: un tool fallito non deve far smettere di chiamare gli altri (26/09)
            return json.dumps({"ok": False, "fatto": NIENTE,
                               "motivo": "chi sta parlando non ha il permesso"
                                         + (" (voce non riconosciuta)" if level == "ospite"
                                            else " (serve chi amministra)"),
                               "per_il_resto": "per le altre richieste chiama i tool come "
                                               "sempre",
                               "conferma": said, "risposta_finale": said},
                              ensure_ascii=False)
        # Minori (05/10, calliope/minori.py): il preset della fascia, nel codice, dopo il livello
        if level is not None:
            from .. import minori
            no = minori.permesso(ctx, name, arguments or {})
            if no is not None:
                return json.dumps(no, ensure_ascii=False)
        # Argomenti contro lo schema (06/10 i mancanti, 09/10 tutto: tools/dialogo.py): niente
        # esecuzione, l'errore strutturato subito al modello, che richiama il tool corretto o
        # chiede il dato alla persona (giro di correzione in Brain, `correggibile`)
        arguments, err = self.controlla(spec, arguments, ctx)
        if err is not None:
            solo_mancanti = (err["errore"].startswith(f"{spec.name} non è partito: manca")
                             and ";" not in err["errore"])
            note_rule(ctx, "tool_argomenti_mancanti" if solo_mancanti
                      else "tool_argomenti_non_validi")
            _segna_registro(ctx)
            return dialogo.come_json(err)
        # Politica unica (05/10, calliope/politica.py): classe del tool, azione chiesta in
        # questo turno, conversazione con dati non fidati, provenienza degli argomenti. Qui,
        # nell'esecutore: il modello non la scavalca e un canale nuovo non la dimentica
        fermo = politica.controlla(spec, name, arguments or {}, ctx)
        if fermo is not None:
            return json.dumps(fermo, ensure_ascii=False)
        prima = (getattr(sc, "identified_by", None), getattr(sc, "from_session", False))
        if breve:
            sc.identified_by, sc.from_session = "voce", False   # solo durante questa chiamata
        try:
            result = spec.func(ctx, **(arguments or {}))
            if result is None:
                result = {"ok": True}
            return json.dumps(dialogo.uniforma(result), ensure_ascii=False, default=str)
        except Exception as e:  # noqa: BLE001 — l'errore torna al modello, mai la traccia
            # Gli argomenti sono già stati controllati: un'eccezione qui è del tool (09/10:
            # prima un TypeError interno diventava «argomenti non validi» con la traccia)
            print(f"   [TOOL] {name} si è fermato: {type(e).__name__}: {e}", flush=True)
            note_rule(ctx, "tool_errore_interno")
            _segna_registro(ctx)
            return dialogo.come_json(dialogo.errore_interno(name, e))
        finally:
            if breve:
                sc.identified_by, sc.from_session = prima
            politica._segna_accettata(ctx, False)
