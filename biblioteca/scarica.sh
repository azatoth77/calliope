#!/bin/sh
# Scarica gli ZIM italiani della biblioteca offline (calliope/biblioteca.py) dal mirror
# ftp.fau.de (~10 MB/s; download.kiwix.org diretto è lento), riprendendo se interrotto,
# con il checksum SHA-256 ufficiale accanto. Per aggiornare: nuove date nei nomi e in
# calliope.yaml (sezione biblioteca). Uso: sh biblioteca/scarica.sh
cd "$(dirname "$0")"
M=https://ftp.fau.de/kiwix/zim
for f in wikipedia/wikipedia_it_all_mini_2026-08.zim \
         wikipedia/wikipedia_it_all_nopic_2026-08.zim \
         vikidia/vikidia_it_all_nopic_2026-09.zim \
         wiktionary/wiktionary_it_all_nopic_2026-08.zim; do
  n=$(basename $f)
  echo "$(date +%H:%M:%S) inizio $n"
  curl -s -S -L -C - --retry 5 --retry-delay 5 -o "$n" "$M/$f" && echo "$(date +%H:%M:%S) fatto $n $(stat -c %s "$n")" || echo "$(date +%H:%M:%S) ERRORE $n"
  curl -s -L --max-time 30 -o "$n.sha256" "https://download.kiwix.org/zim/$f.sha256" || true
  if [ -s "$n.sha256" ]; then
    [ "$(cut -c1-64 "$n.sha256")" = "$(sha256sum "$n" | cut -c1-64)" ] && echo "   checksum ok" || echo "   CHECKSUM SBAGLIATO: riscaricare $n"
  fi
done
echo "$(date +%H:%M:%S) tutto finito"
# Dal 01/10 la ricerca per parole usa un indice SQLite FTS5 accanto ai file (biblioteca/indici/)
echo "Ora l'indice di ricerca (~4 minuti, 1,3 GB), dalla cartella di Calliope:"
echo "   python -m calliope.biblioteca_indice"
