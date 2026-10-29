"""Audit 12: how far is the next native-hour OPEN from the previous hour CLOSE in BTCUSDT 1h archives
(Dec-2024..Sep-2026)? Quantifies what the 'same-boundary' fill actually assumes."""
import sys, importlib.util, json
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, '/Users/locoframe/Desktop/TRADING BOT/src')
spec = importlib.util.spec_from_file_location('repro02', HERE / '02_breakout_repro.py'); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
bars = M.load_bars()
d = np.array([float(bars[i + 1].open / bars[i].close - 1) for i in range(len(bars) - 1)]) * 1e4
four = [i for i in range(len(bars) - 1) if bars[i].end % (4 * M.R.H) == 0]
d4 = d[four]
out = {'all_hours': {'n': len(d), 'median_abs_bp': float(np.median(abs(d))), 'p99_abs_bp': float(np.quantile(abs(d), .99)), 'max_abs_bp': float(abs(d).max()), 'share_exactly_equal_or_1tick': float(np.mean(abs(d) < 0.01))},
       'at_4h_boundaries': {'n': len(d4), 'median_abs_bp': float(np.median(abs(d4))), 'p99_abs_bp': float(np.quantile(abs(d4), .99)), 'max_abs_bp': float(abs(d4).max())}}
print(json.dumps(out, indent=1)); (HERE / 'out/boundary-gap.json').write_text(json.dumps(out, indent=1))
