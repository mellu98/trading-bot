"""Generic CSV bars (1m or 5m), e.g. the bot's Databento MNQ/MES file
reports/quant-validation/bars120.csv.

Required columns: open, high, low, close and `end` (bar end, UTC ISO) or `start`.
Optional: symbol (filtered with --symbol), contract (a change starts a new
segment: no back-adjusted series), spread, volume.

Note on the bot's existing MNQ/MES data: it covers only the cash session
(13:30-20:00 UTC). A1 trades 07:00-11:00 New York and needs 15 bars of warmup
after every gap, so on that file it can only decide from ~10:45 NY: the run is
technically valid but will produce almost no trades. Use 24h CME bars for a
meaningful futures benchmark.
"""
from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from .bars import Bar, aggregate


def _ts(text: str) -> datetime:
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("CSV timestamps must be UTC")
    return value


def load(path: str | Path, *, symbol: str | None = None, interval_seconds: int | None = None,
         target_seconds: int = 300) -> tuple[list[Bar], dict]:
    path = Path(path)
    raw_rows = []
    with path.open(newline="", encoding="utf8") as stream:
        reader = csv.DictReader(stream)
        cols = set(reader.fieldnames or [])
        if not {"open", "high", "low", "close"} <= cols or not ({"end"} & cols or {"start"} & cols):
            raise SystemExit("CSV needs open,high,low,close and end or start columns")
        for r in reader:
            if symbol and "symbol" in cols and r["symbol"] != symbol:
                continue
            raw_rows.append(r)
    if not raw_rows:
        raise SystemExit("no rows for the requested symbol")
    if interval_seconds is None:
        if {"start", "end"} <= cols:
            interval_seconds = int((_ts(raw_rows[0]["end"]) - _ts(raw_rows[0]["start"])).total_seconds())
        else:
            raise SystemExit("pass --interval-seconds when the CSV has only one timestamp column")
    contract_changes = []
    by_contract: dict[str, list[Bar]] = {}
    for r in raw_rows:
        end = _ts(r["end"]) if "end" in cols else _ts(r["start"]) + timedelta(seconds=interval_seconds)
        spread = float(r["spread"]) if "spread" in cols and r["spread"] else None
        volume = float(r["volume"]) if "volume" in cols and r["volume"] else None
        bar = Bar(end, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), spread, volume)
        by_contract.setdefault(r.get("contract", ""), []).append(bar)
    bars: list[Bar] = []
    firsts = []
    for contract, group in by_contract.items():
        group.sort(key=lambda b: b.ts)
        if interval_seconds != target_seconds:
            group = aggregate(group, interval_seconds, target_seconds)
        if group:
            firsts.append(group[0].ts)  # first OUTPUT bar of each contract: forced segment start
        bars.extend(group)
    bars.sort(key=lambda b: b.ts)
    if len(firsts) > 1:
        contract_changes = sorted(ts.isoformat() for ts in firsts)
    return bars, {"source": str(path), "symbol": symbol, "interval_seconds": interval_seconds,
                  "data_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "contract_changes": contract_changes}
