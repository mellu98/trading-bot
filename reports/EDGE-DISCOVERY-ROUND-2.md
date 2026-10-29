# Edge Discovery Round 2 — NESSUNA NUOVA CANDIDATA PROMOSSA

**28 ottobre 2026. Campagna conclusa, senza espandere la ricerca.**

| Ipotesi | Fondamento e fattibilità | Decisione |
|---|---|---|
| H1 — reversal condizionato da volume/liquidità | Meccanismo plausibile; misurabile come adattamento daily long/cash su BTC/ETH con esecuzione oraria modellata | **Non promossa:** negativa dopo costi in entrambi i periodi. Archiviare questa configurazione. |
| H2 — attività/liquidità giornaliera | Testabile il solo volume relativo, non la liquidità quotata; supporto scientifico debole e instabile | **Non promossa:** positivo 2024 non robusto a costi, ritardo e benchmark. |
| H3 — maker liquidity provision | Mancano storico e informazioni necessarie a stimare coda/fill/adverse selection | **Esclusa, non valutabile:** nessun P&L maker inventato, non dichiarata perdente. |

**Nessuna delle nuove configurazioni merita la promozione a conferma prospettica secondo i criteri congelati.** Nessuna modifica o rivalutazione di B, nessuna nuova acquisizione di dati di mercato, nessun ordine, capitale, account, dashboard, servizio o acquisto. Il bot operativo, Databento, Docker e i 179 file protetti restano invariati.

## 1. Cosa dicono davvero le fonti

Tutti e cinque i riferimenti richiesti sono stati verificati su fonti primarie; profondità di accesso dichiarata, senza attribuire risultati non letti.

| Fonte | Stato/accesso | Conseguenza per questa campagna |
|---|---|---|
| [Farag e altri, Returns from liquidity provision, 2025](https://doi.org/10.1016/j.jbankfin.2025.107411), [PDF istituzionale](https://pure-oai.bham.ac.uk/ws/portalfiles/portal/264447617/Farag2022Returns.pdf) | Peer-reviewed; versione pubblicata completa consultata | Reversal a **5 minuti**, long-short; non prova di fill maker o della nostra H1 daily. |
| [Bianchi–Babiak–Dickerson, Trading volume…, 2022](https://www.sciencedirect.com/science/article/pii/S0378426622001418), [WP Riksbank completo](https://www.riksbank.se/globalassets/media/rapporter/working-papers/2022/no.-413-trading-volume-and-liquidity-provision-in-cryptocurreny-markets.pdf) | Articolo peer-reviewed; preview e WP completo, non identità garantita fra versioni | Motivazione del reversal **giornaliero con volume relativo basso**; premio concentrato in asset piccoli/illiquidi. Debole prior per BTC/ETH liquidi; long-short e fill semplificati non trasferibili automaticamente. |
| [Wang–Pang, Predictability on the Move, SSRN 7556359](https://papers.ssrn.com/abstract=7556359) | Working paper ottobre 2026; metadata/abstract, PDF non disponibile | Non ricostruibili da quell'accesso formula e segno di un particolare segnale. H2 non è una replica dei suoi molti predittori. |
| [Galati, Exchange market share…, 2024](https://doi.org/10.1016/j.jbankfin.2024.107222), [PDF istituzionale](https://cris.unibo.it/bitstream/11585/970807/1/Galati2024_JBF.pdf) | Peer-reviewed, testo pubblicato consultato | Più attività, anche sotto regimi senza fee, non implica necessariamente migliore liquidità. |
| [Han–Kang–Ryu, Momentum under realistic assumptions, 2026](https://doi.org/10.1093/rapstu/raag011) | Peer-reviewed, manoscritto accettato; abstract ufficiale, non testo a pagamento | Rendimento aritmetico significativo e profitto composto finanziabile sono questioni diverse. |

Controevidenze: [replica indipendente Han, SSRN 7624971](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7624971), working paper/abstract, instabilità dei premi; [Brauneis e altri, misure di liquidità](https://www.sciencedirect.com/science/article/pii/S0378426620303022), peer-reviewed, limiti delle proxy. Non sono repliche eseguite da noi. [Verifica completa e limiti di consultazione](/Users/locoframe/Desktop/TRADING%20BOT/reports/edge-discovery-round-2/literature.md).

## 2. Dati ammessi, periodi e limiti

Riutilizzati **485 coppie ZIP/CHECKSUM ufficiali già in cache: 439 daily e 46 hourly**, senza nuove acquisizioni. Disponibili OHLC, volumi base/quote, numero trade e acquisti taker; controllati timestamp/unità, continuità, valori e bounds dei campi. Il vecchio loader ometteva alcuni campi ausiliari: usato un lettore isolato, senza modificarlo.

- **H1:** BTCUSDT/ETHUSDT, daily per segnali e rischio, hourly per aperture e marcatura. 2022 completo e gennaio–novembre 2024: **33.600 barre orarie valutate** sui due asset. Periodi scelti per integrità temporale **prima dei nuovi risultati H1**; escluso 2023 con difetti orari noti, senza riparazioni selettive. Warmup daily completo per finestre fino a 32 chiusure.
- **H2:** 13.338 barre daily della coorte BTC, ETH, XRP, BCH, LTC, EOS, BNB. Sviluppo 2020–2022, diagnostica 2023, stress gennaio–novembre 2024. Coorte ancorata nel 2019, BSV già delistato escluso senza sostituzione; mantenuti eleggibilità storica, identità e giorno iniziale BCH parziale escluso.
- Eleggibilità causale: almeno 30 giornate complete e 31 chiusure valide; mediana quote-volume 30 giorni ≥10 milioni USDT. Nessuna selezione odierna dei sopravvissuti o eliminazione di perdenti.
- **Tutto questo storico era già osservato dal progetto**, compreso il vecchio test 2024. Anche 2025 e gennaio–settembre 2026 sono già esplorati e non vengono usati come nuovi holdout. Le partizioni sono verifiche cronologiche **esplorative**, non conferme indipendenti.

Il volume in USDT è una misura di attività riportata dall'exchange, **non spread, profondità o domanda esogena certificata**; dipende anche dal prezzo. Trade-count e taker-volume sono controlli/descrittori, non altri predittori provati per scegliere il migliore. Non attribuiamo causalmente un eventuale rendimento alla “liquidità” senza osservare quella liquidità.

[Inventario e prove sui dati](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/inventory.json).

## 3. Regole e criteri registrati prima dei risultati

### H1 — inversione dopo pressione negativa con volume relativo basso

Meccanismo ipotizzato: una pressione transitoria di vendita con partecipazione ridotta potrebbe riassorbirsi; il rischio contrario è comprare un ribasso informativo destinato a continuare. Il test compra dopo il movimento, non quota passivamente e non presume di incassare uno spread.

Per il giorno completato t: rendimento log negativo, z-score **<−1** rispetto ai **30 rendimenti precedenti escludendo t**, e `L=log(quoteVolume_t / media aritmetica dei30volumi precedenti)<0`. Ogni asset qualificato ha peso base 50%, altrimenti cash. Target ribilanciato per **delta netti** alle **01:00 UTC**, un'ora intera dopo la chiusura; unico vicino alle **02:00 UTC**. Non è uno shock orario, una replica Farag 5 minuti o una strategia maker. Soglia 1σ, asset e ritardo sono scelte tecniche esplicite, non parametri certificati dalla letteratura o ottimizzati sui risultati.

### H2 — volume relativo come unico segnale

Meccanismo ipotizzato, con supporto debole: un calo temporaneo dell’attività potrebbe richiedere un premio al capitale che rimane esposto. L’alternativa sfavorevole è perdita persistente di interesse e ulteriore ribasso; per questo il segno del rendimento non viene dato per certo.

Stessa L, senza filtro sul prezzo: selezionare i due valori eleggibili più bassi **sotto zero**, pesi base 50% ciascuno; uno lascia metà cash, nessuno tutto cash. Tie-break lessicografico. Ribilanciamento daily 00:00 UTC dopo **un intero giorno di disponibilità**: giorno i usa il dato i−2. Unico vicino: **due giorni**, i−3. Nessuna competizione fra trade-count, flussi taker, Amihud, segni opposti o decine di finestre.

### Rischio ed esecuzione comuni

1.000 USDT virtuali per segmento, reset flat, nessuno short/leva; pesi totali ≤1. I pesi base sono soltanto ridotti per un target di volatilità del portafoglio **20% annuo**, stimato dai 30 rendimenti log daily completi a pesi correnti, ddof=1, √365; questo rischio include il giorno di segnale già chiuso. Non è un limite a perdita giornaliera, esposizione o drawdown. Quantità frazionarie di ricerca, non griglie storiche certificate.

Acquisti alla ask sintetica e vendite alla bid sintetica da aperture native; vendite prima degli acquisti, riserva per fee e cassa non negativa. Delta netti: nessuna chiusura/riapertura artificiale quotidiana. NAV al valore di liquidazione con costo d'uscita riservato, non addebitato ripetutamente; costi finali espliciti. Dato richiesto mancante o posizione non marcabile: segmento incompleto, non prezzo inventato o forward-fill eseguibile.

| Scenario | Fee per lato | Slippage per lato | Spread intero | Frizione roundtrip approssimata |
|---|---:|---:|---:|---:|
| Base | 10 bp | 1 bp | 2 bp | 24 bp |
| Avverso | 15 bp | 5 bp | 10 bp | 50 bp |
| Severo | 20 bp | 10 bp | 20 bp | 80 bp |

Scenari di ricerca uguali per strategie/passivi, non tariffe reali certificate o sconti/rebate maker presunti. Senza quote storiche, spread e slippage restano ipotesi, non prezzi eseguibili osservati.

**Budget: quattro configurazioni, non grid search.** Per essere soltanto promettente: primario positivo base/avverso e non negativo severo in tutti i segmenti; vicino positivo base/avverso nel 2024; DD non peggiore del passivo risk-capped e confronto incrementale favorevole; almeno 180 giorni/30 attivi nello stress. Bootstrap paired daily 7/30 giorni, 10.000 repliche, seed 20261028, stessi indici e limite unilaterale α=0,05/2 positivo in entrambi. Per H1 differenza Sharpe col passivo ex ante; per H2 eccesso medio sul passivo a target d'esposizione abbinato, oltre al confronto Sharpe risk-capped. Criteri congelati prima del P&L, nessuna soglia post hoc sulla concentrazione.

[Protocollo](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/protocol.json) · [Configurazioni](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/config.json) · [Freeze](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/freeze.json).

## 4. Risultati netti effettivamente eseguiti

Rendimento composto sul capitale iniziale separato di ciascun segmento, **non previsione futura**.

| Ipotesi | Periodo | Base | Avverso | Severo |
|---|---|---:|---:|---:|
| H1 | 2022 | -2,94% | -4,10% | -5,42% |
| H1 | Gen–nov 2024 | -1,73% | -3,60% | -5,71% |
| H2 | 2020–2022 | -2,88% | -26,74% | -47,10% |
| H2 | 2023 | -7,84% | -23,08% | -37,58% |
| H2 | Gen–nov 2024 | 23,03% | 7,43% | -8,15% |

H1 è negativa persino nel modello base in entrambi i periodi. H2 sopravvive ai costi base/avversi soltanto nel 2024 e torna negativa nel severo. Il risultato 2024 non può cancellare gli altri periodi.

### Da dove viene il netto: contabilità sullo stesso percorso

| Ipotesi | Periodo | P&L ai prezzi grezzi, USDT | Fee+spread+slippage | P&L netto |
|---|---|---:|---:|---:|
| H1 | 2022 | -18,47 | 10,93 | -29,40 |
| H1 | Gen–nov 2024 | 0,22 | 17,55 | -17,33 |
| H2 | 2020–2022 | 249,52 | 278,29 | -28,77 |
| H2 | 2023 | 76,72 | 155,08 | -78,36 |
| H2 | Gen–nov 2024 | 366,61 | 136,32 | 230,29 |

Questa è una decomposizione degli stessi fill e quantità, **non un nuovo backtest a costo zero**. I tre scenari completi cambiano anche quantità/capitale successivo. Per H1 2024 il margine grezzo è appena **0,22 USDT** prima di **17,55** di frizioni; nel 2022 è negativo già grezzo. H2 nel 2024 paga **136,32 USDT** di frizioni, di cui fee 113,60: un segnale positivo sulla carta non basta quando il turnover lo consuma.

### Sensibilità preregistrata al ritardo, stress 2024

| Ipotesi | Unico vicino | Base | Avverso | Severo |
|---|---|---:|---:|---:|
| H1 | 2 ore | -0,73% | -2,62% | -4,75% |
| H2 | 2 giorni | 6,93% | -6,64% | -20,18% |

Il ritardo addizionale non salva H1. H2 scende a +6,93% base e **−6,64% avverso**: il criterio di robustezza fallisce senza cambiare alcuna soglia.

## 5. Benchmark, capitale esposto e rischio

Stress gennaio–novembre 2024, costi base. Candidati e comparatori principali hanno stessa cadenza/età dell'informazione e convenzione di rischio; buy & hold è un riferimento descrittivo investito all'inizio, non risk-matched. EW giornaliero non significa buy & hold statico.

| Configurazione | Netto | Sharpe daily √365 | DD daily | Esposizione media campionata |
|---|---:|---:|---:|---:|
| H1 | -1,73% | -0,40 | 2,71% | 2,27% |
| BTC/ETH EW risk-capped, ore 01 UTC | 42,78% | 1,82 | 15,54% | 39,90% |
| BTC/ETH con esposizione richiesta H1, diagnostico | -2,61% | -0,59 | 3,49% | 2,27% |
| H2 | 23,03% | 1,24 | 14,55% | 30,40% |
| Coorte sette asset EW risk-capped | 49,75% | 1,97 | 15,41% | 40,93% |
| Coorte EW con esposizione richiesta H2 | 21,47% | 1,28 | 11,03% | 30,39% |
| Coorte EW giornaliero senza cap | 103,07% | 1,64 | 36,64% | 100,00% |
| Buy & hold coorte iniziale | 95,47% | 1,57 | 38,75% | 100,00% |
| BTC buy & hold | 127,46% | 1,93 | 26,15% | 100,00% |
| ETH buy & hold | 61,92% | 1,13 | 45,26% | 100,00% |
| Cash | 0,00% | N/D | 0,00% | 0,00% |

Per H1 il comparatore che eredita l'esposizione del segnale è **solo diagnostico**: non è una prova indipendente del timing. H2 rende 15,56 USDT più dell'EW a esposizione richiesta abbinata, ma con Sharpe inferiore e incertezza che include assenza di vantaggio. Il matching riguarda i target noti, non esposizioni realizzate perfettamente identiche dopo costi/drift.

| Ipotesi, 2024 | Giorni attivi | Ordini di allocazione | Esposizione massima | Vol. daily annualizzata | Peggior giorno | Turnover totale due lati |
|---|---:|---:|---:|---:|---:|---:|
| H1 | 38 | 47 | 73,59% | 4,55% | -2,56% | 14,72× |
| H2 | 287 | 783 | 72,98% | 19,77% | -3,63% | 104,35× |

Esposizione campionata alle aperture hourly per H1/daily per H2, non osservata continuamente. Il **2,71% di DD H1** accompagna appena **2,27% d'esposizione media**, non dimostra un vantaggio; l'esposizione massima raggiunge comunque 73,59% e il DD orario è **4,03%**. La liquidità inutilizzata non equivale a qualità del segnale.

Per H2 **104,35× è turnover totale nei 335 giorni**, circa 113,70× annualizzato, **non 104 roundtrip**. I 783 ordini sono ribilanciamenti, non altrettanti trade indipendenti. Il PF del P&L giornaliero 2024 è H1 0,788 e H2 1,203, non PF per trade.

## 6. Stabilità, concentrazione e significatività

H2 base, rendimenti per anno all'interno della relativa curva:

| Anno | Netto |
|---|---:|
| 2020 | -3,95% |
| 2021 | 24,37% |
| 2022 | -18,70% |
| 2023 | -7,84% |
| 2024 gen–nov | 23,03% |

H2 perde anche nel 2020 e 2022; nel 2023 ha DD **26,19%**, peggior giorno **−6,85%** e agosto **−12,89%**. Nel 2024 soltanto 6 degli 11 mesi sono positivi. I cinque giorni migliori sommano **218,15 USDT**, circa **94,73%** dei +230,29 netti. Togliendoli contabilmente rimangono +12,14: diagnostica sul percorso fisso, non backtest eseguibile o giorni da eliminare.

Il regime causale BTC90 giorni positivo/non positivo è soltanto descrittivo: H1 2024 +3,87/−21,20 USDT; H2 +215,73/+14,56. Sono segmentazioni note, non filtri da aggiungere dopo il risultato. Tabelle mensili, anni e regimi completi sono archiviate.

| Confronto stress base | Intervallo bootstrap 95%, blocchi 7 | Blocchi 30 |
|---|---|---|
| H1 differenza Sharpe vs risk-capped | [−4,708; +0,503] | [−4,759; +0,248] |
| H2 eccesso di rendimento medio giornaliero vs EW abbinato | [−4,664; +6,096] **bp/giorno** | [−3,941; +6,093] **bp/giorno** |

Entrambi i limiti inferiori corretti sono negativi. La bootstrap mantiene accoppiati strategia/comparatore e dipendenza a blocchi; è **condizionale ed esplorativa su storia già vista**, non significatività globale, OOS indipendente o probabilità di guadagno futuro. DSR globale non stimabile: il numero totale dei tentativi passati è ignoto. Quattro varianti, scenari di costo, benchmark e righe di report non sono scoperte indipendenti. [Criteri applicati senza modifiche](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/assessment.json).

## 7. H3: perché non abbiamo fabbricato un backtest maker

Il margine economico maker dipende da spread e rebate effettivamente incassati meno fee, adverse selection e costi dell’inventario/uscita. Nello spot long/flat la vendita richiede asset già detenuti e gli acquisti cassa disponibile: non è ammesso inventario negativo per replicare un market maker long-short.

Non possediamo uno storico Binance adeguato per stimare priorità/posizione in coda, cancellazioni, riempimenti, latenza e adverse selection condizionata al fill. OHLC, trade aggregati, un bookTicker L1 e pochi minuti di capture non bastano; neppure la sola profondità aggregata rende certa la priorità individuale.

**Tocco del limite ≠ fill.** Non assumiamo acquisti al minimo, vendite al massimo o un rebate senza conto e condizioni verificati. Le inversioni osservate negli articoli non sono una certificazione dell'esecuzione maker. Prima di un test servirebbero storico e modello di coda validato; **nessuna nuova raccolta, infrastruttura o acquisto è proposto in questa campagna**. H3 resta non valutabile, non confutata economicamente.

## 8. Verifiche, riproduzione e chiusura

- **16 test sintetici PASS**, replicati indipendentemente prima dei risultati: lag/causalità, esclusione del dato corrente, rischio, campi ausiliari, netting, cassa/costi, terminale, timestamp e qualità locale, release e bootstrap. Il RED iniziale era modulo assente; una fixture terminale errata è stata corretta prima dei risultati con la precedente ricevuta conservata, senza cambiare regole economiche.
- **8 sorgenti, 986 input e 179 protetti invariati** dopo l'esperimento. B, il suo protocollo prospettico e i tre report precedenti preservati; importate soltanto primitive pure di contabilità/statistica, non eseguita B. Nessun runtime, journal, account, Docker, Databento, feed o dashboard modificato/attivato.
- **137 JSON riprodotti byte-identici** in una copia workspace separata, senza rete, acquisti o sovrascrittura delle evidenze originali. 135 righe nella tabella completa: non 135 strategie provate. Nessuna modifica post-risultati di sorgenti, parametri o criteri.

[Comandi completi per riproduzione offline sicura](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/README.md) · [Tabella completa](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/compact-results.csv) · [Metriche/anni/mesi/regimi/gate](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/summary.json) · [Manifest consegna](/Users/locoframe/Desktop/TRADING%20BOT/research/edge-discovery-round-2/delivery.json) · [Validazione indipendente](/Users/locoframe/Desktop/TRADING%20BOT/reports/edge-discovery-round-2/adversarial-plan.md).

Test locali, senza lanciare nuovi esperimenti:

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q research/edge-discovery-round-2/test_round2.py
```

Per rifare gli esperimenti eseguire il blocco di **workspace mirror** nel README: ricopia input e primitive pure con la stessa struttura relativa, esegue il runner offline e confronta gli hash. Il runner originale rifiuta deliberatamente risultati già presenti; non cancellarli o rifare il freeze.

SHA256 principali:

```text
freeze     7babd1856493c95ad201a2c0b0d6a5c8786e2c91c958cef14027133652e1149f
risultati  0e80b048c6628c17f2f3df6cff7369e7e91a6ee984ea58d68662600bf62ecf2c
assessment 1773ae0a3107f6326c18d74e89b437fe21b645fe77b4d42123fffd78651a2e6a
```

### Raccomandazione tecnica ed economica

**NESSUNA NUOVA CANDIDATA PROMOSSA.** Archiviare H1/H2 nelle configurazioni testate e non investirvi sviluppo operativo, nuovi filtri o AI. H3 non può essere backtestata onestamente con i dati attuali. Non attivare nuovi forward automatici e non avviare altre dieci ipotesi per cambiare questo esito. B rimane separata e congelata, senza rivalutazioni o attivazioni.

> Abbiamo trovato meccanismi interessanti nella letteratura, ma non un nuovo vantaggio sufficientemente robusto e utilizzabile dal nostro bot. Una regola perde; l'altra guadagna in un anno ma non resiste a costi e confronti seri. Per la terza non abbiamo i dati necessari. La campagna si chiude qui: conserviamo le prove e non impegniamo capitale.
