"""Reference signal/filter/risk seam, not an implementation of LEAN execution."""
from dataclasses import dataclass
from datetime import timedelta
import math
from .schema import timestamp, finite


@dataclass(frozen=True)
class Candidate:
    symbol: str
    contract: str
    side: int
    origin: object
    price: float
    request_key: str

    def __post_init__(self):
        object.__setattr__(self,"origin",timestamp(self.origin))
        finite(self.price)
        if self.symbol not in ("MNQ","MES") or self.side not in (-1,1) or self.price <= 0:
            raise ValueError("invalid candidate")


class SignalGenerator:
    def __init__(self, threshold=2.5): self.threshold, self.previous = threshold, 0
    def direction(self, z):
        if not math.isfinite(z): return 0
        zone = 1 if z < -self.threshold else -1 if z > self.threshold else 0
        side = zone if zone != self.previous else 0
        self.previous = zone
        return side


@dataclass(frozen=True)
class Filter:
    enabled: bool = False
    horizon: int = 5
    edge: float = 0.
    ttl: float = 90.
    tail_level: float = .25

    def __post_init__(self):
        if not isinstance(self.enabled,bool) or not math.isfinite(self.ttl) or not 0 < self.ttl <= 90:
            raise ValueError("boolean filter switch and bounded positive TTL required")
        if self.horizon not in (1, 3, 5, 10, 15) or not math.isfinite(self.edge) or self.edge < 0:
            raise ValueError("invalid fixed filter configuration")
        if self.tail_level not in (.1, .25, .5): raise ValueError("unsupported tail level")

    def prediction_available(self, candidate, prediction, now):
        """Identity, readiness, TTL and target maturity; no directional state or trade decision."""
        p = prediction
        if p is None: return False, 'missing'
        if (p.request_key, p.symbol, p.contract, p.origin) != (
                candidate.request_key, candidate.symbol, candidate.contract, candidate.origin): return False, 'identity'
        if p.available_at > now or p.origin > now: return False, 'not_ready'
        if now >= p.origin+timedelta(minutes=self.horizon): return False, 'target_expired'
        if now-p.origin > timedelta(seconds=self.ttl): return False, 'stale'
        return True, 'available'

    def evaluate(self, candidate, prediction, now):
        if not self.enabled: return True, 'disabled'
        available, reason = self.prediction_available(candidate, prediction, now)
        if not available: return False, reason
        p = prediction
        level = self.tail_level if candidate.side == 1 else 1-self.tail_level
        directional_edge = candidate.side*(p.quantile(self.horizon, level)-candidate.price)
        return (True, 'accepted') if directional_edge >= self.edge else (False, 'distribution_incoherent')


@dataclass(frozen=True)
class RiskState:
    realized: float = 0.
    unrealized: float = 0.
    drawdown: float = 0.
    trades: int = 0
    consecutive_losses: int = 0
    positions: int = 0
    kill: bool = False
    data_fresh: bool = True

    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.realized, self.unrealized, self.drawdown)):
            raise ValueError('nonfinite risk state')
        if self.drawdown < 0 or min(self.trades, self.consecutive_losses, self.positions) < 0:
            raise ValueError('negative risk counts')


@dataclass(frozen=True)
class Risk:
    daily_max_loss: float = 200.
    max_drawdown: float = 500.
    max_trades: int = 10
    max_consecutive_losses: int = 3

    def __post_init__(self):
        if not all(math.isfinite(x) and x > 0 for x in (self.daily_max_loss, self.max_drawdown)):
            raise ValueError('positive finite loss limits required')
        if any(not isinstance(x, int) or isinstance(x, bool) or x < 1 for x in (self.max_trades, self.max_consecutive_losses)):
            raise ValueError('positive integer trade limits required')

    def allow(self, state):
        if state.kill: return False, 'kill'
        if not state.data_fresh: return False, 'stale_data'
        if state.positions: return False, 'position_open'
        if state.realized+state.unrealized <= -self.daily_max_loss: return False, 'daily_max_loss'
        if state.drawdown >= self.max_drawdown: return False, 'max_drawdown'
        if state.trades >= self.max_trades: return False, 'max_trades'
        if state.consecutive_losses >= self.max_consecutive_losses: return False, 'consecutive_losses'
        return True, 'risk_allowed'


def entry_allowed(candidate, prediction, now, forecast_filter, risk, state, calendar_ok):
    if not calendar_ok: return False, 'calendar_or_news'
    allowed, reason = forecast_filter.evaluate(candidate, prediction, now)
    if not allowed: return False, reason
    # Predictions never override the final deterministic risk decision.
    return risk.allow(state)
