# ICT Engine v1.0 — pacchetto autonomo per Francesco

**Stato: RESEARCH / simulation-only.** Nessun backtest di mercato eseguito e nessun edge dimostrato. Sorgente dell'infrastruttura di Francesco non disponibile: nessuna compatibilità concreta dichiarata.

## Avvio

Richiede Python 3.11+ e database timezone IANA installato sul sistema. Il codice operativo e i test non richiedono pacchetti pip. Su Windows installare `tzdata` se il sistema non fornisce America/New_York.

```bash
cd ICT_ENGINE_v1
python3 -m unittest discover -s reference/tests -v
python3 reference/demo.py
```

La demo esegue una sola operazione sintetica predisposta per mostrare il simulatore, non misura performance. Il test `test_end_to_end_long_and_mirror_short` attraversa davvero sweep→MSS→FVG→sizing→fill→target con dati sintetici. Non usare la demo come prova di profittabilità.

## File di lavoro

|File|Contenuto|
|---|---|
|[01_ICT_MASTER_SPEC.md](01_ICT_MASTER_SPEC.md)|Decisioni, baseline e alternative|
|[02_MARKET_SELECTION_MATRIX.csv](02_MARKET_SELECTION_MATRIX.csv)|10 strumenti, pesi e valutazioni condizionali|
|[03_ICT_PARAMETERS.csv](03_ICT_PARAMETERS.csv)|115 parametri e feature con metadata|
|[04_ICT_STRATEGY_CONFIG.yaml](04_ICT_STRATEGY_CONFIG.yaml)|Default SYNTH simulation-only; sintassi JSON valida YAML 1.2|
|[05_ICT_SIGNAL_ENGINE.md](05_ICT_SIGNAL_ENGINE.md)|Algoritmi, decision matrix, state machine|
|[06_RISK_AND_EXECUTION.md](06_RISK_AND_EXECUTION.md)|Sizing multi-asset, costi, protezioni e reconcile|
|[07_BACKTEST_VALIDATION_PROTOCOL.md](07_BACKTEST_VALIDATION_PROTOCOL.md)|Split, bootstrap, multiple testing, gate, AI/ML|
|[08_INTEGRATION_CONTRACT.json](08_INTEGRATION_CONTRACT.json)|JSON Schema draft 2020-12, 8 payload tipizzati|
|[09_RESEARCH_EVIDENCE.md](09_RESEARCH_EVIDENCE.md)|Fonti primarie, limiti e verifiche giurisdizione|
|[10_FRANCESCO_IMPLEMENTATION_ROADMAP.md](10_FRANCESCO_IMPLEMENTATION_ROADMAP.md)|Research→paper→eventuale live autorizzato|
|[11_OPEN_ASSUMPTIONS_AND_GAPS.md](11_OPEN_ASSUMPTIONS_AND_GAPS.md)|Assunzioni e componenti non implementati|
|[12_TECHNICAL_HANDOFF_TO_FRANCESCO.md](12_TECHNICAL_HANDOFF_TO_FRANCESCO.md)|Milestone tecniche, DoD, invarianti|
|[13_ICT_CONCEPT_CATALOG.md](13_ICT_CONCEPT_CATALOG.md)|26 famiglie di concetti formalizzate|
|[14_NEWS_AND_EVENT_FILTER.md](14_NEWS_AND_EVENT_FILTER.md)|Calendario as-of e policy eventi|
|[15_VERIFICATION_REPORT.md](15_VERIFICATION_REPORT.md)|Esiti verifiche eseguite, senza dati di mercato|
|reference/|11 moduli richiesti, config, demo e test|

## Coverage manifest: specifica ≠ reference completa

|Componente|Codice consegnato|Confine|
|---|---|---|
|Market data / ATR|market_data.py|Bar validation e ATR lagged; niente feed reale, reset segmento gestito da caller|
|Market structure|market_structure.py|Pivot strict causali; no HTF aggregatore|
|Liquidity|liquidity_detector.py + Engine|Swing-only, consumed/intact; equal levels/session/PDH solo specifica|
|MSS/displacement|mss_detector.py|Operativo e testato synthetic|
|FVG|fvg_detector.py|Tre barre, middle=MSS, immediate third candle|
|A1 orchestration|ict_strategy.py|Detector streaming e intent; non full lifecycle dispatcher|
|News|news_filter.py|Gate su calendario fornito; coverage/ingestion esterni|
|Risk|risk_manager.py|Gate snapshot; ledger, sticky halts e reservations a carico host|
|Sizing|position_sizing.py|Fee lineari e cash cap con Decimal; margin, tier fees, fee base-asset esterni|
|Execution|execution_adapter.py|OHLC conservativo, long/short, idempotency in-memory, cancel esplicita, stop/TP/time; no rete, partial fills, auto news/session cancel, persist/restart|
|Logging|trade_logger.py|JSONL con checksum evento; non WAL transazionale né hash-chain|
|B1/C1/D1, ML, empirica|documenti|Non implementati né validati su dati reali|

Il caller processa prima gli execution report e aggiorna RiskState.concurrent/reserved_fraction. Non chiamare il detector per autorizzare una nuova entry con uno snapshot di rischio vecchio. Prima del replay completo implementare scheduler di cancel/exit e ledger normativi. Il simulatore non è collegato automaticamente a tutti i gate: questa separazione è esplicita e non può essere ignorata nella promozione.

## Contratto vs oggetti Python

`SignalIntent` sul wire ha direzione LONG/SHORT, numeri decimali stringa, timestamp di ricezione e config hash. La reference interna usa ±1 e float prezzi: la traduzione è responsabilità dell'adattatore M0. Il JSON Schema verifica struttura, non disuguaglianze tra campi: verificare a runtime OHLC, bid≤ask, positive nonzero quantities/prices, unità, known_at≤decision_at<eligible_after≤fill, expiry>eligible_after e geometria stop/target. AccountSnapshot e metadata devono essere freschi e riconciliati. `schema_version` e `strategy_version` sono versioni distinte.

Nessun network client o live adapter è incluso; entrambi Engine e SimulationAdapter rifiutano mode diverso da simulation. Tutti i numeri fee/prezzo del profilo SYNTH sono dimostrativi.
