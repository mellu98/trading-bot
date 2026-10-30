# ICT A1 — binance-BTCUSDT-binance-btcusdt-spot

**Verdetto: RESEARCH.** Evidenze insufficienti o criteri non soddisfatti. Nessun paper trading, nessun capitale.

Motivo: solo 1 trade nel periodo di sviluppo: campione insufficiente per qualsiasi giudizio.

## Cosa è stato testato

- Strategia A1-1.0 (sweep → MSS con displacement → FVG immediato, entry limit al 50% del FVG, stop oltre lo sweep, target sulla liquidità opposta, net RR ≥ 1.5), parametri del pacchetto invariati.
- Mercato: BTCUSDT su binance-spot, M5, sessione 07:00–11:00 New York, solo long.
- Dati: data.binance.vision (official Binance public data); 36 mesi completi (2023-10-01 → 2026-10-01); 1 segmenti continui, 0 barre mancanti.
- Costi base: fee 0.100% per lato, slippage 0.2 bp su stop/uscite a mercato; spread: assumed (fixed).
- Filtro news: not_applied (no point-in-time calendar supplied).
- Rischio per trade 0.25% del capitale, conto iniziale 500 USDT.

## Risultati (R = risultato netto / rischio stimato all'ingresso)

| Periodo | Trade | Win rate | R medio | CI95 R medio | p (R≤0) | PF | Max DD | Netto USDT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Sviluppo 2023-10-01→2025-10-01 | 1 | 0.00% | -1.000 | [-1.000; -1.000] | 1.000 | 0.00 | 0.25% | -1.25 |
| Sviluppo, costs_1.5x | 1 | 0.00% | -1.000 | [-1.000; -1.000] | 1.000 | 0.00 | 0.25% | -1.25 |
| Sviluppo, costs_2x | 1 | 0.00% | -1.000 | [-1.000; -1.000] | 1.000 | 0.00 | 0.25% | -1.25 |
| Sviluppo, slippage_3x | 1 | 0.00% | -1.000 | [-1.000; -1.000] | 1.000 | 0.00 | 0.25% | -1.25 |
| Sviluppo, limite ottimistico (solo diagnostica) | 1 | 0.00% | -1.000 | [-1.000; -1.000] | 1.000 | 0.00 | 0.25% | -1.25 |

Holdout: sealed — holdout non aperto (usa --unseal-holdout, una sola volta).

### Stabilità per fold (sviluppo)

| Fold | Trade | R medio | Netto |
|---|---:|---:|---:|
| 2024-10-01→2025-01-01 | 0 | n/d | 0.00 |
| 2025-01-01→2025-04-01 | 0 | n/d | 0.00 |
| 2025-04-01→2025-07-01 | 0 | n/d | 0.00 |
| 2025-07-01→2025-10-01 | 0 | n/d | 0.00 |

### Confronto con ingressi casuali abbinati

Stessa ora, direzione e geometria stop/target, ingresso casuale: R medio nullo -0.454 (5°–95° percentile -1.000…3.009) contro A1 -1.000; p che A1 non sia migliore = 0.726.

### Dettagli sviluppo

- Long/short: 1/0; uscite: {'STOP': 1}; barre ambigue (stop e target nella stessa barra): 0.
- Fee totali 0.63 USDT; fee burden n/d (fee / profitti lordi dei trade vincenti).
- Sharpe in eccesso su un tasso privo di rischio costante del 4% (approssimazione del T-bill): n/d; esposizione 0.00% del tempo.
- Giorni con trade 1 su 731; massima serie di perdite 1.
- Imbuto dei setup: SWEEP_CONFIRMED 1220, SKIP_SWEEP_INVALIDATED 839, SKIP_MSS_EXPIRED 226, SKIP_FVG_EXPIRED 41, SKIP_NO_TARGET 1, SKIP_ENTRY_OR_STOP 6, SKIP_NET_RR 18, SKIP_SHORT_UNSUPPORTED 12, SKIP_MINIMUM_SIZE 0, SKIP_SPREAD_TOO_HIGH 0, SKIP_SLIPPAGE 12, ENTER_LONG 1, ENTER_SHORT 0.
- Ordini cancellati: {}.
- Vista conto con le regole del pacchetto (stop al drawdown 8%): da 500 a 498.75 USDT con 1 trade; nessun arresto per drawdown.
- Robustezza ±20%: 4% dei vicini con R medio > 0.
- Holm sulla famiglia di 1 trial registrati: soglia 0.0500, non significativo.

## Limiti

- Barre OHLC: ordine intrabar sconosciuto, quindi stop prima del target (limite prudente); il limite ottimistico è solo diagnostica.
- Nessun fill parziale, coda o latenza reale: i risultati non possono qualificare il live (protocollo 07).
- Spread storico non disponibile: valore assunto. Per il protocollo l'esito massimo resta RESEARCH finché non si testa su bid/ask reali.
- Filtro news non applicato: manca un calendario storico point-in-time.
- Nessun numero qui è una previsione di guadagno futuro.

Config hash `3088a1ee71886ef8`, strategy hash `841a01f525ca80fc`, dati `cd1d4663abb0ca08`. Registro trial: `/Users/locoframe/Desktop/TRADING BOT-worktrees/ict-engine-a1/reports/ict/trials.json`.
