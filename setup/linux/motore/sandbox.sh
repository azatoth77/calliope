#!/usr/bin/env bash
# Immagini Docker della sandbox degli agenti (03/10/2026): il codice scritto dall'agente gira
# in un container usa-e-getta, senza rete e con il disco in sola lettura
# (calliope/agenti/sandbox.py, motore «docker»; misure in docs/ricerche/2026-10-03-sandbox.md).
# Dal 04/10 un'immagine per linguaggio (calliope/agenti/linguaggi.py): python (sempre) e
# csharp (facoltativa, ~300 MB: runtime di .NET e compilatore, senza SDK né NuGet).
# javascript (facoltativa, ~200 MB: Node per i test della logica dei giochi, 05/10).
#
#   setup/linux/motore/sandbox.sh costruisci [python|csharp|javascript|tutte]
#                                       costruisce l'immagine (predefinita: python; chiede
#                                       conferma: scarica le immagini di base e le librerie)
#   setup/linux/motore/sandbox.sh stato        le immagini che Calliope cerca e se ci sono
#   setup/linux/motore/sandbox.sh prova        prova vera degli attacchi (prove/prova_sandbox.py
#                                              --docker) e dei programmi in diretta
#                                              (prove/prova_esecuzione.py --docker)
#   setup/linux/motore/sandbox.sh pulisci      toglie le immagini calliope-sandbox vecchie
#
# Oppure, con la versione installata: calliope motore sandbox costruisci [linguaggio]. Niente
# sudo: serve un utente che usa Docker (gruppo docker o Docker rootless). Il nome di ogni
# immagine è <prefisso>:<prime 12 cifre dello SHA-256 del suo Dockerfile> (calliope-sandbox:…,
# calliope-sandbox-dotnet:…), lo stesso che calcola Calliope: dopo un aggiornamento che cambia
# un Dockerfile quel linguaggio non si esegue («calliope stato» lo dice) finché non si
# ricostruisce.
set -euo pipefail

QUI=$(cd "$(dirname "$0")" && pwd)
RADICE=$(cd "$QUI/../../.." && pwd)
SB="$RADICE/setup/linux/sandbox"
SI=0
ARGS=()
for a in "$@"; do
  if [ "$a" = "--si" ]; then SI=1; else ARGS+=("$a"); fi
done
AZIONE="${ARGS[0]:-stato}"
LINGUAGGIO="${ARGS[1]:-python}"
LINGUAGGI="python csharp javascript"

chiedi() {
  [ "$SI" -eq 1 ] && return 0
  printf "%s [s/N] " "$1"
  read -r r || r=""
  case "$r" in s|S|si|sì|SI) return 0 ;; *) echo "Va bene, non faccio niente."; return 1 ;; esac
}

# linguaggio → Dockerfile, prefisso dell'immagine, cosa scarica
dockerfile() {
  case "$1" in
    python) echo "$SB/Dockerfile" ;;
    csharp) echo "$SB/Dockerfile.dotnet" ;;
    javascript) echo "$SB/Dockerfile.node" ;;
    *) return 1 ;;
  esac
}
prefisso() {
  case "$1" in
    python) echo "calliope-sandbox" ;;
    csharp) echo "calliope-sandbox-dotnet" ;;
    javascript) echo "calliope-sandbox-node" ;;
  esac
}
scarica() {
  case "$1" in
    python) echo "python:3.12-slim da Docker Hub e numpy, openpyxl, python-docx, fpdf2, PyYAML, BeautifulSoup da PyPI (~290 MB)" ;;
    csharp) echo "dotnet/sdk:10.0.401 e dotnet/runtime:10.0.12 da mcr.microsoft.com (~1 GB da scaricare; immagine finale ~300 MB)" ;;
    javascript) echo "node:24.21.0-slim da Docker Hub, per i test dei giochi (~80 MB da scaricare, npm tolto)" ;;
  esac
}
# Lo stesso nome che calcola Calliope: prefisso + prime 12 cifre dello SHA-256 del Dockerfile
immagine() { echo "$(prefisso "$1"):$(sha256sum "$(dockerfile "$1")" | cut -c1-12)"; }

docker_ok() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker non c'è: senza, Calliope non esegue il codice degli agenti."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker non risponde, o questo utente non lo può usare (gruppo docker o Docker rootless)."
    exit 1
  fi
}

costruisci() {
  local l="$1" df img
  df=$(dockerfile "$l") || { echo "Linguaggio sconosciuto: $l (python, csharp, javascript, tutte)"; exit 2; }
  [ -f "$df" ] || { echo "Manca $df"; exit 1; }
  img=$(immagine "$l")
  if docker image inspect "$img" >/dev/null 2>&1; then
    echo "L'immagine $img c'è già."
    return 0
  fi
  echo "Costruisco $img da $df."
  echo "Scarica $(scarica "$l")."
  chiedi "Procedo?" || return 0
  docker build --pull -t "$img" -f "$df" "$SB"
  echo "Fatto. Calliope la usa al prossimo lavoro di codice (con agenti_sandbox_motore: auto o docker)."
}

case "$AZIONE" in
  costruisci)
    docker_ok
    if [ "$LINGUAGGIO" = "tutte" ]; then
      for l in $LINGUAGGI; do costruisci "$l"; done
    else
      costruisci "$LINGUAGGIO"
    fi
    ;;
  stato)
    docker_ok
    for l in $LINGUAGGI; do
      img=$(immagine "$l")
      if docker image inspect "$img" >/dev/null 2>&1; then
        echo "$l: $img c'è."
      else
        echo "$l: $img non c'è (calliope motore sandbox costruisci $l)."
      fi
    done
    ;;
  prova)
    docker_ok
    PY="${PYTHON:-}"
    [ -n "$PY" ] || { [ -x "$RADICE/.venv/bin/python" ] && PY="$RADICE/.venv/bin/python"; } || PY=python3
    cd "$RADICE" && "$PY" prove/prova_sandbox.py --docker && "$PY" prove/prova_esecuzione.py --docker
    ;;
  pulisci)
    docker_ok
    vecchie=""
    for l in $LINGUAGGI; do
      img=$(immagine "$l")
      vecchie="$vecchie $(docker images "$(prefisso "$l")" --format '{{.Repository}}:{{.Tag}}' | grep -vx "$img" || true)"
    done
    vecchie=$(echo $vecchie)
    if [ -z "$vecchie" ]; then echo "Nessuna immagine vecchia."; exit 0; fi
    echo "Immagini vecchie: $vecchie"
    chiedi "Le tolgo?" || exit 0
    # shellcheck disable=SC2086
    docker rmi $vecchie
    ;;
  *)
    echo "uso: $0 costruisci [python|csharp|javascript|tutte]|stato|prova|pulisci [--si]"
    exit 2
    ;;
esac
