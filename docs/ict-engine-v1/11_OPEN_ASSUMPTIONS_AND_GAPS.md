# Assunzioni e gap aperti
## Assunzioni adottate senza bloccare il lavoro
A1: reference Python standard library, non stack esistente. A2: clock UTC e bars close-time. A3: M5, pivot strict 2+2, ATR SMA14 lagged. A4: un trade globale e spot long-only default. A5: EUR account. A6: tutte le soglie preregistrate e rivedibili prima del holdout. A7: dati della reference sintetici, fee artificiali. A8: nessun broker reale, endpoint autenticato, deployment o invio ordini in questo pacchetto. A9: timeframe H1/context, blocchi complessi e ML fuori codice v1, dentro specifica sperimentale. A10: nessuna equivalenza tra metadata API generici ed entità accessibile all'utente.

|Gap|Impatto|Input necessario|Azione definita|
|---|---|---|---|
|Repository Francesco assente|integrazione non verificata|linguaggio/framework, schema eventi, ledger, scheduler, database, replay e CI|implementare adapter contract; nessuna riscrittura imposta|
|Venue/account eligibility|mercato primario solo ricerca|entità, paese contrattuale, domicilio/residenza/TIN, prodotto e API account|verifica scritta provider + registro vigente prima di funding|
|Historical bid/ask e trades|nessuna stima edge credibile|data license, copertura, fee as-of, outages|acquisire dataset versionato, QA, backtest dopo|
|Fee/tax/conversion|sizing reale sconosciuto|fee tier e minimi; trattamento specifico fees/tasse transazione|sostituire SYNTH; fail closed se null|
|Native stops/OCO|rischio protezione|capability matrix e test sandbox venue|no live se protezione non dimostrata|
|Calendario point-in-time|news hindsight|feed con event version e known_at, snapshot ufficiali|storico sconosciuto→RESEARCH; runtime stale→block|
|Queue/partial fill/latency|OHLC bias non quantificato|quote/trade replay, execution telemetry|adapter dedicato obbligatorio gate live|
|Broker consistency/restart|doppio ordine e orphan|execution IDs, cumulative filled, broker timestamps|fault injection + reconcile invariants|
|Rendimento|nessuna evidenza empirica|ledger OOS, CI, cost stress, multiple-testing register|stato RESEARCH; nessuna cifra profitto prevista|

## Confini implementazione
Implementato: validazione barre, ATR lagged, swing confermati, sweep, MSS/displacement, FVG, orchestrazione detector A1 swing-only, news filtro point-in-time dato dall'esterno, sizing lineare con Decimal, gate rischio snapshot, simulator OHLC, JSONL logger, test sintetici.
Da adattare/implementare: ingestion reale, PDH/session pool e equal levels nel motore, HTF e daily bias, scheduler cutoff/cancel automatici, ledger MTM e risk reservations persistenti, full order state machine con partial fills, tick replay, bracket/OCO nativi, actual fee currency conversions, margin engine, statistiche empiriche/bootstrap/DSR, osservabilità e ML. Le funzioni di rischio ricevono snapshot; non promettono di ricostruire il ledger autonomamente.

Non impostare flag opzionali a true sperando che funzionino: il motore reference li rifiuta. Moduli di specifica non ancora eseguibili hanno test di accettazione elencati nel handoff. Precisione prezzi float nella reference sufficiente per fixture; produzione usare integer ticks o Decimal end-to-end e quantizzazione venue. La reference è in-memory, non crash-safe. Non può essere promossa live cambiando un flag.
