# Protocollo scientifico preregistrabile
Stato: progettato, non eseguito su mercato. Data freeze, venue, start/end, versione feed, fee schedule, ipotesi, metriche primarie e budget trial vanno firmati prima del primo backtest. Nessun Sharpe, rendimento o win rate di mercato è disponibile in questo pacchetto.

## Dataset e QA
Target acquisizione: almeno 36 mesi completi, preferibili 5 anni, comprendenti regimi diversi. Fonti: stesso venue/prodotto di esecuzione; quote bid/ask e trades tick per simulare ordini; OHLC M1→M5 deterministico per discovery. Crypto volume del venue, non globale; FX tick volume è conteggio attività del feed, non volume mondiale. Nessun book aggregato globale FX. Snapshot di depth e sequence IDs quando disponibili. Record symbol changes, contract roll, outage, timezone, funding/swap, fee tier e conversion rates.

QA per segmento: OHLC validi, prezzi positivi, spread non negativo, timestamps monotoni, duplicate idempotenti identiche eliminabili con audit; duplicati discordanti quarantena. Attesa di barre secondo calendario, non inventare weekend Forex o maintenance CME. Missing scheduled bars→nessun forward fill di OHLC per generare setup; reset e warmup n+1. Quote stale segnalate; zero-volume bars distinguere no trades da mancato feed. Outlier non rimuovere soltanto perché produce perdita: confronto con feed indipendente e flag versione. Ricostruzione H1 da dodici M5 complete; aggregato parziale non utilizzabile.

FX quote history deve essere bid/ask effettiva, non spread costante sul mid. Futures: segnali su contratti realmente negoziabili con mapping as-of e roll preregistrato (5 business days prima scadenza, calendario ufficiale); no fill su serie back-adjusted, niente futuro open interest nella scelta roll. Corporate actions per eventuali ETF: split-adjusted signal history e prezzi eseguibili/coefficienti coerenti; universo point-in-time per evitare survivorship. Mancanza dati corporate actions blocca estensione azionaria.

## Split temporali
Esempio relativo a 36 mesi disponibili: primi 18 train, successivi 6 validation, ultimi 12 test sigillato. Date esatte definite dopo acquisizione, non retroselezionate. All'interno dei primi 24 mesi: expanding train minimo 12 mesi, validation 3 mesi, step 3 mesi → quattro finestre successive. Nessuna ottimizzazione sui 12 mesi finali. Warmup pre-test consentito per feature, non per fitting. Purge qualsiasi trade/label il cui [signal_known_at,exit_at] interseca l'holdout; embargo pari al massimo horizon label, inizialmente 2 ore (24×5m), più TTL pending 30m quando l'etichetta parte dal segnale. Calendar features as-of, actual macro disponibili solo a publication receipt, revisioni escluse.

Se <36 mesi o campione insufficiente, esito RESEARCH, non accorciare holdout dopo aver visto risultati. Una modifica dopo test sigillato crea v2; richiede nuovo periodo futuro holdout. L'uso ripetuto del test diventa training di fatto.

## Famiglia esperimenti e ablation
Primo budget massimo 24 trial totali, inclusi fallimenti, mercati, varianti, selezioni manuali e richieste AI. Registro append-only `trial_id,parent,change,params,config_hash,data_hash,start,end,metrics,decision`. Non esplorare prodotto cartesiano di tutti i range CSV. Prima A1 default; poi eliminare un solo elemento per volta: sweep (sostituito da confermato pivot breakout), displacement, FVG (market su barra successiva MSS), session window (24/7 solo crypto), target liquidity (2R fisso), news filter (solo analisi rischio, non promozione live senza valutazione), entry 0/0,5/1. Ogni variante mantiene gli altri vincoli. Confrontare long-only buy-and-hold con esposizione e volatilità normalizzate; random entries matched per ora/direzione/holding, e breakout semplice con identici costi e stop, su seed preregistrati.

B1, C1 e D1 vengono testate soltanto dopo baseline/ablation. Non unire i filtri migliori di ogni esperimento senza contabilizzare un nuovo modello e un nuovo test. La decisione primaria usa expectancy netta, non win rate.

## Metriche: definizione e limiti
Trade j: P_j=Pnl lordo−tutti i costi, B_j=rischio stimato all'ingresso, R_j=P_j/B_j. N include tutte le operazioni chiuse, breakeven incluso; ordini mai filled analizzati separatamente. Mark-to-market giornaliero anche senza uscite.

|Metrica|Formula|Limite|
|---|---|---|
|Win rate|count(P>0)/N|non misura payoff; zero non win|
|Average win/loss|mean(P\|P>0); mean(−P\|P<0)|NA se sottoinsieme vuoto|
|Expectancy|mean(P); mean(R)|€ dipende da sizing, R facilita confronto|
|Profit factor|sum(P positivo)/abs(sum(P negativo))|NA se nessuna perdita, non infinito “eccellente”|
|Sharpe|sqrt(D)·mean(daily excess returns)/sd(sample)|D=365 crypto/252 business FX; serial correlation richiede CI HAC/bootstrap, annualizzazione convenzionale|
|Sortino|sqrt(D)·mean(r−MAR)/sqrt(mean(min(r−MAR,0)^2))|MAR=0 preregistrato; denominatore zero→NA|
|Max DD|max_t(1−E_t/max_{u≤t}E_u)|equity includa MTM e flussi rettificati; dipende dal percorso|
|Recovery|net profit EUR / max peak-to-trough EUR|denominatore zero→NA|
|Average/median R|mean e median(R)|R può essere <−1 in gap; non troncare|
|Net return|time-weighted equity return con flussi separati|escludere depositi come guadagno|
|Fee burden|total fees / sum(gross winning PnL)|NA se gross wins zero; riportare anche spread/slippage separati|
|Exposure|tempo unione posizioni aperte / tempo osservabile|non sommare tempi simultanei|
|Frequency|trades / giorni eleggibili|separare tradabili e giorni bloccati|
|Consecutive losses|massima run di P<0|descrittiva, non garanzia futura|
|Tail risk|5% daily VaR quantile e ES=mean(r≤q05)|pochi estremi, CI necessari|
|OOS stability|positive fold ratio, dispersione expectancy tra fold|regimi e fold non indipendenti|
|Execution|fill ratio, cancel latency, p50/p95/p99 slippage, reject ratio|paper non misura posizione in coda reale|

## Incertezza e multiple testing
Bootstrap a blocchi di giorni (include no-trade days) preserva clustering di trade. Default 10000 repliche, seed=20261030, blocco 5 giorni; sensitività 1/10/20. Ricampionare i daily ledger e trade cluster con rischio coerente; per DD ricostruire percorso equity, non shuffle indipendente di R e chiamarlo realistic execution. CI percentile 95% di mean R e net daily return; riportare autocorrelazione ed effective sample size stimata. Non assume normalità. Monte Carlo complementare: permutazione blocchi e perturbazione slippage/costs/latency, percentile 95 e 99 DD; non prova worst case.

Famiglia di M trial: p one-sided su expectancy≤0 con centered block bootstrap (null data r−mean(r)); applicare Holm: ordina p_(i), soglia alpha/(M−i+1), interrompi alla prima mancata reiezione. Includere trial scartati. Selezione nested soltanto nel train/validation; final holdout una sola valutazione del modello congelato. DSR/PBO sono diagnostiche ulteriori con implementazione indipendentemente validata, non numeri da inventare: DSR corregge selection bias e momenti non gaussiani; PBO richiede matrice di rendimenti delle configurazioni e partizioni CSCV, non applicare meccanicamente ignorando dipendenze temporali. Documentare effective trials e assunzioni; Holm+holdout rimane gate minimo.

## Stress
Costs 1×/1,5×/2×; slippage 1×/2×/3× e shock di 5 spread; delay 0/250/1000 ms con tick, oppure +1 barra solo come stress severo su OHLC. Limit fill penetration 1/2/3 tick, max participation volume 0,1%/0,5%/1% quando volume affidabile; impossibile FX senza proxy dichiarato. Reject casuali 1% e 5%, outage 5/30 minuti, gap stop e ricostruzione dopo crash. Parametri geometrici perturbati ±10/20% uno per volta con rounding discreto valido. Regimi as-of: segno ritorno trailing 60 giorni e realized vol percentile trailing 252 giorni; bull >+10%, bear<−10%, sideways altrimenti (proxy crypto, per FX usare ±3% preregistrato); volatilità bassa/media/alta per terzili train. Non usare andamento futuro per filtrare segnali, etichette ex post ammesse solo per report descrittivo.

## Gate quantitativi proposti
|Esito|Criteri tutti necessari dove indicato|
|---|---|
|REJECT|errore causale non riparabile, sizing minimo incompatibile, expectancy netta≤0 su test sufficiente, o negatività sotto costi realistici; archiviare trial|
|RESEARCH|dati/spread mancanti, N<200 OOS, <60 giorni con trade, CI include zero, test contaminato, o instabilità; non significa automaticamente assenza edge|
|PAPER TRADE|N≥200 OOS, ≥60 giorni con trade e 12 mesi OOS; CI95 lower(mean R)>0 e Holm p<0,05 nella ricerca; PF≥1,15; almeno 3/4 validation fold expectancy>0; DD≤8% al sizing previsto; 1,5× costi expectancy>0; ≥70% vicini ±20% con expectancy>0; nessun singolo mese >40% del profitto netto positivo; invarianti causali e ledger passano|
|LIMITED LIVE ELIGIBLE|gate precedente + paper almeno 60 giorni e 100 fill, nessun ordine duplicato/orfano, 100% reconcile giornalieri, p95 slippage entro modello, 99,5% eventi processati entro 1 s su hardware target; shadow ≥20 giorni allineato, venue eleggibile e protezioni verificate; APPROVAZIONE UMANA ESPLICITA richiesta|

Soglie convenzionali conservative, non teoremi o power analysis universale. Se il turnover basso impedisce 200 trade, attendere più dati e mostrare minimum detectable effect con variance/block dependence stimata solo dal train. Non abbassare N a posteriori. No live “per scoprire se funziona” quando mancano dati essenziali.

## AI/ML solo dopo A1
Regime classification, volatility forecasting, anomaly detection e diagnostics hanno priorità sul decisore ordini. Feature note al segnale: ATR lagged, time slot, spread percentile as-of, sweep/A, body/A, gap/A, target distance/A, trend H1 closed, prior-only regime. Label meta-model: 1 se net R del trade baseline>0, oppure regressione net R; registrare anche segnali rifiutati con counterfactual simulato separato. No actual news futuro né exit-dependent feature.

Minimo di avvio proposto 2000 segnali con outcome e almeno 24 mesi, con >=200 nel validation/test: altrimenti modello troppo flessibile rispetto al campione. Baseline logistic regularizzata prima di gradient boosting; pesi classe fit sul train, nessun oversampling prima split. Train/validation purged temporali; standardizzazione, imputation, feature selection e calibration solo sul train e calibration subset cronologico. Brier score=mean((p−y)^2), reliability bins e log-loss oltre PnL; accuracy non basta. Soglia di trade scelta solo validation, confrontare medesimo periodo/esposizione/costi con A1. Promuovere ML soltanto con CI95 bootstrap paired(delta net return)>0 su holdout e DD non peggiore.

Drift: PSI per feature con bin fissati train >0,2 per 5 sessioni o Brier deteriorato >20% su ultime 100 label mature→alert/research. Retrain minimo mensile con >=200 nuove label, mai automatic promotion; challenger shadow con versione congelata. LLM può generare ipotesi/codice/review e interpretare incidenti, non quantità, chiavi, stop o bypass di risk gates. Output non strutturato o tool failure non entra nell'execution path.
