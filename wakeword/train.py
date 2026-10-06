"""
Addestra il classificatore della wake word e lo esporta in ONNX (modelli/calliope.onnx).

Ingresso: 16 embedding × 96 (1,28 s) → probabilità che il nome sia appena stato detto.
Stessa architettura dei modelli personalizzati di openWakeWord (rete densa piccola),
quindi il file è compatibile anche con la libreria openwakeword.

Validazione durante l'addestramento (niente registrazioni reali, quelle servono solo
alla valutazione finale):
- richiamo sul 10% di positivi sintetici tenuti da parte;
- falsi risvegli per ora su validation_set_features.npy di openWakeWord (~10,7 h di
  parlato, musica e rumore, quasi tutto in inglese).

Negativi a ogni passo: esempi sintetici (neg.npy), finestre del parlato MLS e, se c'è,
dati/acav_parziale.npy (scarica_acav.py). Senza dropout il modello impara a memoria
(40–75 falsi/ora sulla validazione): il modello scelto usa dropout 0,3.

    .\\wakeword\\.venv\\Scripts\\python.exe wakeword\\train.py [passi] [nome] [larghezza] [peso_neg] [dropout]
    # modello scelto il 24/09 (calliope.onnx = varA):
    .\\wakeword\\.venv\\Scripts\\python.exe wakeword\\train.py 30000 varA 128 30.0 0.3
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import torch
from torch import nn

HERE = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.join(HERE, "dati", "feat")
# Un'altra parola (04/10, parole.py): WW_PAROLA=computer → dati/feat-computer
_PAROLA = os.environ.get("WW_PAROLA", "").strip().lower()
if _PAROLA and _PAROLA != "calliope":
    FEAT = os.path.join(HERE, "dati", f"feat-{_PAROLA}")
MODELS = os.path.join(HERE, "modelli")


class Classifier(nn.Module):
    def __init__(self, width=128, dropout=0.0):
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(), nn.Dropout(dropout / 2),
            nn.Linear(16 * 96, width), nn.LayerNorm(width), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(width, width), nn.LayerNorm(width), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(width, 1), nn.Sigmoid())

    def forward(self, x):
        return self.net(x)


def windows(seq: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """Finestre di 16 embedding che finiscono agli indici idx (esclusi)."""
    return np.stack([seq[i - 16:i] for i in idx])


def fa_per_hour(model, seq, thr=0.5, refractory=25, batch=8192) -> tuple[float, np.ndarray]:
    """Falsi risvegli per ora su una sequenza continua; dopo uno scatto si aspettano 2 s."""
    scores = []
    with torch.no_grad():
        for s in range(16, len(seq) + 1, batch):
            idx = np.arange(s, min(s + batch, len(seq) + 1))
            scores.append(model(torch.from_numpy(windows(seq, idx).astype(np.float32)))
                          .numpy().ravel())
    scores = np.concatenate(scores)
    n, last = 0, -10 ** 9
    for i in np.where(scores >= thr)[0]:
        if i - last > refractory:
            n += 1
            last = i
    return n / (len(seq) * 0.08 / 3600), scores


def main(steps=30000, name="calliope", width=128, max_neg_w=30.0, dropout=0.0, seed=0):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    torch.set_num_threads(int(os.environ.get("WW_THREADS", "8")))
    print(f"passi {steps}, larghezza {width}, peso negativi {max_neg_w}, dropout {dropout}")
    P = np.load(os.path.join(FEAT, "pos.npy"))
    PV = np.load(os.path.join(FEAT, "pos_val.npy")).astype(np.float32)
    N = np.load(os.path.join(FEAT, "neg.npy"))
    S = np.load(os.path.join(FEAT, "mls_seq.npy"))
    L = np.load(os.path.join(FEAT, "mls_len.npy"))
    # indici validi di fine finestra: tutti quelli con 16 embedding dello stesso file
    ends = np.cumsum(L)
    starts = ends - L
    valid = np.concatenate([np.arange(s + 16, e + 1) for s, e in zip(starts, ends) if e - s >= 16])
    V = np.load(os.path.join(HERE, "dati", "validation_set_features.npy"))
    acav_path = os.path.join(HERE, "dati", "acav_parziale.npy")
    A = np.load(acav_path, mmap_mode="r") if os.path.exists(acav_path) else None
    if A is not None:
        print(f"ACAV100M parziale: {len(A)} finestre", flush=True)
    print(f"pos {len(P)}  neg {len(N)}  finestre MLS {len(valid)} "
          f"({len(S) * 0.08 / 3600:.1f} h)  validazione {len(V) * 0.08 / 3600:.1f} h", flush=True)

    model = Classifier(width, dropout)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-2 if dropout else 0.0)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=1e-3, total_steps=steps,
                                                pct_start=0.1)
    bce = nn.BCELoss(reduction="none")
    t0 = time.time()
    best = None
    for step in range(1, steps + 1):
        bp = P[rng.integers(0, len(P), 256)]
        if A is not None:
            bn = N[rng.integers(0, len(N), 384)]
            bs = windows(S, valid[rng.integers(0, len(valid), 384)])
            ba = A[np.sort(rng.integers(0, len(A), 512))]
            parts = [bp, bn, bs, ba]
        else:
            bn = N[rng.integers(0, len(N), 512)]
            bs = windows(S, valid[rng.integers(0, len(valid), 512)])
            parts = [bp, bn, bs]
        x = torch.from_numpy(np.concatenate(parts).astype(np.float32))
        n_neg = len(x) - 256
        y = torch.cat([torch.ones(256), torch.zeros(n_neg)])
        # il peso dei negativi cresce durante l'addestramento (come in openWakeWord)
        nw = 1 + (max_neg_w - 1) * min(1.0, step / (0.7 * steps))
        w = torch.cat([torch.ones(256), torch.full((n_neg,), nw)])
        p = model(x).squeeze(1).clamp(1e-6, 1 - 1e-6)
        loss = (bce(p, y) * w).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
        if step % 2000 == 0 or step == steps:
            model.eval()
            with torch.no_grad():
                pv = model(torch.from_numpy(PV)).numpy().ravel()
            fa, _ = fa_per_hour(model, V)
            rec = float((pv >= 0.5).mean())
            print(f"passo {step}: loss {loss.item():.4f}  richiamo sintetico {rec:.3f}  "
                  f"falsi/ora (validazione oWW) {fa:.2f}  ({time.time() - t0:.0f} s)", flush=True)
            # si tiene il miglior richiamo con meno di 0,5 falsi risvegli per ora
            if step >= steps // 2 and fa <= 0.5 and (best is None or rec > best[0]):
                best = (rec, step, {k: v.clone() for k, v in model.state_dict().items()})
            model.train()

    if best is not None:
        model.load_state_dict(best[2])
        print(f"scelto il passo {best[1]} (richiamo sintetico {best[0]:.3f})")
    model.eval()
    os.makedirs(MODELS, exist_ok=True)
    out = os.path.join(MODELS, f"{name}.onnx")
    torch.onnx.export(model, torch.zeros(1, 16, 96), out, input_names=["input"],
                      output_names=["score"], dynamic_axes={"input": {0: "batch"}},
                      opset_version=17, dynamo=False)
    torch.save(model.state_dict(), os.path.join(MODELS, f"{name}.pt"))
    print("salvato", out)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]) if a else 30000, a[1] if len(a) > 1 else "calliope",
         *(float(x) if "." in x else int(x) for x in a[2:]))
