"""Trade and daily metrics with the definitions of protocol 07 (table "Metriche").

Daily series use calendar days in UTC (ledger convention) and include days with
no trades. Returns are net P&L over the equity at the start of the day.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import median

import numpy as np


def _day(iso: str) -> date:
    return datetime.fromisoformat(iso).date()


def daily_series(trades, start: date, end: date, equity_start: float) -> list[dict]:
    """One row per calendar day in [start, end): net, R sum, trade count, equity at day start."""
    by_day_net = defaultdict(float)
    by_day_r = defaultdict(float)
    by_day_n = defaultdict(int)
    for t in trades:
        d = _day(t["exit_at"])
        by_day_net[d] += t["net_eur"]
        by_day_r[d] += t["R"]
        by_day_n[d] += 1
    rows = []
    equity = equity_start
    d = start
    while d < end:
        net = by_day_net.get(d, 0.0)
        rows.append({"date": d.isoformat(), "net": net, "R": by_day_r.get(d, 0.0), "n": by_day_n.get(d, 0),
                     "equity_start": equity, "ret": net / equity if equity > 0 else 0.0})
        equity += net
        d += timedelta(days=1)
    return rows


def max_drawdown(equity_path) -> tuple[float, float]:
    """(fractional max DD, money max peak-to-trough)."""
    peak = -math.inf
    worst_frac, worst_money = 0.0, 0.0
    for e in equity_path:
        peak = max(peak, e)
        if peak > 0:
            worst_frac = max(worst_frac, 1 - e / peak)
        worst_money = max(worst_money, peak - e)
    return worst_frac, worst_money


def trade_metrics(trades, daily, *, periods_per_year=365, rf_annual=0.0, exposure=None,
                  eligible_days=None) -> dict:
    n = len(trades)
    pnl = [t["net_eur"] for t in trades]
    rs = [t["R"] for t in trades]
    wins = [p for p in pnl if p > 0]
    losses = [-p for p in pnl if p < 0]
    gross_win = sum(t["gross_eur"] for t in trades if t["net_eur"] > 0)
    fees = sum(t["fees_eur"] for t in trades)
    streak = worst_streak = 0
    for p in pnl:
        streak = streak + 1 if p < 0 else 0
        worst_streak = max(worst_streak, streak)
    rets = np.array([d["ret"] for d in daily], dtype=float) if daily else np.array([])
    rf_daily = (1 + rf_annual) ** (1 / periods_per_year) - 1
    excess = rets - rf_daily
    sharpe = sortino = None
    days_with_trades = sum(1 for d in daily if d["n"] > 0)
    # Annualised ratios on a handful of trading days are meaningless: require >= 20.
    if days_with_trades >= 20 and len(rets) > 2 and excess.std(ddof=1) > 0:
        sharpe = float(math.sqrt(periods_per_year) * excess.mean() / excess.std(ddof=1))
    if days_with_trades >= 20 and len(rets) > 2:
        downside = np.minimum(rets, 0.0)
        dd = math.sqrt(float(np.mean(downside ** 2)))
        sortino = float(math.sqrt(periods_per_year) * rets.mean() / dd) if dd > 0 else None
    equity_path = [daily[0]["equity_start"]] + [d["equity_start"] + d["net"] for d in daily] if daily else []
    dd_frac, dd_money = max_drawdown(equity_path) if equity_path else (0.0, 0.0)
    net_total = sum(pnl)
    months = defaultdict(float)
    for t in trades:
        months[t["exit_at"][:7]] += t["net_eur"]
    positive_net = sum(v for v in months.values() if v > 0)
    top_month_share = (max(months.values()) / positive_net) if positive_net > 0 and months else None
    var5 = es5 = None
    if len(rets) >= 20:
        q = float(np.percentile(rets, 5))
        var5, es5 = q, float(rets[rets <= q].mean())
    return {
        "trades": n,
        "win_rate": len(wins) / n if n else None,
        "avg_win": sum(wins) / len(wins) if wins else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "expectancy_money": net_total / n if n else None,
        "mean_R": sum(rs) / n if n else None,
        "median_R": median(rs) if rs else None,
        "profit_factor": (sum(wins) / sum(losses)) if losses else None,
        "net_total": net_total,
        "gross_total": sum(t["gross_eur"] for t in trades),
        "fees_total": fees,
        "fee_burden": fees / gross_win if gross_win > 0 else None,
        "sharpe_excess": sharpe,
        "rf_annual_assumed": rf_annual,
        "sortino": sortino,
        "max_drawdown": dd_frac,
        "max_drawdown_money": dd_money,
        "recovery": net_total / dd_money if dd_money > 0 else None,
        "net_return": (equity_path[-1] / equity_path[0] - 1) if equity_path else None,
        "max_consecutive_losses": worst_streak,
        "var5_daily": var5,
        "es5_daily": es5,
        "days": len(daily),
        "days_with_trades": days_with_trades,
        "frequency_per_eligible_day": (n / eligible_days) if eligible_days else None,
        "exposure": exposure,
        "exit_reasons": dict(Counter(t["reason"] for t in trades)),
        "longs": sum(1 for t in trades if t["direction"] == 1),
        "shorts": sum(1 for t in trades if t["direction"] == -1),
        "ambiguous_bars": sum(1 for t in trades if t.get("ambiguous_bar")),
        "net_by_month": dict(sorted(months.items())),
        "top_month_share_of_positive_net": top_month_share,
    }
