from dataclasses import dataclass
from datetime import datetime
from math import isfinite
@dataclass(frozen=True)
class Bar:
    ts: datetime  # end time, UTC aware
    o: float
    h: float
    l: float
    c: float
    def __post_init__(self):
        if self.ts.tzinfo is None or self.ts.utcoffset().total_seconds()!=0:
            raise ValueError('UTC required')
        if not all(isfinite(x) and x>0 for x in (self.o,self.h,self.l,self.c)):
            raise ValueError('invalid price')
        if not self.l<=min(self.o,self.c)<=max(self.o,self.c)<=self.h:
            raise ValueError('invalid OHLC')
def validate_append(bars,b,seconds):
    if bars and (b.ts-bars[-1].ts).total_seconds()!=seconds:
        raise ValueError('duplicate, unordered or missing bar: reset segment')
def atr(bars,n):
    if len(bars)<n+1: return None
    xs=bars[-n-1:]
    return sum(max(b.h-b.l,abs(b.h-a.c),abs(b.l-a.c)) for a,b in zip(xs,xs[1:]))/n
