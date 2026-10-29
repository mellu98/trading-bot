# Real Timestral inference — measured exploratory results

Both official checkpoints were downloaded anonymously from pinned HuggingFace revisions, with original licenses retained and exact source/config/weights hashes verified. See checkpoints.json.28M:111296464bytes;209M:837271648bytes. No fine-tuning, reinforcement learning, paid inference or external inference service.

## Real CPU execution

Apple Silicon, four CPU threads. All required21quantiles,5operational horizons and provenance validated by the original OfficialAdapter. Both MNQ and MES produced actual predictions with target-only and past-covariate inputs. Two previously optional real-model tests now **pass, not skip**.

28M:7400actual forecasts across19–23October2026, both instruments and feature ablations. Full-call latency median13.93ms,p95 33.38ms,max238.60ms. Every measured call met the60second historical readiness budget. These are measured offline CPU timings, not a live-service SLA.

209M technical benchmark:10timed calls after warmup per context/feature case. Context120median84.1ms target-only and139.0ms past-covariates; context360median69.0ms/213.7ms. Benchmark could contend with the concurrently running28M experiment. No209M economic or full forecast-quality comparison is claimed.

## Accuracy versus last observed close

Fixed15minute origin grid;125origins per instrument/variant for horizons1/3/5/10 and120for15minutes. All five sessions were previously observed. MAE is in **price points**.

| Instrument |5min naive MAE|28M target-only MAE|28M past-covariate MAE|
|---|---:|---:|---:|
|MES|3.260|3.334|3.337|
|MNQ|19.268|19.632|20.349|

All20instrument/variant/horizon MAE comparisons were worse than the last-close baseline. Empirical central80%interval coverage ranged76.8%–86.7%; these dependent, small-sample coverage values do not establish calibration or execution usefulness. Complete pinball losses, quantile coverage and directional counts are in ../timestral-28m-experiment/results.json.

## Same V5 strategies, with/without fixed filter

Unchanged V5 execution/risk, one-bar-lagged forecast readiness, fixed5min median edge0.25point, TTL90seconds. No parameter search. Daily-reset technical accounts, not a continuous deployable portfolio; execution is not the earlier frozen V2 research engine. Conservative OHLC ambiguity remains.

| Strategy |Without AI net/trades|28M target-only net/trades|28M past-covariates net/trades|
|---|---:|---:|---:|
|VWAP|-$162.75 /25|-$151.19 /27|-$168.91 /28|
|ORB|-$108.70 /10|$0 /0|$0 /0|
|Sweep/MSS|$19.79 /18|$0 /0|$18.78 /1|

Skipping all ORB trades is **not evidence of trading advantage**. The target-only VWAP loss reduction ofUSD11.56 remains a loss, is conditional on these observed sessions, and is not statistically established. The covariate arm worsened VWAP. No robust net edge has been demonstrated; Timestral remains OFF for operational orders.

The planned120-session extension was interrupted by the user's new higher-priority V6 Capital.com mission. **No120-session Timestral analysis is claimed.** All120local sessions remain observed research material, not an independent holdout.

## Reproduce

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
./run-timestral-28m.sh verify
# Existing completed logs/results are retained. For a clean run:
./run-timestral-28m.sh prepare --output reports/timestral-28m-reproduction
./run-timestral-28m.sh infer --output reports/timestral-28m-reproduction --license-eligibility-reviewed
./run-timestral-28m.sh compare --output reports/timestral-28m-reproduction
```

User explicitly confirmed license eligibility on26October2026. The flag is not a replacement for that eligibility. Historical predictions displayed in the V6 extension are explicitly CME history, never Capital CFD signals. No strategy is approved; no paid data or real trading occurred.
