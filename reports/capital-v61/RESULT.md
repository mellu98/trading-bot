# Capital DEMO V6.1 — measured verdict

Checked 2026-10-26T14:56:05.185355+00:00. Actual DEMO CFD, not CME futures. No strategy economically approved.

| Area | Verdict | Evidence and boundary |
|---|---|---|
| Streaming | UNSTABLE | 1,074 raw quotes over180.17s, two actual connections; ALL source ages exceed unchanged5s gate. |
| Broker DEMO | VERIFIED | Authenticated configured DEMO account, reconciled flat; preserved V6 protected roundtrip. No new opening. |
| Risk engine | PARTIAL | Local owned-exit/freshness regressions pass; actual open-position kill NOT RUN because feed gate failed. |
| Forward observation | RUNNING | SIGNALS ONLY, labeled REST fallback, stale/future quotes rejected. |
| Automated paper | BLOCKED | Feed quality, actual open-position kill, certified news/strategy and longer operational validation remain incomplete. |

## Feed measurements

Observed source age, NOT one-way transport latency:

| ms | p50 | p95 | p99 | Maximum |
|---|---:|---:|---:|---:|
| WebSocket | 7341.04 | 10644.46 | 15743.42 | 16894.91 |
| REST, including rejected negative observations | 40.91 | 1043.47 | 1539.37 | 1598.43 |

No separately documented server-send timestamp: transport latency not identifiable. Independent receive thread does no HTTP/journal/strategy work. Subscription marketData.subscribe, onlyUS100/US500. Observed rates ~4.82/s and~1.14/s, not a guaranteed cadence. REST source timestamps lead nearby-receipt WS by median7,203ms. Exact upstream/network cause is not identifiable.

Query-only Apple NTP offset +154.940±39.149ms; no system clock adjustment. Best Capital RTT-bounded clock interval +122.287..312.759ms. Negative/future REST quotes remain rejected. Application ping RTT p50~93.60ms/max179.83ms. Runtime local queue/processing metrics in final-verification.json are far below the WS source-age gap.

Official policy:10 requests/s,1session POST/s,40instruments,600s inactivity; implementation retains.13s spacing,2sREST polling,30sWSapplication ping,90sheartbeat timeout. [Capital official API](https://open-api.capital.com/) and [websockets buffers](https://websockets.readthedocs.io/en/stable/topics/memory.html).

## Actual soak / recovery

660.40s wall time,130 samples, a7s application pause and SIGKILL/restart while confirmed flat. NOT an uninterrupted same-session duration or physical network cut. SQLite integrity ok; actual account-owner lock verified. One historical opening remained one; consumed budget and kill survived restart. No new orders. Fresh snapshots113/130; stale snapshots17; auth-false displayed samples1: the WS exception branch hardcoded authentication=False despite a valid HTTP session. This reporting bug was then fixed and independently regressed; it was not an observed credential rejection. No all-day/overnight certification. Actual inactivity expiry was not exercised; active calls keep sessions alive. Renewal and rejected-auth latch tested with fixtures only.

395 accepted quotes exported with original UNIXms, UTC receipt/processing, bid/ask/spread and provenance. Strictly increasing timestamps per instrument: {'US100': True, 'US500': True}. Existing signal engine blocked partial_opening_session; signals0; VWAP blocked without verified traded volume. No new-trade P&L can be inferred. Prior V6 broker loss-0.002USD remains separate from rounded EUR cash.

## Changes and tests

- Bounded single receive thread, fail-closed overflow, original UTC/monotonic capture, revalidation at use, all-market freshness,1Hz health fsync.
- Ownership-checked close/cancel allowed despite disabled entry gate; gate restored even on failure; unknown exits never blindly resubmitted. Actual open-position kill still unverified.
- Known-idle previously verified session renews once before read-only refresh; rejected401/403 latched without repeated prompts/retries. Changed tokens reconnect stream.
- Automatic strategy mode hard-blocked automated_demo_not_certified. No switch bypasses missing news/strategy certification. Old one-shot guard preserved and consumed; kill remains active.
- 124 focused tests passed,4 existing pandas warnings. Timestral, strategies, core risk, base dashboard and1,667 protected prior paths unchanged.

## Run / reproduce

Monitor already running at http://127.0.0.1:8767/. Do not start a second owner. After stopping the current instance:

```sh
"/Users/locoframe/Desktop/TRADING BOT/run-capital-demo.sh" app --mode signals_only
```

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
PYTHONPATH=src .venv/bin/python reports/capital-v61/probe.py --seconds 180
PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests_local/test_capital_input.py tests_local/test_capital_credentials.py tests_local/test_capital_auth.py tests_local/test_capital_demo.py tests_local/test_capital_runtime.py tests_local/test_capital_forward.py tests_local/test_capital_v61.py -q
```

The bounded soak command is PYTHONPATH=src .venv/bin/python reports/capital-v61/soak.py --seconds 660; it pauses/crashes only the flat signals-only owner and never sends orders. Intended rollback boundary: V6.1 capital.py/capital_app.py changes plus test_capital_v61.py; frozen strategies/data unchanged. Do not remove owned-exit/fail-closed safety fixes without separate validation.
