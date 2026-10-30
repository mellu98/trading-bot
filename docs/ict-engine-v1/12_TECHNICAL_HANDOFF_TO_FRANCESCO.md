# TECHNICAL HANDOFF TO FRANCESCO — ICT TRADING SYSTEM
## Executive engineering decision
Innesto proposto: MarketDataPort → FeatureEngine → A1StateMachine → SignalIntent → deterministic RiskPort → ExecutionPort → immutable Ledger. NewsPort e InstrumentPort alimentano gate, non generano ordini. LLM/ML resta fuori dal trusted execution boundary. Nessuna ipotesi su linguaggio, database, framework, API o struttura del tuo repository.

Il contratto JSON 08 è uno schema interoperabile draft 2020-12 con payload e envelope versionati. Python reference è un oracle di ricerca parziale, non libreria da collegare direttamente a un conto. L'interfaccia esatta può essere tradotta in DTO/eventi locali; conservare significato, timestamp e invarianti. Contratti decimali stringa sul wire, integer ticks in produzione, UTC ns ove supportato. Feature store bitemporale: event_time e known_at separati.

## Requisiti non funzionali proposti
Determinismo stesso event log+config+build → stessi intent IDs e decision reasons. Idempotenza effect-once su execution_id con consegna at-least-once. WAL prima dell'effetto esterno, reconciliation dopo crash. Target p99 decision latency≤1 s su M5, bench su hardware reale, non risultato misurato qui. Clock skew≤100 ms su host, quote stale>5 s blocca; sincronizzazione e drift allarmati. Conservare input hashes, fee metadata version, account currency, risk reservation, reject logs e fill ledger per ogni decisione. Nessun secret nei log o file consegnati. Recupero con esposizione incerta blocca nuove entry; downtime è preferibile a ordini duplicati.

## Milestone implementabili
|M|Obiettivo/componenti|Input|Output|Test richiesti|Definition of Done|Blocker|
|---|---|---|---|---|---|---|
|M0 Contract mapping|DTO, schema validation, event ordering, adapter stub|schema 08 e sample payload, attuali interfacce interne|mapping field-by-field con unità/time semantics|invalid payload, unknown version, duplicate IDs|ogni campo essenziale mappato o esplicitamente unavailable; mode simulation enforced|repository necessario solo per mapping concreto|
|M1 Data/metadata|normalizer, calendar, as-of store, instruments|feed storico venue, fee, clocks, session calendar|dataset versionato e QA report|missing bar, DST US/EU mismatch, split/roll, stale FX conversion|nessun fill fabricated; warmup/reset deterministici|licenza/copertura dati|
|M2 Features/A1|pivot, pool lifecycle, sweep, MSS, displacement, FVG, geometry|bar/event fixtures e YAML|intent stream e reason logs|boundary ticks, ties, expiry, both-direction sweeps, prefix invariance, long/short mirror|parità reference per subset supportato; test dei nuovi pool PDH/session indipendenti|nessuno per subset synthetic|
|M3 Risk/ledger|sizing generalizzato, margin, reservations, MTM gates|account, instrument specs, fee tiers|ordine ammissibile o reject; equity riconciliata|€500/€5000, min notional, rounded qty, fee currency base, gap, correlated race|nessuna violazione budget stimato in property test; nessun arrotondamento verso alto|specifiche venue/margine|
|M4 Execution|paper adapter tick, OCO capability, partial fill, restart|quote/trade stream + broker sandbox semantics|order state lifecycle, WAL e reconcile|timeout-after-accept, cancel/fill race, duplicate report, crash in ogni transition, unprotected partial|nessun orphan non rilevato, protezioni coerenti con quantità, deterministic replay|capability broker|
|M5 Research|splits, metrics, block bootstrap, trial registry|dataset congelato e cost model|report OOS riproducibile + GO/NO-GO|leakage sentinel, benchmark null, fee stress, bootstrap seed, multiple trials|criteri 07 applicati senza eccezioni retroattive|dati empirici assenti oggi|
|M6 Paper/shadow|runtime monitor, incident drills, daily reconcile|feed reale, zero execution permission|telemetry e report giornalieri|disconnect, stale calendar, clock jump, manual kill|60d/100fill paper e 20d shadow; cost/latency conformi|tempo e feed|
|M7 Eligibility review|account/legal/capability + audit human gate|evidenze e firma autorizzazione|LIMITED LIVE ELIGIBLE, non live auto|config tamper, bypass LLM, missing approval|tutti gate soddisfatti; live adapter separato|approvazione e verifica venue|

## Acceptance invariants
1. `feature.known_at <= decision_at < order_eligible_at <= fill_at` (eligible_at può coincidere ack, mai precedere signal).
2. Conferma pivot i+k mai utilizzata a i. HTF incompleta non emette valore.
3. Nessun trade nuovo se qualsiasi hard gate false/unknown. Una equity sconosciuta non è zero-risk.
4. Qty multiplo step, prezzo multiplo tick, rischio stimato≤budget; minimi incompatibili→reject.
5. Una execution_id impatta ledger una sola volta; cumulative fill mai diminuisce; filled≤requested salvo errore venue rilevato.
6. Fill durante cancel resta esposizione reale. Terminal cancel non cancella contabilmente i fill precedenti.
7. Qty stop/TP mai maggiore inventory disponibile (considerando fee in base), né minore senza incident aperto.
8. PnL reale e simulato distinguono spread, fees, carry e FX; nessun doppio addebito spread.
9. Restart non sblocca halt daily/DD e non invia vecchi signal scaduti.
10. Il codice AI non può mutare risk limits, secret scope o approval artifact.

## Informazioni da leggere quando disponibile il repository
Entry point ingestion, normalizzazione simboli e timezone; serializzazione eventi e schema migration; database append/transaction semantics; backtest fill conventions; risk engine valuta/unità; scheduler di sessione; API adapter support/unsupported; logging e metriche; deployment/restart; CI fixtures e property testing. L'assenza non impedisce M0 synthetic/M2, ma impedisce affermare compatibilità o production readiness.

## Rischi principali
Quantitativi: costi dominanti sul conto piccolo, selection bias, pochi trade, autocorrelazione, spot long bias durante bull market. Tecnici: pivot lookahead, intrabar ambiguity, tick rounding, conversione USDT impropria, race cancel/fill, stop sintetici durante outage. Operativi: accesso venue non verificato, calendario stale, variazioni fee/margine. Ogni rischio è legato a test o gate nei file 05–07 e 11, non lasciato a discrezione runtime.
