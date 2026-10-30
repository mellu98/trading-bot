import hashlib
import io
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from conftest import REFERENCE, T0, bar
from ict_engine import config
from ict_engine.bars import Bar, aggregate, dedupe_sorted, segments
from ict_engine.execution import SimulationAdapter
from ict_engine.risk import RiskLedger, RiskState, gate
from ict_engine.sizing import size
from ict_engine.stats import bootstrap_mean_r, holm

UTC = timezone.utc


# ------------------------------------------------------------------ package
def test_reference_suite_shipped_with_package_still_passes():
    out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(REFERENCE / "tests")],
                         capture_output=True, text=True, cwd=str(REFERENCE))
    assert out.returncode == 0, out.stderr[-2000:]
    assert "Ran 33 tests" in out.stderr


def test_baseline_is_the_package_config():
    assert config.baseline_matches_package()


def test_live_mode_and_unimplemented_filters_rejected():
    with pytest.raises(ValueError):
        config.build("synthetic", {"mode": "live"})
    with pytest.raises(ValueError):
        config.build("synthetic", {"htf_filter": True})
    with pytest.raises(ValueError):
        config.build("synthetic", {"not_a_key": 1})
    with pytest.raises(ValueError):
        config.build("synthetic", {"risk_fraction": 0.02, "risk_cap_fraction": 0.02})


def test_scenarios_scale_costs_and_change_hash():
    base = config.build("binance-btcusdt-spot")
    stress = config.build("binance-btcusdt-spot", scenario="costs_1.5x")
    assert stress["fee_rate"] == pytest.approx(base["fee_rate"] * 1.5)
    assert stress["slippage_bps"] == pytest.approx(base["slippage_bps"] * 1.5)
    assert config.config_hash(base) != config.config_hash(stress)
    assert config.strategy_hash(base) == config.strategy_hash(stress)  # same hypothesis


# ------------------------------------------------------------------ sizing
def test_spec06_btc_example_500_eur():
    cfg = config.build("binance-btcusdt-spot", {"quote_to_eur": 1 / 1.10, "slippage_price": 50, "slippage_bps": None,
                                                  "risk_fraction": 0.01, "available_cash_eur": 500})
    s = size(500, 100000, 99000, 103000, 1, cfg)
    assert s["qty"] == pytest.approx(0.00440)
    assert s["risk_eur"] <= 5.0


def test_size_never_rounds_up_and_rejects_short_spot():
    cfg = config.build("binance-btcusdt-spot", {"min_qty": 0.01})
    assert size(500, 100000, 99000, 103000, 1, cfg)["reason"] == "SKIP_MINIMUM_SIZE"
    assert size(500, 100000, 101000, 97000, -1, cfg)["reason"] == "SKIP_SHORT_UNSUPPORTED"


def test_futures_margin_mode_integer_contracts():
    cfg = config.build("cme-mnq")
    s = size(100000, 20000, 19980, 20060, 1, cfg)
    assert s["qty"] == int(s["qty"]) and s["qty"] >= 1
    small = config.build("cme-mnq", {"initial_equity": 5000})
    assert size(5000, 20000, 19980, 20060, 1, small)["reason"] == "SKIP_MINIMUM_SIZE"


# ------------------------------------------------------------------ execution
def _sig(**kw):
    s = {"signal_id": "x", "known_at": T0.isoformat(), "expires_at": (T0 + timedelta(minutes=30)).isoformat(),
         "direction": 1, "entry": 100.0, "stop": 98.0, "target": 104.0, "qty": 1.0, "risk_eur": 2.0}
    s.update(kw)
    return s


def _cfg():
    return config.build("synthetic", {"fee_rate": 0.0, "slippage_price": 0.0})


def test_no_fill_on_generating_bar_and_no_target_on_entry_bar():
    a = SimulationAdapter(_cfg())
    a.create(_sig())
    assert a.on_bar(Bar(T0, 100, 105, 99, 101), 0.0) == []  # generating bar (ts == known_at)
    out = a.on_bar(bar(0, 101, 105, 99.5, 104), 0.0)  # fills and touches target: not credited
    assert out == [] and a.orders["x"]["status"] == "OPEN"
    out = a.on_bar(bar(1, 104, 104.5, 103, 104), 0.0)
    assert out[0]["reason"] == "TARGET"


def test_stop_first_and_gap_through_stop():
    a = SimulationAdapter(_cfg())
    a.create(_sig())
    a.on_bar(bar(0, 101, 101, 99.9, 100.5), 0.0)
    out = a.on_bar(bar(1, 100.5, 105, 97, 101), 0.0)
    assert out[0]["reason"] == "STOP" and out[0]["exit_price"] == 98.0
    b = SimulationAdapter(_cfg())
    b.create(_sig(signal_id="y"))
    b.on_bar(bar(0, 101, 101, 99.9, 100.5), 0.0)
    out = b.on_bar(bar(1, 96, 97, 95, 96), 0.0)
    assert out[0]["exit_price"] == 96.0 and out[0]["R"] < -1


def test_optimistic_bound_only_changes_ambiguous_bars():
    a = SimulationAdapter(_cfg(), optimistic=True)
    a.create(_sig())
    a.on_bar(bar(0, 101, 101, 99.9, 100.5), 0.0)
    out = a.on_bar(bar(1, 100.5, 105, 97, 101), 0.0)
    assert out[0]["reason"] == "TARGET" and out[0]["ambiguous_bar"]


def test_expiry_session_end_target_consumed_and_gap_cancels():
    a = SimulationAdapter(_cfg())
    a.create(_sig())
    for i in range(6):
        a.on_bar(bar(i, 101, 102, 100.5, 101), 0.0)
    assert a.orders["x"]["status"] == "EXPIRED"
    # target reached before the entry: order cancelled
    b = SimulationAdapter(_cfg())
    b.create(_sig())
    b.on_bar(bar(0, 101, 104.5, 100.5, 104), 0.0)
    assert b.orders["x"]["cancel_reason"] == "CANCEL_TARGET_CONSUMED"
    # data gap cancels pending
    c = SimulationAdapter(_cfg())
    c.create(_sig())
    c.on_gap()
    assert c.orders["x"]["cancel_reason"] == "CANCEL_DATA_INVALID"


def test_session_cutoff_closes_position_and_cancels_orders():
    t = datetime(2026, 1, 5, 15, 45, tzinfo=UTC)  # 10:45 New York (EST)
    a = SimulationAdapter(_cfg())
    a.create(_sig(known_at=t.isoformat(), expires_at=(t + timedelta(hours=1)).isoformat()))
    a.on_bar(Bar(t + timedelta(minutes=5), 101, 101, 99.5, 100.5), 0.0)  # 10:50 fill
    a.on_bar(Bar(t + timedelta(minutes=10), 100.5, 101, 100, 100.8), 0.0)  # 10:55
    out = a.on_bar(Bar(t + timedelta(minutes=15), 100.8, 101.2, 100.4, 101), 0.0)  # bar ends 11:00
    assert out[0]["reason"] == "SESSION_END"
    b = SimulationAdapter(_cfg())
    b.create(_sig(known_at=(t + timedelta(minutes=10)).isoformat(), expires_at=(t + timedelta(hours=1)).isoformat()))
    b.on_bar(Bar(t + timedelta(minutes=15), 101, 102, 100.5, 101), 0.0)  # 10:55-11:00 not touched
    b.on_bar(Bar(t + timedelta(minutes=20), 101, 102, 99, 101), 0.0)     # starts 11:00 -> cancel, no fill
    assert b.orders["x"]["cancel_reason"] == "CANCEL_SESSION_END"


def test_idempotence_and_conflict():
    a = SimulationAdapter(_cfg())
    first = a.create(_sig())
    assert a.create(_sig()) is first
    with pytest.raises(ValueError):
        a.create(_sig(entry=99.0))


def test_live_forbidden_in_simulator():
    with pytest.raises(ValueError):
        SimulationAdapter({**_cfg(), "mode": "live"})


# ------------------------------------------------------------------ risk
def test_risk_gate_order_and_ledger_resets():
    cfg = config.build("binance-btcusdt-spot")
    assert gate(RiskState(halted=True, drawdown=0.5), cfg) == "DISABLE_KILL_SWITCH"
    led = RiskLedger(cfg)
    d1 = datetime(2026, 1, 5, 13, tzinfo=UTC)
    for _ in range(3):
        led.on_close(d1, -1.0)
    assert gate(led.state(d1, exposure=False), cfg) == "SKIP_LOSS_STREAK"
    led.on_close(d1, 0.0)  # zero interrupts the streak (spec 06)
    assert led.consecutive_losses == 0
    led.on_close(d1, -1.0)
    assert led.state(d1 + timedelta(days=1), exposure=False).consecutive_losses == 0  # new UTC day


def test_drawdown_halt_vs_record():
    halt = RiskLedger(config.build("binance-btcusdt-spot"))
    rec = RiskLedger(config.build("binance-btcusdt-spot", {"drawdown_policy": "record"}))
    t = datetime(2026, 1, 5, 13, tzinfo=UTC)
    for led in (halt, rec):
        led.on_close(t, -50.0)  # -10 %
    assert gate(halt.state(t, exposure=False), halt.cfg) == "DISABLE_KILL_SWITCH"
    assert rec.first_drawdown_breach and not rec.halted


# ------------------------------------------------------------------ bars
def test_aggregate_only_complete_groups_and_segments():
    m1 = [Bar(T0 + timedelta(minutes=i + 1), 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(12)]
    m5 = aggregate(m1, 60, 300)
    assert len(m5) == 2 and m5[0].o == 100 and m5[0].c == 104.5 and m5[0].h == 105
    gap = m5 + [Bar(m5[-1].ts + timedelta(minutes=15), 120, 121, 119, 120)]
    assert len(segments(gap, 300)) == 2


def test_discordant_duplicates_quarantined():
    a = Bar(T0, 100, 101, 99, 100)
    b = Bar(T0, 100, 102, 99, 100)
    clean, info = dedupe_sorted([a, a, b, Bar(T0 + timedelta(minutes=5), 100, 101, 99, 100)])
    assert len(clean) == 1 and info["discordant_quarantined"]


# ------------------------------------------------------------------ data
def test_binance_loader_handles_microseconds_and_refuses_tampering(tmp_path):
    from ict_engine import data_binance
    rows = []
    start = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(3):
        us = int((start + timedelta(minutes=5 * i)).timestamp() * 1_000_000)
        rows.append(f"{us},100,101,99,100.5,10,{us + 299_999_999},0,0,0,0,0")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("BTCUSDT-5m-2025-01.csv", "\n".join(rows))
    body = buf.getvalue()
    path = data_binance.archive_path(tmp_path, "BTCUSDT", "5m", "2025-01")
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    manifest = {"source": "test", "symbol": "BTCUSDT", "interval": "5m", "months": ["2025-01"],
                "files": [{"url": "x/" + path.name, "sha256": hashlib.sha256(body).hexdigest()}]}
    (tmp_path / "binance" / "manifest-BTCUSDT-5m.json").write_text(json.dumps(manifest))
    bars, meta = data_binance.load(tmp_path)
    assert len(bars) == 3 and bars[0].ts == start + timedelta(minutes=5)
    path.write_bytes(body + b"x")
    with pytest.raises(SystemExit):
        data_binance.load(tmp_path)


def test_capital_history_is_read_only():
    from ict_engine import data_capital

    class FakeHTTP:
        orders_enabled = True
    with pytest.raises(ValueError):
        data_capital.ReadOnlyHistory(FakeHTTP())
    assert not data_capital.ROUTE.fullmatch("/positions")
    assert not data_capital.ROUTE.fullmatch("/prices/US100?resolution=MINUTE_5&max=1000&from=2025-01-01T00:00:00&to=2025-01-02T00:00:00&x=1")
    row = data_capital._parse({"snapshotTimeUTC": "2025-01-02T14:35:00",
                               **{n + "Price": {"bid": 100, "ask": 100.5} for n in ("open", "close")},
                               "highPrice": {"bid": 101, "ask": 101.5}, "lowPrice": {"bid": 99, "ask": 99.5},
                               "lastTradedVolume": 12})
    assert row["start_utc"] == "2025-01-02T14:35:00Z"


# ------------------------------------------------------------------ stats
def test_bootstrap_and_holm():
    r = bootstrap_mean_r([1.0, -0.5, 0.0, 2.0] * 50, [1, 1, 0, 1] * 50, reps=2000)
    assert r["ci95"][0] < r["mean_R"] < r["ci95"][1] and r["p_one_sided"] < 0.05
    h = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert h["a"]["reject"] and not h["c"]["reject"] and not h["b"]["reject"]


def test_csv_loader_bot_databento_format_aggregates_and_splits_contracts(tmp_path):
    from ict_engine import data_csv
    from ict_engine.protocol import prepare_segments
    path = tmp_path / "bars120.csv"
    lines = ["symbol,contract,ts_event_ns,start,end,available_at,open,high,low,close,volume"]
    t = datetime(2026, 3, 13, 13, 30, tzinfo=UTC)
    for contract in ("MNQH6", "MNQM6"):
        for i in range(10):
            s = t + timedelta(minutes=i)
            e = s + timedelta(minutes=1)
            lines.append(f"MNQ,{contract},0,{s.isoformat()},{e.isoformat()},{e.isoformat()},100,101,99,100.5,5")
        t += timedelta(minutes=10)
    lines.append(f"MES,MESH6,0,{t.isoformat()},{(t + timedelta(minutes=1)).isoformat()},x,1,2,1,1,1")
    path.write_text("\n".join(lines) + "\n")
    bars, meta = data_csv.load(path, symbol="MNQ")
    assert len(bars) == 4 and meta["interval_seconds"] == 60
    cfg = config.build("cme-mnq")
    _, segs, qa = prepare_segments(bars, cfg, meta["contract_changes"])
    assert len(segs) == 2  # contiguous in time, but the roll forces a new segment
