"""Event loop for engine v2 over the full bar list (no pre-split into segments).

Gaps are classified, not just cut:
- scheduled closures (daily break 16:00-18:30 NY, weekend) keep all context;
- unexpected gaps reset intraday state, drop all pools, cancel pending orders
  and mark the current day/week/sessions incomplete (nothing spanning a hole
  is ever published);
- a futures contract change (roll) resets everything.

Same normative order as A1 (spec 05): execution reports first, then the risk
ledger, then the decision on the closed bar; fills only on later bars.
`fixed_equity=True` keeps sizing and risk gates independent from P&L (used by
the frequency calibration so that it cannot see results).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from . import windows
from .backtest import RunResult, spread_for
from .engine import Context
from .engine_v2 import CompanionSeries, ICTEngine
from .execution import SimulationAdapter
from .news import CalendarWindow
from .risk import RiskLedger, RiskState


def run_v2(bars, cfg, *, end: datetime | None = None, events=None, optimistic=False, companion=None,
           contract_changes=(), currencies=("USD",), fixed_equity=False) -> RunResult:
    comp = companion if isinstance(companion, CompanionSeries) or companion is None else CompanionSeries(companion)
    engine = ICTEngine(cfg, companion=comp)
    sim = SimulationAdapter(cfg, optimistic=optimistic)
    ledger = RiskLedger(cfg)
    calendar = CalendarWindow(events, cfg) if events else None
    rolls = {datetime.fromisoformat(x) for x in contract_changes}
    tf = timedelta(seconds=cfg["timeframe_seconds"])
    res = RunResult(cfg=cfg)
    gaps = Counter()
    decision_days = set()
    prev = None
    for b in bars:
        if end is not None and b.ts > end:
            break
        if prev is not None:
            delta = b.ts - prev.ts
            if delta <= timedelta(0):
                raise ValueError("bars must be sorted and de-duplicated")
            if b.ts in rolls:
                gaps["roll"] += 1
                for report in sim.flatten(prev, spread_for(prev, cfg)):
                    if not fixed_equity:
                        ledger.on_close(prev.ts, report["net_eur"])
                    res.trades.append(report)
                engine.on_gap(full=True)
            elif delta != tf:
                if windows.scheduled_gap(prev.ts, b.ts, cfg):
                    gaps["scheduled"] += 1
                else:
                    gaps["unexpected"] += 1
                    sim.on_gap(b.ts.isoformat())
                    engine.on_gap()
        prev = b
        res.bars += 1
        if res.first_bar is None:
            res.first_bar = b.ts.isoformat()
        res.last_bar = b.ts.isoformat()
        if windows.decision_window(b.ts, cfg) is not None:
            decision_days.add(windows.local(b.ts, cfg).date().isoformat())
        spread = spread_for(b, cfg)
        reports = sim.on_bar(b, spread)
        for _ in sim.new_fills:
            ledger.on_fill(b.ts)
        for report in reports:
            if not fixed_equity:
                ledger.on_close(b.ts, report["net_eur"])
            res.trades.append(report)
        if any(x["status"] == "OPEN" for x in sim.active.values()):
            res.bars_in_position += 1
        exposure = sim.exposure()
        if fixed_equity:
            ledger.roll(b.ts)
            risk = RiskState(daily_trades=ledger.daily_fills, concurrent=1 if exposure else 0,
                             reserved_fraction=cfg["risk_fraction"] if exposure else 0.0)
        else:
            risk = ledger.state(b.ts, exposure=exposure)
        ctx = Context(equity=ledger.equity, spread=spread, quote_time=b.ts,
                      calendar_updated=b.ts if calendar is not None else None,
                      events=calendar.near(b.ts) if calendar is not None else (),
                      currencies=currencies, risk=risk, cash=ledger.equity)
        signal = engine.on_bar(b, ctx)
        if signal:
            sim.create(signal)
            ledger.on_intent(b.ts)
            res.intents.append(signal)
    res.purged_open_at_end = sum(1 for x in sim.active.values() if x["status"] == "OPEN")
    res.cancels = sim.cancels
    res.counts = engine.counts
    res.notable = engine.notable
    res.final_equity = ledger.equity
    res.max_drawdown = ledger.max_drawdown
    res.first_drawdown_breach = ledger.first_drawdown_breach
    res.session_days = sorted(decision_days)
    res.extra = {"gaps": dict(gaps), "smt_available": comp is not None}
    return res
