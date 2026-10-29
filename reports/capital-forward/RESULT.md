# Capital DEMO — first actual forward infrastructure test

## Outcome
**One actual broker DEMO roundtrip completed. Account reconciled flat. No production routing or real-money order.**

Current monitor: http://127.0.0.1:8767/ . Quote observation continues, with the kill switch active and continuous strategy orders disabled. The live process is `./run-capital-demo.sh app --mode technical_test` (without `--technical-test`). It reuses saved credentials and the same persistent journal; setup was not repeated and no credential input was requested.

## Actual broker evidence
- Official DEMO authentication and GET/session + GET/accounts returned HTTP200. Exact configured account verified, status ENABLED, CFD, account currency EUR. No account switch, deposit, purchase or account-setting mutation.
- Identified US100 / US Tech100 and US500 / US500 via actual search plus market details, filtering exact identities. Both were TRADEABLE, marginFactor5%, lotSize1, tick0.1. Minimum quantities 0.001 and0.01 respectively. They are CFDs, NOT CME MNQ/MES futures.
- First and only entry: BUY US100, size0.001; dealReference `o_bb760591-84b0-47a9-b30d-d9eda8123090`.
- Actual fill and position: entry29088.4, stop29073.8, target29117.6, matching size/direction. Native CFD distances14.6 /29.2 points, not CME tick values or stop parameters.
- Owned position: `00000000-6e92-2ad4-049a-f76d0015549e`.
- Controlled close confirmed ACCEPTED/CLOSED via GET/confirms, close level29086.4; no positions or working orders remained.
- Broker-confirmed trade profit: **-0.002 USD**. EUR account cash delta was returned as0.00 at its available rounding precision. This does NOT imply zero economic loss. Fees, slippage decomposition and account-currency conversion of realized profit are not independently certified.
- Evidence: `actual-trade.csv`, `technical-observation.json`, `pre-crash-status.json`, journal `data/capital-v6/technical_test-EUR/state.sqlite`.

## Risk and protection
A fresh broker EURUSD quote (bid1.11871) was checked before submission. Minimum CFD size, native stop minimum/maximum distances and price increment were verified. Estimated nominal stop risk EUR0.0130507; buffered estimate EUR0.0172597; estimated margin EUR1.30064 against virtual available funds EUR1000. The normal stop is NOT guaranteed: gaps, slippage and fees are not bounded by these nominal estimates.

The entry request included broker-native stopDistance and profitDistance atomically; protection was then verified on the actual observed position. The existing Risk Engine evaluated account-currency equity before the probe. No CME point-value constants were transferred to CFD risk.

The durable one-entry budget was marked before network submission. It remains consumed across restarts and error responses. After the controlled close, order transmission returned to disabled. No autonomous strategy entry loop was enabled. The real dashboard kill control was tested while flat and is left active. Actual kill-triggered liquidation of an open position was NOT tested; the actual owned-position controlled close was tested separately.

Current virtual ceilings: daily loss EUR20, drawdown EUR30, native stop budget EUR2, maximum size1 CFD unit and max3 daily entries in configuration. The stronger single-pilot lifetime guard currently overrides those entry allowances; only ONE opening was authorized and executed. See `forward-policy.json`.

## Streaming and current quote health
Initial real WebSocket subscriptions, bid/ask reception and heartbeat acknowledgements worked. A later intentional7s process pause exposed stale recovery issues; stale reconnection was added without relaxing the5s quote-age limit. Subsequent independent new-session/new-WebSocket measurement observed quote ages8451–8643ms while REST quotes and GET/time were current. Repeated WS connections did not resolve that condition.

Therefore WebSocket freshness is **NOT certified**. Delayed data is quarantined and never substituted with fabricated timestamps. Current dashboard connection is explicitly `REST_OBSERVATION_WS_BLOCKED`; each actual quote is labeled `REST_SNAPSHOT`, with broker UTC timestamp and actual reception time. REST fallback never sends technical or strategy orders. This is periodic REST observation, NOT a healthy WebSocket stream.

At the recorded quality checkpoint:1496 accepted quote events, strictly increasing UNIX-ms timestamps per instrument. The188 explicitly labeled REST observations had age-at-receipt p95 approximately958ms, maximum2212ms. Earlier accepted unlabelled WS-era observations stayed within5s; rejected late data was not admitted. These are receipt-age statistics, not pure network latency. Quotes keep updating; `quote-quality.json` and `final-monitor-status.json` are recorded checkpoints, not permanent freshness guarantees.

## Recovery and causal signals
- Actual SIGKILL was performed ONLY after positively confirmed flat positions/orders. SQLite integrity check passed. Restart recovered the completed roundtrip and the consumed entry budget; no duplicate opening was sent.
- Actual broker GET/confirms changed affectedDeals after closure. This had caused a false ambiguity halt. The fix preserves the accepted binding and reuses the verified owned ID; changing/multiple IDs still block. The completed-flat-pilot remediation was applied narrowly, never clearing risk or kill halts.
- Stale data leads to bounded WS failure/quarantine and no new openings; REST observation remains explicitly separate.
- Quote events feed the existing causal CFD signal pipeline. VWAP is blocked because quote counts are not verified traded volume. Intraday restart/missed opening-range data sets `partial_opening_session`; no historical opening range is invented. Current US100/US500 strategy signals remain blocked for that incomplete session.
- Strict news mode remains blocked; no strategy is economically promoted. Timestral remains read-only/off for CFD orders. V1/V2 results unchanged.

## What is and is not certified
**Actual:** authenticated DEMO GETs, market/rule discovery, live WS reception and heartbeats before delay, one accepted protected minimum-size trade and controlled close, flat reconciliation, SIGKILL recovery, current labeled REST quotes, kill control while flat.

**Local/fixture only:** partial fills, deliberately malformed protections, insufficient margin, stale FX, duplicate-submit failure paths, daily-loss/drawdown triggers, and abnormal unknown mutation responses. No extra real orders were submitted to force those cases.

**Not certified:** prolonged WS freshness,24/7 uptime/session/network recovery, kill liquidation with a live DEMO position, real partial fills, strategy profitability, or autonomous continuous order operation.

## Remaining blockers for continuous order forward testing
1. Resolve/verify broker WS delay under the5s policy; REST fallback is observation-only.
2. Define verified CFD signal warm-up/restart recovery or start before New York cash open; current incomplete session stays blocked.
3. Certify news calendar before rigorous mode; no promoted strategy exists.
4. Complete longer soak and execution-quality testing, explicit approval of a new bounded DEMO order budget, and operator acknowledgement/reset of the intentional kill halt. Do NOT reset the pilot guard automatically.

## Reproduce local tests
`PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests_local/test_capital_input.py tests_local/test_capital_credentials.py tests_local/test_capital_auth.py tests_local/test_capital_demo.py tests_local/test_capital_runtime.py tests_local/test_capital_forward.py -q`

**110 passed**,4 pre-existing pandas warnings. Actual broker and crash evidence is separate from these tests. The interrupted identifier-only RED tests from the superseded mission were preserved byte-exact in `reports/capital-identifier/pending_regressions.py`; no identifier-reader changes were applied in this forward mission.

Scope: Capital CFD adapter/runtime/dashboard extension and relevant tests only. Existing Risk Engine, V5 base dashboard, Timestral, strategies and frozen evidence unchanged. No broker adapter was added. Delivery/preservation hashes in this folder identify the work unit; no Git commit was created.
