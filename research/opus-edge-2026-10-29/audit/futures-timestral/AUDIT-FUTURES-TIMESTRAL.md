# Independent audit: MNQ/MES intraday research and the Timestral experiments

Audit date: 2026-10-29. Auditor stance: try to break the earlier reports, don't confirm them.

Scope: `reports/PROJECT-VERDICT.md` §C (six futures ledgers, Timestral "zero trades"), the code that produced those
results, and the saved artefacts. Everything here was recomputed from saved ledgers, saved bars and saved forecasts
with my own code. I reused no project module, so the engine was re-implemented rather than imported.

Constraints respected:
- Nothing in the workspace was modified. 179/179 protected hashes still match `reports/binance-spot/pause-ab/protected-before.json`.
- No services, network calls, Databento or broker access, and no model inference.
- All scripts and outputs are in this folder.
- Files under `research/opus-edge-2026-10-29/` changed during this session. They were not written by this audit.

Severity scale:
- **DEMONSTRATED ERROR**: shown with reproducible numbers.
- **PROBABLE ISSUE**: strong evidence, but it rests on an assumption that the data can't settle.
- **THEORETICAL CONCERN**
- **VERIFIED OK**

---

## 1. Most important results

1. **The Timestral "zero trades" result on BTC is a degenerate test (DEMONSTRATED). It says nothing about the model.**
   - **How the veto works.** It compares the median of a forecast made at O = T−4h with the breakout close at T: `median_step2(O) > close_T·(1+0.24%)` (`reports/binance-spot/timestral-abc/runner.py:25-31,61`).
   - **Why it can never pass.** A breakout candidate must satisfy `close_T > max(high of prior 20 bars)`, which is at least P[O] (`reports/binance-spot/breakout-4h/runner.py:39-42`). This holds for 79/79 primary and 113/113 secondary candidates. So a pure persistence forecaster (median = P[O]) would also veto 100%.
   - **The model can't clear the bar.** To pass, the model would have had to predict, four hours *before* the breakout bar, a further rise of at least the breakout return plus 0.24%. That is ≥0.41% for the smallest breakout and ≈1.3% for the median one.
   - Over all 1,638 origins in 2026, the 28M median 8h forecast has p99 = +0.46%. For the 79 candidates, the maximum is +0.46% (28M) and +0.28% (209M).
   - An oracle that knew the true price at T+4h would accept 25/79. So the gate is not logically impossible, but it is impossible for any realistic martingale-like forecaster.
   - **Consequence.** The economic leg of the `NON_UTILE` verdict ("filtered net ≤ A") is trivially satisfied.

2. **The MNQ/MES 28M filter mostly measured the sign of the trigger bar, not the model (DEMONSTRATED).**
   - **How it works.** The candidate price is `close_t`, but the forecast used has origin t−1 (`src/mnq_local/timestral_experiment.py:112-115`, `src/mnq_timestral/strategy.py:65-67`). So the edge = (model's predicted move) − (bar-t move).
   - **Recomputation.** All 316 recorded decisions were recomputed exactly from `forecasts.jsonl`. Without any model, a persistence forecaster gives the identical decision in 305/316 (96.5%).
   - **Effect by strategy.**
     - ORB and Sweep/MSS trigger bars moved in the signal direction in 35/35 cases, so they were rejected (0/12 and 0–1/23 accepted).
     - VWAP trigger bars moved against the signal in 122/123 cases, so VWAP was accepted (118/123).
   - **This is not a units, quantile-order, horizon, latency, TTL or stale-cache problem.** All of those check out (section 3, Part B).

3. **"Negative already GROSS" holds only under the engine's stop-first convention, and only for MNQ VWAP/ORB (PROBABLE ISSUE).**
   - **Reconciliation.** All six ledgers reconcile to the cent: 2,144 trades. Costs, timing, entry price, brackets and exits were each independently re-simulated, with a 100% match.
   - **The convention.** When stop and target are touched in the same 1-minute bar, the engine books the stop (`src/mnq_timestral/evaluation.py:83-87`). The stops are smaller than a typical 1-minute bar: the MNQ stop is 8 pts against a median 1-minute range of 15.5 pts.
   - **Placebo.** Trading the *opposite* direction at the identical entry times also loses gross in 5 of 6 arms (MNQ VWAP −1,179; ORB −516; Sweep −518; MES VWAP −270; Sweep −294).
   - **Random-direction null.** Entering at every eligible minute in a random direction loses −$1.16/trade on MNQ and −$0.38/trade on MES under stop-first.
   - **Neutral resolution.** With a first-passage resolution of the ambiguous bars, gross is statistically zero for all six arms (t between −1.15 and +1.73).
   - **Directional skill.** The side-minus-opposite difference is not significant in any arm (t from −0.75 to +1.22).
   - **Robust conclusion.** No directional edge, and losses are driven by costs. It is *not* an anti-edge.

4. **"Net negative" is robust for MNQ VWAP and all three MES arms. It is borderline for MNQ ORB and inconclusive for MNQ Sweep/MSS (PROBABLE ISSUE for Sweep).**
   - **MES.** Even under the most optimistic convention, the upper 95% bound of gross per trade (1.91 / 2.90 / 2.73) stays below the cost of $3.73.
   - **MNQ Sweep/MSS.**
     - The first-passage net is −$11 (breakeven).
     - The daily-net 95% CI is [−5.2, +4.9].
     - The project's own block-5 CI is [−8.74, +2.16].
     - The reported −379.42 is within noise and convention sensitivity.

---

## 2. Gross vs net (daily-reset ledgers, 1 tick per side, 120 sessions)

Source: `a1_ledger_audit.json`, `a2_null_reimpl.json`, `a3_power.json`.

The gross figures are shown under four ways of resolving bars where stop and target were both touched:

| Label | How ambiguous bars are resolved |
|---|---|
| stop-first | Stop is booked first. The engine's convention; the reported numbers. |
| first-passage | Driftless probability of touching the stop first. |
| OHLC heuristic | O→L→H→C if the bar closed up, otherwise O→H→L→C. |
| target-first | Target is booked first. Upper bound. |

| Arm | Trades | Gross, stop-first | trade t | Costs (fees+slip) | **Net reported** | Gross, first-passage | Net, first-passage | Gross, OHLC heuristic | Gross, target-first | Net, target-first | Side − opposite t |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ VWAP | 627 | −1,844.00 | −3.55 | 1,396.00 | **−3,240.00** | −584 | −1,980 | −418 | +1,606 | +210 | −0.75 |
| MNQ ORB | 176 | −700.00 | −2.60 | 391.94 | **−1,091.94** | −140 | −531.94 | −194 | +910 | +518.06 | −0.41 |
| MNQ Sweep/MSS | 294 | +275.00 | +0.72 | 654.42 | **−379.42** | +643 | −11.42 | +505 | +1,333 | +678.58 | +1.22 |
| MES VWAP | 633 | −188.75 | −0.54 | 2,359.20 | **−2,547.95** | +60 | −2,299.20 | −38.75 | +501.25 | −1,857.95 | +0.13 |
| MES ORB | 173 | −50.00 | −0.27 | 644.68 | **−694.68** | +10 | −634.68 | +40 | +130 | −514.68 | −0.19 |
| MES Sweep/MSS | 241 | +68.75 | +0.31 | 897.70 | **−828.95** | +118.75 | −778.95 | +98.75 | +218.75 | −678.95 | +0.98 |

Costs per round trip:

| | Fees | Slippage | Total | Share of stop risk |
|---|---:|---:|---:|---:|
| MNQ | $1.22–1.24 | $1.00 | $2.23 | 14% of $16 |
| MES | $1.22–1.24 | $2.50 | $3.73 | 37% of $10 |

Ambiguous trades: MNQ 75 / 35 / 23; MES 23 / 6 / 5.

Can 120 sessions settle the question? The table shows the 95% CI of gross per trade under the first-passage estimate, against the cost per trade:

| Arm | 95% CI of gross/trade | Cost/trade | Verdict |
|---|---|---:|---|
| MNQ VWAP | [−2.52, +0.65] | 2.23 | Rejects net profitability |
| MNQ ORB | [−3.66, +2.07] | 2.23 | Borderline |
| MNQ Sweep | [−0.29, +4.66] | 2.23 | Cannot reject |
| MES VWAP | [−0.99, +1.18] | 3.73 | Rejects |
| MES ORB | [−2.02, +2.14] | 3.73 | Rejects |
| MES Sweep | [−1.29, +2.28] | 3.73 | Rejects |

Caveats:
- All 120 sessions are a single six-month sample. Intraday drift was about zero: mean RTH return −0.02%/day, 55/120 up days for MNQ.
- Every session had already been inspected before these strategies were defined, and there is no out-of-sample period.

---

## 3. Findings table

| ID | Component | Category | Severity | Evidence (file:line / artefact) | Numeric impact | Changes the conclusion? |
|---|---|---|---|---|---|---|
| **B-1** | BTC Timestral A/B/C entry veto | Horizon/anchor misalignment, degenerate test | **DEMONSTRATED ERROR** (design) | `reports/binance-spot/timestral-abc/runner.py:25-31` (gate), `:61` (`rec=forecasts[now-4h]`, `current=close[now]`); `reports/binance-spot/breakout-4h/runner.py:39-42` (breakout ⇒ close_T > P[O]); `b2_btc_abc_filter.json` | 0/79 (primary) and 0/113 (secondary) accepted, for both models and all three cost scenarios. Persistence forecaster: 0/79. Breakout-bar return median +1.07% (min +0.17%) versus model's own 8h median return (all 2026 origins) p50 +0.014%, p99 +0.46%. Oracle: 25/79. Non-stale rules would accept 6/79 (28M own-anchor) or 8/79 (28M fresh origin T); 2/79 for 209M | **Yes.** "Zero trades / NON_UTILE as a filter" is not evidence about Timestral. "No demonstrated advantage" stays true only because nothing was really tested economically |
| **B-2** | BTC forecast-quality evaluation | Alignment and accuracy | **VERIFIED OK** | `runner.py:184-191`; `src/mnq_timestral/model.py:79` (`values[0,0,h-1]`); `b3_forecast_quality.json` | Input tensors end exactly at origin (SHA match 76/76). 28M step-2 MAE 633.84 vs persistence 628.60 (reproduced). Shifting the target by one step raises MAE to 784, so alignment is correct. Paired error improvement CI [−9.66, −1.19] (model worse). IC 0.004 | No. This leg is genuine: zero-shot univariate 28M/209M add no skill over persistence at 4–24h on BTC |
| **B-3** | MNQ/MES 28M lagged filter | Anchor misalignment, so the filter tests the trigger-bar sign | **DEMONSTRATED ERROR** (design) | `src/mnq_local/timestral_experiment.py:112-115` (forecast `bars[:-1]` vs price `bars[-1].close`); `src/mnq_timestral/strategy.py:65-67`; `src/mnq_paper/core.py:382,386`; `b1_mnq_28m_filter.json`, `b1_mnq_28m_filter_rows.csv` | 316/316 decisions recomputed exactly. Identical to the persistence-forecaster decision in 305/316. Trigger bar in signal direction: ORB 12/12, Sweep 23/23, VWAP 1/123. Median model move 0.3–2.9 pts vs last-bar move 3.5–7 pts. Non-stale rules would accept ORB 2–5/12 and Sweep 5–10/23 | **Yes**, for the filtered economic arms (ORB 0 trades, Sweep 0–1, VWAP "−$11.56 better"). They are uninformative about the model |
| B-4 | Timestral units, quantiles, latency, TTL, cache | Possible alternative causes | **VERIFIED OK** | `schema.py:14,154-155,167`; `strategy.py:49-58`; `timestral_experiment.py:38`; `runner.py:9,30-31`; recorded reasons | Price units on both sides (MNQ edge 0.25 pt = 1 tick; BTC hurdle is a fraction applied to price). Level index 10 = 0.50, quantiles non-crossing. Reasons recorded are only `distribution_incoherent`/`accepted` (MNQ) and `nonpositive_forecast_edge_after_cost_hurdle` (BTC; plus 4 `missing_warmup` in 2025). No not_ready, stale, TTL or late rejections. Max latency: MNQ 0.24 s (budget 60 s); BTC p99 0.019 s (28M) and 0.166 s (209M) vs 300 s. Covariates are normalized per row inside the library (`timestral/model.py:3`, `forecaster.py:351-355`) | Rules these out as causes; the cause is B-1/B-3 |
| B-5 | MNQ/MES 1-minute forecast accuracy | Accuracy claim | **VERIFIED OK** (weak evidence) | `timestral_experiment.py:125-154`; `b3_forecast_quality.json` | Reproduced, e.g. MNQ h5 target-only MAE 19.632 vs last close 19.268. Worse than random walk in 20/20 comparisons, but only about 125 origins per horizon over 5 sessions | No |
| B-6 | Timestral documentation | Stale reports | THEORETICAL CONCERN | `reports/timestral-28m-experiment/RESULTS.md:5-7`, `reports/timestral-28m-verification/verification.json` (`real_inference_performed:false`) vs `results.json` (7,400 real forecasts) | — | No; risk of misreading. The current summary is `reports/timestral-real/RESULTS.md` |
| B-7 | `PROJECT-VERDICT.md:87` | Claim wording | PROBABLE ISSUE | `reports/PROJECT-VERDICT.md:87`; `reports/binance-spot/timestral-abc/RESULTS.md:3` ("worsened the positive primary baseline") | The "+7.46 vs 0" comparison is mechanical (B-1). In the MNQ test VWAP had 27–28 trades, so "zero trades" does not generalize | Wording only. "Not demonstrated" stays; "tested and not useful as a filter" is unsupported |
| A-1 | Futures ledgers and cost model | Arithmetic, contract specs, fees, slippage | **VERIFIED OK** | `src/mnq_sim/engine.py:17-23,138-145`; `src/mnq_timestral/evaluation.py:19-21,43-45`; `src/mnq_sim/quant.py:20,49-52`; `a1_ledger_audit.json` | 6/6 ledgers equal the reported counts and nets. Per-trade checks 2,144/2,144: MNQ $2/pt, MES $5/pt, tick 0.25; fees 2×(0.25+0.35+0.02/0.01); slippage 1 tick/side; zero spread; net = gross − fees − slippage | No |
| A-2 | Entry timing | Look-ahead | **VERIFIED OK** | `engine.py:169-184,215,222-227` | 2,144/2,144: signal at bar close t, fill at the open of the bar starting at t. No same-bar fill | No |
| A-3 | Signals (VWAP-z, ORB, Sweep/MSS) | Look-ahead, VWAP anchor, z window | **VERIFIED OK** | `src/mnq_timestral/data.py:21-35`; `strategy.py:24-31`; `src/mnq_sim/strategies.py:47-90`; `a2_null_reimpl.json` | An independent causal re-implementation reproduces the ledgers exactly: MNQ/MES VWAP 627/633 and ORB 176/173 trades, identical entries and nets. VWAP is anchored at 09:30 using typical price; z = residual / 20-bar σ including the current bar. Sweep pivots are confirmed after the right-hand bars, which is causal by construction; the signal itself was not re-implemented | No |
| A-4 | Exit simulation | Stop/target/flatten logic | **VERIFIED OK** | `engine.py:49-59,189-203`; `evaluation.py:81-89` | Independent re-simulation matches exit price, reason and time on 2,144/2,144 trades | No |
| A-5 | Sessions, timezone, DST, daily reset | Calendar | **VERIFIED OK** | `engine.py:133-136,159-163`; `quant.py:91` (UTC-date grouping, equivalent for RTH) | 120 sessions × 390 bars, 09:30–15:59 ET; entries 09:45–15:30; flatten at 15:30. All dates are in EDT, so no DST transition is exercised. zoneinfo is used. Fresh account each day | No |
| A-6 | Contract roll | Data hygiene | THEORETICAL CONCERN (minor) | `reports/quant-validation/data-quality120.json` mapping `previous_day_volume_rank_0` | The expiring contract was used on 06-15, 06-16, 09-14 and 09-15 (plus 09-16 for MNQ), with RTH volume 75–90% below normal (e.g. MNQM6 on 06-16: 267,835 vs about 2M). No cross-contract positions. MNQ VWAP roll-day net −22.56; excluding those days, −3,217.44 | No |
| **A-7** | "Negative before costs" (MNQ VWAP/ORB) | Intrabar convention bias | **PROBABLE ISSUE** (interpretation; sensitivity demonstrated) | `evaluation.py:83-87`; `engine.py:55-58`; `a1`/`a2`/`a3` JSON | Placebo (opposite side) is gross-negative in 5/6 arms. Random-direction null: −1.16/trade (MNQ), −0.38 (MES) under stop-first; −0.20/−0.28 under the OHLC heuristic; +1.74/+0.01 under target-first. MNQ VWAP gross ranges from −1,844 to +1,606 depending on convention; first-passage −584 (t −1.15) | It changes "negative gross / anti-edge" into "no edge, cost-dominated". It does not change "don't trade" |
| **A-8** | Key question: gross or net? | Answer | — | Section 2 | Under the frozen engine, MNQ VWAP and ORB are significantly negative gross. MNQ Sweep is +275 (not significant). All MES arms are about zero gross, so 93–108% of each MES loss is costs. Under neutral resolution, all six are about zero gross | — |
| **A-9** | MNQ Sweep/MSS −379.42 | Statistical power | **PROBABLE ISSUE** | `a3_power.json`; `reports/research-v2/results.json` (block-5 CI [−8.74, +2.16]) | First-passage net −11.42; daily CI [−5.20, +4.87]; target-first bound +678.58 | **Yes for this arm**: it is inconclusive, not demonstrated negative. Context: the separate ATR variant lost before costs (`reports/sweep-atr-experiment/REPORT.md`) |
| A-10 | Informativeness of 120 sessions | Power | VERIFIED (with caveats) | `a3_power.json` | Rejects net profitability at modeled costs for MNQ VWAP and all three MES arms under any plausible convention; MNQ ORB borderline | No; caveat that it is one regime, already inspected, with no out-of-sample period |
| A-11 | Bracket design | Scope / degenerate parameterization | THEORETICAL CONCERN | `evaluation.py:20` (MNQ 15/8 pt, MES 4/2 pt) | The stop is 0.027% of price. MNQ SL is below the median 1-minute range (87% of bars have range ≥ SL); for MES 69% do. Net break-even win rate: MNQ 39.6%, MES 45.8%. Observed: 28–37% | This rejects these noise-scale configurations, not VWAP-MR/ORB/Sweep in general. Only Sweep was re-tested with ATR exits |
| C-1 | Capital.com, tasty and paper runs | Economic dependence | VERIFIED OK | `reports/capital-forward/RESULT.md` (1 DEMO roundtrip, −0.002 USD); `reports/capital-v63/RESULT.md` ("NOT RELIABLE FOR AUTOMATIC ENTRIES") | Technical only. No conclusion in PROJECT-VERDICT §C depends on them | No |

---

## 4. Timestral evidence detail

### MNQ/MES 28M experiment (19–23 Oct 2026; filter at horizon 5 min, median, edge 0.25 pt, forecast lag 1 bar)

In the table below, "persistence" means a forecaster that simply predicts the last known close. "Own anchor" and "fresh origin" are the two non-stale rules: "own anchor" measures the model's predicted move from its own origin price; "fresh origin" uses the forecast made at t.

| Arm | Candidates | Accepted (recorded = recomputed) | Trigger bar in signal direction | Same decision as persistence | Median model move (pt) | Median last-bar move (pt) | Accepted under "own anchor" | Accepted under "fresh origin" |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ORB, target-only | 12 | 0 | 12 | 12/12 | 1.91 | 6.88 | 2 | 5 |
| ORB, past covariates | 12 | 0 | 12 | 12/12 | 2.90 | 6.88 | 3 | 5 |
| Sweep, target-only | 23 | 0 | 23 | 23/23 | 0.34 | 7.00 | 5 | 10 |
| Sweep, past covariates | 23 | 1 | 23 | 22/23 | 0.84 | 7.00 | 6 | 9 |
| VWAP, target-only | 123 | 118 | 1 | 119/123 | 0.30 | 3.50 | 40 | 29 |
| VWAP, past covariates | 123 | 118 | 1 | 117/123 | 0.73 | 3.50 | 49 | 61 |

Mechanism: edge = side·(median₅(t−1) − close_t) = side·(median₅(t−1) − close_{t−1}) − side·(close_t − close_{t−1}).
- Breakout entries (ORB, MSS) are triggered by a move in the signal direction, so they are rejected.
- Mean-reversion entries are triggered by a move against it, so they are accepted.
- Across the six ledgers, the trigger bar moved in the signal direction 100%/99% of the time for ORB/Sweep and 3% for VWAP (`a1_ledger_audit.json`).

### BTC A/B/C (28M/209M; Jan–Sep 2026 primary; 2025 secondary)

| Model / segment | Candidates | Accepted | close_T > P[O] | Persistence would accept | Own-anchor rule | Fresh origin T, step 2 |
|---|---:|---:|---:|---:|---:|---:|
| 28M primary | 79 | 0 | 79 | 0 | 6 | 8 |
| 209M primary | 79 | 0 | 79 | 0 | 2 | 2 |
| 28M secondary | 113 (+4 warm-up) | 0 | 113 | 0 | 0 | 2 |
| 209M secondary | 113 (+4 warm-up) | 0 | 113 | 0 | 1 | 0 |

Matched A trades that the non-stale rules would pass, out of 26:
- 28M: 2, net −0.86.
- 209M: 1, net +0.14 (own anchor) or −0.99 (fresh origin).

These are descriptive only: far too few trades for any economic inference. They confirm that a corrected test would accept little, because the forecasts sit close to persistence.

---

## 5. What is proven and what is only possible

**Proven, with reproducible numbers:**
- The six ledgers are arithmetically correct, causal and exactly reproducible.
- No look-ahead, no same-bar fill, and no cost or contract-spec error.
- Both Timestral economic tests were structurally degenerate (B-1, B-3).
- The forecast-accuracy legs are correctly aligned and show no skill over persistence.

**Probable, because it depends on unobservable intrabar order:**
- The size of the stop-first bias.
- The "fair" gross. The first-passage and OHLC-path figures are estimates, not observations. One-minute OHLC data can't resolve them, and only ohlcv-1m was acquired.

**Not audited in depth:**
- The V5 replay execution path (`src/mnq_local/replay.py`), beyond the facts needed for B-3.
- An independent re-implementation of the Sweep/MSS state machine. Its exits were re-simulated and matched.

**Bottom line:**
- The project's negative economic conclusion for the six futures configurations survives, as "no edge, cost-dominated". The exception is MNQ Sweep/MSS, which is inconclusive.
- The futures losses are mostly due to tiny fixed brackets plus costs and a conservative fill convention. They don't show that the signals predict the wrong direction.
- The Timestral economic conclusion does not survive as evidence: those tests could not have accepted the candidates in question.

---

## 6. Reproduce

All scripts are read-only. Run them from this folder with the project interpreter:

```sh
cd "/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-futures"
PY="/Users/locoframe/Desktop/TRADING BOT/.venv/bin/python"
PYTHONDONTWRITEBYTECODE=1 "$PY" a1_ledger_audit.py        # reconciliation, gross/net, conventions, placebo
PYTHONDONTWRITEBYTECODE=1 "$PY" a2_null_reimpl.py         # independent signals, random-direction null, roll days
PYTHONDONTWRITEBYTECODE=1 "$PY" a3_power.py               # CIs vs cost hurdle
PYTHONDONTWRITEBYTECODE=1 "$PY" b1_mnq_28m_filter.py      # 316 MNQ/MES filter decisions decomposed
PYTHONDONTWRITEBYTECODE=1 "$PY" -I b2_btc_abc_filter.py   # BTC gate geometry (zips read in memory)
PYTHONDONTWRITEBYTECODE=1 "$PY" -I b3_forecast_quality.py # forecast alignment and accuracy
```

Outputs: `a1_ledger_audit.json`, `a2_null_reimpl.json`, `a3_power.json`, `b1_mnq_28m_filter.json`, `b1_mnq_28m_filter_rows.csv`, `b2_btc_abc_filter.json`, `b3_forecast_quality.json`. Shared helpers are in `common.py`.
