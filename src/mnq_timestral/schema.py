"""Strict immutable wire contracts. All timestamps are UTC and bar ends are exclusive."""
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from functools import cached_property
import json
import math
import re
from zoneinfo import ZoneInfo

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
HORIZONS = (1, 3, 5, 10, 15)
LEVELS = (.01, .05, .10, .15, .20, .25, .30, .35, .40, .45, .50,
          .55, .60, .65, .70, .75, .80, .85, .90, .95, .99)


def timestamp(value):
    value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("UTC timezone-aware timestamp required")
    return value


def finite(*values):
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in values):
        raise ValueError("finite numeric values required")


def dumps(obj):
    def convert(x):
        if isinstance(x, datetime): return x.isoformat()
        if hasattr(x, '__dataclass_fields__'):
            result = asdict(x)
            if isinstance(x, Prediction): result['medians'] = list(x.medians)
            return result
        raise TypeError(type(x).__name__)
    return json.dumps(obj, default=convert, allow_nan=False, sort_keys=True, separators=(',', ':'))


def loads(raw):
    def invalid(value): raise ValueError("nonfinite JSON")
    def unique(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    return json.loads(raw, parse_constant=invalid, object_pairs_hook=unique)


@dataclass(frozen=True)
class Bar:
    symbol: str
    contract: str
    start: datetime
    end: datetime
    available_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self):
        for name in ('start', 'end', 'available_at'):
            object.__setattr__(self, name, timestamp(getattr(self, name)))
        if self.symbol not in ('MNQ', 'MES') or not re.fullmatch(self.symbol + r'[HMUZ]\d{1,4}', self.contract):
            raise ValueError("actual quarterly MNQ/MES contract required; continuous symbols forbidden")
        if self.end-self.start != timedelta(minutes=1) or self.start.second or self.start.microsecond:
            raise ValueError("one-minute clock-aligned bar required")
        if self.available_at < self.end: raise ValueError("bar cannot be available before its end")
        finite(self.open, self.high, self.low, self.close, self.volume)
        if not (0 < self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high):
            raise ValueError("invalid positive OHLC")
        if self.volume <= 0 or self.volume != int(self.volume): raise ValueError("positive integer traded volume required")
        if any(abs(v/.25-round(v/.25)) > 1e-8 for v in (self.open,self.high,self.low,self.close)):
            raise ValueError("prices must respect the .25 futures tick")
        for name in ("open","high","low","close","volume"): object.__setattr__(self,name,float(getattr(self,name)))

    @classmethod
    def from_dict(cls, obj): return cls(**obj)


@dataclass(frozen=True)
class Request:
    bars: tuple[Bar, ...]
    requested_at: datetime
    model: str = '28M'
    variant: str = 'past_covariates'

    def __post_init__(self):
        object.__setattr__(self, 'bars', tuple(self.bars))
        object.__setattr__(self, 'requested_at', timestamp(self.requested_at))
        if self.model not in ('28M', '209M') or self.variant not in ('target_only', 'past_covariates'):
            raise ValueError("unknown model or feature variant")
        if not 20 <= len(self.bars) <= 512: raise ValueError("context length must be 20..512")
        first = self.bars[0]
        if not isinstance(first, Bar): raise ValueError("Bar context required")
        local = first.start.astimezone(NY)
        if (local.hour, local.minute) != (9, 30): raise ValueError("context must include cash VWAP anchor 09:30")
        for i, bar in enumerate(self.bars):
            if (bar.symbol, bar.contract) != (first.symbol, first.contract): raise ValueError("mixed contract context")
            if bar.start.astimezone(NY).date() != local.date(): raise ValueError("mixed session context")
            if bar.available_at > self.requested_at: raise ValueError("future/unavailable input")
            if i and (self.bars[i-1].end != bar.start or self.bars[i-1].available_at > bar.available_at):
                raise ValueError("gap, duplicate, reordered or availability-reversed context")
        if self.requested_at < self.origin: raise ValueError("request precedes forecast origin")

    @property
    def origin(self): return self.bars[-1].end
    @property
    def symbol(self): return self.bars[-1].symbol
    @property
    def contract(self): return self.bars[-1].contract
    @cached_property
    def key(self): return sha256(dumps(self).encode()).hexdigest()

    @classmethod
    def from_dict(cls, obj):
        obj = dict(obj)
        obj['bars'] = tuple(Bar.from_dict(b) for b in obj['bars'])
        return cls(**obj)


@dataclass(frozen=True)
class Prediction:
    request_key: str
    symbol: str
    contract: str
    origin: datetime
    available_at: datetime
    model: str
    model_revision: str
    source_revision: str
    config_sha256: str
    weights_sha256: str
    variant: str
    horizons: tuple[int, ...]
    levels: tuple[float, ...]
    values: tuple[tuple[float, ...], ...]
    latency_seconds: float
    clock: str
    context_length: int

    def __post_init__(self):
        for name in ('origin', 'available_at'): object.__setattr__(self, name, timestamp(getattr(self, name)))
        for name in ('horizons', 'levels'): object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, 'values', tuple(tuple(row) for row in self.values))
        if self.horizons != HORIZONS or self.levels != LEVELS: raise ValueError("unexpected horizon/quantile grid")
        if len(self.values) != len(HORIZONS): raise ValueError("forecast dimension mismatch")
        for row in self.values:
            finite(*row)
            if len(row) != len(LEVELS) or any(a > b for a, b in zip(row, row[1:])):
                raise ValueError("invalid or crossing quantiles")
        finite(self.latency_seconds)
        if self.available_at < self.origin or self.latency_seconds < 0: raise ValueError("invalid readiness/latency")
        if self.clock not in ('replay', 'wall') or not 20 <= self.context_length <= 512:
            raise ValueError("invalid clock/context")
        from .model import PINS, SOURCE_REVISION
        pin = PINS.get(self.model)
        if pin is None or (self.model_revision, self.source_revision, self.config_sha256, self.weights_sha256) != (
                pin.revision, SOURCE_REVISION, pin.config_sha256, pin.weights_sha256):
            raise ValueError("unrecognized model provenance")
        if self.variant not in ('target_only', 'past_covariates'): raise ValueError("unknown variant")

    def quantile(self, horizon, level): return self.values[self.horizons.index(horizon)][self.levels.index(level)]
    @property
    def medians(self): return tuple(self.quantile(h, .5) for h in self.horizons)

    def valid_for(self, request, now, ttl=90):
        now = timestamp(now)
        return (self.request_key == request.key and self.symbol == request.symbol and self.contract == request.contract
                and self.model == request.model and self.variant == request.variant and self.origin == request.origin
                and self.available_at <= now and timedelta(0) <= now-self.origin <= timedelta(seconds=ttl))

    @classmethod
    def from_dict(cls, obj):
        obj = dict(obj)
        medians = obj.pop('medians', None)
        result = cls(**obj)
        if medians is not None and tuple(medians) != result.medians:
            raise ValueError('explicit median disagrees with quantile grid')
        return result
