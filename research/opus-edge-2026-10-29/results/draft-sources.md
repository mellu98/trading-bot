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
