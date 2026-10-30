# ICT Engine A1 nel bot

Strategia ICT del pacchetto `docs/ict-engine-v1/` integrata nel bot per **testarla su dati storici reali** e capire se ha un vantaggio dopo i costi. **Solo simulazione**: nessun comando di questo modulo può inviare ordini.

Regole della strategia (A1, invariate rispetto al pacchetto):

1. Lo **sweep** prende un minimo o massimo di swing confermato e la chiusura rientra nella stessa barra.
2. Entro 6 barre arriva un **MSS con displacement**: chiusura oltre l'ultimo swing opposto, con corpo ≥ 1 ATR.
3. Sulla barra successiva compare un **FVG** a tre barre; l'ordine limite va a metà del FVG.
4. Lo stop sta oltre lo sweep; il target è la liquidità opposta più vicina.
5. Il trade si fa solo se il rapporto rischio/rendimento netto (net RR) è ≥ 1,5 dopo i costi.

Timeframe M5, ingressi tra le 07:00 e le 11:00 di New York, rischio dello 0,25% per trade.

## Avvio rapido (sul Mac dove gira il bot)

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"   # cartella del bot
uv sync                                      # solo se manca .venv (serve numpy)
./run-ict.sh selftest                        # 36 test, ~2 min: parità con il codice del pacchetto inclusa
./run-ict.sh quickstart                      # scarica 36 mesi BTCUSDT 5m ufficiali e lancia il test completo
```

Il report è in `reports/ict/<nome-run>/REPORT.md`. I numeri completi sono in `results.json` e i trade dello sviluppo in `trades-dev.csv`.

## Le tre fonti dati

| Fonte | Comando download | Comando test | Note |
|---|---|---|---|
| Binance spot (mercato primario del pacchetto) | `./run-ict.sh download-binance --months 36` | `./run-ict.sh run --source binance --robustness` | Archivi ufficiali `data.binance.vision`, ogni file verificato con SHA256. Nessun account. Lo spread non è nei dati: viene assunto (1 tick). |
| Capital.com DEMO (US100, US500, BTCUSD) | `./run-ict.sh download-capital --epic US100 --months 36` | `./run-ict.sh run --source capital --epic US100 --robustness` | Usa le credenziali DEMO già nel Portachiavi del bot, **in sola lettura**. Barre bid/ask native, quindi lo spread è quello vero. È anche il mercato più vicino al tuo NQ. |
| CSV del bot (MNQ/MES Databento) | già presente: `reports/quant-validation/bars120.csv` | `./run-ict.sh run --source csv --csv reports/quant-validation/bars120.csv --symbol MNQ` | Quel file copre solo 09:30–16:00 NY. A1 lavora 07:00–11:00 e dopo ogni buco riparte da zero con 15 barre di riscaldamento, quindi qui quasi non trada. Serve uno storico 24h. |

Lo storico Capital.com: il bot standard legge solo le ultime 500 barre. Per scaricare anni di dati questo modulo aggiunge un'unica richiesta di lettura `GET /prices` con `from`/`to`, senza modificare il client del bot. I parametri esatti di quella rotta non li ho potuti provare dal mio ambiente. Se Capital.com rifiuta la richiesta, il download si ferma con il codice di errore e non scrive nulla.

## Come leggere il verdetto

| Verdetto | Significato | Cosa fare |
|---|---|---|
| **REJECT (screening)** | Nel periodo di sviluppo l'aspettativa netta è ≤ 0. | Archiviare. Non aprire l'holdout. |
| **RESEARCH** | Campione troppo piccolo o criteri non soddisfatti. | Nessun paper trading. |
| **CANDIDATE** | Aspettativa positiva nello sviluppo. | Aprire l'holdout **una volta**: `run ... --unseal-holdout`. |
| **REJECT** | Perde fuori campione. | Archiviare. |
| **PAPER TRADE** | Tutti i gate del protocollo 07 sono superati. | 60 giorni di paper trading, poi shadow, come da roadmap. Mai capitale reale senza approvazione esplicita. |

Il criterio principale è l'**R medio**: risultato netto diviso per il rischio all'ingresso, dopo fee e slippage. Il win rate da solo non conta.

## Regole che proteggono il risultato

- **Holdout sigillato.** Gli ultimi 12 mesi non vengono nemmeno calcolati senza `--unseal-holdout`. Alla prima apertura si scrive una ricevuta; un'altra configurazione non può riusarlo, serve un nuovo periodo futuro.
- **Ogni modifica è un nuovo trial.** Un `--set chiave=valore`, per esempio `--set entry_fraction=0.6`, cambia l'hash e viene registrato in `reports/ict/trials.json`. Holm corregge la significatività per tutti i trial provati, compresi quelli scartati.
- **Stress dei costi.** Ogni run ripete il test con fee e slippage ×1,5 e ×2 e con slippage ×3.
- **Limite ottimistico.** Quando stop e target cadono nella stessa barra, il motore assume lo stop. Il limite ottimistico mostra quanto pesa questa scelta; serve solo come diagnostica.
- **Benchmark casuale.** Gli stessi trade vengono rifatti con ingresso casuale alla stessa ora, nella stessa direzione e con la stessa geometria di stop e target. Se A1 non batte questo benchmark, la selezione dei setup non aggiunge nulla.
- **Robustezza** (`--robustness`). Ogni parametro geometrico viene spostato del ±20%, uno alla volta, solo nel periodo di sviluppo.

## Cosa è stato verificato

- **Parità con il codice del pacchetto.** Il motore prende la stessa decisione del riferimento (`reference/ict_strategy.py`) su ogni barra di 14 serie sintetiche, ordini compresi (entry, stop, target, quantità).
- **Controllo anti look-ahead.** Su random walk a costo zero con barre costruite da un percorso continuo la strategia non guadagna: R medio −0,07 su 500 trade. In sviluppo è emerso che barre sintetiche con "baffi" casuali danno un falso vantaggio agli ordini limite; il test usa quindi percorsi veri.
- **Test del pacchetto.** I 33 test originali del pacchetto passano ancora.
- **Bug trovato e corretto.** Il taglio di segmento al cambio di contratto futures veniva calcolato sulle barre da 1 minuto invece che su quelle aggregate.

## Differenze rispetto al codice di riferimento

| Punto | Riferimento | Qui | Perché |
|---|---|---|---|
| Pivot | ricalcolati su tutta la storia a ogni barra | tracciati in modo incrementale | Il calcolo del riferimento diventa ingestibile su 3 anni di M5. Il test di parità prova che le decisioni sono identiche. |
| Arrotondamento al tick | `floor(x/tick)` | tolleranza di 1e-9 tick | Evita che un prezzo già sul tick slitti di un tick per l'errore binario (100,6/0,01 = 10059,999…). |
| Uscite a fine sessione, cancel per sessione, target consumato o buco nei dati | descritte nella spec, non implementate | implementate | Sono normative nella spec 01/05/06. |
| Ledger di rischio | a carico dell'host | `risk.py` | Rendimento giornaliero e settimanale, serie di perdite, drawdown. Nel ledger di ricerca il drawdown viene registrato senza fermare il test; la vista conto applica l'arresto all'8%. |
| Slippage BTC | prezzo fisso 0,01 | 0,2 bp del prezzo | Con 1 bp il filtro del pacchetto (slippage ≤ 0,05 ATR) scarterebbe quasi tutte le barre tranquille. |
| Margine | solo contanti | CFD (`margin_rate`) e futures (`margin_per_contract`) | Senza margine, con il contante pieno non si può dimensionare MNQ né un CFD. |

## Non implementato (di proposito)

- **Collegamento al runtime live/paper del bot.** È lo stadio 4 della roadmap e si fa solo dopo un verdetto PAPER TRADE.
- **Varianti e filtri aggiuntivi.** B1, C1, D1, i filtri HTF, premium/discount e daily bias, e il machine learning.
- **Esecuzione realistica.** Fill parziali e replay tick per tick.
- **Calendario news point-in-time.** Si può passare un CSV con `--calendar`, ma il calendario non viene scaricato.

Nessun file esistente del bot è stato modificato. Le aggiunte sono:

- `src/ict_engine/`
- `tests_ict/`
- `docs/ict-engine-v1/`
- `run-ict.sh`
