"""Audit check 01: timestamp units in cached Binance Vision archives (read-only)."""
import zipfile, io, csv, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path("/Users/locoframe/Desktop/TRADING BOT")
files = [
    "data/binance-spot/research/BTCUSDT-1h-2024-12.zip",
    "data/binance-spot/research/BTCUSDT-1h-2025-01.zip",
    "data/binance-spot/research/BTCUSDT-1h-2025-12.zip",
    "data/binance-spot/breakout-4h/BTCUSDT-1h-2026-01.zip",
    "data/binance-spot/breakout-4h/BTCUSDT-1h-2026-09.zip",
    "research/strategy-discovery-2026/data/1h/BTCUSDT/BTCUSDT-1h-2024-11.zip",
    "research/strategy-discovery-2026/data/1h/ETHUSDT/ETHUSDT-1h-2019-12.zip",
    "research/strategy-discovery-2026/data/1d/BTCUSDT/BTCUSDT-1d-2024-11.zip",
]
for f in files:
    p = ROOT / f
    with zipfile.ZipFile(p) as z:
        info = z.infolist()
        txt = z.read(info[0]).decode()
    rows = list(csv.reader(io.StringIO(txt)))
    header = not rows[0][0].isdigit()
    first = rows[1] if header else rows[0]
    last = rows[-1]
    o, c = int(first[0]), int(first[6])
    digits = len(str(o))
    unit = {13: "ms", 16: "us"}.get(digits, "?")
    div = {13: 1e3, 16: 1e6}.get(digits, 1)
    print(f"{f}\n   rows={len(rows)} header={header} open_time={o} ({digits} digits => {unit}) "
          f"-> {datetime.fromtimestamp(o/div, timezone.utc).isoformat()} close_time={c} close-open={c-o} "
          f"last_open={datetime.fromtimestamp(int(last[0])/div, timezone.utc).isoformat()}")
