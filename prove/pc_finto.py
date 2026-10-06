"""
Un PC finto per le prove dei tool pc_* (prova_pc.py, prova_pc_ollama.py).

Implementa PCExecutor in memoria: nessuna libreria nativa, nessun effetto sul PC vero.
Le regole comuni (catalogo, schermo bloccato, ultima ricerca per persona) restano quelle
vere della classe base: le prove le esercitano davvero. Ogni azione finisce in `azioni`.
"""

import datetime

from calliope.pc.base import CAPACITA, PCExecutor

APP = {"calcolatrice": "calc.exe", "blocco note": "notepad.exe", "esplora file": "explorer.exe",
       "impostazioni": "ms-settings:", "browser": "browser", "word": "winword.exe"}


def _giorni_fa(n: int) -> str:
    return (datetime.datetime.now() - datetime.timedelta(days=n)).isoformat(timespec="minutes")


FILE = [
    {"nome": "Bolletta luce agosto", "estensione": "pdf", "percorso": r"C:\finto\bolletta_luce_agosto.pdf",
     "modificato": _giorni_fa(20)},
    {"nome": "Bolletta gas luglio", "estensione": "pdf", "percorso": r"C:\finto\bolletta_gas_luglio.pdf",
     "modificato": _giorni_fa(50)},
    {"nome": "Bolletta acqua", "estensione": "pdf", "percorso": r"C:\finto\bolletta_acqua.pdf",
     "modificato": _giorni_fa(3)},
    {"nome": "Preventivo cucina", "estensione": "docx", "percorso": r"C:\finto\preventivo_cucina.docx",
     "modificato": _giorni_fa(8)},
    {"nome": "Mare 2026", "estensione": "jpg", "percorso": r"C:\finto\mare_2026.jpg",
     "modificato": _giorni_fa(30)},
]
_KIND = {"pdf": {"pdf"}, "documento": {"pdf", "docx", "txt"}, "foto": {"jpg", "png"},
         "musica": {"mp3"}, "video": {"mp4"}}


class FakePC(PCExecutor):
    def __init__(self, nome="portatile", app=None, caps=CAPACITA, volume=40, luminosita=80,
                 media=None, bloccato=False, file=None):
        super().__init__(nome, APP if app is None else app, max_risultati=5)
        self.caps = [c for c in caps if c != "app" or self._app]
        self.volume, self.muto, self.lum = volume, False, luminosita
        # media: None = niente aperto, altrimenti {"titolo", "artista", "app", "in_riproduzione"}
        self.media = media
        self.locked = bloccato
        self.file = FILE if file is None else file
        self.azioni: list[tuple] = []
        self.ultima_ricerca: tuple | None = None

    def capacita(self):
        return list(self.caps)

    def volume_leggi(self):
        return {"ok": True, "livello": self.volume, "muto": self.muto}

    def volume_imposta(self, livello):
        self.volume, self.muto = max(0, min(100, int(livello))), False
        self.azioni.append(("volume", self.volume))
        return self.volume_leggi()

    def volume_muto(self, attivo):
        self.muto = bool(attivo)
        self.azioni.append(("muto", self.muto))
        return self.volume_leggi()

    def media_info(self):
        if not self.media:
            return {"ok": True, "sessione": False, "in_riproduzione": False}
        return {"ok": True, "sessione": True, **self.media}

    def media_comando(self, comando):
        if not self.media:
            return {"ok": False, "errore": "non c'è niente da comandare: nessun programma sta "
                                          "suonando o è in pausa"}
        self.azioni.append(("media", comando))
        if comando in ("riproduci", "pausa"):
            self.media["in_riproduzione"] = comando == "riproduci"
        return {"ok": True, "app": self.media.get("app")}

    def luminosita_leggi(self):
        return {"ok": True, "livello": self.lum}

    def luminosita_imposta(self, livello):
        self.lum = max(0, min(100, int(livello)))
        self.azioni.append(("luminosita", self.lum))
        return {"ok": True, "livello": self.lum}

    def batteria(self):
        return {"ok": True, "batteria": True, "percento": 76, "in_carica": False}

    def schermo(self):
        return {"ok": True, "bloccato": self.locked, "inattivo_s": 5.0}

    def blocca(self):
        self.locked = True
        self.azioni.append(("blocca",))
        return {"ok": True}

    def _programmi(self):
        return ["Microsoft Edge", "Visual Studio Code", "Spotify"]

    def _avvia(self, comando):
        self.azioni.append(("avvia", comando))

    def _cerca(self, testo, tipo, dal, al, massimo):
        self.ultima_ricerca = (testo, tipo, dal, al)
        words = [w[:-1] if len(w) > 4 else w for w in testo.lower().split()
                 if w not in ("il", "la", "di", "del", "della", "file")]
        out = []
        for f in self.file:
            if words and not all(w in f["nome"].lower() for w in words):
                continue
            if tipo in _KIND and f["estensione"] not in _KIND[tipo]:
                continue
            if dal and f["modificato"] < dal[:16]:
                continue
            if al and f["modificato"] >= al[:16]:
                continue
            out.append(dict(f))
        return sorted(out, key=lambda f: f["modificato"], reverse=True)[:massimo]

    def _apri(self, percorso):
        self.azioni.append(("apri", percorso))
