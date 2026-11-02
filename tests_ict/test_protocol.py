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


def test_holdout_seal_is_one_use_per_market(tmp_path):
    h = (date(2025, 1, 1), date(2026, 1, 1))
    m = "capital|US100"
    assert protocol.holdout_state(tmp_path, m, h, "cfgA", "data", unseal=False) == "sealed"
    assert protocol.holdout_state(tmp_path, m, h, "cfgA", "data", unseal=True) == "opened_now"
    assert protocol.holdout_state(tmp_path, m, h, "cfgA", "data", unseal=True) == "consumed_same_config"
    assert protocol.holdout_state(tmp_path, m, h, "cfgB", "data", unseal=True) == "consumed_by_other_config"
    # other market: independent seal
    assert protocol.holdout_state(tmp_path, "capital|US500", h, "cfgB", "data", unseal=False) == "sealed"


def test_seal_ignores_label_and_blocks_overlapping_windows(tmp_path):
    """Francesco's finding: a different label (or --set) used to reopen the same holdout."""
    m = "binance|BTCUSDT"
    assert protocol.holdout_state(tmp_path, m, (date(2025, 1, 1), date(2026, 1, 1)), "cfgA", "d1", True) == "opened_now"
    # same config, data re-downloaded later: the 12-month window moved and overlaps the opened one
    later = (date(2025, 4, 1), date(2026, 4, 1))
    assert protocol.holdout_state(tmp_path, m, later, "cfgA", "d2", True) == "consumed_by_other_config"
    # a development period that overlaps the opened window is flagged
    assert protocol.contaminated_by(tmp_path, m, date(2024, 1, 1), date(2025, 4, 1))
    assert not protocol.contaminated_by(tmp_path, m, date(2023, 1, 1), date(2025, 1, 1))


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


def test_holm_family_includes_older_a1_trials_of_the_same_market():
    items = [
        {"trial_id": "a1", "kind": "decision", "scope": "dev", "dataset_key": "capital|US100|979c74ecaa4dedf6", "p_one_sided": 1.0},
        {"trial_id": "v2", "kind": "decision", "scope": "dev", "dataset_key": "capital|US100", "p_one_sided": 0.03},
        {"trial_id": "cal", "kind": "calibration", "scope": "dev", "dataset_key": "capital|US100"},
        {"trial_id": "other", "kind": "decision", "scope": "dev", "dataset_key": "capital|US500", "p_one_sided": 0.01},
    ]
    h = protocol.family_holm(items, "capital|US100", "dev")
    assert set(h) == {"a1", "v2"} and h["v2"]["family_size"] == 2
