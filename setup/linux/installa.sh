#!/bin/sh
# Prima installazione di Calliope su Linux (DGX Spark con DGX OS, Ubuntu 24.04 aarch64),
# 02/10/2026. Un comando, dalla cartella del repository:
#
#     sh setup/linux/installa.sh [--si] [opzioni di «calliope installa»]
#
# Cosa fa, senza sudo:
#  1. controlla i prerequisiti di sistema; se ne manca uno stampa il comando apt da
#     lanciare e si ferma (non usa sudo);
#  2. se manca uv (Astral), chiede se scaricarlo (~20 MB, installatore ufficiale in
#     ~/.local/bin); con --si non chiede;
#  3. passa a setup/linux/gestore.py: copia della sorgente, versione in una cartella sua
#     con il venv di uv dal lock, verifica, calliope.yaml, servizio systemd utente,
#     comando ~/.local/bin/calliope.
# Non scarica modelli (voci, LLM) da sola: lo dice `calliope stato`, e si fanno dopo, a
# richiesta. Le domande in più sono il modello di riserva di Whisper (1,6 GB, [s/N]) e, se
# c'è Docker, l'immagine della sandbox degli agenti (~290 MB, [s/N]).
# Il server di trascrizione con la GPU: setup/linux/motore/whisper.sh (calliope motore
# whisper compila|scarica|installa). Gli aggiornamenti: `calliope aggiorna` (con ritorno automatico se non parte).
set -eu

QUI=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$QUI/../.." && pwd)
SI=0
for a in "$@"; do [ "$a" = "--si" ] && SI=1; done

echo "Calliope: controllo dei prerequisiti…"
manca_apt=""
manca() { manca_apt="$manca_apt $1"; }

[ "$(uname -s)" = "Linux" ] || { echo "Questo installatore è per Linux."; exit 1; }
command -v python3 >/dev/null 2>&1 || manca python3
command -v git >/dev/null 2>&1 || manca git
command -v curl >/dev/null 2>&1 || manca curl
# PortAudio: il wheel di sounddevice su Linux non lo contiene (senza, Calliope non parte)
if ! ldconfig -p 2>/dev/null | grep -q 'libportaudio\.so\.2'; then manca libportaudio2; fi
# Facoltativi: tunnel SSH degli agenti verso un'altra macchina, font del PDF con «€»
command -v ssh >/dev/null 2>&1 || echo "  (facoltativo) manca ssh: sudo apt install openssh-client"
[ -d /usr/share/fonts/truetype/dejavu ] || echo "  (facoltativo) mancano i font DejaVu per i PDF: sudo apt install fonts-dejavu-core"

if [ -n "$manca_apt" ]; then
  echo ""
  echo "Mancano pacchetti di sistema. Lanciali tu (servono i permessi di amministratore):"
  echo "  sudo apt install$manca_apt"
  echo "poi rilancia: sh setup/linux/installa.sh"
  exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Serve python3 3.10 o più recente per il gestore (Ubuntu 24.04 ha la 3.12)."; exit 1; }

PATH_UTENTE="$PATH"
PATH="$HOME/.local/bin:$PATH"
export PATH
if ! command -v uv >/dev/null 2>&1; then
  echo ""
  echo "Manca uv (gestore dei pacchetti Python di Astral, ~20 MB): crea il venv dal lock."
  if [ "$SI" -ne 1 ]; then
    printf "Lo scarico dall'installatore ufficiale in ~/.local/bin? [s/N] "
    read -r risposta
    case "$risposta" in s|S|si|sì|SI) ;; *) echo "Installazione fermata."; exit 1 ;; esac
  fi
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
fi
echo "uv: $(uv --version)"

# Le opzioni per il gestore, senza --si
set -- $(for a in "$@"; do [ "$a" = "--si" ] || printf '%s\n' "$a"; done)
# Da dove si aggiornerà: il remoto «origin» del clone (per esempio il repository bare sulla
# DGX in cui il portatile fa push), altrimenti il clone stesso
SORGENTE=$(git -C "$REPO" remote get-url origin 2>/dev/null || echo "$REPO")
python3 "$QUI/gestore.py" installa --sorgente "$SORGENTE" "$@"

# Il modello di riserva di Whisper (faster-whisper su CPU, principio 7): sulla DGX trascrive
# il server whisper.cpp, e senza questo modello il primo guasto del server farebbe scaricare
# 1,6 GB con la voce ferma. Dal catalogo delle installazioni, con la sua conferma [s/N] e la
# verifica SHA-256 (calliope stato --installa). Solo da un terminale: senza, lo dice dopo.
echo ""
if [ -t 0 ]; then
  echo "Modello di riserva di Whisper, per trascrivere su CPU se il server non risponde:"
  "$HOME/.local/bin/calliope" stato --installa whisper_riserva || \
    echo "  (non installato: più tardi «calliope stato --installa whisper_riserva»)"
else
  echo "Modello di riserva di Whisper: calliope stato --installa whisper_riserva"
fi

# La sandbox degli agenti in un container (03/10): se Docker c'è e questo utente lo usa,
# l'immagine si costruisce con la sua conferma [s/N] (~290 MB). Senza, il codice degli agenti
# gira nel motore «processo» e «calliope stato» lo dice.
echo ""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if [ -t 0 ]; then
    echo "Sandbox degli agenti: un container senza rete per il codice che scrivono."
    "$HOME/.local/bin/calliope" motore sandbox costruisci ||       echo "  (non costruita: più tardi «calliope motore sandbox costruisci»)"
  else
    echo "Sandbox degli agenti in un container: calliope motore sandbox costruisci"
  fi
else
  echo "Sandbox degli agenti: senza Docker il codice gira in un processo limitato (calliope stato)."
fi

echo ""
echo "Fatto. Prossimi passi:"
echo "  calliope stato            cosa funziona e cosa manca (modelli, voci, audio)"
echo "  calliope avvia            avvia il servizio; calliope log per seguirlo"
echo "  loginctl enable-linger $USER   (una volta) per farla partire all'accensione"
case ":$PATH_UTENTE:" in *":$HOME/.local/bin:"*) ;; *)
  echo "  (aggiungi ~/.local/bin al PATH: Ubuntu lo fa da solo al prossimo accesso)";;
esac
