# BTC/ETH Trend Following B — evidenze ancora insufficienti

**28 ottobre 2026. Unico verdetto: I DATI DISPONIBILI SONO ANCORA INSUFFICIENTI.**

B resta non promossa: non è dimostrato un vantaggio ripetibile rispetto al passivo a rischio comparabile, ma i dati non giustificano neppure una bocciatura definitiva della regola. **Nessuna nuova prova sul 2025/2026**, perché non soddisfano il requisito di campione intatto del progetto. Preparato un protocollo prospettico immutabile; **non avviato**, nessuna integrazione operativa, nessun ordine o modifica di parametri.

## 1. Verifica preliminare: il 2025/2026 non è un nuovo holdout indipendente

La distinzione è essenziale:

- **Esclusione formale dai calcoli B: verificata.** Sviluppo 2020–2022, validazione 2023, test gennaio–novembre 2024; il protocollo B esclude esplicitamente dicembre 2024–settembre 2026.
- **Esclusione dall'intero processo progettuale: non verificabile come indipendenza.** Il 2025 e gennaio–settembre 2026 erano già stati acquisiti e analizzati con SMA168, breakout 4h e Timestral prima di decidere il cambio di strategia e congelare B. Quell'evidenza ha contribuito al percorso di selezione del progetto.
- **Non è dimostrato che i parametri di B siano stati ottimizzati sul 2025.** Non confondiamo contaminazione del percorso progettuale con una prova inesistente di fitting diretto di B su quel periodo.

| Ricevuta originale | Data registrata |
|---|---|
| Acquisizione SMA del 2025 completata | 2026-10-27 06:57:16 UTC |
| Acquisizione breakout con 2025 e gennaio–settembre 2026 completata | 2026-10-27 08:14:42 UTC |
| Freeze Timestral, storico esplicitamente già osservato | 2026-10-27 09:05:25 UTC |
| Freeze finale B | 2026-10-28 13:18:08 UTC |

Sono ricevute interne e hash immutati, non una notarizzazione temporale esterna; non ci basiamo sui soli mtime. Le prove sono gli [archivi di acquisizione precedenti](/Users/locoframe/Desktop/TRADING%20BOT/reports/binance-spot/breakout-4h/acquisition.json), i [risultati Timestral già osservati](/Users/locoframe/Desktop/TRADING%20BOT/reports/binance-spot/timestral-abc/run-1/results.json) e il [protocollo B congelato](/Users/locoframe/Desktop/TRADING%20BOT/research/strategy-discovery-2026/protocol.json). Hash e ulteriori fonti nel [riepilogo verificabile](/Users/locoframe/Desktop/TRADING%20BOT/research/btceth-b-followup/summary.json).

Conclusione: non ricicliamo **interi 2025 e 2026** come nuovi test indipendenti. La prova documentata copre il 2025 e gennaio–settembre 2026; non stiamo dichiarando contaminato ogni giorno successivo del 2026, né selezionando una piccola coda temporale per ottenere un esito favorevole. Nessun nuovo download o backtest di questi periodi è stato eseguito.

## 2. B è rimasta identica

BTCUSDT/ETHUSDT spot, long/cash, niente leva. Ribilanciamento lunedì 00:00 UTC con sole barre chiuse entro domenica 00:00 UTC: **un giorno intero di disponibilità**. Per asset: `0,5 × I(momentum90giorni > 0) × min(1; 20% / volatilità30giorni)`. Volatilità su rendimenti log giornalieri, ddof=1 e √365; eleggibilità originaria su storia completa e quote-volume. Unico vicino già dichiarato: 60 giorni, senza sostituire il primario 90 giorni in base ai risultati.

1.000 USDT virtuali all'inizio di ciascun segmento separato; nessuna concatenazione fra segmenti. Costi per lato fee/slippage e spread intero: **base 10/1/2 bp**, avverso **15/5/10**, severo **20/10/20**. Inclusi acquisti, vendite, ribilanciamenti e liquidazione finale. NAV giornaliera al valore di liquidazione, stesse convenzioni per i comparatori. Non sono tariffe certificate di un conto o fill realmente eseguiti.

Il nuovo codice analizza **soltanto ledger già prodotti** e ricostruisce le 52 decisioni del 2023 dai dati originali. Nessuna nuova variante, strategia, benchmark, ottimizzazione o replica economica del 2025/2026.

## 3. Rendimento, rischio, esposizione e turnover già misurati

Risultati base sul capitale iniziale, non rendimenti annuali promessi. DD su chiusure giornaliere, non intraday; Sharpe annualizzato √365. Esposizione media/massima realmente osservata rispetto alla NAV, non limite teorico.

| Campione | Netto | Max DD | Sharpe | Esposizione media | Massima | Turnover totale, due lati |
|---|---:|---:|---:|---:|---:|---:|
| 2020–2022, sviluppo | 66,13% | 20,05% | 1,08 | 16,31% | 65,09% | 7,54× |
| 2023, validazione | 3,22% | 18,42% | 0,27 | 32,73% | 97,92% | 7,66× |
| Gen–nov 2024, test storico già osservato | 42,54% | 8,71% | 2,34 | 25,79% | 61,52% | 4,76× |

**Attenzione al rischio:** il target di volatilità 20% non limita l'esposizione al 20%, né il drawdown o la perdita giornaliera. Nel 2023 la posizione ha potuto avvicinarsi al 100% del portafoglio. Questi risultati non ereditano lo stop da 1 USDT o il limite d'ingresso 100 USDT del vecchio test tecnico.

| Campione | Volatilità giornaliera annualizzata | Peggior giorno | Quantile 5% giornaliero | Quantile 95% | Mesi positivi | Peggior mese |
|---|---:|---:|---:|---:|---:|---|
| 2020–2022, sviluppo | 17,03% | -11,92% | -1,23% | 1,45% | 13/36 | 2020-03 -11,93% |
| 2023, validazione | 17,94% | -7,00% | -1,41% | 1,32% | 6/12 | 2023-08 -9,69% |
| Gen–nov 2024, test storico già osservato | 17,16% | -3,13% | -1,14% | 1,79% | 6/11 | 2024-04 -4,90% |

Mediana giornaliera **zero** in tutti i segmenti, anche per i periodi interamente cash. Media aritmetica giornaliera: sviluppo +0,0503%, 2023 +0,0131%, 2024 +0,1099%; non è una previsione. Questi quantili descrivono un campione dipendente, **non VaR futuro garantito**. Nessun rendimento è stato stimato da un nuovo campione indipendente in questa missione.

### Costi avversi: regola non cambiata

| Campione | Base | Avverso | Severo |
|---|---:|---:|---:|
| 2020–2022, sviluppo | 66,13% | 64,52% | 62,67% |
| 2023, validazione | 3,22% | 2,19% | 1,02% |
| Gen–nov 2024, test storico già osservato | 42,54% | 41,67% | 40,66% |

La positività sopravvive ai tre modelli di costo. Non basta a dimostrare il vantaggio rispetto all'investimento passivo. Nel 2023 il PF dei P&L giornalieri è 1,032; nel 2024 1,487: **non sono PF per roundtrip**. Gli ordini di allocazione sono rispettivamente 85 e 72, non altrettanti trade indipendenti.

## 4. Confronto corretto con i passivi

Il comparatore principale è BTC/ETH con **stesse sleeve, volatilità target, cadenza, ritardo e costi, ma senza filtro momentum**. Buy & hold individuali sono riferimenti descrittivi a esposizione diversa. L'EW 50/50 settimanale viene chiamato correttamente ribilanciato: **non è buy & hold statico BTC/ETH**, che non era un braccio dell'esperimento originale e non viene inventato ora.

| Periodo | Configurazione | Netto | Max DD | Sharpe | Esposizione media |
|---|---|---:|---:|---:|---:|
| 2023 | B90 | 3,22% | 18,42% | 0,27 | 32,73% |
| 2023 | BTC/ETH passivo, stesso vol-cap | 45,11% | 16,05% | 1,81 | 50,19% |
| 2023 | BTC/ETH EW settimanale, senza cap | 120,73% | 21,91% | 2,04 | 99,73% |
| 2023 | BTC buy & hold | 155,00% | 20,00% | 2,34 | 100,00% |
| 2023 | ETH buy & hold | 90,31% | 27,33% | 1,61 | 100,00% |
| 2023 | Cash | 0,00% | 0,00% | N/D | 0,00% |
| 2024 gen–nov | B90 | 42,54% | 8,71% | 2,34 | 25,79% |
| 2024 gen–nov | BTC/ETH passivo, stesso vol-cap | 44,55% | 13,66% | 1,91 | 39,02% |
| 2024 gen–nov | BTC/ETH EW settimanale, senza cap | 96,20% | 35,45% | 1,58 | 100,00% |
| 2024 gen–nov | BTC buy & hold | 127,46% | 26,15% | 1,93 | 100,00% |
| 2024 gen–nov | ETH buy & hold | 61,92% | 45,26% | 1,13 | 100,00% |
| 2024 gen–nov | Cash | 0,00% | 0,00% | N/D | 0,00% |

Nel 2024 B sacrifica un poco di rendimento rispetto al passivo risk-capped (+42,54% contro +44,55%) e presenta minore DD e migliore Sharpe, ma anche esposizione media molto inferiore (25,79% contro 39,02%). Il benchmark diagnostico che eredita i suoi target d'esposizione rende +42,44%: non prova alpha, perché eredita proprio il timing che vorremmo valutare. Nel 2023 il vantaggio corretto per rischio non si ripete.

## 5. Perché il 2023 è debole

### Partecipazione tardiva alle ripartenze, esposizione durante i ribassi

Le date sono ricostruite da prezzi e volumi già disponibili al cutoff, non da segnali ricostruiti usando il futuro.

- **Gennaio:** il 2 e il 9 entrambe le sleeve sono cash per momentum a 90 giorni negativo; primo target positivo il **16 gennaio**. B guadagna **39,45 USDT**, il passivo risk-capped **199,89**: perde parte della ripartenza iniziale.
- **Secondo/terzo trimestre:** B perde **38,28 e 125,31 USDT**, compensando gran parte dei +107,18 del primo trimestre e +88,64 del quarto.
- **Agosto:** il 14 agosto i target sono BTC **47,84%** ed ETH **50%**, totali **97,84%**, prima del calo. Il **17 agosto** il ledger perde **7,004% / 71,81 USDT in un giorno**; il 21 i target diventano entrambi zero. Agosto chiude −101,60 USDT: BTC −52,22, ETH −49,38. Il segnale lento può uscire dopo il danno, e la volatilità passata bassa può consentire molta esposizione prima del salto.
- **Ottobre:** entrambe le sleeve sono cash nelle decisioni del 2/9/16/23; BTC torna positivo il 30 ottobre, ETH il 6 novembre. Ottobre B appena **+0,19 USDT**, passivo **+139,51**: un'altra ripartenza catturata tardi.

| Mese 2023 | P&L B, USDT | P&L passivo risk-capped, USDT |
|---|---:|---:|
| 2023-01 | 39,45 | 199,89 |
| 2023-02 | -3,39 | 3,47 |
| 2023-03 | 71,12 | 82,60 |
| 2023-04 | 10,55 | 12,26 |
| 2023-05 | -16,17 | -18,78 |
| 2023-06 | -32,66 | 38,42 |
| 2023-07 | -20,19 | -30,03 |
| 2023-08 | -101,60 | -134,62 |
| 2023-09 | -3,52 | 18,70 |
| 2023-10 | 0,19 | 139,51 |
| 2023-11 | 41,42 | 73,52 |
| 2023-12 | 47,03 | 66,11 |

I divari mensili includono anche capitali accumulati differenti: a marzo i rendimenti percentuali dei due percorsi coincidono, ma il passivo parte da una base più alta. **È attribuzione contabile del percorso, non stima causale isolata del filtro**, né prova che un lookback più breve sarebbe migliore. Nessun parametro è stato modificato.

### Non è principalmente un problema di commissioni

B chiude a **+32,22 USDT**, contro **+451,05** del passivo, divario **418,83**. A parità dei rispettivi percorsi congelati:

- Divario dei P&L marcati ai prezzi grezzi: **416,27 USDT**.
- Maggiori frizioni B — **commissioni + spread + slippage**: **2,56 USDT**, soltanto **0,61%** del divario netto. Le sole maggiori commissioni sono 2,136 USDT.
- Costi totali B: **9,40 USDT**; P&L grezzo contabile **41,63**, netto **32,22**. Non è un nuovo backtest senza costi, ma una decomposizione esatta degli stessi fill/quantità.

Quindi ridurre le fee non risolverebbe il principale problema osservato. Il contributo netto annuale è BTC **+25,95**, ETH **+6,28 USDT**: non giustifica eliminare retrospettivamente uno dei due asset.

La cassa media è 67,27%, con 92 giorni completamente cash; questo **non impedisce picchi di esposizione quasi totale**. Il drawdown 18,42% va dalla NAV del 17 aprile 00:00 UTC al minimo del 19 agosto 00:00 UTC e non recupera entro fine anno. La giornata migliore vale circa 127% dell'utile: togliendola contabilmente restano −8,75 USDT; togliendo le cinque migliori −142,83. Diagnostiche a percorso fisso, non nuovi backtest né giorni da rimuovere dalla strategia.

## 6. Solidità statistica: il problema non è risolto

È conservata la bootstrap originale sul test storico 2024, **non ripetuta per cercare un esito migliore**. Differenza Sharpe B − passivo risk-capped:

| Blocchi giornalieri | Intervallo bilaterale 95% | Limite inferiore unilaterale corretto α=0,05/3 |
|---|---|---:|
| 7 | [−0,731; +1,661] | −0,828 |
| 30 | [−0,473; +1,428] | −0,533 |

Entrambi includono assenza di vantaggio; entrambi i gate originali falliscono. Concentrarsi ora soltanto su B **non autorizza a cambiare α da 0,05/3 a 0,05**. Niente DSR globale inventato: il numero completo dei precedenti tentativi del progetto rimane ignoto. Il 2023 analizzato oggi è già noto, quindi questa diagnosi non aggiunge una nuova prova indipendente.

## 7. Protocollo di osservazione prospettica congelato

[Protocollo machine-readable](/Users/locoframe/Desktop/TRADING%20BOT/research/btceth-b-followup/prospective-protocol.json) — SHA256 `45c1d0a40f931ffae157e3ca1e5f33ecbcd8cc0f337268e27b0d1a223d535840`.

**Stato: PREPARED_NOT_RUNNING.** Nessun collector, servizio, operazione o automazione avviata.

- Finestra fissa già proposta: **[1 novembre 2026, 1 novembre 2027) UTC**, 365 giorni, primo ribilanciamento **2 novembre 2026 00:00 UTC**, capitale virtuale iniziale 1.000 USDT e warmup precedente completo. Non si estende fino a un risultato favorevole.
- Stesse B90 e sensibilità60, universo BTC/ETH, costi, vol-cap, comparatori e criteri. Nessuna modifica per correggere il 2023.
- Prima dell'esito: registrazione append-only di ogni decisione, anche target zero e veto; cutoff, barre chiuse effettivamente ricevute, orari di sorgente e ricezione separati, hash del payload/configurazione, target e stato portafoglio. Decisione registrata **prima dell'esecuzione programmata**, senza retrodatazione. Gli hash da soli non garantiscono l'orario reale.
- Il modello economico principale resta apertura candela + spread sintetico/slippage/fee originari, con fill dichiarati **ipotetici**. Eventuali bid/ask osservati in futuro rimangono una diagnostica separata: mai riaddebitare spread sintetico su prezzi già bid/ask, né cambiare il modello principale dopo i risultati.
- Gap, osservazioni mancate/tardive, dato aperto o indisponibile: fail-closed e tracciatura, niente prezzo eseguibile inventato o backfill di decisioni. Un archivio letto dopo l'anno può supportare un replay storico su dati nuovi, **non certifica decisioni o paper execution osservate in tempo reale**.
- Unica valutazione economica alla fine: niente controlli intermedi del P&L, scelta dei mesi, nuova configurazione o estensione. Controlli non economici d'integrità ammessi. Il 2024 rimane un gate fallito storico: la nuova prova non lo riscrive.
- Criteri mantenuti: primario netto positivo base/avverso e non negativo severo, vicino positivo base/avverso senza salvare il primario, DD non peggiore e Sharpe migliore del passivo risk-capped, limiti bootstrap corretti positivi con entrambi i blocchi. Dati insufficienti/statistiche non definite: nessuna promozione. Dodici mesi non garantiscono potenza sufficiente.

**Il protocollo è pronto, l'osservazione no.** Senza una catena effettivamente attiva prima degli esiti non dichiareremo eseguito un forward test. Nessuna approvazione economica o operativa deriva automaticamente da un futuro esito positivo.

## 8. Verifiche, riproduzione e raccomandazione

**6 nuovi test sintetici PASS**, verifica indipendente di riconciliazione delle 72 righe, attribuzione BTC/ETH, compounding mensile/trimestrale e 52 target datati. Verificati **345 input congelati, 3 sorgenti analitiche e 179 file protetti invariati**. Nessun ordine, download, account, parametro o file runtime modificato; nessuna nuova strategia/variante/benchmark. La raccolta operativa Binance non è stata riattivata da questo lavoro. [Review mirata](/Users/locoframe/Desktop/TRADING%20BOT/reports/btceth-b-followup-review.json).

Ricalcolo soltanto diagnostico, senza rete o nuovi backtest:

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
.venv/bin/python research/btceth-b-followup/analyze.py
.venv/bin/python -m pytest -q research/btceth-b-followup/test_analysis.py
```

Il primo comando verifica gli hash e rigenera soltanto quattro output analitici nuovi nella directory di follow-up, deterministicamente; non riscrive dati/configurazioni o risultati originari. **Non rieseguire `freeze`.** [Dati analitici completi](/Users/locoframe/Desktop/TRADING%20BOT/research/btceth-b-followup/findings.json) · [Target e diagnosi 2023](/Users/locoframe/Desktop/TRADING%20BOT/research/btceth-b-followup/diagnosis-2023.json).

**Raccomandazione tecnica:** conservare B e il protocollo, senza integrazione nel bot o aggiustamenti ad hoc. Se si prosegue, soltanto osservazione nuova separata, con decisioni registrate prima degli esiti e una sola valutazione finale.

**Raccomandazione economica:** non impegnare capitale e non finanziare sviluppo operativo sulla base del +42,54% del 2024. Il 2023 rivela ritardo alle inversioni e rischio concentrato; il 2024 rimane incoraggiante ma statisticamente inconcludente rispetto al passivo. Un'ulteriore ottimizzazione retrospettiva non colmerebbe questa lacuna.

> **I DATI DISPONIBILI SONO ANCORA INSUFFICIENTI.** Abbiamo spiegato il problema, non dimostrato un profitto futuro. Non scartiamo B solo per un anno debole, ma non la promuoviamo al paper trading operativo con queste prove.
