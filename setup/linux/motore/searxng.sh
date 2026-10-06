#!/usr/bin/env bash
# Motore di ricerca web di Calliope sulla DGX Spark (03/10/2026): SearXNG in un container
# dell'utente, solo su 127.0.0.1, niente sudo. Lo usa il tool web_cerca (calliope/web/) per
# l'attualità (meteo, notizie, risultati, orari, prezzi) quando internet c'è; senza, Calliope
# funziona uguale e il registro delle capacità lo dice. Rapporto:
# docs/ricerche/2026-10-03-ricerca-web.md.
#
#   setup/linux/motore/searxng.sh avvia      crea (o riavvia) il container calliope-searxng
#   setup/linux/motore/searxng.sh ferma      lo ferma (resta, si riavvia con «avvia»)
#   setup/linux/motore/searxng.sh rimuovi    lo ferma e lo cancella (le impostazioni restano)
#   setup/linux/motore/searxng.sh stato      container, risposta e formato JSON
#   setup/linux/motore/searxng.sh prova      una ricerca vera («meteo Roma»): quanti risultati
#   setup/linux/motore/searxng.sh diagnosi   una copia per 20 secondi con i messaggi sullo
#                                            schermo (il container vero non ha log)
#
# Calliope lo usa con, in ~/calliope/calliope.locale.yaml:
#     web:
#       web_searxng_url: http://127.0.0.1:8004
#
# Se sulla macchina c'è già un altro SearXNG (di un altro progetto): questo
# script non lo tocca e Calliope non lo usa. Il container di Calliope:
# - immagine ufficiale searxng/searxng con tag e digest fissati (arm64 e amd64);
# - porta solo su 127.0.0.1 (PORTA, 8004): né la rete dell'ufficio né internet lo vedono;
# - utente searxng (977) e non root, file system di sola lettura, nessuna capability,
#   no-new-privileges; impostazioni montate in sola lettura, cache in memoria (tmpfs);
# - impostazioni minime (sotto): formato JSON acceso, lingua italiana, ricerca sicura
#   moderata, niente completamento automatico né proxy delle immagini, niente statistiche;
#   motori scelti per l'italiano (sotto, ENGINES);
# - niente log delle domande: il log degli accessi di granian è spento
#   (GRANIAN_LOG_ACCESS_ENABLED=false), ma SearXNG scrive comunque l'URL della richiesta a un
#   motore che non risponde («HTTP Request failed: GET https://search.brave.com/search?q=…»,
#   prova del 03/10). Per questo il container non ha log (--log-driver none): niente resta
#   sul disco. Per un problema c'è «diagnosi», che mostra i messaggi sullo schermo e basta.
#   Calliope manda le domande in POST, quindi nemmeno un URL verso SearXNG le contiene;
# - limite di frequenza: lo fa Calliope (web_max_minuto). Il limiter di SearXNG vuole un
#   server Valkey e serve alle istanze pubbliche: qui c'è un solo client, sulla stessa macchina.
#
# Valori cambiabili da ambiente: DIR (impostazioni, predefinita ~/calliope-motore/searxng),
# PORTA (8004), IMMAGINE.
set -euo pipefail

NOME=calliope-searxng
# Tag e digest dell'indice multi-architettura letti dal Docker Hub il 03/10/2026
IMMAGINE="${IMMAGINE:-searxng/searxng:2026.10.2-19ffbcd30@sha256:c642712fcedcdaa78fac44f71eada86aff510745826ba1bd1a368211fea2ce7f}"
PORTA="${PORTA:-8004}"
DIR="${DIR:-$HOME/calliope-motore/searxng}"
URL="http://127.0.0.1:$PORTA"
AZIONE="${1:-stato}"

# Motori per l'italiano: generali senza chiave d'accesso (DuckDuckGo, Brave, Startpage,
# Qwant, Mojeek, Bing), le notizie (ANSA, Bing News, DuckDuckGo News, Google News), Wikipedia e
# Wikidata e i cambi di valuta. Google web resta spento: chiede spesso il captcha a un indirizzo
# che fa molte ricerche. wttr.in (meteo) no: alla prova del 03/10 dava «parsing error», e le
# previsioni arrivano comunque dai siti di meteo (ilMeteo, 3B Meteo) nei risultati generali.
ENGINES=(duckduckgo brave startpage qwant mojeek bing wikipedia wikidata "bing news"
         "duckduckgo news" "google news" ansa currency)

impostazioni() {
  mkdir -p "$DIR"
  chmod 700 "$DIR"
  if [ ! -s "$DIR/segreto" ]; then
    (umask 077; head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' > "$DIR/segreto")
  fi
  local keep=""
  for e in "${ENGINES[@]}"; do keep+="      - \"$e\""$'\n'; done
  # Riscritto a ogni avvio dal testo qui sotto: segue gli aggiornamenti di Calliope. Il
  # segreto (chiave dei cookie di SearXNG, che qui non servono) resta lo stesso
  cat > "$DIR/settings.yml.tmp" <<EOF
# Generato da setup/linux/motore/searxng.sh: non modificarlo a mano (si riscrive a ogni avvio)
use_default_settings:
  engines:
    keep_only:
$keep
general:
  debug: false
  instance_name: "Calliope"
  enable_metrics: false
search:
  safe_search: 1
  autocomplete: ""
  default_lang: "it-IT"
  formats:
    - html
    - json
server:
  secret_key: "$(cat "$DIR/segreto")"
  limiter: false
  public_instance: false
  image_proxy: false
  method: "POST"
outgoing:
  request_timeout: 3.0
  max_request_timeout: 6.0
engines:
  - name: bing
    disabled: false
  - name: ansa
    disabled: false
EOF
  chmod 644 "$DIR/settings.yml.tmp"
  mv -f -- "$DIR/settings.yml.tmp" "$DIR/settings.yml"
}

pronto() {
  curl -fsS -m 3 -o /dev/null "$URL/healthz" 2>/dev/null
}

case "$AZIONE" in
  avvia)
    command -v docker >/dev/null 2>&1 || { echo "Manca docker."; exit 1; }
    impostazioni
    # Sempre da capo (~2 s): così immagine, opzioni e impostazioni sono quelle di questo
    # script anche dopo un aggiornamento di Calliope. Nel container non c'è niente da tenere
    docker rm -f "$NOME" >/dev/null 2>&1 || true
    docker run -d --name "$NOME" --restart unless-stopped \
      -p "127.0.0.1:$PORTA:8080" \
      --user 977:977 --read-only --cap-drop ALL --security-opt no-new-privileges \
      --tmpfs /var/cache/searxng:rw,size=64m,uid=977,gid=977 --tmpfs /tmp:rw,size=16m \
      -v "$DIR/settings.yml:/etc/searxng/settings.yml:ro" \
      -e GRANIAN_LOG_ACCESS_ENABLED=false -e FORCE_OWNERSHIP=false \
      --memory 1g --pids-limit 256 \
      --log-driver none \
      "$IMMAGINE" >/dev/null
    for _ in $(seq 1 30); do
      pronto && { echo "$NOME risponde su $URL (solo questa macchina)."; exit 0; }
      sleep 1
    done
    echo "$NOME non risponde ancora: $0 diagnosi"
    exit 1
    ;;
  ferma)   docker stop "$NOME" >/dev/null && echo "$NOME fermato." ;;
  rimuovi) docker rm -f "$NOME" >/dev/null 2>&1 || true; echo "$NOME rimosso (impostazioni in $DIR)." ;;
  log)     echo "Il container non ha log (conterrebbero le domande): $0 diagnosi" ;;
  diagnosi)
    # Una copia temporanea su un'altra porta, in primo piano: i messaggi vanno solo sullo
    # schermo e spariscono con lei (--rm). Una ricerca di prova per vedere i motori
    impostazioni
    P2=$((PORTA + 1000))
    echo "Copia di prova su 127.0.0.1:$P2 per 20 secondi…"
    docker run --rm --name "$NOME-diagnosi" -p "127.0.0.1:$P2:8080" \
      --user 977:977 --read-only --cap-drop ALL --security-opt no-new-privileges \
      --tmpfs /var/cache/searxng:rw,size=64m,uid=977,gid=977 --tmpfs /tmp:rw,size=16m \
      -v "$DIR/settings.yml:/etc/searxng/settings.yml:ro" \
      -e GRANIAN_LOG_ACCESS_ENABLED=false -e FORCE_OWNERSHIP=false "$IMMAGINE" &
    sleep 8
    curl -fsS -m 10 -o /dev/null -X POST --data-urlencode "q=prova" -d format=json \
      "http://127.0.0.1:$P2/search" && echo "(ricerca di prova fatta)" || echo "(ricerca di prova non riuscita)"
    sleep 12
    docker stop "$NOME-diagnosi" >/dev/null 2>&1 || true
    wait || true
    ;;
  stato)
    if docker container inspect "$NOME" >/dev/null 2>&1; then
      docker container inspect -f 'container: {{.State.Status}} (riavvio: {{.HostConfig.RestartPolicy.Name}})' "$NOME"
    else
      echo "container: non c'è ($0 avvia)"
    fi
    if pronto; then
      echo "risponde su $URL"
      if curl -fsS -m 5 -o /dev/null -X POST --data-urlencode "q=prova" -d format=json "$URL/search?format=json" 2>/dev/null; then
        echo "formato JSON: acceso"
      else
        echo "formato JSON: NON risponde (impostazioni vecchie? $0 avvia)"
      fi
    else
      echo "non risponde su $URL"
    fi
    ;;
  prova)
    pronto || { echo "$NOME non risponde su $URL: $0 avvia"; exit 1; }
    curl -fsS -m 15 -X POST --data-urlencode "q=${2:-meteo Roma}" -d format=json -d language=it-IT \
      "$URL/search" | python3 -c '
import json, sys
d = json.load(sys.stdin)
r = d.get("results") or []
a = d.get("answers") or []
giu = ", ".join(e[0] for e in d.get("unresponsive_engines") or []) or "nessuno"
print(len(r), "risultati,", len(a), "risposte dirette; motori che non rispondono:", giu)
for x in r[:5]:
    print(" -", x.get("engine"), "|", (x.get("title") or "")[:70])
'
    ;;
  *)
    echo "Uso: $0 avvia|ferma|rimuovi|stato|prova [domanda]|diagnosi" >&2
    exit 2
    ;;
esac
