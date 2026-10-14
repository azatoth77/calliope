#!/usr/bin/env bash
# Il secondo server di trascrizione, per la corsia lenta della stanza (14/10/2026 sera,
# calliope/stanza/lenta.py, `stanza_lenta_stt_url`): lo stesso whisper.cpp compilato da
# whisper.sh (nessuna compilazione nuova), con large-v3 (non turbo) su un'altra porta.
#
# Perché: sulla DGX la corsia lenta usava il whisper-server dei turni (large-v3-turbo), che
# ignora il beam, senza il prompt dei turni: sulle 95 registrazioni conservate con il
# riferimento scritto a mano sbagliava il 4,8 % delle parole contro il 3,0 % dell'originale.
# La ritrascrizione si riaccende solo se questo server fa meglio dei turni sul banco
# (prove/manuali/banco_stanza_lenta.py --conservati).
#
# Il modello (scelta del 14/10 sera, docs/aree/stt-tts.md): large-v3 **q5_0** (1,08 GB di
# file, ~2 GB col calcolo, stima) **residente**: sulla DGX restano ~21 GB, FLUX a richiesta ne
# vuole 13, e con q5_0 il margine resta ~6 GB; f16 (3,1 GB di file, ~3,9 GB) solo se il banco
# dice che q5_0 perde qualità (VARIANTE=f16). Avviarlo e fermarlo a DGX libera farebbe
# risparmiare 2 GB al prezzo di un caricamento a ogni passo e di una gara con FLUX: non vale.
#
#   setup/linux/motore/whisper-lento.sh scarica      il modello, con verifica SHA-256
#   setup/linux/motore/whisper-lento.sh installa     l'unità calliope-whisper-lento.service
#   setup/linux/motore/whisper-lento.sh avvia|ferma|stato|memoria|log
#   setup/linux/motore/whisper-lento.sh disinstalla  ferma e toglie l'unità (il modello resta)
#
# scarica chiede conferma; --si per non chiedere. Serve whisper-server già compilato
# (`calliope motore whisper compila`). Calliope lo usa con, in ~/calliope/calliope.locale.yaml:
#     conversazione_stanza:
#       stanza_lenta_stt_url: http://127.0.0.1:8004/v1
# (con `stanza_lenta_ritrascrivi: auto`, di serie, la ritrascrizione allora si riaccende).
#
# Valori cambiabili da ambiente: DIR (la cartella di whisper.sh, ~/calliope-motore/whispercpp),
# PORTA (8004), BEAM (5), VARIANTE (q5_0 | f16).
set -euo pipefail

DIR="${DIR:-$HOME/calliope-motore/whispercpp}"
PORTA="${PORTA:-8004}"
BEAM="${BEAM:-5}"
VARIANTE="${VARIANTE:-q5_0}"
# Dal repository ufficiale ggerganov/whisper.cpp su Hugging Face, alla stessa revisione del
# modello dei turni; dimensioni e SHA-256 dichiarati da Hugging Face (API dei file, letti il
# 14/10/2026)
MODELLO_REV="5359861c739e955e79d9a303bcbc70fb988958b1"
case "$VARIANTE" in
  q5_0)
    MODELLO="ggml-large-v3-q5_0.bin"
    MODELLO_SHA="d75795ecff3f83b5faa89d1900604ad8c780abd5739fae406de19f23ecd98ad1"
    MODELLO_BYTE=1081140203
    ;;
  f16)
    MODELLO="ggml-large-v3.bin"
    MODELLO_SHA="64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2"
    MODELLO_BYTE=3095033483
    ;;
  *) echo "VARIANTE sconosciuta: $VARIANTE (q5_0 | f16)" >&2; exit 2 ;;
esac
MODELLO_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/$MODELLO_REV/$MODELLO"
UNITA="calliope-whisper-lento"
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
  # whisper-server risponde 200 su / (pagina di prova)
  curl -fsS -o /dev/null "http://127.0.0.1:$PORTA/" 2>/dev/null
}

memoria() {
  # La memoria vera del processo sulla GPU: nvidia-smi per processo (sul GB10 la memoria
  # totale è [N/A], quella dei processi no). La stessa lettura la fa `calliope stato --piano`
  local pid
  pid=$(systemctl --user show "$UNITA" --property=MainPID --value 2>/dev/null || echo 0)
  if [ -z "$pid" ] || [ "$pid" = "0" ]; then echo "memoria: il servizio non gira"; return 0; fi
  nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null \
    | awk -F', *' -v p="$pid" '$1 == p { printf "memoria: %.2f GB sulla GPU (processo %s)\n", $2 * 1048576 / 1e9, p; t = 1 }
                               END { if (!t) print "memoria: nvidia-smi non vede il processo" }'
}

case "$AZIONE" in
  scarica)
    F="$DIR/modelli/$MODELLO"
    mkdir -p "$DIR/modelli"
    if [ -f "$F" ] && [ "$(stat -c %s "$F")" = "$MODELLO_BYTE" ]; then
      echo -n "Il modello c'è già: verifico il checksum… "
      if echo "$MODELLO_SHA  $F" | sha256sum -c --status; then echo "integro."; exit 0; fi
      echo "NON corrisponde: lo riscarico."
    fi
    chiedi "Scarico $MODELLO da Hugging Face ($((MODELLO_BYTE / 1000000)) MB, revisione ${MODELLO_REV:0:12})?" || exit 1
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
    [ -x "$SERVER" ] || { echo "Manca $SERVER: prima «calliope motore whisper compila»"; exit 1; }
    [ -f "$DIR/modelli/$MODELLO" ] || { echo "Manca il modello: prima $0 scarica"; exit 1; }
    U="$HOME/.config/systemd/user/$UNITA.service"
    mkdir -p "$(dirname "$U")"
    sed -e "s|@DIR@|$DIR|g" -e "s|@PORTA@|$PORTA|g" -e "s|@MODELLO@|$MODELLO|g" \
        -e "s|@BEAM@|$BEAM|g" "$QUI/calliope-whisper-lento.service" > "$U.tmp"
    mv -f -- "$U.tmp" "$U"
    systemctl --user daemon-reload
    systemctl --user enable "$UNITA" >/dev/null
    systemctl --user restart "$UNITA"
    echo "Unità installata e avviata: $U"
    for _ in $(seq 1 60); do
      if pronto; then
        echo "Il server risponde su http://127.0.0.1:$PORTA."
        memoria
        echo "Per Calliope: stanza_lenta_stt_url: http://127.0.0.1:$PORTA/v1 nel calliope.locale.yaml"
        exit 0
      fi
      sleep 1
    done
    echo "Il server non risponde ancora: $0 log"
    exit 1
    ;;
  disinstalla)
    systemctl --user disable --now "$UNITA" 2>/dev/null || true
    rm -f -- "$HOME/.config/systemd/user/$UNITA.service"
    systemctl --user daemon-reload
    echo "Unità tolta (il modello resta in $DIR/modelli). Togli anche stanza_lenta_stt_url dal locale."
    ;;
  avvia)   systemctl --user start "$UNITA" ;;
  ferma)   systemctl --user stop "$UNITA" ;;
  log)     journalctl --user -u "$UNITA" -f -n 50 ;;
  memoria) memoria ;;
  stato)
    if pronto; then echo "$UNITA risponde sulla porta $PORTA."; else echo "$UNITA non risponde sulla porta $PORTA."; fi
    systemctl --user is-enabled "$UNITA" 2>/dev/null | sed 's/^/abilitata: /' || true
    systemctl --user is-active "$UNITA" 2>/dev/null | sed 's/^/stato: /' || true
    memoria
    [ -x "$SERVER" ] && echo "programma: $SERVER" || echo "programma: manca (calliope motore whisper compila)"
    [ -f "$DIR/modelli/$MODELLO" ] && echo "modello: $DIR/modelli/$MODELLO" || echo "modello: manca ($0 scarica)"
    ;;
  *)
    echo "Uso: $0 scarica|installa|avvia|ferma|stato|memoria|log|disinstalla [--si]" >&2
    exit 2
    ;;
esac
