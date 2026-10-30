import json
from datetime import date, datetime, timedelta, timezone

from ict_engine import protocol, report
from ict_engine.bars import Bar
from test_sentinel import RELAX, path_bars

UTC = timezone.utc


def _bars(months, start=datetime(2023, 1, 1, tzinfo=UTC)):
    out = []
    t = start
    end = start + timedelta(days=int(months * 30.44))
    while t < end:
        t += timedelta(minutes=5)
        out.append(Bar(t, 100, 101, 99, 100))
    return out


def test_plan_holdout_last_12_months_and_folds():
    p = protocol.plan(_bars(37))
    assert p["months"] == 37
    assert p["holdout_start"] == date(2025, 2, 1) and p["end"] == date(2026, 2, 1)
    assert p["folds"][0] == (date(2024, 1, 1), date(2024, 4, 1))
    assert len(p["folds"]) == 4  # 25 development months: 12 + 4 x 3
    short = protocol.plan(_bars(18))
    assert short["holdout_start"] is None


def test_holdout_receipt_is_one_use(tmp_path):
    h = (date(2025, 1, 1), date(2026, 1, 1))
    assert protocol.check_or_write_receipt(tmp_path, "cfgA", "data", h, unseal=False) == "sealed"
    assert protocol.check_or_write_receipt(tmp_path, "cfgA", "data", h, unseal=True) == "opened_now"
    assert protocol.check_or_write_receipt(tmp_path, "cfgA", "data", h, unseal=True) == "consumed_same_config"
    assert protocol.check_or_write_receipt(tmp_path, "cfgB", "data", h, unseal=True) == "consumed_by_other_config"


def test_boundary_purge():
    t = {"known_at": "2025-01-31T23:00:00+00:00", "exit_at": "2025-02-01T00:10:00+00:00"}
    assert protocol.period_trades([t], date(2025, 1, 1), date(2025, 2, 1)) == []
    assert protocol.period_trades([t], date(2025, 2, 1), date(2025, 3, 1)) == []


def test_end_to_end_report_on_synthetic_data(tmp_path):
    bars = path_bars(400, seed=3)  # ~13 months: development only, no holdout
    meta = {"source": "SYNTHETIC", "symbol": "SYNTH", "data_sha256": "synthetic-3"}
    over = {k: v for k, v in RELAX.items() if k != "drawdown_policy"}
    res = protocol.evaluate(bars, meta, profile="binance-btcusdt-spot", overrides=over, out_root=tmp_path,
                            label="e2e", log=lambda *_: None)
    assert res["holdout"]["status"] == "unavailable"
    assert res["verdict"]["label"] == "RESEARCH"
    assert res["dev"]["metrics"]["trades"] > 0
    assert set(res["dev_stress"]) == {"costs_1.5x", "costs_2x", "slippage_3x"}
    assert res["news_filter"].startswith("not_applied")
    path = report.write(res, tmp_path / "e2e" / "REPORT.md")
    text = path.read_text()
    assert "Verdetto: RESEARCH" in text and "Imbuto dei setup" in text
    reg = json.loads((tmp_path / "trials.json").read_text())
    assert len(reg) == 1 and reg[0]["scope"] == "dev"
    # identical rerun does not duplicate the trial
    protocol.evaluate(bars, meta, profile="binance-btcusdt-spot", overrides=over, out_root=tmp_path,
                      label="e2e", log=lambda *_: None)
    assert len(json.loads((tmp_path / "trials.json").read_text())) == 1
