# 0024. Niente internet quando se ne può fare a meno: il meteo di casa

- **Stato**: accettata (09/10/2026)
- **Area**: [casa](../aree/casa.md), [voce-e-regole](../aree/voce-e-regole.md)

## Contesto

«Che tempo fa?» senza un luogo deve voler dire il tempo di casa. Home Assistant conosce le coordinate
della casa; per trasformarle in un nome di città servirebbe un servizio di geocodifica su internet.

## Decisione

Decisione di chi amministra (09/10): il meteo senza luogo è quello di casa, e **niente internet
quando se ne può fare a meno**. In ordine:

1. un'entità meteo di Home Assistant, se è esposta (`meteo_leggi`, anche le previsioni), senza nessuna
   richiesta esterna;
2. altrimenti la **città della casa** dalla configurazione (`casa_citta`: la città o il paese, mai
   l'indirizzo), con l'estensione del meteo o la ricerca web;
3. altrimenti Calliope chiede dove si trova la casa, e chi amministra può farla ricordare a voce
   (`citta_casa_salva`).

## Alternative considerate

- **Convertire le coordinate con un servizio esterno** (geocodifica inversa): scartata, manderebbe la
  posizione della casa fuori per un dato che si può chiedere una volta.
- **GPS o servizi di mappe** (Nominatim, Pelias, OSRM): già esclusi il 01/10; la posizione di casa è
  configurazione.

## Conseguenze

- La città entra nel prompt di sistema per tutti i livelli (è un dato poco sensibile, mai
  l'indirizzo) e non conta come dato esterno nel controllo della provenienza.
- È un esempio del principio generale ([0001](0001-tutto-in-locale.md)): internet è un extra, e ciò che
  esce va ridotto al minimo.

## Fonti

- [casa](../aree/casa.md), «Il meteo di casa»
- [voce-e-regole](../aree/voce-e-regole.md), «La città della casa e le estensioni nel prompt»
- [`2026-10-01-mappe-e-schermi.md`](../ricerche/2026-10-01-mappe-e-schermi.md) § 1
