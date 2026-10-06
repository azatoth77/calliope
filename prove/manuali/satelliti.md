# Prove manuali del satellite e prima prova con la DGX

*Passi spostati da `prove/LEGGIMI.md` il 06/10/2026. I comandi si lanciano dalla radice del repository.*

## Prova manuale del satellite sul portatile

Server e satellite sullo stesso portatile, con microfono e casse veri: è la stessa forma della
DGX, senza la rete. **Prima chiudere Calliope se è accesa** (il lucchetto è la porta 47913: con
due istanze il microfono sarebbe conteso).

1. In `calliope.locale.yaml`, sezione `server_satelliti` (dal 05/10; vale anche sotto `satellite`): `audio_modo: satellite` (Calliope userà il
   satellite); il resto può restare predefinito (127.0.0.1:8771, niente TLS sulla stessa
   macchina).
2. Primo terminale: `python -m calliope`. Nel riassunto: `audio: microfono e casse del
   satellite`, `satelliti: …`, poi `[SATELLITE] aspetto un satellite su ws://127.0.0.1:8771…`.
3. Secondo terminale: `python avvia_satellite.py` (C920 e I52 per nome) o
   `python -m calliope.satellite`. La prima volta stampa `Codice di abbinamento: 123 456`.
4. Terzo terminale: `python -m calliope.satellite --abbina 123456 --stanza studio`. Il
   satellite scrive `Abbinato come «studio»`, si collega, dice il saluto e stampa l'eco
   misurata (`Eco sentita durante il saluto: N %`); Calliope stampa `studio pronto`.
5. «Calliope, che ore sono?» → risposta dalle casse. Prima di dire il nome, una frase qualunque
   non deve far comparire nulla nel terminale di Calliope (l'audio resta sul satellite).
6. «Calliope, raccontami una storia lunga», poi a metà «Calliope, basta»: si ferma subito
   (`[BARGE-IN] nome sentito sul satellite`), poi resta in ascolto.
7. Timer: «Calliope, metti un timer di 30 secondi»: allo scadere segnale e annuncio dalle casse
   del satellite.
8. Riconnessione: chiudere Calliope (Ctrl+C) e riaprirla: il satellite scrive «Server non
   raggiungibile… riprovo» e si ricollega da solo, senza ripetere il saluto. Chiudere il
   satellite e riaprirlo: Calliope scrive `studio scollegato`, poi `collegato`.
9. Facoltativo: con `schermi_enabled: true` il satellite apre la pagina degli schermi in una
   finestra di Edge (`satellite_schermo: finestra`; `no` per non aprirla).
10. Alla fine rimettere `audio_modo: locale` (o togliere la riga) in `calliope.locale.yaml`.

Avvio automatico del satellite all'accesso: `powershell -ExecutionPolicy Bypass -File
setup\satellite\avvio_automatico.ps1` (`-Togli` per toglierlo).

## Un PC nuovo come satellite con un comando (03/10)

Su un PC Windows **senza niente installato** (né Python né il repository): il server serve la
pagina `https://<server>:8770/satellite` (o `https://<server>:8771/installa`, che va anche con
gli schermi spenti) con il comando da incollare in PowerShell. Il PC non conosce il certificato
del server: il comando fissa la **chiave** del certificato dei satelliti (`sha256//…`) e curl
scarica solo se il server ha quella. Prerequisiti sul server: `audio_modo: satellite`,
`satellite_indirizzo: 0.0.0.0` e `calliope satellite --certificato`, come nella prova
end-to-end qui sotto.

Il posto giusto per provarlo è **Windows Sandbox** (Windows 11 Pro o Enterprise: «Attiva o
disattiva funzionalità di Windows» → Windows Sandbox, poi riavvio): un Windows pulito e usa e
getta, con la rete del PC (con la VPN accesa sul portatile la DGX si raggiunge). Per il
microfono serve un file `.wsb` con `<AudioInput>Enable</AudioInput>`. Vanno bene anche una VM
di Hyper-V o un PC di prova.

1. Sulla DGX: `calliope satellite --elenco`. Stampa la riga «Chiave per i PC nuovi:
   sha256//…» e il comando completo.
2. Nel PC pulito: Edge su `https://<IP della DGX>:8770/satellite`. L'avviso del certificato è
   atteso (Avanzate → Continua): la pagina non è fidata, conta la chiave. Controlla che la
   chiave della pagina sia **identica** a quella del punto 1, poi copia il comando.
3. PowerShell normale (non da amministratore), incolla. Lo script scarica uv da GitHub (SHA-256
   fissato), Python 3.14.8, le librerie da PyPI (versioni e SHA-256 di `uv.lock`) e il pacchetto
   dalla DGX (SHA-256 del manifesto). Chiede l'avvio all'accesso e avvia il satellite, che
   stampa il codice. In locale ci ha messo ~30 s. Prova anche a cambiare un carattere della
   chiave nel comando: deve fermarsi con «curl: (90)» e «Installazione fermata», senza aver
   scritto niente.
4. Sulla DGX: `calliope satellite --abbina <codice> --stanza prova`. Il satellite si collega e
   dice il saluto.
5. Aggiornamento: un `calliope aggiorna` sulla DGX che tocca il codice del satellite. Alla
   riconnessione il satellite scrive `[AGGIORNA] Il server ha la versione …`, poi
   `Versione … pronta`, e si riavvia quando nessuno parla da 20 s. In
   `%LOCALAPPDATA%\Calliope\satellite\avvio.log` compaiono «passo alla versione … in prova» e
   «confermata». Se la versione nuova non si ricollega entro 180 s torna da sola alla precedente
   («torno a …») e non la riprova per 6 ore.

Per disinstallare: chiudi il satellite, cancella `%LOCALAPPDATA%\Calliope\satellite` e il
collegamento «Satellite di Calliope» in `shell:startup`; sulla DGX `calliope satellite --revoca
prova`. Il satellite del repository (`python -m calliope.satellite`) non si aggiorna mai da solo.

Prova end-to-end del 03/10 qui (server di prova su 127.0.0.1, satellite vero sotto `avvio.py`):
installazione in 31 s, abbinamento, aggiornamento confermato in 6 s; la versione che non si
ricollegava è tornata indietro dopo i 45 s di prova impostati e non è stata riprovata.

## Prima prova end-to-end con la DGX (satellite in VPN)

Prerequisiti: Calliope installata sulla DGX (`calliope stato` va), VPN accesa sul portatile,
`wakeword/modelli/` sul portatile.

Sulla DGX (`ssh dgx`):

```sh
calliope satellite --certificato           # crea ~/calliope/satellite.crt e .key, stampa l'impronta
# in ~/calliope/calliope.locale.yaml, sezione server_satelliti (prima satellite: va bene lo stesso):
#   audio_modo: satellite
#   satellite_indirizzo: 0.0.0.0
# (facoltativo, per lo schermo: sezione schermi, schermi_indirizzo: 0.0.0.0)
calliope riavvia && calliope log           # «[SATELLITE] aspetto un satellite su wss://0.0.0.0:8771…»
```

Se il firewall della DGX è acceso (`sudo ufw status`), aprire la porta solo verso la rete della
VPN: `sudo ufw allow from <rete della VPN> to any port 8771 proto tcp` (e 8770 per lo schermo).

Sul portatile, in `calliope.locale.yaml` (con l'indirizzo della DGX in VPN; mai nel codice):

```yaml
satellite:
  satellite_server: wss://<IP della DGX>:8771
```

poi `python avvia_satellite.py`: stampa il codice e l'impronta del server; sulla DGX
`calliope satellite --abbina <codice> --stanza studio`, che stampa la stessa impronta (devono
coincidere). Dopo l'abbinamento il satellite si collega, dice il saluto (sintetizzato sulla DGX)
e misura l'eco. Da provare e annotare:

- tempo dalla fine della frase alla prima voce (`[prima frase …]` nel log della DGX più il
  viaggio: a orecchio, o con `CALLIOPE_DEBUG_AUDIO`), confrontato con lo stesso giro sul
  portatile da solo;
- `ping <IP della DGX>` in VPN: il giro vero, da confrontare con i 50 ms della prova a secco;
- barge-in mentre racconta una storia; timer; spegnere e riaccendere la VPN (il satellite deve
  riprovare e ricollegarsi da solo);
- `calliope satellite --elenco` sulla DGX: ultima connessione aggiornata.
