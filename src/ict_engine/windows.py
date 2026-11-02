"""Trading windows, killzones, trading days and scheduled market closures (New York time).

A1 uses a single session [session_start, session_end). Engine v2 uses a list of
decision windows, each with its own flat time: entries are decided inside
[start, end) and every order/position of that window is cancelled/closed at
`flat`. All clocks are wall-clock New York (IANA, DST-aware).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo


def _t(text: str) -> time:
    h, m = text.split(":")
    return time(int(h), int(m))


@lru_cache(maxsize=None)
def tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def local(ts: datetime, cfg) -> datetime:
    return ts.astimezone(tz(cfg["session_timezone"]))


def windows_of(cfg) -> list[tuple[str, str, str]]:
    if cfg.get("engine") == "v2":
        return [tuple(w) for w in cfg["windows"]]
    return [(cfg["session_start"], cfg["session_end"], cfg["session_end"])]


def decision_window(ts: datetime, cfg):
    """Window (start, end, flat) containing the decision instant `ts` (a bar end), or None."""
    lt = local(ts, cfg)
    if lt.weekday() not in cfg["weekdays"]:
        return None
    clock = f"{lt.hour:02d}:{lt.minute:02d}"
    for w in windows_of(cfg):
        if w[0] <= clock < w[1]:
            return w
    return None


def flat_at(ts: datetime, cfg) -> datetime | None:
    """Flat time (UTC) of the decision window containing `ts`."""
    w = decision_window(ts, cfg)
    if w is None:
        return None
    lt = local(ts, cfg)
    f = _t(w[2])
    flat_local = lt.replace(hour=f.hour, minute=f.minute, second=0, microsecond=0)
    if flat_local <= lt:
        flat_local += timedelta(days=1)
    return flat_local.astimezone(ts.tzinfo)


def in_any(ts: datetime, cfg, spans) -> bool:
    lt = local(ts, cfg)
    clock = f"{lt.hour:02d}:{lt.minute:02d}"
    return any(a <= clock < b for a, b in spans)


def trading_day(bar_start: datetime, cfg):
    """Trading day of a bar (by its START time). FX/indices/futures roll at 17:00 NY; crypto at 00:00 UTC."""
    if cfg.get("asset_class") == "crypto":
        return bar_start.date()
    return (local(bar_start, cfg) + timedelta(hours=7)).date()


def scheduled_gap(prev_end: datetime, next_end: datetime, cfg) -> bool:
    """True when the missing bars fall entirely inside an expected market closure.

    Daily maintenance break 16:00-18:30 NY and the weekend Fri 16:00 -> Sun 19:00 NY
    (FX, index CFDs, CME futures). Crypto trades 24/7: every gap is unexpected.
    """
    if cfg.get("asset_class") == "crypto":
        return False
    tf = timedelta(seconds=cfg["timeframe_seconds"])
    first_missing_start = prev_end            # start of the first missing bar
    last_missing_start = next_end - 2 * tf    # start of the last missing bar
    a, b = local(first_missing_start, cfg), local(last_missing_start, cfg)
    span = b - a
    if span < timedelta(0):
        return True
    # daily break: same evening, inside 16:00-18:30
    if span <= timedelta(hours=2, minutes=30) and a.date() == b.date():
        if time(16, 0) <= a.time() and b.time() < time(18, 30):
            return True
    # weekend: starts Friday after 16:00, ends Sunday before 19:00
    if span <= timedelta(hours=52):
        if a.weekday() == 4 and a.time() >= time(16, 0) and b.weekday() == 6 and b.time() < time(19, 0):
            return True
    return False
