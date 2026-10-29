# Capital DEMO V6.2 — measured decision

**C — EVIDENCE INSUFFICIENT to certify the operational feed or attribute the fault specifically to the provider backend.** The WebSocket delivery path is demonstrably unsuitable for current entry gates. Missing: server emission telemetry or an independent network path to distinguish provider queueing from shared channel/network delay. No threshold was raised.

## Simultaneous measurements

241.92s; 1,285 WS quotes and474 REST observations, US100/US500 returned in the same REST response. Full original UNIXms, UTC receive ns, monotonic receive ns, parse time, bid/ask/spread retained in benchmark/rows.json.

| Instrument | WS timestamp age p50 / p95 | REST timestamp age p50 / p95 | Identical events | WS after first REST receipt p50 / p95 |
|---|---:|---:|---:|---:|
| US100 | 7.537s / 9.132s | 0.116s / 0.314s | 176 | 7.357s / 8.965s |
| US500 | 7.684s / 9.177s | 0.716s / 2.759s | 121 | 7.028s / 8.774s |

Identical-event matching requires epic + source timestamp + bid + ask; repeated REST polls are deduplicated. Client clock offset cancels. These are relative delivery differences, NOT one-way network latency. Clock bounds against GET/time: best +42.85..240.09ms. Parse p95 <0.052ms. Update interarrival p50/p95: US100175.7/505.2ms; US500864.5/3175.6ms. Diagnostic maximum4HTTPrequests/s; runtime conservative pacing retained; no observed429. [Official API](https://open-api.capital.com/).

## Controls / repeat benchmark

61.97s repeat still delayed: identical-event median5.13s/5.21s. An isolated60s Node test briefly looked fresh, but simultaneous120.96s Node and Python both reached WS source-age p95~17s/max~22.5s.574matching US100 events reached the two clients at median0.238ms apart;83US500 at0.226ms. Disabling compression also left6–8s source ages. No client/compression change is justified. One application ping RTT reached13.59s; this does not locate the internal cause. A brief fresh window is not certification.

Four US100 and eight US500 WS messages repeated unchanged bid/ask and quantities. Do not assume an exclusively bid/ask-change-only protocol; official documentation does not certify that policy.

## REST and bars

REST is useful for conservatively gated observation, not complete tick-derived OHLC. Snapshot sampling missed native extrema in3of4fully observed instrument-minutes. Native GET /prices/{US100,US500}?resolution=MINUTE&max=10 was authenticated and verified HTTP200:18closed contiguous UTC minute bars. Best same-broker alternative: REST snapshots for observation and broker-native closed minute bars for research. They are available only after actual receipt, not retrospectively for decisions. Neither path certifies intrabar execution.

## Safety / running state

Fixed a loss-counter recovery bug caused by sorted JSON processing close before entry; idempotent outcomes and daily opening-attempt limits now reach the existing Risk Engine. Actual prior loss is counted once; actual flat SIGKILL/restart preserves counter1, opening count1 and consumed budget; SQLite ok. Kill/protection/unknown-exit handling passed local regressions, not a new open-position broker test. No new orders; historical protected roundtrip unchanged.134focused tests pass,4existing warnings.1,667protected paths unchanged.

SIGNALS ONLY remains running at http://127.0.0.1:8767/ (REST_OBSERVATION_WS_BLOCKED). 1245 new accepted quotes exported; 19 rejected observations logged; 0 signals (partial opening-session gate). REST-derived signals are explicitly tagged sampled/not complete OHLC, include triggering quote context, and are execution-ineligible. News remains uncertified and blocking. No economic promotion.

## Reproduce

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
PYTHONPATH=src .venv/bin/python reports/capital-v62/compare.py --seconds 240 --output "reports/capital-v62/repro-$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests_local/test_capital_input.py tests_local/test_capital_credentials.py tests_local/test_capital_auth.py tests_local/test_capital_demo.py tests_local/test_capital_runtime.py tests_local/test_capital_forward.py tests_local/test_capital_v61.py tests_local/test_capital_v62.py -q
```

The observer already runs. After stopping its current owner, restart with the absolute command:
```sh
"/Users/locoframe/Desktop/TRADING BOT/run-capital-demo.sh" app --mode signals_only
```

Rollback scope: only Capital loss-accounting/read-only native-bar allowlist/provenance changes and V6.2 diagnostic tests; no broker switch or core-strategy/Risk Engine edits. Do not restore the known counter bug without validated replacement.
