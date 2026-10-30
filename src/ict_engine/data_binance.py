"""Official Binance spot klines from data.binance.vision, verified against .CHECKSUM.

Public archives, no account or API key. Same acquisition discipline as the
bot's research/opus-edge-2026-10-29/src/acquire.py: every ZIP is checked
against Binance's official SHA256 file; nothing unverified is ever loaded.

Timestamp units: spot archives use milliseconds up to 2024-12 and MICROseconds
from 2025-01 (Binance README, verified in the bot's audit). Both are handled
and the decoded month is checked against the file name.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .bars import Bar

UTC = timezone.utc
BASE = "https://data.binance.vision/"
UA = {"User-Agent": "trading-bot-ict-research/1.0 (public archives)"}
INTERVAL_SECONDS = {"1m": 60, "5m": 300}


def _get(url: str, tries: int = 4) -> bytes:
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError:
            raise
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))
    raise RuntimeError("unreachable")


def month_list(last: tuple[int, int], count: int) -> list[str]:
    y, m = last
    out = []
    for _ in range(count):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(out)


def last_full_month(today: date | None = None) -> tuple[int, int]:
    today = today or datetime.now(UTC).date()
    first = today.replace(day=1)
    prev = first - timedelta(days=1)
    return prev.year, prev.month


def archive_path(cache: Path, symbol: str, interval: str, month: str) -> Path:
    return cache / "binance" / "spot" / "monthly" / "klines" / symbol / interval / f"{symbol}-{interval}-{month}.zip"


def download(cache: Path, symbol: str = "BTCUSDT", interval: str = "5m", months: int = 36,
             last: tuple[int, int] | None = None, log=print) -> dict:
    """Download (or re-verify) `months` monthly archives ending at `last` (default: last full month)."""
    if interval not in INTERVAL_SECONDS:
        raise ValueError("interval must be 1m or 5m")
    last = last or last_full_month()
    receipts = []
    wanted = month_list(last, months)
    for month in wanted:
        rel = f"data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
        dest = archive_path(cache, symbol, interval, month)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            official = _get(BASE + rel + ".CHECKSUM").decode().split()[0]
        except urllib.error.HTTPError as error:
            if error.code == 404 and month == wanted[-1]:
                raise SystemExit(f"{month} not published yet on data.binance.vision; pass --last-month earlier")
            raise
        if dest.exists():
            body, status = dest.read_bytes(), "cached"
        else:
            body, status = _get(BASE + rel), "downloaded"
        sha = hashlib.sha256(body).hexdigest()
        if sha != official:
            raise SystemExit(f"CHECKSUM MISMATCH {rel}: {sha} != {official} (file not saved)")
        if status == "downloaded":
            dest.write_bytes(body)
        (dest.parent / (dest.name + ".CHECKSUM")).write_text(f"{official}  {dest.name}\n")
        receipts.append({"url": BASE + rel, "sha256": sha, "bytes": len(body), "status": status,
                         "verified_at_utc": datetime.now(UTC).isoformat()})
        log(f"  {month}: {status}, sha256 ok")
        time.sleep(0.05)
    manifest = {"source": "data.binance.vision (official Binance public data)", "symbol": symbol,
                "interval": interval, "months": wanted, "files": receipts}
    out = cache / "binance" / f"manifest-{symbol}-{interval}.json"
    out.write_text(json.dumps(manifest, indent=1))
    return manifest


def _parse_ts(raw: str, month: str) -> datetime:
    value = int(raw)
    # 13 digits = ms, 16 digits = us (from 2025-01 on spot)
    if value >= 10**15:
        dt = datetime.fromtimestamp(value / 1e6, UTC)
    else:
        dt = datetime.fromtimestamp(value / 1e3, UTC)
    return dt


def load(cache: Path, symbol: str = "BTCUSDT", interval: str = "5m", months: list[str] | None = None) -> tuple[list[Bar], dict]:
    """Load verified archives into Bars (ts = open_time + interval). Refuses unverified files."""
    manifest_path = cache / "binance" / f"manifest-{symbol}-{interval}.json"
    if not manifest_path.exists():
        raise SystemExit(f"no verified download for {symbol} {interval}: run the download command first")
    manifest = json.loads(manifest_path.read_text())
    months = months or manifest["months"]
    step = INTERVAL_SECONDS[interval]
    by_month = {Path(f["url"]).name: f["sha256"] for f in manifest["files"]}
    bars: list[Bar] = []
    digest = hashlib.sha256()
    for month in months:
        path = archive_path(cache, symbol, interval, month)
        body = path.read_bytes()
        sha = hashlib.sha256(body).hexdigest()
        if by_month.get(path.name) != sha:
            raise SystemExit(f"{path.name} does not match its verified checksum; re-run download")
        digest.update(sha.encode())
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            name = z.namelist()[0]
            text = z.read(name).decode()
        for row in csv.reader(io.StringIO(text)):
            if not row or not row[0].strip().isdigit():
                continue  # header line present in some archives
            start = _parse_ts(row[0], month)
            if start.strftime("%Y-%m") != month:
                raise SystemExit(f"timestamp unit error in {path.name}: decoded {start.isoformat()}")
            o, h, l, c, v = (float(x) for x in row[1:6])
            bars.append(Bar(start + timedelta(seconds=step), o, h, l, c, None, v))
    return bars, {"source": manifest["source"], "symbol": symbol, "interval": interval,
                  "months": months, "data_sha256": digest.hexdigest()}
