"""Synthetic market-like bars for engine v2 tests (no edge by construction).

Index-CFD calendar (Sunday 18:00 -> Friday 17:00 New York, daily break
17:00-18:00), intraday volatility profile, high/low from a fine random path,
optional correlated companion series for SMT.
"""
import math
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ict_engine.bars import Bar

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def _vol(lt):
    h = lt.hour + lt.minute / 60
    if 9.5 <= h < 11:
        return 1.8
    if 2 <= h < 5:
        return 1.0
    if 11 <= h < 16:
        return 1.2
    return 0.5


def market(days, seed, *, start=17000.0, vol=0.0011, tick=0.25, spread=None, companion=False, corr=0.85,
           t0=datetime(2024, 1, 7, 23, 0, tzinfo=UTC)):
    rng = random.Random(seed)
    t, end = t0, t0 + timedelta(days=days)
    p = [start, start / 3.4]
    out = ([], [])
    while t < end:
        s = t
        t += timedelta(minutes=5)
        lt = s.astimezone(NY)
        wd, hm = lt.weekday(), (lt.hour, lt.minute)
        closed = wd == 5 or (wd == 6 and hm < (18, 0)) or (wd == 4 and hm >= (17, 0)) or (17, 0) <= hm < (18, 0)
        zs = [rng.gauss(0, 1) for _ in range(20)]
        if closed:
            continue
        vm = _vol(lt) * (3 if rng.random() < 0.03 else 1)
        for k in range(2 if companion else 1):
            o = hi = lo = p[k]
            sub = vol * vm / math.sqrt(20)
            for z in zs:
                zz = z if k == 0 else corr * z + math.sqrt(1 - corr ** 2) * rng.gauss(0, 1)
                p[k] *= math.exp(zz * sub)
                hi, lo = max(hi, p[k]), min(lo, p[k])
            r = lambda x: round(x / tick) * tick
            o, hi, lo, c = r(o), r(hi), r(lo), r(p[k])
            hi, lo = max(hi, o, c), min(lo, o, c)
            out[k].append(Bar(t, o, hi, lo, c, spread))
            p[k] = c
    return out if companion else out[0]
