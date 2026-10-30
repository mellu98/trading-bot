# ICT A1 — risultati del run di Francesco (30/10/2026)

Run di `run-ict.sh` sul branch `ict-engine-a1` (commit `17d2232`) con i parametri del pacchetto invariati. Gli holdout non sono stati aperti: sono ancora sigillati.

## File in questa cartella

| File | Contenuto |
|---|---|
| `REPORT-BTCUSDT-binance.md` | `./run-ict.sh quickstart`: BTCUSDT spot, dati pubblici Binance, 36 mesi |
| `REPORT-US100-capital.md` | `./run-ict.sh run --source capital --epic US100 --robustness`: conto DEMO Capital.com, 33 mesi |
| `data_capital-fixes.patch` | 3 correzioni a `src/ict_engine/data_capital.py`, senza le quali il download di US100 non si completa |

I due report sono copiati senza modifiche da `reports/ict/<label>/REPORT.md`. I dati scaricati non sono nel repo (`data/` è in `.gitignore`).

## Risultati

| Mercato | Periodo di sviluppo | Trade | Esito | Verdetto |
|---|---|---:|---|---|
| BTCUSDT, Binance spot | 2023-10 → 2025-09 (24 mesi) | 1 | long, stop, −1R | RESEARCH |
| US100, Capital.com DEMO | 2024-01 → 2025-09 (21 mesi) | 1 | short, stop, −1R | RESEARCH |

- **BTCUSDT:** 1.220 sweep confermati, 1 solo ingresso. La maggior parte degli sweep si invalida (839) o non arriva in tempo alla MSS (226). Degli scarti successivi, 18 sono per RR netto < 1,5 con fee 0,10% per lato e 12 perché short: il profilo Binance è solo long.
- **US100:** 390 sweep confermati, 1 solo ingresso. Il filtro spread ≤ 0,1 ATR blocca circa il 58% della finestra 07:00–11:00 NY, quasi tutto il pre-market (12.182 scarti `SKIP_SPREAD_TOO_HIGH`), e lo slippage ne aggiunge altri 1.221.
- **Robustezza ±20%:** 4% dei vicini con R medio > 0 su BTCUSDT, 0% su US100.
- Con circa un trade ogni due anni, il gate del paper trading (≥ 200 trade fuori campione) non è raggiungibile.

## Le 3 correzioni al download di Capital.com

1. **Finestra da 999 intervalli invece di 1000.** `GET /prices` conta `from` e `to` come inclusi: 1000 passi danno 1001 barre e la risposta è `400 error.invalid.max.daterange`.
2. **Barre con bid/ask incrociati in quarantena.** 145 barre su 204.614 (0,07%) facevano fallire `_parse` e fermavano il download. Ora vengono saltate, mai corrette, e contate nel manifest (`quarantined_bars`).
3. **Retry sulle GET.** Un `CapitalError('transport_unknown')` arrivato dopo circa due anni di storico faceva perdere tutto il download. Ora la GET, che è idempotente, viene ripetuta fino a 3 volte con attesa crescente.

Lo storico 5m di US100 su Capital.com parte da gennaio 2024: per le date precedenti l'API risponde `404 error.prices.not-found`.

Per applicare la patch, dalla radice del repo sul branch `ict-engine-a1`:

```bash
git fetch origin
git show origin/ict-engine-a1-risultati:reports/ict/risultati-francesco-2026-10-30/data_capital-fixes.patch | git apply
./run-ict.sh selftest
```

Con la patch applicata il selftest passa 36 test su 36.

## Da correggere prima di aprire un holdout

Il sigillo dell'holdout è legato alla label, non al dataset. `check_or_write_receipt` (`src/ict_engine/protocol.py`) scrive `holdout-receipt.json` nella cartella `reports/ict/<label>/`, e la label (`src/ict_engine/cli.py:48`) cambia con `--label` o con qualsiasi `--set`. Con una label diversa lo stesso holdout si può quindi aprire di nuovo. La ricevuta andrebbe legata al dataset (hash dei dati + finestra di holdout) in un registro unico, come `trials.json`.

## Identificativi

| Run | Config | Strategia | Dati |
|---|---|---|---|
| BTCUSDT | `3088a1ee71886ef8` | `841a01f525ca80fc` | `cd1d4663abb0ca08` |
| US100 | `766297791d1fbd71` | `841a01f525ca80fc` | `979c74ecaa4dedf6` |

Il registro `trials.json` del run contiene 2 trial di sviluppo, uno per dataset.
