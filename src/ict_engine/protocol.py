"""Validation protocol 07 applied to A1: splits, sealed holdout, stress, benchmark, gates.

Splits (by calendar month, decided by the data, never chosen after results):
- holdout = last 12 full months, sealed; evaluated once, only with --unseal-holdout,
  which writes a receipt BEFORE computing anything. A different config afterwards
  cannot reuse it (protocol: a change after the sealed test is v2 and needs a new
  future period);
- development = everything before; validation folds = consecutive 3-month windows
  after the first 12 development months (expanding train, step 3). A1 has no
  fitted parameters, so folds measure stability, not tuning.
Trades whose [known_at, exit_at] crosses the holdout boundary are purged.

Every run is registered in reports/ict/trials.json (append-only). Holm uses the
whole family registered for the same dataset, discarded trials included.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import STRATEGY_VERSION, config
from .backtest import run
from .bars import dedupe_sorted, quality_report, segments
from .benchmark import random_matched
from .metrics import daily_series, trade_metrics
from .stats import autocorr1, bootstrap_mean, bootstrap_mean_r, holm

UTC = timezone.utc
CRYPTO_VENUES = ("binance-spot",)


# ------------------------------------------------------------------ calendar
def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, k: int) -> date:
    y, m = divmod(d.month - 1 + k, 12)
    return date(d.year + y, m + 1, 1)


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def full_months(bars) -> tuple[date, date]:
    """[first_full_month_start, end_exclusive) covered by the data."""
    first = bars[0].ts - timedelta(minutes=5)
    last = bars[-1].ts
    start = _month_start(first.date())
    if first > _dt(start) + timedelta(days=1):
        start = _add_months(start, 1)
    end = _month_start(last.date())
    if last >= _dt(_add_months(end, 1)) - timedelta(days=1):
        end = _add_months(end, 1)
    return start, end


def plan(bars) -> dict:
    start, end = full_months(bars)
    months = (end.year - start.year) * 12 + end.month - start.month
    holdout_start = _add_months(end, -12) if months >= 24 else None
    dev_end = holdout_start or end
    folds = []
    f = _add_months(start, 12)
    while _add_months(f, 3) <= dev_end:
        folds.append((f, _add_months(f, 3)))
        f = _add_months(f, 3)
    return {"start": start, "end": end, "months": months, "holdout_start": holdout_start,
            "dev_end": dev_end, "folds": folds}


# ------------------------------------------------------------------ helpers
def prepare_segments(bars, cfg, contract_changes=()):
    clean, info = dedupe_sorted(bars)
    qa = quality_report(clean, cfg["timeframe_seconds"], info)
    segs = segments(clean, cfg["timeframe_seconds"])
    if contract_changes:
        cuts = {datetime.fromisoformat(x) for x in contract_changes}
        split = []
        for seg in segs:
            cur = []
            for b in seg:
                if b.ts in cuts and cur:
                    split.append(cur)
                    cur = []
                cur.append(b)
            if cur:
                split.append(cur)
        segs = split
    qa["segments_after_contract_splits"] = len(segs)
    return clean, segs, qa


def _in(t, start: date, end: date) -> bool:
    k = datetime.fromisoformat(t["known_at"])
    return _dt(start) <= k < _dt(end)


def period_trades(trades, start: date, end: date):
    """Trades decided in [start, end) and closed before end (boundary purge)."""
    return [t for t in trades if _in(t, start, end) and datetime.fromisoformat(t["exit_at"]) <= _dt(end)]


def evaluate_period(res, start: date, end: date, *, ppy, rf, block=5, sensitivity=False):
    trades = period_trades(res.trades, start, end)
    equity0 = res.cfg["initial_equity"] + sum(t["net_eur"] for t in res.trades
                                              if datetime.fromisoformat(t["exit_at"]) < _dt(start))
    daily = daily_series(trades, start, end, equity0)
    eligible = sum(1 for d in res.session_days if start.isoformat() <= d < end.isoformat())
    span = (_dt(end) - _dt(start)).total_seconds()
    exposure = sum(t["held_bars"] for t in trades) * res.cfg["timeframe_seconds"] / span if span > 0 else None
    m = trade_metrics(trades, daily, periods_per_year=ppy, rf_annual=rf, eligible_days=eligible, exposure=exposure)
    boot = bootstrap_mean_r([d["R"] for d in daily], [d["n"] for d in daily], block=block)
    out = {"from": start.isoformat(), "to": end.isoformat(), "metrics": m, "bootstrap": boot,
           "daily_return": bootstrap_mean([d["ret"] for d in daily], block=block),
           "autocorr_lag1_daily": autocorr1([d["ret"] for d in daily])}
    if sensitivity:
        out["bootstrap_block_sensitivity"] = {
            str(b): bootstrap_mean_r([d["R"] for d in daily], [d["n"] for d in daily], block=b)["ci95"]
            for b in (1, 10, 20)}
    return out, trades


# ------------------------------------------------------------------ registry
def registry_path(out_root: Path) -> Path:
    return out_root / "trials.json"


def register(out_root: Path, entry: dict) -> list:
    path = registry_path(out_root)
    items = json.loads(path.read_text()) if path.exists() else []
    if not any(x["trial_id"] == entry["trial_id"] for x in items):
        items.append(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=1))
        tmp.replace(path)
    return items


def family_holm(items, dataset_key: str, scope: str) -> dict:
    fam = {x["trial_id"]: x["p_one_sided"] for x in items
           if x["dataset_key"] == dataset_key and x["scope"] == scope and x.get("kind") == "decision"}
    return holm(fam)


# ------------------------------------------------------------------ holdout seal
def holdout_receipt(out_dir: Path) -> Path:
    return out_dir / "holdout-receipt.json"


def check_or_write_receipt(out_dir: Path, cfg_hash: str, data_hash: str, holdout: tuple, unseal: bool) -> str:
    path = holdout_receipt(out_dir)
    if path.exists():
        receipt = json.loads(path.read_text())
        if receipt["config_hash"] != cfg_hash or receipt["data_sha256"] != data_hash:
            return "consumed_by_other_config"
        return "consumed_same_config"
    if not unseal:
        return "sealed"
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"config_hash": cfg_hash, "data_sha256": data_hash,
                                "holdout": [holdout[0].isoformat(), holdout[1].isoformat()],
                                "opened_at_utc": datetime.now(UTC).isoformat(),
                                "rule": "One evaluation of the frozen config. Any change = new version and new future holdout."},
                               indent=1))
    return "opened_now"


# ------------------------------------------------------------------ gates
def screening_verdict(dev: dict) -> dict:
    m, b = dev["metrics"], dev["bootstrap"]
    n = m["trades"]
    if n < 30:
        return {"label": "RESEARCH", "why": f"solo {n} trade nel periodo di sviluppo: campione insufficiente per qualsiasi giudizio"}
    if m["mean_R"] is not None and m["mean_R"] <= 0:
        sure = b["ci95"][1] is not None and b["ci95"][1] < 0
        return {"label": "REJECT (screening)",
                "why": "expectancy netta <= 0 nel periodo di sviluppo" + (" con CI95 interamente negativo" if sure else "")
                       + ": non conviene consumare l'holdout"}
    return {"label": "CANDIDATE", "why": "expectancy netta positiva nello sviluppo: ha senso aprire l'holdout una sola volta"}


def paper_gate(hold: dict, dev_folds: list, stress_hold: dict | None, robustness: dict | None,
               holm_result: dict | None, spread_known: bool, months_oos: int) -> dict:
    m, b = hold["metrics"], hold["bootstrap"]
    checks = {
        "N_oos>=200": m["trades"] >= 200,
        "days_with_trades>=60": m["days_with_trades"] >= 60,
        "oos_months>=12": months_oos >= 12,
        "CI95_lower_meanR>0": b["ci95"][0] is not None and b["ci95"][0] > 0,
        "holm_p<0.05": bool(holm_result and holm_result.get("reject")),
        "profit_factor>=1.15": m["profit_factor"] is not None and m["profit_factor"] >= 1.15,
        "folds_positive>=75%": bool(dev_folds) and sum(1 for f in dev_folds if (f["metrics"]["mean_R"] or 0) > 0) >= 0.75 * len(dev_folds),
        "max_dd<=8%": m["max_drawdown"] <= 0.08,
        "costs_1.5x_expectancy>0": bool(stress_hold) and (stress_hold["metrics"]["mean_R"] or 0) > 0,
        "neighbours_+-20%_positive>=70%": bool(robustness) and robustness.get("share_positive", 0) >= 0.70,
        "no_month>40%_of_profit": m["top_month_share_of_positive_net"] is not None and m["top_month_share_of_positive_net"] <= 0.40,
        "historical_spread_available": spread_known,
    }
    failed = [k for k, v in checks.items() if not v]
    if m["mean_R"] is not None and m["mean_R"] <= 0 and m["trades"] >= 30:
        label = "REJECT"
    elif not failed:
        label = "PAPER TRADE"
    else:
        label = "RESEARCH"
    return {"label": label, "checks": checks, "failed": failed}


# ------------------------------------------------------------------ main entry
def evaluate(bars, data_meta: dict, *, profile: str, overrides: dict, out_root: Path, label: str,
             events=None, unseal=False, robustness=False, log=print) -> dict:
    news_applied = bool(events)
    if not news_applied:
        overrides = {**overrides, "news_enabled": False}
    overrides = {**data_meta.get("instrument_overrides", {}), **overrides}
    research_over = {**overrides, "drawdown_policy": "record"}
    cfg = config.build(profile, research_over, "base")
    cfg_hash = config.config_hash(cfg)
    data_hash = data_meta["data_sha256"]
    ppy = 365 if cfg["venue"] in CRYPTO_VENUES else 252
    rf = 0.04
    clean, segs, qa = prepare_segments(bars, cfg, data_meta.get("contract_changes", ()))
    p = plan(clean)
    out_dir = out_root / label
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"Dati: {qa['bars']} barre, {qa['segments']} segmenti, {p['months']} mesi completi "
        f"({p['start']} -> {p['end']}).")
    if p["months"] < 13:
        raise SystemExit("servono almeno 13 mesi completi di dati (12 di sviluppo + 1 fold)")

    dev_end = p["dev_end"]
    log("Sviluppo: backtest A1 con costi base...")
    base_dev = run(segs, cfg, end=_dt(dev_end), events=events)
    dev, dev_trades = evaluate_period(base_dev, p["start"], dev_end, ppy=ppy, rf=rf, sensitivity=True)
    folds = [evaluate_period(base_dev, a, b, ppy=ppy, rf=rf)[0] for a, b in p["folds"]]

    log("Sviluppo: stress dei costi e limite ottimistico...")
    stress_dev = {}
    for scen in ("costs_1.5x", "costs_2x", "slippage_3x"):
        c = config.build(profile, research_over, scen)
        r = run(segs, c, end=_dt(dev_end), events=events)
        stress_dev[scen] = evaluate_period(r, p["start"], dev_end, ppy=ppy, rf=rf)[0]
    opt = run(segs, cfg, end=_dt(dev_end), events=events, optimistic=True)
    optimistic_dev = evaluate_period(opt, p["start"], dev_end, ppy=ppy, rf=rf)[0]

    log("Sviluppo: benchmark con ingressi casuali abbinati...")
    bench_dev = random_matched(dev_trades, segs, cfg, _dt(p["start"]), _dt(dev_end))

    # Account view with the spec's real halting rule (drawdown latches).
    account_cfg = config.build(profile, overrides, "base")
    account_dev = run(segs, account_cfg, end=_dt(dev_end), events=events)

    robust = None
    if robustness:
        log("Robustezza: parametri geometrici +-20% uno alla volta (solo sviluppo)...")
        rows = []
        for key in config.GEOMETRIC_KEYS:
            for mult in (0.8, 1.2):
                try:
                    c = config.build(profile, {**research_over, key: cfg[key] * mult}, "base")
                except ValueError as error:
                    rows.append({"param": key, "mult": mult, "error": str(error)})
                    continue
                r = run(segs, c, end=_dt(dev_end), events=events)
                ev = evaluate_period(r, p["start"], dev_end, ppy=ppy, rf=rf)[0]["metrics"]
                rows.append({"param": key, "mult": mult, "value": c[key], "trades": ev["trades"], "mean_R": ev["mean_R"]})
        valid = [r for r in rows if "mean_R" in r and r["mean_R"] is not None]
        robust = {"rows": rows, "share_positive": (sum(1 for r in valid if r["mean_R"] > 0) / len(valid)) if valid else 0.0}

    dataset_key = f"{data_meta.get('source')}|{data_meta.get('symbol')}|{data_hash[:16]}"
    entry_dev = {
        "trial_id": hashlib.sha256(f"{cfg_hash}|{data_hash}|dev".encode()).hexdigest()[:16],
        "kind": "decision", "scope": "dev", "dataset_key": dataset_key, "label": label,
        "strategy_version": STRATEGY_VERSION, "strategy_hash": config.strategy_hash(cfg), "config_hash": cfg_hash,
        "profile": profile, "overrides": overrides, "period": [p["start"].isoformat(), dev_end.isoformat()],
        "trades": dev["metrics"]["trades"], "mean_R": dev["metrics"]["mean_R"],
        "p_one_sided": dev["bootstrap"]["p_one_sided"], "registered_at_utc": datetime.now(UTC).isoformat(),
    }
    items = register(out_root, entry_dev)
    holm_dev = family_holm(items, dataset_key, "dev").get(entry_dev["trial_id"])

    result = {
        "strategy_version": STRATEGY_VERSION, "label": label, "profile": profile, "config": cfg,
        "config_hash": cfg_hash, "strategy_hash": config.strategy_hash(cfg),
        "baseline_matches_package": config.baseline_matches_package(),
        "data": {**{k: v for k, v in data_meta.items() if k != "instrument_overrides"}, "quality": qa},
        "plan": {"start": p["start"].isoformat(), "end": p["end"].isoformat(), "months": p["months"],
                 "holdout_start": p["holdout_start"].isoformat() if p["holdout_start"] else None,
                 "folds": [[a.isoformat(), b.isoformat()] for a, b in p["folds"]]},
        "news_filter": "applied" if news_applied else "not_applied (no point-in-time calendar supplied)",
        "spread_source": "native_bid_ask" if cfg["spread_mode"] == "bar" else f"assumed ({cfg['spread_mode']})",
        "dev": dev, "dev_folds": folds, "dev_stress": stress_dev, "dev_optimistic_bound": optimistic_dev,
        "dev_benchmark_random": bench_dev, "dev_decision_counts": dict(base_dev.counts),
        "dev_cancels": _count(base_dev.cancels, "reason"),
        "dev_first_drawdown_breach_research": base_dev.first_drawdown_breach,
        "account_view_dev": {"initial_equity": account_cfg["initial_equity"], "final_equity": account_dev.final_equity,
                             "trades": len(period_trades(account_dev.trades, p["start"], dev_end)),
                             "halted_at": account_dev.first_drawdown_breach, "max_drawdown": account_dev.max_drawdown,
                             "currency": account_cfg["account_currency"], "sizing_realistic": account_cfg["sizing_realistic"]},
        "robustness": robust, "holm_dev": holm_dev, "screening": screening_verdict(dev),
        "registry": str(registry_path(out_root)),
    }

    # ---------------------------------------------------------------- holdout
    if p["holdout_start"] is None:
        result["holdout"] = {"status": "unavailable", "why": "meno di 24 mesi completi: nessun holdout di 12 mesi"}
        result["verdict"] = {"label": "RESEARCH", "why": "dati insufficienti per il protocollo (servono >= 36 mesi)"}
    else:
        state = check_or_write_receipt(out_dir, cfg_hash, data_hash, (p["holdout_start"], p["end"]), unseal)
        if state == "sealed":
            result["holdout"] = {"status": "sealed", "why": "holdout non aperto (usa --unseal-holdout, una sola volta)"}
            result["verdict"] = result["screening"]
        elif state == "consumed_by_other_config":
            result["holdout"] = {"status": "consumed_by_other_config",
                                 "why": "holdout già usato da un'altra configurazione: serve un nuovo periodo futuro"}
            result["verdict"] = {"label": "RESEARCH", "why": result["holdout"]["why"]}
        else:
            log("Holdout: valutazione unica della configurazione congelata...")
            full = run(segs, cfg, end=_dt(p["end"]), events=events)
            hold, hold_trades = evaluate_period(full, p["holdout_start"], p["end"], ppy=ppy, rf=rf, sensitivity=True)
            c15 = config.build(profile, research_over, "costs_1.5x")
            full15 = run(segs, c15, end=_dt(p["end"]), events=events)
            hold15 = evaluate_period(full15, p["holdout_start"], p["end"], ppy=ppy, rf=rf)[0]
            bench_hold = random_matched(hold_trades, segs, cfg, _dt(p["holdout_start"]), _dt(p["end"]))
            entry_h = {**entry_dev, "trial_id": hashlib.sha256(f"{cfg_hash}|{data_hash}|holdout".encode()).hexdigest()[:16],
                       "scope": "holdout", "period": [p["holdout_start"].isoformat(), p["end"].isoformat()],
                       "trades": hold["metrics"]["trades"], "mean_R": hold["metrics"]["mean_R"],
                       "p_one_sided": hold["bootstrap"]["p_one_sided"], "registered_at_utc": datetime.now(UTC).isoformat()}
            items = register(out_root, entry_h)
            holm_h = family_holm(items, dataset_key, "holdout").get(entry_h["trial_id"])
            gate = paper_gate(hold, folds, hold15, robust, holm_h, cfg["spread_mode"] == "bar", 12)
            result["holdout"] = {"status": state, "period": hold, "costs_1.5x": hold15,
                                 "benchmark_random": bench_hold, "holm": holm_h}
            result["verdict"] = gate
    (out_dir / "results.json").write_text(json.dumps(result, indent=1, default=str))
    _write_trades(out_dir / "trades-dev.csv", dev_trades)
    return result


def _count(rows, key):
    out = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def _write_trades(path: Path, trades):
    import csv
    cols = ["known_at", "filled_at", "exit_at", "direction", "entry", "stop", "target", "exit_price",
            "reason", "qty", "held_bars", "gross_eur", "fees_eur", "net_eur", "risk_eur", "R", "ambiguous_bar"]
    with path.open("w", newline="") as stream:
        w = csv.DictWriter(stream, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(trades)
