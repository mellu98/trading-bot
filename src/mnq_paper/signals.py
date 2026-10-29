"""Signal seam; default is the existing unapproved V1 strategy, not a new one."""
from typing import Protocol
from mnq_timestral.schema import Request
from mnq_timestral.data import features
from mnq_timestral.strategy import SignalGenerator


class SignalSource(Protocol):
    identity: str
    def evaluate(self,bars,now,state: dict) -> tuple[int,dict]: ...


class VwapV1Source:
    identity='vwap_v1'
    def evaluate(self,bars,now,state):
        f=features(Request(tuple(bars),now))
        generator=SignalGenerator();generator.previous=state.get('previous',0)
        side=generator.direction(float(f.z[-1]))
        return side,{'previous':generator.previous}
