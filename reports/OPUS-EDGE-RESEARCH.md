# Ricerca di un vantaggio economico — Opus

**29 ottobre 2026. Autore: Claude Opus, Chief Quant Researcher (revisione indipendente). Verdetto: NESSUN EDGE CREDIBILE.**

Report gemello: [OPUS-INDEPENDENT-AUDIT.md](OPUS-INDEPENDENT-AUDIT.md). Codice, protocolli, dati e risultati: `research/opus-edge-2026-10-29/` (README con i comandi di riproduzione).

## 0. Sintesi

- Ho cercato **fonti di rendimento con una controparte identificabile**, non parametri migliori: per ogni ipotesi chi paga, perché accetta di pagare, cosa eliminerebbe il premio, se un piccolo operatore può incassarlo.
- Due candidate, scelte per meccanismo e verificabilità, testate con regole e criteri congelati **prima** dei risultati, dati ufficiali verificati con checksum, costi in tre scenari e il **T-bill** come benchmark:
  - **E1 — carry delta-neutral sul funding BTC/ETH:** meccanismo reale (i long con leva pagano), premio molto alto nel 2020–2021, ma nel 2024–set 2026 rende **+4,60%/anno contro il T-bill al 4,44%**. Con costi avversi è sotto il T-bill, e lo è in ogni scenario dal 2025. Non promossa.
  - **E2 — turn-of-the-month sull'azionario USA:** anomalia fortissima fino al 2005 (t = 7,2 e 3,2), **scomparsa dal 2006** (t = 0,20, nessun alpha) su 5.218 giorni. Non promossa.
- Nessuna ipotesi esaminata giustifica investimenti operativi. L'unica famiglia con premio documentato non testata (vendita di volatilità) richiede derivati, dati di opzioni non presenti nel progetto e gestione del rischio di coda.
- Quello che nei dati del progetto 2020–2024 ha "reso" è l'**esposizione al mercato cripto** (il passivo con controllo della volatilità), non un vantaggio di trading.

## 1. Premesse rimesse in discussione

1. **Il mercato scelto.** BTC/USDT spot, MNQ e MES sono fra gli strumenti più liquidi e competitivi al mondo. Segnali ricavati da sole barre OHLCV pubbliche, su orizzonti da minuti a settimane, competono con operatori che hanno dati, latenza e costi migliori. Un piccolo operatore non ha vantaggi di informazione o velocità; i suoi vantaggi possibili sono pazienza, nessun vincolo di benchmark, capacità minima richiesta, disponibilità a sopportare rischi che altri evitano.
2. **La domanda mancante: chi paga?** Nessuna delle ipotesi precedenti indicava una controparte che paghi sistematicamente. Senza controparte un rendimento storico positivo è indistinguibile dalla selezione su rumore. Criterio adottato qui: un'ipotesi entra in test solo se si sa chi è dall'altra parte, perché accetta di pagare e cosa eliminerebbe il premio.
3. **Il benchmark.** Una strategia che sta spesso in cassa va confrontata con il tasso privo di rischio (T-bill USA: 5,07% medio nel 2023, 4,97% nel 2024, 4,07% nel 2025, 3,71% nel 2026), non con la cassa allo 0%. Una strategia market-neutral deve battere il T-bill, non lo zero.
4. **La potenza.** Prima di chiedersi se una strategia funziona occorre chiedersi se il campione può dirlo. Con dati giornalieri, distinguere uno Sharpe di 0,5 da zero richiede decenni; solo premi ad alto Sharpe sono verificabili in mesi.
5. **Dove un piccolo operatore può realisticamente guadagnare.** Premi al rischio con controparte chiara (carry, assicurazione), flussi strutturali prevedibili, inefficienze troppo piccole per i grandi. Le prime due famiglie sono state testate qui; la terza richiede dati di microstruttura e costi da market maker che un conto VIP0 non ha.

## 2. Fonti esaminate

### 2.1 Dati ufficiali usati direttamente (verificati dall'uso)

| Fonte | Uso | Verifica effettuata |
|---|---|---|
| [Binance public data](https://github.com/binance/binance-public-data) — `data.binance.vision` | Funding USDⓈ-M, klines 1h spot e perpetual BTCUSDT/ETHUSDT 2020-01 → 2026-09; mark price (3 mesi, diagnostica) | 489 ZIP verificati contro il `.CHECKSUM` ufficiale, 13,1 MB, ricevute UTC in `cache/receipts-binance.json`. Spot in millisecondi fino al 2024 e in **microsecondi dal 2025-01** (verificato sul contenuto: open time a 16 cifre); perpetual sempre in millisecondi. |
| [Kenneth R. French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html), `F-F_Research_Data_Factors_daily` | Mercato USA value-weighted (Mkt-RF + RF), 1926-07-01 → 2026-09-30 | Intestazione: file costruito sul database CRSP 202609; SHA256 `96c23b88…9c89`. |
| [FRED DTB3](https://fred.stlouisfed.org/series/DTB3) | T-bill a 3 mesi, benchmark privo di rischio | Serie fino al 2026-10-27; SHA256 `18b5d8f1…30b3`. Medie annue: 2023 5,07%, 2024 4,97%, 2025 4,07%, 2026 3,71%. |

Controllo incrociato indipendente: l'agente di letteratura ha ricalcolato il funding annuo via API pubblica Binance ottenendo gli stessi valori dei miei archivi (es. BTC 2021 30,6%, 2024 11,9%, 2025 5,1%).

### 2.2 Le quattro fonti indicate

SSRN e ScienceDirect bloccano l'accesso automatico (403/Cloudflare): non ho aggirato i controlli, quindi tre fonti sono verificate a livello di metadati e abstract (Crossref/OpenAlex), non di testo integrale.

| Fonte indicata | Identità verificata | Stato | Cosa sostiene davvero | Accesso |
|---|---|---|---|---|
| [github.com/binance/binance-public-data](https://github.com/binance/binance-public-data) | Repository ufficiale di `data.binance.vision` | Attivo; nota ufficiale nel README (commit 2025-01-09): timestamp spot in microsecondi dal 1° gennaio 2025 | Archivi spot, USDⓈ-M, COIN-M, opzioni (BVOL); `.CHECKSUM` SHA256 per ogni ZIP. Funding, mark/index/premium dal 2020-01; open interest dal 2020-09; bookTicker USDⓈ-M solo 2023-05 → 2024-03 | Testo integrale + uso diretto di 489 archivi |
| [SSRN 7350238](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7350238) | Nefedov, *How Much Sharpe is Illusory? Quantifying Backtest Overfitting in Crypto Factor Strategies*, DOI 10.2139/ssrn.7350238 | Preprint 2026, non peer-reviewed | 137 perpetual Binance 2020–2024, 6 fattori: il protocollo "ingenuo" gonfia lo Sharpe di 3,6 volte; con protocollo rigoroso (walk-forward, costi, Deflated Sharpe) **nessun fattore sopravvive**, 4 su 6 negativi fuori campione; la funding-carry sopravvive solo con costi ottimistici | Abstract |
| [SSRN 7556359](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7556359) | Wang, Pang, *Predictability on the Move: The Cryptocurrency Cross-Section*, DOI 10.2139/ssrn.7556359 (registrato 2026-10-06) | Preprint, non peer-reviewed | 1.043 segnali su universo Binance point-in-time: i premi pubblicati di size, momentum e trend si indeboliscono; su tutto il campione il test anti data-snooping **non seleziona nessun segnale**; nelle finestre recenti emergono segnali di liquidità a un giorno, positivi solo "a costi bassi" | Abstract |
| [doi 10.1016/j.bcra.2025.100354](https://doi.org/10.1016/j.bcra.2025.100354) | Werapun, Karode, Suaboot, Arpornthip, Sangiamkul, *Exploring risk and return profiles of funding rate arbitrage on CEX and DEX*, Blockchain: Research and Applications 7(4) 100354 | Peer-reviewed, open access | Arbitraggio del funding su Binance, BitMEX, ApolloX, Drift (BTC, ETH, XRP, BNB, SOL), 60 scenari: rendimenti "fino al 115,9% in sei mesi". È **il migliore di 60 scenari**; costi, leva e periodo non verificabili dall'abstract: **non è un rendimento atteso** | Abstract (testo bloccato) |

### 2.3 Letteratura cripto rilevante (verificata dall'agente di ricerca; "TI" = testo integrale letto)

| Fonte | Risultato verificato | Limite / controevidenza |
|---|---|---|
| He, Manela, Ross, von Wachter, *Fundamentals of Perpetual Futures*, [arXiv 2212.06888](https://arxiv.org/abs/2212.06888) v7, set. 2026 (TI) | Carry statica BTC 2020-01 → 2024-03 a costo zero: 10,18%/anno, Sharpe 2,24; ETH 13,22%; BNB −5,14%. Le deviazioni dal prezzo di non-arbitraggio calano di ~22 punti l'anno e di ~80% dopo il 2022 (portfolio margin Binance, aprile 2022) | La strategia dinamica redditizia assume fee maker da grandi volumi (0,164% round trip contro 0,24–0,30% del VIP0) e fill passivi |
| Christin, Routledge, Soska, Zetlin-Jones, *The Crypto Carry Trade*, working paper 2022 (TI) | Carry BTC 2020-08 → 2022-06 21,84%/anno lordo, in calo per periodi: 39,0 → 19,6 → 14,7 → 7,6% | Esclude costi e margini; periodo rialzista |
| Schmeling, Schrimpf, Todorov, *Crypto Carry*, [BIS WP 1087](https://www.bis.org/publications/working-paper-1087-crypto-carry.pdf) (TI); Management Science 2026 (abstract) | Carry media ~10%/anno 2019–2022 con picchi oltre il 40%; i long sono soprattutto piccoli operatori; un aumento della carry di 10 punti prevede liquidazioni pari al 44% dell'open interest il mese dopo | Su CME la cash-and-carry mensile ha Sharpe 0,59 prima dei costi: il premio è anche rischio di crash |
| Borri, Liu, Tsyvinski, Wu, *Cryptocurrency as an Investable Asset Class*, Annual Review of Financial Economics 2026 (TI parziale) | Sharpe della carry BTC 6,45 sul campione intero, 4,06 dal 2024, **negativa nel 2025**; size e momentum a 12–24 settimane non significativi dopo il 2020 | Nessun costo |
| Liu, Tsyvinski, Wu, JF 2022; Liu, Tsyvinski, RFS 2021; Han, Kang, Ryu SSRN 4675565 (abstract) | Fattori di mercato, size, momentum; momentum temporale forte in campione; con ipotesi realistiche il momentum cross-sectional è "quasi inesistente" | Coerente con il fallimento della famiglia A |
| Baur et al. 2019; Kaiser 2019; Mueller 2024, Finance Research Letters (abstract) | Nessun effetto calendario robusto sui rendimenti cripto; effetto lunedì scomparso dopo il 2015 | — |
| Alexander, Imeraj 2020, J. Alternative Investments; Almeida et al. 2025, arXiv 2410.15195 (abstract) | Il premio per il rischio di varianza BTC esiste ed è maggiore di quello dell'S&P 500, dipendente dal regime | **Nessuna evidenza verificata di rendimenti netti** per un retail che vende volatilità; coda di crash decisiva |
| Makarov, Schoar, JFE 2020; Crépellière et al., J. Financial Markets 2023 (abstract) | Arbitraggio fra exchange quasi impossibile da sfruttare dal 2018 | Infattibile per un piccolo operatore |
| Commissioni e regole Binance (pagine ufficiali lette il 29/10/2026) | VIP0 spot 0,100%/0,100%; USDⓈ-M 0,0200%/0,0500%; funding base 0,01% ogni 8h (~10,95%/anno) quando il premio è in banda; cap BTC/ETH ±0,30%; passaggio automatico a funding orario se si tocca il cap (dal 2025-05-02) | Il funding BTC non ha mai superato la base nel 2025–2026 |
| Repository GitHub sulla carry (solo README, nessun codice eseguito) | Il più documentato (santzmr) riporta −1,52% in 3,5 anni con fee taker contro +5,20% lordo; un altro (tommybook) riporta carry BTC +35,7% nel 2021, +5,3% nel 2025, +2,5% nel 2026 | Rendimenti dei README non verificati; coerenti con i miei dati |

### 2.4 Mercati alternativi alle cripto (verificati dall'agente di ricerca; TI = testo integrale, AB = abstract/pagina editore, SEC = solo fonte secondaria)

| Fonte | Risultato verificato | Stato dopo la pubblicazione |
|---|---|---|
| McConnell, Xu, *Equity Returns at the Turn of the Month*, Financial Analysts Journal 64(2), 2008 (AB); Lakonishok, Smidt, RFS 1(4), 1988 (SEC) | CRSP 1926–2005: 0,15%/giorno nei 4 giorni TOM contro −0,001% negli altri; presente in 31 paesi su 35 | La mia replica (E2) coincide fino al 2005 e mostra **effetto nullo dal 2006** |
| Etula, Rinne, Suominen, Vaittinen, *Dash for Cash*, [RFS 33(1), 2020](https://academic.oup.com/rfs/article/33/1/75/5494694) (TI, open access) | Meccanismo causale: istituzioni vendono prima di fine mese per esigenze di pagamento nel ciclo di regolamento; 1995–2013: +77 bp cumulati da T−3 a T+3, −17 bp da T−8 a T−4; il cambio di regolamento europeo 2014 indebolisce il pattern (t −3,66) | **Mai testato dopo il 2013** in lavori peer-reviewed; dati di un blog di practitioner indicano indebolimento. Candidato al prossimo test (sezione 9) |
| Ko, Yang, *The Pre-Holiday Premium of Ariel (1990)…*, Critical Finance Review (TI) | Premio pre-festivo non significativo nelle large cap dopo il 1983/1990 (t 0,64–0,93 su Dow e S&P 500) | Morto per ETF e future |
| Lucca, Moench, JF 2015 (AB); Kurov, Wolfe, Gilbert, Finance Research Letters 2021 (AB) | Drift pre-FOMC ~49 bp (SEC) | "Sostanzialmente scomparso dopo il 2015" |
| Greenwood, Sammon, *The Disappearing Index Effect*, JF 80(2), 2025 (AB) | Effetto inclusione S&P 500 dal 7,4% (anni '90) a meno dell'1% | Morto |
| Boyarchenko, Larsen, Whelan, NY Fed [Liberty Street Economics, 1/7/2026](https://libertystreeteconomics.newyorkfed.org/2026/07/the-disappearing-overnight-drift/) (TI) | Drift notturno E-mini 2–3 a.m. ~3,7%/anno 1998–2020 | ~0 nel 2021–2025 |
| ETF NightShares NSPY/NIWM ([WealthManagement, 2023](https://www.wealthmanagement.com/etfs/night-effect-etfs-shut-down-overnight-stock-returns-elusive), TI) | ETF reali basati sull'effetto overnight, lanciati a giugno 2022 | **Chiusi a luglio 2023**: NSPY −6,9% contro S&P 500 +22% (prova live) |
| Hurst, Ooi, Pedersen, *A Century of Evidence on Trend-Following*, AQR 2014 (TI); Moskowitz, Ooi, Pedersen, JFE 2012 (AB) | Trend multi-asset 1880–2013: netto 11,2%/anno, Sharpe 0,77 (simulato); 2000–2013 Sharpe 0,62 | Huang et al., JFE 2020 (AB): poca prevedibilità asset per asset. Indici CTA live: ~0,8–1,6%/anno negli anni 2010, +20% nel 2022, circa piatti 2023 e 2025 (SEC) |
| Moreira, Muir, JF 2017 (TI parziale); Cederburg et al., JFE 2020 (AB) | Gestione della volatilità: alpha in campione | Su 103 strategie **non batte** le versioni non gestite in tempo reale: è controllo del rischio, non edge |
| Carr, Wu, RFS 2009 (AB); XIV, 5/2/2018 (SEC) | Premio per il rischio di varianza negativo in media (i venditori guadagnano) | XIV −96% in una seduta: il premio è pagato in rischio di rovina |
| Harvey, Mazzoleni, Melone, NBER WP 33554, 2025 (AB) | Flussi di ribilanciamento a pesi fissi: rendimento azionario del giorno dopo −17 bp quando le azioni sono sopra il peso obiettivo | Working paper, nessuna verifica fuori campione; definizione del segnale non verificata |

### 2.5 Meta-evidenza: perché il prior deve essere scettico

| Fonte | Dato verificato |
|---|---|
| McLean, Pontiff, JF 2016 (SEC, coerente fra fonti) | I predittori pubblicati rendono il 26% in meno fuori campione e il **58% in meno dopo la pubblicazione** |
| Chen, Velikov, JFQA 2023 (AB) | Al netto degli spread e del decadimento, l'anomalia media rende **~4 bp al mese**; le migliori ≤10 bp (impatto di prezzo escluso) |
| Hou, Xue, Zhang, RFS 2020 (AB) | Il 65% di 452 anomalie non si replica a t ≥ 1,96 |
| Jensen, Kelly, Pedersen, JF 2023 (TI parziale) | 82,4% dei fattori si replica come portafogli di carta, **prima dei costi**: replicabile non significa negoziabile da un piccolo conto |
| Harvey, Liu, Zhu, RFS 2016 (AB) | Una nuova scoperta in campione dovrebbe superare t > 3 |
| Chague, De Losso, Giovannetti 2019 (AB); Barber, Lee, Liu, Odean, J. Financial Markets 2014 (SEC) | Brasile: il **97%** di chi ha fatto day trading su future per almeno 300 giorni ha perso; Taiwan: meno dell'1% dei day trader è prevedibilmente profittevole al netto delle commissioni |

## 3. Ranking motivato delle famiglie (massimo cinque)

Punteggi 1–5 (5 = migliore). "Evidenza" valuta qualità e sopravvivenza post-pubblicazione delle prove; "Fattibilità" valuta dati, costi, complessità e capitale per un piccolo operatore; "Verificabilità" quanto rapidamente un test futuro può dare una risposta con potenza adeguata.

| # | Famiglia | Chi paga e perché | Meccanismo | Evidenza | Fattibilità | Verificabilità | Rischio principale | Decisione |
|---|---|---|---|---:|---:|---:|---|---|
| 1 | **Carry del funding/basis cripto**, delta-neutral | Speculatori long con leva pagano il funding a chi fornisce il lato short coperto | 5 | 4 | 3 (richiede derivati) | 5 (volatilità ~0,5%) | Exchange, stablecoin, ADL, liquidazione | **Testata (E1):** premio reale ma oggi ≈ T-bill. Non promossa. |
| 2 | **Flussi istituzionali di fine mese** (turn-of-the-month canonico; finestra "Dash for Cash" T−3…T+3; ribilanciamento a pesi fissi) | Istituzioni che vendono e comprano per esigenze di cassa e di regolamento, non per prezzo | 4 | 2 (canonico decaduto; le due varianti con meccanismo più preciso non sono mai state verificate fuori campione) | 5 | 1 (servono anni per confermare; un test può solo "uccidere") | Crollo nei giorni investiti; accorciamento del regolamento (T+1) | **Testata la versione canonica (E2):** scomparsa dal 2006. Non promossa. La finestra di Etula et al. è il test più economico ancora aperto (sezione 9). |
| 3 | **Premio per il rischio di volatilità** (vendita di opzioni, anche coperta) | Chi compra assicurazione contro crolli | 5 | 3 (esistenza robusta su indici e su BTC; nessuna evidenza verificata di rendimenti netti per un retail) | 2 (derivati, dati opzioni non gratuiti, spread) | 3 | Perdite di coda concentrate (XIV −96% in un giorno) | **Non testata:** mancano dati opzioni storici nel progetto e autorizzazione ai derivati. |
| 4 | **Trend multi-asset / managed futures** | Chi si copre paga gli speculatori; investitori lenti | 3 | 3 (secolo di backtest, Sharpe netto simulato 0,77; indici CTA reali ~0,8–1,6%/anno negli anni 2010) | 2 (servono futures diversificati; micro-contratti poco granulari per piccoli capitali) | 1 | Lunghi periodi piatti o perdenti | **Non testata qui:** B è la versione solo cripto e non batte il proprio passivo. È un premio diversificante, non un edge; un piccolo operatore lo compra già pronto in ETF. |
| 5 | **Beta cripto con controllo della volatilità** | Nessuno paga un "edge": è esposizione al premio di mercato | 2 | 2 (la gestione della volatilità non batte il passivo in tempo reale su 103 strategie) | 5 | 1 | Drawdown del mercato cripto, nessun flusso di cassa sottostante | **Non è un edge:** è ciò che ha "reso" nei dati 2020–2024, ma è una scelta di asset allocation, non di trading. |

**Escluse con motivazione (nessuna controparte o evidenza contraria):**
- *Pattern intraday e materiale ICT.* Nel progetto si riduce a un'ipotesi Sweep/MSS solo-prezzo (nessun archivio ICT presente). Il fondamento accademico più vicino (Osler, JF 2003: ordini take-profit raggruppati sui numeri tondi e stop-loss appena oltre, nel mercato valutario) spiega perché certi livelli contano, non dimostra un edge netto negoziabile; nei test del progetto Sweep/MSS non mostra abilità direzionale.
- *VWAP/ORB su micro future* (nessuna abilità direzionale, perdite da costi); *previsioni con modelli fondazionali* (nessuna capacità rispetto al prezzo invariato); *momentum cross-sectional su 7 cripto* (nessun valore oltre l'EW abbinato; letteratura: "quasi inesistente" con ipotesi realistiche); *reversal e volume relativo* (costi); *impulso BTC→ETH* (antieconomico, errore E-3 dell'audit).
- *Market making retail* (fee VIP0 superiori allo spread di BTCUSDT); *arbitraggio fra exchange* (sparito dal 2018); *effetti calendario cripto* (non robusti); *token unlock* (un solo preprint con 52 eventi).
- *Carry su altcoin:* funding annuo negativo in più anni (BNB 2022–2025, SOL 2022 e 2026); dati API raccolti dall'agente di letteratura, coerenti con i miei archivi su BTC/ETH.
- *Anomalie azionarie decadute dopo la pubblicazione:* overnight (drift E-mini ~0 dal 2021; ETF NightShares chiusi dopo 13 mesi a −6,9% contro S&P +22%), drift pre-FOMC (scomparso dopo il 2015), pre-festivo (non significativo sulle large cap), inclusione negli indici (da 7,4% a meno dell'1%), anomalie su singoli titoli (~4 bp/mese netti).

## 4. Perché proprio due candidate e non altre

- Ho scelto **E1** perché ha il meccanismo economico più convincente fra le famiglie testabili con dati ufficiali gratuiti, non era mai stata esaminata dal progetto ed è ad alto Sharpe storico, quindi verificabile rapidamente.
- Ho scelto **E2** perché è la famiglia strutturale più documentata su un mercato diverso, con 100 anni di dati ufficiali gratuiti: un test con potenza vera, che risolve anche il dubbio "forse il problema è il mercato cripto".
- Non ho testato il premio di volatilità perché i dati storici di opzioni non sono nel progetto e acquistarli richiede autorizzazione; non ho testato il trend multi-asset perché i dati di futures diversificati non sono gratuiti e la versione cripto (B) è già stata esaminata.
- Non ho consumato alcun holdout: non esiste un periodo storico incontaminato; tutto è dichiarato esplorativo.

## 5. Esperimenti preregistrati ed effettivamente eseguiti

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

## 6. Limiti statistici

- **Potenza.** Con rendimenti giornalieri iid (ipotesi ottimistica), per confermare con test unilaterale al 5% e potenza 80% uno Sharpe annuo di 0,5 servono ~26 anni; di 1,0 ~7 anni; di 2,0 ~2,4 anni (`research/opus-edge-2026-10-29/results/power.json`). Per una *differenza* di Sharpe di 0,36 fra due strategie correlate 0,8–0,9 (il caso B contro passivo) servono **38–72 anni**. Quasi tutti i test del progetto erano quindi destinati a "inconcludente" indipendentemente dalla verità.
- **Selezione.** Il progetto ha provato ≥20 configurazioni su storie sovrapposte, più le 4 di questa revisione. Con un anno di dati l'errore standard di uno Sharpe annualizzato è ~1: il migliore di 20 tentativi casuali mostrerebbe in media ~1,9. Il Deflated Sharpe globale resta non stimabile senza inventario completo dei tentativi.
- **Contaminazione.** Nessun periodo è un holdout vero: il funding è pubblico; il 2006–2026 azionario è stato studiato da altri; il ricercatore conosce la storia dei mercati. E1/E2 sono valutazioni esplorative con regole congelate, non conferme.
- **Esecuzione.** Niente bid/ask storico, niente sequenza intrabar, mark price usato solo come diagnostica; T-bill a sconto/360 leggermente prudente a favore della carry.
- **Rischi non modellati in E1:** default o blocco dell'exchange, depeg USDT, auto-deleveraging (in un crollo lo short in profitto può essere chiuso d'ufficio lasciando lo spot scoperto), errori operativi, fiscalità.

## 7. Requisiti tecnici ed economici (se mai si riprendesse)

| | E1 carry funding | E2 turn-of-month |
|---|---|---|
| Strumenti | Conto spot + futures USDⓈ-M (derivati: **non autorizzati**) | ETF UCITS S&P 500 o micro future MES pienamente collateralizzato |
| Capitale minimo | Poche centinaia di USDT tecnicamente; utile solo con capitale per cui lo 0,1–0,4% annuo conta | Basso; costi fissi di commissione pesano sotto ~10.000 € |
| Infrastruttura | Monitoraggio margine 24/7, trasferimenti fra wallet, gestione ADL e liquidazioni, riconciliazione funding | 24 ordini l'anno, eseguibili anche a mano |
| Rendimento atteso dalle evidenze | ≈ T-bill (eccesso 2024–2026 da −0,5% a +0,4% annuo secondo i costi) | ≈ esposizione proporzionale al tempo investito; nessun alpha dal 2006 |
| Rischi principali | Controparte exchange, stablecoin, liquidazione, ADL | Crollo in un giorno TOM; costi fiscali e di commissione per un retail italiano |

## 8. Evidenze a favore e contro

**A favore (verificate):** il funding BTC/ETH è stato positivo in media in ogni anno 2020–2026; nel 2020–2021 la carry ha reso molto più del T-bill con volatilità del 4–5%; il TOM ha concentrato il 100% del premio azionario 1926–1987 e il 79% nel 1988–2005.

**Contro (verificate):** dal 2024 la carry rende quanto il T-bill e dal 2025 meno; la versione condizionata peggiora sempre per turnover; il TOM non ha alpha dal 2006 (t = 0,20); tutte le strategie di prezzo del progetto risultano senza edge o antieconomiche; B non batte il proprio passivo sull'intera storia e nel 2023 rende meno del T-bill.

## 9. Prossimo esperimento realmente informativo

Non un altro backtest su BTC/ETH/MNQ/MES: sarebbe di nuovo esplorativo, contaminato e senza potenza. Due possibilità, entrambe da autorizzare esplicitamente prima di iniziare:

1. **Raccomandata — decisione di governance, non esperimento:** chiudere la ricerca di edge con questo approccio e documentarlo ai soci; tenere l'infrastruttura archiviata. Separare la domanda "vogliamo esposizione cripto/azionaria?" (asset allocation passiva, con rischio dichiarato) dalla domanda "abbiamo un vantaggio?" (oggi: no).
2. **Solo se i soci vogliono continuare la ricerca: un unico test "di uccisione", gratuito e di poche ore.** Verificare la finestra di Etula et al. (2020, "Dash for Cash"), il cui campione finisce nel dicembre 2013, sul periodo **2014-01 → 2026-09** con i dati French già scaricati: acquisto alla chiusura di T−4, vendita alla chiusura di T+3, T-bill negli altri giorni; più, con correzione di Bonferroni, la variante che sposta l'ingresso secondo il ciclo di regolamento (T+3 fino a settembre 2017, T+2 fino a maggio 2024, poi T+1; date da verificare prima del congelamento). Criteri e costi come E2, scritti prima. È il test più informativo per costo perché ha un meccanismo causale pubblicato, un periodo successivo al campione degli autori e dati ufficiali; se fallisce, la famiglia dei flussi di calendario è chiusa. Avvertenze: priorità bassa (la versione canonica è morta e i dati dei practitioner indicano indebolimento), conosco già l'esito aggregato dei 4 giorni canonici T…T+3 in quel periodo (restano non osservati i 3 giorni T−3…T−1), e anche un esito positivo resterebbe esplorativo con rendimento assoluto inferiore al buy & hold. **Non l'ho eseguito**: avrei superato il limite di due candidate e il budget di varianti di E2.

Il premio per il rischio di volatilità resta l'unica famiglia con premio robusto non testata, ma richiede derivati, dati di opzioni storici non presenti nel progetto e gestione del rischio di rovina: oggi non giustifica investimenti operativi.

Il protocollo prospettico già preparato per B (12 mesi) **non** è consigliato come strumento decisionale: con potenza dell'8–14% finirebbe quasi certamente "inconcludente".

## 10. Cosa è stato eseguito e cosa no

**Eseguito:** audit completo del codice e riproduzione byte per byte dei risultati precedenti (vedi audit); verifica delle quattro fonti indicate e di oltre 50 lavori scientifici, working paper, pagine ufficiali e repository (due agenti di ricerca in parallelo; profondità di lettura dichiarata per ciascuna fonte); acquisizione e verifica checksum di 486 archivi Binance, French daily factors, FRED DTB3, 3 archivi mark price per diagnostica; 9 test sintetici del simulatore (tutti PASS); controlli strutturali dei dati; congelamento di due protocolli; E1 su due segmenti × 3 configurazioni × 3 scenari di costo; E2 su 6 segmenti; analisi di potenza; ricalcolo in eccesso sul T-bill dei risultati precedenti; diagnostica mark price.

**Non eseguito:** lettura del testo integrale delle due fonti SSRN e dell'articolo BCRA (accesso automatico bloccato: verificati metadati e abstract); nessun test del premio di volatilità, del trend multi-asset, della finestra "Dash for Cash" o di dati di order book; nessun paper trading o raccolta prospettica; nessuna variante aggiuntiva dopo i risultati; nessuna acquisizione di dati a pagamento; nessuna modifica al bot o ai file esistenti.

## 11. Risposte alle sette domande

1. **Abbiamo commesso errori sostanziali?** Sì, ma non nei calcoli: quattro errori dimostrati (test Timestral degeneri, famiglia C mai calcolata per un difetto del loader, confronti contro cassa allo 0% invece del T-bill, gate e test prospettico di B senza potenza). Nessuno ribalta una non promozione. L'errore più sostanziale è di impostazione: cercare pattern di prezzo senza una controparte che paghi, su mercati molto efficienti, con campioni che non potevano dare risposte.
2. **Abbiamo scartato troppo presto qualcosa di promettente?** No. C era peggio di quanto dichiarato; Timestral non è stato testato correttamente ma non mostra capacità previsiva; Sweep/MSS su MNQ è inconclusivo ma senza abilità direzionale; B è più debole di quanto suggerito. La lacuna vera era non aver esaminato premi con controparte economica: ora esaminati.
3. **Quale famiglia ha il meccanismo più convincente?** La carry del funding: chi vuole leva paga chi la fornisce. È anche l'unica in cui il premio è osservabile direttamente nei dati ufficiali. Ma dal 2024 è sceso al livello del tasso privo di rischio.
4. **Quali evidenze abbiamo verificato concretamente?** Riproduzione esatta di tutti i ledger e le statistiche precedenti; assenza di look-ahead; unità dei timestamp; i quattro errori dell'audit; il funding annuo BTC/ETH 2020–2026 da archivi ufficiali (coincidente con il ricalcolo via API dell'agente di letteratura); i risultati netti di E1 ed E2 con costi e benchmark; la potenza dei test; l'identità e le tesi delle quattro fonti indicate; la compressione della carry confermata da letteratura indipendente (Borri et al. 2026: Sharpe della carry BTC negativo nel 2025) e il decadimento post-pubblicazione delle anomalie di calendario (pre-FOMC, overnight con chiusura degli ETF NightShares, inclusione negli indici).
5. **Esiste una candidata meritevole di paper trading prospettico?** No. Nessuna supera i criteri preregistrati. Un paper trading di E1 misurerebbe con buona precisione un premio che oggi è circa il T-bill; un paper trading di B non avrebbe potenza per decidere.
6. **Cosa manca per dimostrare un vantaggio economico?** Una controparte che paghi più del tasso privo di rischio dopo i costi raggiungibili da un conto retail; prezzi eseguibili (bid/ask, mark price, fill reali); un effetto abbastanza grande da essere rilevato nel tempo disponibile; evidenza che sopravviva alla pubblicazione. Nessuna delle ipotesi esaminate soddisfa insieme queste condizioni.
7. **Ha senso continuare a investire o fermarsi?** Fermarsi con gli investimenti operativi e con la ricerca di pattern su questi mercati. Conservare codice e dati in archivio. Se i soci vogliono esposizione a cripto o azioni, è una decisione di allocazione passiva con rischio dichiarato, non un edge. Ripartire solo con una domanda nuova, una controparte esplicita, budget e regola di stop scritti prima.

## Verdetto finale

### NESSUN EDGE CREDIBILE — nessuna ipotesi esaminata giustifica ulteriori investimenti operativi.

- Le strategie di prezzo del progetto (ICT/Sweep, VWAP, ORB, breakout, SMA, Timestral, momentum, reversal, impulso BTC→ETH) non mostrano vantaggio: alcune sono antieconomiche, le altre senza abilità misurabile dopo i costi.
- La famiglia con il meccanismo più solido, la carry del funding, oggi paga circa quanto un T-bill e richiede derivati e rischio di controparte.
- L'anomalia strutturale più documentata sul mercato azionario è scomparsa dopo la pubblicazione.
- Non definisco "vincente" nessuna strategia e non propongo paper trading: non ci sono candidate che lo meritino.

> Da dire ai soci: abbiamo verificato con rigore che i calcoli erano giusti e che le idee non lo erano. Abbiamo poi provato le due fonti di guadagno più sensate per chi opera in piccolo: una oggi rende quanto i titoli di Stato con più rischi, l'altra è sparita da vent'anni. Non mettiamo capitale, non sviluppiamo altro sul bot. Conserviamo codice e dati; se un giorno vorremo riprovare, partiremo da una domanda nuova con budget e regola di stop scritti prima.
