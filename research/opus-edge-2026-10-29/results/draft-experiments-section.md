## 6. Esperimenti preregistrati ed effettivamente eseguiti

Due sole candidate, scelte per meccanismo economico e verificabilità con dati ufficiali gratuiti, non per rendimento storico. Protocolli congelati con ricevuta SHA256 **prima** di qualsiasi risultato economico (`research/opus-edge-2026-10-29/protocol/freeze-receipts.json`):

| Esperimento | Protocollo | SHA256 protocollo | Congelato (UTC) | Risultati presenti al congelamento |
|---|---|---|---|---|
| E1 carry funding | `protocol/E1-funding-carry.json` | `4568eb5d59f8a300730f9124ab692d049c30a9938a4462a3e9dcc527b042f6d6` | 2026-10-29 09:29:53 | solo `power.json` (nessun P&L) |
| E2 turn-of-month | `protocol/E2-turn-of-month.json` | `b14182f4ffb2eb12db38774c254ed8cf2f0743e5aea512b21d177baf5429b5e6` | 2026-10-29 09:31:56 | nessun risultato E2 |

Unica modifica pre-congelamento dettata dai dati: il controllo strutturale (senza statistiche economiche) ha trovato 16 barre spot di durata irregolare (manutenzioni Binance 2020–2023) e 31 ore spot mancanti; regola fissata prima dei risultati: barre irregolari mantenute e segnalate, ore mancanti = niente esecuzione quel giorno.

### E1 — Carry delta-neutral sul funding (spot long + perpetual USDⓈ-M short)

**Ipotesi.** La domanda di leva long sui perpetual mantiene il funding mediamente positivo; chi fornisce il lato short coperto con spot incassa il funding. **Controparte:** speculatori long con leva. **Perché può persistere:** capitale immobilizzato su due wallet, margine/liquidazione, rischio exchange e stablecoin, segmentazione. **Cosa lo uccide:** affollamento (basis trade, stablecoin sintetiche delta-neutral dal 2024), funding negativo nei mercati ribassisti, costi di turnover.

**Regole congelate.** BTCUSDT/ETHUSDT 50/50, sleeve indipendenti; quantità spot = quantità short perpetual; collaterale isolato 0,5 × nozionale (2x); decisione ed esecuzione giornaliera alle 01:00 UTC sull'apertura oraria, usando solo funding regolati prima; ribilanciamento se collaterale/nozionale esce da [0,25; 1,0]; liquidazione simulata se, nell'ora, il **massimo last-price** del perpetual porta il margine sotto 0,5% (perdita dell'intero collaterale). Configurazioni: **E1A sempre attiva**, **E1B isteresi** (entra se funding 7 gg annualizzato ≥10%, esce se ≤0%), vicino E1B 20%/0% solo descrittivo. Costi per lato e per gamba: base spot 10 bp + perpetual 5 bp + 1 bp spread + 1 bp slippage; avverso 15/7,5/5/5; severo 20/10/10/10. Benchmark: T-bill 3 mesi (FRED DTB3), cassa USDT 0%, buy & hold 50/50.

**Dati.** 486 archivi ufficiali `data.binance.vision` (funding, klines 1h perpetual e spot, 2020-01 → 2026-09), tutti verificati contro `.CHECKSUM`; spot in µs dal 2025 normalizzato; perpetual senza ore mancanti; 7.395 regolamenti funding per simbolo, tutti a 8h (00/08/16 UTC).

**Segmenti.** D esplorativo 2020-01-08 → 2023-12-31 (meccanica e stabilità); E valutazione segregata 2024-01-01 → 2026-09-30. Il progetto non aveva mai caricato dati di funding o perpetual, ma la storia del funding è pubblica: **nessun periodo è un holdout vero**.

#### Risultati segmento E (2024-01 → 2026-09), 10.000 USDT

| Config | Costi | Netto | Annuo | T-bill annuo | Eccesso annuo | Vol | Sharpe in eccesso | Max DD | In mercato | Liquidazioni |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| E1A sempre attiva | base | 13,16% | 4,60% | 4,44% | **+0,15%** | 0,44% | 0,35 | 0,41% | 100% | 0 |
| E1A sempre attiva | avverso | 12,22% | 4,28% | 4,44% | −0,16% | 0,57% | −0,27 | 0,56% | 100% | 0 |
| E1A sempre attiva | severo | 11,14% | 3,91% | 4,44% | −0,53% | 0,79% | −0,65 | 0,93% | 100% | 0 |
| E1B isteresi 10/0 | base | 9,74% | 3,44% | 4,44% | −1,01% | 0,46% | −2,16 | 0,26% | 53% | 0 |
| E1B vicino 20/0 | base | 7,52% | 2,67% | 4,44% | −1,77% | 0,41% | −4,31 | 0,24% | 34% | 0 |
| Buy & hold 50/50 | base | 56,57% | 17,70% | 4,44% | +13,26% | 52,29% | 0,49 | 58,49% | 100% | — |

Decomposizione E1A base: funding incassato **1.385,30 USDT**, P&L prezzi spot+perpetual **+1,89**, fee 56,34, spread 7,51, slippage 7,51, netto **+1.315,82**. Beta verso BTC −0,002. A costi zero l'eccesso sul T-bill sarebbe circa **+0,39%/anno**: il problema non sono le commissioni, è il premio.

| E1A base | Strategia | T-bill | Eccesso |
|---|---:|---:|---:|
| 2024 | 8,52% | 5,18% | +3,34% |
| 2025 | 3,18% | 4,21% | −1,03% |
| 2026 gen–set | 1,06% | 2,82% | −1,76% |

Funding descrittivo (somma dei tassi regolati, scala 365 gg): BTC 2020 17,2% · 2021 30,6% · 2022 4,2% · 2023 7,9% · 2024 11,9% · 2025 5,1% · 2026 2,9% (26% dei regolamenti negativi); ETH 27,4% · 37,5% · 0,8% · 8,3% · 13,0% · 4,9% · 1,9% (30% negativi nel 2026).

**Criteri preregistrati (segmento E):** E1A fallisce c1 (eccesso negativo con costi avversi), c2 (bootstrap: limite inferiore unilaterale della media giornaliera in eccesso −0,21 bp con blocchi 7 e −0,37 bp con blocchi 30), c5 (eccesso positivo solo nel 2024); passa c3 (DD 0,41%) e c4 (zero liquidazioni). E1B fallisce anche c6 (rende meno della versione sempre attiva). **Esito: non promossa.**

#### Segmento D (2020–2023, esplorativo)

E1A base +42,19% (+9,24%/anno, T-bill 1,91%, eccesso +7,32%/anno, Sharpe in eccesso 1,51), ma l'eccesso è concentrato nel 2021 (+25,84%); 2022 −0,63%, 2023 +0,29%. Una liquidazione simulata il 13/3/2020: la regola congelata usa il massimo last-price, e il perpetual ETH ha stampato 323 USDT contro un mark price massimo di 119,47 (diagnostica post-hoc `research/opus-edge-2026-10-29/results/E1/diag-markprice.json`). Con la regola reale di Binance sul mark price quella liquidazione probabilmente non sarebbe avvenuta: il segmento D è quindi prudenziale, ma non cambia la valutazione di E.

**Lettura economica.** Il meccanismo è reale e misurabile: il funding è stato positivo in media in ogni anno. Ma il premio si è compresso fino al tasso privo di rischio: nel 2024–2026 la carry ha reso quanto un T-bill, con in più rischio exchange, stablecoin, ADL e operatività. Con un eccesso di +0,15–0,39%/anno basta una probabilità annua di perdita totale presso l'exchange superiore a circa 0,2–0,4% per renderla svantaggiosa. L'isteresi peggiora sempre: la persistenza del funding non paga il turnover.

### E2 — Turn-of-the-month sul mercato azionario USA

**Ipotesi.** Flussi istituzionali prevedibili a cavallo di fine mese (contributi e stipendi investiti a inizio mese, vendite per esigenze di liquidità prima della fine) rendono più alti i rendimenti dei giorni TOM. **Controparte:** investitori istituzionali che comprano/vendono per calendario di cassa, non per prezzo. **Cosa lo uccide:** anticipazione da parte di arbitraggisti dopo la pubblicazione.

**Regole congelate.** Definizione canonica (Lakonishok–Smidt 1988; McConnell–Xu 2008): ultimo giorno di borsa del mese e primi tre del mese successivo; acquisto alla chiusura del giorno −2, vendita alla chiusura del giorno +3; T-bill negli altri giorni. Una sola variante, nessun vicino. Costi per lato 2 bp base, 5 avverso, 10 severo, 24 lati l'anno. Dati: Kenneth French daily factors (CRSP value-weighted, file costruito sul database CRSP 202609), 1926-07-01 → 2026-09-30, 26.338 giorni.

| Segmento | Giorni | TOM bp/g | Altri bp/g | t NW diff. | Strategia annuo | Eccesso vs T-bill | Sharpe ecc. | B&H Sharpe ecc. | Alpha annuo (t) | Placebo p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1926–1987 | 16.579 | 15,11 | −0,01 | 7,16 | 9,61% | 6,49% | 0,95 | 0,41 | 5,24% (6,75) | 0,000 |
| 1988–2005 | 4.541 | 13,53 | 0,83 | 3,22 | 10,54% | 6,19% | 0,86 | 0,53 | 4,37% (2,84) | 0,000 |
| **2006–set 2026** | 5.218 | 4,98 | 4,18 | **0,20** | 3,36% | 1,61% | **0,23** | **0,56** | −0,02% (−0,01) | 0,326 |
| 2006–2012 | 1.761 | 4,70 | 1,64 | 0,40 | 2,99% | 1,33% | 0,18 | 0,24 | 0,80% (0,27) | 0,301 |
| 2013–2019 | 1.762 | 2,19 | 6,28 | −0,78 | 1,11% | 0,38% | 0,09 | 1,05 | −2,47% (−1,14) | 0,817 |
| 2020–set 2026 | 1.695 | 8,16 | 4,64 | 0,48 | 6,16% | 3,23% | 0,41 | 0,65 | 1,27% (0,44) | 0,223 |

Quota del premio azionario realizzata nei giorni TOM (che sono ~19% dei giorni): **100%** nel 1926–1987, **79%** nel 1988–2005, **22%** nel 2006–2026, cioè proporzionale al tempo. Costi severi: eccesso 2006–2026 −0,36%/anno.

**Criteri preregistrati 2006–2026:** falliscono tutti (c1–c7). **Esito: non promossa.** È un caso da manuale di anomalia documentata che scompare dopo la pubblicazione, con un campione abbastanza grande (20 anni, 5.218 giorni) da renderlo una conclusione solida, non un problema di potenza.
