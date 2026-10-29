# MNQ/MES Timestral research — simulation only

A standalone Python research extension, **not an existing LEAN bot**. This initially empty workspace had no engine, dataset, broker connection or verified fee schedule. No live/paper broker integration, order submission, fine-tuning or reinforcement learning is implemented. The filter defaults to **disabled** and research results never enable it.

## Run

```sh
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen mnq-research compare --output reports/comparison.json
```

The last command exits **2**, writes `not_evaluated`, and deliberately reports **no invented P&L** when inputs are missing.

Optional official inference dependency (no weights downloaded by installation):

```sh
uv sync --frozen --extra model
```

The source is pinned to [Timestral a534bdb](https://github.com/mistralai/timestral/tree/a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff). Checkpoints, revision IDs, SHA256s and sizes are in `src/mnq_timestral/model.py`. **Weights use Modified MIT terms**, not the source code's Apache license: review [28M license](https://huggingface.co/mistralai/Timestral-28M/blob/49b26409ac87b5935539a5d8ffe7f397b720db47/LICENSE) and [209M license](https://huggingface.co/mistralai/Timestral-209M/blob/9874d252ab0aae16f7f7c999f98f98d6ad7d8365/LICENSE), including the company/employer prior-month revenue restriction above $20 million, before explicitly provisioning:

```sh
uv run --extra model mnq-research provision --model 28M --destination models/28M --license-eligibility-reviewed
uv run --extra model mnq-research provision --model 209M --destination models/209M --license-eligibility-reviewed
uv run --extra model mnq-research serve --model 28M --checkpoint models/28M --threads 1
```

Provisioning is the only model-download command. Loading/inference require locally verified config and weights and `local_files_only=True`. No weights were downloaded for implementation/testing.

## Data and experiment contract

CSV header: `symbol,contract,start,end,available_at,open,high,low,close,volume`. Symbols: MNQ/MES; contracts: actual quarterly dated symbols such as MESZ6, never a continuous/back-adjusted series. All timestamps are UTC ISO8601. `start` is the one-minute bar start; `end=start+60s`; `available_at>=end` must reflect actual historical delivery latency, not a fabricated zero-latency assumption. Positive traded futures volume only; missing minutes are never row-compressed. One active actual contract per instrument/session is declared externally. No synthetic market data is bundled.

Manifest JSON must include:

- `source`, `license`, `retrieved_at` (UTC), `audit_reference`, `attested_verified:true`, `sha256` (CSV digest), `timestamp_convention:"bar_start_utc"`, `interval_seconds:60`, `price_adjustment:"none"`.
- `calendar_source`, `news_source`, `roll_policy` (nonempty evidence references).
- `active_contracts`: date → `{ "MNQ":"MNQZ6", "MES":"MESZ6" }`, according to a documented causal roll policy.
- `sessions`: NY session date → `{ "open":"...UTC...", "close":"...UTC...", "known_at":"...UTC...", "news_complete":true, "news_blocks":[{"start":"...UTC...","end":"...UTC...","known_at":"...UTC..."}] }`. Windows already include your pre/post-event embargo. Calendar and news must have been knowable before their relevant timestamps. Unknown sessions/news block the run; no guessed holidays. A complete minute grid from 09:30 through the strategy's closing window is required for economic screening.
- `costs`: each symbol → `commission_per_side`, `exchange_per_side`, `regulatory_per_side` (USD), `spread_ticks`, `entry_slippage_ticks`, `exit_slippage_ticks`, `evidence` and `attested_verified:true`. Supply documented numbers; none are supplied as if verified.

Attestations/hashes verify declared integrity, **not independent vendor authenticity or fee correctness**. No paid data is requested. Fees and spread/slippage need your broker/exchange evidence.

```sh
uv run mnq-research plan-template --output data/plan.json
# Review the small grid and session counts; attest the holdout was previously unseen.
uv run mnq-research register --data data/bars.csv --manifest data/manifest.json --plan data/plan.json --registration data/experiment.json
uv run --extra model mnq-research forecast --data data/bars.csv --manifest data/manifest.json --checkpoint-28m models/28M --checkpoint-209m models/209M --threads 1 --output reports/forecasts.jsonl
uv run mnq-research compare --data data/bars.csv --manifest data/manifest.json --forecasts reports/forecasts.jsonl --registration data/experiment.json --output reports/comparison.json
```

The registration freezes data/manifest/plan hashes and whole-session splits. Comparison writes a one-use `.consumed.json` receipt **before** examining test/holdout results. Identical reruns return the persisted report; changed forecast/config input cannot silently reuse that holdout. Interrupted runs remain consumed and require a **new untouched period**, not deletion of the guard. This local guard does not prove the operator never inspected raw holdout data. Source edits and repeated research elsewhere remain a human governance responsibility.

`forecast` emits measured CPU latency, wall-clock generation time, simulated readiness (historical data availability + measured adapter duration), model/source revisions, checksums, context identity and quantiles for horizons 1/3/5/10/15. Actual label times remain bar end + horizon, never shifted by data/inference latency. Errors are logged, never filled with synthetic forecasts. The official adapter uses price `(B,1,T)` as target; optional **past** covariates `(B,4,T)` are log returns, volume, trailing volatility and VWAP distance. No known-future market covariates. Marginal price quantiles **are not TP-before-SL probabilities**. A forecast cannot authorize an entry at or after its target timestamp, even if its cache TTL remains valid. Horizon 1 remains in forecast diagnostics but is explicitly unavailable for economic selection under the strict next-minute-open rule.

## Strategy and execution assumptions

Reference VWAP uses HLC3 × traded volume, anchored at cash NY 09:30. Z-score uses the population standard deviation of the last 20 **historically stored residuals**; earliest warm-up completion is 09:50. Signals cross ±2.5 and rearm on leaving the zone. Windows are NY 09:45–15:30, shortened to five minutes before an externally documented early close. Both entry and execution times must pass news/calendar gates.

A is unfiltered VWAP/Z-score; B uses the exact same candidate stream plus a predicted-tail-price coherence filter; C is an **exploratory** independent directional prediction strategy. Risk is final, one contract/position per symbol, fixed MNQ TP/SL 15/8 points and MES 4/2, never widened. Tick .25; point values MNQ $2 and MES $5. Risk and capital are per-symbol research settings, **not a reconciled portfolio/broker risk engine**. The separate return-to-VWAP exit variant is not implemented.

Entry is the first minute open **strictly after** data/signal/result readiness. Brackets are anchored to the raw open, with separate spread/slippage deductions; stop-first if both levels occur, worse stop gap fills, no favorable target-gap improvement. Trades are flat each session; no trade/15-minute forecast label crosses split/session boundaries. Gaps make economic execution unpriceable and block the run. Risk checks realized plus minute-marked unrealized loss; gaps/slippage can exceed limits. Minute-bar ordering, spread and fills remain a **screening approximation**, not executable market evidence. Tick-data and actual LEAN/broker lifecycle validation remain outstanding.

Threshold/feature/horizon selection uses validation only; regime cutoffs use calibration only. Walk-forward test and reserved holdout are separate. All variants are logged; the final holdout is not reused for tuning. Reports include quantile coverage/pinball/MAE, A/B/C gross/net/fees/execution costs, rejection reasons, counterfactual missed positive baseline trades, regimes, latency/errors, cost stresses and paired daily bootstrap bounds (seeded, declared model×symbol family=4, minimum 30 sessions). Bootstrap independence across days is an assumption, not guaranteed significance. Cost stress replays the same frozen rule, never retunes it. Model attribution additionally requires preregistered floors of 30 usable forecasts and 80% actionable forecast coverage, plus positive B net P&L. Missing/stale output or unavailable validation selection produces `insufficient_model_evidence`, not evidence that the model improved returns by remaining in cash; reports show a separate cash-only reference. Plans lacking these fields must not be retrofitted after viewing a holdout. No positive outcome bypasses the execution-quality gate.

## Integration boundary

`AsyncPredictionProvider(HTTPTransport(...))`: `submit(request)` queues at most one request; `latest(request,now)` reads only cache and rejects mismatch/stale/future responses. Both avoid inference/network on the calling trading thread. Use one provider per instrument, call `close()` on shutdown. Transport has a bounded timeout/backoff; late results cannot reopen a closed provider. Local service admits at most four request workers before thread/body creation, applies a five-second absolute socket lifetime (including trickled input), permits one active inference, and refuses non-loopback binding. Expiring a socket does not cancel model compute: its admission/inference slots remain occupied until the handler returns. `Filter(enabled=False)` never requires a prediction. `entry_allowed` evaluates calendar, optional prediction, then deterministic risk. It cannot send orders. A future LEAN integration must keep exits/order ownership entirely in LEAN and be independently tested.

CPU benchmark with a saved `Request` JSON (same fields as `Request` in `schema.py`):

```sh
uv run --extra model mnq-research benchmark --model 28M --checkpoint models/28M --request data/request.json --iterations 5 --threads 1 --output reports/cpu.json
```

Tests use labeled synthetic prices, costs and mocked model outputs. They validate software behavior, **not Timestral inference accuracy, MNQ/MES profitability, broker behavior or LEAN readiness**. Remove this isolated package/environment to roll it back; no existing trading engine was altered.
