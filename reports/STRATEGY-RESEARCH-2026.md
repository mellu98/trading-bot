# Strategy Research 2026 — servono dati futuri, nessuna strategia promossa

**28 ottobre 2026 — decisione obbligatoria: B — SERVONO DATI FUTURI.**

Abbiamo eseguito un confronto congelato, non una ricerca del parametro vincente. **A e B producono utili storici netti, ma nessuna supera tutti i criteri stabiliti prima dei risultati.** B presenta punti stimati interessanti per rischio e drawdown nel test storico 2024; l'incertezza comparativa e il debole 2023 impediscono di attribuirle un vantaggio credibile. C non è economicamente misurata: ha un blocco di qualità/prerequisiti dello storico orario. Non è una strategia dimostrata perdente.

**Nessuna integrazione nel runtime, nessun forward operativo avviato, nessun ordine, nessuna spesa.** Restano archiviati il precedente BTC 4h e i risultati futures/Timestral. Tutti i 179 file protetti sono invariati.

## 1. Evidenze scientifiche e limiti delle fonti

| Fonte ufficiale/primaria consultata | Evidenza utile | Limite effettivo della consultazione e del trasferimento |
|---|---|---|
| [Liu–Tsyvinski, NBER w24877](https://www.nber.org/papers/w24877) | Momentum e dinamiche specifiche crypto motivano una prova semplice. | Abstract/frontespizio e [lista pubblicazioni Yale](https://economics.yale.edu/people/aleh-tsyvinski/papers), non testo integrale. Gli autori sono **due**: Goldstein non è coautore di questo lavoro. Non prova la nostra redditività netta. |
| [Guo e altri, 2024](https://www.sciencedirect.com/science/article/pii/S0165188924000551) | Possibile trasmissione di informazione fra crypto. | Abstract, introduzione e frammenti metodologici, non appendici/codice. Dati al **minuto**, non orari. Universo selezionato nel 2020 applicato anche al 2019: cautela ex post. La nostra C ritardata non è una replica. |
| [Risk-managed momentum, Yang 2025](https://www.sciencedirect.com/science/article/pii/S1544612325011377) | Motivazione di momentum e controllo della volatilità. | Frammenti del publisher: long winner/short loser, scaling medio 1,14; campione/costi completi non verificati. Non prova uno spot long/cash senza leva. |
| [Arefev, SSRN 7404139](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7404139) | Controevidenza sulla robustezza netta dopo spread. | Working paper indipendente settembre 2026, non peer-reviewed; metadata/abstract verificati, PDF non verificato. Perpetual 2020–2026, non il nostro spot. Non replicato qui. |
| [Bailey–López de Prado, DSR](https://doi.org/10.3905/jpm.2014.40.5.094), [PDF autore](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) | Correzione per selezione e tentativi multipli. | PDF autore consultato. Il numero globale dei tentativi passati del progetto è ignoto: **DSR globale non stimabile**, non inventiamo N=3 o N=6. |

Ulteriore controevidenza peer-reviewed: [Grobys e altri 2025](https://link.springer.com/article/10.1007/s11408-025-00474-9), crash e instabilità del momentum. Nessuna di queste fonti dimostra che il nostro adattamento sia profittevole. [Note e fonti dettagliate](/Users/locoframe/Desktop/TRADING%20BOT/reports/strategy-research-2026/literature.md).

## 2. Regole congelate: tre famiglie, massimo sei configurazioni

Capitale iniziale **1.000 USDT per segmento**, spot long/cash, niente short o leva; pesi aggregati ≤100%, acquisti finanziati dalla cassa dopo commissioni. Quantità frazionarie continue di ricerca, non griglie storiche certificate. Non sono trasferiti i vecchi limiti futures, il cap di ingresso 100 USDT o lo stop da 1 USDT del precedente test tecnico.

### A — momentum cross-sectional

Coorte storica BTC, ETH, XRP, BCH, LTC, EOS, BNB. Ogni lunedì 00:00 UTC si selezionano i due rendimenti a **14 giorni** più alti, soltanto se positivi; peso iniziale 50% ciascuno. Un solo vincitore impiega 50%, nessuno lascia tutto cash. Eleggibilità: almeno 30 giornate intere consecutive e 31 chiusure per i rendimenti, mediana del quote-volume USDT degli ultimi 30 giorni ≥10 milioni. I pesi sono scalati verso il basso, mai verso l'alto, per un cap di volatilità annua prevista **20%**, stimata sui 30 rendimenti log giornalieri passati del portafoglio a pesi correnti, deviazione campionaria ddof=1 e √365. Unico vicino: lookback **7 giorni**.

### B — trend time-series BTC/ETH

Stesso ribilanciamento settimanale e ritardo di A. Ogni sleeve BTC/ETH ha peso `0,5 × indicatore(rendimento90giorni > 0) × min(1; 20% / volatilità30giorni)`. Volatilità su rendimenti log giornalieri, ddof=1, √365; niente leva. Identica eleggibilità causale di liquidità/storia. Unico vicino: **60 giorni**, non scelto dopo il risultato. Nessuno stop fisso o target viene aggiunto: è un modello di allocazione long/cash, non una garanzia di perdita massima.

### C — impulso BTC verso ETH

Z-score del rendimento log orario BTC rispetto alle **168 ore precedenti escludendo l'ora corrente**; ingresso ETH se z>1. Si attende **un'intera ora dopo la chiusura** prima dell'apertura di esecuzione; mantenimento un'ora, poi uscita. Unica sensibilità: ritardo di **due** ore, soglia invariata. Una posizione, fino al 100% della cassa disponibile incluse riserve per costi; uscita dovuta prima di un eventuale nuovo ingresso, con entrambe le frizioni. Non è la replica del modello accademico al minuto.

**Disponibilità:** per A/B il lunedì si usano dati chiusi entro la domenica 00:00 UTC, cioè l'ultima barra termina un giorno intero prima del fill modellato. Nessun fill alla stessa frontiera in cui nasce il dato. I segmenti ripartono flat e includono costi iniziali/finali; nessun capitale viene concatenato fra sviluppo, validazione e test.

[Protocollo completo](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/protocol.json) · [Configurazioni](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/config.json).

## 3. Dati, universo e integrità

Fonte: [archivi pubblici ufficiali Binance](https://github.com/binance/binance-public-data), solo ZIP mensili e relativi CHECKSUM. Prima inventariati i 22 archivi BTC 1h dicembre 2024–settembre 2026 già osservati: **non sono nuovi test indipendenti** e non sono stati riciclati come holdout. Per questo esperimento sono stati acquisiti soltanto i daily dei sette asset e gli hourly BTC/ETH necessari. Il backtester precedente è BTC-only e accoppiato al runtime protetto: il minimo calcolo di portafoglio multiasset è rimasto in script puri offline isolati, senza un nuovo motore operativo.

- **559 coppie ZIP/CHECKSUM**, 1.118 GET pubblici, nessun endpoint privato: **5.931.934 byte compressi inclusi checksum**, 15.906.019 decodificati. Tutti gli hash ufficiali corrispondono; originali e ricevute UTC conservati.
- Warmup daily settembre–dicembre 2019; orario dicembre 2019. Intervalli UTC semiaperti: sviluppo **2020-01-01 → 2023-01-01**, validazione **2023-01-01 → 2024-01-01**, test **2024-01-01 → 2024-12-01**: 1.096, 365 e 335 giorni.
- Il 2024 è stato scaricato e aperto soltanto dopo configurazioni, controllo indipendente e risultati sviluppo/validazione, senza modificarne le regole. È un **test storico segregato del progetto**, non prospettico; conoscenza pubblica degli eventi storici non esclusa. Ora è consumato e non può tornare holdout per altre varianti.
- Universo ancorato allo [snapshot 29 dicembre 2019](https://coinmarketcap.com/historical/20191229/): primi otto non-stablecoin, escluso BSV già delistato da Binance, **senza sostituirlo** con un successivo vincitore. Non è un universo di sopravvissuti scelto oggi; resta comunque una coorte piccola, non tutto il mercato crypto.
- EOS: esistenza pre-ancora provata da 30 barre nell'archivio ufficiale settembre 2019. BCHUSDT parte il 28 novembre 2019; quel giorno parziale non vale come giornata intera e non viene ricostruito retroattivamente da BCHABC. Le eleggibilità successive dipendono soltanto dalla storia già chiusa.
- Verificati timestamp/unità, estremi mensili, conteggi, duplicati, continuità e validità OHLC/volumi. Test per millisecondi e microsecondi: i nuovi archivi 2019–2024 sono in ms; non si generalizza ai file spot dal 2025 in µs.

### C: blocco reale, con limite del loader dichiarato

Gli hourly BTC/ETH dicembre 2019–dicembre 2023 hanno ciascuno **35.777 righe contro 35.808 attese**, 15 transizioni con gap e 8 barre con durata irregolare, compreso il **24 marzo 2023**: il problema riguarda davvero anche la validazione, non soltanto sviluppo. Nessun riempimento, prezzo eseguibile inventato o liquidazione retrospettiva.

**Nel 2024 ci sono invece 8.040 barre orarie per asset, senza gap o durate irregolari nel controllo timestamp.** Il loader congelato richiede continuità dell'intera storia e propaga il rifiuto dopo il primo mese scartato: non permette una valutazione autonoma di C sul successivo segmento pulito. Il risultato C è quindi **NON CALCOLATO / prerequisito storico-validazione incompleto**, non P&L negativo e non prova di dati 2024 difettosi. Non è stato avviato un altro ciclo di riparazioni o una selezione di sottofinestre favorevoli. A/B daily non sono compromesse.

[Prova qualità](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/blind-data-proof.json) · [Diagnosi solo timestamp](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/hourly-timestamp-diagnostic.json) · [Prova holdout](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/blind-holdout-proof.json).

## 4. Costi, esecuzione e criteri fissati prima degli esiti

| Scenario | Commissione per lato | Slippage per lato | Spread intero |
|---|---:|---:|---:|
| Base | 10 bp | 1 bp | 2 bp |
| Avverso | 15 bp | 5 bp | 10 bp |
| Severo | 20 bp | 10 bp | 20 bp |

Sono ipotesi prudenti di ricerca, **non tariffe certificate di un conto**. Acquisti alla ask sintetica e vendite alla bid sintetica ricavate dall'apertura storica, slippage sfavorevole, fee su ogni lato, vendite prima degli acquisti e riserva di cassa. Nessun forward-fill eseguibile. NAV giornaliera al valore di liquidazione, riservando una sola uscita ipotetica senza addebitarla ripetutamente alla cassa; la liquidazione finale realizza il costo una volta. Identico criterio per strategie e benchmark.

Congelati: segni netti positivi base/avverso e non negativi severo sia in validazione sia nel test; vicino positivo base/avverso nel test, senza poter salvare la primaria; DD giornaliero del test non peggiore del passivo risk-capped. A deve aggiungere rendimento medio giornaliero rispetto all'EW con esposizione richiesta abbinata e non peggiorare lo Sharpe risk-capped; B/C devono migliorare lo Sharpe rispetto al proprio passivo risk-capped ex ante.

In più: bootstrap **paired**, stessi indici giornalieri, blocchi circolari contigui **7 e 30 giorni**, 10.000 repliche, seed 20261028. Limite inferiore unilaterale a **α=0,05/3** positivo in entrambi, soltanto sui costi base del test. È controllo condizionale delle tre famiglie correnti, non una correzione globale di tutti i tentativi del progetto. Nessuna soglia aggiunta dopo i risultati di validazione.

## 5. Risultati economici effettivamente eseguiti

Rendimenti sul capitale iniziale del singolo segmento, **non rendimenti annuali promessi**. Sharpe giornaliero √365; DD sulla NAV giornaliera di liquidazione, non intraday.

| Periodo | Famiglia | Netto base | Netto avverso | Netto severo | Sharpe base | DD base |
|---|---|---:|---:|---:|---:|---:|
| Sviluppo 2020–2022 | A | 87,96% | 79,80% | 70,81% | 1,15 | 26,33% |
| Sviluppo 2020–2022 | B | 66,13% | 64,52% | 62,67% | 1,08 | 20,05% |
| Validazione 2023 | A | 18,51% | 15,41% | 11,93% | 0,97 | 17,30% |
| Validazione 2023 | B | 3,22% | 2,19% | 1,02% | 0,27 | 18,42% |
| Test gen–nov 2024 | A | 20,12% | 17,57% | 14,70% | 1,22 | 13,06% |
| Test gen–nov 2024 | B | 42,54% | 41,67% | 40,66% | 2,34 | 8,71% |

C: nessun rendimento o metrica economica disponibile nei tre segmenti per il limite descritto. I booleani `false` nei suoi gate indicano mancata verifica/fail-closed, non perdite misurate.

### Dettaglio del test 2024, base

| Famiglia | P&L USDT | Ordini simulati | PF P&L giornaliero | Sortino | Max esposizione osservata | Turnover totale a due lati |
|---|---:|---:|---:|---:|---:|---:|
| A | 201,18 | 110 | 1,21 | 1,95 | 66,24% | 16,56× |
| B | 425,40 | 72 | 1,49 | 4,21 | 61,52% | 4,76× |

**110/72 sono ordini di allocazione/ribilanciamento, non 110/72 roundtrip indipendenti.** Il PF aggrega P&L giornalieri, non vincite/perdite per trade; non ne ricaviamo una finta expectancy per operazione. B chiude il segmento con **1.425,40 USDT virtuali**, A con **1.201,18**. CAGR puramente storico: A 22,11%, B 47,14%; non estrapolabile.

| Famiglia | Fee USDT | Spread modellato USDT | Slippage USDT | Frizioni complessive USDT |
|---|---:|---:|---:|---:|
| A | 17,63 | 1,76 | 1,76 | 21,16 |
| B | 5,99 | 0,60 | 0,60 | 7,19 |

I costi influenzano quantità e percorso: gli scenari non sono soltanto una sottrazione aritmetica da trade immutati. Non includono imposte, lavoro, hardware o costi di custodia.

### Sensibilità predefinita, non selezione del migliore

| Famiglia | Unico vicino | Netto base | Avverso | Severo | DD base |
|---|---|---:|---:|---:|---:|
| A | 7 giorni | 10,83% | 7,78% | 4,36% | 25,33% |
| B | 60 giorni | 29,75% | 28,83% | 27,77% | 16,54% |

Il segno positivo sopravvive, ma A cambia molto per DD/rendimento e B60 rende meno di B90. Non sono prove di ottimalità né autorizzano altri tentativi per migliorare il risultato.

## 6. Benchmark: quanta parte viene dal mercato e dall'esposizione

Tutti sul medesimo segmento 2024 con i costi base e contabilità coerente. I passivi risk-capped usano gli stessi stimatori/cadenze della relativa strategia, senza il segnale di trend/ranking. Buy & hold investe all'inizio del segmento; le strategie partono dal primo lunedì previsto.

| Configurazione | Netto | Sharpe | DD | Esposizione media |
|---|---:|---:|---:|---:|
| A — momentum relativo | 20,12% | 1,22 | 13,06% | 26,06% |
| Universo A equal-weight + cap volatilità | 54,04% | 2,04 | 14,88% | 41,21% |
| Universo A EW con esposizione richiesta di A | 33,39% | 1,83 | 14,12% | 26,10% |
| Universo A EW settimanale senza cap | 105,34% | 1,66 | 36,93% | 100,00% |
| Universo A buy & hold coorte iniziale | 95,47% | 1,57 | 38,75% | 100,00% |
| B — trend BTC/ETH | 42,54% | 2,34 | 8,71% | 25,79% |
| BTC/ETH passivo + stesso cap per sleeve | 44,55% | 1,91 | 13,66% | 39,02% |
| BTC/ETH EW con esposizione richiesta di B | 42,44% | 2,31 | 8,46% | 25,78% |
| BTC/ETH EW settimanale senza cap | 96,20% | 1,58 | 35,45% | 100,00% |
| BTC buy & hold | 127,46% | 1,93 | 26,15% | 100,00% |
| ETH buy & hold | 61,92% | 1,13 | 45,26% | 100,00% |
| Liquidità | 0,00% | N/D | 0,00% | 0,00% |

**A:** +20,12% è inferiore sia all'EW con esposizione richiesta abbinata (+33,39%) sia all'EW risk-capped (+54,04%). Il ranking non dimostra valore aggiuntivo nella configurazione testata.

**B:** +42,54% è leggermente sotto il passivo risk-capped +44,55%, ma con Sharpe migliore e DD minore. Resta però investita mediamente **25,79%**, contro **39,02%** del passivo: parte della protezione dipende dal minore capitale a rischio. L'EW che eredita l'esposizione richiesta di B produce +42,44%, quasi uguale: è una diagnostica, **non un test indipendente del timing** che eredita. Il matching riguarda i target noti, non esposizioni realizzate identiche dopo costi e drift. Nessuno di questi confronti dimostra alpha.

## 7. Stabilità temporale, regimi e concentrazione

Rendimenti annuali a costi base entro la curva del rispettivo segmento; sviluppo non viene resettato ogni anno.

| Anno | A | B |
|---|---:|---:|
| 2020 | 52,03% | 48,38% |
| 2021 | 50,58% | 24,56% |
| 2022 | -17,90% | -10,11% |
| 2023 | 18,51% | 3,22% |
| 2024 gen–nov | 20,12% | 42,54% |

Nel 2023 A +18,51% contro +25,74% dell'EW risk-capped; B appena +3,22% contro +45,11% del passivo BTC/ETH risk-capped. Il migliore rischio stimato di B nel 2024 **non è stabile in tutti i periodi**: nel 2023 il suo DD è 18,42%, contro 16,05% del comparatore. Entrambe perdono nel 2022.

Classificazione causale del regime: rendimento BTC90 giorni positivo/non positivo già disponibile al momento considerato, non regimi costruiti guardando il futuro.

| Famiglia, test 2024 | P&L in regime BTC90 positivo | Negli altri giorni | Primi 5 giorni / utile netto | Netto togliendo contabilmente quei 5 giorni |
|---|---:|---:|---:|---:|
| A | 170,06 | 31,12 | 85,26% | 29,66 |
| B | 412,83 | 12,57 | 54,95% | 191,63 |

Circa **97%** dell'utile B 2024 cade nel regime positivo. Nel 2023 un solo giorno B vale circa **127%** dell'utile annuale: togliendolo dalla contabilità storica restano −8,75 USDT. Per A i cinque migliori giorni valgono circa 133% dell'utile 2023. Sono **giorni**, non trade. Rimuoverli è una diagnostica a percorso fisso, non un nuovo backtest eseguibile, e non giustifica eliminarli operativamente.

## 8. Incertezza e decisione per famiglia

| Famiglia | Evidenza incrementale nel test | Limite inferiore corretto, blocchi 7 / 30 | Esito |
|---|---|---|---|
| A | Ranking peggiore del comparatore abbinato; Sharpe 1,222 < 2,039 risk-capped | −0,1266% / −0,1228% di rendimento giornaliero in eccesso | Non promossa: manca un vantaggio aggiuntivo convincente. |
| B | Differenza Sharpe puntuale +0,428; DD migliore | −0,828 / −0,533 di differenza Sharpe | Non promossa: extra beneficio corretto per rischio inconcludente. |
| C | Non misurata | N/D | Non promossa per evidenza insufficiente; non economicamente confutata. |

Per B gli intervalli bootstrap bilaterali 95% della differenza Sharpe sono **[−0,731; +1,661]** con blocchi 7 e **[−0,473; +1,428]** con blocchi 30. Entrambi includono assenza di vantaggio; anche i limiti unilaterali corretti falliscono. Nessuna probabilità di profitto futuro viene dedotta da questi intervalli.

Il periodo finale contiene 335 giornate dipendenti e un regime storico specifico, non 335 prove indipendenti. I vicini sono correlati. Bootstrap condizionata al percorso osservato, senza ricreare le decisioni su nuovi mercati; incertezza di specifica, rischio USDT/depeg e conoscenza storica pubblica non eliminati. **DSR globale non stimabile**, tentativi storici ignoti. [Esito meccanico dei criteri](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/assessment.json): nessuna famiglia passa la congiunzione.

## 9. Eseguibilità e verifiche software

- Nessun bid/ask storico o coda d'esecuzione osservata: spread, slippage e disponibilità all'apertura dopo un intero lag restano modelli, non fill certificati. Quantità/minimi/griglie, impatto, arresti dell'exchange e custodia non sono verificati economicamente.
- La volatilità target non è una garanzia; DD giornaliero sottostima possibili escursioni intraday. Questi modelli non possiedono un nuovo stop server-side. USDT è trattato alla pari con il cash, remunerazione zero.
- **23 test sintetici realmente eseguiti**, replicati indipendentemente: costi/cassa, lag, esclusione del dato corrente, unità timestamp, gap e isolamento famiglie, riapertura/uscita, frontiere temporali e release. Il RED iniziale era assenza del modulo, non la dimostrazione di un bug riparato del vecchio runtime.
- Controllo scientifico indipendente cieco al nuovo P&L prima dell'esecuzione. Unica correzione pre-dati del freeze iniziale: diagnostica BTC incompleta non deve far fallire famiglie valide; versione precedente conservata. Nessuna modifica di sorgente o parametro dopo i risultati.
- **219 JSON riprodotti byte-identici offline** su copia separata e stessi archivi; nessuna riscrittura dei risultati originali. La tabella CSV ha 216 righe fra benchmark/costi/periodi/blocchi: **non 216 tentativi indipendenti**. Sei configurazioni predefinite, di cui due C non calcolabili economicamente.
- **179 file protetti invariati**; niente runtime operativo, account, Docker, Databento, chiavi, journal, dashboard o servizi riattivati. Timestral resta fuori. Nessun ordine reale o simulato nel bot operativo.

Repository Git/facade `gentle-ai` non disponibili e CodeGraph non inizializzato/utilizzabile in questa workspace: usata ricognizione mirata delegata. Nessun commit o ricevuta di autorità nativa viene dichiarato. Il controllo scientifico e gli hash sono evidenze distinte, non sostituti fittizi di tali ricevute.

## 10. Raccomandazione e prossimo esperimento minimo

### B — SERVONO DATI FUTURI

**Non promuovere nessuna strategia. Non integrare A, B o C nel runtime e non avviare ingressi automatici o un forward operativo della strategia.**

A non giustifica altro sviluppo di questa configurazione di ranking; C resta una domanda non risolta, non un risultato negativo. B è soltanto l'ipotesi congelata che offrirebbe più informazione da un successivo dato nuovo, grazie al punto rischio/rendimento e alla bassa rotazione: **non il vincitore statisticamente validato fra tre**. Il suo fallimento dei gate rimane valido.

Se la ricerca prosegue, il prossimo esperimento minimo è **offline/prospettico, senza nuovo runtime**: conservare B90, vicino60, costi e comparatori immutati; finestra futura fissata oggi **[2026-11-01, 2027-11-01) UTC**, con warmup solo precedente, archivi pubblici BTC/ETH e nessun acquisto. Raccolta/controllo qualità non deve selezionare periodi favorevoli. Nessuna consultazione economica intermedia, selezione di nuovi parametri o estensione fino al successo; una sola valutazione finale. Riapplicare segni base/avverso/severo, vicino, DD e Sharpe relativo, stessi bootstrap 7/30 giorni e α=0,05/3. Dati incompleti o statistica non definita restano mancata promozione; una CI non positiva resta inconcludente/non promossa. Dodici mesi non garantiscono potenza sufficiente. **Protocollo proposto, non raccolta o attivazione avviata.**

Non acquistare dati, non aggiungere AI o funzionalità operative per trasformare un backtest positivo in una falsa approvazione.

### Da spiegare ai due soci

> Abbiamo testato regole fissate prima di guardare i risultati. Due approcci guadagnano nella simulazione storica, ma uno non aggiunge valore rispetto a una distribuzione passiva e l'altro non dimostra ancora che la migliore protezione sia ripetibile. Il terzo non è stato misurabile correttamente. Conserviamo il codice; non mettiamo soldi e non attiviamo il bot. Se vogliamo una prova in più, usiamo soltanto dati futuri e la stessa regola semplice, senza cambiarla dopo ogni risultato.

## Artefatti e riproduzione

- [Sorgenti, configurazioni, cache e comandi completi](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/README.md).
- [Tabella completa](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/compact-results.csv), [anni/regimi/concentrazione](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/primary-summary.json).
- [Freeze sorgenti](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/source-freeze.json), [manifest consegna](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/delivery.json), [riproducibilità](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/reproducibility.json).
- [Validazione avversaria e cronologia](/Users/locoframe/Desktop/TRADING%20BOT/reports/strategy-research-2026/adversarial-plan.md).

Hash SHA256:

```text
sorgenti   17d58cc404464ff6e812755cf514f98e14eaa7e29ae608310d03f073b1e0b410
dev/val    eb58d14e51c30138763ff59fed1e4d3d6d715d6623c012d819337fc33c01453a
holdout    f6103de9f45b26f800979e831b94ad494c37bc15b92c1586739ba0f89ba97526
assessment bceb400d4a0b438559ddda75bd3dfef7c8881aff939e4fa7f26aa3e4b34ce2d5
```

Test locali senza rete:

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python -m pytest -q research/strategy-discovery-2026/test_engine.py
```

Per rifare tutti i numeri, eseguire il blocco **Completed-run reproduction without overwriting evidence** nel README collegato: crea una copia isolata con cache e ricevute, poi esegue `runner.py development-validation`, `runner.py holdout`, `assess.py` e confronta tutti i 219 JSON. Il secondo run nella directory originale rifiuta deliberatamente di sovrascrivere le evidenze. Non rieseguire l'acquisizione.
