# Fixed three-family crypto research

Isolated research only. No operational imports, accounts, exchange order endpoints, services or old-file edits. Root owns `reports/STRATEGY-RESEARCH-2026.md`. No financial results exist until the root authorizes the data-bound release.

## Reproduce the controls

From the workspace root:

```sh
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python -m pytest -q research/strategy-discovery-2026/test_engine.py
```

23 focused synthetic tests passed before first new archive access. Initial RED was missing-module collection failure, not a claimed behavioral defect repair. A pre-data blind-review fix guards an incomplete BTC comparator; its earlier exact source receipt is retained as `source-freeze-v1.json`. Final active code/config/protocol/universe receipt is `source-freeze.json`; do not overwrite it.

## Data stages

```sh
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/data.py acquire --phase development-validation
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/data.py quality --phase development-validation
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/data.py freeze-inputs --phase development-validation
```

Acquisition never overwrites an existing manifest. Cache retains original ZIP/CHECKSUM bytes and request receipts. Quality examines timestamps/counts/calendar boundaries/OHLC validity and hashes, not strategy returns. Known BCH prelisting September/October2019 is not requested. Whole partial listing day28November2019 is excluded from completed-day eligibility. A/B use daily bars; C uses BTC/ETH hourly bars. No historical1m/universe-wide download.

## Financial release

After independent blind review and input freeze, root must create `financial-release.json` containing:

```json
{
  "source_freeze_sha256": "SHA256 of source-freeze.json",
  "data_freeze_sha256": "SHA256 of data-freeze-development-validation.json",
  "authorized_by": "Root after independent blind review; no strategy retuning"
}
```

Then exactly one immutable run:

```sh
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/runner.py development-validation
```

This produces `results-development-validation/`, refuses network, verifies frozen sources/inputs and refuses an existing output directory. It runs all3families, both predeclared primary/neighbor configurations,3cost scenarios and frozen benchmarks without selection/retuning. The six variants are correlated, not six independent discoveries. No global DSR can be computed from unknown prior trial history.

## Locked holdout

Nothing in the commands above acquires or reads2024holdout prices. Root must first create `holdout-release.json` binding the same `source_freeze_sha256` to authorize the99holdout archive pairs and blind quality:

```sh
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/data.py acquire --phase holdout
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/data.py quality --phase holdout
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/data.py freeze-inputs --phase holdout
```

A separate root `financial-holdout-release.json` with source hash plus `data-freeze-holdout.json` hash is required before:

```sh
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/runner.py holdout
PYTHONPATH=research/strategy-discovery-2026 .venv/bin/python research/strategy-discovery-2026/assess.py
```

No change based on development/validation results is permitted. Holdout is Jan1–Dec1 2024 UTC half-open; Dec2024was already observed and is excluded. Both sets remain historical, not prospective future tests.

## Interpretation boundaries

- Capital1000USDT, no leverage/short, at most100%long; continuous fractional research quantities, not exchange-grid certification. Old100USDT entrycap/1USDT stoprisk are NOT inherited.
- Daily features have a full completed-day availability lag. C has a full1h/2h delay, not same-boundary fills. Historical open/BBO/slippage remain modeled rather than observed executable quotes.
- Cash/fees are self-financing; close marks reserve hypothetical liquidation cost. Benchmark/candidate valuation is identical. C sells/reopens incur both costs.
- A exposure-matched comparator matches **known requested target exposure**, not exactly realized exposure after costs; it is an incremental-ranking diagnostic, not a new independent strategy.
- Missing held prices or required-source gaps yield `INCOMPLETE_NO_PROMOTION`, not executable forward-filled prices or retrospective last-good-bar liquidation. A-only source defects do not block intact B/C.
- PF uses DAILY PnL for A/B/all primary summaries; C has additional actual roundtrip PF. Daily Sharpe uses sqrt365; hourlyC sqrt8760is secondary. Zero-denominator statistics are null, never infinite wins.
- Conditional paired circular7/30day bootstrap with10000replicates/seed20261028is not future-profit probability or a correction for unknown earlier project searches.

Rollback: remove only this isolated research directory. No runtime behavior or archived prior configuration depends on it.

## Completed-run reproduction without overwriting evidence

The completed run now has immutable result directories. A second run in-place correctly refuses them. The verified method is a fresh **copy** under this same isolated research root, using the same cached originals, receipts, sources and releases. Never rerun acquisition or delete original results. This procedure reproduced **219 JSON artifacts byte-for-byte**, including both phase summaries and assessment; see `reproducibility.json`.

To create another fresh offline copy (the destination must not exist):

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
.venv/bin/python - <<'PY'
from pathlib import Path
import json,shutil
r=Path('research/strategy-discovery-2026').resolve()
d=r/'offline-reproduction-fresh'
assert not d.exists(), 'Choose a new destination; never overwrite prior evidence'
d.mkdir()
names=list(json.loads((r/'source-freeze.json').read_text())['sources'])
names += ['source-freeze.json','financial-release.json','financial-holdout-release.json',
          'holdout-release.json','data-freeze-development-validation.json','data-freeze-holdout.json',
          'acquisition-development-validation.json','acquisition-holdout.json']
for name in names:shutil.copy2(r/name,d/name)
shutil.copytree(r/'data',d/'data')
PY
REPLAY_DIR="$PWD/research/strategy-discovery-2026/offline-reproduction-fresh"
PYTHONPATH="$REPLAY_DIR" .venv/bin/python "$REPLAY_DIR/runner.py" development-validation
PYTHONPATH="$REPLAY_DIR" .venv/bin/python "$REPLAY_DIR/runner.py" holdout
PYTHONPATH="$REPLAY_DIR" .venv/bin/python "$REPLAY_DIR/assess.py"
.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib
r=Path('research/strategy-discovery-2026');d=r/'offline-reproduction-fresh'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[p.relative_to(r) for folder in ('results-development-validation','results-holdout')
       for p in (r/folder).glob('*.json')]+[Path('assessment.json')]
assert all(sha(r/p)==sha(d/p) for p in paths)
print(len(paths),'JSON artifacts match exactly')
PY
```

### Important data limitation found, not repaired

All559officialZIP/CHECKSUM pairs matched. Seven daily series were valid; BCH's28Nov2019listing day remained excluded from full-history eligibility. Historic BTC/ETH hourly files each contain8shortbars and15gaps, including a real24Mar2023defect: C's development/validation is incomplete, not economically negative. The frozen loader also uses an all-history prerequisite which cascades after its first rejected month. **Raw2024hourly data actually has8040bars per asset with zero shortbars/gaps**; C2024is uncomputed under that frozen prerequisite, NOT evidence of2024archive gaps. Root explicitly retained the original scope/code rather than starting a repair/retuning cycle. C cannot meet its validation gate in this experiment.

`compact-results.csv` has216arm/period/cost rows, including blocked rows. This is NOT216independent strategy trials: the design has3primary families+3robustness neighbors; benchmarks/costs/segments are not separate discoveries. `primary-summary.json` contains exact compact metrics, yearly/regime PnL and concentration diagnostics. `assessment.json` applies the predeclared conjunction: no family is promoted; B's favorable2024point estimates still fail the paired adjusted uncertainty gates.
