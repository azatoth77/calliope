#!/usr/bin/env bash
# Server vLLM per la voce e per Whisper sulla DGX Spark (02/10/2026), accanto a quello
# dell'agente (container calliope-vllm, porta 8000, script in ~/calliope-motore/: vedi
# prove/LEGGIMI.md). Stessa immagine, che su questa DGX funziona con il driver di DGX OS;
# container dell'utente, solo su 127.0.0.1, niente sudo.
#
#   setup/linux/motore/vllm.sh voce avvia|ferma|stato    gemma per la voce, porta 8001
#     (03/10: Gemma 4 26B-A4B NVFP4, container calliope-vllm-voce, si riaccende da solo dopo
#     un riavvio della DGX; Calliope lo usa con `llm_profilo: gemma4-26b-vllm` in
#     calliope.locale.yaml, vedi docs/ricerche/2026-10-03-modello-davanti.md. Per tornare al
#     4B di Ollama: `llm_profilo: gemma4-e4b-ollama`, `calliope riavvia`, poi `vllm.sh voce
#     ferma` per liberare la memoria)
#   setup/linux/motore/vllm.sh agente avvia|rifai|ferma|stato|riprendi   l'agente, porta 8000
#     (04/10: Qwen3.6-35B-A3B NVFP4, container calliope-vllm, gli stessi argomenti di
#     ~/calliope-motore/avvia.sh, che resta per la prima installazione; vedi prove/LEGGIMI.md).
#     PAUSA=1 accende la modalità sviluppo di vLLM (VLLM_SERVER_DEV_MODE=1) per
#     `POST /pause?mode=keep` e `/resume`: con l'agente sulla GPU della voce l'arbitro di
#     Calliope congela le generazioni mentre si parla invece di chiuderle (niente passo perso,
#     calliope/agenti/arbitro.py). Predefinito: quello del container che si sostituisce,
#     altrimenti spenta. Perché spenta di predefinito: la modalità sviluppo apre anche
#     /sleep, /collective_rpc, /update_weights, /reset_prefix_cache, /server_info… senza
#     chiave (la --api-key di vLLM protegge solo /v1); va accesa sapendolo, ed è l'unico
#     modo di rifare il container senza perderla per sbaglio. Mitigazioni sempre attive per
#     l'agente: porta solo su 127.0.0.1 e una rete Docker sua (RETE, predefinita
#     calliope-vllm), così i container di altri progetti sulla rete «bridge» non
#     arrivano all'IP del container. `riprendi`: POST /resume a mano (se Calliope fosse morta
#     con vLLM in pausa; Calliope lo fa da sola all'avvio)
#   setup/linux/motore/vllm.sh stt  avvia|ferma|stato    Whisper large-v3-turbo, porta 8002
#   setup/linux/motore/vllm.sh stt  immagine             costruisce l'immagine con l'audio
#
# Whisper su vLLM è SCARTATO (02/10, sulla DGX): senza beam search la WER sulle registrazioni
# con riferimento era 21 %, contro 12,4 % di whisper.cpp con -bs 5 (setup/linux/motore/
# whisper.sh, il server in uso) e 11,0 % di faster-whisper sul portatile. «stt» resta qui
# solo per rifare il confronto.
#
# NON scarica modelli: se i pesi non sono nella cache si ferma e dice il comando, da
# lanciare a mano solo dopo averlo deciso (sono GB). Valori cambiabili da ambiente:
# IMMAGINE, HF (cartella della cache di Hugging Face), MODELLO, NOME (nome servito),
# PORTA, MEM (--gpu-memory-utilization: frazione dei ~119 GB unificati), CONTESTO.
#
# Memoria: agente 0,40 + voce 0,24 (26B: 17,5 GiB di pesi, il resto cache fp8 per 32k token)
# = 0,64; Whisper ora è whisper.cpp, fuori da vLLM (~2 GB). Le note NVIDIA per DGX Spark
# consigliano di non superare ~0,7 in tutto (memoria unificata: il resto serve al sistema,
# a Ollama se acceso e a Calliope). Da misurare con nvidia-smi alla prima prova.
set -euo pipefail

RUOLO="${1:-}"
AZIONE="${2:-stato}"
BASE="vllm/vllm-openai:v0.29.0"
# L'immagine ufficiale non ha l'extra «audio» di vLLM (soundfile, av, soxr…): con Whisper
# ogni richiesta dava 400 «Invalid or unsupported audio file» («Please install vllm[audio]»,
# prima prova sulla DGX, 02/10). Per Whisper serve un'immagine derivata, costruita qui con
# `vllm.sh stt immagine` (scarica solo quei pacchetti, con le versioni dell'immagine fisse).
IMMAGINE_AUDIO="calliope-vllm-audio:v0.29.0"
HF="${HF:-$HOME/calliope-motore/hf}"

RETE_PROPRIA=""
AMBIENTE=()
case "$RUOLO" in
  agente)
    CONTAINER=calliope-vllm
    IMMAGINE="${IMMAGINE:-$BASE}"
    PORTA="${PORTA:-8000}"
    MODELLO="${MODELLO:-nvidia/Qwen3.6-35B-A3B-NVFP4}"
    NOME="${NOME:-qwen3.6-35b}"
    MEM="${MEM:-0.40}"
    RIAVVIO="${RIAVVIO:-unless-stopped}"
    RETE_PROPRIA="${RETE:-calliope-vllm}"
    # Le opzioni di ~/calliope-motore/avvia.sh (prove/LEGGIMI.md): parser qwen3_xml (con
    # hermes le chiamate restano testo), marlin per l'NVFP4 sul GB10, MTP spenta (non parte
    # con la v0.29.0)
    OPZIONI=(--tensor-parallel-size 1 --trust-remote-code
             --max-model-len "${CONTESTO:-131072}" --max-num-seqs 4
             --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching
             --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3)
    case "$MODELLO" in
      *NVFP4*) OPZIONI+=(--kv-cache-dtype fp8 --attention-backend flashinfer --moe-backend marlin) ;;
    esac
    # Modalità sviluppo: se PAUSA non è data, quella del container di adesso
    if [ -z "${PAUSA:-}" ]; then
      if docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
          | grep -qx 'VLLM_SERVER_DEV_MODE=1'; then PAUSA=1; else PAUSA=0; fi
    fi
    [ "$PAUSA" = 1 ] && AMBIENTE+=(-e VLLM_SERVER_DEV_MODE=1)
    ;;
  voce)
    CONTAINER=calliope-vllm-voce
    IMMAGINE="${IMMAGINE:-$BASE}"
    PORTA="${PORTA:-8001}"
    MODELLO="${MODELLO:-nvidia/Gemma-4-26B-A4B-NVFP4}"
    NOME="${NOME:-gemma4-26b}"
    MEM="${MEM:-0.24}"
    RIAVVIO="${RIAVVIO:-unless-stopped}"
    # Parser dei tool e del ragionamento di Gemma 4 (scheda del modello NVIDIA). Il thinking
    # lo spegne Calliope con chat_template_kwargs (profilo gemma4-26b-vllm). NVFP4: cache
    # fp8 e MoE con i kernel CUTLASS (marlin dà la stessa velocità, ~29 token/s, 03/10).
    OPZIONI=(--enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4
             --max-model-len "${CONTESTO:-32768}" --max-num-seqs 4
             --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching
             --trust-remote-code)
    case "$MODELLO" in
      *NVFP4*) OPZIONI+=(--kv-cache-dtype fp8 --moe-backend "${MOE:-cutlass}") ;;
    esac
    ;;
  stt)
    CONTAINER=calliope-stt
    IMMAGINE="${IMMAGINE:-$IMMAGINE_AUDIO}"
    PORTA="${PORTA:-8002}"
    MODELLO="${MODELLO:-openai/whisper-large-v3-turbo}"
    NOME="${NOME:-whisper-large-v3-turbo}"
    MEM="${MEM:-0.06}"
    RIAVVIO="${RIAVVIO:-no}"
    # L'encoder di Whisper vuole 1500 token per clip (30 s di audio): senza un budget più
    # grande vLLM 0.29 non parte («max_tokens_per_mm_item (1500) is larger than
    # max_num_batched_tokens (896)», prima prova sulla DGX, 02/10)
    OPZIONI=(--max-num-seqs 2 --max-num-batched-tokens 2048)
    ;;
  *)
    echo "Uso: $0 agente|voce|stt avvia|ferma|stato|immagine (anche rifai; agente: riprendi)" >&2
    exit 2
    ;;
esac

pesi_presenti() {
  local dir="models--${MODELLO//\//--}"
  [ -d "$HF/hub/$dir" ] || [ -d "$HF/$dir" ]
}

pronto() {
  curl -fsS "http://127.0.0.1:$PORTA/v1/models" >/dev/null 2>&1
}

case "$AZIONE" in
  immagine)
    # Solo i pacchetti dell'extra audio; «-c» con le versioni già installate: torch, numpy
    # e il resto dell'immagine non cambiano
    printf '%s\n' "FROM $BASE" \
      'RUN pip freeze > /tmp/fissi.txt && pip install --no-cache-dir -c /tmp/fissi.txt av scipy soundfile soxr "mistral_common[audio]" && python3 -c "import soundfile, av, soxr"' \
      | docker build -t "$IMMAGINE_AUDIO" -
    exit $?
    ;;
  avvia|rifai)
    # rifai: toglie il container e lo ricrea anche se risponde (per cambiare PAUSA o RETE)
    if [ "$AZIONE" = avvia ] && pronto; then echo "$CONTAINER risponde già sulla porta $PORTA."; exit 0; fi
    if ! docker image inspect "$IMMAGINE" >/dev/null 2>&1; then
      echo "Manca l'immagine $IMMAGINE. Non la preparo da sola (scarica pacchetti):"
      echo "  $0 $RUOLO immagine"
      exit 1
    fi
    if ! pesi_presenti; then
      echo "Mancano i pesi di $MODELLO in $HF. Non li scarico da solo."
      echo "Quando hai deciso (sono GB), per esempio:"
      echo "  HF_HOME=$HF HF_HUB_DISABLE_XET=1 hf download $MODELLO"
      exit 1
    fi
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    # Come il container dell'agente (~/calliope-motore/avvia.sh): utente non root, cache di
    # torch.compile e Triton in ~/calliope-motore/cache (un riavvio non ricompila: ~1 minuto
    # invece di ~4 al primo avvio, quasi tutto lettura dei pesi)
    CACHE="${CACHE:-$HOME/calliope-motore/cache}"
    mkdir -p "$CACHE"
    # Gemma 4: il modello di chat corretto (gemma4_template.py: thinking spento anche dopo il
    # risultato di un tool, altrimenti a volte ragiona per secondi in silenzio)
    if [ "$RUOLO" = voce ] && [[ "$MODELLO" == *[Gg]emma-4* ]]; then
      ORIG=$(ls "$HF"/hub/models--${MODELLO//\//--}/snapshots/*/chat_template.jinja 2>/dev/null | head -1)
      if [ -n "$ORIG" ] && python3 "$(dirname "$0")/gemma4_template.py" "$ORIG" "$CACHE/gemma4-voce.jinja"; then
        OPZIONI+=(--chat-template /cache/gemma4-voce.jinja)
      else
        echo "Attenzione: modello di chat di Gemma 4 non corretto (resta quello del checkpoint)."
      fi
    fi
    RETE_OPZ=()
    if [ -n "$RETE_PROPRIA" ]; then
      # Una rete Docker solo per questo container: niente vicini sulla rete «bridge»
      docker network inspect "$RETE_PROPRIA" >/dev/null 2>&1 \
        || docker network create "$RETE_PROPRIA" >/dev/null
      RETE_OPZ=(--network "$RETE_PROPRIA")
    fi
    if [ "${#AMBIENTE[@]}" -gt 0 ]; then
      echo "Modalità sviluppo di vLLM accesa (pausa e ripresa per l'arbitro): solo 127.0.0.1, rete $RETE_PROPRIA."
    fi
    docker run -d --name "$CONTAINER" --restart "$RIAVVIO" --gpus all --ipc=host \
      --user "$(id -u):$(id -g)" -p "127.0.0.1:$PORTA:8000" "${RETE_OPZ[@]}" "${AMBIENTE[@]}" \
      -e HOME=/cache -e HF_HOME=/hf -e HF_HUB_OFFLINE=1 \
      -e VLLM_CACHE_ROOT=/cache/vllm -e TRITON_CACHE_DIR=/cache/triton \
      -e FLASHINFER_WORKSPACE_BASE=/cache \
      -v "$HF:/hf" -v "$CACHE:/cache" \
      "$IMMAGINE" --model "$MODELLO" --served-model-name "$NOME" --host 0.0.0.0 \
      --port 8000 --gpu-memory-utilization "$MEM" "${OPZIONI[@]}" >/dev/null
    echo -n "Avvio di $CONTAINER ($MODELLO)…"
    for _ in $(seq 1 180); do
      if pronto; then echo " pronto su http://127.0.0.1:$PORTA/v1 (nome servito: $NOME)."; exit 0; fi
      if ! docker ps -q -f "name=^${CONTAINER}$" | grep -q .; then
        echo " il container si è fermato. Ultime righe del log:"
        docker logs --tail 30 "$CONTAINER" 2>&1 || true
        exit 1
      fi
      echo -n "."
      sleep 5
    done
    echo " non risponde dopo 15 minuti: docker logs -f $CONTAINER"
    exit 1
    ;;
  ferma)
    docker rm -f "$CONTAINER" >/dev/null 2>&1 && echo "$CONTAINER fermato." || echo "$CONTAINER non c'era."
    ;;
  riprendi)
    if [ "$RUOLO" != agente ]; then echo "riprendi vale solo per l'agente" >&2; exit 2; fi
    curl -fsS -X POST "http://127.0.0.1:$PORTA/resume" && echo \
      || { echo "Nessuna risposta da /resume (modalità sviluppo spenta o server giù)."; exit 1; }
    ;;
  stato)
    if pronto; then
      echo "$CONTAINER risponde sulla porta $PORTA:"
      curl -fsS "http://127.0.0.1:$PORTA/v1/models"; echo
      if [ "$RUOLO" = agente ]; then
        P=$(curl -fsS "http://127.0.0.1:$PORTA/is_paused" 2>/dev/null) \
          && echo "Modalità sviluppo accesa, pausa: $P" || echo "Modalità sviluppo spenta (niente /pause)."
      fi
    else
      echo "$CONTAINER non risponde sulla porta $PORTA."
    fi
    docker ps -a -f "name=^${CONTAINER}$" --format '{{.Names}}  {{.Status}}' || true
    ;;
  *)
    echo "Uso: $0 agente|voce|stt avvia|ferma|stato|immagine (anche rifai; agente: riprendi)" >&2
    exit 2
    ;;
esac
