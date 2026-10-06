#!/bin/sh
# Confronto tra modelli (26/09/2026): stesse strategie, un modello alla volta.
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python.exe
export PYTHONUTF8=1
$PY -u docs/ricerche/banchi/ricerca_tool/banco.py --modello gemma4:e4b-it-qat --strategie piatto40-istr,piatto10-istr,rag-bge-k5-istr
for M in gemma4:e2b-it-qat qwen3.5:4b qwen3:8b; do
  $PY -u docs/ricerche/banchi/ricerca_tool/banco.py --modello $M --strategie piatto10,piatto40,rag-bge-k5,meta
  ollama ps
  nvidia-smi --query-gpu=memory.used --format=csv
done
