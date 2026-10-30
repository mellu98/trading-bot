"""Causal detectors, ported 1:1 from docs/ict-engine-v1/reference.

atr, confirmed_pivots, sweep, displaced, mss and fvg keep the reference
formulas and argument conventions (cfg dict, direction +1/-1, lagged ATR).
`confirmed_pivots` is kept for parity tests; the engine uses the equivalent
incremental tracker in engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass


def atr(bars, n):
    """Simple mean of the last n true ranges; caller passes bars completed BEFORE the decision bar."""
    if len(bars) < n + 1:
        return None
    xs = bars[-n - 1:]
    return sum(max(b.h - b.l, abs(b.h - a.c), abs(b.l - a.c)) for a, b in zip(xs, xs[1:])) / n


@dataclass(frozen=True)
class Pivot:
    index: int
    known_at: int
    kind: str
    price: float


def confirmed_pivots(bars, left, right):
    """Strict pivots: ties are not pivots; pivot i is known only at i+right."""
    out = []
    for i in range(left, len(bars) - right):
        others = bars[i - left:i] + bars[i + 1:i + right + 1]
        if all(bars[i].h > x.h for x in others):
            out.append(Pivot(i, i + right, "HIGH", bars[i].h))
        if all(bars[i].l < x.l for x in others):
            out.append(Pivot(i, i + right, "LOW", bars[i].l))
    return out


def sweep(bar, pool, direction, atr_value, cfg):
    """Same-bar sweep and recovery of a confirmed pool (long sweeps a LOW, short a HIGH)."""
    penetration = pool.price - bar.l if direction == 1 else bar.h - pool.price
    recovered = direction * (bar.c - pool.price) >= cfg["sweep_recovery_ticks"] * cfg["tick_size"]
    return cfg["sweep_min_atr"] * atr_value <= penetration <= cfg["sweep_max_atr"] * atr_value and recovered


def displaced(bar, direction, atr_value, cfg):
    r = bar.h - bar.l
    if r <= 0 or atr_value <= 0:
        return False
    body = direction * (bar.c - bar.o)
    end = (bar.h - bar.c if direction == 1 else bar.c - bar.l) / r
    return body >= cfg["body_atr_min"] * atr_value and body / r >= cfg["body_ratio_min"] and end <= cfg["close_extreme_max"]


def mss(bar, level, direction, atr_value, cfg):
    return direction * (bar.c - level) > cfg["mss_buffer_ticks"] * cfg["tick_size"] and displaced(bar, direction, atr_value, cfg)


def fvg(bars, direction, atr_value, cfg):
    """Three-bar gap whose middle bar is the caller's MSS bar. Returns (lo, hi) or None."""
    if len(bars) < 3:
        return None
    a, _, c = bars[-3:]
    lo, hi = (a.h, c.l) if direction == 1 else (c.h, a.l)
    if cfg["fvg_min_atr"] * atr_value <= hi - lo <= cfg["fvg_max_atr"] * atr_value:
        return (lo, hi)
    return None
