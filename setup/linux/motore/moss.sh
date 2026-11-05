#!/usr/bin/env bash
# MOSS-TTSD per il podcast dello Studio (04/11/2026, issue #387, calliope/studio/podcast_motore.py): pesi, codice e
# ambiente a versione fissata, in una cartella sola, montata in sola lettura dal container del podcast.
# `trust_remote_code` è il rischio: i pesi si scaricano UNA volta, a mano, e si verificano; mai a ogni avvio.
#
#   setup/linux/motore/moss.sh installa    scarica codice, ambiente e pesi (28 GB, circa 75 minuti) in un container con la
#                                          rete, senza capacità e con la memoria stretta (moss_installa.py), poi verifica
#   setup/linux/motore/moss.sh adotta DIR  li prende da una cartella già scaricata (DIR/pesi, DIR/src, DIR/venv:
#                                          ~/prove-voci del banco del 04/11) con collegamenti fisici, pota e verifica
#   setup/linux/motore/moss.sh verifica    tutto ciò che viene eseguito, per hash, anche i pesi; un file in più non torna
#   setup/linux/motore/moss.sh elenco      riscrive `moss.sha256` dalla cartella (solo dopo aver deciso una versione nuova)
#   setup/linux/motore/moss.sh stato       cosa c'è
#
# MOSS="$HOME/calliope-motore/moss" è la cartella (config: studio_podcast_moss). Niente rete durante il podcast.
set -euo pipefail

AZIONE="${1:-stato}"
MOSS="${MOSS:-$HOME/calliope-motore/moss}"
QUI="$(cd "$(dirname "$0")" && pwd)"
MOTORE="$QUI/../../../calliope/studio/podcast_motore.py"
IMMAGINE="vllm/vllm-openai:v0.29.0"

case "$AZIONE" in
  installa)
    docker image inspect "$IMMAGINE" >/dev/null 2>&1 || { echo "Manca l'immagine $IMMAGINE (quella di vLLM)."; exit 1; }
    mkdir -p "$MOSS/pesi" "$MOSS/src" "$MOSS/venv"
    # Il download con la rete, ma senza capacità e con la memoria stretta: il banco del 04/11 ha mandato in swap la
    # voce con xet e un --memory-swap diverso da --memory
    docker run --rm --name calliope-moss-installa --memory=1500m --memory-swap=1500m --cap-drop ALL \
      --security-opt no-new-privileges --user "$(id -u):$(id -g)" -v "$MOSS:/pv" \
      -v "$QUI/moss_installa.py:/moss_installa.py:ro" --entrypoint python3 "$IMMAGINE" /moss_installa.py "${@:2}"
    python3 "$MOTORE" pota "$MOSS"
    case " $* " in *" --senza-pesi "*) echo "Senza i pesi: niente verifica."; exit 0 ;; esac
    python3 "$MOTORE" verifica "$MOSS"
    ;;
  adotta)
    DA="${2:?uso: moss.sh adotta DIR}"
    mkdir -p "$MOSS/pesi" "$MOSS/src" "$MOSS/venv"
    for d in pesi/moss-ttsd pesi/moss-tokenizer src/MOSS-TTSD venv/moss; do
      [ -e "$MOSS/$d" ] || cp -al "$DA/$d" "$MOSS/$d"
    done
    python3 "$MOTORE" pota "$MOSS"
    python3 "$MOTORE" verifica "$MOSS"
    ;;
  verifica)
    python3 "$MOTORE" verifica "$MOSS"
    ;;
  elenco)
    python3 "$MOTORE" elenco "$MOSS" \
      "I file di MOSS-TTSD a versione fissata: codice 46973e4, pesi c7cd852, tokenizer 3cd226b." \
      "$(docker image inspect --format '{{.Id}}' "$IMMAGINE")"
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
