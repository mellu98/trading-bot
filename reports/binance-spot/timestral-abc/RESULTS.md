# Timestral: not useful in this exact tested entry-filter configuration

Both28M and209M satisfy the frozen descriptive verdict **NON_UTILE_NELLA_CONFIGURAZIONE_TESTATA**. This does not establish universal Timestral uselessness. Real inference worked; the fixed four-hour-lagged entry veto worsened the positive primary baseline by suppressing every candidate. No historical result can establish UTILE or activate trading.

## Primary diagnostic: January–September2026, already observed

| Arm | Closed trades | Net USDT | PF | Hour-close DD USDT | Entry filter |
|---|---:|---:|---:|---:|---|
| A: Unchanged baseline | 26 | +7.46356876 | 1.5576528829012624 | 11.69840 | No filter |
| B: 28M veto | 0 | +0.00000000 | N/A (no trades) | 0.00000 | 0/79 allowed |
| C: 209M veto | 0 | +0.00000000 | N/A (no trades) | 0.00000 | 0/79 allowed |

BaselineA exactly reproduces every original metric in all six period/cost combinations; primary net remains7.463568755668508329USDT. Both model arms vetoed79actual flat candidates solely for insufficient forecast edge after the fixed cost hurdle—not missing forecasts, fabricated model failures or Risk changes. Both have0gross/fees/spread/slippage/net/DD and undefined trade expectancy/win rate/PF, not artificial infinite PF. Original Risk and Spot fills/stops/exits/size logic are unchanged.

| Period/cost | A trades/net USDT | B trades/net | C trades/net |
|---|---|---|---|
| secondary/base | 38 / -4.15169358 | 0 / +0.00000000 | 0 / +0.00000000 |
| secondary/adverse | 38 / -7.31721689 | 0 / +0.00000000 | 0 / +0.00000000 |
| secondary/severe | 39 / -11.75839917 | 0 / +0.00000000 | 0 / +0.00000000 |
| primary/base | 26 / +7.46356876 | 0 / +0.00000000 | 0 / +0.00000000 |
| primary/adverse | 26 / +4.05591054 | 0 / +0.00000000 | 0 / +0.00000000 |
| primary/severe | 27 / -1.40460377 | 0 / +0.00000000 | 0 / +0.00000000 |

B−A and C−A mean daily marked net: -0.02733908USDT; 5-day circular bootstrap97.5% one-sided lower -0.16878065,95% interval [-0.16878065157566746, 0.06302074563108127].10000replicates,seed1729;1/10day sensitivities retained. This is conditional observed-path resampling, not risk-path re-simulation or independent future proof. All three cost scenarios were fully replayed with identical model hurdle, not arithmetic cost subtraction or best-scenario selection.

All26originalAentry opportunities were vetoed, including nine eventually profitableAroundtrips. These are matched baseline counterfactuals, not a causal profit-lost estimate; changing positions can change subsequent candidate sets. Secondary2025cash-abstention avoids negative baseline PnL but is not evidence of model edge or a reason to select another configuration.

## Real forecast quality

100% eligible primary forecast coverage for each model;1636matched mature primary horizon2origins. Price persistence equals zero cumulative return: ONE point baseline, not two independent competitors.

| Model/horizon | N | MAE price USDT/BTC | Persistence MAE | RMSE price | 80% interval coverage | Return IC |
|---|---:|---:|---:|---:|---:|---:|
| 28M/1steps=4h | 1637 | 441.53691 | 437.86302 | 644.84725 | 0.84239 | 0.00851 |
| 28M/2steps=8h | 1636 | 633.83875 | 628.59572 | 926.80232 | 0.83741 | 0.00370 |
| 28M/3steps=12h | 1635 | 788.39520 | 778.16513 | 1145.97661 | 0.83364 | -0.01543 |
| 28M/6steps=24h | 1632 | 1193.82571 | 1170.15506 | 1696.58955 | 0.81740 | -0.08714 |
| 209M/1steps=4h | 1637 | 440.56681 | 437.86302 | 645.05381 | 0.82224 | -0.03328 |
| 209M/2steps=8h | 1636 | 634.26235 | 628.59572 | 927.71062 | 0.82029 | -0.03570 |
| 209M/3steps=12h | 1635 | 785.84685 | 778.16513 | 1144.18527 | 0.81284 | -0.05325 |
| 209M/6steps=24h | 1632 | 1186.30821 | 1170.15506 | 1684.42588 | 0.80270 | -0.09428 |

Full results.json contains cumulative-return MAE, tie-inclusive and conditional nonzero directional accuracy/counts, all21level pinball losses, interval widths, past-only empirical-return naive quantiles, secondary2025scores and paired absolute-error uncertainty. The naive quantile median may differ from point persistence. Forecast-error bootstrap values are daily mean absolute-error improvements in price units; the reused generic helper retains a field named mean_daily_net, which is NOT PnL in that nested forecast-error context.

### Lag and information age

CandidateT uses only cached forecastO=T−4h, step2targetT+4h; measured availabilityO+latency<T. This avoids pretending to infer atT and fill the same-boundary next open instantaneously. The model is four hours behind the latest known candidate price. Frozen primary forecast-quality scores fairly compare information atO, not the newer information available atT.

An explicitly additive diagnostic on26mature originalAentries compares model step2 to newer P[T] persistence:28M MAE1122.00751,209M1153.51547, newer persistence413.15154USDT/BTC (olderP[O]1142.26077). No additional strategy/PnL configuration was run; this clarifies why stale-origin forecasts reject breakouts. See matched-A-candidate-diagnostic.json/CSVs.

## Actual compute and provenance

| Model | Real valid / warmup-missing rows | Full wall / process CPU s | Path p50/p95/p99/max ms | Cold load / warmup s | Peak RSS MiB |
|---|---|---|---|---|---|
| 28M |3758 /70|35.838/35.238|8.938/11.947/19.035/36.900|0.209/0.027|432.19|
| 209M |3758 /70|250.629/239.635|58.155/103.098/166.007/1253.969|1.043/0.088|1723.09|

CPU1/inter-op1, models sequential in distinct processes, float32raw256completed4hcloses,15steps, all21officialquantiles, target-only/no covariates, symmetric averaging true, clip_nonnegative false.0nonfinite/nonpositive/crossing/model errors or timeouts; no sorting/clipping repair.70early2025warmup rows/model are explicit missing, not fake predictions. Actual wall issuance and counterfactual historical availability are distinct. Per-origin path timing includes progress-file write I/O (Path.write_text, not fsync), so it is not pure network/model latency. Pure-call smoke timings are separately in ../../timestral-btc-smoke/. Peak RSS is whole process peak incl loading, macOS ru_maxrss bytes.

Both full-run first eligible forecasts match the earlier real BTC smoke input tensor SHA and all315quantiles bit-for-bit; the smoke already made four identical calls/model. No full-model inference was repeated. Cached economic replays produced73byte-identical report artifacts; parent independently passed63provenance/ledger/accuracy/replay checks.

An original supervisor non-atomic progress-read race raised JSONDecodeError while28Mworker continued to a fully valid cache. No model/source/protocol/cache was rewritten. Parent authorized an additive supervisor with partial/absent/stale-progress controls and unchanged300s deadline before209ran once. supervisor-incident.json and supervisor-addendum.json preserve that provenance; no Git/gentle-ai authority receipt is claimed.

All2025andJan–Sep2026history was already observed before this A/B/C test. Unknown model pretraining cutoff/dataset inventory means model-training overlap cannot be ruled out. No external cutoff dates are invented. Only an issued-before-outcome future cohort can establish prospective value. Model license eligibility was already human-confirmed; original licenses and pinned checkpoint/source integrity are preserved.

## Prospective preparation, not future evidence

Prepared SIGNALS_ONLY recorder uses existing Binance PublicREST/Feed/nativeWS; no account, Risk instance, order API, simulated position or dashboard. Native4h warmup was authorized separately: exactly two publicGETs, serverTime plus fixed public native4h klines,256closedcontiguous bars through2026-10-27T08:00Z, noformingbar and no Sep→Octgap splice. These recent bars are WARMUP ONLY, never a new A/B/C financial test or backdated prospective predictions. Original1m provider allowlist is unchanged; a shadow-only fixed native4hGET is frozen in the additive bootstrap receipt.

At the next real4hboundary, complete240native1m bars or one closed1m REST reconciliation produces the new closedbar. Only healthy/complete/current256context can issue actual forecasts within300s, in sequential off-feed-loop subprocesses. The first later lagged decision cannot use a warmup-origin invented forecast. All historical catch-up remains warmup; missed/late origins never backfilled as prospective. Strict news/readiness remains blocked as appropriate.

Actual initial20sprobe:1043messages/oneclosed1m,0full4hcontexts/0modeljobs/0orders. After native warmup, actual20sprobe:2834messages,256closed4hcontext,0future4hclosures/0modeljobs/0orders. A full futurebar issuance and mature outcome were NOT observed during this session. Long-term recorder is PREPARED, not left running. Existing technical observer remains separate, flat/spent.

Future minimum:90newUTCdays AND30closed baseline counterfactual trades AND20per filtered arm; otherwise inconclusive. Promotion criteria remain the immutable parent protocol (including two-model97.5%lower bounds, costs/risk and calibration), never automatic orders or promotion. Existing live-feed instability is not solved by this research.

## Exact commands

```sh
# Existing completed cached reproduction; use a fresh tag, never overwrite journals:
PYTHONPATH=src .venv/bin/python reports/binance-spot/timestral-abc/runner.py run --tag run-3
# Targeted controls (11 unique), no models/prices/network:
PYTHONPATH=src .venv/bin/python -m pytest -q reports/binance-spot/timestral-abc/test_abc.py reports/binance-spot/timestral-abc/test_supervisor.py reports/binance-spot/timestral-abc/test_shadow.py reports/binance-spot/timestral-abc/test_bootstrap.py
# Prepared future read-only recording; no orders. Initial native warmup auto-runs only if absent:
PYTHONPATH=src OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1 .venv/bin/python reports/binance-spot/timestral-abc/shadow.py record --folder data/binance-spot/timestral-shadow --seconds 0
```
The future command is deliberately not executed indefinitely in this session. Do not rerun model inference commands over existing caches. Each model ran once; the additive supervisor is only for the209Mprogress-transport remedy, not a new inference policy.

## Identities and boundaries

| Artifact | SHA256 |
|---|---|
| Parent protocol |e4852ae6a1e3c9ff37c08b724e54f3bef23c1d3c12179baa0a09123ae5d2b3ab|
| Scientific execution freeze |fe947dd22fe92ba0ff1769792ad5fba5d73952146b43ecb4dea00d439942bc75|
| Retrospective dataset |a32da0e732d8eb1f271e3e55ba42ec916e6fbfc13a68e293e09002d9801880ac|
|28Mforecasts|32bda775df769360a64ed45b6d3429c42b8b0796f0b398c1a687667d126936e9|
|209Mforecasts|40cc3cc8ed59cc3a3856885e06d3c14b1e5838f18dc148d9dcb757c5efb2b2a9|
|Both results.json|58332fd55e3b355d8622d5f19df4b5f5e98099ab3e2b362c38c8211215004145|

Original Timestral implementation/Runtime/Risk/Spot/observer/futures baselines and prior evidence were not edited. This isolated experiment reuses the verified official generic forecaster rather than relabeling BTC as CME through the incompatible one-minute schema. Inventory and stale prelicense-document distinctions are in ../../timestral-btc-smoke/INVENTORY.md. Rollback boundary is this isolated ABC/optional shadow preparation plus separate data/binance-spot/timestral-abc and timestral-shadow folders; never reset paper.sqlite or alter prior evidence. No Git, no commits/gentle-ai authority, CodeGraphNotInitialized targeted fallback. skill_resolution: paths-injected.
