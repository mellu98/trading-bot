"""Audit 04: reproduce Strategy Discovery 2026 A/B ledgers byte-for-byte with the frozen
pure functions (runner.simulate is side-effect free; runner.run is NOT called), recompute
paired bootstrap, and run read-only diagnostics. Writes only to scratch/out."""
import sys, json, hashlib
from pathlib import Path
import numpy as np
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT'); SD = ROOT / 'research/strategy-discovery-2026'
OUT = Path(__file__).resolve().parent / 'out'
sys.path.insert(0, str(SD))
import data as D, engine as E, runner as RN


def dumps(x): return json.dumps(x, indent=2, sort_keys=True, allow_nan=False) + '\n'


def main():
    costs = json.loads((SD / 'config.json').read_text())['costs']
    rep = {'byte_exact': [], 'mismatch': []}
    for phase, segments in (('development-validation', ['development', 'validation']), ('holdout', ['holdout'])):
        data, quality = D.load_manifest(phase)
        folder = SD / ('results-' + phase)
        for segment in segments:
            for family in ('A', 'B'):
                modes = ['strategy', 'riskcap', 'uncapped', 'bh_btc', 'bh_eth', 'cash'] + (['matched', 'fixed_cohort'] if family == 'A' else ['matched'])
                for cname, cc in costs.items():
                    for variant in ('primary', 'neighbor'):
                        for mode in (modes if variant == 'primary' else ['strategy']):
                            res = RN.simulate(data, segment, family, variant, E.Costs(**cc), mode)
                            f = folder / f'{segment}-{family}-{cname}-{variant}_{mode}.json'
                            same = dumps(res) == f.read_text()
                            (rep['byte_exact'] if same else rep['mismatch']).append(f.name)
                # paired inference recomputation (base)
                main_ = json.loads((folder / f'{segment}-{family}-base-primary_strategy.json').read_text())['metrics']
                bench = json.loads((folder / f'{segment}-{family}-base-primary_{"matched" if family == "A" else "riskcap"}.json').read_text())['metrics']
                inf = E.paired_bootstrap(main_['daily_returns'], bench['daily_returns'], 'mean_excess' if family == 'A' else 'sharpe_difference')
                saved = json.loads((folder / 'results.json').read_text())['results'][segment][family]['base'].get('inference')
                rep.setdefault('inference', {})[f'{segment}/{family}'] = {'recomputed': inf['blocks'], 'saved_equal': saved == json.loads(json.dumps(inf)) if saved else 'no-saved'}
            print(phase, segment, 'exact', len(rep['byte_exact']), 'mismatch', len(rep['mismatch']), flush=True)
    (OUT / 'sd2026-repro.json').write_text(json.dumps(rep, indent=1))
    print('MISMATCHES', rep['mismatch'][:20])
    for k, v in rep['inference'].items(): print(k, v)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True); main()
