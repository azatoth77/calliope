"""
Le frasi degli esercizi con le varianti (12/10/2026 sera, decisioni di Dario): «ripetimi il
numero», «a che punto siete», «un passo oltre il programma», le interrogazioni. Le dice il
codice, mai il modello, e **mai la stessa due volte di fila** alla stessa persona.

Perché qui e non nel catalogo di `calliope/frasi.py`: lì il modo predefinito («ombra») dice
sempre la forma di oggi e scrive la variante solo nel registro, mentre queste devono cambiare
davvero da subito (una bambina che si sente dire tre volte «Non ho capito il numero: me lo
ripeti?» smette di rispondere). Il tono è quello del turno (`frasi.FRASI.tono_turno()`: di chi
parla, o della casa); senza varianti per quel tono valgono quelle del tono normale.

Solo testo, nessun modello: latenza zero; profilo da 8 GB uguale.
"""

from __future__ import annotations

import random
import threading

# id → tono → varianti. I segnaposto ({punto}, {classe}…) sono gli stessi in ogni variante.
CATALOGO: dict[str, dict[str, tuple[str, ...]]] = {
    # Il numero non si ricava dalla frase (regola esercizi_numero_non_detto)
    "numero.ripeti": {
        "normale": ("Non ho capito bene il numero: me lo ridici piano?",
                    "Scusa, mi è sfuggito: lo ripeti scandendo?",
                    "Me lo dici un'altra volta, una cifra alla volta?",
                    "Il numero non l'ho capito: me lo ripeti più lentamente?",
                    "Non l'ho sentito bene: mi ridici il numero, piano piano?"),
        "amichevole": ("Ops, il numero mi è scappato: me lo ridici piano?",
                       "Non ho capito bene il numero: lo ripeti scandendo?",
                       "Me lo dici ancora, una cifra alla volta?",
                       "Mi è sfuggito! Me lo ripeti piano piano?"),
        "ironico": ("Le mie orecchie hanno perso il numero: me lo ridici piano?",
                    "Il numero è scappato via: lo ripeti scandendo?",
                    "Me lo ridici una cifra alla volta? Prometto di stare attenta.",
                    "Non l'ho afferrato: me lo ripeti più piano?"),
        "formale": ("Non ho capito bene il numero: me lo ripete piano?",
                    "Mi scusi, mi è sfuggito: lo ripete scandendo?",
                    "Me lo dice un'altra volta, una cifra alla volta?"),
        "essenziale": ("Non ho capito il numero: ripetilo piano?",
                       "Numero non capito: lo ripeti scandendo?",
                       "Ridimmelo una cifra alla volta?"),
        "computer_di_bordo": ("Numero non riconosciuto: ripeti scandendo?",
                              "Dato non acquisito: ripeti il numero lentamente?",
                              "Ripeti il numero, una cifra alla volta?"),
    },
    # Dopo due tentativi non capiti, con uno schermo abbinato
    "numero.schermo": {
        "normale": ("Se vuoi, scrivilo o toccalo sullo schermo.",
                    "Puoi anche scriverlo sullo schermo, se preferisci.",
                    "Se è più facile, scrivilo sullo schermo."),
        "formale": ("Se preferisce, può scriverlo sullo schermo.",
                    "Può anche scriverlo sullo schermo."),
        "computer_di_bordo": ("In alternativa, inserisci il numero sullo schermo.",),
    },
    # A inizio sessione: l'informazione c'è ma è vecchia
    "punto.noto": {
        "normale": ("Siete ancora {punto}, o siete andati avanti?",
                    "In classe siete sempre {punto}, o siete più avanti?",
                    "L'ultima volta eravate {punto}: è ancora così, o siete andati avanti?"),
        "amichevole": ("Siete ancora {punto}, o siete andati avanti?",
                       "Dimmi un po': siete sempre {punto}, o più avanti?"),
        "formale": ("Siete ancora {punto}, o siete andati avanti?",
                    "L'ultima volta eravate {punto}: è ancora così?"),
        "essenziale": ("Ancora {punto}, o più avanti?",),
        "computer_di_bordo": ("Verifica: ancora {punto}, o avanzati?",),
    },
    # A inizio sessione: l'informazione manca
    "punto.ignoto": {
        "normale": ("A che punto siete in {materia}? Per esempio, {esempio}?",
                    "Dimmi a che punto siete in {materia}: per esempio, {esempio}?",
                    "Per prepararti gli esercizi giusti: a che punto siete in {materia}? "
                    "Per esempio, {esempio}?"),
        "amichevole": ("Raccontami: a che punto siete in {materia}? Per esempio, {esempio}?",
                       "A che punto siete in {materia}? Per esempio, {esempio}?"),
        "formale": ("A che punto siete in {materia}? Per esempio, {esempio}?",),
        "essenziale": ("A che punto siete in {materia}? Per esempio, {esempio}?",),
        "computer_di_bordo": ("Dato mancante: a che punto siete in {materia}? Per esempio, "
                              "{esempio}?",),
    },
    # Molte sbagliate di fila
    "punto.difficile": {
        "normale": ("Queste ti stanno venendo difficili: in classe siete già arrivati qui, o "
                    "siete un passo indietro?",
                    "Mi sa che sono un po' difficili: le state già facendo in classe, o non "
                    "ancora?",
                    "Forse queste sono troppo difficili: a scuola a che punto siete?"),
        "amichevole": ("Uffa, queste sono toste! In classe le state già facendo, o non ancora?",
                       "Mi sa che queste sono difficili: a scuola a che punto siete?"),
        "formale": ("Forse sono troppo difficili: in classe siete già arrivati qui?",),
        "essenziale": ("Troppo difficili? In classe a che punto siete?",),
        "computer_di_bordo": ("Difficoltà elevata rilevata: in classe a che punto siete?",),
    },
    # Tutte giuste al primo colpo
    "punto.facile": {
        "normale": ("Ti vengono tutte giuste al primo colpo! In classe siete andati più avanti?",
                    "Queste sono facili per te: a scuola siete già più avanti?",
                    "Tutte giuste subito: in classe state facendo cose più difficili?"),
        "amichevole": ("Ma sei fortissim{o}! In classe siete andati più avanti?",
                       "Troppo facili per te! A scuola siete già più avanti?"),
        "formale": ("Le vengono tutte giuste: in classe siete più avanti?",),
        "essenziale": ("Troppo facili? In classe siete più avanti?",),
        "computer_di_bordo": ("Precisione massima rilevata: in classe siete più avanti?",),
    },
    # La risposta non si collega all'indice
    "punto.foto": {
        "normale": ("Non riesco a collegarlo al programma: se vuoi, fammi vedere una foto della "
                    "pagina del libro o del compito.",
                    "Questo non lo trovo nel programma: mi fai vedere una foto della pagina del "
                    "libro, o del compito?",
                    "Non so bene a cosa corrisponda: se mi mandi una foto della pagina del libro o "
                    "del compito, capisco meglio."),
        "formale": ("Non riesco a collegarlo al programma: se vuole, mi mostri una foto della "
                    "pagina del libro o del compito.",),
    },
    "punto.salvato": {
        "normale": ("Va bene, me lo segno: {punto}.", "D'accordo, me lo ricordo: {punto}.",
                    "Bene, segnato: {punto}."),
        "amichevole": ("Perfetto, me lo segno: {punto}.", "Fatto, me lo ricordo: {punto}."),
        "formale": ("Va bene, me lo segno: {punto}.",),
        "essenziale": ("Segnato: {punto}.",),
        "computer_di_bordo": ("Registrato: {punto}.",),
    },
    # Oltre il programma, solo se la persona lo chiede (per quella sessione)
    "oltre": {
        "normale": ("È un passo oltre il programma di {classe}: proviamo.",
                    "Questo va un po' oltre il programma di {classe}, ma proviamo.",
                    "È un passo oltre il programma di {classe}: vediamo come va."),
        "amichevole": ("È un passo oltre il programma di {classe}: proviamo, ci divertiamo!",
                       "Questo è oltre il programma di {classe}: sfida accettata, proviamo."),
        "formale": ("È un passo oltre il programma di {classe}: proviamo.",),
        "essenziale": ("Oltre il programma di {classe}: proviamo.",),
        "computer_di_bordo": ("Livello oltre il programma di {classe}: avvio.",),
    },
    # Nessun livello adatto alla classe adesso
    "nessun_livello": {
        "normale": ("Nel programma di {classe}{quando} non {ce} ancora {argomento}, e non ho "
                    "esercizi adatti. Facciamo {proposte}?",
                    "{Argomento} {e_sono} un po' più avanti del programma di {classe}{quando}: "
                    "non ho esercizi adatti. Ti va di fare {proposte}?"),
        "formale": ("Nel programma di {classe}{quando} non {ce} ancora {argomento}, e non ho "
                    "esercizi adatti. Facciamo {proposte}?",),
    },
    # Interrogazioni
    "interroga.inizio": {
        "normale": ("Facciamo finta di essere a scuola: ti interrogo {su}, {n} domande.",
                    "Simuliamo l'interrogazione {su}: ti faccio {n} domande.",
                    "Pronta l'interrogazione {su}: {n} domande."),
        "amichevole": ("Si gioca all'interrogazione {su}! {n} domande.",
                       "Ti interrogo {su}: {n} domande, tranquill{o}."),
        "formale": ("Simuliamo l'interrogazione {su}: {n} domande.",),
    },
    # Senza la pagina del libro non si improvvisa
    "interroga.pagina": {
        "normale": ("Per interrogarti mi serve la pagina del libro: mi fai una foto, o me la "
                    "scrivi?",
                    "Non voglio inventare le domande: mi fai una foto della pagina del libro, o "
                    "me la scrivi?",
                    "Mi serve il testo del libro: me ne mandi una foto, o lo scrivi?"),
        "formale": ("Per interrogarla mi serve la pagina del libro: mi mostra una foto, o me la "
                    "scrive?",),
    },
    "interroga.da_guardare": {
        "normale": ("Me la segno: questa risposta la guarda anche chi ti segue.",
                    "Grazie: su questa sentiamo anche chi ti segue.",
                    "D'accordo, me la segno: la ricontrolla con te chi ti segue."),
        "formale": ("La segno: questa risposta la guarda anche chi la segue.",),
    },
}


def tono_turno() -> str:
    try:
        from ..frasi import FRASI
        return FRASI.tono_turno()
    except Exception:  # noqa: BLE001 — senza il catalogo, il tono normale
        return "normale"


class Varianti:
    """Sceglie una variante, mai uguale all'ultima detta alla stessa persona per quell'id."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self._ultime: dict[tuple, str] = {}
        self._lock = threading.Lock()

    def dici(self, ident: str, persona=None, tono: str | None = None, **valori) -> str:
        forme_per_tono = CATALOGO[ident]
        t = tono or tono_turno()
        forme = forme_per_tono.get(t) or forme_per_tono["normale"]
        testi = [f.format(**valori) for f in forme]
        with self._lock:
            ultima = self._ultime.get((persona, ident))
            scelte = [x for x in testi if x != ultima] or testi
            testo = self.rng.choice(scelte)
            self._ultime[(persona, ident)] = testo
            if len(self._ultime) > 2000:
                self._ultime.clear()
        return testo
