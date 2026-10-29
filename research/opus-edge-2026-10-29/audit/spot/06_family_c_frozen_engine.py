"""Audit 06 -- EXPLORATORY on already-observed data. Runs the FROZEN family-C simulate()
(research/strategy-discovery-2026/runner.py, unmodified, imported read-only) on hourly bars
loaded by a gap-tolerant scratch loader instead of the frozen cascading loader:
irregular-duration bars and missing hours are simply absent (NaN on the grid). Daily bars come
from the frozen load_manifest (they have no errors). Nothing is written in the project tree.
This shows what C would have reported had the loader not cascaded. Not a promotion test."""
import sys, csv, io, json, zipfile
from pathlib import Path
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT'); SD = ROOT / 'research/strategy-discovery-2026'
OUT = Path(__file__).resolve().parent / 'out'
sys.path.insert(0, str(SD))
import data as D, engine as E, runner as RN


def tolerant_hourly(symbol, lo='2019-12', hi='2024-12'):
    bars = []
    for mon in D.months(lo, hi):
        p = SD / 'data/1h' / symbol / f'{symbol}-1h-{mon}.zip'
        with zipfile.ZipFile(p) as z: content = z.read(z.namelist()[0]).decode()
        for row in csv.reader(io.StringIO(content)):
            try: bars.append(D.parse_row(row, int(mon[:4]), 3600, symbol))
            except ValueError: pass  # irregular bar => absent
    return bars


def main():
    data, quality = D.load_manifest('holdout')
    assert set(quality['errors']) == {'1h/BTCUSDT', '1h/ETHUSDT'}
    for s in ('BTCUSDT', 'ETHUSDT'): data[('1h', s)] = tolerant_hourly(s)
    costs = json.loads((SD / 'config.json').read_text())['costs']; rep = {}
    for segment in ('development', 'validation', 'holdout'):
        for cname, cc in costs.items():
            for variant, mode in (('primary', 'strategy'), ('neighbor', 'strategy'), ('primary', 'riskcap'), ('primary', 'bh_eth')):
                res = RN.simulate(data, segment, 'C', variant, E.Costs(**cc), mode)
                m = RN.compact(res)
                key = f'{segment}/{cname}/{variant}_{mode}'
                rep[key] = {k: m.get(k) for k in ('status', 'error', 'net_return', 'daily_sharpe_365', 'max_drawdown', 'order_count', 'roundtrip_count', 'roundtrip_profit_factor', 'fees', 'two_way_turnover', 'skipped_entries', 'average_exposure')}
                print(key, json.dumps(rep[key]), flush=True)
    (OUT / 'family-c-frozen-engine.json').write_text(json.dumps(rep, indent=1))


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True); main()
