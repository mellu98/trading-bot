"""B1: why did the MNQ/MES Timestral-28M lagged filter reject (almost) all ORB / Sweep candidates and accept
VWAP ones? Recompute every recorded filter decision from the saved forecasts and bars. Read-only."""
import csv, json, sys
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-futures')
from common import ROOT, OUT

EXP = ROOT / 'reports/timestral-28m-experiment'
H5 = 2       # index of horizon 5 in (1,3,5,10,15)  (schema.py:13)
MED = 10     # index of level .50 in LEVELS          (schema.py:14)
EDGE = .25   # timestral_experiment.py:38

# saved forecasts: (symbol, origin, variant) -> 5x21 quantile grid in PRICE units
fc = {}
with (EXP / 'forecasts.jsonl').open() as f:
    for line in f:
        p = json.loads(line)['prediction']
        fc[p['symbol'], p['origin'], p['variant']] = p['values']
# bars: close at each bar end
close = {}
with (ROOT / 'reports/real-simulation/bars.csv').open() as f:
    for r in csv.DictReader(f):
        close[r['symbol'], datetime.fromisoformat(r['end']).isoformat()] = float(r['close'])

rows = []
for strategy in ('vwap_v1', 'orb_v2', 'sweep_mss_v2'):
    for variant in ('target_only', 'past_covariates'):
        for path in sorted((EXP / 'replay' / strategy / variant).glob('*/filter-decisions.json')):
            for a in json.loads(path.read_text()):
                t = datetime.fromisoformat(a['at']); o = t - timedelta(minutes=1)
                sym, side = a['symbol'], a['side']
                c_t = close[sym, t.isoformat()]; c_o = close[sym, o.isoformat()]
                lag = fc[sym, o.isoformat(), variant]          # forecast actually used (origin t-1)
                fresh = fc.get((sym, t.isoformat(), variant))  # forecast with origin t (exists in the same log)
                med_lag = lag[H5][MED]
                edge = side * (med_lag - c_t)                   # strategy.py:65-67 with price=close_t
                rows.append({
                    'strategy': strategy, 'variant': variant, 'at': a['at'], 'symbol': sym, 'side': side,
                    'recorded_allowed': a['allowed_by_filter'], 'recorded_reason': a['reason'],
                    'recomputed_allowed': bool(edge >= EDGE), 'edge': edge,
                    'model_move_signed': side * (med_lag - c_o),          # model's own view from its anchor
                    'last_bar_move_signed': side * (c_t - c_o),           # trigger bar move in signal direction
                    'persistence_forecaster_allowed': bool(-side * (c_t - c_o) >= EDGE),
                    'own_anchor_allowed': bool(side * (med_lag - c_o) >= EDGE),
                    'fresh_origin_allowed': bool(side * (fresh[H5][MED] - c_t) >= EDGE) if fresh else None,
                    'lag_q10_q90_width': lag[H5][18 - 0] - lag[H5][2] if False else lag[H5][18] - lag[H5][2]})

summary = {}
by = defaultdict(list)
for r in rows:
    by[r['strategy'], r['variant']].append(r)
for (s, v), rr in sorted(by.items()):
    lm = np.array([r['last_bar_move_signed'] for r in rr]); mm = np.array([r['model_move_signed'] for r in rr])
    summary[f'{s}/{v}'] = {
        'candidates': len(rr),
        'recorded_allowed': sum(r['recorded_allowed'] for r in rr),
        'recomputed_allowed': sum(r['recomputed_allowed'] for r in rr),
        'recompute_matches_record': sum(r['recomputed_allowed'] == r['recorded_allowed'] for r in rr),
        'recorded_reasons': dict(Counter(r['recorded_reason'] for r in rr)),
        'trigger_bar_moved_in_signal_direction': int((lm > 0).sum()),
        'median_abs_last_bar_move_pts': float(np.median(np.abs(lm))),
        'median_abs_model_move_pts': float(np.median(np.abs(mm))),
        'share_abs_model_move_lt_abs_last_bar_move': float(np.mean(np.abs(mm) < np.abs(lm))),
        'persistence_forecaster_would_allow': sum(r['persistence_forecaster_allowed'] for r in rr),
        'decision_identical_to_persistence_forecaster': sum(r['persistence_forecaster_allowed'] == r['recorded_allowed'] for r in rr),
        'own_anchor_rule_would_allow': sum(r['own_anchor_allowed'] for r in rr),
        'fresh_origin_rule_would_allow': sum(bool(r['fresh_origin_allowed']) for r in rr),
        'median_q10_q90_width_pts': float(np.median([r['lag_q10_q90_width'] for r in rr]))}
    print(s, v, json.dumps(summary[f'{s}/{v}']))
(OUT / 'b1_mnq_28m_filter.json').write_text(json.dumps({'summary': summary}, indent=2))
with (OUT / 'b1_mnq_28m_filter_rows.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
