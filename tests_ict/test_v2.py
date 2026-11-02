"""Engine v2 (full ICT): causality of every context element, PD arrays, SMT,
intent invariants, prefix invariance, no-edge sentinel, P&L-blind calibration."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from ict_engine import arrays, calibrate, config, protocol, windows
from ict_engine.backtest import RunResult
from ict_engine.backtest_v2 import run_v2
from ict_engine.bars import Bar
from ict_engine.context import MarketContext, PoolBook
from ict_engine.engine import Context
from ict_engine.engine_v2 import CompanionSeries, ICTEngine
from ict_engine.execution import SimulationAdapter
from synth import NY, market

UTC = timezone.utc
LOOSE = calibrate.level_overrides("capital-us100-cfd", {}, len(calibrate.LADDER) - 1)


def v2cfg(profile="capital-us100-cfd", **over):
    base = {"spread_mode": "fixed", "spread_price": 0.5, "news_enabled": False, "drawdown_policy": "record",
            "tick_size": 0.25}
    return config.build(profile, {**base, **over}, engine="v2")


# ------------------------------------------------------------------ config
def test_a1_configs_and_hashes_unchanged_by_v2():
    c = config.build("binance-btcusdt-spot", {"news_enabled": False, "drawdown_policy": "record"})
    assert config.config_hash(c).startswith("3088a1ee71886ef8")  # Francesco's run, 30/10/2026
    assert config.strategy_hash(c).startswith("841a01f525ca80fc")
    assert "engine" not in c and config.baseline_matches_package()


def test_v2_presets_and_validation():
    fx = config.build("capital-eurusd-cfd", engine="v2")
    idx = config.build("capital-us500-cfd", engine="v2")
    assert fx["asset_class"] == "fx" and fx["windows"][0] == ["02:00", "05:00", "08:00"]
    assert idx["asset_class"] == "index" and idx["windows"][-1] == ["13:30", "15:30", "16:00"]
    with pytest.raises(ValueError):
        config.build("capital-us100-cfd", {"models": ["magic"]}, engine="v2")
    with pytest.raises(ValueError):
        config.build("capital-us100-cfd", {"mode": "live"}, engine="v2")
    with pytest.raises(ValueError):
        ICTEngine(config.build("capital-us100-cfd"))  # A1 config refused


# ------------------------------------------------------------------ windows
def test_windows_dst_flat_and_scheduled_gaps():
    cfg = v2cfg()
    winter = datetime(2025, 1, 15, 13, 0, tzinfo=UTC)   # 08:00 NY (EST)
    summer = datetime(2025, 7, 15, 12, 0, tzinfo=UTC)   # 08:00 NY (EDT)
    for ts in (winter, summer):
        assert windows.decision_window(ts, cfg)[0] == "07:00"
        assert windows.local(windows.flat_at(ts, cfg), cfg).strftime("%H:%M") == "12:00"
    assert windows.decision_window(datetime(2025, 1, 15, 17, 0, tzinfo=UTC), cfg) is None  # 12:00 NY lunch
    friday = datetime(2025, 1, 17, 22, 0, tzinfo=UTC)    # Fri 17:00 NY
    sunday = datetime(2025, 1, 19, 23, 5, tzinfo=UTC)    # Sun 18:05 NY
    assert windows.scheduled_gap(friday, sunday, cfg)
    brk_a, brk_b = datetime(2025, 1, 15, 22, 0, tzinfo=UTC), datetime(2025, 1, 15, 23, 5, tzinfo=UTC)
    assert windows.scheduled_gap(brk_a, brk_b, cfg)
    hole_a, hole_b = datetime(2025, 1, 15, 14, 0, tzinfo=UTC), datetime(2025, 1, 15, 14, 30, tzinfo=UTC)
    assert not windows.scheduled_gap(hole_a, hole_b, cfg)
    assert windows.trading_day(datetime(2025, 1, 19, 23, 0, tzinfo=UTC), cfg).isoformat() == "2025-01-20"


# ------------------------------------------------------------------ context causality
def _feed(bars, cfg):
    book = PoolBook()
    ctx = MarketContext(cfg, book)
    seen = []
    for b in bars:
        ctx.on_bar(b)
        book.apply_bar(b)
        seen.append((b, [(p.ptype, p.kind, p.price, p.known_at) for p in book.pools]))
    return ctx, seen


def test_pdh_pdl_published_only_at_the_roll_with_previous_day_values():
    cfg = v2cfg()
    bars = market(4, 3)
    ctx, seen = _feed(bars, cfg)
    by_day = {}
    for b in bars:
        by_day.setdefault(windows.trading_day(b.ts - timedelta(minutes=5), cfg), []).append(b)
    days = sorted(by_day)
    day2, day3 = by_day[days[1]], by_day[days[2]]
    first3 = day3[0].ts
    for b, pools in seen:
        pd = [p for p in pools if p[0] == "pd"]
        if b.ts < first3:
            assert all(p[3] < first3 for p in pd)
        if b.ts == first3:
            levels = {p[1]: p[2] for p in pd if p[3] == first3}
            assert levels == {"HIGH": max(x.h for x in day2), "LOW": min(x.l for x in day2)}
    assert ctx.daily_bias in (-1, 0, 1)


def test_asia_range_known_only_at_midnight_new_york():
    cfg = v2cfg()
    bars = market(3, 4)
    _, seen = _feed(bars, cfg)
    for b, pools in seen:
        lt = b.ts.astimezone(NY)
        asia = [p for p in pools if p[0] == "asia" and p[3] == b.ts]
        if asia:
            assert (lt.hour, lt.minute) == (0, 0)
            start = b.ts - timedelta(hours=4)
            inside = [x for x, _ in seen if start < x.ts <= b.ts]
            assert {p[1]: p[2] for p in asia} == {"HIGH": max(x.h for x in inside), "LOW": min(x.l for x in inside)}


def test_h1_aggregation_requires_complete_hours_and_trend():
    cfg = v2cfg()
    t0 = datetime(2025, 3, 4, 14, 0, tzinfo=UTC)
    m5 = [Bar(t0 + timedelta(minutes=5 * (k + 1)), 100 + k, 101 + k, 99 + k, 100.5 + k) for k in range(12)]
    ctx, _ = _feed(m5, cfg)
    assert len(ctx.h1) == 1 and ctx.h1[0]["o"] == 100 and ctx.h1[0]["h"] == 112 and ctx.h1[0]["l"] == 99
    ctx2, _ = _feed(m5[:5] + m5[6:], cfg)  # one missing M5 bar: no H1 bar
    assert len(ctx2.h1) == 0
    # two rising swing highs and lows -> +1, two falling -> -1, mixed -> 0
    for hs, ls, want in (((100, 105), (95, 97), 1), ((105, 100), (97, 95), -1), ((100, 105), (97, 95), 0)):
        c = MarketContext(cfg, PoolBook())
        c.h1_highs.extend([(h, t0) for h in hs])
        c.h1_lows.extend([(x, t0) for x in ls])
        c._structure()
        assert c.trend == want
    ctx3 = MarketContext(cfg, PoolBook())
    ctx3.h1_highs.extend([(100, t0), (105, t0)])
    ctx3.h1_lows.extend([(95, t0), (97, t0)])
    ctx3._structure()
    assert ctx3.trend == 1 and ctx3.range == (97, 105)
    assert ctx3.zone(99) is None  # no H1 close yet -> range not validated
    ctx3.last_h1_close = 101
    assert ctx3.zone(101) == pytest.approx(0.5)


def test_equal_highs_pool_created_from_two_intact_pivots():
    cfg = v2cfg(equal_tolerance_atr=0.05)
    eng = ICTEngine(cfg)
    t0 = datetime(2025, 3, 4, 12, 0, tzinfo=UTC)
    bars = []
    highs = [100.5] * 20 + [100.5, 101.0, 102.0, 101.0, 100.5, 100.5, 101.0, 101.75, 101.0, 100.5, 100.5, 100.5]
    for k, h in enumerate(highs):
        bars.append(Bar(t0 + timedelta(minutes=5 * (k + 1)), 100.0, h, 99.5, 100.0))
    ctx = Context(equity=1e6, spread=0.25, quote_time=None, calendar_updated=None)
    for b in bars:
        eng.on_bar(b, Context(**{**ctx.__dict__, "quote_time": b.ts}))
    eq = [p for p in eng.book.pools if p.ptype == "equal"]
    assert eq and eq[0].kind == "HIGH" and eq[0].price == 102.0


# ------------------------------------------------------------------ PD arrays
T = datetime(2025, 3, 4, 14, 0, tzinfo=UTC)


def seq(rows):
    bars = [Bar(T + timedelta(minutes=5 * (k + 1)), *r) for k, r in enumerate(rows)]
    return bars, (lambda k: bars[k])


def test_fvg_ce_and_no_retroactive_fill():
    cfg = v2cfg()
    bars, get = seq([(100, 101, 99, 100.5), (100.5, 104, 100.4, 103.8), (103.8, 104.5, 102, 104)])
    z = arrays.fvg(get, 1, 1, 2, 2.0, cfg)
    assert (z["lo"], z["hi"], z["entry"]) == (101, 102, 101.5)
    bars2, get2 = seq([(100, 101, 99, 100.5), (100.5, 104, 100.4, 103.8), (103.8, 104.5, 102, 104),
                       (104, 104.2, 101.4, 103)])
    assert arrays.fvg(get2, 1, 1, 3, 2.0, cfg) is None  # already retraced to CE


def test_inverse_fvg_order_block_breaker_and_ote():
    cfg = v2cfg()
    _, get = seq([(105, 106, 104, 104.2), (104.2, 104.3, 101, 101.2), (101.2, 102, 100, 101.5),
                  (101.5, 104.8, 101.4, 104.6)])
    z = arrays.ifvg(get, 1, 3, 2.0, {**cfg, "ifvg_lookback": 3})
    assert (z["array"], z["lo"], z["hi"], z["entry"]) == ("ifvg", 102, 104, 103)
    _, get = seq([(101, 101.5, 99, 99.5), (99.5, 103, 99.4, 102.9), (102.9, 103.5, 102, 103.2)])
    z = arrays.order_block(get, 1, 1, 2, cfg, 0)
    assert (z["lo"], z["hi"], z["entry"]) == (99, 101.5, 100.25)
    _, get = seq([(100, 102, 99.8, 101.8), (101.8, 101.9, 98, 98.2), (98.2, 98.5, 97, 98.3),
                  (98.3, 102.6, 98.2, 102.4), (102.4, 103, 101.5, 102.8)])
    z = arrays.breaker(get, 1, 2, 4, cfg, 0)
    assert (z["array"], z["lo"], z["hi"]) == ("breaker", 99.8, 102) and z["entry"] == pytest.approx(100.9)
    z = arrays.ote_zone(get, 1, 2, 97, 4, cfg)
    assert z["lo"] == pytest.approx(103 - 0.79 * 6) and z["hi"] == pytest.approx(103 - 0.62 * 6)
    assert z["entry"] == pytest.approx(103 - 0.705 * 6)


def test_smt_divergence_with_companion():
    t = [T + timedelta(minutes=5 * k) for k in range(6)]
    held = CompanionSeries([Bar(x, 50.5, 51, 50 if k == 1 else 50.2, 50.5) for k, x in enumerate(t)])
    took = CompanionSeries([Bar(x, 50.5, 51, 50 if k == 1 else (49.5 if k == 4 else 50.2), 50.5) for k, x in enumerate(t)])
    assert held.diverges(t[1], t[5], "LOW") is True      # companion held its low: bullish SMT
    assert took.diverges(t[1], t[5], "LOW") is False     # companion also swept it: no SMT
    assert took.diverges(t[1], t[3], "LOW") is True      # as-of: the later sweep is not visible yet
    assert held.diverges(t[0] - timedelta(minutes=1), t[5], "LOW") is None


# ------------------------------------------------------------------ simulator
def test_adapter_flat_at_closes_positions_and_cancels_orders():
    cfg = v2cfg(fee_rate=0.0, slippage_bps=0.0)
    t = datetime(2025, 3, 4, 16, 40, tzinfo=UTC)  # 11:40 NY
    flat = t + timedelta(minutes=20)
    sig = {"signal_id": "a", "known_at": t.isoformat(), "expires_at": flat.isoformat(), "flat_at": flat.isoformat(),
           "direction": 1, "entry": 100.0, "stop": 98.0, "target": 106.0, "qty": 1.0, "risk_eur": 2.0}
    a = SimulationAdapter(cfg)
    a.create(sig)
    a.on_bar(Bar(t + timedelta(minutes=5), 101, 101, 99.5, 100.5), 0.0)
    a.on_bar(Bar(t + timedelta(minutes=10), 100.5, 101, 100, 100.8), 0.0)
    a.on_bar(Bar(t + timedelta(minutes=15), 100.8, 101, 100.2, 101), 0.0)
    out = a.on_bar(Bar(t + timedelta(minutes=20), 101, 101.5, 100.5, 101.2), 0.0)
    assert out and out[0]["reason"] == "SESSION_END"


def test_stress_reprices_the_same_trades():
    cfg = v2cfg(fee_rate=0.0001, slippage_bps=1.0)
    base = [{"direction": 1, "entry": 100.0, "exit_price": 98.0 - 0.01, "reason": "STOP", "qty": 2.0,
             "slippage": 0.01, "risk_eur": 4.1, "gross_eur": 0, "fees_eur": 0, "net_eur": 0, "R": 0},
            {"direction": -1, "entry": 100.0, "exit_price": 96.0, "reason": "TARGET", "qty": 1.0,
             "slippage": 0.01, "risk_eur": 2.0, "gross_eur": 0, "fees_eur": 0, "net_eur": 0, "R": 0}]
    res = RunResult(cfg=cfg, trades=base)
    out = protocol.reprice(res, cfg, "costs_1.5x").trades
    assert len(out) == 2
    assert out[0]["exit_price"] == pytest.approx(98.0 - 0.015)  # stop slippage x1.5
    assert out[1]["exit_price"] == 96.0                           # limit target: no slippage
    fee0 = 0.0001 * (out[0]["exit_price"] + 100.0) * 2.0 * 1.5
    assert out[0]["fees_eur"] == pytest.approx(fee0)
    assert out[1]["gross_eur"] == pytest.approx(4.0)


# ------------------------------------------------------------------ engine end to end
@pytest.fixture(scope="module")
def runs():
    bars, comp = market(70, 21, companion=True, spread=None)
    cfg = v2cfg(**LOOSE)
    full = run_v2(bars, cfg, companion=CompanionSeries(comp))
    cut = bars[len(bars) * 2 // 3].ts
    part = run_v2([b for b in bars if b.ts <= cut], cfg, companion=CompanionSeries([b for b in comp if b.ts <= cut]))
    return bars, cfg, full, part, cut


def test_all_three_models_and_several_arrays_trade(runs):
    _, _, full, _, _ = runs
    models = {t["model"] for t in full.trades}
    arrays_used = {t["array"] for t in full.trades}
    assert models == {"reversal", "continuation", "silver_bullet"}
    assert {"fvg"} < arrays_used
    assert any(t["smt"] is True for t in full.intents)
    assert full.extra["gaps"].get("scheduled", 0) > 0 and full.extra["gaps"].get("unexpected", 0) == 0


def test_prefix_invariance_no_lookahead(runs):
    _, _, full, part, cut = runs
    early_full = [s for s in full.intents if datetime.fromisoformat(s["known_at"]) <= cut]
    assert early_full == part.intents
    assert len(part.intents) > 10


def test_every_intent_respects_the_rules(runs):
    _, cfg, full, _, _ = runs
    tick = cfg["tick_size"]
    for s in full.intents:
        k = datetime.fromisoformat(s["known_at"])
        flat = datetime.fromisoformat(s["flat_at"])
        assert windows.decision_window(k, cfg) is not None
        assert flat - k >= timedelta(minutes=cfg["no_entry_before_flat_minutes"])
        assert datetime.fromisoformat(s["expires_at"]) <= flat
        d = s["direction"]
        assert d * (s["entry"] - s["stop"]) > 0 and d * (s["target"] - s["entry"]) > 0
        lo, hi = s["zone"]
        assert lo - tick <= s["entry"] <= hi + tick
        assert s["score"] == sum(1 for v in s["confluence"].values() if v) >= cfg["min_confluence"]
        assert s["net_rr"] >= cfg["min_net_rr"]
        assert s["risk_eur"] <= cfg["initial_equity"] * cfg["risk_fraction"] * 1.5  # equity drifts with P&L


def test_no_edge_on_random_walk_at_zero_cost():
    trades = []
    for seed in (31, 32, 33):
        bars = market(60, seed, spread=None)
        cfg = v2cfg(**{**LOOSE, "spread_price": 0.0, "slippage_bps": 0.0, "fee_rate": 0.0})
        trades += run_v2(bars, cfg).trades
    assert len(trades) >= 80
    mean = sum(t["R"] for t in trades) / len(trades)
    sd = (sum((t["R"] - mean) ** 2 for t in trades) / (len(trades) - 1)) ** 0.5
    assert mean / (sd / len(trades) ** 0.5) < 2.0, mean


# ------------------------------------------------------------------ calibration
def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_calibration_is_pnl_blind_and_closest_to_target():
    bars = market(45, 41, spread=None)
    meta = {"source": "SYNTH", "symbol": "US100", "data_sha256": "x",
            "instrument_overrides": {"spread_mode": "fixed", "spread_price": 0.5, "tick_size": 0.25}}
    out = calibrate.calibrate(bars, meta, profile="capital-us100-cfd", overrides={}, dev_end=bars[-1].ts,
                              target=0.6, log=lambda *_: None)
    forbidden = {"net", "net_eur", "R", "mean_R", "gross", "gross_eur", "pnl", "fees_eur", "net_total", "profit_factor"}
    assert not forbidden & set(_keys(out)) and out["pnl_blind"]
    best = min(out["levels"], key=lambda r: (abs(r["per_day"] - 0.6), r["level"]))
    assert out["chosen_level"] == best["level"]
    assert out["levels"][-1]["per_day"] >= out["levels"][0]["per_day"]
    json.dumps(out)
    # the chosen overrides rebuild a valid v2 config
    config.build("capital-us100-cfd", out["chosen_overrides"], engine="v2")


def test_futures_csv_path_with_roll_and_companion(tmp_path):
    """24h CME bars from CSV (e.g. Databento): roll resets context, MES is the SMT companion of MNQ."""
    from ict_engine import data_csv
    nq, es = market(16, 51, companion=True, spread=None)
    roll = nq[len(nq) // 2].ts
    lines = ["symbol,contract,start,end,open,high,low,close,volume"]
    for sym, bars, off in (("MNQ", nq, 40.0), ("MES", es, 10.0)):
        for b in bars:
            new = b.ts >= roll
            c = f"{sym}{'M5' if new else 'H5'}"
            o = off if new else 0.0
            s = b.ts - timedelta(minutes=5)
            lines.append(f"{sym},{c},{s.isoformat()},{b.ts.isoformat()},{b.o + o},{b.h + o},{b.l + o},{b.c + o},10")
    path = tmp_path / "cme.csv"
    path.write_text("\n".join(lines) + "\n")
    bars, meta = data_csv.load(path, symbol="MNQ")
    comp, _ = data_csv.load(path, symbol="MES")
    assert len(meta["contract_changes"]) == 2
    cfg = config.build("cme-mnq", {**LOOSE, "news_enabled": False, "drawdown_policy": "record"}, engine="v2")
    assert cfg["asset_class"] == "future"
    res = run_v2(bars, cfg, companion=CompanionSeries(comp), contract_changes=meta["contract_changes"])
    assert res.extra["gaps"]["roll"] == 1 and res.extra["gaps"].get("unexpected", 0) == 0
    assert res.intents and all(float(s["qty"]).is_integer() for s in res.intents)
    # no trade spans the roll
    for t in res.trades:
        assert not (datetime.fromisoformat(t["filled_at"]) < roll <= datetime.fromisoformat(t["exit_at"]))


def test_roll_flattens_open_positions_on_the_old_contract():
    cfg = v2cfg(fee_rate=0.0, slippage_bps=0.0)
    t = datetime(2025, 3, 4, 15, 0, tzinfo=UTC)
    flat = t + timedelta(hours=1)
    a = SimulationAdapter(cfg)
    a.create({"signal_id": "r", "known_at": t.isoformat(), "expires_at": flat.isoformat(), "flat_at": flat.isoformat(),
              "direction": 1, "entry": 100.0, "stop": 98.0, "target": 106.0, "qty": 1.0, "risk_eur": 2.0})
    a.on_bar(Bar(t + timedelta(minutes=5), 101, 101, 99.5, 100.5), 0.0)
    last_old = Bar(t + timedelta(minutes=10), 100.5, 101.5, 100.2, 101.0)
    a.on_bar(last_old, 0.0)
    out = a.flatten(last_old, 0.0)
    assert out[0]["reason"] == "ROLL" and out[0]["exit_price"] == 101.0 and not a.exposure()
