# Round 2: fixed exploratory experiment, no new candidate promoted

All four preregistered variants and frozen benchmarks/costs/periods ran once after root release and independent blind review. H3 maker was excluded, not simulated. Every period was already observed: these results are exploratory, not independent out-of-sample confirmation. Old B and its prospective protocol remain unchanged.

- `protocol.json`, `config.json`, `freeze.json`: pre-results methods, eight sources, 986 inputs, 179 protected hashes.
- `results/results.json`, `assessment.json`: all135arm/period/cost outputs and frozen screen;135is not independent strategy-trial count.
- `compact-results.csv`, `summary.json`: exact tables, calendar/regime/concentration/cost details.
- `reproducibility.json`: **137JSON artifacts reproduced byte-identically**, including assessment, with no new methods/downloads.

## Controls, without market-data calculation

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q research/edge-discovery-round-2/test_round2.py
```

16synthetic tests passed. The initial RED was absent-module collection, not an old-runtime bug. One provisional receipt is preserved in `freeze-provisional.json`: the terminal test initially made its second target inactive, so the position correctly closed before the terminal boundary. Only that synthetic fixture and the guard rejecting failed pytest transcripts changed before final freeze. `synthetic-fixture-failure.txt` preserves the failed test. `pre_financial_amendment` has three metadata keys, not three amendments. No signal rule or market outcome was changed.

## Safe offline reproduction after immutable results exist

`runner.py run` deliberately refuses the existing results directory. Do not delete/overwrite it, rerun freeze or acquire data. The runner verifies original inputs by workspace-relative paths and imports only pinned pure accounting. Therefore use a fresh **minimal workspace mirror** inside this same isolated research directory. The tested procedure below copies bytes, never changes old files or starts their operational code. Choose a new destination if it already exists.

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
.venv/bin/python - <<'PY'
from pathlib import Path
import json,hashlib,shutil,subprocess,sys,os
root=Path.cwd();r=root/'research/edge-discovery-round-2'
f=json.loads((r/'freeze.json').read_text())
mirror=r/'offline-reproduction-fresh'/'workspace'
assert not mirror.exists(), 'Never overwrite previous evidence'
mirror.mkdir(parents=True)
for rel in set(f['inputs'])|set(f['protected']):
    p=Path(rel);assert not p.is_absolute() and '..' not in p.parts
    dest=mirror/p;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/p,dest)
mr=mirror/'research/edge-discovery-round-2';mr.mkdir(parents=True)
for name in list(f['sources'])+['freeze.json','release.json','tests-green.txt',
        'freeze-provisional.json','synthetic-fixture-failure.txt','tdd-red.txt']:
    shutil.copy2(r/name,mr/name)
env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONPATH']=str(mr)
with (mr/'run.log').open('w') as log:
    subprocess.run([sys.executable,str(mr/'runner.py'),'run'],cwd=mirror,env=env,
                   stdout=log,stderr=subprocess.STDOUT,check=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[p.relative_to(r) for p in (r/'results').glob('*.json')]+[Path('assessment.json')]
assert all(sha(r/p)==sha(mr/p) for p in paths)
assert all(sha(root/Path(p))==h for p,h in f['inputs'].items())
assert all(sha(root/Path(p))==h for p,h in f['protected'].items())
print(len(paths),'JSON artifacts match; original inputs/protected files unchanged')
PY
```

No downloader exists in this module; the frozen CLI denies socket connections. Reproduction repeats the same experiment for integrity, not another variant or a new significance test. Bootstrap remains seed20261028/10000/circular7and30dailyblocks, alpha.05/2 for two current primary families, conditional and exploratory only. Global historical search count is unknown.

## Interpretation limits

H1 uses DAILY negative-shock/low-volume features and hourly execution after a full1h/2h availability lag, NOT an hourly-shock or five-minute paper replication. H2 uses only low relative quote volume for selection; trade counts/taker flows are quality fields, not extra filters. Common risk volatility includes current closed feature return; signal baselines exclude it.

Synthetic spread/slippage/fees, continuous fractional quantity and candle-open availability are research models, not measured executable BBO, account tariffs or maker fills. The20%forecast-volatility cap is not a drawdown, daily-loss or exposure guarantee. H1's small average exposure does not prove hedging skill. Daily-PnL PF is not roundtrip PF; allocation order counts are not independent trades. Remove-best-days and gross-before-friction numbers are fixed-path accounting diagnostics, not executable counterfactual backtests.

Stop here: no retuning, new hypotheses, maker-fill assumptions or runtime activation follows these results. Rollback is removal of this new research directory only.
