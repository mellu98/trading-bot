"""Bars, quality checks, contiguous segments and M1 -> M5 aggregation.

Convention (same as the reference): `ts` is the bar END time, UTC aware. A bar
becomes observable at `ts`; decisions taken on it can only fill on later bars.
Prices are mid prices; `spread` is the ask-bid at the bar close when the source
provides native bid/ask (Capital.com), otherwise None.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite

UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class Bar:
    ts: datetime  # end time, UTC aware
    o: float
    h: float
    l: float
    c: float
    spread: float | None = None
    volume: float | None = None

    def __post_init__(self):
        if self.ts.tzinfo is None or self.ts.utcoffset().total_seconds() != 0:
            raise ValueError("UTC required")
        if not all(isfinite(x) and x > 0 for x in (self.o, self.h, self.l, self.c)):
            raise ValueError("invalid price")
        if not self.l <= min(self.o, self.c) <= max(self.o, self.c) <= self.h:
            raise ValueError("invalid OHLC")
        if self.spread is not None and not (isfinite(self.spread) and self.spread >= 0):
            raise ValueError("invalid spread")


def validate_append(bars, b, seconds):
    """Reference rule: any duplicate, reorder or missing bar ends the segment."""
    if bars and (b.ts - bars[-1].ts).total_seconds() != seconds:
        raise ValueError("duplicate, unordered or missing bar: reset segment")


def dedupe_sorted(bars: list[Bar]) -> tuple[list[Bar], dict]:
    """Sort, drop identical duplicates, quarantine (drop) timestamps with discordant duplicates."""
    by_ts: dict[datetime, list[Bar]] = {}
    for b in bars:
        by_ts.setdefault(b.ts, []).append(b)
    clean, identical, discordant = [], 0, []
    for ts in sorted(by_ts):
        group = by_ts[ts]
        if len(group) == 1:
            clean.append(group[0])
        elif all(x == group[0] for x in group):
            identical += len(group) - 1
            clean.append(group[0])
        else:
            discordant.append(ts.isoformat())
    return clean, {"identical_duplicates_dropped": identical, "discordant_quarantined": discordant}


def segments(bars: list[Bar], seconds: int) -> list[list[Bar]]:
    """Split a sorted, de-duplicated bar list into contiguous segments."""
    out: list[list[Bar]] = []
    current: list[Bar] = []
    step = timedelta(seconds=seconds)
    for b in bars:
        if current and b.ts - current[-1].ts != step:
            out.append(current)
            current = []
        current.append(b)
    if current:
        out.append(current)
    return out


def quality_report(bars: list[Bar], seconds: int, dedupe_info: dict | None = None) -> dict:
    segs = segments(bars, seconds)
    gaps = []
    for a, b in zip(segs, segs[1:]):
        missing = int((b[0].ts - a[-1].ts).total_seconds() // seconds) - 1
        gaps.append({"after": a[-1].ts.isoformat(), "resume": b[0].ts.isoformat(), "missing_bars": missing})
    long_gaps = [g for g in gaps if g["missing_bars"] > 1]
    return {
        "bars": len(bars),
        "first_end": bars[0].ts.isoformat() if bars else None,
        "last_end": bars[-1].ts.isoformat() if bars else None,
        "segments": len(segs),
        "gaps": len(gaps),
        "missing_bars_total": sum(g["missing_bars"] for g in gaps),
        "largest_gaps": sorted(gaps, key=lambda g: -g["missing_bars"])[:10],
        "gaps_over_one_bar": len(long_gaps),
        "zero_range_bars": sum(1 for b in bars if b.h == b.l),
        "spread_available": bool(bars) and all(b.spread is not None for b in bars),
        **(dedupe_info or {}),
    }


def aggregate(bars: list[Bar], source_seconds: int, target_seconds: int) -> list[Bar]:
    """Deterministic aggregation; only complete, aligned groups are emitted (no partial bars)."""
    if target_seconds % source_seconds:
        raise ValueError("target timeframe must be a multiple of the source timeframe")
    k = target_seconds // source_seconds
    groups: dict[datetime, list[Bar]] = {}
    for b in bars:
        start = b.ts - timedelta(seconds=source_seconds)
        epoch = int(start.timestamp())
        bucket_start = epoch - epoch % target_seconds
        end = datetime.fromtimestamp(bucket_start + target_seconds, UTC)
        groups.setdefault(end, []).append(b)
    out = []
    for end in sorted(groups):
        g = sorted(groups[end], key=lambda x: x.ts)
        if len(g) != k or g[-1].ts != end:
            continue
        if any((y.ts - x.ts).total_seconds() != source_seconds for x, y in zip(g, g[1:])):
            continue
        vols = [x.volume for x in g]
        out.append(Bar(end, g[0].o, max(x.h for x in g), min(x.l for x in g), g[-1].c,
                       spread=g[-1].spread,
                       volume=None if any(v is None for v in vols) else sum(vols)))
    return out
