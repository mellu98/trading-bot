"""Audit 13: spot-check BTCETH-B-VALIDATION.md tables against the frozen B ledgers (read-only)."""
import json, math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
SD = Path('/Users/locoframe/Desktop/TRADING BOT/research/strategy-discovery-2026')
want = {'development': (66.13, 20.05, 1.08, 16.31, 65.09, 7.54, 17.03, -11.92, '13/36'), 'validation': (3.22, 18.42, 0.27, 32.73, 97.92, 7.66, 17.94, -7.00, '6/12'),
        'holdout': (42.54, 8.71, 2.34, 25.79, 61.52, 4.76, 17.16, -3.13, '6/11')}
out = {}
for seg, w in want.items():
    f = SD / ('results-holdout' if seg == 'holdout' else 'results-development-validation') / f'{seg}-B-base-primary_strategy.json'
    x = json.loads(f.read_text()); m = x['metrics']; eq = np.array(x['equity']); ts = x['times']; r = eq[1:] / eq[:-1] - 1
    months = {}
    for i in range(1, len(eq)):
        k = datetime.fromtimestamp(ts[i] - 1, timezone.utc).strftime('%Y-%m'); months.setdefault(k, [i - 1, i]); months[k][1] = i
    pos = sum(eq[b] / eq[a] - 1 > 0 for a, b in months.values())
    got = (m['net_return'] * 100, m['max_drawdown'] * 100, m['daily_sharpe_365'], m['average_exposure'] * 100, m['maximum_exposure'] * 100, m['two_way_turnover'], float(np.std(r, ddof=1) * math.sqrt(365) * 100), float(r.min() * 100), f'{pos}/{len(months)}')
    out[seg] = [(round(g, 2) if isinstance(g, float) else g, ww, (abs(g - ww) <= .006) if isinstance(g, float) else g == ww) for g, ww in zip(got, w)]
print(json.dumps(out)); print('ALL_OK', all(c for v in out.values() for _, _, c in v))
