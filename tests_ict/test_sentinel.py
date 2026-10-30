"""Leakage sentinel: on a no-edge random walk with zero costs A1 must not make money.

Bars are built from a fine path (high/low are real path extremes). A positive,
stable expectancy here would mean the engine or the fill model sees the future.
Note: bars with detached random wicks are NOT a valid null — a limit order that
buys the wick earns by construction (observed during development).
"""
import math
import random
from datetime import datetime, timedelta, timezone

from ict_engine import config
from ict_engine.backtest import run
from ict_engine.bars import Bar, segments

UTC = timezone.utc
RELAX = {"body_atr_min": .5, "body_ratio_min": .55, "fvg_min_atr": .05, "sweep_max_atr": 1.0,
         "short_allowed": True, "fee_rate": 0.0, "slippage_bps": 0.0, "max_daily_trades": 10,
         "max_consecutive_losses": 99, "daily_loss_fraction": 1.0, "weekly_loss_fraction": 1.0,
         "drawdown_policy": "record", "news_enabled": False, "session_start": "00:00", "session_end": "23:55",
         "weekdays": [0, 1, 2, 3, 4, 5, 6]}


def path_bars(days, seed, start=60000.0, vol=0.0012, steps=20):
    rng = random.Random(seed)
    t = datetime(2024, 1, 1, tzinfo=UTC)
    out, p = [], start
    sub = vol / math.sqrt(steps)
    for _ in range(days * 288):
        o = hi = lo = p
        fat = 3 if rng.random() < 0.04 else 1
        for _ in range(steps):
            p = p * math.exp(rng.gauss(0, sub) * fat)
            hi, lo = max(hi, p), min(lo, p)
        t += timedelta(minutes=5)
        out.append(Bar(t, round(o, 2), round(hi, 2), round(lo, 2), round(p, 2)))
        p = round(p, 2)
    return out


def test_no_edge_on_path_consistent_random_walk():
    trades = []
    for seed in range(10, 16):
        bars = path_bars(180, seed)
        cfg = config.build("binance-btcusdt-spot", RELAX)
        trades += run(segments(bars, 300), cfg).trades
    assert len(trades) >= 100
    mean_r = sum(t["R"] for t in trades) / len(trades)
    sd = (sum((t["R"] - mean_r) ** 2 for t in trades) / (len(trades) - 1)) ** 0.5
    # Not significantly positive (t < 2) at zero cost.
    assert mean_r / (sd / len(trades) ** 0.5) < 2.0, mean_r
