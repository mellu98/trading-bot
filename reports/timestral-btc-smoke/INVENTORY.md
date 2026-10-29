# Timestral inventory: both checkpoints actually execute

Both official cached models passed real sequential CPU1 BTC4h inference. This is technical verification, not evidence of predictive or financial advantage. Original Timestral/Runtime/Risk/live observer files are untouched; no new history, dependency, provider or service was added.

| Smoke, context256/raw closes/15steps | 28M | 209M |
|---|---:|---:|
| Three-call median/max |20.866/34.097ms|79.088/96.622ms|
| Cold load |.702s|4.302s|
| Resident after inference |268.81MiB|859.17MiB|
| Process peak incl loading |362.89MiB|1584.58MiB|

One warmup excluded. CPU/inter-op1, float32/eval, target-only, symmetric averaging true, clip_nonnegative false, all21quantiles finite/noncrossing, repeated predictions bit-identical. Official source RECORD/config/weights checks succeeded. Network connections were denied. Models never resident concurrently. Context is the first256complete4h closes from the existing CHECKSUM-verified Dec2024+Jan2025 cache, with exact input hash and source provenance. Steps are4h units, not minutes. All predictions/configuration/timing/RSS records are in28M.json/209M.json; no targets or PnL were scored.

## Evidence chronology and seams

- `src/mnq_timestral/model.py`: reusable original verified local loader. Its `.forecaster.forecast` accepts generic tensors.
- Original schema/Request/Prediction/features and HTTP service are intentionally CME1m/MNQ/MES-specific. BTC cannot honestly be relabeled to reuse that wire contract. No original schema was changed; generic official forecast is called directly for the isolated smoke.
- `reports/timestral-real/*`: actual official28M first inference and both-model CPU benchmarks. Source revisiona534bdbd244d64f3d9d743f46c7bf6fc330ed4ff; checkpoint revisions49b26409.../9874d252.... Exact bytes111296464/837271648 and hashes verified, licenses preserved.
- `reports/timestral-28m-experiment/forecasts.jsonl`:7400actual28M forecasts,3700target-only/3700past covariates, five already-observed CME sessions19–23Oct2026/MNQ+MES. Later results.json is complete actual inference; all20MAE comparisons worse than price persistence. No robust economic edge demonstrated.
-209M prior evidence is technical CME benchmarking only, not an economic209M comparison. Full120-session extension was deferred; helper presence is not execution evidence.
- `reports/local-v5/timestral-status.json`, earlier verification.json and28mexperiment/RESULTS.md contain stale prelicense/predownload statements. They are preserved, not treated as current unavailability; later real logs/checkpoints/results supersede those stage claims. License eligibility was already human-confirmed; no repeated request.
- Fake forecaster tests in test_core.py and synthetic predictions in local experiment tests validate wiring/causality, not real quality. Optional model tests require explicit checkpoint paths; past SKIPs are not real inference proof.68existing Timestral/control tests passed in this inventory run; the new two-model smoke independently used real weights.

Machine memory pressure makes these few CPU timings a narrow technical smoke, not a stable SLA. Current Binance observer87703/8767 remains flat/spent1BUY1SELL and original cash999.76609237980375. Strict entry/news/readiness guards remain blocked when unhealthy. No model has been activated in trading.

Complete mapping, provenance and mock/real distinctions: inventory.json. No Git/gentle-ai; CodeGraph NotInitialized targeted fallback. skill_resolution: paths-injected.
