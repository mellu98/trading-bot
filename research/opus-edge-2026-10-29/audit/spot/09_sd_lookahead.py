"""Audit 09: no-look-ahead perturbation probe for Strategy-Discovery A/B features.
For every Monday execution index i, features computed by the frozen daily_features() from the
full grid must equal those computed when every daily row >= i-1 is overwritten with garbage."""
import sys, json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT'); SD = ROOT / 'research/strategy-discovery-2026'
sys.path.insert(0, str(SD))
import data as D, engine as E, runner as RN
data, _ = D.load_manifest('holdout'); out = {}
for fam, syms in (('A', D.SYMBOLS), ('B', D.SYMBOLS[:2])):
    g = RN.grid(data, '1d', syms); checked = 0; diffs = 0
    for i, t in enumerate(g['times']):
        if datetime.fromtimestamp(int(t), timezone.utc).weekday() != 0 or i < 40: continue
        for lb in ((14, 7) if fam == 'A' else (90, 60)):
            a = E.daily_features(g['close'], g['volume'], g['full'], i, lb)
            c = g['close'].copy(); v = g['volume'].copy(); f = g['full'].copy()
            c[i - 1:] = 1e9; v[i - 1:] = 1e-3; f[i - 1:] = True
            b = E.daily_features(c, v, f, i, lb)
            for k in ('eligible', 'momentum', 'returns', 'vol'):
                if not np.array_equal(a[k], b[k], equal_nan=True): diffs += 1
            checked += 1
    out[fam] = {'monday_decisions_x_lookbacks_checked': checked, 'differences': diffs}
print(json.dumps(out))
(Path(__file__).resolve().parent / 'out/sd-lookahead.json').write_text(json.dumps(out))
