"""Point-in-time economic calendar gate (ported from reference/news_filter.py).

A calendar is optional for research runs. Without one the run is marked
`news_filter: not_applied` and the verdict can never exceed RESEARCH for live
promotion purposes (spec 07/14: unknown history -> RESEARCH).

CSV format for --calendar (UTC ISO timestamps):
    scheduled_at,known_at,currencies,importance,category
    2025-03-12T12:30:00Z,2025-03-01T00:00:00Z,USD,3,CPI
`currencies` may hold several codes separated by ';'.
"""
from __future__ import annotations

import bisect
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Event:
    scheduled_at: datetime
    known_at: datetime
    currencies: tuple
    importance: int
    category: str


def blocked(now, events, updated_at, currencies, cfg):
    if updated_at is None or updated_at > now or (now - updated_at).total_seconds() > cfg["calendar_max_age_seconds"]:
        return "SKIP_CALENDAR_STALE"
    before = timedelta(minutes=cfg["news_before_minutes"])
    after = timedelta(minutes=cfg["news_after_minutes"])
    for e in events:
        if (e.known_at <= now and set(e.currencies) & set(currencies) and e.importance >= 3
                and e.scheduled_at - before <= now <= e.scheduled_at + after):
            return "SKIP_NEWS_BLACKOUT"
    return None


def _ts(text: str) -> datetime:
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("calendar timestamps must be UTC")
    return value


def load_calendar(path: str | Path) -> list[Event]:
    events = []
    with open(path, newline="", encoding="utf8") as stream:
        for row in csv.DictReader(stream):
            events.append(Event(
                scheduled_at=_ts(row["scheduled_at"]),
                known_at=_ts(row["known_at"]),
                currencies=tuple(c.strip() for c in row["currencies"].split(";") if c.strip()),
                importance=int(row["importance"]),
                category=row.get("category", "").strip(),
            ))
    events.sort(key=lambda e: e.scheduled_at)
    return events


class CalendarWindow:
    """Fast lookup of events near a timestamp for long backtests."""

    def __init__(self, events: list[Event], cfg: dict):
        self.events = sorted(events, key=lambda e: e.scheduled_at)
        self.keys = [e.scheduled_at for e in self.events]
        self.pad = timedelta(minutes=max(cfg["news_before_minutes"], cfg["news_after_minutes"]) + 1)

    def near(self, now: datetime) -> tuple:
        lo = bisect.bisect_left(self.keys, now - self.pad)
        hi = bisect.bisect_right(self.keys, now + self.pad)
        return tuple(self.events[lo:hi])
