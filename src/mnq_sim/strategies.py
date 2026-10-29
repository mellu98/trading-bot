"""Causal, price-only research plugins. No ICT attribution or liquidity observation.

The optional plugins replace candidate generation only. Risk, news, brackets,
next-open execution and pessimistic intrabar handling remain in the stable replay.
"""
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Protocol

from mnq_data.core import digest
from mnq_timestral.schema import NY, Bar
from .quant import QuantReplay


@dataclass(frozen=True)
class StrategyConfig:
    kind: str
    opening_minutes: int = 15
    buffer_ticks: int = 1
    pivot_left: int = 2
    pivot_right: int = 2
    mss_timeout: int = 10

    def __post_init__(self):
        if self.kind not in ('orb', 'sweep_mss'):
            raise ValueError('Unknown research strategy')
        for name in ('opening_minutes','buffer_ticks','pivot_left','pivot_right','mss_timeout'):
            value=getattr(self,name)
            if type(value) is not int or value<1:
                raise ValueError('Positive integer strategy parameters required')
        if self.opening_minutes>60:
            raise ValueError('Opening range exceeds supported initial hour')


class CandidateStrategy(Protocol):
    """Implement this seam to add a strategy without changing execution or risk."""
    audit: dict
    def on_bar(self,bar: Bar) -> int: ...


class PriceStrategy:
    def __init__(self,spec: StrategyConfig):
        self.spec=spec;self.date=None;self.symbol=None;self.audit={}
        self.history=[];self.pending=None;self.high_pivot=None;self.low_pivot=None
        self.consumed=set();self.used_sides=set()

    def on_bar(self,bar):
        local=bar.start.astimezone(NY);date=local.date()
        if bar.available_at!=bar.end:
            raise ValueError('Replay requires bar availability at close; delayed data unsupported')
        if self.symbol is not None and self.symbol!=bar.symbol:
            raise ValueError('One instrument per strategy instance required')
        self.symbol=bar.symbol
        if self.date!=date:
            if self.date and date<self.date:raise ValueError('Session order reversed')
            if (local.hour,local.minute)!=(9,30):raise ValueError('Complete cash opening required')
            self.date=date;self.history=[];self.pending=None;self.high_pivot=None;self.low_pivot=None
            self.consumed=set();self.used_sides=set()
        if self.history:
            last=self.history[-1]
            if last.end!=bar.start or last.contract!=bar.contract:
                raise ValueError('Gap, duplicate, reorder or intraday contract change')
        if not (9,30)<=(local.hour,local.minute)<(16,0):
            raise ValueError('Cash-session bar required')
        self.audit={'strategy':self.spec.kind,'known_at':bar.end.isoformat()}
        signal=self._orb(bar) if self.spec.kind=='orb' else self._sweep(bar)
        self.history.append(bar)
        if self.spec.kind=='sweep_mss':self._confirm_pivots()
        return signal

    def _orb(self,bar):
        n=self.spec.opening_minutes
        if len(self.history)<n:return 0
        opening=self.history[:n];high=max(b.high for b in opening);low=min(b.low for b in opening)
        self.audit.update(range_high=high,range_low=low,range_known_at=opening[-1].end.isoformat())
        buffer=.25*self.spec.buffer_ticks
        side=1 if bar.close>=high+buffer else -1 if bar.close<=low-buffer else 0
        if side and side not in self.used_sides:
            self.used_sides.add(side)
            return side
        return 0

    def _confirm_pivots(self):
        left=self.spec.pivot_left;right=self.spec.pivot_right
        i=len(self.history)-1-right
        if i<left:return
        pivot=self.history[i];window=self.history[i-left:i]+self.history[i+1:i+right+1]
        evidence={'index':i,'confirmed_at':self.history[-1].end.isoformat()}
        if all(pivot.high>b.high for b in window):self.high_pivot={**evidence,'price':pivot.high}
        if all(pivot.low<b.low for b in window):self.low_pivot={**evidence,'price':pivot.low}

    def _sweep(self,bar):
        i=len(self.history);buffer=.25*self.spec.buffer_ticks
        high=self.high_pivot;low=self.low_pivot
        low_fresh=low is not None and ('low',low['index']) not in self.consumed
        high_fresh=high is not None and ('high',high['index']) not in self.consumed
        down_breach=low is not None and bar.low<=low['price']-buffer
        up_breach=high is not None and bar.high>=high['price']+buffer
        # A level ceases to represent an untouched pivot on its FIRST breach,
        # even without a reclaim and even while another setup is pending.
        if down_breach:self.consumed.add(('low',low['index']))
        if up_breach:self.consumed.add(('high',high['index']))
        pending=self.pending
        if pending:
            side=pending['side'];invalid=(bar.low<pending['extreme'] if side==1 else bar.high>pending['extreme'])
            if invalid or i-pending['index']>self.spec.mss_timeout:
                self.pending=None
                self.audit['setup_cancelled']='extreme_or_timeout'
            elif side*(bar.close-pending['level'])>=buffer:
                self.pending=None
                self.audit.update(mss_level=pending['level'],sweep_at=pending['sweep_at'],
                                  pivot_confirmed_at=pending['confirmed_at'])
                return side
            else:return 0
        if high is None or low is None:return 0
        down=down_breach and low_fresh and bar.close>low['price']
        up=up_breach and high_fresh and bar.close<high['price']
        # Both sides swept in one OHLC interval: sequencing unknowable, no setup.
        if down and up:
            self.consumed.update((('low',low['index']),('high',high['index'])))
            return 0
        if not (down or up):return 0
        side=1 if down else -1;pivot=low if down else high;opposite=high if down else low
        key=('low' if down else 'high',pivot['index'])
        # A reclaim that already closed through the opposite level is not a
        # later MSS. Never infer two ordered events within the sweep bar.
        if side*(bar.close-opposite['price'])>=0:return 0
        self.pending={'side':side,'index':i,'extreme':bar.low if down else bar.high,
                      'level':opposite['price'],'sweep_at':bar.end.isoformat(),
                      'confirmed_at':max(pivot['confirmed_at'],opposite['confirmed_at'])}
        return 0


class _GeneratorAdapter:
    def __init__(self,strategy):self.strategy=strategy;self.side=0;self.previous=0
    def direction(self,_z):return self.side


class StrategyReplay(QuantReplay):
    """Offline plugin execution with prefix-rebuilt deterministic restart state."""
    def __init__(self,bars,config,spec,state=None,**kwargs):
        self.spec=spec;self.strategy_identity=digest(asdict(spec))
        if state is not None and state.get('strategy_identity')!=self.strategy_identity:
            raise ValueError('Restart strategy identity mismatch')
        super().__init__(bars,config,state=state,**kwargs)
        self.generators={root:_GeneratorAdapter(PriceStrategy(spec)) for root in ('MNQ','MES')}
        # Rebuild only already-processed strategy observations, never future bars.
        for _,group in self.events[:self.index]:
            for root,bar in group.items():self.generators[root].strategy.on_bar(bar)

    def step(self,start,group):
        for root,bar in group.items():
            adapter=self.generators[root];adapter.side=adapter.strategy.on_bar(bar)
        offset=len(self.decisions)
        super().step(start,group)
        for decision in self.decisions[offset:]:
            decision['strategy_evidence']=dict(self.generators[decision['symbol']].strategy.audit)

    def state(self):return {**super().state(),'strategy_identity':self.strategy_identity}
