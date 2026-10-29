# Round2 — fattibilità scientifica prima del backtest

**H1 e H2 sono falsificabili con i dati disponibili, ma soltanto come adattamenti esplorativi. H3 non è valutabile economicamente con OHLC e bookTicker: non implementarla.** Nessun nuovo risultato finanziario è stato consultato da questo agente. B rimane congelata; il protocollo del coordinatore è l'unica autorità esecutiva.

## Le cinque fonti richieste

| Fonte primaria verificata | Stato e accesso reale | Cosa possiamo trasferire |
|---|---|---|
| [Farag–Luo–Yarovaya–Zięba,2025](https://doi.org/10.1016/j.jbankfin.2025.107411), [PDF istituzionale](https://pure-oai.bham.ac.uk/ws/portalfiles/portal/264447617/Farag2022Returns.pdf) | Peer-reviewed, JBF175; versione pubblicata19p, sezioni dati/metodo consultate. | Premio reversal a **5minuti**, non una strategia daily. Long-short e forward-fill richiedono cautela; nessuna dimostrazione di fill maker personali. |
| [Bianchi–Babiak–Dickerson,2022](https://www.sciencedirect.com/science/article/pii/S0378426622001418), [WP Riksbank413](https://www.riksbank.se/globalassets/media/rapporter/working-papers/2022/no.-413-trading-volume-and-liquidity-provision-in-cryptocurreny-markets.pdf) | Articolo peer-reviewed; consultati preview publisher e WP48p completo, non garantita identità di ogni dettaglio finale. | **Reversal giornaliero con volume relativo basso**, non shock orario ad alto volume. Assunzioni di esecuzione semplificate, non ricetta realtime. |
| [Wang–Pang,SSRN7556359](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7556359) | Working paper3ottobre2026, pubblicato6ottobre; solo metadata/abstract primari indicizzati, PDF bloccato. | Segnali e prevedibilità variano nel tempo. Non sono verificabili da quell'abstract le formule, i segni e i costi di un predittore preciso. |
| [Galati,2024](https://doi.org/10.1016/j.jbankfin.2024.107222), [PDF istituzionale](https://cris.unibo.it/bitstream/11585/970807/1/Galati2024_JBF.pdf) | Peer-reviewed, JBF165; versione pubblicata24p consultata nelle sezioni pertinenti. | Il caso Binance senza fee mostra che maggiore attività non equivale necessariamente a migliore liquidità o minori frizioni. |
| [Han–Kang–Ryu,RAPS2026](https://academic.oup.com/raps/advance-article-abstract/doi/10.1093/rapstu/raag011/8914819) | Manoscritto accettato peer-reviewed, online13ottobre2026; solo abstract ufficiale, non testo a pagamento. | Media aritmetica significativa e profitto composto finanziabile non sono equivalenti. Non è conferma automatica di B o delle nuove ipotesi. |

I cinque identificativi corrispondono ai titoli attesi. Errori403 o redirect non significano che il lavoro non esista. Le versioni preliminari non vanno mescolate con quelle pubblicate: nel caso Farag differiscono anche alcune conclusioni geografiche dell'abstract.

## Scelte del coordinatore congelate prima degli esiti

**H1 — pressione temporanea con partecipazione ridotta, BTC/ETH.** Giorno completato: rendimento log negativo e z-score inferiore a−1 rispetto ai30rendimenti precedenti, corrente escluso; `log(quoteVolume corrente / media aritmetica dei30giorni precedenti)<0`. Ogni asset qualificato riceve una sleeve da50%, residuo cash; cap comune di volatilità20% annuo, stimato causalmente su30giorni. Ribilanciamento giornaliero mediante delta netti e **un'ora intera** di disponibilità: apertura nativa01UTC. Unico vicino: due ore/02UTC. Sviluppo2022 e stress gennaio–novembre2024 per qualità timestamp verificata prima dei risultati, senza riparare il2023 difettoso.

È un adattamento daily ispirato a Bianchi, **non replica dei5minuti Farag**. BTC/ETH liquidi hanno supporto economico debole nella fonte. Soglia1sigma, selezione dei due asset, vol-cap e ritardo sono scelte dichiarate dal coordinatore, non parametri “dimostrati” dagli articoli né selezionati dai rendimenti.

**H2 — volume relativo come unico predittore.** Stesso log-rapporto alla media aritmetica30giorni, sette asset della coorte storica2019: i due valori più bassi sotto zero, sleeve50%, senza filtro sul rendimento. Stesso cap comune20%; ingresso dopo **un giorno intero** di disponibilità, vicino dopo due giorni. Nessuna variante60giorni né sostituzione con trade-count, taker-flow o Amihud. Supporto debole e dipendente dai controlli: non è replica dei segnali Wang–Pang non ricostruibili dall'abstract.

Massimo **quattro configurazioni**. Costi per lato fee/slippage e spread intero: base10/1/2bp, avverso15/5/10, severo20/10/20. Senza quote storiche, spread e slippage sono scenari, non fill misurati. Il protocollo eseguibile del coordinatore prevale su questo riepilogo; nessun risultato economico è stato letto per modificarlo.

## Controevidenze e decisione sui dati

La [replica indipendente Han,SSRN7624971](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7624971), pubblicata17ottobre2026, segnala inversioni e instabilità dei premi volume/volatilità. È **working paper, abstract soltanto**, non una nostra riproduzione. La [ricerca peer-reviewed Brauneis e altri2021](https://www.sciencedirect.com/science/article/pii/S0378426620303022) distingue utilità delle proxy di liquidità da misure reali: Amihud/OHLC non ricostruiscono la coda.

**H3 esclusa dal backtest:** mancano sequenza storica profonda degli ordini, priorità, cancellazioni e fill condizionati. Una candela che tocca il limite non dimostra acquisto; anche la profondità aggregata richiederebbe assunzioni sulla coda. I brevi capture recenti non sostituiscono uno storico multi-regime. Nessuna nuova infrastruttura è giustificata in questa campagna.

Tutto lo storico già utilizzato resta **esplorativo**, compreso il precedente holdout2024. Rendimenti netti, NAV finanziabile, costi avversi, concentrazione, benchmark comparabili e dipendenza statistica determinano l'esito; non il migliore numero fra poche configurazioni. Dopo H1/H2 e la sola fattibilità H3, arrestare la ricerca prevista.
