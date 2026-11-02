"""Frequency calibration for engine v2, blind to profits.

Goal set by the user: about one trade per trading day per market. The ladder
below goes from the strictest ICT reading (all confluences, package
displacement) to looser ones, one documented step at a time. On the
DEVELOPMENT period only, each level is run with P&L feedback switched off
(fixed equity, no loss-based gates) and only the number of filled trades is
read. The level whose trades/day is closest to the target is chosen (ties ->
stricter). Profits are never computed into the output, so the choice cannot
be tuned on results; the protocol then evaluates that single frozen config
as one trial.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .backtest_v2 import run_v2
from .bars import dedupe_sorted

UTC = timezone.utc

# Cumulative steps, strictest first. Each entry: (label, overrides added at this level).
LADDER = [
    ("tutte le confluenze >= 4", {"min_confluence": 4}),
    ("confluenze >= 3", {"min_confluence": 3}),
    ("confluenze >= 2", {"min_confluence": 2}),
    ("displacement corpo >= 0,8 ATR", {"body_atr_min": 0.8}),
    ("confluenze >= 1", {"min_confluence": 1}),
    ("displacement 0,6 ATR, corpo 55%", {"body_atr_min": 0.6, "body_ratio_min": 0.55}),
    ("nessuna confluenza minima", {"min_confluence": 0}),
    ("displacement 0,45 ATR, corpo 50%, chiusura nel 30% estremo",
     {"body_atr_min": 0.45, "body_ratio_min": 0.5, "close_extreme_max": 0.3}),
    ("MSS entro 10 barre, FVG >= 0,05 ATR, ordine valido 12 barre",
     {"mss_ttl_bars": 10, "fvg_min_atr": 0.05, "order_ttl_bars": 12}),
    ("target: prima liquidità con RR >= minimo", {"target_mode": "nearest_rr"}),
    ("ingresso al 25% della zona (più vicino al prezzo)", {"entry_fraction": 0.25}),
    ("displacement 0,3 ATR, sweep fino a 0,8 ATR",
     {"body_atr_min": 0.3, "body_ratio_min": 0.45, "close_extreme_max": 0.35, "sweep_max_atr": 0.8}),
    ("killzone aggiuntiva", {"__extra_window__": True}),
    ("MSS senza displacement (solo chiusura oltre la struttura)",
     {"body_atr_min": 0.0, "body_ratio_min": 0.0, "close_extreme_max": 1.0}),
]

EXTRA_WINDOW = {"index": ["02:00", "05:00", "07:00"], "future": ["02:00", "05:00", "07:00"],
                "crypto": ["02:00", "05:00", "07:00"], "fx": ["13:00", "15:00", "16:00"]}

# Gates that read P&L are neutralised during calibration (frequency only).
BLIND = {"daily_loss_fraction": 1.0, "weekly_loss_fraction": 1.0, "max_consecutive_losses": 10**6,
         "drawdown_policy": "record"}


def level_overrides(profile: str, base: dict, level: int) -> dict:
    out = dict(base)
    asset = config.ASSET_CLASS.get(profile, "index")
    for _, step in LADDER[:level + 1]:
        step = dict(step)
        if step.pop("__extra_window__", False):
            w = copy.deepcopy(config.V2_PRESETS[asset]["windows"])
            w.append(EXTRA_WINDOW[asset])
            out["windows"] = sorted(w)
        out.update(step)
    return out


def calibrate(bars, data_meta: dict, *, profile: str, overrides: dict, dev_end: datetime, target: float = 1.0,
              companion=None, contract_changes=(), log=print) -> dict:
    clean, _ = dedupe_sorted(bars)
    base = {**data_meta.get("instrument_overrides", {}), **overrides, "news_enabled": False}
    rows = []
    for k in range(len(LADDER)):
        over = level_overrides(profile, base, k)
        cfg = config.build(profile, {**over, **BLIND}, engine="v2")
        res = run_v2(clean, cfg, end=dev_end, companion=companion, contract_changes=contract_changes,
                     fixed_equity=True)
        days = len(res.session_days)
        n = sum(1 for t in res.trades if datetime.fromisoformat(t["exit_at"]) <= dev_end)
        per_day = n / days if days else 0.0
        rows.append({"level": k, "step": LADDER[k][0], "trades": n, "trading_days": days,
                     "per_day": round(per_day, 3)})
        log(f"  livello {k:2d}: {per_day:5.2f} trade/giorno ({n} trade, {days} giorni) — {LADDER[k][0]}")
        if per_day >= target * 1.5:
            break  # looser levels only add trades
    best = min(rows, key=lambda r: (abs(r["per_day"] - target), r["level"]))
    chosen = level_overrides(profile, base, best["level"])
    chosen.pop("news_enabled", None)
    for key in data_meta.get("instrument_overrides", {}):
        chosen.pop(key, None)
    out = {
        "kind": "calibration", "pnl_blind": True, "target_per_day": target, "profile": profile,
        "market": f"{data_meta.get('source')}|{data_meta.get('symbol')}",
        "data_sha256": data_meta.get("data_sha256"), "dev_end": dev_end.isoformat(),
        "levels": rows, "chosen_level": best["level"], "chosen_per_day": best["per_day"],
        "chosen_overrides": chosen, "calibrated_at_utc": datetime.now(UTC).isoformat(),
        "note": "Solo conteggi di trade eseguiti nel periodo di sviluppo; nessun P&L calcolato nell'output.",
    }
    out["calibration_id"] = hashlib.sha256(json.dumps(
        {k: out[k] for k in ("profile", "market", "data_sha256", "dev_end", "chosen_overrides", "target_per_day")},
        sort_keys=True).encode()).hexdigest()[:16]
    return out


def path_for(out_root: Path, profile: str, symbol: str) -> Path:
    return out_root / "calibration" / f"{symbol}-{profile}.json"
