"""Synthetic tests for the E1 carry simulator and shared statistics (no market data)."""
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from carry import DAY_MS, decide, simulate  # noqa: E402
from common import HOUR_MS, circular_block_bootstrap, max_drawdown, newey_west_t, to_ms  # noqa: E402

T0 = 1_704_067_200_000  # 2024-01-01T00:00Z
ZERO = {"spot_fee": 0.0, "perp_fee": 0.0, "half_spread": 0.0, "slippage": 0.0}
BASE = {"spot_fee": 0.001, "perp_fee": 0.0005, "half_spread": 0.0001, "slippage": 0.0001}
CFG = {"symbols": ["X"], "weights": {"X": 1.0}, "margin_fraction": 0.5, "rebalance_band": [0.5, 2.0],
       "maintenance_margin_rate": 0.005, "execution_hour_utc": 1, "rule": "always_on"}


def flat_bars(days, px=100.0, path=None):
    out = {}
    for h in range(days * 24):
        t = T0 + h * HOUR_MS
        p = path(h) if path else px
        out[t] = (p, p, p, p, t + HOUR_MS - 1)
    return out


def funding_every_8h(days, rate):
    return [(T0 + k * 8 * HOUR_MS, 8, rate) for k in range(days * 3)]


def run(cfg, bs, bf, fl, days, cost=ZERO):
    return simulate(cfg, {"X": bs}, {"X": bf}, {"X": fl}, T0 + HOUR_MS, T0 + days * DAY_MS, cost, 1000.0,
                    lambda t: 0.0)


def test_constant_prices_funding_accrues_on_notional():
    days, rate = 10, 0.0001
    daily, sl, _ = run(CFG, flat_bars(days), flat_bars(days), funding_every_8h(days, rate), days)
    q = 1000.0 / (100 * (1 + 0.5))  # spot + 0.5 margin, zero costs
    # first settlement after entry at 01:00 is 08:00 of day 0 -> 3*days-1 settlements
    expected = q * 100 * rate * (3 * days - 1)
    assert abs(sl["X"].funding - expected) < 1e-9
    assert abs(daily[-1]["nav"] - (1000 + expected)) < 1e-6


def test_price_moves_are_hedged():
    days = 6
    path = lambda h: 100 * (1 + 0.002 * h)  # +29% steady trend, identical spot and perp
    daily, sl, _ = run(CFG, flat_bars(days, path=path), flat_bars(days, path=path), [], days)
    assert abs(daily[-1]["nav"] - 1000.0) < 1e-6
    assert sl["X"].liquidations == 0


def test_costs_reduce_nav_and_cash_never_negative():
    days = 5
    daily, sl, _ = run(CFG, flat_bars(days), flat_bars(days), [], days, BASE)
    assert daily[-1]["nav"] < 1000.0
    assert sl["X"].cash >= 0
    # one entry + one exit, both legs: spot (10+1+1 bp) on 2/3 of capital, perp (5+1+1) roughly
    loss = 1000.0 - daily[-1]["nav"]
    assert 2.0 < loss < 4.0


def test_liquidation_on_spike():
    days = 3
    spike = lambda h: 100.0 if h < 30 else 170.0  # +70% jump after entry
    daily, sl, _ = run(CFG, flat_bars(days, path=spike), flat_bars(days, path=spike), [], days)
    assert sl["X"].liquidations == 1


def test_rebalance_on_large_move():
    days = 4
    up = lambda h: 100.0 if h < 20 else 130.0  # +30%: collateral ratio falls below 0.25
    daily, sl, _ = run(CFG, flat_bars(days, path=up), flat_bars(days, path=up), [], days)
    assert sl["X"].rebalances >= 1 and sl["X"].liquidations == 0
    assert abs(daily[-1]["nav"] - 1000.0) < 1e-6


def test_decision_uses_only_settlements_before_execution():
    cfg = dict(CFG, rule="hysteresis", signal_lookback_days=7, entry_threshold_annual=0.10,
               exit_threshold_annual=0.0)
    t_exec = T0 + 7 * DAY_MS + HOUR_MS
    # huge rate stamped exactly at the execution time must be ignored
    fl = [(T0 + 7 * DAY_MS + HOUR_MS, 8, 0.05)]
    assert decide("hysteresis", fl, t_exec, 7 * DAY_MS, cfg, False) is False
    fl = [(T0 + 7 * DAY_MS, 8, 0.05)]  # 00:00 settlement, one hour before execution
    assert decide("hysteresis", fl, t_exec, 7 * DAY_MS, cfg, False) is True
    fl = [(T0, 8, 0.05)]  # exactly 7 days before: outside (lo, t)
    assert decide("hysteresis", fl, t_exec, 7 * DAY_MS, cfg, False) is False


def test_hysteresis_exits_when_funding_turns_negative():
    days = 30
    fl = [(T0 + k * 8 * HOUR_MS, 8, 0.0005 if k < 45 else -0.0005) for k in range(days * 3)]
    cfg = dict(CFG, rule="hysteresis", signal_lookback_days=7, entry_threshold_annual=0.10,
               exit_threshold_annual=0.0)
    daily, sl, _ = run(cfg, flat_bars(days), flat_bars(days), fl, days)
    kinds = [e[1] for e in sl["X"].events]
    assert kinds.count("set") == 1 and kinds.count("exit") == 1


def test_microsecond_normalisation():
    assert to_ms("1735689600000000") == 1735689600000
    assert to_ms("1735689600000") == 1735689600000


def test_stats_helpers():
    assert abs(max_drawdown([1, 2, 1, 3]) - 0.5) < 1e-12
    x = [0.01, -0.01] * 50
    assert abs(newey_west_t(x, 5)) < 1e-9
    d = circular_block_bootstrap([1.0] * 20, 5, 50, 1)
    assert all(abs(v - 1.0) < 1e-12 for v in d)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # report every failure
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
