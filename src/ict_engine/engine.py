"""A1 streaming engine: sweep -> MSS/displacement -> immediate FVG -> limit intent.

Decision logic is a line-by-line port of docs/ict-engine-v1/reference/ict_strategy.py
(same reason codes, same order of checks). Two implementation changes, both
verified by the parity test against the reference engine:

1. Pivots are tracked incrementally (O(1) per bar) instead of rescanning the
   whole history every bar, which is O(n^2) and unusable on years of M5 bars.
   Unbroken pivots form a monotonic stack (each later unbroken HIGH is lower
   than every earlier unbroken HIGH), so "intact" status is maintained exactly.
2. Tick rounding uses a 1e-9 tick tolerance so that a price already on the grid
   is not pushed one tick away by binary floating point (100.6/0.01 -> 10059.999...).

The engine emits simulation intents only. The caller owns the order lifecycle
and must report exposure through Context.risk (concurrent/reserved_fraction).
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from math import ceil, floor, isfinite
from zoneinfo import ZoneInfo

from .detectors import fvg, mss, sweep
from .news import blocked
from .risk import RiskState, gate
from .sizing import size, slippage_for

# Codes recorded every bar; kept as counts only to bound memory on long runs.
ROUTINE = {"WAIT_WARMUP", "WAIT_SWEEP", "WAIT_MSS", "WAIT_FVG", "SKIP_SESSION", "SKIP_CONCURRENT"}


@dataclass(frozen=True)
class Context:
    equity: float
    spread: float
    quote_time: object
    calendar_updated: object
    events: tuple = ()
    currencies: tuple = ("USD",)
    risk: RiskState = RiskState()
    cash: float | None = None  # extension: current cash for sizing (None = cfg available_cash_eur)


class _Pivot:
    __slots__ = ("index", "known_at", "kind", "price", "broken_at")

    def __init__(self, index, known_at, kind, price):
        self.index, self.known_at, self.kind, self.price = index, known_at, kind, price
        self.broken_at = None

    def intact(self, end):
        return self.broken_at is None or self.broken_at > end


def floor_tick(x, tick):
    return floor(x / tick + 1e-9) * tick


def ceil_tick(x, tick):
    return ceil(x / tick - 1e-9) * tick


class A1Engine:
    def __init__(self, cfg, *, keep_log=False):
        if cfg["mode"] != "simulation":
            raise ValueError("simulation only")
        if any(cfg[k] for k in ("htf_filter", "premium_discount_filter", "daily_bias_filter")):
            raise ValueError("optional filters not implemented")
        if cfg["fvg_ttl_bars"] != 1:
            raise ValueError("A1 requires immediate FVG")
        self.cfg = cfg
        self.tz = ZoneInfo(cfg["session_timezone"])
        self.keep_log = keep_log
        self.log = []          # full per-bar log (tests) when keep_log=True
        self.notable = []      # non-routine decisions (always kept, for audit)
        self.counts = Counter()
        n = cfg["atr_period"]
        self.window = max(n + 1, cfg["pivot_left"] + cfg["pivot_right"] + 1, 3)
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        """Start a new contiguous segment: warmup n+1, no setup, no pools (spec 07 QA)."""
        self.buf = deque(maxlen=self.window)
        self.n = 0
        self.last_ts = None
        self.setup = None
        self.used = set()
        self.recent = deque()
        self.high_stack = []
        self.low_stack = []

    def record(self, b, code):
        self.counts[code] += 1
        if self.keep_log:
            self.log.append({"ts": b.ts.isoformat(), "reason": code})
        if code not in ROUTINE:
            self.notable.append({"ts": b.ts.isoformat(), "reason": code})

    def _prior_atr(self):
        n = self.cfg["atr_period"]
        if self.n < n + 1:
            return None
        xs = list(self.buf)[-n - 1:]
        return sum(max(b.h - b.l, abs(b.h - a.c), abs(b.l - a.c)) for a, b in zip(xs, xs[1:])) / n

    def _confirm_pivots(self):
        """Pivot j = i-1-right becomes known before bar i (reference: pivots on bars[:i])."""
        left, right = self.cfg["pivot_left"], self.cfg["pivot_right"]
        j = self.n - 1 - right
        if j < left:
            return
        win = list(self.buf)[-(left + right + 1):]
        centre = win[left]
        others = win[:left] + win[left + 1:]
        if all(centre.h > x.h for x in others):
            p = _Pivot(j, j + right, "HIGH", centre.h)
            self.recent.append(p)
            self.high_stack.append(p)
        if all(centre.l < x.l for x in others):
            p = _Pivot(j, j + right, "LOW", centre.l)
            self.recent.append(p)
            self.low_stack.append(p)

    def _apply_breaks(self, b, i):
        while self.high_stack and self.high_stack[-1].price <= b.h:
            self.high_stack.pop().broken_at = i
        while self.low_stack and self.low_stack[-1].price >= b.l:
            self.low_stack.pop().broken_at = i

    # --------------------------------------------------------------- decision
    def on_bar(self, b, ctx):
        if not all(isfinite(x) for x in (ctx.equity, ctx.spread)) or ctx.equity <= 0 or ctx.spread < 0:
            raise ValueError("invalid account/quote")
        c = self.cfg
        if self.last_ts is not None and (b.ts - self.last_ts).total_seconds() != c["timeframe_seconds"]:
            raise ValueError("duplicate, unordered or missing bar: reset segment")
        prior_atr = self._prior_atr()
        self._confirm_pivots()
        self.buf.append(b)
        i = self.n
        self.n += 1
        self.last_ts = b.ts
        self._apply_breaks(b, i)
        lookback = c["structure_lookback"]
        while self.recent and i - self.recent[0].index > lookback:
            self.recent.popleft()

        if prior_atr is None or prior_atr <= 0:
            self.record(b, "WAIT_WARMUP")
            return None
        local = b.ts.astimezone(self.tz)
        clock = f"{local.hour:02d}:{local.minute:02d}"
        reason = gate(ctx.risk, c)
        if not reason and c["news_enabled"]:
            reason = blocked(b.ts, ctx.events, ctx.calendar_updated, ctx.currencies, c)
        if not (c["session_start"] <= clock < c["session_end"] and local.weekday() in c["weekdays"]):
            reason = reason or "SKIP_SESSION"
        age = (b.ts - ctx.quote_time).total_seconds()
        if not 0 <= age <= c["quote_max_age_seconds"]:
            reason = reason or "SKIP_STALE_QUOTE"
        if ctx.spread < 0 or ctx.spread > c["max_spread_atr"] * prior_atr:
            reason = reason or "SKIP_SPREAD_TOO_HIGH"
        slip = slippage_for(b.c, c)
        if slip > c["max_slippage_atr"] * prior_atr:
            reason = reason or "SKIP_SLIPPAGE"
        if reason:
            self.setup = None
            self.record(b, reason)
            return None

        s = self.setup
        if s:
            d = s["direction"]
            if (b.l < s["extreme"] if d == 1 else b.h > s["extreme"]):
                self.setup = None
                self.record(b, "SKIP_SWEEP_INVALIDATED")
                return None
            if s["mss_index"] is None:
                if i - s["sweep_index"] > c["mss_ttl_bars"]:
                    self.setup = None
                    self.record(b, "SKIP_MSS_EXPIRED")
                    return None
                if mss(b, s["break_level"], d, prior_atr, c):
                    s["mss_index"] = i
                    s["mss_ts"] = b.ts.isoformat()
            else:
                if i - s["mss_index"] > c["fvg_ttl_bars"]:
                    self.setup = None
                    self.record(b, "SKIP_FVG_EXPIRED")
                    return None
                gap = fvg(list(self.buf), d, prior_atr, c)
                # Exactly the displacement/MSS candle is the middle candle.
                if gap and i == s["mss_index"] + 1:
                    return self._intent(b, ctx, s, gap, prior_atr, slip, i)
            if s["mss_index"] is not None and i == s["mss_index"] + 1:
                self.setup = None
                self.record(b, "SKIP_FVG_EXPIRED")
                return None
            self.record(b, "WAIT_FVG" if s["mss_index"] is not None else "WAIT_MSS")
            return None

        candidates = []
        for p in self.recent:
            d = 1 if p.kind == "LOW" else -1
            if (p.index, p.kind) in self.used or i - p.index > lookback or not p.intact(i - 1):
                continue
            if sweep(b, p, d, prior_atr, c):
                opposite = [x for x in self.recent if x.kind != p.kind and i - x.index <= lookback]
                if opposite:
                    candidates.append((p, d, max(opposite, key=lambda x: x.index)))
        if len({d for _, d, _ in candidates}) > 1:
            self.record(b, "SKIP_DUAL_SWEEP")
            return None
        if candidates:
            p, d, op = max(candidates, key=lambda x: x[0].index)
            self.used.add((p.index, p.kind))
            self.setup = {"direction": d, "sweep_index": i, "extreme": b.l if d == 1 else b.h,
                          "break_level": op.price, "mss_index": None, "pool_price": p.price,
                          "pool_id": f"{p.kind}@{p.index}", "sweep_ts": b.ts.isoformat()}
            self.record(b, "SWEEP_CONFIRMED")
        else:
            self.record(b, "WAIT_SWEEP")
        return None

    def _intent(self, b, ctx, s, gap, prior_atr, slip, i):
        c = self.cfg
        d = s["direction"]
        tick = c["tick_size"]
        lo, hi = gap
        entry = hi - c["entry_fraction"] * (hi - lo) if d == 1 else lo + c["entry_fraction"] * (hi - lo)
        entry = floor_tick(entry, tick) if d == 1 else ceil_tick(entry, tick)
        buff = max(c["stop_buffer_atr"] * prior_atr, c["stop_buffer_spreads"] * ctx.spread, tick)
        stop = s["extreme"] - d * buff
        stop = floor_tick(stop, tick) if d == 1 else ceil_tick(stop, tick)
        stack = self.high_stack if d == 1 else self.low_stack
        targets = [p.price - d * tick for p in stack if d * (p.price - entry) > 0]
        targets = [x for x in targets if d * (x - entry) > 0]
        if not targets:
            self.setup = None
            self.record(b, "SKIP_NO_TARGET")
            return None
        target = min(targets) if d == 1 else max(targets)
        target = floor_tick(target, tick) if d == 1 else ceil_tick(target, tick)
        dist = abs(entry - stop) / prior_atr
        if not c["stop_min_atr"] <= dist <= c["stop_max_atr"] or (
                b.c + ctx.spread / 2 <= entry if d == 1 else b.c - ctx.spread / 2 >= entry):
            self.setup = None
            self.record(b, "SKIP_ENTRY_OR_STOP")
            return None
        sized = size(ctx.equity, entry, stop, target, d, c, cash=ctx.cash, slippage=slip)
        self.setup = None
        if not sized["qty"]:
            self.record(b, sized["reason"])
            return None
        sid = sha256(f"{c['version']}|{c['symbol']}|{b.ts.isoformat()}|{d}|{s['sweep_index']}".encode()).hexdigest()
        signal = {
            "signal_id": sid, "version": c["version"], "symbol": c["symbol"], "direction": d,
            "known_at": b.ts.isoformat(), "entry": entry, "stop": stop, "target": target,
            "expires_at": (b.ts + timedelta(seconds=c["order_ttl_bars"] * c["timeframe_seconds"])).isoformat(),
            **sized,
            # audit context (contract 08 market_context)
            "atr_lag": prior_atr, "spread": ctx.spread, "slippage": slip, "sweep_extreme": s["extreme"],
            "mss_level": s["break_level"], "sweep_pool_id": s["pool_id"], "pool_price": s["pool_price"],
            "sweep_at": s["sweep_ts"], "mss_at": s["mss_ts"],
        }
        self.record(b, "ENTER_LONG" if d == 1 else "ENTER_SHORT")
        return signal
