"""Synthetic fixtures: not market data or evidence of predictive value."""
from datetime import datetime, timedelta, timezone
import pytest
from mnq_timestral.schema import Bar, Request, Prediction, LEVELS, HORIZONS
from mnq_timestral.model import PINS, SOURCE_REVISION

UTC = timezone.utc

def bars(n=40, symbol="MES", date="2026-10-20", hour=13, prices=None):
    start = datetime.fromisoformat(f"{date}T{hour}:30:00+00:00")
    values = prices or [6000 + (i % 5) * .25 for i in range(n)]
    return tuple(Bar(symbol, symbol + "Z6", start + timedelta(minutes=i),
                     start + timedelta(minutes=i+1), start + timedelta(minutes=i+1),
                     p, p+.5, p-.5, p, 100+i) for i,p in enumerate(values))

def request(n=40, **kwargs):
    bs=bars(n, **kwargs)
    return Request(bs, bs[-1].available_at, "28M", "past_covariates")

def prediction(req, delta=1, delay=0):
    pin=PINS[req.model]
    rows=tuple(tuple(req.bars[-1].close + delta + (q-.5)*4 for q in LEVELS) for _ in HORIZONS)
    return Prediction(req.key, req.symbol, req.contract, req.origin,
                      req.requested_at+timedelta(seconds=delay), req.model,
                      pin.revision, SOURCE_REVISION, pin.config_sha256, pin.weights_sha256,
                      req.variant, HORIZONS, LEVELS, rows, max(0,delay), "replay", len(req.bars))

@pytest.fixture
def req(): return request()

@pytest.fixture
def pred(req): return prediction(req)
