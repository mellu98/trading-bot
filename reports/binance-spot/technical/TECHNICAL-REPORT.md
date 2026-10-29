# BTCUSDT public feed and one local paper roundtrip: PASS

Real Binance Spot public REST/WebSocket data drove exactly **one local virtual BUY and one SELL**, including a real SIGKILL with an open protected position and recovery from the same SQLite journal. No account, credentials, private endpoint, remote order, leverage or margin was used. This proves technical plumbing, NOT an economically validated strategy.

## Actual result

| Item | Measured value |
|---|---|
| Mode | LIVE_PUBLIC_DATA_LOCAL_PAPER / BTCUSDT |
| Entry UTC | 2026-10-27 06:20:06.561452 |
| Quantity | 0.00125000 BTC, actual LOT_SIZE grid |
| Observed entry bid / ask | 79804.00 / 79804.01 USDT |
| Modeled entry fill | 79811.990401 USDT = ask × 1.0001 |
| Entry fee / total cash consumed | 0.09976498800125 / 99.86475298925125 USDT |
| Persisted protective stop | 79412.93 USDT |
| Initial modeled loss including costs | 0.707773341385 USDT; not a guaranteed gap-loss bound |
| Persisted deadline UTC | 2026-10-27 06:21:06.561457 |
| Actual local exit UTC / reason | 2026-10-27 06:21:06.600313 / time_exit |
| Observed exit bid / ask | 79792.44 / 79792.45 USDT |
| Modeled exit fill | 79784.460756 USDT = bid × 0.9999 |
| Exit fee | 0.099730575945 USDT |
| Gross after modeled slippage | -0.03441205625 USDT |
| Total modeled fees | 0.19949556394625 USDT |
| Net / final virtual cash | **-0.23390762019625 / 999.76609237980375 USDT** |
| Final exposure / lifetime budget | Flat, zero BTC; spent, no second BUY |

Fees are an explicitly modeled 0.1% each side, settled in quote USDT for this simulator, without BNB discount. They are NOT an account-certified fee tier/asset or real charges. Maximum initial cash is 100 USDT including entry fee, from 1000 virtual USDT. No Spot amount is interpreted as a CME contract or futures point value.

## Functional status

| Capability | Evidence |
|---|---|
| FEED LIVE | Actual public native trades/bookTicker/kline_1m; REST/WS comparisons pass |
| PAPER ENTRY | One deterministic technical BUY only after the feed certificate passed |
| STOP / RISK | Real stop/deadline persisted and recovered; synthetic stop/kill/stale-exit paths pass. **No natural stop trigger claimed** |
| PAPER EXIT | Actual fresh public bid used for the 60-second local exit; no remote SELL |
| PNL | Exact Decimal execution/cash/fee/PnL reconciliation; two executions, one closed cycle |
| RECOVERY | SIGKILL PID 56486 while open; PID 56788 restored the same journal, position, stop, deadline and spent budget; no duplicated BUY |

The certificate before entry recorded 60.024 actual connected seconds, one real native x=true closed minute candle, fresh book/trades, exact REST book/candle comparison and 982 shared REST/WS trade matches. Source clock midpoint offset was +146.581 ms with ±127.366 ms request uncertainty. Maximum measured receipt-to-handler queue delay was 58.366 ms. Raw source ages include negative values; they are recorded, not presented as transport latency. Source-age freshness is gated using the reported clock uncertainty; no host clock or threshold was changed to obtain PASS.

bookTicker has no exchange E/T timestamp: only actual UTC/monotonic receipt freshness is measurable. Closed native candles alone are signal-ready; forming candles are retained but cannot satisfy that gate. Trade ID gaps are checked and reconciled against public recent trades. Book update IDs must increase but are NOT assumed contiguous. The actual process restart produced a trade gap and REST reconciliation recovered it.

## Reused runtime, not a broker adapter

- SpotRuntime subclasses the existing V3 Runtime and reuses its order/state ownership, stop/cycle conventions, the existing AtomicJournal/Journal and **unchanged Risk/RiskState**. Necessary opt-in Spot accounting/admission overrides avoid the original hardcoded integer CME quantity, 0.25 tick, point values, futures fee floor and expiry/cash-session rules.
- Existing Dashboard/View/server and renderer are reused. Only the conditional Spot panel was added to the old dashboard HTML; the historical branch and port 8765 were not replaced.
- Public HTTP is fixed-origin, GET-only, path/parameter allowlisted, redirects refused, no environment proxy/account cookies, no order/private route. Native WS uses bounded buffering and bounded reconnect backoff, with TLS verification and protocol ping/pong support.
- New entries require 60 seconds, a native closed candle, receipt/source freshness ≤2 seconds, spread ≤10 bps, queue delay ≤250 ms, clock uncertainty and coherent REST evidence. Protective exits bypass entry certificate/spread/news/kill gates but require a newly received valid fresh bid. Without one, the exit remains durable and pending.
- Stop 0.5%, exit 60 seconds, daily risk 10 USDT / global drawdown 20 USDT; long/flat only, one position and one lifetime technical BUY. Original deterministic Risk is unchanged. News strict mode remains blocked, economic strategy unapproved, Timestral disabled.

## Source freeze and recovery correction

The successful actual roundtrip used protocol SHA256 `6618d16afb607de89e8c2065ad004f4d7e2062e88c4c2af5259e70bc3202a4a0`, preserved as protocol-v1-completed-roundtrip.json with exact successful source snapshots in successful-roundtrip-source/.

After the position was flat, one synthetic RED→GREEN transport fix added an epoch guard: every reconnect clears the cached quote/trade receipt and discards buffered packets captured before the new connection. No parameters, costs, timing/freshness thresholds or risk rules changed. No further BUY was permitted. The current source manifest is frozen under protocol SHA256 `66d678f232061456734399f08b8b663b916adfcb466c3e50151bbcce9c01ec64`; epoch-safety-amendment.json records exact old/new source hashes. The observer was restarted flat under that source and its real feed certificate passed again.

## Running observer and commands

**PID 57187**, [existing dashboard server on port 8767](http://127.0.0.1:8767), journal `/Users/locoframe/Desktop/TRADING BOT/data/binance-spot/paper.sqlite`. It remains **OBSERVE_ONLY**, with exactly one BUY/SELL and the persistent lifetime budget spent. It cannot create another technical entry after restart. Public raw logs/journal append while observing; stop this owned observer when no longer needed.

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
./run-binance-paper.sh
# Existing spent journal resumes observation, NOT another roundtrip.
# Stop only this flat observer if desired:
kill -TERM 57187
```

Do not delete/reset the journal to force another BUY. No paid subscription or trade was requested. Default UI remains loopback-only and cannot activate a broker or live mode.

## Verification and preservation

**58 tests pass: 12 Spot + 46 pertinent existing Risk/journal/replay/dashboard tests**. Original RED logs and both green runs are retained. Four pre-existing pandas timezone warnings are unrelated. The optional IB v4 test module could not collect because ibapi is absent; it was not installed or activated, and that failure is not counted as a passing test.

```sh
export PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -m pytest tests_local/test_binance_spot.py tests_local/test_dashboard.py tests_local/test_replay.py tests_paper/test_runtime.py -q
```

The prior 1978-path baseline was rechecked: the **only changed prior path is src/mnq_local/dashboard.html**, explicitly required for its opt-in Spot view. Its exact original bytes/hash are recoverable from dashboard-before-spot.html. All 459 frozen archive entries verify unchanged. Previous H1/research/Capital/vendor evidence and production Risk Python sources remain untouched. No Git commit or unavailable native review receipt is claimed.

Evidence: technical-verification.json, real-restart-control.json, open-before-sigkill.json, open-after-real-restart.json, journal-lifecycle-evidence.json, roundtrip.json, raw public JSONL, state-export.json and epoch-safety-amendment.json. Current process/status exports update while observing; closed roundtrip and verification snapshots remain independently readable.

## Attribution and scope

Market data: Binance Spot public market-data-only API. Sources: [public endpoints](https://developers.binance.com/en/docs/products/spot/faqs/market_data_only), [native streams](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md), [published fee schedule](https://www.binance.com/en/fee/trading), [public-data terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md). Scope is local, noncommercial, nonproduction technical paper research only; no commercial/live proprietary execution or redistribution license is inferred.

No historical 2025 BTC price was downloaded or inspected for this technical task. The separately frozen research protocol was not changed or evaluated here.
