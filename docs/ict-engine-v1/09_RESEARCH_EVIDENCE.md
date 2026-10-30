# Registro evidenze e fonti primarie
Ricerca consultata il 30 ottobre 2026. Stato: metadata/estratti recuperati tramite ricerca, non audit completo di ogni pagina o video. Nessun risultato di profittabilità ICT è stato verificato. Regole numeriche, punteggi, parametri e criteri di promozione sono proposte del progetto. Non si deduce l'edge dalla notorietà del docente.

|ID|Fonte primaria e link|Cosa sostiene / limite|
|---|---|---|
|S01|The Inner Circle Trader, [Mentorship 2022 Episode 6](https://www.youtube.com/watch?v=Bkt8B3kLATQ)|Video ufficiale reperito, descrizione FVG e market structure shift. Non validazione statistica; non è stata visionata integralmente la lezione|
|S02|The Inner Circle Trader, [Silver Bullet Time Based Trading Model 2023](https://www.youtube.com/watch?v=tRq1hyGGtl4)|Esistenza del modello time-based originale; variante D1 qui è proxy progettuale, non replica certificata|
|S03|[ESMA statement 24 febbraio 2026](https://www.esma.europa.eu/press-news/esma-news/esma-reminds-firms-their-obligations-under-cfd-product-intervention-measures)|Perpetuals che rientrano nei CFD soggetti a misure applicabili; appropriatezza e restrizioni non eliminabili cambiando nome al prodotto|
|S04|[ESMA MiCA register](https://www.esma.europa.eu/pl/node/201529)|Registro CASP da consultare per entità esatta; autorizzazione provider non certifica ogni coppia, cliente o API|
|S05|[OJK: fine transizione OJK/Bappebti, 20 gennaio 2026](https://ojk.go.id/id/berita-dan-kegiatan/siaran-pers/Pages/Nota-Kesepahaman-OJK-Bappebti-2026.aspx)|Trasferimento vigilanza asset finanziari digitali; non prova ammissibilità di uno straniero specifico|
|S06|[OJK PADK 3/2026](https://www.ojk.go.id/id/regulasi/Pages/PADK-Nomor-3-Tahun-2026-Penyelenggaraan-Perdagangan-Aset-Keuangan-Digital-termasuk-Aset-Kripto.aspx)|Pagina indica decorrenza 1 settembre 2026 e disposizioni implementative; allegati non analizzati integralmente|
|S07|[OJK avviso operatori illegali](https://ojk.go.id/id/berita-dan-kegiatan/info-terkini/Pages/Satgas-PASTI-Hentikan-27-Gadai-Swasta-Ilegal-dan-228-Pedagang-Aset-Keuangan-Digital-Ilegal.aspx)|Verificare licenza del provider e lista asset ammessi; non affidarsi all'accessibilità tecnica del sito|
|S08|[CME MNQ contract specification](https://www.cmegroup.com/markets/equities/nasdaq/micro-e-mini-nasdaq-100.contractSpecs.html)|Moltiplicatore $2 e tick 0,25 punti; fee e margine conto sono separati|
|S09|[CME Micro E-mini overview](https://www.cmegroup.com/education/courses/micro-e-mini-futures/micro-e-mini-futures-products-overview)|MES tick 0,25 punti=$1,25, m=$5; specifiche da riconfermare al runtime|
|S10|[OANDA v20 primitives](https://developer.oanda.com/rest-live-v20/primitives-df/)|Metadata come minimumTradeSize e tradeUnitsPrecision; non promessa di apertura conto o API per entità italiana/indonesiana|
|S11|[Binance official spot API filters](https://github.com/binance/binance-spot-api-docs/blob/master/filters.md)|LOT_SIZE, min notional e price filters; doc tecnica esemplificativa, non raccomandazione o verifica eleggibilità Binance|
|S12|[Federal Reserve FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)|Calendario istituzionale programmato; distinguere meeting, announcement e press conference|
|S13|[BLS release calendar / Employment Situation](https://www.bls.gov/schedule/news_release/empsit.htm)|Fonte NFP/unemployment; archiviare snapshot storici as-of|
|S14|[BEA release schedule](https://www.bea.gov/news/schedule/)|GDP e Personal Income/Outlays/PCE; revisioni non utilizzabili retroattivamente|
|S15|Bailey et al., [The Probability of Backtest Overfitting](https://escholarship.org/uc/item/4w1110bb)|Motiva controllo selezione tra strategie; non misura l'overfitting di A1 senza dataset|
|S16|Bailey e López de Prado, [Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)|Correzioni selection bias/non-normalità; implementazione e assunzioni vanno validate indipendentemente|

## Distinzione origine / convenzione
FVG e MSS sono collegati al materiale originale reperito; la geometria a tre barre è anche esplicitamente fornita nel brief. Soglie 0,05/0,50 ATR, pivot 2+2, body 0,65, entry 50%, news 30 minuti, TTL, rank pool e test sono **P**, non attribuzioni a Huddleston. CHoCH/BOS e classificazioni internal/external hanno uso variabile: il glossario assegna significati locali. I blocchi/OTE/bias sono proxy quantitativi proposti; verificare eventuale fedeltà terminologica sul video originale prima di presentarli esternamente come “ICT originale”. Nessun materiale community viene usato come prova di rendimento.

## Giurisdizione: verificato e ancora aperto
Italia: verificare entità legale in registri autorizzati, servizi abilitati, appropriateness per prodotti complessi, condizioni CASP MiCA per crypto. FX retail “spot” può essere rolling spot/CFD: non presumere che sia cambio valuta deliverable. Leva, negative balance protection e margin close-out dipendono dal prodotto e dalle misure applicabili: non vengono inventati valori account-specific.

Indonesia: OJK è riferimento verificato per asset digitali; non estendere automaticamente quel regime a Forex/CFD o intermediari esteri. Richiedere classificazione del prodotto e conferma del regolatore/entità competente per lo specifico contratto. Passaporto italiano, prova indirizzo, residenza fiscale, TIN, fonte fondi e presenza fisica sono dati distinti; condizioni aggiuntive per non residenti/documenti locali da confermare con provider. Un VPN o un endpoint API funzionante non dimostra accesso consentito.

Nessun broker o exchange è stato verificato come effettivamente apribile da Simone. Il progetto procede in simulazione; l'eleggibilità reale resta un hard gate, non una supposizione. Prezzi/spread/fee attuali non sono disponibili e non sono sostituiti con numeri apparentemente reali.
