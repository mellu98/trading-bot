# Scientific falsification gate — strategy discovery 2026

**Pre-results plan, not a claim that any strategy works.** This independent scientific review has not inspected new candidate performance or 2024 financial results. The coordinator must freeze the final protocol, code, configuration, tests, seed and data identities before releasing the holdout. These gates do not certify production readiness or constitute a native code-review receipt.

## Decision before results

| Item | Required treatment |
|---|---|
| Candidate count | At most one primary and one adjacent sensitivity configuration for A, B and C: six configurations maximum. Register every attempted variant, failure and abandoned experiment. |
| Primary versus neighbor | The neighbor measures fragility. It cannot replace a failed primary, become a new winner, or authorize a rescue search. |
| Chronology | Proposed: 2019 warmup; 2020–2022 development; 2023 validation; 2024-01-01 through 2024-11-30 final holdout. Verify actual coverage and earlier project use before freezing. |
| Prior observation | BTC 2025, January–September 2026 and December 2024 warmup are not new holdouts. A project-unseen historical period is not prospective evidence or protection against public knowledge. |
| Capital | Start with 1,000 USDT simulated equity; no borrowing or short sales; portfolio gross exposure at most current equity, cash nonnegative after fees. Explicitly distinguish this from the old 100-USDT entry cap. |
| Costs | Freeze base/adverse/severe fees, full spread and slippage separately, per-side convention and cost-aware sizing. Do not optimize costs to obtain success. |
| Stop rule | One bounded run and one concrete causal implementation correction cycle. Economic failure is not permission to tune, extend the sample, or add another strategy. |

## Mandatory vetoes

1. **Information or execution leakage.** Signal inputs must be available before the simulated order. Signals from a completed daily/hourly bar cannot fill at that bar's closing boundary. Model a complete intervening execution bar and fill at the following open; record signal close, assumed availability and execution timestamps. Shift signals and allocations, not merely reported trade timestamps. Rolling volume, volatility and covariance use past bars only. A prefix-causality fixture must leave earlier allocations and returns unchanged when future prices are altered.
2. **Unproved point-in-time universe.** A needs a dated selection source, symbol/listing history, delisting policy, missing-bar policy and asset identity handling. Do not backfill later winners, drop future losers, forward-fill ghost prices, or replace assets using subsequent returns. A fixed historical cohort tests that cohort, not an investable broad-market strategy. If membership cannot be established, mark A data-limited and ineligible for promotion.
3. **Invalid market data.** Check official archive checksums, timestamp unit, UTC alignment, expected interval, uniqueness, OHLC/volume validity, coverage and gaps. Do not silently bridge gaps or fabricate tradable prices. Separate checksum integrity from correctness of economic data. Archive candles do not establish historical bid/ask, order book depth or guaranteed fills.
4. **Unfrozen test.** No holdout financial summaries, candidate scores, charts or parameter comparisons before the hash-bound release. Loading bytes solely for checksum/schema/coverage inspection is not performance inspection; candidate return calculations are. Any accidental preview or later scope/code/config change needs an explicit contamination/addendum record, not a silently renewed holdout.
5. **Unfair attribution.** All comparisons must use the same capital, periods, marking frequency, execution convention and entry/terminal liquidation costs. No ex-post leverage to match risk. Do not call an exposure effect alpha. Separate account return, deployed-capital return and additional return against relevant passive exposure.
6. **Overstated statistical evidence.** Six mission variants do not represent the complete historical project search. A Deflated Sharpe Ratio using only three or six trials cannot certify project-wide statistical significance. Use an explicitly conditional estimate with assumptions and trial-count sensitivity, or report not estimable. Never turn a bootstrap interval into a probability of future profit.

## Freeze the economic comparison

For each family, freeze one coherent underlying passive benchmark: the historically eligible equal-weight cohort for A; BTC/ETH equal-weight for B; ETH for the BTC-to-ETH long/flat hypothesis C. Also report BTC and ETH buy-and-hold where informative, and cash earning zero USDT return. Stablecoin, venue, custody and inflation risk remain outside the zero-return cash model.

Use two additional comparisons, fixed before results:

- **Risk-cap passive:** a passive underlying portfolio with the same trailing-data volatility estimator and unlevered volatility cap chosen for the strategy; a deterministic rule with no future realized-volatility scaling.
- **Exposure-matched passive diagnostic:** the passive underlying multiplied by the candidate's lagged investable gross exposure, using the same execution timing and costs. This is a counterfactual diagnostic, not an independently passive allocation and not proof of causal alpha. Its mechanics must be frozen, including turnover and funding effects.

Do not retrospectively select whichever comparator makes a candidate look best. Show raw passive, risk-cap passive and exposure-matched results together. Benchmarks that mechanically trade at candidate timing must pay the corresponding costs.

## Proposed promotion contract — coordinator acceptance required before results

**A — PROMISING CANDIDATE means eligible only for a new paper-trading experiment, never live capital.** A candidate is eligible only if every applicable veto is cleared and its primary meets all of the following:

| Gate | Proposed criterion |
|---|---|
| Economic repeatability | Positive net return in both validation and holdout under base and adverse costs. |
| Incremental benefit | Positive holdout cumulative net incremental result against both frozen risk-cap and exposure-matched comparators. |
| Risk | Holdout maximum drawdown no worse than the frozen risk-cap comparator. Report Sortino, downside tails and exposure so low risk cannot be mistaken for profitable skill. |
| Local stability | The single frozen neighboring configuration does not reverse the holdout base/adverse net-return signs; it is not a substitute primary. |
| Uncertainty | The paired block-bootstrap 95% interval for holdout mean daily net incremental return against each comparator has a positive lower endpoint. This is conditional exploratory evidence, not a global multiple-testing-adjusted discovery claim. |
| Concentration | Report top-one/top-five profitable trade or contribution shares, positive periods and regime results. Reliance on a single exceptional event must be disclosed; do not impose a post-results numerical cutoff. |
| Severe costs | Mandatory stress diagnostic. A sign flip limits execution confidence and must be explicit; whether it is an absolute veto must be decided now, not after results. |

Proposed bootstrap implementation: paired daily strategy-minus-benchmark returns, contiguous circular blocks, 10,000 resamples, seed 20261028, primary block length seven days; repeat at 30 days only as a declared dependence sensitivity. Report interval construction, observation count, truncation, missing days and degeneracy. These values are proposals until the coordinator's final frozen protocol accepts or replaces them. Do not choose block length after observing intervals. Very few effective blocks sharply limit interpretation.

**B — FUTURE DATA NEEDED:** plausible incremental economic point estimates, but uncertainty, limited independent regimes, data limitations or contaminated historical testing prevent the stated promotion gates. Do not extend the historical search until a pass appears. State exactly what future paper evidence would address the gap, without deploying it now.

**C — NO STRATEGY PROMOTED:** primaries lack convincing incremental benefit or are economically fragile under realistic cost/risk assumptions. The best of three can still be rejected. Failure to meet a p-value alone does not prove a negative true expected return; distinguish weak evidence from demonstrated cost failure.

If no candidate qualifies for A, the coordinator chooses B versus C by the reason for failure, not by a forced ranking. Preserve a family-by-family rejection table.

## Metrics and interpretation checklist

- [ ] Returns and drawdown are equity-based after fees, spread and slippage; disclose unrealized marking and terminal liquidation.
- [ ] Daily Sharpe/Sortino use 365-day crypto annualization and identical UTC observations; hourly C is aggregated to daily for comparable portfolio risk reporting. Zero volatility/downside denominators are N/A, never infinity-as-success.
- [ ] Roundtrip profit factor is labeled as such; daily positive/negative-return ratio is not mislabeled trade profit factor. Cross-sectional rebalances need an explicit lot or portfolio-trade definition; otherwise PF is N/A.
- [ ] Report turnover, cost drag, average/maximum gross exposure, invested time, trade count and executable order-size assumptions. Hourly lead-lag predictability without post-delay net profit is not an economic strategy.
- [ ] Show development, validation and holdout separately, plus yearly/regime outcomes defined without future knowledge. The short holdout has incomplete regime coverage.
- [ ] Concentration removal is labeled fixed-ledger attribution, not a re-executed counterfactual; trend strategies may legitimately earn from tails, but one tail is weak replication.
- [ ] Neighbor robustness, costs and uncertainty use the frozen variants; no parameter grids, large ML search, forecast leaderboard or unregistered rescue rules.
- [ ] Reject gross-return-only claims, long-short-paper-to-long-only extrapolation, unmeasured historical execution claims and global DSR claims with unknown prior trials.

## Evidence and next action

Inputs read before this plan: `/Users/locoframe/.codex/attachments/65c873ed-15fc-49d3-bb53-89d87e3061fe/Testo incollato.txt` and `/Users/locoframe/Desktop/TRADING BOT/reports/PROJECT-VERDICT.md`. The latter documents old observed periods, costs, capital conventions, concentration and same-boundary execution limitations; it is not new-candidate evidence.

Next: coordinator accepts a concrete protocol; Agent B provides frozen configuration, simulator, timing/data fixtures and manifest; this reviewer performs one blind pre-holdout scientific contract inspection without financial results. After explicit release, apply the same accepted gates to the actual results. No production files, old strategy, accounts, journal, Databento, Docker or services are modified by this plan.

## Accepted pre-results addendum 1 — coordinator methodology

**Recorded before new financial results on 2026-10-28.** The original proposal above is retained for provenance. This addendum supersedes only the stated proposal choices below; the coordinator's final frozen protocol is authoritative for implementation. No candidate return, chart or holdout score was inspected for this assessment.

### Accepted decisions

| Topic | Accepted coordinator decision |
|---|---|
| Periods | Warmup September–December 2019; development 2020–2022; validation 2023; holdout January–November 2024, excluding previously seen December 2024. Express endpoints as right-open UTC intervals. |
| Variants | Maximum six: A 14-day momentum primary / 7-day neighbor, weekly top-two positive momentum; B 90-day momentum primary / 60-day neighbor; C one-complete-hour execution delay primary / two-hour delay neighbor. Neighbors never rescue primaries. |
| Costs in basis points | Base fee 10 / slippage 1 / full spread 2; adverse 15 / 5 / 10; severe 20 / 10 / 20. Fee and slippage are per side; charge half of full spread per side. No cost scenario is selected after results. |
| Execution | Daily/weekly decisions wait one complete daily execution bar; C waits at least one complete hourly execution bar. Signal availability and fill chronology must be explicit in code and fixtures. |
| A allocation | Fixed 2019-12-29 top-eight nonstable cohort, Binance historically eligible, no BSV replacement; expected seven subject to source verification. Thirty-day history and trailing 30-day median quote volume at least 10 million USDT. Rank into top two with positive momentum, then portfolio forecast volatility from past 30 daily returns at current target weights, sample standard deviation, annualized by square root of 365; scale down only toward 20% annual volatility. |
| B allocation | BTC and ETH sleeves each at most 0.5 equity when its momentum is positive, multiplied by min(1, 0.20 / trailing-30-day annualized asset volatility); no leverage. Passive comparator applies the same per-sleeve volatility cap without the momentum switch. |
| C signal | BTC hourly return z-score above one, mean and standard deviation from 168 prior hourly returns excluding current signal return; long ETH for one hour after delayed entry; one position, no short or leverage. Pending-order/exit mechanics must be explicit. |
| Capital and passives | Initial equity 1,000 USDT, cash return zero; BTC/ETH buy-and-hold plus coherent family passive, with comparable starting/terminal costs. A relevant passive is historically eligible equal-weight with the same causal volatility cap. |
| Metric clocks | Primary metrics use daily portfolio returns and square root of 365 annualization. C hourly metrics may be secondary with square root of 8,760; disclose hourly drawdown separately. |
| Mandatory economic gates | Primary validation and holdout net returns strictly positive under base and adverse; severe validation and holdout net returns nonnegative. Neighbor holdout base/adverse signs positive. |
| A incremental/risk gates | Positive incremental net return versus contemporaneously exposure-matched historically eligible equal weight; Sharpe at least the risk-cap equal-weight comparator and drawdown no worse. |
| B/C incremental/risk gates | Higher net daily Sharpe and drawdown no worse than their frozen ex-ante risk-cap passive comparator. Exposure-matched passive is diagnostic only, not a veto. |
| Statistical gate | Paired daily circular block bootstrap, 10,000 replications, seed 20261028; primary blocks seven days and dependence sensitivity 30 days. Require lower percentile at 0.05/3 to be strictly positive for both block lengths. A statistic is mean daily net excess versus exposure-matched equal weight; B/C statistic is net daily Sharpe difference versus risk-cap passive. |
| Multiplicity limits | Bonferroni applies only to three frozen mission primary-family tests. Both block-length checks and neighbor checks are conjunctions, not searches for a passing alternative. Unknown previous project trials still prevent a global discovery-significance claim; project-wide DSR is not estimable. |

### Why the exposure-gate correction is necessary

The original generic requirement for positive incremental return against exposure-matched passive is withdrawn **for B and C only**. B's economic mechanism includes deciding when to hold cash; a benchmark given exactly that exposure path inherits the timing signal. For C, ETH at exactly the same exposure, timing and costs can be identical to the strategy, making strictly positive excess impossible by construction. Such a comparator is useful attribution, not an independent economic hurdle. A is different: its relative-ranking mechanism can be compared against equal-weight assets at the same total exposure while retaining an independent allocation comparison. This is a pre-results logical correction, not a result-driven relaxation.

### Mechanics to resolve in the final freeze

1. Use exact holdout boundaries `[2024-01-01T00:00:00Z, 2024-12-01T00:00:00Z)` and do not consume December returns. A terminal mark or liquidation must not use an excluded future price.
2. Name the cost scenario for inferential/Sharpe/drawdown comparisons before results. This reviewer recommends base for those gates, alongside the separately mandatory base/adverse/severe economic gates; the coordinator must make the final choice.
3. State C's risk-cap ETH comparator window/cap and causal rebalancing schedule, and specify whether a pending/held trade ignores new signals, cancels, exits or re-enters. No overlapping exposure or retroactively accepted signal.
4. Make eligibility, delisting and missing-held-asset behavior deterministic. Invalid or unavailable execution prices cannot silently erase orders or losses; unresolved material handling blocks promotion.
5. Apply identical sampled day indices to each strategy/benchmark pair. Undefined Sharpe, too few valid observations or degenerate comparisons cannot pass by returning infinity or silently dropping samples. Report conditional uncertainty honestly.

The fixed historical cohort and published long-short/perpetual/minute-scale evidence do not automatically validate long-only spot results. This remains a bounded experiment, not a claim of general cryptocurrency momentum profitability.

## Accepted pre-results addendum 2 — final mechanics and partial blind inspection

The coordinator resolved the five mechanics before financial results:

- Holdout is right-open `[2024-01-01, 2024-12-01)` UTC. Inferential, Sharpe and drawdown gates use **base costs only**; the separately mandatory base/adverse positive and severe nonnegative validation/holdout gates remain conjunctions.
- C invests 100% of available cash in ETH, with no strategy volatility scaling. Its comparator is ETH with trailing 30 **completed daily** returns, sample standard deviation and square-root-of-365 annualization, target 20% volatility capped at one, daily UTC rebalancing with the same full-day lag. At each due entry, process due exit first; buy only if flat; occupied entries are skipped and logged. Ignore no signal merely because it occurs while holding; record its scheduled execution outcome. Do not schedule an entry whose planned exit exceeds the period.
- Missing entry price or not-yet-listed asset means skip and log. Missing held-asset exit/mark price or uncertain identity/delisting means affected candidate-period **INCOMPLETE / NOT PROMOTED**; do not forward-fill, liquidate at a future last bar or erase losses. Other valid candidates may continue.
- Use identical resampled day indexes for each bootstrap pair. Undefined variance/Sharpe or insufficient valid observations means not promoted.
- Also report A's uncapped weekly eligible equal weight and start-only equal-weight buy-and-hold with historically eligible sleeves and unavailable sleeves remaining cash. Physical availability is checked at entry without recalculating indicators using later information.

### Partial blind code gate — not holdout release

Read only `/Users/locoframe/Desktop/TRADING BOT/research/strategy-discovery-2026/data.py`, `engine.py`, `test_engine.py`, `tdd-red.txt` and `tests-green.txt` at the partial handoff. No archived prices, economic result, chart or return table was inspected. The runner/protocol/final freeze were not yet available; this is not a completed scientific gate.

| Observation | Assessment |
|---|---|
| `engine.py` daily features 41–50; impulse/schedule 77–88 | Daily execution uses latest close at index `i-2`; C excludes current return from its 168-bar estimation window and schedules `j+1+delay`. These primitives match the intended complete-bar delay under the stated indexing. Runner chronology still requires verification. |
| `engine.py` accounting 10–39 | Explicit half-spread, slippage and fee conventions; sell-before-buy; cost-aware cash scaling; held missing-price rejection. No concrete conservation or future-input defect found in these primitives. |
| `engine.py` bootstrap 100–114 | Candidate and benchmark share sampled indexes; seed and 7/30-day lengths agree with freeze; any nonfinite sampled statistic invalidates the interval rather than producing an artificial pass. |
| `data.py` load 81–96 | A missing archive or any asset gap aborts the entire shared load. Final runner must isolate/classify affected candidate-period quality errors so a failed A asset does not incorrectly prevent valid B/C assessment. If all planned archives are complete, this branch is not triggered; do not claim it has been observed on real data. |
| `data.py` monthly coverage | Count, continuity and unit checks exist. Final quality gate must verify exact per-month first/last timestamps and overall period coverage, plus point-in-time cohort/source evidence. Source checksum integrity alone is not that proof. |
| TDD evidence | RED is module-import failure before `engine.py` existed; GREEN records 17 passing tests. This supports test-first scaffolding, not a claim that every scientific contract has a demonstrated behavioral failing-test/correction sequence. |

Still pending in the final handoff: full initial/terminal costs and period boundaries; portfolio reset conventions; C exits/reentries/skips; A exposure-matched benchmark implementation; coherent passive timing; undefined-gate handling; final metrics/concentration/regime output; and source/config/test/data hash verification. No source was edited by this reviewer. No native code-review receipt is asserted.

## Final blind scientific code gate — GO, before financial release

**2026-10-28: GO for the frozen research implementation, conditional on the separately required blind data-quality/point-in-time freeze before financial release.** This is neither an economic endorsement nor authority to release the holdout without the coordinator. No market prices, financial results or candidate return table were inspected by this reviewer.

Read the final protocol, config, universe, engine, data loader, runner, assessment gates, synthetic tests and source manifest. Independently ran `.venv/bin/python -m pytest -q research/strategy-discovery-2026/test_engine.py -p no:cacheprovider`: **23 passed in 0.07s**. Checked every one of the eight frozen source hashes and the declared test-log hash: all match.

| Frozen artifact | SHA-256 |
|---|---|
| `source-freeze.json` | `17d58cc404464ff6e812755cf514f98e14eaa7e29ae608310d03f073b1e0b410` |
| `protocol.json` | `72c4a902c03edd558b98de880fd41f815a3ccc1187674e34f3a4bcb917ea54e8` |
| `config.json` | `a52e0d3aa1679939d2ff78a33b7b7e9496c8d19696b3c2e5a871741c497ccaab` |
| `runner.py` | `3b48ab4eba6165daf541a2213c311a9a84e36af664b745c971642279fc148524` |
| `test_engine.py` | `32cca8b7479ff30a9cb547a26ce54c92f632893e0fe0620f4a9541ef9e672258` |

The prior source freeze `55d8a4c571617d84dc4ee463fce145c6f9522c4512f0c70e7e61b9c9d1b85a01` is preserved separately as `source-freeze-v1.json`. Before any authorized GET or economic result, one bounded diagnostic guard corrected the runner's assumption that BTC buy-and-hold must be complete whenever a different candidate/comparator is complete. `add_market_diagnostic` now reports unavailable beta rather than crashing; its synthetic regression passes. This changes neither strategy allocations nor promotion rules. The original preimplementation RED log remains described as missing-module collection, not a fabricated behavioral repair history.

### Confirmed contract

- A/B use frozen Monday rebalancing with the full completed-day information lag; A portfolio covariance cap and B per-sleeve volatility caps match protocol. C uses its full-hour delay, cash-limited ETH entry, due-exit-before-reentry, one-hour holding and paid close/reopen.
- Base/adverse primary validation and holdout signs, mandatory nonnegative severe results, positive base/adverse holdout neighbor signs, base-only relative Sharpe/drawdown gates, and both family-adjusted bootstrap bounds are conjunctive in `assess.py`; no neighbor rescue or winner substitution.
- A's comparator matches **ex-ante requested target exposure**, not exact realized exposure after differing cost drag. B/C do not face the logically impossible same-signal exposure veto. Volatility estimators use daily log returns as explicitly frozen.
- Equity is **liquidation-value NAV**: hypothetical exit frictions reserve unrealized liquidation value without repeatedly charging cash; the actual finite terminal trade realizes costs once. Drawdown must be labeled accordingly. Terminal close is a finite research valuation/fill assumption, not certified executable production liquidation.
- The loader checks exact monthly first/last/count, continuity and integrity and records errors per required asset series; affected families are incomplete while unaffected valid families can continue. Held unavailable prices fail closed rather than being filled forward.
- The two strategy/comparator series share bootstrap day indexes. Undefined statistics cannot pass. Conditional current-three-family inference is not project-wide significance and global DSR remains not estimable.
- At inspection, `financial-release.json`, `holdout-release.json` and `financial-holdout-release.json` were all absent. Source/data hash binding, no-overwrite result paths and separate holdout acquisition/financial release gates are implemented. No source was edited by this reviewer.

**Remaining planned gate, not a new research round:** blind downloaded-archive coverage/integrity, official pre-anchor EOS existence, historical cohort eligibility, frozen data identities and coordinator authorization. Only then may economic evaluation run. Native `gentle-ai` receipt is unavailable and is not claimed.

## Authorized development/validation interpretation — holdout not inspected

The coordinator subsequently authorized the single frozen development/validation run. Read `/Users/locoframe/Desktop/TRADING BOT/research/strategy-discovery-2026/results-development-validation/results.json`, SHA-256 `eb58d14e51c30138763ff59fed1e4d3d6d715d6623c012d819337fc33c01453a`. No rules, source, parameters or promotion thresholds changed. The following is interpretation, not a new test or promotion decision.

| Validation 2023, base costs | A primary | A target-matched EW | A risk-cap EW | B primary | B risk-cap passive |
|---|---:|---:|---:|---:|---:|
| Net return | 18.51% | 9.75% | 25.74% | 3.22% | 45.11% |
| Daily Sharpe | 0.973 | 0.627 | 1.146 | 0.267 | 1.810 |
| Liquidation-value daily maximum drawdown | 17.30% | 16.10% | 17.17% | 18.42% | 16.05% |
| Average account gross exposure | 33.24% | 33.17% | 47.59% | 32.73% | 50.19% |

- **A:** Validation remains positive at adverse 15.41% and severe 11.93%; its ranking contrast is positive in 2023 but negative over development: primary 87.96% versus target-matched EW 103.84%. A convincing stable selection benefit is therefore not already established. Validation top-five daily contributions equal 133.18% of total net profit; the best single day is 34.22%, not more than the entire profit. These are portfolio-day attributions, not roundtrip concentration and not executable removed-day reruns.
- **B:** Validation remains positive at adverse 2.19% and severe 1.02%, but is materially weaker than its coherent risk-cap passive in return, Sharpe and drawdown. The best day contributes 127.15% of the 32.22-USDT net profit; fixed-path subtraction leaves -8.75 USDT. Development did show lower drawdown than its risk-cap passive (20.05% versus 34.53%) and slightly higher Sharpe (1.079 versus 0.967), so the validation result is a lack of stable replication, not proof that the strategy always loses.
- **Do not change gates:** Both A/B satisfy the frozen validation cost-sign conjunction. Relative Sharpe/drawdown and adjusted inferential vetoes were frozen for holdout only. The diagnostic validation weakness cannot be retroactively made an extra veto, and positive validation cannot waive holdout gates.
- **C is uncomputed, not a losing strategy:** Both development and validation are `INCOMPLETE_NO_PROMOTION` due required hourly-source defects. The frozen loader's all-history continuity rule also prevents an eventual later C run when earlier required history is invalid. If 2024 files are clean, call C **UNCOMPUTED / blocked required source history and validation**, not negative edge and not evidence of a 2024 gap. A clean holdout alone cannot repair the already-required invalid validation conjunction. No silent data repair, gap filling or new segment-only simulator is introduced.

The capital remains 1,000 USDT per independently reset segment, not a continuous 2020–2024 realized account. A/B average exposure well below full investment and lower passive exposure-adjusted comparisons must stay visible. No holdout outcome or final mission verdict is inferred here.

## Final independent interpretation — B: future evidence needed; none promoted

**After the coordinator's explicit holdout financial release, the defensible mission recommendation is B — FUTURE DATA NEEDED. No strategy is promoted or activated.** B, the time-series family, has an encouraging holdout risk-adjusted point estimate but fails the frozen uncertainty criteria and has weak validation replication. Calling it the most informative unchanged hypothesis for future evidence is not selecting a statistically validated winner. There is no instruction to collect future data, run paper trading, repair C or develop the bot now.

Read and verified:

- `/Users/locoframe/Desktop/TRADING BOT/research/strategy-discovery-2026/results-holdout/results.json`: SHA-256 `f6103de9f45b26f800979e831b94ad494c37bc15b92c1586739ba0f89ba97526`.
- `/Users/locoframe/Desktop/TRADING BOT/research/strategy-discovery-2026/assessment.json`: SHA-256 `bceb400d4a0b438559ddda75bd3dfef7c8881aff939e4fa7f26aa3e4b34ce2d5`.

### Same frozen gates, no post-results exceptions

| Holdout January–November 2024 | A primary | A target-matched EW | A risk-cap EW | B primary | B risk-cap passive |
|---|---:|---:|---:|---:|---:|
| Base net return | 20.12% | 33.39% | 54.04% | 42.54% | 44.55% |
| Net profit from 1,000 USDT | 201.18 | 333.91 | 540.37 | 425.40 | 445.54 |
| Daily Sharpe | 1.222 | 1.829 | 2.039 | 2.337 | 1.908 |
| Liquidation-value daily drawdown | 13.06% | 14.12% | 14.88% | 8.71% | 13.66% |
| Average account gross exposure | 26.06% | 26.10% | 41.21% | 25.79% | 39.02% |

**A is not promoted.** It survives the frozen cost-sign gates (holdout base/adverse/severe 20.12% / 17.57% / 14.70%) and neighbor signs, but fails positive mean ranking excess, the relative risk-adjusted comparison and both adjusted uncertainty bounds. The mean-excess bootstrap 95% intervals include zero; family-adjusted lower bounds are negative at both seven and 30 days. Lower drawdown than risk-cap EW does not waive the failed ranking and Sharpe requirements. The 2023 positive ranking contrast did not replicate in the holdout.

**B is not promoted.** Holdout base/adverse/severe net returns are 42.54% / 41.67% / 40.66%, with positive neighbor signs. Point-estimate Sharpe and drawdown gates pass, but the paired Sharpe-difference 95% intervals are **[-0.731, 1.661]** at seven-day blocks and **[-0.473, 1.428]** at 30 days. Family-adjusted lower bounds are **-0.828 / -0.533**, so both frozen inferential gates fail. Positive historical PnL and a higher estimated Sharpe are not sufficient evidence of a reliably additional risk-adjusted advantage. This does not demonstrate negative true expectancy either.

**C remains uncomputed, not economically falsified.** The assessment's false gates arise from incomplete required history/validation, not measured losing trades or negative return estimates. The coordinator's separate timestamp-only inspection reports clean 2024 hourly files, 8,040 bars per asset; the frozen all-history continuity block must not be misdescribed as a 2024 gap. No segment-only rescue or data repair was introduced after results.

### Attribution and practical limits

- B's account is initially 1,000 USDT, can invest at most its current equity, and averages 25.79% gross exposure with a 61.52% observed maximum. These are fractions of changing account NAV, not fixed 257.90/615.20-USDT order caps. The passive risk-cap comparator averages 39.02% exposure. Full BTC buy-and-hold earns 127.46% but with 26.15% drawdown and 100% exposure; comparing returns alone is unfair.
- About 97.04% of B's net holdout PnL occurs on days assigned to the causal BTC-positive 90-day regime. Its descriptive BTC beta is 0.257, not a causal alpha estimate. The target-exposure diagnostic earns 42.44%, very close to B's 42.54%; it inherits timing, so it neither proves alpha nor constitutes an extra frozen veto.
- B's best day accounts for 15.67% of holdout net profit and its top five days approximately 54.95%; it is not the prior strategy's one-trade-more-than-all-profit pathology in this holdout. However, validation B's best day exceeds its total net profit, and its 2023 relative results were materially weak. A's best day is 22.78% and top five approximately 85.26% of holdout net profit. These are daily attribution diagnostics, not roundtrip-trade results or executable day-removal tests.
- The primary/neighbor contrast is material: B's neighbor earns 29.75% with Sharpe 1.673 and drawdown 16.54%, versus primary 42.54%, 2.337 and 8.71%. Both signs pass the prespecified local gate, but strong parameter invariance is not established. Do not change that gate after observing the magnitude.
- Eleven historical holdout months, dependence-sensitive resampling, incomplete earlier regime replication, public historical knowledge and unknown previous project trial count limit certainty. There is no valid project-wide Deflated Sharpe Ratio or estimated probability of future profitability here. Costs remain modeled, not account-certified, and delayed candle-open fills and continuous fractional quantities are not actual execution evidence.

**Decision rationale:** A lacks demonstrated additional selection benefit; B's extra risk-adjusted benefit is unresolved rather than established or disproved; C is data-limited and unmeasured. Therefore B — future evidence needed is more faithful than either promoting a winner or claiming all three economic hypotheses have been refuted. Preserve the frozen artifacts, stop this bounded research run, keep the old operational configuration archived, and authorize no deployment or new development automatically.
