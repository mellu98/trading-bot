"""POST-HOC DIAGNOSTIC (not part of the frozen E1 rules): were the extreme perp wicks that drive the
simulated liquidations visible in Binance's MARK price (used for real liquidations) or only in last trades?

Downloads two official markPriceKlines archives (checksum-verified) and compares hourly highs.
Usage: python -I diag_markprice.py <research_dir>
"""
import hashlib
import json
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import iso, load_klines  # noqa: E402

root = pathlib.Path(sys.argv[1])
base = "https://data.binance.vision/data/futures/um/monthly/markPriceKlines/{s}/1h/{s}-1h-{m}.zip"
jobs = [("ETHUSDT", "2020-03"), ("BTCUSDT", "2020-03"), ("BTCUSDT", "2021-07")]
out = {"note": "post-hoc diagnostic; frozen E1 results are NOT recomputed or changed", "cases": []}
for s, m in jobs:
    url = base.format(s=s, m=m)
    dest = root / "cache" / "binance" / "data" / "futures" / "um" / "monthly" / "markPriceKlines" / s / "1h" / f"{s}-1h-{m}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    ck = urllib.request.urlopen(url + ".CHECKSUM", timeout=60).read().decode().split()[0]
    if not dest.exists():
        dest.write_bytes(urllib.request.urlopen(url, timeout=60).read())
    if hashlib.sha256(dest.read_bytes()).hexdigest() != ck:
        raise SystemExit("checksum mismatch " + url)
    mark = load_klines(dest.parent)
    last = load_klines(root / "cache" / "binance" / "data" / "futures" / "um" / "monthly" / "klines" / s / "1h")
    rows = []
    keys = sorted(k for k in mark if iso(k)[:7] == m)
    for a, b in zip(keys, keys[1:]):
        if b in last and a in last:
            rows.append((last[b][1] / last[a][3] - 1, mark[b][1] / mark[a][3] - 1, iso(b), last[b][1], mark[b][1]))
    rows.sort(reverse=True)
    out["cases"].append({"symbol": s, "month": m, "checksum": ck,
                         "top_last_price_wicks": [{"hour": r[2], "last_high_vs_prev_close": round(r[0], 4),
                                                   "mark_high_vs_prev_mark_close": round(r[1], 4),
                                                   "last_high": r[3], "mark_high": r[4]} for r in rows[:3]]})
(root / "results" / "E1" / "diag-markprice.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
