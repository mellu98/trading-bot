# Trading Bot — verdetto tecnico ed economico

**Data: 28 ottobre 2026. Raccomandazione principale: CAMBIARE STRATEGIA.**

**Forza delle evidenze: media per questa decisione di investimento; bassa per stimare il rendimento futuro.** La configurazione BTC/USDT 4h non ha dimostrato un vantaggio abbastanza robusto da giustificare altro sviluppo operativo. Conservare la piattaforma, ma archiviare questa configurazione come **non promossa**: niente denaro reale, nuovi abbonamenti, AI o ulteriore hardening destinato a renderla operativa. Non significa che ogni strategia automatica sia impossibile, né che sia dimostrato un rendimento atteso negativo di questa regola.

## A. Cosa abbiamo costruito

Esiste una piattaforma riutilizzabile di ricerca e simulazione: dati storici verificati, backtest riproducibili, Risk Engine, posizioni simulate, journal SQLite e recupero dello stato. Il collegamento pubblico Binance ha fornito prezzi reali e consentito un roundtrip tecnico automatico, con un BUY e un SELL **eseguiti soltanto nel simulatore locale**. Contabilità e saldo virtuale si riconciliano. Non sono ordini accettati da Binance né guadagni reali.

La distinzione decisiva è questa:

- **Runtime operativo esistente:** esegue il test tecnico una tantum, non la strategia breakout 4h.
- **Strategia 4h:** implementata nel simulatore offline.
- **Collector forward:** acquisisce contesto e dovrebbe registrare condizioni, ma non costruisce conto, ammissione del rischio, portafoglio o ordini; è sempre non operativo.

Non abbiamo quindi già un bot 4h autonomo al quale manchi soltanto un feed perfetto. Abbiamo componenti utili, ma la catena operativa della strategia non è stata dimostrata.

## B. Problemi tecnici e incidenza reale

| Evidenza verificata | Significato concreto |
|---|---|
| Dopo il riavvio, B per 300,098 secondi: zero superamenti di 250 ms; massimo elaborazione 5,345 ms; event loop 29,864 ms | Le pause precedenti non si sono ripresentate in quella finestra. Non è certificazione di continuità o ripetibilità. |
| Nello stesso test, 13 campioni book e 67 trade non freschi dopo inizializzazione; 13 iniziali sconosciuti | La soglia originale di 2 secondi rimane fallita: gli ingressi devono restare bloccati. |
| 40 trade identici disponibili nel REST già ricevuto prima della ricezione WS, massimo 1,437 secondi | Differenza di disponibilità misurata con orologio monotono, non prova della causa o della latenza di rete. |
| Overflow WebSocket corretto; separato overflow del worker I/O non critico aveva arrestato l'observer completo | Non tutti i problemi di stabilità sono risolti. Le due code non vanno confuse. |
| Stop soltanto virtuale nello stesso processo | Senza processo e prezzo fresco l'uscita può rimanere pendente. Non esiste una protezione server-side verificata. |

La revisione dei log ha aggiornato il precedente conteggio: **75 risposte native 4h**, cinque avvii di contesto e 70 fetch successivi, ma **zero condizioni di segnale 4h registrate** e 199 eventi di blocco. Il collector interroga la dashboard prima di registrare la condizione: con observer spento, quella dipendenza fallisce.

Per la barra terminata il 27 ottobre alle **20:00 UTC**, la prima risposta completa registrata dal nostro percorso arriva alle **20:15:22,497649 UTC**. Questo include polling ed errori del nostro percorso; non è il tempo di pubblicazione dimostrato dell'exchange. Rende comunque impossibile sostenere che quel percorso potesse eseguire all'apertura delle 20:00.

È stato inoltre riprodotto offline un difetto circoscritto: il collector usa una singola `read(1000001)` e poi interpreta il JSON, ma la lettura può restituire solo il primo chunk. Con la libreria installata, un corpo valido di 34 byte viene letto inizialmente per 10 byte e produce `JSONDecodeError`. I byte delle vecchie risposte fallite non erano conservati: il difetto è confermato, non la causa unica di ogni errore storico. **Nessun file protetto è stato corretto durante questa valutazione.**

Conclusione tecnica: le oscillazioni di pochi millisecondi non meritano altro lavoro indefinito. Disponibilità della barra, collegamento reale della strategia, recupero e protezioni sono invece requisiti materiali, non perfezionismo teorico. L'orizzonte 4h non li annulla.

## C. Risultati economici verificati

### Regole e capitale

BTCUSDT spot, solo long/flat, una posizione e nessuna leva. Entrata su chiusura 4h superiore ai massimi delle **20 barre precedenti**; uscita su chiusura inferiore ai minimi delle **10 precedenti**. Stop iniziale fisso a **2 ATR**, con ATR aritmetico su 14 barre complete; niente target o trailing. Il modello entra/esce all'apertura dell'ora nativa successiva al segnale.

Capitale virtuale iniziale **1.000 USDT**, massimo **100 USDT** impiegati per ingresso, rischio iniziale modellato massimo **1 USDT** incluse frizioni. Quel limite non garantisce la perdita massima reale in presenza di gap o mancata esecuzione dello stop.

### Costi già congelati, non ottimizzati qui

| Scenario | Commissione per lato | Slippage per lato | Spread intero modellato |
|---|---:|---:|---:|
| Base | 0,10% | 0,01% | 0,02% |
| Avverso | 0,15% | 0,05% | 0,10% |
| Severo | 0,20% | 0,10% | 0,20% |

Sono assunzioni di ricerca, non commissioni certificate di un conto. Nel 2026 base, il risultato ai prezzi di riferimento è circa **+10,00 USDT**; commissioni **2,11**, spread **0,21** e slippage **0,21** portano al netto **+7,46**. Non sono inclusi lavoro, hardware, eventuali abbonamenti o imposte.

### Backtest spot

Tutti gli importi sono USDT simulati. Drawdown: peggior calo della curva marcata a chiusura oraria, non tick-by-tick.

| Configurazione | Periodo | Operazioni | Netto | Profit factor | Drawdown massimo |
|---|---|---:|---:|---:|---:|
| Breakout 4h, base | 2025, già osservato | 38 | −4,15 | 0,83 | 10,11 |
| Breakout 4h, base | Gennaio–settembre 2026 | 26 | **+7,46** | **1,56** | **11,70** |
| Breakout 4h, avverso | Gennaio–settembre 2026 | 26 | +4,06 | 1,29 | 12,74 |
| Breakout 4h, severo | Gennaio–settembre 2026 | **27** | **−1,40** | 0,91 | 13,67 |
| Buy & hold, base | Gennaio–settembre 2026 | 1 | −4,78 | 0 | 44,43 |
| Nessuna operazione | Stesso periodo | 0 | 0 | N/A | 0 |

Lo scenario severo ha 27 operazioni: i costi cambiano anche dimensionamento e percorso della simulazione. Non è una semplice sottrazione di costi dagli stessi 26 trade.

Buy & hold impiega 100 USDT e lascia 900 cash, ma non applica lo stesso stop o gli stessi limiti di rischio: **non è un confronto risk-matched**. La strategia rimane investita per circa il 30,9% delle ore; non si può attribuire tutta la differenza rispetto a buy & hold alla qualità del segnale.

Per i 26 trade base: expectancy **+0,287 USDT per operazione**, win rate **34,62%**, deviazione standard dei payoff **3,32 USDT**, durata mediana **68 ore**, massima **192 ore**. Il profitto è **0,746% del capitale simulato in nove mesi**, non un rendimento annualizzato.

### Altre ipotesi già esaminate

Futures: 120 sessioni, 5 maggio–23 ottobre 2026, già osservate. I ledger diagnostici con reset giornaliero non equivalgono a un portafoglio continuo eseguibile. Valuta USD, distinta dagli USDT della tabella precedente.

| Configurazione | Operazioni | Netto USD |
|---|---:|---:|
| MNQ VWAP | 627 | −3.240,00 |
| MNQ ORB | 176 | −1.091,94 |
| MNQ Sweep/MSS | 294 | −379,42 |
| MES VWAP | 633 | −2.547,95 |
| MES ORB | 173 | −694,68 |
| MES Sweep/MSS | 241 | −828,95 |

Anche la precedente SMA168 spot perde nel suo test 2025. Timestral 28M e 209M hanno eseguito inferenza reale, ma nei filtri testati rifiutano tutti i candidati e producono zero operazioni, contro il +7,46 della baseline. **Nessun vantaggio dimostrato in quella configurazione**, non una confutazione di ogni possibile uso dei modelli.

## D. Possibilità reali di profitto

Il risultato positivo non è inventato, ma la sua robustezza non è sufficiente:

- Il miglior trade, 17–23 agosto, vale **+16,18 USDT**, più dell'intero profitto. I restanti 25 sommano **−8,71**. È una diagnostica sul ledger, non un nuovo backtest: eliminare un trade cambierebbe il percorso. Il trend following può legittimamente dipendere da pochi grandi vincitori; serve però replicazione, qui assente.
- Sono positivi soltanto **3 mesi su 9** e **1 trimestre su 3**. Il protocollo richiedeva almeno due trimestri positivi: criterio fallito.
- La bootstrap originaria, replicata esattamente, dà un intervallo di incertezza 95% dell'utile medio giornaliero di circa **[−0,063; +0,169] USDT**. Comprende perdite e non supera il criterio originario. Non è una probabilità di profitto futuro.
- Il 2025 è negativo e lo scenario severo 2026 torna negativo. La sensibilità dei parametri non è dimostrata: non abbiamo eseguito una ricerca per scegliere soglie migliori.

**Indipendenza del test:** il congelamento originale precedeva l'acquisizione degli archivi 2026. Quel test storico aveva valore come campione non ancora usato dal progetto; non lo cancelliamo retroattivamente. Oggi è però già osservato e riutilizzato, quindi non può diventare un nuovo holdout per ulteriori varianti. Non è una prova prospettica e non esclude conoscenza pubblica o selezione a livello di progetto.

**Limite esecutivo:** la chiusura 4h e l'apertura oraria usata per il fill condividono la stessa frontiera temporale. Nella realtà occorre prima ricevere la barra, poi usare una quota successiva disponibile. Lo spread è sintetico: le barre 1h non certificano bid/ask, sequenza intrabar o fill dello stop. Il modello è contabilmente coerente, ma il suo PnL non è ancora dimostrato eseguibile.

Pertanto: esiste una possibilità teorica, esiste un risultato storico favorevole in un segmento, **non esiste redditività futura dimostrata**. Non si possono usare i 26 trade per prometterla o scalare linearmente il profitto.

## E. Distanza dall'operatività

Per il paper continuo manca una milestone essenziale: **barra chiusa realmente disponibile → quota fresca → segnale 4h → decisione del Risk Engine → fill locale → protezione e recupero**, con ogni veto registrato. Il collector attuale non dimostra questa catena e non dovrebbe dipendere dalla dashboard per osservare un segnale. La modalità news rigorosa rimane bloccata.

Sono interventi circoscritti possibili, non una nuova architettura. **Non vanno però sviluppati prima di giustificare economicamente la strategia.** Non forniamo percentuali di completamento o tempi di consegna arbitrari.

Prima di denaro reale servirebbero inoltre validazione indipendente della strategia e verifiche dell'esecuzione/protezioni/riconciliazione nell'ambiente effettivamente scelto. Il simulatore locale e le vecchie prove su altri ambienti non certificano ordini reali Binance. Nessuna attivazione è proposta ora.

## F. Verdetto finale

### CAMBIARE STRATEGIA — evidenza media

L'infrastruttura ha valore riutilizzabile; la strategia corrente non offre un vantaggio convincente. **Fermare ulteriori investimenti operativi sulla configurazione attuale**, senza buttare codice o dati. Non implementare subito un'altra strategia, nuovi filtri o AI: questa valutazione non ne ha selezionata una nuova.

Non raccomandiamo CONTINUARE perché sono falliti criteri economici fissati prima del risultato. Non raccomandiamo di dichiarare impossibile l'intero progetto: le prove non giustificano una conclusione così generale. La fiducia è media sulla decisione di non finanziare questa configurazione, bassa su qualsiasi affermazione sul suo vero rendimento futuro.

Il singolo tipo di prova che manca per rivalutare **questa stessa regola** è una coorte prospettica immutabile: segnali prima dell'esito e prezzi eseguibili dopo la disponibilità del dato. Il protocollo esistente richiede almeno **90 nuovi giorni UTC e 20 roundtrip chiusi**, senza controllo economico ripetuto o estensione fino al successo. Non garantisce potenza statistica o promozione. **Non è stato avviato e non serve per rimandare la decisione di oggi.**

## G. Prossima azione concreta

**Formalizzare con il socio l'archiviazione della configurazione BTC 4h come non promossa e lo stop agli sviluppi ad essa dedicati.** Conservare la piattaforma per eventuale ricerca diversa, senza autorizzare automaticamente altro codice o spese. Non occorre un'altra campagna di diagnostica per questa decisione.

Da dire al socio:

> Abbiamo costruito e verificato componenti utili di simulazione, ma non un sistema con profitto dimostrato. Il miglior backtest resta fragile e non supera i criteri di robustezza. Fermiamo gli sviluppi della configurazione attuale e conserviamo l'infrastruttura; non mettiamo capitale reale.

## Verifiche eseguite e riproducibilità

Due filoni indipendenti: affidabilità essenziale ed economia. Riconciliati **12 ledger spot e 6 futures**, verificati 22 archivi/checksum e 16.056 barre orarie, replicata la bootstrap originaria. I due replay originali sono già identici: un terzo replay non avrebbe aggiunto informazione. Una sola fixture offline ha verificato il contratto di lettura HTTP. Nessuna nuova acquisizione o connessione ai feed, inferenza, posizione, dashboard, servizio o operazione Docker durante questo audit.

Controllo finale: journal integro e flat/spent, porta 8767 chiusa, tutti i **179 file protetti invariati**, Databento intatto. Nessuna modifica del runtime o delle strategie. Questo report classifica la configurazione come non promossa; non sposta o cancella gli artefatti congelati.

- [Analisi economica e dettagli dei costi](/Users/locoframe/Desktop/TRADING%20BOT/reports/project-verdict/economic.md)
- [Numeri economici verificati](/Users/locoframe/Desktop/TRADING%20BOT/reports/project-verdict/economic.json)
- [Analisi tecnica essenziale](/Users/locoframe/Desktop/TRADING%20BOT/reports/project-verdict/technical.md)
- [Prove tecniche, righe sorgenti e hash](/Users/locoframe/Desktop/TRADING%20BOT/reports/project-verdict/technical.json)
- [Cronologia della diagnosi e controllo dopo riavvio](/Users/locoframe/Desktop/TRADING%20BOT/reports/binance-spot/pause-ab/REPORT.md)

Ricalcolo economico offline, senza servizi o chiamate di mercato:

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
.venv/bin/python reports/project-verdict/economic-analysis.py
```

L'assenza di repository Git e del facade nativo `gentle-ai` è documentata: nessun commit o ricevuta di autorità è stato dichiarato. Gli hash e le fonti del ricalcolo sono nel freeze economico e nei JSON di prova.
