"""
Unisce più classificatori (stessa architettura, addestramenti diversi) in un solo ONNX
che restituisce la media dei punteggi. Costa poco: le embedding si calcolano una volta
sola, i classificatori sono piccoli.

    .\wakeword\.venv\Scripts\python.exe wakeword\ensemble.py uscita varA:128 varB:256 ...
"""
import os
import sys

import torch
from torch import nn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from train import Classifier  # noqa: E402

MODELS = os.path.join(HERE, "modelli")


class Mean(nn.Module):
    def __init__(self, models):
        super().__init__()
        self.models = nn.ModuleList(models)

    def forward(self, x):
        return torch.stack([m(x) for m in self.models]).mean(0)


def main(out, *specs):
    models = []
    for spec in specs:
        name, width = spec.split(":")
        m = Classifier(int(width))
        m.load_state_dict(torch.load(os.path.join(MODELS, name + ".pt")))
        models.append(m.eval())
    ens = Mean(models).eval()
    path = os.path.join(MODELS, out + ".onnx")
    torch.onnx.export(ens, torch.zeros(1, 16, 96), path, input_names=["input"],
                      output_names=["score"], dynamic_axes={"input": {0: "batch"}},
                      opset_version=17, dynamo=False)
    print("salvato", path)


if __name__ == "__main__":
    main(*sys.argv[1:])
