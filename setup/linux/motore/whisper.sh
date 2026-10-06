#!/usr/bin/env bash
# Server di trascrizione della DGX Spark: whisper.cpp compilato con CUDA (02/10/2026).
# Scelto all'installazione del 02/10 sulle 104 registrazioni con riferimento
# (prove/prova_whisper.py --server): WER 12,4 % contro 21 % di vLLM con Whisper (niente beam
# search) e 11,0 % di faster-whisper sul portatile. Rapporto:
# docs/ricerche/2026-10-02-impacchettamento-dgx-linux.md, §1.1.
#
#   setup/linux/motore/whisper.sh compila    sorgente al commit fissato + build CUDA
#   setup/linux/motore/whisper.sh scarica    modello ggml con verifica SHA-256
#   setup/linux/motore/whisper.sh installa   unità systemd utente calliope-whisper.service
#   setup/linux/motore/whisper.sh avvia|ferma|stato|log
#
# compila e scarica chiedono conferma (scaricano dalla rete: ~15 MB di sorgente, 1,6 GB di
# modello); --si per non chiedere. Niente sudo: servono git, cmake, g++ e il CUDA di DGX OS
# (/usr/local/cuda/bin/nvcc), già presenti sulla DGX. Calliope lo usa con, in
# ~/calliope/calliope.locale.yaml:
#     stt:
#       stt_motore: server
#       stt_url: http://127.0.0.1:8003/v1
# e se il server non risponde trascrive su CPU con faster-whisper (principio 7: il modello di
# riserva lo prepara `calliope stato --installa whisper_riserva`).
#
# Valori cambiabili da ambiente: DIR (cartella, predefinita ~/calliope-motore/whispercpp:
# sorgente in DIR/src, modelli in DIR/modelli), PORTA (8003), COMMIT (di whisper.cpp),
# BEAM (5), PROMPT («Conversazione con Calliope.»; Calliope comunque manda il suo prompt a
# ogni richiesta, e whisper-server usa quello).
set -euo pipefail

DIR="${DIR:-$HOME/calliope-motore/whispercpp}"
PORTA="${PORTA:-8003}"
BEAM="${BEAM:-5}"
PROMPT="${PROMPT:-Conversazione con Calliope.}"
# Il commit compilato e provato sulla DGX il 02/10 (master del 02/10/2026, CUDA 13.0.88)
COMMIT="${COMMIT:-60c0be6ac8fa71b1a2ae2dd938a31a34a508e774}"
REPO="https://github.com/ggml-org/whisper.cpp"
# Modello: ggml-large-v3-turbo.bin dal repository ufficiale ggerganov/whisper.cpp su Hugging
# Face, a una revisione fissa; dimensione e SHA-256 sono quelli dichiarati da Hugging Face
# (X-Linked-Size, X-Linked-ETag, letti il 02/10) e del file in uso sulla DGX
MODELLO="ggml-large-v3-turbo.bin"
MODELLO_REV="5359861c739e955e79d9a303bcbc70fb988958b1"
MODELLO_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/$MODELLO_REV/$MODELLO"
MODELLO_SHA="1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"
MODELLO_BYTE=1624555275
UNITA="calliope-whisper"
QUI=$(cd "$(dirname "$0")" && pwd)
SERVER="$DIR/src/build/bin/whisper-server"

SI=0
for a in "$@"; do [ "$a" = "--si" ] && SI=1; done
AZIONE="${1:-stato}"

chiedi() {
  [ "$SI" -eq 1 ] && return 0
  printf "%s [s/N] " "$1"
  read -r r || r=""
  case "$r" in s|S|si|sì|SI) return 0 ;; *) echo "Va bene, non faccio niente."; return 1 ;; esac
}

pronto() {
  # whisper-server risponde 200 su / (pagina di prova); /v1/models non c'è
  curl -fsS -o /dev/null "http://127.0.0.1:$PORTA/" 2>/dev/null
}

case "$AZIONE" in
  compila)
    NVCC=$(command -v nvcc || echo /usr/local/cuda/bin/nvcc)
    for c in git cmake g++; do
      command -v "$c" >/dev/null 2>&1 || { echo "Manca $c: sudo apt install git cmake g++"; exit 1; }
    done
    [ -x "$NVCC" ] || { echo "Manca nvcc (CUDA): su DGX OS è in /usr/local/cuda/bin."; exit 1; }
    chiedi "Scarico whisper.cpp ($REPO, commit ${COMMIT:0:12}) e lo compilo con CUDA in $DIR/src?" || exit 1
    mkdir -p "$DIR/src"
    cd "$DIR/src"
    [ -d .git ] || git init -q
    git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REPO"
    git fetch -q --depth 1 origin "$COMMIT"
    git checkout -q --detach FETCH_HEAD
    # CMAKE_CUDA_ARCHITECTURES=native: sulla GB10 con CUDA 13 diventa sm_121 (così è stato
    # compilato il 02/10); il PATH con nvcc serve a cmake per trovare il compilatore CUDA
    PATH="$(dirname "$NVCC"):$PATH" cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_CUDA_ARCHITECTURES=native 2>&1 | tee "$DIR/build.log"
    PATH="$(dirname "$NVCC"):$PATH" cmake --build build --config Release -j "$(nproc)" \
      --target whisper-server 2>&1 | tee -a "$DIR/build.log"
    [ -x "$SERVER" ] && echo "Compilato: $SERVER" || { echo "Compilazione non riuscita: $DIR/build.log"; exit 1; }
    ;;
  scarica)
    F="$DIR/modelli/$MODELLO"
    mkdir -p "$DIR/modelli"
    if [ -f "$F" ] && [ "$(stat -c %s "$F")" = "$MODELLO_BYTE" ]; then
      echo -n "Il modello c'è già: verifico il checksum… "
      if echo "$MODELLO_SHA  $F" | sha256sum -c --status; then echo "integro."; exit 0; fi
      echo "NON corrisponde: lo riscarico."
    fi
    chiedi "Scarico $MODELLO da Hugging Face (1,6 GB, revisione ${MODELLO_REV:0:12})?" || exit 1
    # .part con ripresa (-C -), poi il checksum, poi il nome vero: un file a metà non si usa mai
    curl -fL --retry 3 -C - -o "$F.part" "$MODELLO_URL"
    echo -n "Verifico il checksum… "
    if ! echo "$MODELLO_SHA  $F.part" | sha256sum -c --status; then
      echo "NON corrisponde: cancello il file scaricato."
      rm -f -- "$F.part"
      exit 1
    fi
    mv -f -- "$F.part" "$F"
    echo "integro: $F"
    ;;
  installa)
    [ -x "$SERVER" ] || { echo "Manca $SERVER: prima $0 compila"; exit 1; }
    [ -f "$DIR/modelli/$MODELLO" ] || { echo "Manca il modello: prima $0 scarica"; exit 1; }
    U="$HOME/.config/systemd/user/$UNITA.service"
    mkdir -p "$(dirname "$U")"
    sed -e "s|@DIR@|$DIR|g" -e "s|@PORTA@|$PORTA|g" -e "s|@MODELLO@|$MODELLO|g" \
        -e "s|@BEAM@|$BEAM|g" -e "s|@PROMPT@|$PROMPT|g" "$QUI/calliope-whisper.service" > "$U.tmp"
    mv -f -- "$U.tmp" "$U"
    systemctl --user daemon-reload
    systemctl --user enable "$UNITA" >/dev/null
    systemctl --user restart "$UNITA"
    echo "Unità installata e avviata: $U"
    # calliope.service (setup/linux/calliope.service) ha già Wants= e After= su questa unità
    if [ -f "$HOME/.config/systemd/user/calliope.service" ] && \
       ! grep -q "Wants=.*$UNITA" "$HOME/.config/systemd/user/calliope.service"; then
      echo "Attenzione: calliope.service non aspetta ancora il server (versione vecchia):"
      echo "  calliope aggiorna   (l'unità nuova ha Wants=/After=$UNITA.service)"
    fi
    for _ in $(seq 1 30); do pronto && { echo "Il server risponde su http://127.0.0.1:$PORTA."; exit 0; }; sleep 1; done
    echo "Il server non risponde ancora: $0 log"
    exit 1
    ;;
  avvia)   systemctl --user start "$UNITA" ;;
  ferma)   systemctl --user stop "$UNITA" ;;
  log)     journalctl --user -u "$UNITA" -f -n 50 ;;
  stato)
    if pronto; then echo "$UNITA risponde sulla porta $PORTA."; else echo "$UNITA non risponde sulla porta $PORTA."; fi
    systemctl --user is-enabled "$UNITA" 2>/dev/null | sed 's/^/abilitata: /' || true
    systemctl --user is-active "$UNITA" 2>/dev/null | sed 's/^/stato: /' || true
    [ -x "$SERVER" ] && echo "programma: $SERVER" || echo "programma: manca ($0 compila)"
    [ -f "$DIR/modelli/$MODELLO" ] && echo "modello: $DIR/modelli/$MODELLO" || echo "modello: manca ($0 scarica)"
    ;;
  *)
    echo "Uso: $0 compila|scarica|installa|avvia|ferma|stato|log [--si]" >&2
    exit 2
    ;;
esac
