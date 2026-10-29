"""Audit 07: reproduce Edge Discovery Round 2 H1/H2 result JSONs byte-for-byte with the frozen
pure simulate() (runner.run/freeze NOT called), plus a no-look-ahead perturbation check of the
H1/H2 feature functions. Writes only to scratch/out."""
import sys, json
from pathlib import Path
import numpy as np
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT'); ED = ROOT / 'research/edge-discovery-round-2'
OUT = Path(__file__).resolve().parent / 'out'
sys.path.insert(0, str(ED))
import data as D, signals as SG, runner as RN
from reuse import Costs


def dumps(x): return json.dumps(x, indent=2, sort_keys=True, allow_nan=False) + '\n'


def lookahead_probe(cache):
    """Features at index j must not change when every daily value after j is replaced by garbage."""
    bad = 0; checked = 0
    for family, symbols in (('H1', D.SYMBOLS[:2]), ('H2', D.SYMBOLS)):
        g = D.daily_grid(cache, symbols); fn = SG.h1_features if family == 'H1' else SG.h2_features
        for j in range(40, len(g['times']) - 1, 7):
            a = fn(g['close'], g['quote'], g['full'], j)
            c2 = g['close'].copy(); q2 = g['quote'].copy(); c2[j + 1:] = 1e9; q2[j + 1:] = 1e-3
            b = fn(c2, q2, g['full'], j)
            for k in a:
                if isinstance(a[k], np.ndarray) and not np.array_equal(a[k], b[k], equal_nan=True): bad += 1
            checked += 1
    return {'feature_dates_checked': checked, 'differences': bad}


def main():
    cache, quality = D.read_cache(); config = D.load(ED / 'config.json'); rep = {'byte_exact': 0, 'mismatch': []}
    saved_all = D.load(ED / 'results/results.json')['results']
    for family, segments in RN.SEGMENTS.items():
        for segment in segments:
            for scenario, cc in config['costs'].items():
                for variant in ('primary', 'neighbor'):
                    modes = ['strategy', 'riskcap', 'matched', 'uncapped', 'fixed_cohort', 'bh_btc', 'bh_eth', 'cash'] if variant == 'primary' else ['strategy']
                    for mode in modes:
                        res = RN.simulate(cache, family, segment, variant, Costs(**cc), mode)
                        f = ED / 'results' / f'{family}-{segment}-{scenario}-{variant}_{mode}.json'
                        if dumps(RN.clean(res)) == f.read_text(): rep['byte_exact'] += 1
                        else: rep['mismatch'].append(f.name)
            p = D.load(ED / 'results' / f'{family}-{segment}-base-primary_strategy.json')['metrics']
            c = D.load(ED / 'results' / f'{family}-{segment}-base-primary_{"riskcap" if family == "H1" else "matched"}.json')['metrics']
            inf = SG.paired_bootstrap(p['daily_returns'], c['daily_returns'], 'sharpe_difference' if family == 'H1' else 'mean_excess')
            rep.setdefault('inference', {})[f'{family}/{segment}'] = {'blocks': RN.clean(inf['blocks']), 'equal_saved': RN.clean(inf) == saved_all[family][segment]['base'].get('inference')}
            print(family, segment, rep['byte_exact'], len(rep['mismatch']), flush=True)
    rep['lookahead_probe'] = lookahead_probe(cache)
    (OUT / 'edge-r2-repro.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != 'inference'}, indent=1)); print(json.dumps(rep['inference'], indent=1)[:3000])


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True); main()
