"""Matched random-entry benchmark (protocol 07: "random entries matched per ora/direzione").

Null hypothesis: A1's selection adds nothing over random timing. For every real
A1 trade we draw a random decision bar in the same period with the same New
York hour and an in-session weekday, keep the same direction and the same stop
and target distances in lagged-ATR units, enter at the next bar's open (market,
paying half spread), and exit with the same conservative OHLC rules and costs
(stop first, no target on the entry bar, time exit, session cutoff).
R is computed per unit, so it does not depend on account size.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .backtest import spread_for
from .sizing import slippage_for


def _lagged_atr(seg, n):
    """ATR known before bar i (same as the engine's prior ATR)."""
    out = [None] * len(seg)
    for i in range(n + 1, len(seg)):
        xs = seg[i - n - 1:i]
        out[i] = sum(max(b.h - b.l, abs(b.h - a.c), abs(b.l - a.c)) for a, b in zip(xs, xs[1:])) / n
    return out


def build_index(segments, cfg, start: datetime, end: datetime):
    """Decision bars available for random draws, keyed by New York hour."""
    tz = ZoneInfo(cfg["session_timezone"])
    pools: dict[int, list] = {}
    atrs = []
    for s_idx, seg in enumerate(segments):
        atr = _lagged_atr(seg, cfg["atr_period"])
        atrs.append(atr)
        for k, b in enumerate(seg[:-1]):
            if b.ts < start or b.ts >= end or atr[k] is None or atr[k] <= 0:
                continue
            local = b.ts.astimezone(tz)
            clock = f"{local.hour:02d}:{local.minute:02d}"
            if local.weekday() not in cfg["weekdays"] or not (cfg["session_start"] <= clock < cfg["session_end"]):
                continue
            pools.setdefault(local.hour, []).append((s_idx, k))
    return pools, atrs


def simulate_unit(seg, k, atr, d, stop_atr, target_atr, cfg):
    """Market entry at bar k+1 open; returns R per unit or None if not simulable."""
    tz = ZoneInfo(cfg["session_timezone"])
    if k + 1 >= len(seg):
        return None
    first = seg[k + 1]
    sp = spread_for(first, cfg)
    entry = first.o + d * sp / 2
    slip = slippage_for(entry, cfg)
    stop = entry - d * stop_atr * atr
    target = entry + d * target_atr * atr
    m, x, f = cfg["multiplier"], cfg["quote_to_eur"], cfg["fee_rate"]
    risk = (abs(entry - stop) + slip) * m * x + f * (entry + stop + slip) * m * x + cfg["unit_fee_eur"]
    if risk <= 0 or stop <= 0:
        return None
    tick = cfg["tick_size"]
    held = 0
    for j in range(k + 1, len(seg)):
        b = seg[j]
        sp = spread_for(b, cfg)
        side = -sp / 2 if d == 1 else sp / 2
        lo, hi, op = b.l + side, b.h + side, b.o + side
        held += 1
        new = j == k + 1
        hitstop = lo <= stop if d == 1 else hi >= stop
        hittarget = hi >= target + tick if d == 1 else lo <= target - tick
        local_end = b.ts.astimezone(tz)
        reaches_cutoff = f"{local_end.hour:02d}:{local_end.minute:02d}" >= cfg["session_end"]
        exit_price = None
        if hitstop:
            exit_price = (min(op, stop) if d == 1 else max(op, stop)) - d * slip
        elif hittarget and not new:
            exit_price = target
        elif held >= cfg["max_hold_bars"] or reaches_cutoff:
            exit_price = b.c + side - d * slip
        if exit_price is not None:
            gross = d * (exit_price - entry) * m * x
            fees = f * (exit_price + entry) * m * x + cfg["unit_fee_eur"]
            return (gross - fees) / risk
    return None  # segment ended with the position open: unpriceable, excluded


def random_matched(trades, segments, cfg, start: datetime, end: datetime, *, reps=200, seed=20261030) -> dict:
    tz = ZoneInfo(cfg["session_timezone"])
    pools, atrs = build_index(segments, cfg, start, end)
    specs = []
    for t in trades:
        atr = t.get("atr_lag")
        if not atr:
            continue
        hour = datetime.fromisoformat(t["known_at"]).astimezone(tz).hour
        if hour not in pools:
            continue
        specs.append((hour, t["direction"], abs(t["entry"] - t["stop"]) / atr, abs(t["target"] - t["entry"]) / atr))
    if not specs:
        return {"available": False, "reason": "no trades to match"}
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        rs = []
        for hour, d, s_atr, t_atr in specs:
            for _try in range(20):
                s_idx, k = rng.choice(pools[hour])
                r = simulate_unit(segments[s_idx], k, atrs[s_idx][k], d, s_atr, t_atr, cfg)
                if r is not None:
                    rs.append(r)
                    break
        if rs:
            means.append(sum(rs) / len(rs))
    actual = sum(t["R"] for t in trades) / len(trades)
    means.sort()
    better = sum(1 for m in means if m >= actual)
    return {
        "available": True, "reps": len(means), "seed": seed, "matched_trades": len(specs),
        "a1_mean_R": actual,
        "null_mean_R": sum(means) / len(means),
        "null_p5": means[int(0.05 * (len(means) - 1))], "null_p95": means[int(0.95 * (len(means) - 1))],
        "p_value_a1_not_better": (better + 1) / (len(means) + 1),
    }
