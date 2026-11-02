"""Market context for engine v2: liquidity pools, trading days, sessions, H1 structure.

Everything here is causal: a level is published only when the period that
defines it is complete (PDH/PDL at the trading-day roll, the Asia range at
00:00 NY, an H1 swing two closed H1 bars after its extreme...). The engine
calls `MarketContext.on_bar(b)` AFTER deciding on bar `b`, so anything that
`b` completes is usable from the next bar on.

Catalog references (docs/ict-engine-v1/13): swing, equal highs/lows,
PDH/PDL/PWH/PWL, Asian/London range, internal/external (H1) structure,
HTF/daily bias, premium/discount, midnight open.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import windows

# Higher = preferred when one bar sweeps several pools on the same side (spec pool_rank).
PRIORITY = {"pw": 6, "pd": 5, "asia": 4, "london": 4, "nyam": 4, "equal": 3, "h1": 3, "swing": 1}
DAILY_TYPES = {"pd", "asia", "london", "nyam"}


@dataclass(eq=False)
class Pool:
    pid: int
    kind: str              # HIGH (buy-side liquidity proxy) | LOW (sell-side)
    price: float
    ptype: str             # swing | equal | h1 | pd | pw | asia | london | nyam
    known_at: datetime     # usable for decisions on bars ending strictly after this
    src_ts: datetime       # end of the bar that printed the extreme (SMT reference)
    index: int | None = None   # M5 index (swing / equal) for lookback
    expires: datetime | None = None
    broken: bool = False
    used: bool = False


class PoolBook:
    def __init__(self):
        self.pools: list[Pool] = []
        self._next = 0

    def add(self, kind, price, ptype, known_at, src_ts, index=None, expires=None) -> Pool:
        p = Pool(self._next, kind, price, ptype, known_at, src_ts, index, expires)
        self._next += 1
        self.pools.append(p)
        return p

    def apply_bar(self, b) -> None:
        """Mark pools traded through by bar b (touch counts, as in A1) and prune."""
        keep = []
        for p in self.pools:
            if p.known_at < b.ts:
                if (p.kind == "HIGH" and b.h >= p.price) or (p.kind == "LOW" and b.l <= p.price):
                    p.broken = True
            if p.broken or (p.expires is not None and p.expires <= b.ts):
                continue
            keep.append(p)
        self.pools = keep

    def live(self, now, types):
        return [p for p in self.pools if p.ptype in types and p.known_at < now and not p.broken
                and (p.expires is None or p.expires > now)]

    def drop(self, types) -> None:
        self.pools = [p for p in self.pools if p.ptype not in types]

    def clear(self) -> None:
        self.pools = []


def _acc(b):
    return {"o": b.o, "h": b.h, "l": b.l, "c": b.c, "hi_ts": b.ts, "lo_ts": b.ts, "n": 1, "complete": True}


def _add(acc, b):
    if b.h > acc["h"]:
        acc["h"], acc["hi_ts"] = b.h, b.ts
    if b.l < acc["l"]:
        acc["l"], acc["lo_ts"] = b.l, b.ts
    acc["c"] = b.c
    acc["n"] += 1


class MarketContext:
    def __init__(self, cfg, book: PoolBook):
        self.cfg = cfg
        self.book = book
        self.tf = timedelta(seconds=cfg["timeframe_seconds"])
        self.types = set(cfg["pool_types"])
        self.reset()

    # ------------------------------------------------------------- state
    def reset(self):
        self.tday = None
        self.day = None
        self.prev_day = None
        self.wkey = None
        self.week = None
        self.prev_week = None
        self.sess = {}
        self.midnight_open = None
        self.h1_bucket = None
        self.h1 = deque(maxlen=600)
        self.h1_highs = deque(maxlen=8)   # confirmed H1 swing highs (price, ts)
        self.h1_lows = deque(maxlen=8)
        self.trend = 0
        self.range = None
        self.last_h1_close = None
        self.gap_pending = True  # start of data: the first day/week are partial

    def mark_incomplete(self):
        """Unexpected data gap: nothing that spans it may be published."""
        self.gap_pending = True
        if self.day:
            self.day["complete"] = False
        if self.week:
            self.week["complete"] = False
        for acc in self.sess.values():
            acc["complete"] = False
        self.h1_bucket = None

    # ------------------------------------------------------------- queries
    @property
    def daily_bias(self) -> int:
        d = self.prev_day
        if not d or d["c"] == d["o"]:
            return 0
        return 1 if d["c"] > d["o"] else -1

    def zone(self, price):
        """Premium/discount z in the H1 dealing range; None when the range is invalid."""
        if self.range is None:
            return None
        lo, hi = self.range
        if self.last_h1_close is None or not lo <= self.last_h1_close <= hi:
            return None
        return (price - lo) / (hi - lo)

    # ------------------------------------------------------------- update
    def on_bar(self, b):
        c = self.cfg
        start = b.ts - self.tf
        td = windows.trading_day(start, c)
        if td != self.tday:
            self._roll_day(td, b)
        else:
            _add(self.day, b)
            _add(self.week, b)
        self._sessions(b, start)
        lt = windows.local(start, c)
        if lt.hour == 0 and lt.minute == 0:
            self.midnight_open = b.o
        self._h1(b, start)

    def _roll_day(self, td, b):
        if self.day is not None and self.day["complete"]:
            self.prev_day = self.day
        else:
            self.prev_day = None
        self.book.drop(DAILY_TYPES)
        if self.prev_day and "pd" in self.types:
            self.book.add("HIGH", self.prev_day["h"], "pd", b.ts, self.prev_day["hi_ts"])
            self.book.add("LOW", self.prev_day["l"], "pd", b.ts, self.prev_day["lo_ts"])
        wkey = td.isocalendar()[:2]
        if wkey != self.wkey:
            self.prev_week = self.week if (self.week is not None and self.week["complete"]) else None
            self.book.drop({"pw"})
            if self.prev_week and "pw" in self.types:
                self.book.add("HIGH", self.prev_week["h"], "pw", b.ts, self.prev_week["hi_ts"])
                self.book.add("LOW", self.prev_week["l"], "pw", b.ts, self.prev_week["lo_ts"])
            self.wkey = wkey
            self.week = _acc(b)
            self.week["complete"] = not self.gap_pending
        else:
            _add(self.week, b)
        self.tday = td
        self.day = _acc(b)
        self.day["complete"] = not self.gap_pending
        self.gap_pending = False
        self.sess = {}
        self.midnight_open = None

    def _sessions(self, b, start):
        c = self.cfg
        lt = windows.local(start, c)
        clock = f"{lt.hour:02d}:{lt.minute:02d}"
        le = windows.local(b.ts, c)
        end_clock = f"{le.hour:02d}:{le.minute:02d}"
        if end_clock == "00:00":
            end_clock = "24:00"
        step = int(self.tf.total_seconds() // 60)
        for name, (s_start, s_end) in c["sessions"].items():
            if not s_start <= clock < s_end:
                continue
            acc = self.sess.get(name)
            if acc is None:
                acc = _acc(b)
                acc["complete"] = clock == s_start
                self.sess[name] = acc
            else:
                _add(acc, b)
            if end_clock == s_end:
                h0, m0 = map(int, s_start.split(":"))
                h1, m1 = map(int, s_end.split(":"))
                expected = ((h1 * 60 + m1) - (h0 * 60 + m0)) // step
                if acc["complete"] and acc["n"] == expected and name in self.types:
                    self.book.add("HIGH", acc["h"], name, b.ts, acc["hi_ts"])
                    self.book.add("LOW", acc["l"], name, b.ts, acc["lo_ts"])

    def _h1(self, b, start):
        key = start.replace(minute=0, second=0, microsecond=0)
        if self.h1_bucket is None or self.h1_bucket[0] != key:
            self.h1_bucket = (key, _acc(b)) if start == key else None
            if self.h1_bucket is None:
                return
        else:
            _add(self.h1_bucket[1], b)
        acc = self.h1_bucket[1]
        if b.ts == key + timedelta(hours=1):
            self.h1_bucket = None
            if acc["n"] != int(3600 // self.tf.total_seconds()):
                return
            self.h1.append({"end": b.ts, **acc})
            self.last_h1_close = acc["c"]
            self._h1_pivot(b.ts)
            if self.range is not None:
                lo, hi = self.range
                if not lo <= acc["c"] <= hi:
                    self.range = None  # close outside the dealing range invalidates it

    def _h1_pivot(self, now):
        k = self.cfg["h1_pivot"]
        bars = self.h1
        j = len(bars) - 1 - k
        if j < k:
            return
        centre = bars[j]
        others = [bars[x] for x in range(j - k, j + k + 1) if x != j]
        hours = self.cfg["h1_pool_hours"]
        changed = False
        if all(centre["h"] > o["h"] for o in others):
            self.h1_highs.append((centre["h"], centre["hi_ts"]))
            changed = True
            if "h1" in self.types:
                self.book.add("HIGH", centre["h"], "h1", now, centre["hi_ts"], expires=now + timedelta(hours=hours))
        if all(centre["l"] < o["l"] for o in others):
            self.h1_lows.append((centre["l"], centre["lo_ts"]))
            changed = True
            if "h1" in self.types:
                self.book.add("LOW", centre["l"], "h1", now, centre["lo_ts"], expires=now + timedelta(hours=hours))
        if changed:
            self._structure()

    def _structure(self):
        hs, ls = self.h1_highs, self.h1_lows
        trend = 0
        if len(hs) >= 2 and len(ls) >= 2:
            if hs[-1][0] > hs[-2][0] and ls[-1][0] > ls[-2][0]:
                trend = 1
            elif hs[-1][0] < hs[-2][0] and ls[-1][0] < ls[-2][0]:
                trend = -1
        self.trend = trend
        if hs and ls and ls[-1][0] < hs[-1][0]:
            self.range = (ls[-1][0], hs[-1][0])
        else:
            self.range = None
