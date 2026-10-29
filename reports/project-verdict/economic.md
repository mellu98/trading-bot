# Verdetto economico: cambiare strategia, non aggiungere complessità

**Raccomandazione indipendente: CAMBIARE STRATEGIA. Forza delle evidenze: media per la decisione di investimento; bassa sul vero rendimento futuro.** La configurazione attuale non dimostra un vantaggio convincente: il risultato positivo esiste, è contabilmente riproducibile, ma dipende da un singolo grande vincitore, non è stabile tra periodi e fallisce i criteri originariamente congelati. Non è una prova statistica che il suo rendimento atteso sia negativo. Non giustifica altro sviluppo del software per questa configurazione né operatività reale.

## Risposta breve alle domande economiche

- **Positiva dopo i costi?** Sì nel modello base e avverso gennaio–settembre 2026; no nel severo e nel 2025. Sono risultati simulati, non guadagni reali né costi empiricamente certificati.
- **Persistente fuori sviluppo?** Non dimostrato. Il 2026 era un test storico non ancora acquisito dal progetto al congelamento originale; oggi è già osservato e non costituisce una nuova validazione indipendente.
- **Fragile?** Sì: un trade +16,18 USDT spiega più del profitto complessivo +7,46; senza quel trade il ledger residuo perde 8,71 USDT. La concentrazione non è di per sé una confutazione del trend following, ma qui manca la replicazione che la renda credibile.
- **Il rischio è giustificato?** Non dalle prove disponibili: drawdown a chiusura oraria 11,70 USDT contro utile 7,46; l'incertezza include perdite. Il drawdown intrahour effettivo può essere maggiore.
- **Timestral aiuta?** No nella configurazione precisa testata: entrambi i modelli hanno escluso tutti i candidati, producendo zero trade. L'inferenza era reale; la sofisticazione non ha creato edge.

## 1. Regole effettivamente congelate e verificate

Fonti: `reports/binance-spot/breakout-4h/protocol.json`, `execution-freeze.json`, `runner.py`, dipendenze immutabili elencate nel freeze.

| Elemento | Regola |
|---|---|
| Mercato | Binance BTCUSDT spot, long/flat, nessuna leva/short/piramidazione, una posizione |
| Barre | Quattro barre native 1h complete e contigue, aggregate in 4h UTC [00,04), [04,08), ecc. |
| Entrata | Alla chiusura di t: close strettamente maggiore del massimo delle 20 barre 4h precedenti, esclusa t; entrata modellata all'open della successiva ora nativa |
| Uscita canale | Se long: close strettamente minore del minimo delle 10 barre precedenti, esclusa t; vendita al successivo open 1h |
| ATR | Media aritmetica degli ultimi 14 true range 4h completati, incluso t; non Wilder/EWMA |
| Stop | Fisso iniziale: floor a tick 0,01 di (fill ask modellato − 2×ATR al segnale); nessun trailing/TP/time exit |
| Ordine eventi | Gap sotto stop all'open prima di vendita canale pendente; altrimenti low bid orario tocca stop; nessun ordinamento favorevole stop/target |
| Capitale e size | 1.000 USDT iniziali; massimo 100 USDT per entrata incluse fee; massimo 1 USDT perdita iniziale MODELLATA incluse fee/slippage round trip; quantità arrotondata in basso a 0,00001 BTC; notional minimo 5 |
| Risk | Giornaliero 10 USDT, drawdown globale 20, massimo 10 ingressi/giorno e 3 perdite consecutive nel giorno; reset UTC del solo halt giornaliero a flat, globale persistente nel segmento |
| Segmenti | Inizio flat e warmup solo prezzi; nessuna posizione/segnale pendente trasferita tra segmenti; liquidazione terminale esplicitamente etichettata, nessun ingresso all'ultima ora |

Per i 26 trade 2026: initial risk 0,96873–0,99945 USDT; entry cash 20,07–89,35 USDT, nessuna violazione del cap/grid e nessun Risk halt/rifiuto. Gap e impossibilità di eseguire uno stop possono comunque superare il rischio modellato: **1 USDT non è una garanzia di perdita massima**.

## 2. Provenienza, copertura e indipendenza

Ricalcolo indipendente dai file ZIP originali, senza scaricare dati: tutti i 22 ZIP e CHECKSUM locali corrispondono ai manifest; tutti gli OHLCV sono validi, ordinati, senza gap/duplicati e con chiusura inclusiva/unità temporali esatte. Si ricostruisce lo stesso SHA del dataset normalizzato.

| Uso | Periodo UTC semiaperto | Ore 1h | Stato scientifico attuale |
|---|---|---:|---|
| Warmup | 2024-12-01 / 2025-01-01 | 744 | Già osservato, solo prezzi |
| Sviluppo descrittivo | 2025-01-01 / 2026-01-01 | 8.760 | Già osservato prima del breakout |
| Test originale | 2026-01-01 / 2026-10-01 | 6.552 | Storico inizialmente project-unseen; ora osservato anche in Timestral |
| Totale | 2024-12-01 / 2026-10-01 | 16.056 | 4.014 aggregazioni complete 4h |

La cronologia documentata è coerente: freeze implementazione `1793088773238448000 ns`; prima richiesta dei nuovi archivi 2026 `1793088862630327000 ns`; ultima risposta `1793088882224490000 ns`. Il protocollo era già congelato prima. Le fonti correnti corrispondono ancora agli hash del freeze. Questo tutela il test storico originale, non lo trasforma in prova prospettica né esclude conoscenza pubblica/umana del periodo.

Il recorder Timestral contiene anche 256 barre native recenti: il `data/binance-spot/timestral-shadow/bootstrap-proof.json` esaminato termina il 27 ottobre 2026 alle 08:00 UTC ed esplicitamente dichiara **WARMUP_ONLY_NOT_NEW_FINANCIAL_TEST_NOT_PROSPECTIVE_PREDICTIONS**. Altri warmup recenti eventualmente raccolti non diventano automaticamente un holdout: usare prezzi storici per contesto non significa aver osservato una previsione emessa prima dell'esito. Non è stato creato un nuovo OOS con questi dati. I 120 giorni CME precedenti sono già osservati.

BTCUSDT è selezionato ex ante per questo test, quindi non c'è selezione del vincitore tra asset nel breakout. Resta condizionamento su un asset sopravvissuto/liquido: non è una prova universale su crypto. La sequenza di ipotesi già esaminate (futures, SMA, breakout, filtro AI) aumenta il rischio di selezione a livello di progetto; non esiste un inventario completo che permetta una correzione quantitativa affidabile.

## 3. Costi: assunzioni, non certificazione di un account

| Scenario congelato | Fee per lato | Slippage avverso per lato | Spread intero | Frizione round trip indicativa |
|---|---:|---:|---:|---:|
| Base | 10 bp | 1 bp | 2 bp | circa 24 bp |
| Avverso | 15 bp | 5 bp | 10 bp | circa 50 bp |
| Severo | 20 bp | 10 bp | 20 bp | circa 80 bp |

Fee regolate in USDT, nessuno sconto BNB. Non si afferma che queste siano le commissioni attuali dell'utente. Gli scenari già esistenti sono **simulazioni complete**: costi diversi possono modificare size/stop/percorso; il severo ha infatti 27 trade contro 26. Non abbiamo sottratto costi nuovi da un PnL fisso e chiamato il risultato backtest.

Decomposizione base 2026 riconciliata con Decimal:

| Voce | USDT |
|---|---:|
| PnL grezzo ai riferimenti prezzo | +9,99972090 |
| Spread modellato | −0,21134619 |
| Slippage modellato | −0,21134609 |
| Fee | −2,11345987 |
| **Netto** | **+7,46356876** |

Fee/costi esecuzione assorbono circa un quarto del gross. Nessuna spesa di lavoro, hardware, eventuali abbonamenti o imposte è inclusa; qui non vengono inventati costi assenti. Il capitale simulato è piccolo e limitato dalla policy: non si può moltiplicare linearmente il profitto per promettere rendimenti su size maggiori.

## 4. Tabella economica ricontata dai ledger originali

Drawdown = massimo peak-to-trough della curva oraria marcata con riserva dei costi di liquidazione; non drawdown tick-by-tick.

| Regola | Periodo | Costi | Trade | Netto USDT | PF | DD USDT |
|---|---|---|---:|---:|---:|---:|
| Breakout 4h | 2025 osservato | Base | 38 | −4,15169 | 0,82956 | 10,11324 |
| Breakout 4h | 2025 osservato | Avverso | 38 | −7,31722 | 0,70695 | 10,05857 |
| Breakout 4h | 2025 osservato | Severo | 39 | −11,75840 | 0,56235 | 13,70780 |
| Breakout 4h | gen–set 2026 | Base | 26 | +7,46357 | 1,55765 | 11,69840 |
| Breakout 4h | gen–set 2026 | Avverso | 26 | +4,05591 | 1,29456 | 12,74268 |
| Breakout 4h | gen–set 2026 | Severo | 27 | −1,40460 | 0,91371 | 13,66870 |
| Buy & hold | gen–set 2026 | Base | 1 | −4,78005 | 0 | 44,42920 |
| Cash | gen–set 2026 | Nessuno | 0 | 0 | N/A | 0 |

Buy & hold impiega 100 USDT iniziali incluse fee e lascia 900 cash; stesso modello prezzo/costi/grid, ma **non** stessi controlli 1-USDT stop/daily10/DD20. È un riferimento, non confronto risk-matched né portafoglio deployable con il Risk attivo. Il breakout sta a mercato al massimo 2.026/6.552 ore (30,92%), mentre B&H quasi tutto il periodo; capitale d'ingresso mediato sul tempo circa 12,56 USDT, non esposizione nozionale mark-to-market certificata. Il semplice +12,24 USDT rispetto a B&H non prova superiorità: la CI95 del differenziale medio giornaliero a blocchi5 è [−0,14767; +0,25020] USDT.

Il netto base è +0,746% dei 1.000 USDT simulati in nove mesi; non è una stima annualizzata. Le 26 operazioni hanno win rate 34,62%, expectancy +0,28706 USDT/trade, deviazione standard campionaria dei payoff 3,31910 USDT, serie massima di cinque perdite, durata mediana 68 ore/massima 192. Le cinque perdite non contraddicono il limite consecutivo GIORNALIERO: non sono cinque perdite nello stesso giorno.

## 5. La fragilità determinante

Il trade 17–23 agosto produce **+16,17803 USDT**, circa il 77,60% dei guadagni dei trade vincenti. I restanti 25 trade sommano **−8,71447 USDT**; PF residuo 0,34888. Togliendo i migliori due: −10,12792/PF0,24328; migliori tre: −10,94180/PF0,18247. Sono diagnostiche sullo stesso ledger, non strategie eseguibili: togliere un trade cambierebbe opportunità, cash e Risk. Non sono nuovi backtest.

| Trimestre 2026 | PnL marcato USDT |
|---|---:|
| Q1 | −2,41233 |
| Q2 | −3,69783 |
| Q3 | +13,57373 |

Solo **3 mesi positivi su 9**, **1 trimestre positivo su 3**; agosto da solo +14,69439 USDT. Il medesimo protocollo richiedeva almeno due trimestri positivi: requisito fallito. Anche il requisito di limite inferiore positivo dell'expectancy giornaliera fallisce.

La bootstrap originaria è stata ricalcolata indipendentemente, ottenendo esattamente gli stessi numeri: 10.000 ricampionamenti circolari di blocchi5 giorni UTC, seed1729; media giornaliera +0,02733908 USDT, CI95 [−0,06302075; +0,16878065], limite inferiore unilaterale95 −0,05291423. Anche blocchi1/10 hanno limite inferiore negativo. È incertezza **condizionale al percorso osservato**, non simulazione di nuovo Risk, ipotesi IID sui 26 trade o probabilità di profitto futuro. I blocchi di pochi giorni non inventano più regimi indipendenti di quelli osservati.

Sensibilità dei parametri non stimata: nessuna griglia, nessuna variazione di canale/ATR selezionata dopo aver visto i risultati. Conosciamo solo la sensibilità ai tre costi già congelati. Questo limite è preferibile a ottimizzare il test fino a farlo risultare positivo.

## 6. Realtà dell'esecuzione: cosa il backtest non dimostra

1. Le feature usano soltanto barre completate, canali escludono t e ATR non usa il futuro. **Ma** close 4h e successivo open 1h sono alla stessa frontiera temporale: il backtest assume di conoscere il close e ottenere immediatamente quel prezzo. Nella realtà il close arriva dopo la sua produzione e l'ordine può usare solo la prima quota disponibile successivamente. Non è stato misurato il PnL con quella latenza e quelle quote; il costo base non prova automaticamente di coprirla.
2. OHLC1h sono prezzi delle transazioni, non BBO storico. Lo spread è sintetico e la profondità mostrata è illimitata per il piccolo cap: non dimostrano liquidità, queue, market impact o fill effettivi. Tick/step/minnotional sono assunzioni di ricerca, non certificazione point-in-time dei filtri exchange.
3. Gap-stop-first e assenza di target evitano un vantaggio artificiale nella scelta stop/target. Restano 11 stop 2026 con tempo solo limitato all'ora: un low non ricostruisce sequenza, disponibilità esecutiva o prezzo reale dello stop. Nessuna precisione tick-by-tick viene attribuita a questi dati.
4. Si verificano cash, fee, conservazione PnL e size; ciò certifica la coerenza del **modello**, non l'eseguibilità dei prezzi. Un feed perfetto non eliminerebbe questo limite economico. Non è stato trovato un errore contabile che trasformi il risultato in una prova di edge, né è stato corretto il runtime.

## 7. Gli altri esperimenti non salvano l'ipotesi

I sei ledger futures V2 giornalieri sono stati riconciliati indipendentemente con i riepiloghi esistenti. Periodo delle barre esaminate: 5 maggio–23 ottobre 2026, 120 sessioni/93.600 barre complessive sui due strumenti. Tutto già osservato; il reset diagnostico giornaliero non è un portafoglio continuo deployable e non va sommato come se le strategie fossero indipendenti.

| Braccio futures | Trade | Gross USD | Fee USD | Frizione USD | Netto USD | Netto avverso USD |
|---|---:|---:|---:|---:|---:|---:|
| MNQ VWAP | 627 | −1.844,00 | 769,00 | 627,00 | −3.240,00 | −4.494,00 |
| MNQ ORB | 176 | −700,00 | 215,94 | 176,00 | −1.091,94 | −1.443,94 |
| MNQ Sweep/MSS | 294 | +275,00 | 360,42 | 294,00 | −379,42 | −967,42 |
| MES VWAP | 633 | −188,75 | 776,70 | 1.582,50 | −2.547,95 | −5.238,20 |
| MES ORB | 173 | −50,00 | 212,18 | 432,50 | −694,68 | −1.429,93 |
| MES Sweep/MSS | 241 | +68,75 | 295,20 | 602,50 | −828,95 | −1.853,20 |

Anche la precedente SMA168 spot perde nel suo test originale ottobre–dicembre2025: 19 trade, −14,95955 USDT, PF0,13662; la validation luglio–settembre: 28 trade, −6,45070/PF0,55441. Sono ipotesi diverse, non campioni da unire per sostenere il breakout.

Timestral A/B/C usa storia già osservata. Il JSON esistente conferma: baseline primaria26/+7,46357; filtro28M0/0; filtro209M0/0. Non furono esclusioni per forecast mancanti o modelli inventati: nel report congelato entrambi rifiutano 79/79 candidati per hurdle di edge insufficiente. La previsione ritardata quattro ore non supera la baseline; non si generalizza questo esito a ogni uso possibile del modello. Training cutoff/dataset inventory ignoti impediscono di escludere overlap di pretraining. Nessuna nuova inferenza è stata eseguita.

## 8. Decisione e unico passo utile

**Non continuare a perfezionare feed, AI o architettura come se il margine fosse già dimostrato.** Economicamente la scelta sostenuta da queste prove è archiviare la configurazione attuale come **non promossa** e riutilizzare l'infrastruttura, se si procede, per una diversa ipotesi economica da formulare prima di altro codice. Non abbiamo progettato né ottimizzato tale strategia durante il giudizio. Il fallimento di queste regole non dimostra che ogni strategia automatica sia impossibile; non giustifica però un nuovo ciclo senza un criterio di uscita.

**Prossima azione proposta:** interrompere gli sviluppi sulla configurazione corrente e formalizzarne l'archiviazione/non-promozione con il socio, preservando fonti e simulatori. Non occorrono altre settimane di diagnostica per prendere questa decisione di allocazione.

Se invece si vuole conoscere il vero edge di QUESTA stessa regola, manca un solo tipo di esperimento informativo: una coorte prospettica immutabile con segnali emessi prima dell'esito e prime quote effettivamente disponibili dopo il close, spread e costi registrati, includendo tutti gli eventi/mancati fill. Il protocollo esistente prevede **almeno 90 nuovi giorni UTC E 20 round trip ipotetici chiusi**, senza peeking economico/estensione fino al successo; non sono una garanzia di potenza o di PASS. Solo dati successivi al più recente punto già osservato/emesso possono qualificare. Qui non è stato avviato tale forward né lo proponiamo come condizione per rimandare il verdetto attuale. Storico L1 assente e nessun nuovo holdout documentato impediscono una certificazione esecutiva/prospettica oggi.

## Riproducibilità e integrità

Nessun download, inferenza nuova, replay di strategia nuovo, ordine, servizio o modifica del runtime. Un solo script offline riconta i trade congelati e replica l'incertezza esistente; i risultati dei due replay originali sono già byte-identici. Non era necessario un terzo replay per verificare i numeri richiesti.

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
.venv/bin/python reports/project-verdict/economic-analysis.py
```

Il freeze diagnostico è stato scritto **prima** dei calcoli e vincola 63 input, inclusi script, fonti, protocolli, ledger e manifest. Esito: 12 ledger spot riconciliati, 6 futures riconciliati, archivi/checksum/normalizzazione verificati, bootstrap esatta, **179 file protetti uguali al manifest originale prima e dopo**. Nessuna ricevuta Git/gentle-ai è dichiarata: workspace senza repository Git, gentle-ai assente; CodeGraph non inizializzato, fallback mirato già dichiarato.

| Identità | SHA256 |
|---|---|
| Protocollo breakout | `70bea1510b04f67cfb65db7881ed6319534fbf009b71b514afd07d49918fd3c4` |
| Freeze implementazione | `258d555a0b83f8a389e34fe8cc0222bb56fdc4ac238896e0b36041611e4a9c48` |
| Dataset normalizzato | `a32da0e732d8eb1f271e3e55ba42ec916e6fbfc13a68e293e09002d9801880ac` |
| Risultati originali run1/run2 | `b052317d22ad203cd3e25e6a48859ffa35510d58b108bd2be1194e1aea221af0` |
| Freeze audit economico | `984ea2d53e7000c40391a41c4e83bcf1405c5c7e35bc807af99b679ac2251cbc` |

Output: `reports/project-verdict/economic.json`; sorgente e manifest `economic-analysis.py` / `economic-freeze.json`. Rollback: rimuovere solo questi nuovi artefatti economici; nessun comportamento del bot dipende da essi. `skill_resolution: paths-injected`.

## Key Learnings:

1. La contabilità corretta dimostra la coerenza di una simulazione, non il suo edge: un solo vincitore +16,18 sostiene un netto totale +7,46 su 26 trade.
2. Un test storico congelato prima dell'acquisizione conserva valore scientifico originale, ma dopo l'ispezione non può essere riciclato come nuovo OOS.
3. Next-open causale sul calendario non implica fill disponibile: il close 4h deve essere ricevuto prima di poter utilizzare una quota successiva.
