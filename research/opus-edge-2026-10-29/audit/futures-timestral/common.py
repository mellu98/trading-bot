"""Read-only helpers for the independent futures audit. Never writes into the project tree."""
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path('/Users/locoframe/Desktop/TRADING BOT')
OUT = Path('/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-futures')
NY = ZoneInfo('America/New_York')
UTC = timezone.utc
PV = {'MNQ': 2.0, 'MES': 5.0}
TICK = 0.25
DIST = {'MES': (4.0, 2.0), 'MNQ': (15.0, 8.0)}   # (TP, SL) points, copied from evaluation.py:20


def reg_fee(date):
    """quant.py:20 fee_for_date: NFA .02 before 2026-07-01 else .01."""
    return .02 if date < '2026-07-01' else .01


class Session:
    __slots__ = ('date', 'sym', 'contract', 'start', 'o', 'h', 'l', 'c', 'v', 'idx')

    def __init__(self, date, sym, rows):
        self.date, self.sym = date, sym
        self.contract = rows[0]['contract']
        self.start = [datetime.fromisoformat(r['start']) for r in rows]
        self.o = np.array([float(r['open']) for r in rows])
        self.h = np.array([float(r['high']) for r in rows])
        self.l = np.array([float(r['low']) for r in rows])
        self.c = np.array([float(r['close']) for r in rows])
        self.v = np.array([float(r['volume']) for r in rows])
        self.idx = {s: i for i, s in enumerate(self.start)}

    def end(self, i):
        return self.start[i] + timedelta(minutes=1)


def load_bars120():
    rows = defaultdict(list)
    with (ROOT / 'reports/quant-validation/bars120.csv').open(newline='') as f:
        for r in csv.DictReader(f):
            d = datetime.fromisoformat(r['start']).astimezone(NY).date().isoformat()
            rows[d, r['symbol']].append(r)
    sessions = {}
    for k, rr in rows.items():
        rr.sort(key=lambda r: int(r['ts_event_ns']))
        assert len({r['contract'] for r in rr}) == 1, k
        sessions[k] = Session(k[0], k[1], rr)
    return sessions


def in_window(ts):
    t = ts.astimezone(NY)
    return (9, 45) <= (t.hour, t.minute) < (15, 30)


def simulate_exit(s, i0, side, entry, tp, sl, policy='stop_first', realized_day=0., fees=0., execc=0.,
                  daily_max_loss=200.):
    """Re-implementation of engine.py Replay exit logic (lines 189-203) + evaluation.simulate_trade.

    policy: 'stop_first' (engine), 'target_first' (optimistic bound), 'ohlc_path' (O->L->H->C if up-bar else O->H->L->C).
    Returns (raw_exit, reason, exit_index, ambiguous).
    """
    stop = entry - side * sl
    target = entry + side * tp
    n = len(s.o)
    for i in range(i0, n):
        o, h, l, c = s.o[i], s.h[i], s.l[i], s.c[i]
        hit_stop = (l <= stop) if side == 1 else (h >= stop)
        hit_target = (h >= target) if side == 1 else (l <= target)
        amb = hit_stop and hit_target
        stop_px = min(o, stop) if side == 1 else max(o, stop)
        if amb:
            if policy == 'stop_first':
                first = 'stop'
            elif policy == 'target_first':
                first = 'target'
            else:
                # heuristic path; gap-through open beyond stop is always a stop
                if (side == 1 and o <= stop) or (side == -1 and o >= stop):
                    first = 'stop'
                elif (side == 1 and o >= target) or (side == -1 and o <= target):
                    first = 'target'
                else:
                    up_bar = c >= o
                    # up bar: O->L->H->C ; down bar: O->H->L->C
                    low_first = up_bar
                    if side == 1:
                        first = 'stop' if low_first else 'target'
                    else:
                        first = 'target' if low_first else 'stop'
            if first == 'stop':
                return stop_px, 'stop', i, True
            return target, 'target', i, True
        if hit_stop:
            return stop_px, 'stop', i, False
        if hit_target:
            return target, 'target', i, False
        if not in_window(s.end(i)):
            return c, 'session_close', i, False
        mark = side * (c - entry) * PV[s.sym] - fees - execc
        if realized_day + mark <= -daily_max_loss:
            return c, 'risk_loss', i, False
    return s.c[-1], 'end_of_data', n - 1, False


def block_bootstrap_mean(x, block=5, reps=10000, seed=1729):
    x = np.asarray(x, float)
    n = len(x)
    rng = np.random.default_rng(seed)
    nb = (n + block - 1) // block
    starts = rng.integers(0, n, size=(reps, nb))
    idx = ((starts[:, :, None] + np.arange(block)) % n).reshape(reps, -1)[:, :n]
    m = x[idx].mean(axis=1)
    return float(np.quantile(m, .025)), float(np.quantile(m, .975))
