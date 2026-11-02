"""Capital.com DEMO native bid/ask 5-minute history, READ-ONLY.

Uses the bot's existing Capital.com integration (mnq_local.capital): the same
DEMO-only origin, the same Keychain credentials (service
`trading-bot.capital-demo`, or CAPITAL_DEMO_* environment variables) and the
same login/account verification. Nothing in this module can create, modify or
close an order: the bot client is constructed with orders_enabled=False and the
only extra route is a strictly validated GET on /prices with from/to, which the
bot's whitelist does not include (it only allows the latest 10/500 bars).

Bars: Capital's snapshotTimeUTC is the bar START. Mid OHLC = (bid+ask)/2 and
`spread` = ask-bid at the bar close. Historical candles can be revised by the
broker; this loader stores what the API returned at download time.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .bars import Bar

UTC = timezone.utc
EPICS = ("US100", "US500", "EURUSD", "GBPUSD", "AUDUSD", "BTCUSD")
STEP = 300
PAGE = 1000  # Capital.com maximum bars per request
ROUTE = re.compile(r"/prices/(US100|US500|EURUSD|GBPUSD|AUDUSD|BTCUSD)\?resolution=MINUTE_5&max=1000"
                   r"&from=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}&to=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
FIELDS = ["start_utc", "bid_o", "bid_h", "bid_l", "bid_c", "ask_o", "ask_h", "ask_l", "ask_c", "volume"]


def csv_path(cache: Path, epic: str) -> Path:
    return cache / "capital" / f"{epic}-MINUTE_5.csv"


class ReadOnlyHistory:
    """Thin read-only extension of the bot's verified DEMO session."""

    def __init__(self, http):
        if http.orders_enabled:
            raise ValueError("history client must be built with orders_enabled=False")
        self.http = http
        self.relogins = 0

    def prices(self, epic: str, start: datetime, end: datetime) -> dict:
        path = (f"/prices/{epic}?resolution=MINUTE_5&max={PAGE}"
                f"&from={start:%Y-%m-%dT%H:%M:%S}&to={end:%Y-%m-%dT%H:%M:%S}")
        if not ROUTE.fullmatch(path):
            raise ValueError("forbidden history route")
        if not self.http.verified or not self.http.tokens:
            raise RuntimeError("Capital DEMO session not verified")
        time.sleep(0.15)  # stay well under the documented 10 requests/second
        headers = {"Accept": "application/json", "User-Agent": "trading-bot-ict-history/1",
                   **self.http.tokens}
        for attempt in range(4):
            try:
                status, result, _ = self.http.sender("GET", path, headers, None)
                break
            except ConnectionError:  # CapitalError('transport_unknown'): timeout/reset on an idempotent GET
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        if status in (401, 403) and self.relogins == 0:
            self.relogins += 1
            self.http.login()  # one renewal of an expired DEMO session, through the bot's own login
            return self.prices(epic, start, end)
        return {"status": status, "body": result}


def _dec(x) -> Decimal:
    value = Decimal(str(x))
    if not value.is_finite():
        raise ValueError("non-finite price")
    return value


def _parse(raw: dict) -> dict:
    text = raw.get("snapshotTimeUTC")
    if not isinstance(text, str):
        raise ValueError("explicit UTC timestamp required")
    start = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if int(start.timestamp()) % STEP:
        raise ValueError("timestamp not aligned to 5 minutes")
    row = {"start_utc": start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    for side, key in (("bid", "bid"), ("ask", "ask")):
        o, h, l, c = (_dec(raw[n + "Price"][key]) for n in ("open", "high", "low", "close"))
        if not 0 < l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("invalid native OHLC")
        row.update({f"{side}_o": str(o), f"{side}_h": str(h), f"{side}_l": str(l), f"{side}_c": str(c)})
    if any(_dec(row[f"ask_{k}"]) < _dec(row[f"bid_{k}"]) for k in "ohlc"):
        raise ValueError("crossed bid/ask")
    volume = raw.get("lastTradedVolume")
    row["volume"] = "" if volume is None else str(_dec(volume))
    return row


def instrument_overrides(market: dict) -> dict:
    """Map /markets/{epic} metadata to config overrides (lot step, minimum, margin, tick)."""
    i, r, s = market["instrument"], market["dealingRules"], market["snapshot"]
    out = {
        "lot_step": float(r["minSizeIncrement"]["value"]),
        "min_qty": float(r["minDealSize"]["value"]),
        "margin_rate": float(i["marginFactor"]) / 100.0,
        "account_currency": i.get("currency", "USD"),
    }
    places = s.get("decimalPlacesFactor")
    if isinstance(places, int) and 0 <= places <= 8:
        out["tick_size"] = 10 ** -places
    return out


def download(cache: Path, epic: str = "US100", months: int = 36, log=print) -> dict:
    if epic not in EPICS:
        raise ValueError(f"epic must be one of {EPICS}")
    from mnq_local.capital import CapitalHTTP, Credentials  # bot integration (Keychain, DEMO only)

    http = CapitalHTTP(Credentials.load(), orders_enabled=False)
    account = http.login()
    market = http.request("GET", f"/markets/{epic}")
    history = ReadOnlyHistory(http)
    target = csv_path(cache, epic)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict] = {}
    if target.exists():
        with target.open(newline="") as stream:
            rows = {r["start_utc"]: r for r in csv.DictReader(stream)}
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    end = now - timedelta(minutes=now.minute % 5)
    stop_at = end - timedelta(days=int(months * 30.44))
    window = timedelta(seconds=STEP * (PAGE - 1))  # from/to inclusive: 1000 steps = 1001 bars -> error.invalid.max.daterange
    empty_streak, requests, rejected, quarantined = 0, 0, None, {}
    while end > stop_at:
        start = max(stop_at, end - window)
        reply = history.prices(epic, start, end)
        requests += 1
        if not 200 <= reply["status"] < 300:
            rejected = {"status": reply["status"], "error": (reply["body"] or {}).get("errorCode"),
                        "from": start.isoformat()}
            log(f"  API stopped at {start:%Y-%m-%d}: {rejected}")
            break
        prices = reply["body"].get("prices", [])
        if not prices:
            empty_streak += 1
            if empty_streak >= 6:
                log(f"  no data before {end:%Y-%m-%d}: history exhausted")
                break
        else:
            empty_streak = 0
            for raw in prices:
                try:
                    row = _parse(raw)
                except ValueError as error:  # broker candle anomaly: quarantined and counted, never repaired
                    quarantined[str(error)] = quarantined.get(str(error), 0) + 1
                    continue
                rows[row["start_utc"]] = row
        if requests % 20 == 0:
            log(f"  ...{start:%Y-%m-%d} ({len(rows)} bars)")
        end = start
    ordered = [rows[k] for k in sorted(rows)]
    if not ordered:
        raise SystemExit(f"Capital.com non ha restituito barre storiche per {epic}: {rejected or 'nessun dato'}. "
                         "Nessun file scritto. Copia questo messaggio a Claude per adattare i parametri.")
    with target.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(ordered)
    manifest = {
        "source": "Capital.com DEMO REST /prices (native bid/ask), read-only",
        "epic": epic, "resolution": "MINUTE_5", "bars": len(ordered),
        "first_start": ordered[0]["start_utc"] if ordered else None,
        "last_start": ordered[-1]["start_utc"] if ordered else None,
        "requests": requests, "stopped_by": rejected, "quarantined_bars": quarantined,
        "downloaded_at_utc": datetime.now(UTC).isoformat(),
        "account_currency": account.get("currency"),
        "instrument_overrides": instrument_overrides(market),
        "csv_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "note": "Broker candles may be revised after download; coverage depends on the depth the API serves.",
    }
    (cache / "capital" / f"manifest-{epic}.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def load(cache: Path, epic: str) -> tuple[list[Bar], dict]:
    path = csv_path(cache, epic)
    manifest_path = cache / "capital" / f"manifest-{epic}.json"
    if not path.exists() or not manifest_path.exists():
        raise SystemExit(f"no Capital.com history for {epic}: run the download command first")
    manifest = json.loads(manifest_path.read_text())
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != manifest["csv_sha256"]:
        raise SystemExit("Capital history file changed after download; re-run download")
    bars = []
    with path.open(newline="") as stream:
        for r in csv.DictReader(stream):
            start = datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00"))
            mid = {k: (float(r[f"bid_{k}"]) + float(r[f"ask_{k}"])) / 2 for k in "ohlc"}
            spread = float(r["ask_c"]) - float(r["bid_c"])
            vol = float(r["volume"]) if r["volume"] else None
            bars.append(Bar(start + timedelta(seconds=STEP), mid["o"], mid["h"], mid["l"], mid["c"], spread, vol))
    return bars, {"source": manifest["source"], "symbol": epic, "data_sha256": sha,
                  "instrument_overrides": manifest.get("instrument_overrides", {})}
