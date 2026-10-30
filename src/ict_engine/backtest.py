"""Event loop: bars -> execution reports -> risk ledger -> A1 engine -> intents.

Normative event order (spec 05): for every closed bar, first apply execution
(fills/exits produced by that bar), update the risk ledger, then let the engine
decide on the closed bar; a new intent can only fill on later bars.

Data gaps end the segment: the engine restarts its warmup, pending orders are
cancelled (CANCEL_DATA_INVALID) and an open position keeps its stop, which is
evaluated on the next available bar (gap-through-stop at the worse open).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from .engine import A1Engine, Context
from .execution import SimulationAdapter
from .news import CalendarWindow
from .risk import RiskLedger


def spread_for(b, cfg) -> float:
    mode = cfg["spread_mode"]
    if mode == "bar":
        if b.spread is None:
            raise ValueError("profile needs native bid/ask bars (spread_mode=bar) but the data has no spread")
        return b.spread
    if mode == "bps":
        return b.c * cfg["spread_bps"] / 1e4
    return cfg["spread_price"]  # fixed | context


@dataclass
class RunResult:
    cfg: dict
    trades: list = field(default_factory=list)
    intents: list = field(default_factory=list)
    cancels: list = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    notable: list = field(default_factory=list)
    bars: int = 0
    bars_in_position: int = 0
    segments: int = 0
    purged_open_at_end: int = 0
    first_bar: str | None = None
    last_bar: str | None = None
    final_equity: float = 0.0
    max_drawdown: float = 0.0
    first_drawdown_breach: str | None = None
    session_days: list = field(default_factory=list)


def run(segments, cfg, *, end: datetime | None = None, events=None, optimistic=False,
        currencies=("USD",)) -> RunResult:
    """Run A1 over contiguous segments up to `end` (exclusive). Trades still open at `end` are purged."""
    engine = A1Engine(cfg)
    sim = SimulationAdapter(cfg, optimistic=optimistic)
    ledger = RiskLedger(cfg)
    calendar = CalendarWindow(events, cfg) if events else None
    tz = ZoneInfo(cfg["session_timezone"])
    res = RunResult(cfg=cfg)
    session_days = set()
    stop = False
    for k, seg in enumerate(segments):
        if stop:
            break
        if k > 0:
            sim.on_gap(seg[0].ts.isoformat())
            engine.reset()
        res.segments += 1
        for b in seg:
            if end is not None and b.ts > end:
                stop = True
                break
            res.bars += 1
            if res.first_bar is None:
                res.first_bar = b.ts.isoformat()
            res.last_bar = b.ts.isoformat()
            local = b.ts.astimezone(tz)
            if local.weekday() in cfg["weekdays"]:
                session_days.add(local.date().isoformat())
            spread = spread_for(b, cfg)
            for report in sim.on_bar(b, spread):
                ledger.on_close(b.ts, report["net_eur"])
                res.trades.append(report)
            if any(x["status"] == "OPEN" for x in sim.active.values()):
                res.bars_in_position += 1
            exposure = sim.exposure()
            ctx = Context(
                equity=ledger.equity, spread=spread, quote_time=b.ts,
                calendar_updated=b.ts if calendar is not None else None,
                events=calendar.near(b.ts) if calendar is not None else (),
                currencies=currencies, risk=ledger.state(b.ts, exposure=exposure), cash=ledger.equity,
            )
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
    res.session_days = sorted(session_days)
    return res
