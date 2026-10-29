# V6.3 — native Capital DEMO candles

**Verdict: NOT RELIABLE FOR AUTOMATIC ENTRIES. Forward collection is running; orders remain disabled.**

## Measured, not simulated

Official authenticated `GET /prices/{epic}`: **1,328 successful reads over 721.74 seconds**, US100/US500, MINUTE/MINUTE_5. No transport errors. The application now uses native candles only; no WebSocket connection and no snapshot-derived OHLC signals.

First observed source rollover after nominal bar end (client UTC; availability upper bounds, NOT exact publication or network latency):

| Instrument / resolution | Closures observed | p50 | p95 | Maximum |
|---|---:|---:|---:|---:|
| US100 / 1m | 12 | 7.044s | 17.978s | 22.684s |
| US500 / 1m | 12 | 11.916s | 16.510s | 16.822s |
| US100 / 5m | 2 | — | — | 16.468s (range 10.955–16.468s) |
| US500 / 5m | 2 | — | — | 17.092s (range 12.534–17.092s) |

**100/1,328 responses contained crossed bid/ask values. 204 historical revision events affected 56 instrument/resolution bars, all in ask fields; bid OHLC/volume did not change in those events.** These revisions occurred after a successor source bar was already present. No duplicate, reordered or noncontiguous source responses in this bounded capture. Raw payloads and before/after examples are retained in `raw-candles.jsonl` and `native-analysis.json`.

No claim is made about the provider's undocumented reason for changing ask history. The payload is unsuitable for certifying immutable bid/ask bars. The official API exposes no finality flag. The five-second safety limit was NOT increased.

## Working software and actual forward

- Native provider: explicit UTC and integer receipt ns; observed successor plus two stable post-close reads ≥1s apart; historical bootstrap is not counted as forward latency. Revisions/invalid geometry quarantine the affected context. API pacing remains conservative.
- ORB/MSS reuse frozen kernels with explicit CFD tick/lot/currency checks and 1m/5m profiles. Actual verified availability gates the event-time kernel; actual decision times remain audited. No CME volume, costs or cash-risk model is imported. VWAP remains blocked without verified volume.
- Same SQLite owner/cache/journal, REST bid/ask observation, broker reconciliation, native quality/delay dashboard. Actual forward produced **4 no-entry decisions, 0 nonzero candidates and 0 new orders** before all four contexts were quarantined. This is NOT evidence of financial performance.
- First native runtime observed **390.10s**, second **248.03s**, followed by the current running instance. REST source age in the first segment: p50 267.6ms, p95 2,734.3ms, max 5,606.2ms; stale samples were rejected. Native strategy processing p95 6.72ms, startup max 547.70ms.
- Actual SIGKILL while broker flat: SQLite integrity OK, cache and 860 processed IDs restored, no duplicate decisions. Prior one-entry budget, loss counter and kill state preserved. Reconciliation confirms zero positions and working orders.
- **159 tests passed**, including real local PTY/Keychain fixture tests. Risk kill/stale/loss/position limits and protected exits have local contract coverage. Open-position kill/crash recovery was **NOT** newly tested on the broker: unsafe feed prevents opening. Prior real protected DEMO roundtrip evidence remains intact.
- **1,667 protected paths and previous reports unchanged.** Timestral off; no real-money route, no economic strategy approval.

## Remaining gates

Stable native bid/ask and bounded availability; longer multi-session observation; certified news calendar; calibrated CFD costs/execution and independent financial validation. Automated DEMO remains BLOCKED. Collection continues, but quarantined bars do not generate new signals. No broker change, purchase or new strategy.

## Reproduce

From `/Users/locoframe/Desktop/TRADING BOT`:

```sh
# Already running: do not start a second journal owner.
./run-capital-demo.sh app --mode signals_only

PYTHONPATH=src:tests_local:adapters/databento/src:adapters/databento_planner/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests_local/test_capital*.py -q
PYTHONPATH=src .venv/bin/python reports/capital-v63/analyze_native.py
.venv/bin/python reports/capital-v63/verify_forward.py
```

Dashboard: http://127.0.0.1:8767/. Evidence: `verification.json`, `recovery.json`, `actual-decisions.json`, `regression-tests.txt`. Current process identity is in `runtime-pid.json`.

Official endpoint/schema/rate-limit reference: [Capital.com Public API](https://open-api.capital.com/). No guarantee of historical candle finality is inferred from that documentation.
