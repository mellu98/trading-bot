import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
REFERENCE = ROOT / "docs" / "ict-engine-v1" / "reference"

from ict_engine.bars import Bar  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 1, 5, 11, 0, tzinfo=UTC)  # Monday 06:00 New York


def bar(i, o, h, l, c, spread=None, t0=T0):
    return Bar(t0 + timedelta(minutes=5 * (i + 1)), o, h, l, c, spread)


def random_walk(n, seed, *, start=1000.0, tick=0.25, t0=T0, shock=0.06):
    """Fat-tailed tick-grid random walk: no edge by construction."""
    rng = random.Random(seed)
    out = []
    price = start
    for i in range(n):
        o = price
        step = rng.gauss(0, 6)
        if rng.random() < shock:
            step *= rng.choice((3, 4, 5))
        c = max(tick * 40, round((o + step * tick) / tick) * tick)
        up = round(rng.expovariate(1 / 3)) * tick
        dn = round(rng.expovariate(1 / 3)) * tick
        h = max(o, c) + up
        l = max(tick, min(o, c) - dn)
        out.append(Bar(t0 + timedelta(minutes=5 * (i + 1)), o, h, l, c))
        price = c
    return out
