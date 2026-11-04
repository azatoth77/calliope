#!/usr/bin/env bash
# MOSS-TTSD per il podcast dello Studio (04/11/2026, issue #387, calliope/studio/podcast_motore.py): pesi, codice e
# ambiente a versione fissata, in una cartella sola, montata in sola lettura dal container del podcast.
# `trust_remote_code` è il rischio: i pesi si scaricano UNA volta, a mano, e si verificano; mai a ogni avvio.
#
#   setup/linux/motore/moss.sh installa    scarica codice e pesi (28 GB, circa 75 minuti) in un container con la rete,
#                                          senza capacità e con la memoria stretta, e poi verifica
#   setup/linux/motore/moss.sh adotta DIR  li prende da una cartella già scaricata (DIR/pesi, DIR/src, DIR/venv:
#                                          ~/prove-voci del banco del 04/11) con collegamenti fisici, e verifica
#   setup/linux/motore/moss.sh verifica    gli hash di tutto, anche dei pesi: `moss.sha256` qui accanto
#   setup/linux/motore/moss.sh elenco      riscrive `moss.sha256` dalla cartella (solo dopo aver deciso una versione nuova)
#   setup/linux/motore/moss.sh stato       cosa c'è
#
# MOSS="$HOME/calliope-motore/moss" è la cartella (config: studio_podcast_moss). Niente rete durante il podcast.
set -euo pipefail

AZIONE="${1:-stato}"
MOSS="${MOSS:-$HOME/calliope-motore/moss}"
QUI="$(cd "$(dirname "$0")" && pwd)"
ELENCO="$QUI/moss.sha256"
IMMAGINE="vllm/vllm-openai:v0.29.0"
CODICE=46973e425da227bfa3b315dcd7a4aba8b6be5574
PESI=c7cd852d87aff71cab5bd2b9b05509cedc0ef1ba
TOKENIZER=3cd226ba2947efa357ef453bcad111b6eafba782

verifica() {
  cd "$MOSS"
  male=0
  while read -r hash dim rel; do
    case "$hash" in ''|\#*) continue ;; esac
    [ -f "$rel" ] || { echo "MANCA  $rel"; male=1; continue; }
    [ "$(stat -c %s "$rel")" = "$dim" ] || { echo "DIMENSIONE  $rel"; male=1; continue; }
    [ "$(sha256sum "$rel" | cut -d' ' -f1)" = "$hash" ] || { echo "HASH  $rel"; male=1; }
  done < "$ELENCO"
  [ "$male" = 0 ] && echo "Tutto come in moss.sha256." || { echo "Non torna: il podcast non parte."; exit 1; }
}

case "$AZIONE" in
  installa)
    docker image inspect "$IMMAGINE" >/dev/null 2>&1 || { echo "Manca l'immagine $IMMAGINE (quella di vLLM)."; exit 1; }
    mkdir -p "$MOSS/pesi" "$MOSS/src" "$MOSS/venv" "$MOSS/tmp"
    cat > "$MOSS/tmp/installa.sh" <<SCRIPT
set -eu
export HF_HOME=/pv/tmp/hf TMPDIR=/pv/tmp HF_HUB_DISABLE_XET=1 HF_HUB_DISABLE_TELEMETRY=1 UV_CACHE_DIR=/pv/tmp/uv
cd /pv/src
[ -d MOSS-TTSD ] || git clone -q https://github.com/OpenMOSS/MOSS-TTSD
git -C MOSS-TTSD checkout -q $CODICE
uv venv -q --system-site-packages --python /usr/bin/python3 /pv/venv/moss
uv pip install -q --python /pv/venv/moss/bin/python --only-binary :all: --no-deps "transformers==5.0.0" "tokenizers==0.22.2" \
  "tiktoken==0.12.0" soundfile einops "librosa==0.11.0" soxr audioread lazy_loader pooch platformdirs msgpack numba llvmlite \
  joblib scikit-learn threadpoolctl decorator orjson pybase64 scipy
hf download OpenMOSS-Team/MOSS-TTSD-v1.0 --revision $PESI --local-dir /pv/pesi/moss-ttsd --max-workers 2
hf download OpenMOSS-Team/MOSS-Audio-Tokenizer --revision $TOKENIZER --local-dir /pv/pesi/moss-tokenizer --max-workers 2
SCRIPT
    # Il download con la rete, ma senza capacità e con la memoria stretta: il banco del 04/11 ha mandato in swap la
    # voce con xet e un --memory-swap diverso da --memory
    docker run --rm --name calliope-moss-installa --memory=1500m --memory-swap=1500m --cap-drop ALL \
      --security-opt no-new-privileges --user "$(id -u):$(id -g)" -e HOME=/pv/tmp -v "$MOSS:/pv" \
      --entrypoint bash "$IMMAGINE" /pv/tmp/installa.sh
    rm -rf "$MOSS/tmp"
    verifica
    ;;
  adotta)
    DA="${2:?uso: moss.sh adotta DIR}"
    mkdir -p "$MOSS/pesi" "$MOSS/src" "$MOSS/venv"
    for d in pesi/moss-ttsd pesi/moss-tokenizer src/MOSS-TTSD venv/moss; do
      [ -e "$MOSS/$d" ] || cp -al "$DA/$d" "$MOSS/$d"
    done
    verifica
    ;;
  verifica)
    verifica
    ;;
  elenco)
    cd "$MOSS"
    {
      echo "# I file di MOSS-TTSD a versione fissata (codice $CODICE, pesi $PESI, tokenizer $TOKENIZER): sha256, byte, percorso."
      find pesi/moss-ttsd pesi/moss-tokenizer -type f ! -path '*/.cache/*' ! -path '*/__pycache__/*' ! -name '*.md' -print0 | sort -z \
        | xargs -0 -I{} sh -c 'printf "%s %s %s\n" "$(sha256sum "$1" | cut -d" " -f1)" "$(stat -c %s "$1")" "$1"' _ {}
      for f in src/MOSS-TTSD/generation_utils.py; do
        printf "%s %s %s\n" "$(sha256sum "$f" | cut -d" " -f1)" "$(stat -c %s "$f")" "$f"
      done
    } > "$ELENCO"
    wc -l "$ELENCO"
    ;;
  stato)
    if [ -d "$MOSS/pesi/moss-ttsd" ]; then echo "MOSS in $MOSS: $(du -sh "$MOSS" | cut -f1)"; else echo "MOSS non c'è in $MOSS."; fi
    docker ps -a -f "name=^calliope-moss$" --format '{{.Names}}  {{.Status}}' || true
    ;;
  *)
    echo "Uso: $0 installa|adotta DIR|verifica|elenco|stato" >&2
    exit 2
    ;;
esac
