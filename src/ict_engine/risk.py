"""Risk gate (ported from reference/risk_manager.py) and the ledger that feeds it.

The reference gate only evaluates a snapshot; the spec leaves the ledger to the
host. RiskLedger is that host-side ledger for backtests:
- equity in account currency, realized P&L only (one position at a time, so
  intraday MTM of a single open trade is ignored: documented simplification);
- daily return reset at 00:00 UTC, weekly at Monday 00:00 UTC (spec 06);
- loss streak reset at the new UTC day; daily trade count = intents per UTC day;
- drawdown from the flow-adjusted peak. Policy "halt" latches like the spec
  (no automatic resume); policy "record" keeps trading and records the first
  breach, so the research ledger can measure the whole period.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class RiskState:
    day_return: float = 0
    week_return: float = 0
    drawdown: float = 0
    consecutive_losses: int = 0
    daily_trades: int = 0
    concurrent: int = 0
    reserved_fraction: float = 0
    api_errors: int = 0
    halted: bool = False


def gate(state, cfg):
    checks = [
        (state.halted, "DISABLE_KILL_SWITCH"),
        (state.drawdown >= cfg["drawdown_fraction"], "DISABLE_DRAWDOWN"),
        (state.day_return <= -cfg["daily_loss_fraction"], "SKIP_DAILY_LOSS"),
        (state.week_return <= -cfg["weekly_loss_fraction"], "SKIP_WEEKLY_LOSS"),
        (state.consecutive_losses >= cfg["max_consecutive_losses"], "SKIP_LOSS_STREAK"),
        (state.daily_trades >= cfg["max_daily_trades"], "SKIP_TRADE_LIMIT"),
        (state.concurrent >= cfg["max_concurrent"], "SKIP_CONCURRENT"),
        (state.reserved_fraction + cfg["risk_fraction"] > cfg["max_aggregate_risk_fraction"], "SKIP_AGGREGATE_RISK"),
        (state.api_errors >= cfg["api_error_limit"], "DISABLE_API_ERRORS"),
    ]
    return next((code for test, code in checks if test), None)


def _day(ts: datetime):
    return ts.date()


def _week(ts: datetime):
    monday = ts.date() - timedelta(days=ts.weekday())
    return monday


class RiskLedger:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.equity = float(cfg["initial_equity"])
        self.peak = self.equity
        self.day = None
        self.week = None
        self.day_start = self.equity
        self.week_start = self.equity
        self.consecutive_losses = 0
        self.daily_trades = 0
        self.halted = False
        self.first_drawdown_breach = None
        self.max_drawdown = 0.0

    def roll(self, ts: datetime) -> None:
        if self.day != _day(ts):
            self.day = _day(ts)
            self.day_start = self.equity
            self.daily_trades = 0
            self.consecutive_losses = 0
        if self.week != _week(ts):
            self.week = _week(ts)
            self.week_start = self.equity

    def drawdown(self) -> float:
        return 1 - self.equity / self.peak if self.peak > 0 else 1.0

    def state(self, ts: datetime, *, exposure: bool) -> RiskState:
        self.roll(ts)
        dd = self.drawdown()
        if self.cfg["drawdown_policy"] == "record":
            dd_for_gate = 0.0  # breach recorded in on_close, never blocks the research ledger
        else:
            dd_for_gate = dd
        return RiskState(
            day_return=(self.equity - self.day_start) / self.day_start if self.day_start > 0 else -1.0,
            week_return=(self.equity - self.week_start) / self.week_start if self.week_start > 0 else -1.0,
            drawdown=dd_for_gate,
            consecutive_losses=self.consecutive_losses,
            daily_trades=self.daily_trades,
            concurrent=1 if exposure else 0,
            reserved_fraction=self.cfg["risk_fraction"] if exposure else 0.0,
            halted=self.halted,
        )

    def on_intent(self, ts: datetime) -> None:
        self.roll(ts)
        self.daily_trades += 1

    def on_close(self, ts: datetime, net: float) -> None:
        self.roll(ts)
        self.equity += net
        if net < 0:
            self.consecutive_losses += 1
        else:
            # Spec 06: a zero result interrupts the losing streak but is not a win.
            self.consecutive_losses = 0
        self.peak = max(self.peak, self.equity)
        dd = self.drawdown()
        self.max_drawdown = max(self.max_drawdown, dd)
        if dd >= self.cfg["drawdown_fraction"] and self.first_drawdown_breach is None:
            self.first_drawdown_breach = ts.isoformat()
            if self.cfg["drawdown_policy"] == "halt":
                self.halted = True
