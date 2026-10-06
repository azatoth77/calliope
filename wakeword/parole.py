"""
Parole per la wake word oltre a «Calliope» (04/10, docs/ricerche/2026-10-04-personalita-wake-word.md).

Con `WW_PAROLA=<nome>` genera.py, feature.py e train.py lavorano su questa parola invece
che sul nome, in cartelle loro (dati/tts-<nome>, dati/feat-<nome>, modelli/<nome>.onnx), e
riusano i negativi che non dipendono dalla parola già calcolati per «Calliope»
(dati/feat/neg.npy e il parlato MLS in dati/feat/mls_seq.npy) più l'ACAV100M parziale:
così non serve riscaricare MLS (1,8 GB) né rifare le sue feature.

Per ogni parola: varianti fonetiche (quelle di espeak per l'italiano, con l'accento
sulla sillaba giusta), testi, parole e frasi simili che non devono svegliare, pezzi della
parola. NON vanno tra i negativi le frasi con la parola dentro («il computer è lento»):
acusticamente sono la parola; che non sia un richiamo lo decide il testo
(wake_posizione: inizio, calliope/wakeword.find_wake_word).
"""

PAROLE = {
    "computer": {
        # espeak (piper, voce italiana): «Computer» → kompjˈuteɾ; con le pronunce più
        # inglesi e quelle storpiate dette in fretta
        "fonemi": ["kompjˈuteɾ", "kompjˈuter", "kompjˈuːteɾ", "kɔmpjˈuteɾ", "kompjˈutəɾ",
                   "kəmpjˈuːtəɹ", "kompjˈutɛɾ", "kumpjˈuteɾ"],
        "testi": ["Computer.", "Computer!", "Computer?", "Computer,", "Computer..."],
        "simili": """computo compito compiuto compiere competere computare compieta comprare
compleanno compost componente completo comporre comunque commento compagno compasso
compatto compenso compiti computisteria computerizzato commuter scooter Peter Jupiter
Gunter cutter putter compro compra comparsa compare compito tutor router poter potere
Copernico colpire comprimere""".split(),
        "frasi": [
            "Ho fatto il compito di matematica.", "Il computo metrico è pronto.",
            "Bisogna competere con gli altri.", "Vado a comprare il pane.",
            "Domani è il compleanno di Marco.", "La compostiera è piena.",
            "Che ore sono?", "Accendi la luce in cucina.", "Il componente è rotto.",
            "Comunque ci vediamo dopo.", "Il compasso è nel cassetto.",
            "Il router del wifi è spento.", "Ho preso lo scooter.", "Il tutor ha chiamato.",
            "Potere e volere.", "Ha compiuto gli anni ieri.", "Compra le pile.",
        ],
        "pezzi": ["[[kompj]]", "[[kˈom]]", "[[pjˈuteɾ]]", "[[ˈuteɾ]]", "[[kompjˈu]]"],
    },
}
