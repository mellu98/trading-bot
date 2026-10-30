"""Decision parity with the reference engine shipped in docs/ict-engine-v1/reference.

The reference rescans all pivots every bar (O(n^2)); ict_engine tracks them
incrementally. Both must produce the same reason code on every bar and the
same intents. Prices sit on a 0.25 tick grid (exact in binary floating point)
so the tick-rounding tolerance cannot introduce differences.

Two fixtures:
- baseline A1 config: exercises warmup, session, spread, sweep/MSS lifecycle;
- relaxed geometry (as in the reference end-to-end test, 24h session): reaches
  real intents, so entry/stop/target/sizing parity is covered too.
"""
import importlib
import sys

import pytest

from conftest import REFERENCE, random_walk
from ict_engine import config
from ict_engine.engine import A1Engine, Context

RELAXED = {"atr_period": 3, "pivot_left": 1, "pivot_right": 1, "body_atr_min": .5, "body_ratio_min": .6,
           "fvg_min_atr": .05, "sweep_max_atr": 1, "min_notional": 0, "fee_rate": 0, "slippage_price": 0,
           "max_spread_atr": 1.0, "session_start": "00:00", "session_end": "23:59",
           "weekdays": [0, 1, 2, 3, 4, 5, 6]}


def load_reference():
    sys.path.insert(0, str(REFERENCE))
    try:
        strategy = importlib.import_module("ict_strategy")
        risk = importlib.import_module("risk_manager")
    finally:
        sys.path.remove(str(REFERENCE))
    return strategy, risk


def compare(cfg, bars):
    ref_strategy, ref_risk = load_reference()
    ref = ref_strategy.Engine(dict(cfg))
    mine = A1Engine(cfg, keep_log=True)
    ref_signals, my_signals = [], []
    for b in bars:
        rctx = ref_strategy.Context(equity=1_000_000.0, spread=0.25, quote_time=b.ts,
                                    calendar_updated=b.ts, risk=ref_risk.RiskState())
        mctx = Context(equity=1_000_000.0, spread=0.25, quote_time=b.ts, calendar_updated=b.ts)
        rs = ref.on_bar(b, rctx)
        ms = mine.on_bar(b, mctx)
        assert (rs is None) == (ms is None), b.ts
        if rs:
            ref_signals.append(rs)
            my_signals.append({k: ms[k] for k in rs})
    assert [x["reason"] for x in mine.log] == [x["reason"] for x in ref.log]
    assert my_signals == ref_signals
    return {x["reason"] for x in ref.log}, len(ref_signals)


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
@pytest.mark.parametrize("short", [False, True])
def test_baseline_config_matches_reference(seed, short):
    cfg = config.build("synthetic", {"tick_size": 0.25, "short_allowed": short, "available_cash_eur": 1e7})
    codes, _ = compare(cfg, random_walk(3000, seed))
    assert "SWEEP_CONFIRMED" in codes


def test_relaxed_geometry_matches_reference_including_intents():
    total = 0
    seen = set()
    for seed in range(1, 7):
        cfg = config.build("synthetic", {"tick_size": 0.25, "short_allowed": True, "available_cash_eur": 1e7, **RELAXED})
        codes, n = compare(cfg, random_walk(3000, seed, shock=0.15))
        total += n
        seen |= codes
    assert total >= 10
    for code in ("ENTER_LONG", "ENTER_SHORT", "SKIP_NET_RR", "SKIP_NO_TARGET", "SKIP_FVG_EXPIRED",
                 "SKIP_MSS_EXPIRED", "SKIP_SWEEP_INVALIDATED", "SKIP_DUAL_SWEEP"):
        assert code in seen, code
