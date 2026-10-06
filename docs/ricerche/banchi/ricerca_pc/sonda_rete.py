"""Quanto costa il salto di rete verso un «esecutore» sul PC? Server HTTP minimo (stdlib)
su 127.0.0.1 con token per PC e un'unica capacità di SOLA LETTURA (volume attuale),
chiamata 50 volte da un client httpx con connessione tenuta aperta. Nessuna azione.
"""

import json
import statistics
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import hmac

TOKEN = "prova-token-lungo-e-casuale"


def read_volume():
    from pycaw.pycaw import AudioUtilities
    vol = AudioUtilities.GetSpeakers().EndpointVolume
    return round(vol.GetMasterVolumeLevelScalar() * 100)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        auth = self.headers.get("Authorization", "")
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        if not hmac.compare_digest(auth, f"Bearer {TOKEN}"):
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.loads(raw)
        if body.get("capacita") == "volume_leggi":
            import comtypes
            comtypes.CoInitialize()
            res = {"ok": True, "volume": read_volume()}
        else:
            res = {"ok": False, "errore": "capacità sconosciuta"}
        data = json.dumps(res).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

import httpx

with httpx.Client(base_url=f"http://127.0.0.1:{port}") as c:
    t_bad = time.perf_counter()
    r = c.post("/v1/esegui", json={"capacita": "volume_leggi"})
    bad = (r.status_code, round((time.perf_counter() - t_bad) * 1000, 1))
    times = []
    for _ in range(50):
        t = time.perf_counter()
        r = c.post("/v1/esegui", json={"capacita": "volume_leggi"},
                   headers={"Authorization": f"Bearer {TOKEN}"})
        times.append((time.perf_counter() - t) * 1000)
    print(json.dumps({"senza_token": bad, "risposta": r.json(),
                      "ms_mediana": round(statistics.median(times), 1),
                      "ms_p90": round(sorted(times)[44], 1),
                      "ms_primo": round(times[0], 1)}, ensure_ascii=False))
srv.shutdown()
