# ICT A1 — capital-US100-capital-us100-cfd

**Verdetto: RESEARCH.** Evidenze insufficienti o criteri non soddisfatti. Nessun paper trading, nessun capitale.

Motivo: solo 1 trade nel periodo di sviluppo: campione insufficiente per qualsiasi giudizio.

## Cosa è stato testato

- Strategia A1-1.0 (sweep → MSS con displacement → FVG immediato, entry limit al 50% del FVG, stop oltre lo sweep, target sulla liquidità opposta, net RR ≥ 1.5), parametri del pacchetto invariati.
- Mercato: US100 su capital-demo-cfd, M5, sessione 07:00–11:00 New York, long e short.
- Dati: Capital.com DEMO REST /prices (native bid/ask), read-only; 33 mesi completi (2024-01-01 → 2026-10-01); 922 segmenti continui, 92745 barre mancanti.
- Costi base: fee 0.000% per lato, slippage 0.5 bp su stop/uscite a mercato; spread: native_bid_ask.
- Filtro news: not_applied (no point-in-time calendar supplied).
- Rischio per trade 0.25% del capitale, conto iniziale 5000 USD.

## Risultati (R = risultato netto / rischio stimato all'ingresso)

| Periodo | Trade | Win rate | R medio | CI95 R medio | p (R≤0) | PF | Max DD | Netto USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Sviluppo 2024-01-01→2025-10-01 | 1 | 0.00% | -1.000 | [-1.000; -1.000] | 1.000 | 0.00 | 0.25% | -12.48 |
| Sviluppo, costs_1.5x | 0 | n/d | n/d | [n/d; n/d] | n/d | n/d | 0.00% | 0.00 |
| Sviluppo, costs_2x | 0 | n/d | n/d | [n/d; n/d] | n/d | n/d | 0.00% | 0.00 |
| Sviluppo, slippage_3x | 0 | n/d | n/d | [n/d; n/d] | n/d | n/d | 0.00% | 0.00 |
| Sviluppo, limite ottimistico (solo diagnostica) | 1 | 0.00% | -1.000 | [-1.000; -1.000] | 1.000 | 0.00 | 0.25% | -12.48 |

Holdout: sealed — holdout non aperto (usa --unseal-holdout, una sola volta).

### Stabilità per fold (sviluppo)

| Fold | Trade | R medio | Netto |
|---|---:|---:|---:|
| 2025-01-01→2025-04-01 | 0 | n/d | 0.00 |
| 2025-04-01→2025-07-01 | 0 | n/d | 0.00 |
| 2025-07-01→2025-10-01 | 0 | n/d | 0.00 |

### Confronto con ingressi casuali abbinati

Stessa ora, direzione e geometria stop/target, ingresso casuale: R medio nullo -0.184 (5°–95° percentile -1.000…2.243) contro A1 -1.000; p che A1 non sia migliore = 0.507.

### Dettagli sviluppo

- Long/short: 0/1; uscite: {'STOP': 1}; barre ambigue (stop e target nella stessa barra): 0.
- Fee totali 0.00 USD; fee burden n/d (fee / profitti lordi dei trade vincenti).
- Sharpe in eccesso su un tasso privo di rischio costante del 4% (approssimazione del T-bill): n/d; esposizione 0.00% del tempo.
- Giorni con trade 1 su 639; massima serie di perdite 1.
- Imbuto dei setup: SWEEP_CONFIRMED 390, SKIP_SWEEP_INVALIDATED 245, SKIP_MSS_EXPIRED 52, SKIP_FVG_EXPIRED 15, SKIP_NO_TARGET 5, SKIP_ENTRY_OR_STOP 2, SKIP_NET_RR 4, SKIP_SHORT_UNSUPPORTED 0, SKIP_MINIMUM_SIZE 0, SKIP_SPREAD_TOO_HIGH 12182, SKIP_SLIPPAGE 1221, ENTER_LONG 0, ENTER_SHORT 1.
- Ordini cancellati: {}.
- Vista conto con le regole del pacchetto (stop al drawdown 8%): da 5000 a 4987.52 USD con 1 trade; nessun arresto per drawdown.
- Robustezza ±20%: 0% dei vicini con R medio > 0.
- Holm sulla famiglia di 1 trial registrati: soglia 0.0500, non significativo.

## Limiti

- Barre OHLC: ordine intrabar sconosciuto, quindi stop prima del target (limite prudente); il limite ottimistico è solo diagnostica.
- Nessun fill parziale, coda o latenza reale: i risultati non possono qualificare il live (protocollo 07).
- Filtro news non applicato: manca un calendario storico point-in-time.
- Nessun numero qui è una previsione di guadagno futuro.

Config hash `766297791d1fbd71`, strategy hash `841a01f525ca80fc`, dati `979c74ecaa4dedf6`. Registro trial: `/Users/locoframe/Desktop/TRADING BOT-worktrees/ict-engine-a1/reports/ict/trials.json`.
