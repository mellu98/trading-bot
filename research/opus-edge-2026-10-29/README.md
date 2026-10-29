# Opus edge research — 29 ottobre 2026

Cartella isolata, solo offline. Non modifica file esistenti del progetto, non avvia servizi, non invia ordini.

## Contenuto

- `src/acquire.py` — download degli archivi pubblici ufficiali (Binance public data con verifica `.CHECKSUM`, Kenneth French daily factors, FRED DTB3) con ricevute UTC in `cache/receipts-*.json`. Non sovrascrive file esistenti.
- `src/quality.py` — controlli strutturali (unità ms/µs, continuità oraria, timestamp funding) senza statistiche economiche.
- `src/carry.py`, `src/run_e1.py` — E1, carry delta-neutral funding (spot long + perpetual short), regole in `protocol/E1-funding-carry.json`.
- `src/tom.py` — E2, turn-of-the-month sul mercato azionario USA, regole in `protocol/E2-turn-of-month.json`.
- `src/power.py` — potenza statistica dei test sullo Sharpe.
- `src/test_carry.py` — test sintetici del simulatore e delle statistiche.
- `src/freeze.py` — ricevuta append-only (`protocol/freeze-receipts.json`) con SHA256 di protocollo e sorgenti, scritta prima dei risultati economici.

## Riproduzione (offline, dopo il download)

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
PY=.venv/bin/python; R=research/opus-edge-2026-10-29
PYTHONDONTWRITEBYTECODE=1 $PY -I $R/src/test_carry.py
PYTHONDONTWRITEBYTECODE=1 $PY -I $R/src/quality.py $R
# i runner rifiutano di sovrascrivere risultati esistenti: per rifarli usare una copia della cartella
PYTHONDONTWRITEBYTECODE=1 $PY -I $R/src/run_e1.py $R D_exploratory
PYTHONDONTWRITEBYTECODE=1 $PY -I $R/src/run_e1.py $R E_segregated_evaluation
PYTHONDONTWRITEBYTECODE=1 $PY -I $R/src/run_e1.py $R descriptives
PYTHONDONTWRITEBYTECODE=1 $PY -I $R/src/tom.py $R
PYTHONDONTWRITEBYTECODE=1 $PY -I $R/src/power.py $R
```

Il download (`src/acquire.py <cache> binance|french|fred`) richiede rete pubblica; ogni ZIP Binance è verificato contro il checksum ufficiale.

## Esiti (dettagli in `reports/OPUS-EDGE-RESEARCH.md`)

- **E1 carry funding BTC/ETH** (protocollo SHA256 `4568eb5d…f6d6`): 2024-01 → 2026-09 sempre attiva +4,60%/anno contro T-bill 4,44%; criteri c1, c2, c5 falliti. Non promossa.
- **E2 turn-of-the-month** (protocollo SHA256 `b14182f4…b5e6`): differenza TOM−altri +0,8 bp/giorno (t 0,20) nel 2006–2026; tutti i criteri falliti. Non promossa.
- Valutazione meccanica dei criteri: `results/assessment.json`; tabelle: `results/tables.md`; potenza: `results/power.json`; diagnostica mark price: `results/E1/diag-markprice.json`.

## Altri contenuti

- `audit/spot/`, `audit/futures-timestral/`, `audit/opus/`: report, script e output degli audit indipendenti (eseguibili in sola lettura; i comandi sono in fondo a ciascun report).
- `results/draft-*.md` + `src/assemble_report.py`: sezioni da cui è assemblato `reports/OPUS-EDGE-RESEARCH.md`.
- `results/MANIFEST.sha256`, `protocol/SOURCES.sha256`: hash di risultati e sorgenti al momento della consegna.
