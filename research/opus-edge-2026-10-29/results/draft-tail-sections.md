## 7. Limiti statistici

- **Potenza.** Con rendimenti giornalieri iid (ipotesi ottimistica), per confermare con test unilaterale al 5% e potenza 80% uno Sharpe annuo di 0,5 servono ~26 anni; di 1,0 ~7 anni; di 2,0 ~2,4 anni (`research/opus-edge-2026-10-29/results/power.json`). Per una *differenza* di Sharpe di 0,36 fra due strategie correlate 0,8–0,9 (il caso B contro passivo) servono **38–72 anni**. Quasi tutti i test del progetto erano quindi destinati a "inconcludente" indipendentemente dalla verità.
- **Selezione.** Il progetto ha provato ≥20 configurazioni su storie sovrapposte, più le 4 di questa revisione. Con un anno di dati l'errore standard di uno Sharpe annualizzato è ~1: il migliore di 20 tentativi casuali mostrerebbe in media ~1,9. Il Deflated Sharpe globale resta non stimabile senza inventario completo dei tentativi.
- **Contaminazione.** Nessun periodo è un holdout vero: il funding è pubblico; il 2006–2026 azionario è stato studiato da altri; il ricercatore conosce la storia dei mercati. E1/E2 sono valutazioni esplorative con regole congelate, non conferme.
- **Esecuzione.** Niente bid/ask storico, niente sequenza intrabar, mark price usato solo come diagnostica; T-bill a sconto/360 leggermente prudente a favore della carry.
- **Rischi non modellati in E1:** default o blocco dell'exchange, depeg USDT, auto-deleveraging (in un crollo lo short in profitto può essere chiuso d'ufficio lasciando lo spot scoperto), errori operativi, fiscalità.

## 8. Requisiti tecnici ed economici (se mai si riprendesse)

| | E1 carry funding | E2 turn-of-month |
|---|---|---|
| Strumenti | Conto spot + futures USDⓈ-M (derivati: **non autorizzati**) | ETF UCITS S&P 500 o micro future MES pienamente collateralizzato |
| Capitale minimo | Poche centinaia di USDT tecnicamente; utile solo con capitale per cui lo 0,1–0,4% annuo conta | Basso; costi fissi di commissione pesano sotto ~10.000 € |
| Infrastruttura | Monitoraggio margine 24/7, trasferimenti fra wallet, gestione ADL e liquidazioni, riconciliazione funding | 24 ordini l'anno, eseguibili anche a mano |
| Rendimento atteso dalle evidenze | ≈ T-bill (eccesso 2024–2026 da −0,5% a +0,4% annuo secondo i costi) | ≈ esposizione proporzionale al tempo investito; nessun alpha dal 2006 |
| Rischi principali | Controparte exchange, stablecoin, liquidazione, ADL | Crollo in un giorno TOM; costi fiscali e di commissione per un retail italiano |

## 9. Evidenze a favore e contro

**A favore (verificate):** il funding BTC/ETH è stato positivo in media in ogni anno 2020–2026; nel 2020–2021 la carry ha reso molto più del T-bill con volatilità del 4–5%; il TOM ha concentrato il 100% del premio azionario 1926–1987 e il 79% nel 1988–2005.

**Contro (verificate):** dal 2024 la carry rende quanto il T-bill e dal 2025 meno; la versione condizionata peggiora sempre per turnover; il TOM non ha alpha dal 2006 (t = 0,20); tutte le strategie di prezzo del progetto risultano senza edge o antieconomiche; B non batte il proprio passivo sull'intera storia e nel 2023 rende meno del T-bill.

## 10. Prossimo esperimento realmente informativo

Non un altro backtest su BTC/ETH/MNQ/MES: sarebbe di nuovo esplorativo, contaminato e senza potenza. Due possibilità, entrambe da autorizzare esplicitamente prima di iniziare:

1. **Raccomandata — decisione di governance, non esperimento:** chiudere la ricerca di edge con questo approccio e documentarlo ai soci; tenere l'infrastruttura archiviata. Separare la domanda "vogliamo esposizione cripto/azionaria?" (asset allocation passiva, con rischio dichiarato) dalla domanda "abbiamo un vantaggio?" (oggi: no).
2. **Solo se i soci vogliono continuare la ricerca: un unico test "di uccisione", gratuito e di poche ore.** Verificare la finestra di Etula et al. (2020, "Dash for Cash"), il cui campione finisce nel dicembre 2013, sul periodo **2014-01 → 2026-09** con i dati French già scaricati: acquisto alla chiusura di T−4, vendita alla chiusura di T+3, T-bill negli altri giorni; più, con correzione di Bonferroni, la variante che sposta l'ingresso secondo il ciclo di regolamento (T+3 fino a settembre 2017, T+2 fino a maggio 2024, poi T+1; date da verificare prima del congelamento). Criteri e costi come E2, scritti prima. È il test più informativo per costo perché ha un meccanismo causale pubblicato, un periodo successivo al campione degli autori e dati ufficiali; se fallisce, la famiglia dei flussi di calendario è chiusa. Avvertenze: priorità bassa (la versione canonica è morta e i dati dei practitioner indicano indebolimento), conosco già l'esito aggregato dei 4 giorni canonici T…T+3 in quel periodo (restano non osservati i 3 giorni T−3…T−1), e anche un esito positivo resterebbe esplorativo con rendimento assoluto inferiore al buy & hold. **Non l'ho eseguito**: avrei superato il limite di due candidate e il budget di varianti di E2.

Il premio per il rischio di volatilità resta l'unica famiglia con premio robusto non testata, ma richiede derivati, dati di opzioni storici non presenti nel progetto e gestione del rischio di rovina: oggi non giustifica investimenti operativi.

Il protocollo prospettico già preparato per B (12 mesi) **non** è consigliato come strumento decisionale: con potenza dell'8–14% finirebbe quasi certamente "inconcludente".
