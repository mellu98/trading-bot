"""Read-only ledger diagnostics; not a backtest, parameter search or signal filter."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "reports/quant-validation/bars120.csv"
EXPECTED_DATA = "b5d3e676d1de881a8bd1a07eedccc14f286a615db0d7b4169f9950fead600ff5"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    with path.open(newline="") as source:
        return list(csv.DictReader(source))


def dt(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    assert result.utcoffset() == timedelta(0), "Expected explicit UTC"
    return result


def close_enough(a: float, b: float) -> None:
    assert math.isclose(a, b, abs_tol=1e-7), (a, b)


def main() -> None:
    assert digest(DATA) == EXPECTED_DATA
    paths = [DATA, ROOT / "reports/research-v2/results.json",
             ROOT / "reports/research-v2/protocol.json",
             ROOT / "reports/offline-hardening/research-verification.json"]
    original = json.loads(paths[1].read_text())
    stress = json.loads(paths[3].read_text())
    bars = rows(DATA)
    assert len(bars) == 93600
    index = {(b["symbol"], b["contract"], b["start"]): b for b in bars}
    assert len(index) == len(bars)
    # Causal denominator: 20 completed bars preceding entry, within one session.
    prior_ranges = {}
    groups = defaultdict(list)
    for b in bars:
        assert dt(b["available_at"]) >= dt(b["end"]) > dt(b["start"])
        groups[b["symbol"], b["contract"], b["start"][:10]].append(b)
    for group in groups.values():
        group.sort(key=lambda b: int(b["ts_event_ns"]))
        for i in range(20, len(group)):
            history = group[i-20:i]
            assert all(dt(b["available_at"]) <= dt(group[i]["start"]) for b in history)
            prior_ranges[group[i]["symbol"], group[i]["contract"], group[i]["start"]] = statistics.median(
                float(b["high"]) - float(b["low"]) for b in history)
    result = {"status": "EXPLORATORY_FIXED_LEDGER_DIAGNOSTICS_NOT_A_NEW_BACKTEST",
              "independent_holdout": False, "new_network_requests": 0,
              "bars": len(bars), "sessions": len({b["start"][:10] for b in bars}),
              "method": "Daily-reset diagnostic ledgers, not deployable portfolio returns. "
                        "Markouts ignore actual exits, overlap and later risk state; no strategy P&L claim. "
                        "Entry-bar range and holding duration are retrospective diagnostics only. "
                        "Prior20 range uses only completed, available same-session bars. "
                        "Execution costs are assumptions, not observed bid/ask or empirical slippage.",
              "arms": {}}
    for symbol, point in (("MNQ", 2.0), ("MES", 5.0)):
        for strategy in ("vwap_v1_fixed", "orb", "sweep_mss"):
            name = f"{symbol}/{strategy}"
            path = ROOT / f"reports/research-v2/results/{name}/daily_reset_diagnostic/ticks1.0/trades.csv"
            paths.append(path)
            trades = rows(path)
            old = original["results"][name + "/daily_reset_diagnostic/ticks1.0"]
            assert len(trades) == old["trades"]
            values = {key: sum(float(t[key]) for t in trades)
                      for key in ("gross", "fees", "execution_cost", "net")}
            for key, value in values.items():
                close_enough(value, old[key])
            close_enough(values["gross"] - values["fees"] - values["execution_cost"], values["net"])
            duration, signal_ratio, entry_ratio, prior_ratio = [], [], [], []
            markouts = {h: [] for h in (1, 5, 15)}
            same_bar_stops, stops = 0, 0
            for t in trades:
                entry = dt(t["entry_at"])
                assert dt(t["signal_bar_start"]) < dt(t["signal_at"]) <= entry <= dt(t["exit_at"])
                elapsed = (dt(t["exit_at"]) - entry).total_seconds() / 60
                duration.append(elapsed)
                if t["reason"] == "stop":
                    stops += 1
                    same_bar_stops += elapsed <= 1
                stop = abs(float(t["raw_entry"]) - float(t["stop"]))
                assert stop > 0
                for field, output in (("signal_bar_start", signal_ratio), ("entry_at", entry_ratio)):
                    b = index[symbol, t["contract"], t[field]]
                    output.append((float(b["high"]) - float(b["low"])) / stop)
                key = symbol, t["contract"], t["entry_at"]
                if key in prior_ranges:
                    prior_ratio.append(prior_ranges[key] / stop)
                for horizon, output in markouts.items():
                    # Close of exactly H contiguous same-session bars from the raw entry.
                    interval = [(entry + timedelta(minutes=i)).isoformat() for i in range(horizon)]
                    if any(stamp[:10] != t["entry_at"][:10] or
                           (symbol, t["contract"], stamp) not in index for stamp in interval):
                        continue
                    b = index[symbol, t["contract"], interval[-1]]
                    pnl = int(t["side"]) * (float(b["close"]) - float(t["raw_entry"])) * point
                    output.append(pnl)
            costs = (values["fees"] + values["execution_cost"]) / len(trades)
            loss = abs(float(trades[0]["raw_entry"]) - float(trades[0]["stop"])) * point
            win = abs(float(trades[0]["target"]) - float(trades[0]["raw_entry"])) * point
            result["arms"][name] = {
                "trades": len(trades), **values, "win_rate": old["win_rate"],
                "profit_factor": old["profit_factor"], "cost_per_roundtrip": costs,
                "gross_per_trade": values["gross"] / len(trades),
                "net_without_slippage_fixed_ledger": values["gross"] - values["fees"],
                "idealized_binary_target_stop_break_even_win_rate": (loss + costs) / (loss + win),
                "median_duration_minutes_bar_bound": statistics.median(duration),
                "stops": stops, "stop_in_entry_minute": same_bar_stops,
                "fraction_stops_in_entry_minute": same_bar_stops / stops,
                "signal_bar_range_over_stop_median": statistics.median(signal_ratio),
                "entry_bar_range_over_stop_median_retrospective": statistics.median(entry_ratio),
                "prior20_median_range_over_stop_median": statistics.median(prior_ratio),
                "prior20_eligible_trades": len(prior_ratio),
                "markout_gross_per_trade_diagnostic_only": {
                    str(h): {"n": len(v), "mean_usd": statistics.mean(v), "median_usd": statistics.median(v)}
                    for h, v in markouts.items()},
                "ambiguous_intrabar": old["ambiguous_intrabar"],
                "excluding_ambiguous_descriptive": old["excluding_ambiguous_descriptive"],
                "by_regime": old["by_regime"], "by_time": old["by_time"],
                "positive_months": sum(v["net"] > 0 for v in old["by_month"].values()),
                "positive_20session_blocks": sum(v["net"] > 0 for v in old["temporal_blocks"]),
                "block5_mean_daily_net_ci95": old["uncertainty"]["by_block_length"]["5"]["ci95"],
                "adverse_cost_scenario_net": stress["one_predeclared_cost_stress"][name]["net"],
            }
    result["input_sha256"] = {str(p.relative_to(ROOT)): digest(p) for p in paths}
    for p in paths:
        assert digest(p) == result["input_sha256"][str(p.relative_to(ROOT))]
    target = Path(__file__).with_name("diagnostics.json")
    target.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "arms_reconciled": len(result["arms"]),
                      "sessions": result["sessions"], "diagnostics_sha256": digest(target)}))


if __name__ == "__main__":
    main()
