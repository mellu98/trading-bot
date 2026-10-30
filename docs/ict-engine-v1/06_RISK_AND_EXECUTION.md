# Rischio, costi ed esecuzione
## Unità e quantità
Valuta conto EUR. x_t = EUR per una unità della valuta quote, ottenuto con tasso eseguibile e conversion fee; se EUR/USD=1,10 allora x_USD=1/1,10, non 1,10. Per JPY convertire JPY→EUR, non usare il tasso USD per errore. USDT non è USD: conversione e haircut separati, depeg stress obbligatorio.

q è quantità base per spot/FX oppure numero contratti. m è quote per punto per unità q. Spot e FX in unità base: m=1. FX in lotti standard: m=100000 se contratto lo conferma; non assumere standard per ogni broker. CFD m da instrument metadata, spesso differente per simbolo/entità. MNQ m=2 USD/punto, tick 0,25 → tick value 0,50 USD; MES m=5 USD/punto, tick 0,25 → 1,25 USD. Futures q intero. Solo contratti outright, metadata da CME e broker. Margine broker non è perdita massima.

Definire prezzi eseguibili: long entra ask, esce bid; short entra bid, esce ask. In replay bid/ask già incorpora spread: non aggiungerlo di nuovo come fee. Se segnale su mid e ordine limit a E, attendere ask≤E per buy e bid≥E per sell. Stop long trigger bid≤S, short ask≥S. Le convenzioni effettive del broker vanno verificate; differenze diventano adapter capability.

Budget B=min(r·equity, 0,01·equity, budget aggregato residuo, daily headroom prudenziale). Per q:
L(q)=q·m·x·(|E−S|+s_stop)+fees_entry(q,E)+fees_exit(q,S adverse)+conversion(q)+carry_reserve(q)+fixed_costs.
G(q)=q·m·x·(|T−E|−s_target)−fees_entry−fees_target−conversion−carry_reserve−fixed_costs.
Richiedere L(q)≤B, G(q)/L(q)≥1,5, q·m·E≥min_notional_quote, q≥min_qty, cash o margin entro disponibilità. Se fees con minimi/scaglioni, cercare il massimo q sulla griglia con validazione finale (binary search solo se funzione vincoli monotona; altrimenti scansione discendente limitata). Non interpolare fee a quantità diversa. Floor, mai ceil.

Per fee lineari L=q·ell+F, q_risk=floor_step((B−F)/ell). q_final=min(q_risk,q_cash,q_margin,q_depth,q_max_venue), poi validare minimi e RR. q_cash=floor_step(cash_EUR/(E·m·x·(1+f_entry))) per spot. Riservare entry fee fissa e buffer cash prima di applicare questa formula. q_margin da funzione margin venue, inclusi haircuts; NON inferire leva dal solo stop. La reference impone cash pieno, quindi è conservativa e non simula margine CFD/futures.

## Esempi sintetici di fattibilità (non quotazioni correnti)
|Strumento|Ipotesi|€500, B=€5|€5000, B=€50|
|---|---|---|---|
|EUR/USD unità|E=1,1000, S=1,0990, x=1/1,10; slippage=0,0001; fee RT=0,00006 USD/unità; step 1000|ell=0,0010545 EUR; q=4000, loss≈€4,22, notional≈€4000: serve margine autorizzato, cash spot insufficiente|q=47000, loss≈€49,56; notional≈€47000; verificare margine e fee minime|
|BTC spot|E=100000 USD, S=99000; slippage=50; fee 0,1% per lato; x=1/1,10; step 0,00001|ell≈€1135,5/BTC; q_risk≈0,00440 BTC, cash≈€400,4 incl fee|q≈0,04403 BTC; cash≈€4006,7; verifica min notional|
|CFD indice|m=1 USD/punto ipotetico, stop 10 punti+1 slippage, fee RT $1/unità, x=1/1,10, step 1|ell≈€10,91; q=0 → reject|q=4, loss≈€43,64; margine ignoto → blocco finché disponibile|
|MNQ|stop 20 punti, slippage 1 punto, fee RT $1,50 ipotetica|ell=$43,50/1,10≈€39,55 → reject|q=1 possibile per rischio nominale, ma margine e gap possono renderlo inadatto|

Con r iniziale=0,25% i budget sono €1,25 e €12,50. Non alzare r per forzare l'operazione minima. Gli esempi non configurano il profilo reale; C.yaml usa SYNTH, non prezzi o fee verificati.

## Stop e uscite: esperimenti separati
|Metodo|Formula long; short simmetrico|Tradeoff / esclusione|
|---|---|---|
|Sweep puro|S=L_sweep−τ|stretto, sensibile a spread e rumore; scartare se dist/ATR<0,2|
|Strutturale|S=ultimo low confermato−τ|più ampio, q inferiore; manca pivot→reject|
|ATR|S=E−kA, k=1,5; grid 1/1,5/2|semplice, non legato all'invalidazione sweep; nuovo trial|
|Strutturale buffer baseline|S=L_sweep−max(0,1A,2spread,τ)|costo realistico, qty talvolta zero; stop>3A→reject|
|Target liquidità baseline|nearest unconsumed high−τ|distanza variabile; nessun target→reject|
|RR fisso|T=E+2(E−S), net RR ricalcolato|confronto eliminando selezione pool, non baseline|
|Parziale|50% a 1R, residuo a 2R; ogni leg step/min notional valido|fee e minimi possono dominare, sotto minimi reject variante|
|Break-even|dopo bid≥E+1R, S=E+fee_equivalent+slippage|non garantisce zero perdita; test separato|
|Trailing|dopo 1R, S=max(S,highest_bid_since_entry−1,5A)|aggiornare solo close, valido barra successiva; mai allargare|
|Strutturale exit|close sotto ultimo low confermato post-entry→market next quote|non sostituisce stop protettivo; latenza/gap|
|Time exit baseline|24 M5 o session/blackout cutoff|riduce carry, può troncare vincitori|

## Cost model e simulazione
Scaricare fee tier valido alla data e registrare maker/taker effettivo, commissioni fisse, broker mark-up, exchange/clearing, IVA/tasse di transazione applicabili, conversioni, borrow, funding e swaps. Fiscalità sul reddito fuori PnL strategico ma distinta nel business case. Maker non è garantito da ordine limit: marketable limit può essere taker. Nel dubbio stimare taker per entrata e uscita, fee stop sempre taker. Spot non a margine non ha funding derivati; rimangono custodia, conversione e spread. FX/CFD rollover comprende eventuali giorni tripli, calendarizzazione da broker. Baseline flat prima rollover non esenta dai costi di un'uscita fallita.

Replay tick/quote preferito. In OHLC: no fill sulla barra generatrice; limit richiede penetrazione di ≥1 tick; nessun miglioramento prezzo all'open; stop prima del target se entrambi toccati; sulla barra entry non accreditare TP, ma attribuire stop se possibile. È un bound prudente, non una stima imparziale. Riportare anche bound ottimista per quantificare ambiguità, mai selezionare sulla base di quello. Gap oltre stop eseguito all'open peggiore più slippage. OHLC non supporta queue position, partial fill, spread path o latenza intrabar verificabile: tali risultati non possono superare il gate live.

## Circuit breaker e rischio aggregato
Equity marked-to-liquidation include PnL non realizzato e fee stimate. Daily return=(E_t−E_day_start−net_flows)/E_day_start, weekly analogo; reset a 00 UTC e lunedì 00 UTC nel ledger, indipendente dal calendario barra. Drawdown=1−E_t/peak_equity_flow_adjusted. Daily −2%, weekly −4%, DD 8%, 3 perdite consecutive, massimo 3 trade/giorno: default conservativi da validare. Daily/weekly halt non riparte perché una posizione recupera. Reset daily/weekly solo al boundary successivo; streak reset al nuovo giorno con diagnosi registrata, DD/kill soltanto revisione umana. Loss=net PnL<0, zero interrompe sequenza ma non conta come win.

Riservare worst estimated risk per filled e leaves simultaneamente; riserva atomica prima submit, rilasciata solo a terminal report. Max 1 esposizione baseline, risk aggregato 1%; nessuna diversificazione per BTC/ETH o FX USD. Estensione futura: bucket crypto ed esposizione netta USD con limite rischio 1% per bucket; correlazione rolling 60 giorni chiusi, |rho|≥0,7 unisce bucket, insufficienza dati→trattare correlati. Correlazione non protegge da shock comuni.

Spread/ATR≤0,1; quote age≤5 s; slippage stimato≤0,05 ATR. Estensione volatility circuit: ATR oltre percentile 99,5 degli ultimi 60 giorni stessi slot → no entry; history insufficiente→non attivare tale filtro senza dichiarare fallback. 3 errori API consecutivi→halt; feed staleness→cancel entry e mantenere native stop; se stop assente e connessione disponibile liquidazione prudente. Senza connessione non si può garantire flatten.

## OCO, partial fills, restart
Native bracket/OCO preferibile solo se semantica documentata. Stop-market protegge dal mancato fill ma non dal gap; stop-limit può restare ineseguito: non alternativa equivalente. Un limit protettivo sintetico richiede supervisore separato; se venue non consente stop affidabile, niente live. Partial fill: proteggere cum_qty subito, resize protezione a incrementi, cancel leaves a scadenza. Fee per fill e rounding in valuta fee; se fee in base asset, net inventory minore: exit non può vendere gross quantity.

Idempotency key=hash(strategy_version, config_hash, symbol, direction, source_event_id). Stesso ID/payload→stesso ordine, stesso ID/payload diverso→errore. Modify cancel/replace con nuova versione e vecchia order linkage, rischio doppia presenza fino ack. Fill durante cancel accettato e protetto, non ignorato. Restart: bloccare, fetch posizioni/ordini/fills dal watermark, dedup execution_id, riconciliare, rilevare orphan, ricreare solo protezioni mancanti dopo verifica; nessun ordine nuovo finché diff≠0.
