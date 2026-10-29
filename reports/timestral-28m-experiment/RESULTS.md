# Timestral-28M experiment — not yet model-evaluated

## Answers supported by current evidence

1. Real Timestral forecasts on MNQ/MES: **not verified**. No checkpoint weights were downloaded or executed.
2. Forecast accuracy and operational usability: **not evaluated**. CPU latency, calibration, coverage and model error remain unknown.
3. Improvement in net strategy results: **not evaluated**. Missing model outputs are not substituted with mock or random-walk forecasts.

The external prerequisite is confirmation of eligibility under the checkpoint's Modified MIT company/employer prior-month worldwide consolidated revenue condition (USD20 million threshold). The pinned official license was re-fetched with HTTP200 and matches the V5 SHA256. See `../timestral-28m-verification/license-current.json`. Public download availability does not establish eligibility.

## Work actually executed

Unchanged V5 runtime, risk, journal and conservative OHLC matching; actual cached CME bars, 19–23 October2026, MNQ/MES,3900bars. These five sessions and all120 historical sessions have already been observed. This is an initial technical comparison, NOT new independent evidence or a reproduction of V2's different execution model. Each day uses a fresh diagnostic account, not a continuously deployable portfolio.

| Existing strategy, no AI | Closed trades | Gross after modeled slippage | Fees | Net | Profit factor | Worst session marked drawdown |
|---|---:|---:|---:|---:|---:|---:|
| VWAP V1 |25|-$132.25|$30.50|-$162.75|0.4323|$47.91|
| ORB V2 under V5 execution |10|-$96.50|$12.20|-$108.70|0.1473|$42.66|
| Sweep/MSS V2 under V5 execution |18|$41.75|$21.96|$19.79|1.1224|$47.41|

No winner is promoted. OHLC ambiguity flags:10/6/5 respectively; these include more than stop/target collisions. Net results use V5's adverse execution model, $0.61fees/side and1tick slippage. The positive five-day Sweep/MSS result does not overturn the prior120-session research conclusion.

Non-AI forecast reference (last known close), mean absolute error in **price points**,250total origins across instruments at each horizon except15min (240):

| Horizon minutes | MES MAE | MNQ MAE |
|---|---:|---:|
|1|1.500|9.846|
|3|2.470|15.846|
|5|3.260|19.268|
|10|5.054|28.576|
|15|6.25625|35.1270833|

These are NOT Timestral forecasts or results.

## Implemented experiment

- Original pinned `OfficialAdapter` and `TimestralForecaster`; no changes to previously verified components.
-28M only, close-price target; target-only and past-covariate ablations; horizons1/3/5/10/15.
-7400planned real forecast records, all causal prefixes; cached JSONL with input keys, pinned model identity, quantiles, wall timestamp and separately declared historical readiness.
- Fixed5min median directional filter, minimum0.25point edge, TTL90seconds; no threshold search.
- One-bar lag and measured full-call CPU readiness prevent same-boundary inference/lookahead. Strict risk/news gates remain final authority.
- Scores on fixed15min origin grid: MAE vs last-close reference, directional accuracy with tie handling, pinball, quantile coverage/calibration,80%interval width/coverage. No statistical independence or financial usefulness assumed.
- Matched filtered replays, daily net differences and total-call latency distribution. Economic comparison refuses incomplete forecast logs.

## Verification

-54original tests passed;2real-model tests skipped because no provisioned weights.
-44local tests passed (33existing+11new). **98unique passes,2skips**, not the sum of overlapping suite totals.
- New tests use clearly synthetic forecast fixtures; they are not real-model verification.
-1519previously verified files unchanged. October19VWAP tradeCSV matches original V5 byte-for-byte.
- Runtime and checkpoint eligibility gates were exercised; unauthorized provisioning fails before any network/checkpoint access.

## Reproduce

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
./run-timestral-28m.sh verify
# Only AFTER eligibility has actually been confirmed:
./run-timestral-28m.sh infer --license-eligibility-reviewed
./run-timestral-28m.sh compare
```

Inference uses the existing torch environment; baseline/comparison use the existing V5 environment. No new dependencies installed. The infer command may resume complete JSONL records; damaged or duplicate logs fail closed. Use a fresh output directory for a clean rerun:

```sh
./run-timestral-28m.sh prepare --output reports/timestral-28m-reproduction
./run-timestral-28m.sh infer --output reports/timestral-28m-reproduction --license-eligibility-reviewed
./run-timestral-28m.sh compare --output reports/timestral-28m-reproduction
```

Paper/live trading remains disabled. No broker, dashboard, paid-data request, production access or new strategy was added.
