# Audit indipendente del progetto Trading Bot — Opus

**29 ottobre 2026. Revisore: Claude Opus (Chief Quant Researcher, revisione indipendente).**
Ambito: tutto il lavoro economico precedente (BTC 4h, SMA168, futures MNQ/MES, Timestral, Strategy Discovery A/B/C, Edge Discovery H1/H2/H3, follow-up B). Metodo: rilettura del codice, riesecuzione del codice originale in sola lettura su copie temporanee, re-implementazioni indipendenti, sonde anti look-ahead, ricalcolo delle statistiche. Report gemello: [OPUS-EDGE-RESEARCH.md](OPUS-EDGE-RESEARCH.md).

## 0. Sintesi

1. **I numeri riportati sono calcolati correttamente.** Riprodotti byte per byte: 12 `metrics.json` del breakout 4h, 3 split SMA168, 153/153 JSON A/B di Strategy Discovery 2026, 135/135 JSON di Edge Discovery Round 2, tutti i blocchi bootstrap; 243 numeri di testata nei quattro report coincidono con i ledger. I 6 ledger futures si riconciliano al centesimo su 2.144 trade. Nessun look-ahead trovato con sonde di perturbazione e troncamento. Unità dei timestamp (ms → µs dal 2025) gestite correttamente da tutti i loader che toccano dati 2025+.
2. **Errori dimostrati che cambiano una conclusione: quattro.**
   - I due test economici di Timestral erano **strutturalmente degeneri**: non potevano approvare i candidati qualunque fosse il modello. "Timestral provato e inutile come filtro" non è supportato; l'unica evidenza valida è che le previsioni non battono il "prezzo invariato".
   - La famiglia C non è mai stata calcolata per un **difetto a cascata del loader**; sui dati 2024 puliti è fortemente perdente (−80,8%). Non è una "domanda aperta".
   - Rendimenti e Sharpe sono confrontati con **cassa allo 0%** invece che con il tasso privo di rischio: nel 2023 B (+3,22%) rende meno del T-bill (+5,27%).
   - I gate statistici di B e il test prospettico proposto hanno **potenza dell'8–14%**: per confermare la differenza di Sharpe osservata servirebbero decenni di dati.
3. **Nessun errore trasforma una strategia scartata in una promettente.** Cambiano lo status di C (da "non misurata" a "antieconomica"), di Timestral (da "testato e respinto" a "non testato economicamente, senza capacità previsiva"), di MNQ Sweep/MSS (da "negativa" a "inconclusiva") e l'enfasi su B (più debole di quanto i report suggeriscano).
4. **Il processo era rigoroso; il disegno sperimentale molto meno.** Congelamenti, ricevute, costi e benchmark erano curati. Il limite strutturale è stato cercare segnali di prezzo su mercati molto efficienti, con campioni brevi e test senza potenza: quasi ogni esito era destinato a "inconcludente".

## 1. Stato reale del progetto (verificato oggi)

| Elemento | Stato verificato |
|---|---|
| Repository Git | **Assente**: nessuna `.git` nella workspace né sopra; nessun remote, branch o commit. Tutta la tracciabilità è affidata a hash e ricevute JSON. |
| Codice | ~8.500 righe Python: `src/mnq_local` (runtime Binance spot, journal SQLite, risk engine, dashboard, adattatori Capital.com/tasty/Databento), `src/mnq_sim` (backtester futures), `src/mnq_timestral` (adattatore e valutazione modelli), `src/mnq_paper`; `adapters/databento*`; tre campagne in `research/`. |
| Dati | 49 MB archivi Binance spot (BTC/ETH e coorte di 7 asset, con checksum), 905 MB pesi Timestral 28M/209M, 2,5 MB Databento MNQ/MES 1 minuto (120 sessioni). |
| Servizi | **Nessun processo del bot attivo**; porta 8767 chiusa; `recorder.pid` punta a un PID non più esistente. Il protocollo prospettico di B è `PREPARED_NOT_RUNNING`. |
| Strategie | Nessuna promossa. Nessuna integrazione operativa, nessun ordine reale. |
| File protetti | 179/179 hash invariati all'inizio e alla fine di questo audit. |
| Aggiunte di questa revisione | Solo file nuovi: `reports/OPUS-*.md`, `research/opus-edge-2026-10-29/` (codice, protocolli, cache dati, risultati, copie degli script di audit) e l'indice `.codegraph/` alla radice (richiesto dalle istruzioni globali dell'utente). Nessun file esistente modificato. |

**Provenienza dati.** Gli archivi Binance spot sono in millisecondi fino al 2024-12 e in **microsecondi dal 2025-01** (open time a 16 cifre); i perpetual USDⓈ-M restano in millisecondi. Verificato due volte: sulla cache del progetto e su 486 archivi riscaricati per questa revisione. I loader del breakout, di SMA168, di Timestral e di `economic-analysis.py` convertono per anno e verificano che l'anno decodificato coincida: un'unità sbagliata farebbe fallire il caricamento, non lo corromperebbe. Strategy Discovery ed Edge Round 2 gestiscono entrambe le unità ma non caricano mai dati 2025+. Lo spot 2020–2023 contiene 31 ore mancanti e 16 barre di durata irregolare (manutenzioni Binance): i loader precedenti le trattano in modo prudente.

## 2. Come è stato condotto l'audit

- **Due audit indipendenti in parallelo** (spot; futures + Timestral) con istruzioni di "rompere" i report, più verifiche dirette mie su ogni errore dichiarato prima di citarlo.
- Codice originale eseguito in sola lettura con journal e output reindirizzati in cartelle temporanee; snapshot dell'albero prima/dopo: 0 file modificati o rimossi.
- Sonde: dati futuri sostituiti con valori spazzatura (0 differenze su 1.072 valutazioni A/B e 538 H1/H2); troncamento del backtest breakout a tre date (segnali e trade identici prima del taglio); ritardo di esecuzione di 1–2 ore; re-implementazione indipendente di VWAP-z e ORB futures (stessi 627/633/176/173 trade).
- Script, output e report degli audit sono conservati in `research/opus-edge-2026-10-29/audit/` (`spot/`, `futures-timestral/`, `opus/`).

## 3. Errori dimostrati

| # | Dove | Errore | Evidenza | Impatto sulla conclusione |
|---|---|---|---|---|
| E-1 | Timestral filtro su breakout BTC 4h | Il gate confronta la mediana di una previsione con origine **4 ore prima** della candela di breakout con la chiusura della candela stessa: `median_step2(T−4h) > close_T × 1,0024`. Ma un breakout richiede `close_T >` massimo dei 20 massimi precedenti, quindi sopra il prezzo all'origine. Un previsore "prezzo invariato" avrebbe respinto il 100%. | `reports/binance-spot/timestral-abc/runner.py:25-31,61`; `reports/binance-spot/breakout-4h/runner.py:39-42`. 79/79 candidati primari e 113/113 secondari hanno `close_T > P[origine]`. Il modello avrebbe dovuto prevedere ≥ +0,41% (≈ +1,3% per il breakout mediano); il p99 della mediana prevista 28M è +0,46%. Un oracolo con il prezzo vero accetterebbe 25/79. | **Sì.** "0 trade contro +7,46" non dice nulla su Timestral (`PROJECT-VERDICT.md:87`). |
| E-2 | Timestral 28M su MNQ/MES | Previsione con origine al minuto t−1 confrontata con la chiusura del minuto t: il filtro misura il segno della candela di trigger, non il modello. | `src/mnq_local/timestral_experiment.py:112-115`, `src/mnq_timestral/strategy.py:65-67`. Su 316 decisioni ricalcolate esattamente, un previsore "prezzo invariato" decide come il modello in 305 (96,5%). ORB e Sweep (trigger nella direzione del segnale, 35/35) respinti; VWAP (trigger contrario, 122/123) accettato. | **Sì** per i rami filtrati: non informativi sul modello. |
| E-3 | Strategy Discovery, famiglia C | Il loader orario confronta ogni mese con l'ultima barra **accettata**: dopo il primo mese scartato (2020-02) ogni mese successivo fallisce come "gap", compresi gli 11 mesi 2024 perfettamente puliti (8.040/8.040 ore). Il protocollo invalida solo il periodo colpito. | `research/strategy-discovery-2026/data.py:100-102`; `runner.py:92-94,129-130`; `protocol.json` (`execution_accounting.missing`); `quality-holdout.json`: 58/60 mesi orari scartati per asset. | **Sì** per lo status: C eseguita con il motore congelato su dati tolleranti ai gap (esplorativo, dati già visti) perde **−80,8%** nel 2024 base (847 roundtrip, PF 0,46), −97,9% avverso, −99,8% severo, −77,7% nel 2023. Il rendimento lordo medio dopo il segnale è −0,3/+5,1/+4,8 bp contro ~24 bp di costo per roundtrip. Non promozione invariata; "domanda aperta" è sbagliato. |
| E-4 | Tutti i confronti di rischio/rendimento | Sharpe e rendimenti calcolati contro **cassa USDT allo 0%**, non contro il tasso privo di rischio. Per strategie con molta cassa il confronto economico corretto è il T-bill. | Ricalcolo sui ledger congelati con FRED DTB3 (`research/opus-edge-2026-10-29/audit/opus/rf_adjust.json`): 2023 B **+3,22% contro T-bill +5,27%**, Sharpe in eccesso **−0,02** (riportato 0,27); 2024 B Sharpe in eccesso 2,04 contro 1,68 del passivo risk-capped: differenza 0,36 invece di 0,43. | Rafforza la non promozione di B: nell'anno di validazione non ha battuto il denaro in T-bill. |
| E-5 | Potenza statistica di B | I gate bootstrap di B richiedono una differenza di Sharpe stimata ≥1,30 (blocchi 7 gg) o ≥1,03 (30 gg); con l'effetto osservato (+0,43) la potenza è **8–11%**. Il test prospettico di 12 mesi ha potenza analoga. | `research/strategy-discovery-2026/engine.py:100-114`, `assess.py:24`; ricalcolo dell'audit spot (F8) e calcolo indipendente in `research/opus-edge-2026-10-29/results/power.json`: per confermare una differenza di Sharpe di 0,36 con correlazione 0,8–0,9 servono **38–72 anni** di dati giornalieri (approssimazione iid, ottimistica). | Il fallimento dei gate è un'evidenza debole in entrambe le direzioni; il forward di 12 mesi non può decidere nulla. |

Un difetto documentale minore: `reports/timestral-28m-experiment/RESULTS.md` e `reports/timestral-28m-verification/verification.json` dichiarano ancora che non è stata eseguita inferenza, mentre `results.json` contiene 7.400 previsioni reali; il riepilogo corretto è `reports/timestral-real/RESULTS.md`.

## 4. Problemi probabili e preoccupazioni teoriche

| Tema | Evidenza | Valutazione |
|---|---|---|
| Futures: "negativi già prima dei costi" | Il motore registra lo stop quando stop e target cadono nello stesso minuto (`src/mnq_timestral/evaluation.py:83-87`); lo stop MNQ (8 punti) è più piccolo del range mediano di un minuto (15,5). Anche la direzione opposta perde lordo in 5/6 rami; con risoluzione neutra tutti e sei sono ~0 lordi; nessun ramo mostra abilità direzionale (t lato−opposto da −0,75 a +1,22). | **Probabile.** Conclusione corretta: nessun edge, perdite da costi (2,23 $ MNQ, 3,73 $ MES per roundtrip, 14% e 37% dello stop) su bracket a scala di rumore (stop 0,027% del prezzo). Non un "anti-edge". |
| MNQ Sweep/MSS −379,42 | Netto con risoluzione neutra −11; IC giornaliero 95% [−5,2; +4,9]. | **Inconclusivo**, non dimostrato negativo. Bassa priorità: nessuna abilità direzionale e la variante ATR perdeva prima dei costi. |
| 120 sessioni futures | Bastano a respingere la profittabilità netta per MNQ VWAP e i tre rami MES con qualunque convenzione; ORB al limite. | Un solo regime semestrale già osservato, senza periodo fuori campione. |
| SMA168 disattivata di fatto | `src/mnq_local/binance_spot.py:175` rifiuta l'ingresso se il rischio supera il budget residuo di drawdown (20 − DD): con budget 4,97–5,14 USDT e rischio 5,14–5,20 ogni ingresso successivo è respinto e l'equity si congela. Operatività reale solo 1/1–10/2, 1–29/7, 1/10–26/11 2025. | **Probabile** (meccanismo dimostrato). "Nessun blocco di rischio" è tecnicamente vero ma fuorviante. REJECT resta: le perdite sono precedenti. |
| Breakout: fill sullo stesso confine 4h/1h | Nel 98,5% delle ore l'apertura successiva coincide con la chiusura precedente entro 0,01 bp. Con 1 ora di ritardo: +7,46 → +6,94 USDT; con 2 ore: +8,25. | Effetto piccolo; verdetto INCONCLUSIVO invariato. |
| Breakout contro buy & hold | Buy & hold impiega 100 USDT sempre, la strategia ≤12,6 USDT medi pesati nel tempo; scalato all'esposizione il buy & hold farebbe −0,60 invece di −4,78. | Non citare "+7,46 contro −4,78" come sovraperformance. |
| B sull'intera storia | Unendo tutti i ledger B 2020-01 → 2024-11 (1.796 giorni): Sharpe 1,14 contro 1,31 del passivo con stesso cap di volatilità (differenza −0,17, IC 95% circa [−0,78; +0,45]); 2023 significativamente peggiore (IC [−3,04; −0,24]). | Non promuovere B è corretto; indicarla come "candidata più informativa" è debolmente supportato. |
| Gate di drawdown | Confrontare DD favorisce meccanicamente il braccio meno esposto (B 25,8% contro 39,0%). | Lo Sharpe, invariante alla scala, non ne risente. |
| Selezione multipla | ≥20 configurazioni su storie sovrapposte (SMA, breakout, Timestral ×2, futures ×6, SD-2026 ×6, ED-2 ×4); il test 2024 di SD-2026 è riusato come "stress" in ED-2. | Con un anno di dati l'errore standard di uno Sharpe annualizzato è ~1: il migliore di 20 tentativi puramente casuali mostrerebbe in media uno Sharpe vicino a 2. Ogni segmento positivo isolato va letto con questa lente. |

## 5. Affidabilità dei backtest precedenti

| Esperimento | Calcoli | Disegno | Conclusione corretta oggi |
|---|---|---|---|
| BTC 4h breakout | Esatti, riprodotti | Rischio 1 USDT e cap 100 USDT su 1.000: test tecnico, non economico; 26 trade, potenza minima (t per trade ≈ 0,44) | Inconclusivo, non promosso. Corretto. |
| SMA168 | Esatti | Disattivata di fatto dal budget di DD per gran parte dei periodi | Respinta (perdite realizzate prima del blocco). |
| Futures MNQ/MES (6 rami) | Esatti, causali | Bracket fissi a scala di rumore; convenzione stop-first prudente | Nessun edge, perdite da costi; Sweep MNQ inconclusivo. |
| Timestral (BTC e MNQ/MES) | Accuratezza corretta | Test economici degeneri (E-1, E-2) | Nessuna capacità previsiva rispetto al prezzo invariato; nessun test economico valido eseguito. |
| SD-2026 A (momentum) | Esatti | Benchmark e criteri adeguati | Il ranking non aggiunge valore all'EW abbinato. Corretto. |
| SD-2026 B (trend + cap vol) | Esatti | Gate con potenza 8–14%; confronto contro cassa allo 0% | Nessun valore aggiunto dimostrato; sull'intera storia leggermente peggiore del passivo; 2023 sotto il T-bill. |
| SD-2026 C (impulso BTC→ETH) | Mai calcolata per il difetto E-3 | — | Antieconomica: lordo di pochi bp contro ~24 bp di costo. |
| ED-2 H1 / H2 | Esatti | Adeguato | Correttamente non promosse; H2 nel 2020–22 significativamente peggiore del comparatore abbinato. |
| ED-2 H3 (maker) | Non testabile | Mancano dati di coda/fill | Corretto non inventare un P&L. Con fee VIP0 (0,10% spot) uno spread BTCUSDT di frazioni di bp non può remunerare un maker retail. |

## 6. Abbiamo scartato qualcosa troppo presto?

- **No, nel senso che conta.** Nessuna strategia scartata rivela, all'audit, un vantaggio nascosto.
- **C** era peggio di quanto dichiarato, non meglio.
- **Timestral** non è mai stato testato economicamente in modo valido, ma le sue previsioni non battono il "prezzo invariato" (BTC: errore assoluto medio leggermente e significativamente peggiore, 633,84 contro 628,60 a 8 ore, su 1.636 origini; MNQ/MES peggiore in 20/20 confronti su campioni piccoli). Rifare il filtro correttamente accetterebbe pochissimi trade (6/79 e 2/79 con regole non stantie): non è una priorità.
- **MNQ Sweep/MSS** è inconclusivo, non negativo: ma senza abilità direzionale misurabile.
- **Lacuna vera della ricerca precedente:** nessuna campagna ha esaminato fonti di rendimento con una controparte economica identificabile (carry del funding, flussi istituzionali di calendario, premi assicurativi). Le ho esaminate in [OPUS-EDGE-RESEARCH.md](OPUS-EDGE-RESEARCH.md).

## 7. Cosa possiamo riutilizzare

- **Riutilizzabile:** pipeline di acquisizione con checksum e ricevute; primitive contabili (costi, NAV di liquidazione, bootstrap a blocchi accoppiato) verificate; backtester futures (ledger esatti); disciplina di congelamento pre-risultati; runtime spot (journal, risk engine) solo come base tecnica per eventuali osservazioni prospettiche; simulatore carry e controlli di qualità di questa revisione.
- **Da non riutilizzare così com'è:** i due harness di filtro Timestral; il loader orario di SD-2026 (cascata); l'uso del test prospettico di 12 mesi di B come strumento decisionale; Sharpe e rendimenti senza tasso privo di rischio.
- **Regole da adottare d'ora in poi:** benchmark in eccesso sul T-bill; analisi di potenza prima di ogni esperimento (se l'effetto plausibile non è rilevabile nel campione disponibile, non si esegue); inventario globale dei tentativi per stimare la selezione; controparte economica esplicita come prerequisito di ogni ipotesi.

## 8. Riproducibilità e integrità

- Script, output e report degli audit: `research/opus-edge-2026-10-29/audit/spot/AUDIT-SPOT.md` (tabella F1–F19), `research/opus-edge-2026-10-29/audit/futures-timestral/AUDIT-FUTURES-TIMESTRAL.md` (tabella A-1…C-1), `research/opus-edge-2026-10-29/audit/opus/` (ricalcolo in eccesso sul T-bill e hash iniziali dei file protetti). Ogni script elenca il comando di esecuzione in sola lettura.
- 179 file protetti: hash identici a inizio e fine revisione. Nessun servizio avviato, nessun ordine, nessuna chiamata Databento o broker, nessuna spesa. Nessun file esistente modificato o cancellato.
- **Non verificato:** eseguibilità reale dei fill (manca storico bid/ask e sequenza intrabar), capacità, entità esatta della selezione a livello di progetto (manca un inventario completo dei tentativi), motore di replay V5 nel dettaglio e macchina a stati Sweep/MSS (uscite verificate, segnale non re-implementato).
