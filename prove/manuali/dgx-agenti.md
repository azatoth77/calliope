# Prima prova sulla DGX Spark (agenti)

*Passi spostati da `prove/LEGGIMI.md` il 06/10/2026. I comandi si lanciano dalla radice del repository.*

## Prima prova sulla DGX Spark (agenti, 02/10/2026)

La DGX in ufficio si raggiunge solo in VPN; Calliope ci arriva con un tunnel SSH aperto da
sola (`ssh -N -L 11436:127.0.0.1:8000 dgx`), senza password e senza domande. Nessuna prova
automatica la contatta: questi passi sono a mano.

**Motore dell'agente sulla DGX: vLLM, non Ollama** (02/10). Ollama 0.35.0 della DGX va in
«CUDA error: an illegal memory access» con le richieste dell'agente che hanno gli strumenti
(vedi `docs/aree/setup-windows.md`, «Agenti per i lavori lunghi»); l'Ollama della DGX resta com'è e non si tocca. vLLM gira in
un container Docker dell'utente, senza sudo e senza servizi di sistema, solo su 127.0.0.1:

| | |
|---|---|
| Immagine | `vllm/vllm-openai:v0.29.0` (arm64, CUDA 13.0, torch 2.13; ~22 GB) — quella del playbook NVIDIA «vLLM» per DGX Spark per Qwen3.6 |
| Pesi | `nvidia/Qwen3.6-35B-A3B-NVFP4` (23,5 GB) in `~/calliope-motore/hf/` |
| Script | `~/calliope-motore/avvia.sh`, `ferma.sh`, `stato.sh`, `scarica.sh`; log di scaricamento in `~/calliope-motore/log/` |
| Container | `calliope-vllm`, porta `127.0.0.1:8000`; dal 04/10 con `setup/linux/motore/vllm.sh agente` (`calliope motore vllm agente avvia|rifai|ferma|stato|riprendi`): `--restart unless-stopped`, rete Docker sua `calliope-vllm`, modalità sviluppo con `PAUSA=1` (vedi sotto) |
| Nome servito | `qwen3.6-35b` (in `dgx.yaml`: `agente_modello`) |
| Memoria | `--gpu-memory-utilization 0.40` (~48 GB dei ~120 unificati: pesi 23 GB, KV cache fp8 22,5 GB, 2,1 milioni di token); il resto a Ollama e agli altri servizi |

```bash
# sulla DGX (ssh dgx)
~/calliope-motore/avvia.sh      # ~2,5 minuti la prima volta (compilazione), poi «Pronto.»
~/calliope-motore/stato.sh      # acceso? modelli serviti, memoria, ultime righe del log
~/calliope-motore/ferma.sh      # ferma e toglie il container; i pesi restano
docker logs -f calliope-vllm    # il log completo
# un altro modello (pesi prima con scarica.sh <repo>):
MODELLO=<repo HF> NOME=<nome servito> ~/calliope-motore/avvia.sh
```

Opzioni del server (in `avvia.sh`): `--enable-auto-tool-choice --tool-call-parser qwen3_xml`
(con `hermes` le chiamate di Qwen3.6 restano testo), `--reasoning-parser qwen3`,
`--kv-cache-dtype fp8 --attention-backend flashinfer --moe-backend marlin` (sul GB10, sm_121,
marlin è la via per l'NVFP4), `--max-model-len 131072 --max-num-seqs 4`, prefix caching. La
decodifica speculativa MTP del playbook (`--speculative-config`) **non parte** con la v0.29.0
(«moe_backend='marlin' is not supported for unquantized MoE»: lo strato MTP non è
quantizzato): in `avvia.sh` è spenta, e con un'immagine nuova si riprova con
`SPEC='{"method":"mtp","num_speculative_tokens":3,"moe_backend":"triton"}' ./avvia.sh`. Lo scaricamento con Xet di Hugging Face si è fermato a 0 byte/s: `scarica.sh`
usa l'HTTP normale (`HF_HUB_DISABLE_XET=1`), ~6 MB/s su quella linea (~65 minuti).

**Modalità sviluppo per la pausa dell'arbitro** (04/10). Con `VLLM_SERVER_DEV_MODE=1` vLLM
0.29.0 ha `POST /pause?mode=keep` e `POST /resume` (e `GET /is_paused`): l'arbitro di Calliope
congela le generazioni dell'agente mentre si parla invece di chiuderle (`docs/aree/agenti-estensioni.md`, «Pausa di
vLLM»). La stessa variabile apre anche, **senza chiave** (la `--api-key` di vLLM protegge solo
`/v1`, `/v2`, `/inference`, `/cohere`): `/abort_requests`, `/sleep`, `/wake_up`,
`/is_sleeping`, `/collective_rpc` (chiama un metodo dei worker per nome), `/init_weight_transfer_engine`,
`/start_weight_update`, `/start_draft_weight_update`, `/update_weights`, `/finish_weight_update`,
`/update_weight_version`, `/weight_info`, `/get_world_size`, `/reset_prefix_cache`,
`/reset_mm_cache`, `/reset_encoder_cache`, `/server_info` (configurazione e variabili `VLLM_*`
senza quelle con «KEY», informazioni di sistema). Mitigazioni: porta solo su 127.0.0.1 (come
prima) e una **rete Docker sua** (`calliope-vllm`): prima il container era sulla rete «bridge»
con i container di altri progetti, che potevano
raggiungerne l'IP (verificato dal registro: nessuno lo faceva, tutte le richieste da
127.0.0.1 attraverso docker-proxy; dopo, da quei container l'IP non risponde). Resta: ogni
processo della DGX può chiamare questi endpoint (fermare il server, svuotare la cache,
cambiare i pesi); poteva già usare `/v1`, e chi è nel gruppo docker comanda comunque i
container. Comandi:

```bash
calliope motore vllm agente stato        # anche «Modalità sviluppo accesa, pausa: {"is_paused":false}»
PAUSA=1 calliope motore vllm agente rifai   # ricrea il container (stessi argomenti di avvia.sh); ~3,5 minuti
PAUSA=0 calliope motore vllm agente rifai   # senza modalità sviluppo: l'arbitro torna a chiudere gli stream
calliope motore vllm agente riprendi     # POST /resume a mano (Calliope lo fa da sola all'avvio e a SIGTERM)
```

Senza `PAUSA` `rifai` tiene la scelta del container che sostituisce. Misure del 04/10: pausa
22 ms, ripresa 2 ms; la generazione congelata riparte senza rileggere il prompt, una richiesta
nuova arrivata in pausa aspetta la ripresa, uno stream chiuso in pausa si annulla (0 richieste
in corso dopo).

1. **SSH una volta a mano.** In `%USERPROFILE%\.ssh\config` l'alias (indirizzo, utente,
   chiave: Calliope non legge questo file e non stampa mai questi valori):

   ```
   Host dgx
       HostName <indirizzo della DGX nella VPN>
       User <utente>
       IdentityFile ~/.ssh/<chiave>
       ServerAliveInterval 30
   ```

   Con la VPN accesa: `ssh dgx` da un terminale, per accettare l'impronta della DGX (con
   `BatchMode=yes` Calliope non può farlo) e controllare che la chiave funzioni senza
   password. Se la chiave ha una passphrase: servizio «OpenSSH Authentication Agent»
   avviato e `ssh-add`.
2. **Il motore sulla DGX**: `~/calliope-motore/avvia.sh` (sopra). Con il motore «ollama»
   invece: Ollama solo su 127.0.0.1 e `ollama pull qwen3.6:35b`.
3. **`dgx.yaml`** accanto a `calliope.yaml` (c'è già: alias, `motore: openai`, «tunnel»,
   porte 8000 → 11436, `qwen3.6-35b`).
4. **Prova del collegamento** (apre il tunnel, chiede versione e modelli — `/version` e
   `/v1/models` con vLLM, `/api/version` e `/api/tags` con Ollama — chiude):

   ```powershell
   .\.venv\Scripts\python.exe -m calliope.agenti --prova
   ```

   Esito atteso (02/10): «ok tunnel aperto in 0.6 s», «ok Il server OpenAI (vLLM 0.29.0)
   risponde (25 ms)», «ok il modello agente qwen3.6-35b c'è», «Tutto pronto». Se no, la riga
   «NO» dice cosa fare (VPN spenta, chiave non caricata, impronta da accettare, porta 11436
   occupata, motore spento, modello non servito). `python -m calliope.stato` mostra la riga
   «agenti (lavori lunghi)». Va lanciato da PowerShell: l'ssh di Git Bash non legge
   `%USERPROFILE%\.ssh\config`.
5. **Banco contro la DGX** (lungo: 12 + 12 compiti, poi la contesa; i risultati restano nella
   cartella data):

   ```powershell
   .\.venv\Scripts\python.exe -u prove\prova_lavori.py --dgx --uscita C:\banco_dgx
   # solo una parte: --solo codice | --solo documenti | --solo contesa; --compiti c01,d10
   ```

   Soglie decise prima: codice ≥ 9/12 alla fine, documenti ≥ 10/12, contesa con l'arbitro ≤
   +0,15 s (con la DGX la GPU non è condivisa: la voce deve restare uguale). L'italiano dei
   documenti si giudica a mano sui file in `C:\banco_dgx\risultati`.
6. **A voce**: «Calliope, scrivimi uno script Python che rinomina le foto per data, con i
   test» → «È un lavoro di programmazione… Procedo?» → «Sì» → a lavoro finito il segnale, la
   frase e la scheda con il codice sullo schermo; i file in Documenti\Calliope\Lavori.
