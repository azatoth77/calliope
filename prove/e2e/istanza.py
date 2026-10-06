"""
La Calliope di prova sulla DGX (06/10/2026): cartella dati, configurazione, profili,
abbinamenti, avvio e arresto. Non tocca mai la Calliope vera: dalla sua cartella dati
(`~/calliope/`) legge solo le chiavi del modello della voce (profilo, keep_alive…), i file
delle voci, dei modelli e della biblioteca (in sola lettura, per percorso o con un collegamento
simbolico al singolo file) e l'ora dell'ultimo turno del suo registro (guardia).

Stessi Ollama, vLLM, Whisper e SearXNG della Calliope vera (servizi esistenti: mai fermati né
riconfigurati). Per non far ricaricare il modello della voce a Ollama, l'istanza manda lo
stesso `num_ctx` che il modello ha già (letto da /api/ps) e lo stesso `keep_alive`.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# Porte dell'istanza (la vera usa 8770 e 8771)
PORTA_SCHERMI = 18770
PORTA_SATELLITI = 18771
TOKEN_HA = "tok-finto-e2e-NON-STAMPARE"     # dell'HA finto: non è un segreto
# Chiavi della configurazione vera che l'istanza copia (solo il modello della voce e i
# servizi locali su 127.0.0.1; mai casa, emittente, indirizzi di rete, segreti)
CHIAVI_VERE = ("llm_profilo", "llm_backend", "llm_keep_alive", "llm_native_url",
               "llm_base_url", "llm_model", "llm_think", "contesto_rilettura_max_s",
               "stt_motore", "stt_url", "stt_modello", "stt_correzione",
               "agenti_url", "agenti_modello", "web_searxng_url", "conversazioni_parallele",
               "tono")
GUARDIA_S = 180.0                           # la Calliope vera deve tacere da almeno tanto
# Le varianti della trascrizione da confrontare (07/10, `--stt`, docs/aree/stt-tts.md):
# A correzione spenta, B parole incerte al modello della voce nei dati del turno, B2 la frase
# capita scritta in testa e trattenuta, C correzione delle frasi incerte con un tetto di 1 s.
# Valgono sopra la configurazione vera
VARIANTI_STT = {
    "A": {"stt_correzione": False, "stt_incerte_al_modello": False},
    "B": {"stt_correzione": False, "stt_incerte_al_modello": True},
    "C": {"stt_correzione": True, "stt_correzione_timeout_s": 1.0,
          "stt_incerte_al_modello": False},
    # B2 (07/10): la riga «⟦capito: …⟧» trattenuta, valida solo se accettabile
    "B2": {"stt_correzione": False, "stt_incerte_al_modello": False,
           "stt_incerte_riscrivi": True},
}


def porta_libera(preferita: int = 0) -> int:
    for p in ([preferita] if preferita else []) + [0]:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError("nessuna porta libera")


def locale_su_127(v) -> bool:
    return isinstance(v, str) and ("127.0.0.1" in v or "localhost" in v)


class Istanza:
    def __init__(self, dati: Path, codice: Path, vera: Path, log=print,
                 sorgente: Path | None = None, stt: str | None = None):
        self.dati, self.codice, self.vera = Path(dati), Path(codice), Path(vera)
        # `sorgente`: il package calliope/ e calliope.yaml da provare, se non sono quelli della
        # versione in uso (`lancia --codice-qui`: il ramo del portatile); il venv resta quello
        # della versione (stesse dipendenze). `stt`: la variante della trascrizione (VARIANTI_STT)
        self.sorgente = Path(sorgente) if sorgente else self.codice
        self.stt = (stt or "").upper() or None
        self.log = log
        self.proc: subprocess.Popen | None = None
        self.porta_schermi = PORTA_SCHERMI
        self.porta_satelliti = PORTA_SATELLITI
        self.ha = None
        self.profili: dict[str, str] = {}       # nome → id del profilo
        self.token_sat: dict[str, str] = {}     # stanza → token del satellite
        self.richiesta_schermo: dict[str, str] = {}   # stanza → token dello schermo
        self.cfg_vera: dict = {}
        self.num_ctx = None

    # ── guardia sulla Calliope vera ──
    def ultimo_turno_vero(self) -> float:
        """Secondi dall'ultima riga scritta nel registro dei turni della Calliope vera
        (sola lettura della data di modifica)."""
        files = list((self.vera / "registro").glob("turni-*.jsonl"))
        if not files:
            return float("inf")
        return time.time() - max(f.stat().st_mtime for f in files)

    def aspetta_silenzio(self, soglia: float = GUARDIA_S, massimo: float = 3600.0,
                         motivo: str = "") -> float:
        """Aspetta che la Calliope vera taccia da `soglia` secondi; i secondi aspettati."""
        t0 = time.monotonic()
        avvisato = False
        while True:
            fa = self.ultimo_turno_vero()
            if fa >= soglia:
                return time.monotonic() - t0
            if not avvisato:
                self.log(f"[guardia] la Calliope vera ha parlato {fa:.0f} s fa: aspetto"
                         f"{' (' + motivo + ')' if motivo else ''}")
                avvisato = True
            if time.monotonic() - t0 > massimo:
                raise TimeoutError("la Calliope vera non si ferma")
            time.sleep(min(30.0, soglia - fa + 1))

    # ── preparazione ──
    def _leggi_cfg_vera(self) -> dict:
        import yaml
        out = {}
        for nome in ("calliope.yaml", "calliope.locale.yaml"):
            p = self.vera / nome
            if not p.is_file():
                continue
            dati = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            piatto = {}
            for k, v in dati.items():
                if isinstance(v, dict):          # sezioni
                    piatto.update(v)
                else:
                    piatto[k] = v
            for k in CHIAVI_VERE:
                if k in piatto:
                    v = piatto[k]
                    if k.endswith("_url") and v and not locale_su_127(v):
                        continue                 # solo servizi di questa macchina
                    out[k] = v
        return out

    def prepara(self, voci, ha_url: str):
        """Cartella dati da capo, configurazione, profili e abbinamenti."""
        d = self.dati
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        for sotto in ("istanza",):
            p = d / sotto
            if p.exists():
                shutil.rmtree(p)
        ist = d / "istanza"
        ist.mkdir(mode=0o700)
        self.ist = ist
        # Voci di Piper: un collegamento per file (VOICE_MAP usa «voices/…» relativo)
        (ist / "voices").mkdir()
        for f in (self.vera / "voices").glob("*.onnx*"):
            (ist / "voices" / f.name).symlink_to(f)
        self.cfg_vera = self._leggi_cfg_vera()
        self.porta_schermi = porta_libera(PORTA_SCHERMI)
        self.porta_satelliti = porta_libera(PORTA_SATELLITI)
        bib = self.vera / "biblioteca"
        righe = dict(self.cfg_vera)
        righe.update({
            # Audio dai satelliti, due stanze insieme
            "audio_modo": "satellite", "satellite_indirizzo": "127.0.0.1",
            "satellite_porta": self.porta_satelliti, "satelliti_insieme": True,
            "satellite_installazione": False, "satellite_aggiornamenti": False,
            "schermi_indirizzo": "127.0.0.1", "schermi_porta": self.porta_schermi,
            "schermi_scritto_al_minuto": 120,
            # File di sola lettura della Calliope vera, per percorso
            "piper_voice": str(ist / "voices" / "it_IT-serena-high.onnx"),
            "wake_model": str(self.vera / "wakeword" / "modelli" / "calliope.onnx"),
            "speaker_model": str(next((self.vera / "models" / "speaker").glob("*.onnx"))),
            "telefono_web": str(self.vera / "models" / "web"),
            "whisper_cartella": str(self.vera / "models" / "whisper"),
            # Casa: l'HA finto
            "casa_url": ha_url,
            # Agenti: lo stesso vLLM, senza pausa (la pausa è della Calliope vera)
            "agenti_pausa_vllm": False, "agenti_config_file": str(ist / "nessun-dgx.yaml"),
            # Niente installazioni, archivio di casa né rete verso fuori dalla pagina
            "installa_enabled": False, "archivio_enabled": False,
            "documenti_cartella": str(ist / "Documenti"),
            "ufficio_modelli": str(ist / "Modelli"),
            "storia_inattiva_s": 300.0,
        })
        if self.stt:
            righe.update(VARIANTI_STT[self.stt])
            self.log(f"[istanza] trascrizione: variante {self.stt} {VARIANTI_STT[self.stt]}")
        for chiave, nome in (("biblioteca_mini", "wikipedia_it_all_mini"),
                             ("biblioteca_completa", "wikipedia_it_all_nopic"),
                             ("biblioteca_ragazzi", "vikidia_it_all_nopic"),
                             ("biblioteca_dizionario", "wiktionary_it_all_nopic")):
            trovati = sorted(bib.glob(nome + "_*.zim"))
            if trovati:
                righe[chiave] = str(trovati[-1])
        if not any(k.startswith("biblioteca_") for k in righe):
            righe["biblioteca_enabled"] = False
        # calliope.yaml uguale a quello della versione; i valori della prova nel file locale
        shutil.copy(self.sorgente / "calliope.yaml", ist / "calliope.yaml")
        (ist / "calliope.locale.yaml").write_text(json.dumps(righe, indent=1,
                                                             ensure_ascii=False),
                                                  encoding="utf-8")
        (ist / "segreti.yaml").write_text(f'home_assistant:\n  token: "{TOKEN_HA}"\n',
                                          encoding="utf-8")
        os.chmod(ist / "segreti.yaml", 0o600)
        self._num_ctx(righe)
        self._profili(voci)
        self._abbina()

    def env(self) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("CALLIOPE_") and k not in ("NOTIFY_SOCKET",)}
        env.update(PYTHONPATH=str(self.sorgente), PYTHONUTF8="1", PYTHONUNBUFFERED="1",
                   CALLIOPE_CONFIG=str(self.ist / "calliope.yaml"),
                   CALLIOPE_CONFIG_LOCALE=str(self.ist / "calliope.locale.yaml"),
                   CALLIOPE_AGENTI_CONFIG=str(self.ist / "nessun-dgx.yaml"),
                   CALLIOPE_PORTA_ISTANZA=str(porta_libera()))
        return env

    def cfg(self):
        """La Config dell'istanza, come la vede Calliope."""
        vecchio = {k: os.environ.get(k) for k in ("CALLIOPE_CONFIG", "CALLIOPE_CONFIG_LOCALE",
                                                 "CALLIOPE_AGENTI_CONFIG")}
        e = self.env()
        try:
            for k in vecchio:
                os.environ[k] = e[k]
            from calliope.config import load_config
            return load_config()
        finally:
            for k, v in vecchio.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _num_ctx(self, righe: dict):
        """Lo stesso num_ctx che il modello della voce ha già in Ollama (altrimenti Ollama
        lo ricaricherebbe, e la Calliope vera pagherebbe il caricamento)."""
        import httpx
        cfg = self.cfg()
        modello, url = cfg.llm_model, (cfg.llm_native_url or "http://127.0.0.1:11434")
        n = None
        try:
            for m in httpx.get(url.rstrip("/") + "/api/ps", timeout=5).json().get("models", []):
                if m.get("name") == modello or m.get("model") == modello:
                    n = int(m.get("context_length") or 0) or None
        except Exception as e:  # noqa: BLE001
            self.log(f"[istanza] /api/ps non risponde: {e}")
        if n is None:
            try:
                scelte = json.loads((self.vera / "contesto.json").read_text(encoding="utf-8"))
                n = next((int(v["finestra"]) for k, v in scelte.items() if modello in k), None)
            except (OSError, ValueError, KeyError, StopIteration):
                n = None
        if n:
            righe["llm_num_ctx"] = n
            (self.ist / "calliope.locale.yaml").write_text(
                json.dumps(righe, indent=1, ensure_ascii=False), encoding="utf-8")
        self.num_ctx, self.modello = n, modello
        self.log(f"[istanza] modello della voce {modello}, num_ctx {n} (come la Calliope vera)")

    def _profili(self, voci):
        from calliope.speaker_id import SpeakerRegistry
        from .voci import PERSONE
        cfg = self.cfg()
        SpeakerRegistry.PATH = self.ist / "speakers.json"
        reg = SpeakerRegistry(cfg)
        for nome, p in PERSONE.items():
            if not p.registrata:
                continue
            embs = [reg.embed(x) for x in voci.arruolamento(nome)]
            if not embs:
                self.log(f"[istanza] {nome}: nessuna frase per l'impronta, salto")
                continue
            prof = reg.set_voiceprint(nome, embs, gender=p.genere, admin=p.admin)
            self.profili[nome] = prof.id
            self.log(f"[istanza] {nome}: impronta da {len(embs)} frasi"
                     f"{' (amministra)' if p.admin else ''}")
        for nome, p in PERSONE.items():
            if p.nascita and nome in reg.users:
                prof = reg.users[nome]
                prof.nascita, prof.fascia = p.nascita, None
                prof.tutori = [self.profili[t] for t in p.tutori if t in self.profili]
        reg.save()
        reg.flush()
        os.chmod(self.ist / "speakers.json", 0o600)
        self.registro_voci = reg

    def _abbina(self):
        """Satelliti «studio» (con il PC finto) e «cucina»; uno schermo personale di Andrea
        nello studio (foto, allegati, scritto)."""
        from calliope.satellite.archivio import ArchivioSatelliti
        from calliope.schermi.archivio import ArchivioSchermi
        db = str(self.ist / "memoria.db")
        arch = ArchivioSatelliti(db)
        _, self.token_sat["studio"] = arch.crea_con_token("studio", ruolo="pc")
        _, self.token_sat["cucina"] = arch.crea_con_token("cucina")
        arch.close()
        sch = ArchivioSchermi(db)
        r = sch.nuova_richiesta()
        if "Andrea" in self.profili:
            sch.abbina(r["codice"], "studio", self.profili["Andrea"], "Andrea")
            self.richiesta_schermo["studio"] = r["richiesta"]
        sch.close()

    # ── avvio e arresto ──
    def avvia(self):
        self.log_file = open(self.dati / "istanza.log", "a", encoding="utf-8")
        self.proc = subprocess.Popen(
            [str(self.codice / ".venv" / "bin" / "python"), "-u", "-m", "calliope"],
            cwd=self.ist, env=self.env(), stdout=self.log_file, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
        (self.dati / "istanza.pid").write_text(str(self.proc.pid))
        self.log(f"[istanza] avviata (pid {self.proc.pid}), satelliti :{self.porta_satelliti},"
                 f" schermi :{self.porta_schermi}")

    def viva(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def ferma(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                self.proc.wait(5)
        try:
            (self.dati / "istanza.pid").unlink()
        except OSError:
            pass
        if getattr(self, "log_file", None):
            self.log_file.close()

    # ── registro dei turni dell'istanza ──
    def turni(self) -> list[dict]:
        out = []
        for f in sorted((self.ist / "registro").glob("turni-*.jsonl")):
            for r in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    out.append(json.loads(r))
                except ValueError:
                    pass
        return out

    def log_testo(self) -> str:
        try:
            return (self.dati / "istanza.log").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


def modelli_ollama(url: str = "http://127.0.0.1:11434") -> dict[str, dict]:
    """I modelli caricati in Ollama: nome → {ctx, sempre} (sempre: keep_alive infinito)."""
    import httpx
    try:
        r = httpx.get(url + "/api/ps", timeout=5).json()
    except Exception:  # noqa: BLE001
        return {}
    return {m["name"]: {"ctx": m.get("context_length"),
                        "sempre": str(m.get("expires_at", ""))[:4] > "2100"}
            for m in r.get("models") or []}


def ripristina_ollama(prima: dict, log=print, url: str = "http://127.0.0.1:11434") -> list[str]:
    """Rimette in Ollama i modelli di prima della prova (06/10: Ollama 0.35 ne tiene al più
    3 e l'archivio delle conversazioni dell'istanza caricava qwen3-embedding, che scacciava il
    guardiano della Calliope vera): toglie quelli caricati dopo, ricarica quelli scacciati con
    lo stesso contesto e lo stesso keep_alive. Solo carico e scarico di modelli, nessuna
    configurazione."""
    import httpx
    fatti = []
    ora = modelli_ollama(url)
    for nome in ora:
        if nome not in prima:
            try:
                httpx.post(url + "/api/generate", json={"model": nome, "keep_alive": 0},
                           timeout=60)
                fatti.append(f"scaricato {nome}")
            except Exception as e:  # noqa: BLE001
                fatti.append(f"{nome}: non scaricato ({e})")
    for nome, m in prima.items():
        if nome in ora:
            continue
        corpo = {"model": nome, "keep_alive": "-1m" if m["sempre"] else "30m",
                 "options": {"num_ctx": m["ctx"]} if m.get("ctx") else {}}
        try:
            if "embed" in nome:
                httpx.post(url + "/api/embed", json={**corpo, "input": "x"}, timeout=300)
            else:
                httpx.post(url + "/api/generate", json={**corpo, "prompt": ""}, timeout=300)
            fatti.append(f"ricaricato {nome}")
        except Exception as e:  # noqa: BLE001
            fatti.append(f"{nome}: non ricaricato ({e})")
    for f in fatti:
        log(f"[ollama] {f}")
    return fatti


def pulisci(dati: Path, tieni=("risultati",)):
    """Ferma un'istanza rimasta (pid salvato) e cancella tutto tranne i risultati."""
    pid = dati / "istanza.pid"
    if pid.is_file():
        try:
            n = int(pid.read_text().strip())
            os.killpg(n, signal.SIGTERM)
            for _ in range(40):
                time.sleep(0.5)
                os.killpg(n, 0)
            os.killpg(n, signal.SIGKILL)
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass
        pid.unlink(missing_ok=True)
    def scrivibile(funzione, percorso, _):
        # Le estensioni approvate sono in sola lettura (file e cartelle): si rendono
        # scrivibili solo per cancellarle
        try:
            os.chmod(os.path.dirname(percorso), 0o700)
            os.chmod(percorso, 0o700)
            funzione(percorso)
        except OSError:
            pass
    for p in dati.iterdir() if dati.is_dir() else []:
        if p.name in tieni:
            os.chmod(p, 0o700)
            continue
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p, onexc=scrivibile)
        else:
            p.unlink(missing_ok=True)


if __name__ == "__main__":       # python -m prove.e2e.istanza --pulisci <dati>
    if len(sys.argv) == 3 and sys.argv[1] == "--pulisci":
        pulisci(Path(sys.argv[2]).expanduser())
