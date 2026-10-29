"""Causal features, explicit clock horizons, and externally attested input gates."""
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from hashlib import sha256
from pathlib import Path
import csv
import numpy as np
from .schema import Bar, Request, NY, UTC, HORIZONS, timestamp, loads


@dataclass(frozen=True)
class Features:
    context: np.ndarray
    past: np.ndarray
    vwap: np.ndarray
    residual: np.ndarray
    z: np.ndarray
    volatility: np.ndarray


def features(request: Request):
    bars = request.bars
    close = np.array([b.close for b in bars], dtype=np.float64)
    volume = np.array([b.volume for b in bars], dtype=np.float64)
    typical = np.array([(b.high+b.low+b.close)/3 for b in bars])
    vwap = np.cumsum(typical*volume)/np.cumsum(volume)
    residual = close-vwap
    returns = np.r_[0., np.diff(np.log(close))]
    volatility = np.array([np.std(returns[max(0, i-19):i+1], ddof=0) for i in range(len(bars))])
    z = np.full(len(bars), np.nan)
    for i in range(19, len(bars)):
        sigma = np.std(residual[i-19:i+1], ddof=0)
        z[i] = residual[i]/sigma if sigma > 0 else 0.
    past = np.stack((returns, volume, volatility, residual), axis=0)[None, :, :]
    return Features(close[None, None, :], past, vwap, residual, z, volatility)


def horizon_targets(request, bars):
    lookup = {(b.contract, b.end): b for b in bars}
    result = {}
    for h in HORIZONS:
        path = [lookup.get((request.contract, request.origin+timedelta(minutes=k))) for k in range(1, h+1)]
        result[h] = path[-1].close if all(b is not None and b.start.astimezone(NY).date() ==
                      request.bars[-1].start.astimezone(NY).date() for b in path) else None
    return result


def file_hash(path):
    h = sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def session_window(date, calendar):
    """Missing/unknown calendar or news fails closed. Close five minutes before exchange close."""
    rec = calendar.get(date)
    if not rec or rec.get('news_complete') is not True: return None
    try:
        opened, closed, known = (timestamp(rec[k]) for k in ('open', 'close', 'known_at'))
        local_open = datetime.combine(datetime.fromisoformat(date).date(), time(9, 30), NY).astimezone(UTC)
        if opened != local_open or closed <= opened or known > opened: return None
        if not isinstance(rec['news_blocks'], list): return None
        for block in rec['news_blocks']:
            a, b, k = (timestamp(block[x]) for x in ('start', 'end', 'known_at'))
            if a >= b or k > a: return None
        start = opened+timedelta(minutes=15)
        regular_end = datetime.combine(opened.astimezone(NY).date(), time(15, 30), NY).astimezone(UTC)
        end = min(regular_end, closed-timedelta(minutes=5))
        return (start, end) if start < end else None
    except (ValueError, TypeError, KeyError): return None


def news_allowed(now, record):
    return not any(timestamp(b['start']) <= now <= timestamp(b['end']) for b in record['news_blocks'])


def load_bars(path):
    result = []
    with open(path, newline='') as stream:
        for row in csv.DictReader(stream):
            for key in ('open', 'high', 'low', 'close', 'volume'): row[key] = float(row[key])
            result.append(Bar.from_dict(row))
    return tuple(result)


def validate_dataset(csv_path, manifest_path):
    """Verify declared integrity/attestations, NOT independently authenticate vendor data."""
    manifest = loads(Path(manifest_path).read_text())
    required = ('source', 'license', 'retrieved_at', 'audit_reference', 'calendar_source', 'news_source', 'roll_policy')
    if any(not isinstance(manifest.get(k), str) or not manifest[k].strip() for k in required):
        raise ValueError("missing provenance evidence")
    timestamp(manifest['retrieved_at'])
    if manifest.get('attested_verified') is not True: raise ValueError("input audit attestation missing")
    if manifest.get('sha256') != file_hash(csv_path): raise ValueError("dataset checksum mismatch")
    if manifest.get('timestamp_convention') != 'bar_start_utc' or manifest.get('price_adjustment') != 'none':
        raise ValueError("requires unadjusted actual-contract start-stamped UTC OHLCV")
    if manifest.get('interval_seconds') != 60: raise ValueError("one-minute interval required")
    bars = load_bars(csv_path)
    if not bars: raise ValueError("empty dataset")
    calendar = manifest.get('sessions', {})
    active = manifest.get('active_contracts', {})
    seen = set()
    previous = {}
    sessions = set()
    for bar in bars:
        key = (bar.symbol, bar.start)
        if key in seen: raise ValueError("duplicate symbol timestamp")
        seen.add(key)
        if bar.symbol in previous and previous[bar.symbol] >= bar.start: raise ValueError("data not chronological")
        previous[bar.symbol] = bar.start
        date = bar.start.astimezone(NY).date().isoformat()
        sessions.add(date)
        if active.get(date, {}).get(bar.symbol) != bar.contract: raise ValueError("missing/contradictory active contract evidence")
        if session_window(date, calendar) is None: raise ValueError("calendar/news unavailable or unknown")
    for symbol in ('MNQ', 'MES'):
        if not any(b.symbol == symbol for b in bars): raise ValueError("both MNQ and MES data required for declared family")
    if not {'MNQ', 'MES'}.issubset(manifest.get('costs', {})): raise ValueError("verified costs required per symbol")
    from .evaluation import Costs
    for symbol in ('MNQ', 'MES'):
        cost = manifest['costs'][symbol]
        if cost.get('attested_verified') is not True: raise ValueError("cost audit attestation missing")
        Costs.from_dict(cost)
    return bars, manifest
