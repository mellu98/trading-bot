"""Audit 11 -- EXPLORATORY, already-observed data. (a) Pooled 2020-01..2024-11 paired comparison of
family B (and A) against its frozen comparator, concatenating the three frozen per-segment daily
return ledgers (no new simulation). (b) Approximate power of the frozen holdout bootstrap gate.
Uses the frozen engine.paired_bootstrap (same seed/blocks) -- not a new gate, not a selection."""
import sys, json, math
from pathlib import Path
import numpy as np
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT'); SD = ROOT / 'research/strategy-discovery-2026'
OUT = Path(__file__).resolve().parent / 'out'
sys.path.insert(0, str(SD))
import engine as E


def led(seg, fam, arm):
    folder = 'results-holdout' if seg == 'holdout' else 'results-development-validation'
    return json.loads((SD / folder / f'{seg}-{fam}-base-{arm}.json').read_text())['metrics']['daily_returns']


def shp(x): x = np.asarray(x); return float(x.mean() / x.std(ddof=1) * math.sqrt(365))


rep = {}
for fam, comp, metric in (('B', 'primary_riskcap', 'sharpe_difference'), ('A', 'primary_matched', 'mean_excess'), ('A', 'primary_riskcap', 'sharpe_difference')):
    a = []; b = []; per = {}
    for seg in ('development', 'validation', 'holdout'):
        x = led(seg, fam, 'primary_strategy'); y = led(seg, fam, comp); a += x; b += y
        per[seg] = {'days': len(x), 'sharpe_strategy': round(shp(x), 3), 'sharpe_comparator': round(shp(y), 3), 'diff': round(shp(x) - shp(y), 3),
                    'mean_excess_bp_day': round(float(np.mean(np.array(x) - np.array(y))) * 1e4, 3)}
    inf = E.paired_bootstrap(a, b, metric)
    rep[f'{fam}_vs_{comp}'] = {'per_segment_point': per, 'pooled_days': len(a), 'pooled_sharpe_strategy': round(shp(a), 3), 'pooled_sharpe_comparator': round(shp(b), 3),
                               'pooled_diff': round(shp(a) - shp(b), 3), 'pooled_mean_excess_bp_day': round(float(np.mean(np.array(a) - np.array(b))) * 1e4, 3),
                               'pooled_paired_bootstrap_' + metric: inf['blocks']}
# (b) power of the frozen B holdout gate (normal approx from the frozen bootstrap CI width)
for k, (lo, hi) in {'7': (-0.730914884036778, 1.6614466595111217), '30': (-0.4726926090848869, 1.4281063761226152)}.items():
    se = (hi - lo) / (2 * 1.959964); zc = 2.128045  # one-sided alpha .05/3
    needed = zc * se
    pw = {str(d): round(0.5 * math.erfc((zc - d / se) / math.sqrt(2)), 4) for d in (0.43, 0.5, 1.0)}
    rep[f'B_holdout_gate_power_block{k}'] = {'bootstrap_se_sharpe_diff': round(se, 3), 'point_estimate_needed_to_pass': round(needed, 3), 'power_if_true_diff': pw}
(OUT / 'b-pooled-power.json').write_text(json.dumps(rep, indent=1)); print(json.dumps(rep, indent=1))
