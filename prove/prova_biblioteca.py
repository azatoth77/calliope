import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Biblioteca offline: banco di domande dette a voce.

    python prove\\prova_biblioteca.py            # a secco: recall@3 e latenza della ricerca
    python prove\\prova_biblioteca.py --ollama   # anche end-to-end con Brain su Ollama,
                                                 # con e senza biblioteca
Se il file ZIM mini non c'è la prova salta (esce con 0). Rapporti:
docs/ricerche/2026-09-26-biblioteca-prova.md e, per il passaggio da libzim a SQLite FTS5,
docs/ricerche/2026-10-01-biblioteca-senza-libzim.md (banco nuovo da 46 domande).
"""

import re
import statistics
import time
from pathlib import Path

from calliope.config import Config

# (domanda come arriva da Whisper, regex della risposta giusta; None = la biblioteca
# non serve, e allora il secondo campo è il tool atteso o None)
BANCO = [
    # geografia
    ("Quanto è alto il Monte Bianco?", r"48[0-9]{2}|4[ .]8[0-9]{2}"),
    ("Qual è la capitale dell'Australia?", r"Canberra"),
    ("Quanto è lungo il Po?", r"65[12]"),
    ("Qual è il lago più grande d'Italia?", r"Garda"),
    ("Quanti abitanti ha Milano?", r"1[ .,]?3[0-9]{2}|1,[34] milion"),
    ("Qual è la capitale del Canada?", r"Ottawa"),
    ("In che stato si trova il Kilimangiaro?", r"Tanzania"),
    ("Qual è la montagna più alta del mondo?", r"Everest"),
    ("In che regione si trova Matera?", r"Basilicata"),
    ("Qual è il fiume più lungo del mondo?", r"Nilo|Rio delle Amazzoni|Amazzoni"),
    # storia
    ("In che anno è caduto il muro di Berlino?", r"1989"),
    ("Quando è nato Giulio Cesare?", r"10[012] a\.? ?C|12 luglio"),
    ("In che anno Cristoforo Colombo arrivò in America?", r"1492"),
    ("Chi è stato il primo presidente della Repubblica italiana?", r"De Nicola|Einaudi"),
    ("Quando è finita la seconda guerra mondiale?", r"1945"),
    ("Chi ha scritto la Divina Commedia?", r"Dante"),
    ("In che anno è morto Napoleone?", r"1821"),
    ("Chi ha dipinto la Gioconda?", r"Leonardo"),
    ("Quando è stata fondata Roma?", r"753"),
    ("Chi ha scritto I promessi sposi?", r"Manzoni"),
    # scienza
    ("Chi ha scoperto la penicillina?", r"Fleming"),
    ("Qual è il simbolo chimico del sodio?", r"\bNa\b"),
    ("Quanti pianeti ci sono nel sistema solare?", r"\botto\b|\b8\b"),
    ("Qual è la formula chimica dell'acqua?", r"H2O|H₂O"),
    ("Quanto dista la Luna dalla Terra?", r"38[0-9][ .]?[0-9]{3}|384"),
    ("Qual è la velocità della luce?", r"299[ .]?792|300[ .]?000|300 mila"),
    ("Chi ha formulato la teoria della relatività?", r"Einstein"),
    ("Qual è il numero atomico dell'ossigeno?", r"\b8\b|\botto\b"),
    ("Qual è il pianeta più grande del sistema solare?", r"Giove"),
    ("Cos'è la fotosintesi?", r"luce|clorofill|anidride carbonica|zucchero|glucosio"),
    # compiti di un ragazzo di 14 anni
    ("Cos'è un'iperbole?", r"esager|figura retorica|curva|conica"),
    ("Chi era Giuseppe Garibaldi?", r"generale|patriota|Mille|Risorgimento|condottiero"),
    ("Quanto è grande la superficie dell'Italia?", r"30[12][ .]?[0-9]{3}|302"),
    ("Cos'è il teorema di Pitagora?", r"cateti|ipotenusa|triangolo rettangolo"),
    # con errori di trascrizione tipici di Whisper
    ("Quanto è alto il monte bianko?", r"48[0-9]{2}|4[ .]8[0-9]{2}"),
    ("Chi a scritto la divina comedia?", r"Dante"),
    ("Qual è la capitale della Spana?", r"Madrid"),
    ("In che anno e caduto il muro di berlino", r"1989"),
    # la biblioteca non serve
    ("Raccontami una barzelletta.", None, None),
    ("Che ore sono?", None, "ora_attuale"),
    ("Quanto fa 17 per 6?", None, "calcola"),
    ("Come stai?", None, None),
    ("Mi consigli un film da vedere stasera?", None, None),
]

# Fatti meno noti e numeri precisi: dove un modello da 4B sbaglia più spesso. Sulle
# domande da manuale qui sopra, senza biblioteca, il modello rispondeva già 41 su 43.
BANCO_DIFFICILE = [
    ("Quanto è alto il Gran Sasso?", r"2[ .]?912"),
    ("Quanti abitanti ha Matera?", r"\b5[0-9][ .]?[0-9]{3}\b"),
    ("In che anno è nato Alessandro Manzoni?", r"1785"),
    ("Quanto è lungo il Tevere?", r"40[0-9]"),
    ("Chi ha scoperto il neutrone?", r"Chadwick"),
    ("In che anno è stata fondata la Juventus?", r"1897"),
    ("Qual è la capitale del Kazakistan?", r"Astana"),
    ("Quanto è profondo il lago di Garda?", r"34[0-9]"),
    ("Chi ha composto la Traviata?", r"Verdi"),
    ("In che anno è morto Leonardo da Vinci?", r"1519"),
    ("Qual è il numero atomico del ferro?", r"\b26\b"),
    ("Quanto è alta la torre di Pisa?", r"\b5[5-8]\b"),
    ("In che anno è stata inaugurata la torre Eiffel?", r"1889"),
    ("Chi era il padre di Alessandro Magno?", r"Filippo"),
    ("Qual è la capitale della Mongolia?", r"Ulan Bator|Ulaanbaatar"),
    ("Quando è nato Giacomo Leopardi?", r"1798"),
    ("Qual è il punto più profondo degli oceani?", r"Marianne|Challenger"),
    ("In che anno è stato firmato il trattato di Maastricht?", r"1992"),
]


# Domande nuove, scritte il 01/10 SENZA guardare i risultati: banco di controllo per non
# tarare la ricerca (SQLite FTS5 al posto di Xapian) sulle domande qui sopra. Con libzim e
# Xapian: 36/46 (docs/ricerche/2026-10-01-biblioteca-senza-libzim.md, §4).
BANCO_NUOVO = [
    ("Quanto è alto l'Etna?", r"3[ .]?[34][0-9]{2}"),
    ("Qual è la capitale del Portogallo?", r"Lisbona"),
    ("Quanti abitanti ha Torino?", r"8[0-9]{2}[ .]?[0-9]{3}"),
    ("In che anno è nato Galileo Galilei?", r"1564"),
    ("Chi ha scritto il Decameron?", r"Boccaccio"),
    ("Chi ha dipinto la Cappella Sistina?", r"Michelangelo"),
    ("Quando è iniziata la prima guerra mondiale?", r"1914"),
    ("Chi ha inventato il telefono?", r"Meucci|Bell"),
    ("Qual è il simbolo chimico dell'oro?", r"\bAu\b"),
    ("Quanto è lungo l'Arno?", r"24[0-9]"),
    ("Qual è la capitale del Giappone?", r"Tokyo|Tokio"),
    ("In che anno è stata scoperta l'America?", r"1492"),
    ("Chi ha composto la Nona sinfonia?", r"Beethoven"),
    ("Qual è il numero atomico del carbonio?", r"\b6\b|\bsei\b"),
    ("Quanto è alto il Cervino?", r"4[ .]?478"),
    ("Chi era la moglie di Napoleone?", r"Giuseppina|Joséphine|Maria Luisa"),
    ("In che anno è morto Dante Alighieri?", r"1321"),
    ("Qual è la capitale dell'Egitto?", r"Cairo"),
    ("Quanti abitanti ha Napoli?", r"9[0-9]{2}[ .]?[0-9]{3}"),
    ("Chi ha scritto l'Odissea?", r"Omero"),
    ("In che anno è stata fondata la Fiat?", r"1899"),
    ("Chi ha scoperto l'America?", r"Colombo"),
    ("Qual è la valuta del Giappone?", r"\byen\b"),
    ("In che anno è nato Mozart?", r"1756"),
    ("Chi ha scritto Il nome della rosa?", r"Eco\b"),
    ("Quanto è profondo il lago di Como?", r"4[01][0-9]"),
    ("Qual è la capitale del Brasile?", r"Brasília|Brasilia"),
    ("Chi ha dipinto la Notte stellata?", r"Van Gogh"),
    ("In che anno è caduto l'Impero romano d'Occidente?", r"476"),
    ("Qual è il simbolo chimico del potassio?", r"\bK\b"),
    ("Chi ha fondato la Ferrari?", r"Enzo Ferrari"),
    ("Qual è la lingua ufficiale del Brasile?", r"portoghese"),
    ("Quando è nato Giuseppe Verdi?", r"1813"),
    ("In che regione si trova Assisi?", r"Umbria"),
    ("Quanto è alta la Mole Antonelliana?", r"16[0-9]"),
    ("Chi ha scritto Pinocchio?", r"Collodi"),
    ("Qual è la capitale dell'Argentina?", r"Buenos Aires"),
    ("In che anno l'uomo è andato sulla Luna?", r"1969"),
    ("Chi era Cleopatra?", r"regina|faraon|Egitto"),
    ("Cos'è un vulcano?", r"magma|lava|crosta"),
    ("Quanto dura un anno su Marte?", r"68[67]|1,88"),
    ("Chi ha vinto i mondiali di calcio del 2006?", r"Italia"),
    ("In che anno è iniziata la costruzione della torre di Pisa?", r"1173"),
    ("A quanti gradi bolle l'acqua?", r"\b100\b"),
    ("Quanti abitanti ha la Sicilia?", r"\b4[ .]?[0-9]{3}[ .]?[0-9]{3}|4,[0-9] milion"),
    ("Chi ha scritto la Costituzione italiana?", r"Costituente|Assemblea"),
]


# Citazioni (Wikiquote, 01/10): a secco il primo passaggio dev'essere di Wikiquote e
# contenere l'autore; end-to-end la risposta detta
CITAZIONI_SECCO = [
    ("Chi ha detto che la fantasia è più importante della conoscenza?", r"Einstein"),
    ("Chi ha detto «Dostoevskij a me ha dato più di qualunque scienziato»?", r"Einstein"),
]
CITAZIONI = CITAZIONI_SECCO + [
    ("Chi ha detto che la bellezza salverà il mondo?", r"Dostoevskij|Dostoevskij|Dostoevsky"),
    # una frase di Einstein, non la sua biografia (le prime della sua voce di Wikiquote)
    ("Dimmi una citazione di Albert Einstein",
     r"Dio|Dostoevskij|Gauss|semplicità|teoria|osservare|realtà"),
]


def banco(bib, fatti, nome: str, k: int) -> tuple[int, list[float], float]:
    """Recall@k e tempi di `cerca` su un banco: (trovati, tempi dopo la prima, prima)."""
    trovati, tempi, prima = 0, [], None
    for i, (domanda, risposta) in enumerate(fatti):
        t = time.perf_counter()
        passaggi = bib.cerca(domanda)
        dt = (time.perf_counter() - t) * 1000
        if i == 0:
            prima = dt
        else:
            tempi.append(dt)
        testo = " ".join(f"{p.titolo} {p.testo}" for p in passaggi)
        ok = bool(re.search(risposta, testo, re.I))
        trovati += ok
        print(f"{'ok ' if ok else 'NO '} {dt:5.0f} ms  «{domanda}» → "
              + " | ".join(p.titolo for p in passaggi))
    q = sorted(tempi)
    print(f"\n{nome}: recall@{k} {trovati}/{len(fatti)}   latenza: prima domanda "
          f"{prima:.0f} ms, poi mediana {statistics.median(q):.0f} ms, p95 "
          f"{q[int(.95 * len(q))]:.0f} ms, massimo {max(q):.0f} ms\n")
    return trovati, tempi, prima


# Codice d'uscita di una prova saltata per intero (06/10): il runner la conta a parte,
# non come superata (prove/__main__.py)
SALTATA = 77


def main():
    cfg = Config()
    if not cfg.biblioteca_mini or not Path(cfg.biblioteca_mini).exists():
        print(f"File della biblioteca assente ({cfg.biblioteca_mini}): prova saltata.")
        return SALTATA
    from calliope.biblioteca import Biblioteca
    t0 = time.perf_counter()
    bib = Biblioteca(cfg)
    print(f"Biblioteca: {bib.descrizione()} (aperta in {(time.perf_counter() - t0) * 1000:.0f} ms)")

    print("Indici di ricerca: " + ", ".join(
        f"{Path(a.path).name} {'sì' if a.indice else 'no'}" for a in bib._tutti()))

    # ── a secco: la risposta giusta è tra i passaggi restituiti? ──
    fatti = [c for c in BANCO + BANCO_DIFFICILE if c[1] is not None]
    trovati, tempi, _ = banco(bib, fatti, "Banco", cfg.biblioteca_k)
    nuovi, tempi2, _ = banco(bib, BANCO_NUOVO, "Banco nuovo (01/10)", cfg.biblioteca_k)
    q = sorted(tempi + tempi2)
    print(f"Totale {trovati + nuovi}/{len(fatti) + len(BANCO_NUOVO)}; cerca su tutte: mediana "
          f"{statistics.median(q):.0f} ms, p95 {q[int(.95 * len(q))]:.0f} ms\n")
    # Senza indice (ricerca ridotta) il recall scende: la soglia vale solo con gli indici
    if bib.archivi[0].indice is not None:
        # Al più una risposta in meno dei valori dichiarati (49/56 e 36/46, 01/10): con l'80 e
        # il 70 per cento ne passavano cinque in meno senza che nessuno se ne accorgesse (06/10).
        # Con un banco cambiato le soglie vanno riviste insieme
        esito = (len(fatti) == 56 and len(BANCO_NUOVO) == 46 and trovati >= 48
                 and nuovi >= 35)
        if not esito:
            print(f"ERR banco {trovati}/{len(fatti)} (minimo 48/56), nuovo {nuovi}/"
                  f"{len(BANCO_NUOVO)} (minimo 35/46)")
    else:
        print("ATTENZIONE: manca l'indice di Wikipedia ridotta (python -m "
              "calliope.biblioteca_indice): soglie non controllate")
        esito = trovati >= int(0.5 * len(fatti))
    altre = 0

    # ── Wikizionario: significati, sinonimi, contrari (26/09) ──
    if bib.dizionario:
        for domanda, atteso in [("Cosa significa effimero?", r"dura (solamente|poco)"),
                                ("Che vuol dire procrastinare?", r"rimandare"),
                                ("Dimmi un sinonimo di felice", r"contento|allegro"),
                                ("Qual è il contrario di coraggioso?", r"pauroso|timoroso")]:
            p = bib.cerca(domanda)
            ok = bool(p) and p[0].fonte == "Wikizionario" and bool(re.search(atteso, p[0].testo))
            esito, altre = esito and ok, altre + ok
            print(f"{'ok ' if ok else 'NO '} dizionario «{domanda}» → {p[0].testo[:80] if p else '—'}")
    # ── Vikidia: in modalità semplice passa davanti a Wikipedia (26/09) ──
    if bib.ragazzi:
        for domanda in ("Chi era Giulio Cesare?", "Come funziona un vulcano?"):
            p = bib.cerca(domanda, semplice=True)
            ok = bool(p) and p[0].fonte == "Vikidia" and " – " not in p[0].testo[:60]
            esito, altre = esito and ok, altre + ok
            print(f"{'ok ' if ok else 'NO '} semplice «{domanda}» → "
                  f"{(p[0].fonte + ': ' + p[0].testo[:70]) if p else '—'}")
        p = bib.cerca("Chi era Giulio Cesare?")
        ok = bool(p) and p[0].fonte == "Wikipedia"
        esito, altre = esito and ok, altre + ok
        print(f"{'ok ' if ok else 'NO '} normale «Chi era Giulio Cesare?» → {p[0].fonte if p else '—'}")

    # ── significati ambigui: solo se la voce principale è una disambiguazione (26/09) ──
    for domanda, attese in [("Cos'è un'iperbole?", {"figura retorica", "in geometria"}),
                            ("Cos'è il mercurio?", {"pianeta del sistema solare", "elemento chimico"}),
                            ("Chi era Nettuno?", {"figura della mitologia romana"}),
                            # soggetto con sole parole di richiesta o di attributo intorno
                            ("Parlami di Venere", {"pianeta del sistema solare"}),
                            ("Quanto è grande Venere?", {"pianeta del sistema solare"})]:
        nomi = {p.titolo for p in bib.opzioni(domanda)}
        ok = attese <= nomi and len(nomi) <= 3
        esito, altre = esito and ok, altre + ok
        print(f"{'ok ' if ok else 'NO '} ambiguo «{domanda}» → {sorted(nomi)}")
    # Casi contrari del 01/10: il modello riformula la domanda e una parola che su Wikipedia
    # ha una disambiguazione («muro», «profondità», «composto», «punto», «fine») non è il
    # soggetto: niente «la parola ha più significati»
    for domanda in ("Quanto è lungo il Tevere?", "Quando è nato Alessandro Manzoni?",
                    "Parlami del Colosseo", "Cos'è l'iperbole in geometria?", "Cos'è un vulcano?",
                    "caduta del muro di Berlino", "profondità del lago di Garda",
                    "chi ha composto la Traviata", "punto più profondo degli oceani",
                    "fine della seconda guerra mondiale"):
        nomi = [p.titolo for p in bib.opzioni(domanda)]
        ok = not nomi
        esito, altre = esito and ok, altre + ok
        print(f"{'ok ' if ok else 'NO '} non ambiguo «{domanda}» → {nomi or '—'}")

    print(f"\nAltre prove (dizionario, Vikidia, significati ambigui): {altre}/22")

    # ── citazioni da Wikiquote (01/10), solo se è scaricata, accesa e indicizzata ──
    if bib.citazioni:
        citaz = 0
        for domanda, atteso in CITAZIONI_SECCO:
            p = bib.cerca(domanda)
            ok = bool(p) and p[0].fonte == "Wikiquote" and bool(
                re.search(atteso, f"{p[0].titolo} {p[0].testo}"))
            citaz += ok
            print(f"{'ok ' if ok else 'NO '} citazione «{domanda}» → "
                  f"{(p[0].fonte + ' · ' + p[0].titolo + ': ' + p[0].testo[:70]) if p else '—'}")
        p = bib.cerca("Dimmi una citazione di Albert Einstein")
        ok = bool(p) and p[0].fonte == "Wikiquote" and p[0].titolo == "Albert Einstein" \
            and "Einstein" not in p[0].testo
        citaz += ok
        print(f"{'ok ' if ok else 'NO '} citazione di un autore: una sua frase, non una su di lui "
              f"→ {p[0].testo[:70] if p else '—'}")
        p = bib.cerca("Chi era Albert Einstein?")
        ok = bool(p) and all(x.fonte != "Wikiquote" for x in p)
        citaz += ok
        print(f"{'ok ' if ok else 'NO '} domanda normale: niente Wikiquote → "
              f"{[x.fonte for x in p]}")
        esito = esito and citaz == len(CITAZIONI_SECCO) + 2
        print(f"Citazioni: {citaz}/{len(CITAZIONI_SECCO) + 2}")
    if "--ollama" in sys.argv:
        esito = end_to_end(cfg, bib, BANCO, "domande da manuale") and esito
        end_to_end(cfg, bib, BANCO_DIFFICILE, "fatti meno noti")
        if bib.citazioni:
            end_to_end(cfg, bib, CITAZIONI, "citazioni (Wikiquote)")
    return 0 if esito else 1


def end_to_end(cfg, bib, banco, nome) -> bool:
    """Brain vero su Ollama, con e senza biblioteca: tool, risposta, prima frase."""
    from calliope.brain import Brain
    from calliope.tools.builtin import build_registry
    from calliope.tools.spec import ToolContext

    class Ctx:
        current_speaker, current_level = "Dario", "amministra"

    class Speakers:
        def get(self, n):
            return None

    righe = {}
    for con in (True, False):
        giusti = tool_ok = 0
        primi = []
        for caso in banco:
            domanda, risposta = caso[0], caso[1]
            atteso = caso[2] if len(caso) > 2 else "biblioteca_cerca"
            ctx = ToolContext(cfg=cfg, speakers=Speakers(), speaker_ctx=Ctx(), speaker=None,
                              biblioteca=bib if con else None)
            b = Brain(cfg, build_registry(biblioteca=con, citazioni=con and bib.citazioni), ctx)
            t = time.perf_counter()
            primo, pezzi = None, []
            for pezzo in b.stream_reply(domanda, "amministra"):
                if primo is None and pezzo.strip():
                    primo = time.perf_counter() - t
                pezzi.append(pezzo)
            detto = "".join(pezzi).strip()
            tools = [x["nome"] for x in b.last_tools]
            if primo is not None:
                primi.append(primo)
            if risposta is None:
                ok_t = (atteso in tools) if atteso else not tools
                ok_r = ok_t
            else:
                ok_t = ("biblioteca_cerca" in tools) if con else True
                ok_r = bool(re.search(risposta, detto, re.I))
            tool_ok += ok_t
            giusti += ok_r
            print(f"[{'con' if con else 'senza'}] {'ok ' if ok_r else 'NO '}"
                  f"{'' if ok_t else '(tool) '}{primo or 0:4.2f}s «{domanda}» → "
                  f"{tools or '—'} | {detto[:90]!r}")
        righe[con] = (giusti, tool_ok, statistics.median(primi) if primi else 0,
                      max(primi) if primi else 0)
    n = len(banco)
    print(f"\n── {nome} ──")
    for con, (g, t, med, mx) in righe.items():
        print(f"{'CON' if con else 'SENZA'} biblioteca: risposte giuste {g}/{n}, tool giusti {t}/{n}, "
              f"prima frase mediana {med:.2f} s, massimo {mx:.2f} s")
    return righe[True][0] >= righe[False][0]


if __name__ == "__main__":
    sys.exit(main())
