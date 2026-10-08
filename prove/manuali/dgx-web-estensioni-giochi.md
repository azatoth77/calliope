# Ricerca su internet, estensioni e giochi sulla DGX

*Passi spostati da `prove/LEGGIMI.md` il 06/10/2026. I comandi si lanciano dalla radice del repository.*

## Ricerca su internet sulla DGX (SearXNG, 03/10)

```bash
# sulla DGX: il container calliope-searxng (solo 127.0.0.1:8004, niente log)
calliope motore searxng avvia
calliope motore searxng stato          # container, /healthz, formato JSON
calliope motore searxng prova "meteo Roma"   # una ricerca vera: risultati e motori giù
# in ~/calliope/calliope.locale.yaml, sezione web:
#   web_searxng_url: http://127.0.0.1:8004
#   web_dati_privati: ["<indirizzo di casa>", "<cognome>"]   # facoltativo
calliope riavvia
```

Poi a voce: «Calliope, che tempo fa domani a Milano?» (frase d'attesa, risposta con il sito
citato, scheda «Da internet» sugli schermi). `calliope stato` deve dire «ricerca web: SearXNG
risponde». Dal portatile, per provare il codice contro il SearXNG vero: `ssh -N -L
127.0.0.1:18004:127.0.0.1:8004 <alias>` e `web_searxng_url: http://127.0.0.1:18004`.

## Estensioni sulla DGX (04/10)

Le prove con il container vero e l'agente vero, da una copia del ramo (non tocca il servizio
né i suoi dati):

```sh
git archive <ramo> | ssh dgx 'mkdir -p ~/est-prova && tar -x -C ~/est-prova'
cd ~/est-prova && PY=~/.local/share/calliope/versioni/$(cat ~/.local/share/calliope/attuale)/.venv/bin/python
$PY prove/prova_estensioni.py --docker                     # container veri, attacchi, ~10 s
CALLIOPE_CONFIG=~/calliope/calliope.yaml $PY prove/prova_estensioni_agente.py --casa
$PY prove/prova_estensioni_attacchi.py --docker            # banco d'attacco, ~10 s
CALLIOPE_CONFIG=~/calliope/calliope.yaml $PY prove/prova_estensioni_agente.py --non-approvare \
    --compito "Crea un'estensione che legge la tabella delle regioni dalla pagina pubblica https://it.wikipedia.org/wiki/Regioni_d%27Italia e, data una regione, dice capoluogo e abitanti."
```

Serve l'immagine della sandbox (`calliope motore sandbox costruisci`): le estensioni usano la
stessa. Dal 05/10 l'immagine ha anche BeautifulSoup (nome nuovo, `calliope-sandbox:2269a79f10e2`):
dopo l'aggiornamento va ricostruita una volta, prima di quello il codice non si esegue
(«calliope stato» lo dice).

Prova a voce di un'estensione che legge un sito (05/10, dopo l'aggiornamento): «Calliope, crea
un'estensione che legge la tabella delle regioni da Wikipedia e mi dice capoluogo e abitanti
di una regione» → «Procedo?» → «sì» → in ~2 minuti l'annuncio con i permessi («legge pagine
pubbliche di internet…») e «Vuoi approvarla?» → «sì» → frase di sfida → «Calliope, quanti
abitanti ha la Toscana?». Nel registro delle uscite (`~/calliope/estensioni/uscite.jsonl`)
una riga per ogni pagina, con il solo host; `calliope stato --dettagli` ne dice il riepilogo.

## Giochi sulla DGX (05/10)

I test della logica dei giochi girano con Node in un container (immagine
`calliope-sandbox-node`, ~250 MB, `node:24.21.0-slim` senza npm): va costruita una volta, poi
l'agente fa girare i `*.test.js` con esegui_test (~0,2 s a esecuzione).

```sh
calliope motore sandbox costruisci javascript      # oppure setup/linux/motore/sandbox.sh costruisci javascript
cd ~/est-prova && CALLIOPE_CONFIG=~/calliope/calliope.yaml $PY prove/prova_estensioni_agente.py     --gioco --non-approvare --compito "Un gioco del memory per bambini sullo schermo: …"
```

Prova a voce (dopo l'aggiornamento, con uno schermo abbinato): «Calliope, fammi un gioco del
memory per i bambini» (sviluppo_apri gioco=true; anche un familiare adulto) → «Procedo?» →
«sì» → annuncio con «lo può approvare un adulto di casa» → «sì» (voce riconosciuta: niente
sfida) → «Calliope, giochiamo a memory»: la scheda compare sullo schermo da cui si parla. Per
Bianca: «abilita il memory per Bianca» (tutore), oppure Bianca lo chiede e la richiesta arriva al
tutore («Intanto: Bianca ti ha chiesto…»). «Oggi Bianca può giocare mezz'ora in più» lo dice
qualunque adulto riconosciuto.
