from dataclasses import dataclass
from datetime import datetime,timedelta
@dataclass(frozen=True)
class Event:
    scheduled_at: datetime
    known_at: datetime
    currencies: tuple
    importance: int
    category: str
def blocked(now,events,updated_at,currencies,cfg):
    if updated_at is None or updated_at>now or (now-updated_at).total_seconds()>cfg['calendar_max_age_seconds']:
        return 'SKIP_CALENDAR_STALE'
    before=timedelta(minutes=cfg['news_before_minutes']);after=timedelta(minutes=cfg['news_after_minutes'])
    for e in events:
        if e.known_at<=now and set(e.currencies)&set(currencies) and e.importance>=3 and e.scheduled_at-before<=now<=e.scheduled_at+after:
            return 'SKIP_NEWS_BLACKOUT'
    return None
