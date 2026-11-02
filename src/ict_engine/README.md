# ICT nel bot: motore v2 (completo) e A1 (archiviata)

Strategie ICT integrate nel bot per **testarle su dati storici reali** e capire se hanno un vantaggio dopo i costi. **Solo simulazione**: nessun comando di questo modulo può inviare ordini.

- **v2 (completa)** è quella da testare adesso: tutti i concetti ICT del glossario del pacchetto, su NQ ed ES e sul forex principale, con la frequenza tarata a circa **un trade al giorno**.
- **A1** è la strategia base del pacchetto. È rimasta identica: su BTC e US100 ha fatto 1 trade in circa 2 anni ed è archiviata come "non utilizzabile".

## Avvio rapido (sul Mac dove gira il bot)

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"   # cartella del bot
git fetch && git checkout ict-engine-v2
uv sync                                      # solo se manca .venv (serve numpy)
./run-ict.sh selftest                        # ~2 min, deve dire "passed" e nessun "failed"
./run-ict.sh full-test                       # NQ, ES, EUR/USD, GBP/USD, AUD/USD: download, taratura, test
```

`full-test` fa tutto da solo, per ogni mercato:

1. scarica lo storico a 5 minuti dal conto **DEMO Capital.com** del bot, in sola lettura e con le credenziali già nel Portachiavi (salta i mercati già scaricati);
2. **tara la frequenza** a 1 trade al giorno sul periodo di sviluppo, guardando solo quanti trade escono e mai i profitti;
3. lancia il test completo del protocollo. Gli holdout restano sigillati.

Alla fine scrive `reports/ict/RIEPILOGO.md`, una tabella con tutti i mercati, più un `REPORT.md` per mercato. Tempo indicativo: 30–60 minuti.

| Mercato | Su Capital.com | Mercato correlato per l'SMT |
|---|---|---|
| NQ (Nasdaq 100) | US100 | US500 |
| ES (S&P 500) | US500 | US100 |
| EUR/USD | EURUSD | GBPUSD |
| GBP/USD | GBPUSD | EURUSD |
| AUD/USD | AUDUSD | EURUSD |

Opzioni utili:
- `--markets US100,EURUSD` per testare solo alcuni mercati;
- `--target 1.5` per cambiare i trade al giorno;
- `--refresh` per riscaricare i dati;
- `--no-robustness` per un giro più veloce.

### Futures CME veri (NQ, ES, MNQ, MES)

US100 e US500 sono i CFD di Capital.com sugli stessi indici di NQ ed ES. Per i futures CME servono barre 24 ore (per esempio da Databento, a pagamento) in un CSV con colonne `symbol,contract,start,end,open,high,low,close,volume`, in UTC, con il contratto reale di ogni barra. Il roll avviene in automatico al cambio di contratto. Comandi:

```sh
./run-ict.sh calibrate --source csv --csv dati.csv --symbol MNQ --profile cme-mnq
./run-ict.sh run --source csv --csv dati.csv --symbol MNQ --profile cme-mnq --engine v2 --calibrated --robustness
```

Se il CSV contiene anche MES, viene usato in automatico per l'SMT. Il file Databento già presente nel bot (`bars120.csv`) copre solo 09:30–16:00 e non basta.

## Strategia v2: cosa fa

Ogni concetto segue la formalizzazione del glossario `docs/ict-engine-v1/13_ICT_CONCEPT_CATALOG.md`. Tutti i numeri sono convenzioni del progetto, non regole attribuite a ICT.

**Liquidità** (dove si cercano gli sweep e i target):
- swing high/low M5 e uguali (EQH/EQL);
- swing H1;
- PDH/PDL e PWH/PWL;
- massimo e minimo delle sessioni di Asia (20–24 NY), Londra (02–05) e NY mattina (07–11).

Ogni livello diventa utilizzabile solo quando il periodo che lo definisce è chiuso: il PDH al cambio di giornata delle 17:00 NY, il range di Asia a mezzanotte di NY.

**Tre modelli di ingresso:**
1. **Inversione.** Sweep di un livello di liquidità con chiusura che rientra, poi MSS con displacement entro poche barre, poi ingresso sulla zona migliore della gamba.
2. **Continuazione.** Il trend H1 è definito, il prezzo ritraccia oltre metà del dealing range (in discount per i long) senza rompere l'origine, poi MSS nella direzione del trend.
3. **Silver Bullet.** Nelle finestre 10–11 e 14–15 NY (03–04 sul forex), una candela di displacement nella direzione del bias rompe la struttura; l'ingresso è sull'FVG che lascia.

**Zone di ingresso**, in ordine di priorità: FVG (a metà, la CE), FVG invertito, breaker block, order block, OTE (0,705). Le zone già toccate dal prezzo non contano: niente fill retroattivi.

**Stop, target e gestione:**
- stop oltre l'estremo dello sweep o del pullback, più un buffer;
- target sulla liquidità opposta più vicina;
- il trade si fa solo con rapporto rischio/rendimento netto (net RR) ≥ 1,5 dopo i costi;
- costi totali (spread + slippage + fee) al massimo il 25% della distanza dello stop;
- chiusura a fine finestra: 12:00 e 16:00 NY sugli indici, 08:00 e 12:00 sul forex;
- massimo 3 trade al giorno e una posizione alla volta, rischio dello 0,25% per trade.

**Confluenze** (ognuna vale un punto; ogni trade registra quali aveva):
- allineamento al trend H1;
- bias giornaliero;
- premium/discount;
- killzone;
- liquidità esterna (non un semplice swing);
- SMT con il mercato correlato;
- ingresso dentro l'OTE;
- zone sovrapposte.

`min_confluence` è la soglia minima di punti.

### La taratura a 1 trade al giorno

`calibrate` prova una scala di 14 livelli, dal più severo al più permissivo:
- prima tutte le confluenze e il displacement del pacchetto;
- poi abbassa le confluenze e il displacement;
- poi allunga i tempi e usa la prima liquidità che dà RR sufficiente;
- poi aggiunge una killzone (Londra sugli indici, 13–15 NY sul forex);
- all'ultimo livello toglie il displacement.

Sceglie il livello che in sviluppo dà la frequenza più vicina all'obiettivo. Durante la taratura le regole di rischio basate sulle perdite sono spente e il capitale resta fisso, quindi il risultato non può influire sulla scelta. Il file `reports/ict/calibration/<mercato>.json` contiene solo conteggi di trade.

Se un mercato raggiunge 1 trade al giorno solo agli ultimi livelli, è già un'informazione: l'ICT "pieno" su quel mercato trada molto meno di così.

## Come leggere il verdetto

| Verdetto | Significato | Cosa fare |
|---|---|---|
| **REJECT (screening)** | Nel periodo di sviluppo l'aspettativa netta è ≤ 0. | Archiviare. Non aprire l'holdout. |
| **RESEARCH** | Campione troppo piccolo o criteri non soddisfatti. | Nessun paper trading. |
| **CANDIDATE** | Aspettativa positiva nello sviluppo. | Parlarne prima, poi aprire l'holdout **una volta**: `run ... --engine v2 --calibrated --unseal-holdout`. |
| **REJECT** | Perde fuori campione. | Archiviare. |
| **PAPER TRADE** | Tutti i gate del protocollo 07 sono superati. | 60 giorni di paper trading, poi shadow, come da roadmap. Mai capitale reale senza approvazione esplicita. |

Il criterio principale è l'**R medio**: risultato netto diviso per il rischio all'ingresso, dopo fee e slippage. Il win rate da solo non conta. Nel report trovi anche gli spaccati per modello, punteggio di confluenza, zona e tipo di liquidità. Servono a capire; scegliere a posteriori il pezzo migliore è overfitting.

## Regole che proteggono il risultato

- **Holdout sigillato per mercato.** Gli ultimi 12 mesi non vengono calcolati senza `--unseal-holdout`. L'apertura viene registrata in `reports/ict/holdouts.json` **per mercato**, non per nome del run. Dopo, nessun'altra configurazione e nessuna finestra sovrapposta può riaprirlo, nemmeno cambiando label o riscaricando i dati. Se il periodo di sviluppo include mesi di un holdout già aperto, il report lo segnala.
- **Ogni modifica è un nuovo trial.** Un `--set chiave=valore` cambia l'hash e viene registrato in `reports/ict/trials.json`. Holm corregge la significatività su tutti i trial dello stesso mercato, compresi A1 e quelli scartati.
- **Stress dei costi sugli stessi trade.** Fee e slippage ×1,5 e ×2, slippage ×3, applicati agli stessi trade. Misura quanto pesano i costi, senza cambiare le decisioni.
- **Limite ottimistico.** Quando stop e target cadono nella stessa barra, il motore assume lo stop. Il limite ottimistico mostra quanto pesa questa scelta; serve solo come diagnostica.
- **Benchmark casuale.** Gli stessi trade rifatti con ingresso casuale alla stessa ora, nella stessa direzione e con la stessa geometria di stop e target.
- **Robustezza.** Ogni parametro geometrico viene spostato del ±20%, uno alla volta, solo nel periodo di sviluppo.
- **Buchi nei dati.** Weekend e pausa giornaliera mantengono il contesto. Un buco imprevisto azzera lo stato e non pubblica livelli calcolati su dati incompleti. Il roll di un futures chiude le posizioni sul vecchio contratto.

## Cosa è stato verificato (`./run-ict.sh selftest`)

- **A1 identica.** Stesse decisioni del codice del pacchetto su ogni barra, e gli hash di configurazione coincidono con quelli del run di Francesco. I 33 test originali del pacchetto passano.
- **Niente look-ahead in v2.** Le decisioni prese su una parte dei dati restano identiche quando si aggiungono i mesi successivi (prefix invariance). Test dedicati verificano che PDH/PDL, range di Asia, H1 ed SMT diventano visibili solo dopo la chiusura del loro periodo.
- **Regole rispettate.** Ogni ordine generato sta in una finestra valida, con lo stop oltre l'ingresso, il target oltre l'ingresso, l'ingresso dentro la zona e il punteggio coerente.
- **Nessun falso vantaggio.** Su prezzi casuali e a costo zero v2 non guadagna. Con i costi, sui dati sintetici in formato Capital.com, la catena completa dà REJECT a circa 1 trade al giorno, come deve.
- **Taratura cieca ai profitti.** L'output contiene solo conteggi.
- **Download Capital.com.** Le correzioni di Francesco (finestra di 999 intervalli, barre anomale scartate, nuovo tentativo sugli errori di rete) sono applicate. Il download ora copre anche EURUSD, GBPUSD e AUDUSD.

## Limiti

- **Barre OHLC.** L'ordine dentro la barra non si conosce, niente fill parziali né coda: i risultati non possono qualificare il live.
- **Calendario news.** Non è incluso: senza `--calendar` il filtro news non è applicato. Sul forex pesa più che altrove (NFP, CPI, FOMC).
- **Metadati dei CFD.** Lotti, minimi e margine dei CFD vengono dai dati che Capital.com restituisce al download; i valori nei profili sono solo di riserva.
- **Ciò che non è implementato:** il collegamento al runtime live/paper del bot, che si fa solo dopo un verdetto PAPER TRADE, e il machine learning.

Nessun file esistente del bot fuori da questo modulo è stato modificato. Le aggiunte sono `src/ict_engine/`, `tests_ict/`, `docs/ict-engine-v1/` e `run-ict.sh`.
