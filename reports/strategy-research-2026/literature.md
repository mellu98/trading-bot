# Letteratura: ipotesi falsificabili, non promesse di profitto

**Esito della ricerca scientifica:** le tre famiglie hanno un meccanismo plausibile, ma nessuna fonte dimostra la redditività netta della nostra implementazione spot long/cash. Non sono stati consultati risultati dei nuovi backtest. Il protocollo congelato dal coordinatore, non questo memo, è l'unica autorità esecutiva.

## Che cosa è stato verificato

| Fonte primaria | Livello effettivamente consultato | Conseguenza per l'esperimento |
|---|---|---|
| [Liu–Tsyvinski, NBER24877](https://www.nber.org/papers/w24877), poi RFS2021 | Abstract/frontespizio indicizzati; conferma nella [pagina dell'autore Yale](https://economics.yale.edu/people/aleh-tsyvinski/papers). Testo completo non disponibile. | Motivazione del trend, non prova di rendimento netto. Il working paper ha **due autori**, non tre: Goldstein non va attribuito come coautore. |
| [Guo–Sang–Tu–Wang2024](https://www.sciencedirect.com/science/article/pii/S0165188924000551) | Abstract, introduzione e frammenti metodologici del publisher; non appendici/code. | La documentazione riguarda minuti, non un'ora. L'universo fissato nel2020 applicato anche al2019 richiede cautela point-in-time. |
| [Yang2025](https://www.sciencedirect.com/science/article/pii/S1544612325011377) | Abstract, introduzione e frammenti; campione completo e costi non verificati. | Il risultato non può essere trasferito a BTC/ETH senza leva. |
| [Arefev, SSRN7404139](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7404139) | Metadata/abstract primari indicizzati, pagina autore; PDF non verificato. | Replica indipendente **non peer-reviewed**, settembre2026: controevidenza sui perpetual, non test della nostra strategia spot. |
| [Bailey–López de Prado2014](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) | PDF completo dell'autore, versione31luglio2014; [DOI ufficiale](https://doi.org/10.3905/jpm.2014.40.5.094). | DSR richiede assunzioni esplicite sui tentativi; non ripara leakage o fill impossibili. |

Controevidenza aggiuntiva peer-reviewed: [Grobys e altri2025](https://link.springer.com/article/10.1007/s11408-025-00474-9). Differenze di universo, pesi e short-leg producono conclusioni diverse. Non assumere che il controllo della volatilità elimini i crash.

## Universo: ancoraggio storico, non vincitori odierni

Lo [snapshot CMC29dicembre2019](https://coinmarketcap.com/historical/20191229/) identifica gli otto non-stablecoin iniziali. BSV va escluso perché Binance aveva già [delistato BCHSV](https://www.binance.com/en-PH/support/announcement/detail/360026666152). Non va sostituito con il successivo vincitore.

Candidati: **BTC, ETH, XRP, BCH, LTC, EOS, BNB**. Annunci ufficiali e limiti sono nel JSON. L'eleggibilità finale richiede archivi ufficiali precedenti all'ancora, mediana dei volumi USDT dei30giorni completati precedenti almeno10milioni, senza contare giornate iniziali parziali, e gestione di sospensioni/delisting. L'annuncio originale EOSUSDT non è stato reperito: non dichiarare completata questa prova. Il rename BCHABC→BCH è documentato1:1; non fondere ticker senza lineage. Nessun dato finanziario è stato scaricato da questo agente.

## Tre proposte pre-risultati

- **A:** forza relativa14giorni, due sleeve da50%, solo rendimenti positivi, ribilanciamento settimanale; unico vicino7giorni. Cap di volatilità del portafoglio20% con soli rendimenti passati30giorni, identico al benchmark equal-weight.
- **B:** BTC/ETH, trend90giorni e volatilità30giorni, target20% annuo per sleeve, pesi limitati senza leva; vicino60giorni. Il target è un budget, non una garanzia sulla volatilità realizzata.
- **C:** impulso BTC1h oltre una deviazione standard storica168h, posizione ETH1h dopo **un'ora intera di ritardo**; vicino ritardo2h. È una falsificazione semplice, non una replica dei modelli accademici.

Il coordinatore ha confermato questa selezione **prima di qualsiasi risultato finanziario**. Tutte le costanti sono scelte progettuali dichiarate **prima** degli esiti, non parametri “dimostrati” dalla letteratura. Nessuna scelta del migliore vicino dopo il test. In caso di differenza prevale il protocollo congelato, con tracciamento della decisione pre-risultati.

## Limiti decisivi

Sviluppo2020–2022, validazione2023 e test storico2024gennaio–novembre sono una possibile separazione, solo se l'inventario conferma che il test non era stato consultato. Non sono dati futuri: gli eventi storici sono pubblicamente noti. Dicembre2024 e2025–2026 già osservati non diventano nuovi holdout.

Commissioni, spread, slippage, turnover, ritardo e capitale esposto vanno congelati; OHLC non verifica bid/ask storici o fill reali. Confrontare liquidità e passivi sullo stesso universo, anche a rischio/esposizione comparabili usando scale fissate nello sviluppo. Rendimenti positivi ma concentrati o statisticamente incerti non autorizzano integrazione operativa.

**Prossimo passo unico:** eseguire il piccolo protocollo congelato e tentare di respingerlo. Se nessuna famiglia resiste, nessuna strategia viene promossa.
