"""Non-economic data-quality checks (structure only: units, continuity, timestamps, counts).

Deliberately prints no returns, funding levels or P&L, so it can run before the freeze.
Usage: python -I quality.py <research_dir>
"""
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import HOUR_MS, iso, load_funding, load_klines, ms, to_ms, _rows  # noqa: E402
import datetime as dt  # noqa: E402

root = pathlib.Path(sys.argv[1])
cache = root / "cache" / "binance" / "data"
start, end = ms(dt.datetime(2020, 1, 1)), ms(dt.datetime(2026, 10, 1))
report = {"window": [iso(start), iso(end)], "klines": {}, "funding": {}, "units": {}}

for market, sub in (("spot", "spot/monthly/klines/{s}/1h"), ("perp", "futures/um/monthly/klines/{s}/1h")):
    for s in ("BTCUSDT", "ETHUSDT"):
        folder = cache / sub.format(s=s)
        # raw unit census per archive year (before normalisation)
        census = collections.Counter()
        for zp in sorted(folder.glob("*.zip")):
            first = next(_rows(zp))
            census[(zp.name[-11:-7], "us" if int(first[0]) > 10**14 else "ms")] += 1
        report["units"][f"{market}:{s}"] = {f"{y}:{u}": n for (y, u), n in sorted(census.items())}
        bars = load_klines(folder)
        expected = (end - start) // HOUR_MS
        present = [t for t in bars if start <= t < end]
        missing = sorted(set(range(start, end, HOUR_MS)) - set(present))
        runs, prev = [], None
        for t in missing:
            if prev is None or t != prev + HOUR_MS:
                runs.append([t, t])
            else:
                runs[-1][1] = t
            prev = t
        report["klines"][f"{market}:{s}"] = {
            "expected_hours": expected, "present": len(present), "missing": len(missing),
            "missing_runs": [[iso(a), iso(b + HOUR_MS), (b - a) // HOUR_MS + 1] for a, b in runs],
        }

for s in ("BTCUSDT", "ETHUSDT"):
    fl = load_funding(cache / f"futures/um/monthly/fundingRate/{s}")
    inside = [x for x in fl if start <= x[0] < end]
    intervals = collections.Counter(x[1] for x in inside)
    offsets = collections.Counter(x[0] % HOUR_MS for x in inside)
    hours = collections.Counter((x[0] // HOUR_MS) % 24 for x in inside)
    spacing = collections.Counter((b[0] - a[0]) // 60000 for a, b in zip(inside, inside[1:]))
    report["funding"][s] = {
        "settlements": len(inside), "first": iso(inside[0][0]), "last": iso(inside[-1][0]),
        "interval_hours": dict(intervals), "ms_offset_from_hour": {str(k): v for k, v in offsets.most_common(5)},
        "settlement_hours_utc": dict(sorted(hours.items())),
        "spacing_minutes_top": {str(k): v for k, v in spacing.most_common(6)},
        "irregular_spacing": [[iso(a[0]), iso(b[0])] for a, b in zip(inside, inside[1:])
                              if abs((b[0] - a[0]) - 8 * HOUR_MS) > 60000][:20],
    }

import common  # noqa: E402

report["kline_anomalies"] = [[a, k, iso(o), iso(c + 1)] for (a, k, o, c) in common.ANOMALIES]
out = root / "results" / "data-quality.json"
out.write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1)[:6000])
