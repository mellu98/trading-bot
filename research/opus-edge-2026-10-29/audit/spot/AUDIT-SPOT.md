# AUDIT-SPOT: independent audit of the Binance-spot backtests

Date: 2026-10-29. Auditor: independent quant review (read-only). Workspace: `/Users/locoframe/Desktop/TRADING BOT`.
All scripts and outputs are in `/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-spot/`.

## 0. Bottom line

1. **The accounting and the reported numbers are right.** I reran the original code read-only, with journals redirected to scratch:
   - All 12 breakout `metrics.json`, all 3 SMA168 split metrics, all 153 Strategy-Discovery A/B result JSONs, all 135 Edge-Round-2 result JSONs and every paired-bootstrap block reproduce **byte-for-byte**.
   - 243 headline numbers in the four reports match the ledgers at the precision shown.
   - Timestamp units are handled correctly everywhere in scope.
   - Perturbation and truncation probes found **no look-ahead**.
2. **One coding defect does change a reported conclusion: family C.** The frozen hourly loader cascades: one rejected month blocks every later month (data.py:100-102). So family C's clean 2024 holdout (8040/8040 hours for both assets) was never computed. The reports call C "not measured, not refuted, an open question". I ran the unmodified frozen C `simulate()` on gap-tolerant data. This is exploratory, on data already seen. Results:
   - 2024 holdout, base costs: **−80.8 %** (847 round trips, round-trip PF 0.46).
   - 2024 holdout: −97.9 % adverse, −99.8 % severe; neighbor −85.9 %.
   - 2023: −77.7 %.
   - Mean next-hour ETH gross return after BTC z>1 is −0.3 to +5.1 bp, against a round-trip cost of about 24 bp.

   **C is decisively uneconomic, not an open question.** The "no promotion" verdict stands.
3. **The same-boundary fill (4h close = next 1h open) does not drive the breakout result.** In 98.5 % of hours the next open equals the prior close within 0.01 bp. Filling one hour later: test base +7.46 → **+6.94 USDT**. Filling two hours later: +8.25. The gate outcome is unchanged: INCONCLUSIVE.
4. **SMA168 was effectively switched off early in every split.** The drawdown budget left (20 − DD, 4.97–5.14 USDT) fell below the 5.14–5.20 USDT modeled risk per trade. After that point every entry was rejected and equity stayed frozen. Trading only happened in these windows:
   - Development: 1 Jan – 10 Feb 2025.
   - Validation: 1 – 29 Jul.
   - Test: 1 Oct – 26 Nov.

   The report's "No latched risk halts occurred" is technically true but misleading. REJECT still stands.
5. **Family B is weaker than the narrative suggests.**
   - Pooled over every frozen B ledger 2020-01 → 2024-11 (1796 days): Sharpe of B is **1.14** against **1.31** for its vol-capped passive comparator (−0.17; 95 % CI about [−0.78, +0.45]).
   - In 2023 B is significantly worse than that comparator.
   - B failed only the bootstrap gates. Those gates have about **8–14 % power** at the observed 2024 effect, and the proposed 12-month prospective test would have similar power.
   - Not promoting B is right. Singling it out as the most informative candidate is weakly supported.

## 1. Scope and method

- **Backtests covered:**
  - BTC 4h Donchian 20/10 breakout, plus the economic re-audit in `reports/project-verdict`.
  - The earlier SMA168 test (`reports/binance-spot/research`).
  - Strategy Discovery 2026 families A, B and C.
  - Edge Discovery Round 2, H1 and H2.
  - `research/btceth-b-followup`.
- **Isolation:** original modules were imported read-only with bytecode writing disabled. I never called `runner.load()` (it writes `data-quality.json`), any `run()`, `freeze()` or `acquire()`. `engine()` and `AtomicJournal` received scratch paths.
- **No writes to the project:** a tree snapshot (path, size, mtime for 9128 files) before and after shows 0 changed and 0 removed files. All 179 protected files still match `pause-ab/reboot-20261028/protected-after.json` by SHA-256.
- **Concurrent additions not from this audit:** the 915 files added during the session are all under `research/opus-edge-2026-10-29/`. Another process was writing there; none of them came from this audit.
- **No network, services or downloads.**

## 2. Timestamp units (checklist item 2, the critical one)

| Archive (cached) | open_time | digits | unit | close − open |
|---|---|---:|---|---:|
| `data/binance-spot/research/BTCUSDT-1h-2024-12.zip` | 1733011200000 | 13 | ms | 3 599 999 |
| `data/binance-spot/research/BTCUSDT-1h-2025-01.zip` | 1735689600000000 | 16 | µs | 3 599 999 999 |
| `data/binance-spot/research/BTCUSDT-1h-2025-12.zip` | 1764547200000000 | 16 | µs | 3 599 999 999 |
| `data/binance-spot/breakout-4h/BTCUSDT-1h-2026-01.zip`, `-2026-09.zip` | 1767225600000000 … | 16 | µs | 3 599 999 999 |
| `research/strategy-discovery-2026/data/1h/*/…-2024-11.zip`, `…/1d/…-2024-11.zip` | 1730419200000 | 13 | ms | — |

How each loader handles the switch:

- **Breakout and SMA (and Timestral, which reuses them):** `reports/binance-spot/research/runner.py:34-46` multiplies by 1000 for ≥2025 and by 1e6 before. It asserts that the converted year equals the archive year and that close = start + 1h − 1 unit. A wrong unit would therefore raise, not slip through silently.
- **Project-verdict re-audit:** `economic-analysis.py:49-53` uses the same logic.
- **Strategy Discovery and Edge Round 2:** `strategy-discovery-2026/data.py:12-14` and `edge-discovery-round-2/data.py:15-17` handle the switch correctly. They never actually load 2025+ data, because their cache ends 2024-11.
- **B follow-up:** `btceth-b-followup/analyze.py` asserts every timestamp is before 2024-12-01.

**VERIFIED OK.**

Out-of-scope note: `research/opus-edge-2026-10-29/src/common.py:14-21` `to_ms()` raises on every µs close_time, because …999999 % 1000 ≠ 0. Its loader would therefore reject any 2025+ spot archive. It fails closed, not silently. That folder was being written by another process during this audit.

## 3. Findings

Severity: DEMONSTRATED ERROR (reproducible evidence) / PROBABLE ISSUE / THEORETICAL CONCERN / VERIFIED OK. Category numbers follow the brief's checklist (1–10).

| id | backtest | cat | severity | evidence (file:line) | measured impact | changes report conclusion? |
|---|---|---|---|---|---|---|
| F1 | SD-2026 family C | 10, 2 | **DEMONSTRATED ERROR** (code does not match the protocol's "family-period" rule; the authors disclose it as a limitation) | `research/strategy-discovery-2026/data.py:93,97` reject a month. `:100-102`: the next month is compared with `series[-1]`, which never advances past a rejected month, so every later month fails. `runner.py:92-94,129-130`: any 1h error blocks C in every segment. `protocol.json:41` says a continuity gap invalidates the affected **family-period**. `quality-holdout.json`: 58 of 60 1h months per asset rejected (every month after 2020-01), including all 11 clean 2024 months. My loader finds 8040/8040 regular hours for BTC and ETH in 2024. | C holdout 2024 was never computed. | **Yes, for C's status.** "C NON CALCOLATO … non economicamente confutata … domanda non risolta" (`STRATEGY-RESEARCH-2026.md:5,56,166,189`) should read "uneconomic under its frozen spec" (see F2). Non-promotion is unchanged: 2023 validation has a real gap and the economics are negative. |
| F2 | SD-2026 family C (exploratory) | 3, 4, 9 | **VERIFIED** (exploratory result, frozen engine) | `06_family_c_frozen_engine.py` runs the unmodified `runner.simulate` on gap-tolerant bars. `05_family_c_exploratory.py` is an independent per-signal calculation (agrees to 6 decimals). | 2024 base −80.81 % (847 round trips, round-trip PF 0.46, fees 790 USDT on 1000). Adverse −97.88 %, severe −99.83 %, neighbor base −85.87 %. 2023 base −77.72 %. 2020–22: INCOMPLETE (a position is held over a missing hour). | Yes, as above. |
| F3 | Breakout 4h | 3 | THEORETICAL CONCERN (measured, small) | `reports/binance-spot/breakout-4h/runner.py:126-131`: signal at 4h close. `:112,117`: fill at the open of the next native hour, which is the same instant. `PROJECT-VERDICT.md:100` already flags this. | Next open equals prior close within 0.01 bp in 98.5 % of hours (max 1.6 bp), i.e. a zero-latency fill at the signal close. Filled 1h later: test base 7.46 → **6.94**, adverse 4.06 → 3.38, severe −1.40 → −0.003; 2025 base −4.15 → −5.84. Filled 2h later: test base 8.25, 2025 base −3.17. The delayed variants still have 1 positive test quarter and bootstrap lower bound below 0. | No. INCONCLUSIVE either way. |
| F4 | SMA168 | 3 | THEORETICAL CONCERN (measured) | `reports/binance-spot/research/runner.py:125,138` (same-boundary fill) | Filled 1h later: test −14.96 → **−16.87**; development 0.44 → −1.37; validation −6.45 → +1.72 (41 vs 28 trades, a path change caused by risk admission). | No. REJECT stands. |
| F5 | SMA168 | 7 | **PROBABLE ISSUE** (mechanism demonstrated; reporting misleading) | `src/mnq_local/binance_spot.py:175` rejects an entry when initial risk > max_drawdown − current DD. Per-trade modeled risk is 5.14–5.20 USDT. `runner.py:90` counts a rejection but sets no halt. `RESEARCH-REPORT.md:17` says "No latched risk halts occurred". | All 74/25/22 admission rejections happen with DD budget 4.97–5.14 USDT, after the last trade of the split. With equity frozen, DD can never shrink, so the latch is permanent. Trading windows: dev 1 Jan–10 Feb 2025; val 1–29 Jul; test 1 Oct–26 Nov. The `risk_halts` gate cannot see this kind of latch. | No for the verdict: losses were realized before the latch (test gross raw −10.44). It does change how to read the sample: about 8 of 13 test weeks, about 6 of 26 development weeks. |
| F6 | Breakout 4h | 6 | THEORETICAL CONCERN (disclosed) | `protocol.json:7,19,74`; `economic.json` `time_weighted_entry_cash_upper_bound` | B&H deploys 100 USDT 100 % of hours. The strategy deploys ≤12.6 USDT time-weighted (30.9 % of hours). Scaled to that exposure, B&H would be about −0.60 USDT instead of −4.78. | No. B&H is not a gate. Do not quote "+7.46 vs −4.78" as outperformance. |
| F7 | SD-2026 B | 9 | **PROBABLE ISSUE** (selective emphasis) | Frozen B ledgers in `results-*/…-B-base-primary_{strategy,riskcap}.json`; `out/b-pooled-power.json` | Sharpe difference B minus passive, by segment: +0.11 (2020–22), **−1.54 (2023; frozen CI [−3.04, −0.24], significant)**, +0.43 (2024). Pooled over 1796 days: 1.14 vs 1.31, diff −0.17, paired bootstrap 95 % CI [−0.78, +0.45] (7-day blocks). Mean excess −2.6 bp/day. | Non-promotion unchanged. It undercuts "B presenta punti stimati interessanti … ipotesi che offrirebbe più informazione" (`STRATEGY-RESEARCH-2026.md:5,189`): across all observed history B shows no risk-adjusted value over its own passive comparator. |
| F8 | SD-2026 B gate and prospective plan | 8 | **PROBABLE ISSUE** (power) | `engine.py:100-114`; `assess.py:24`; `STRATEGY-RESEARCH-2026.md:191`; `BTCETH-B-VALIDATION.md:148` | Holdout bootstrap SE of the Sharpe difference is 0.61 (7d) / 0.49 (30d). Passing at α=.05/3 one-sided needs a point estimate ≥1.30 / ≥1.03. Power if the true difference is 0.43: **8 % / 11 %**; if 0.5: 10 % / 14 %; if 1.0: 31 % / 47 %. | Failing the gate is weak evidence either way. A 12-month forward test under the same rule will most likely end "inconclusive" whatever the truth. The reports say only qualitatively "Dodici mesi non garantiscono potenza sufficiente". |
| F9 | SD-2026 B and A | 6 | THEORETICAL CONCERN | `assess.py:18` (strategy DD ≤ comparator DD) | B's average exposure is 25.8 % against 39.0 % for the comparator. A drawdown gate mechanically favors lower exposure. The Sharpe gate is scale-invariant and unaffected. | No. |
| F10 | All loaders | 2 | VERIFIED OK | §2 | — | — |
| F11 | Breakout 1h→4h aggregation | 2 | VERIFIED OK | `breakout-4h/runner.py:21-31` (contiguity, UTC 4h anchor, 4 bars required); `:109,126-127` (a 4h bar enters history only after its last hour closes); `load()` rejects incomplete months. 16 056 h → 4014 complete 4h bars. | Truncation probe (`08_probes.py`): signals and closed trades before cuts at 2026-03-01, 06-01 and 08-20 match the full run exactly. | — |
| F12 | Look-ahead in A, B, H1, H2, breakout, C | 1 | VERIFIED OK | `engine.py:43` (j=i−2, a full day of lag); `edge…/runner.py:41,53` (lag asserted); `engine.py:77-87` (C: 168h window excludes the current hour, entry j+1+delay) | Garbage written to every future row: 0 differences in 1072 A/B and 538 H1/H2 feature evaluations. Breakout truncation probe identical. | — |
| F13 | All | 4 | VERIFIED OK | `binance_spot.py:170-176,203-205` (fee on fill notional, both sides); `engine.py:13-15,33-38` (spread and slippage enter the fill once; the decompositions are reporting only) | No double counting. The ledgers reconcile exactly; `economic-analysis.py` asserts this too. | — |
| F14 | All | 5 | VERIFIED OK | `engine.py:19-22` (liquidation-marked NAV, exit reserve not charged repeatedly); yearly compounding reconciles (A: 1.5203·1.5058·0.8210 = 1.8796 → +87.96 %) | — | — |
| F15 | All | 8 | VERIFIED OK (implementation) | `research/runner.py:201-206`, `engine.py:100-114`, `signals.py` (paired_bootstrap) | Circular blocks are correct, paired on the same indices, and the one-sided lower bound is the α-quantile (α .05 breakout/SMA, .05/3 SD-2026, .025 ED-2). Sharpe uses √365 daily and √8760 hourly. All seeds reproduce. Breakout per-trade t ≈ 0.44 (n=26): very low power. | — |
| F16 | A and H2 universe | 1, 9 | VERIFIED OK | `universe.json` (CMC 2019-12-29 top-8 non-stable ∩ Binance, BSV excluded before the anchor, no replacement); eligibility uses only trailing completed bars | — | — |
| F17 | Project level | 9 | THEORETICAL CONCERN (acknowledged) | ≥20 configurations (SMA, breakout, Timestral×2, futures×6, SD-2026×6, ED-2×4) on overlapping history; the 2024 SD holdout is reused as ED-2 "stress"; DSR "not estimable" | Any single positive segment is heavily selection-exposed. | No (nothing is promoted). |
| F18 | ED-2 H1/H2 | 1–10 | VERIFIED OK | 135/135 JSON byte-exact; timing asserts hold | H2 vs exposure-matched EW in 2020–22: CI [−5.7, −0.8] bp/day, significantly worse. H1 gross ≈ 0 or negative before costs. | No. Both correctly not promoted. |
| F19 | Documented rule vs code | 10 | VERIFIED OK, except F1 | Breakout `protocol.json:86-93` vs `runner.py:34-42,56-81,108-131`; SD-2026 `protocol.json` A/B/C rules vs `engine.py`; ED-2 `protocol.json` vs `signals.py` | — | — |

## 4. Exploratory results (all on already-observed data, not new tests)

### 4.1 Family C statistic (requested)

The rule is frozen and untuned:

- BTC hourly log return r[t]; z[t] = (r[t] − mean(r[t−168:t])) / sd(r[t−168:t], ddof=1), current hour excluded. Signal: z > 1.
- ETH entry at the open of bar t+2, one full hour after the signal bar closes. Exit at the open of t+3.
- Base round trip: about 24 bp (10 bp fee per side, 1 bp slippage per side, 2 bp spread).
- Irregular bars (8 per asset in 2020–23) and missing hours are left as NaN. Any window that touches one is skipped.
- 2024 has 8040/8040 regular hours for both assets.

| segment (entry date) | tradable signals | per year | mean gross bp | median bp | t (iid) | mean net bp: base / adverse / severe | compounded net, base | unconditional ETH mean bp/h |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020–2022 (gaps skipped) | 2500 | 833 | −0.31 | −2.96 | −0.14 | −24.3 / −50.2 / −80.0 | −99.8 % | 1.37 |
| 2023 (gap 24 Mar skipped) | 787 | 788 | +5.09 | +0.61 | 2.46 | −18.9 / −44.8 / −74.6 | −77.7 % | 0.86 |
| 2024 Jan–Nov (gap-free) | 847 | 924 | +4.82 | +3.55 | 1.78 | −19.2 / −45.1 / −74.9 | −80.8 % | 0.83 |

- **Per calendar year (primary rule):**

  | year | signals | mean gross bp |
  |---|---:|---:|
  | 2020 | 785 | +0.47 |
  | 2021 | 865 | −2.39 |
  | 2022 | 849 | +1.09 |
  | 2023 | 787 | +5.09 |
  | 2024 | 847 | +4.82 |

- **Neighbor (+2h):** +2.40 / +6.00 / +1.18 bp gross. Net is still about −18 to −23 bp.
- **Same-boundary entry (not the spec, shown only to check for any lead–lag):** +5.0 / −0.4 / −1.9 bp.
- **Break-even:** the costs would have to fall below about 5 bp per round trip, i.e. essentially zero fees.
- **Frozen engine on the same data:** identical numbers (−0.808107 / −0.777230). The 2024 ETH vol-capped comparator made +32.4 % and ETH buy-and-hold +61.9 %.

### 4.2 Breakout and SMA fill-timing sensitivity

| run | segment / costs | trades | net USDT | PF | positive quarters | bootstrap-5 lower |
|---|---|---:|---:|---:|---:|---:|
| original | test / base | 26 | +7.464 | 1.558 | 1 | −0.0529 |
| +1h | test / base | 27 | +6.937 | 1.478 | 1 | −0.0566 |
| +1h | test / adverse | 27 | +3.380 | 1.226 | 1 | −0.0614 |
| +1h | test / severe | 27 | −0.003 | 1.000 | 1 | −0.0661 |
| +2h | test / base | 26 | +8.248 | 1.633 | 1 | −0.0509 |
| +1h | 2025 / base | 39 | −5.839 | 0.775 | 2 | −0.065 |
| SMA original → +1h | test | 19 → 17 | −14.96 → −16.87 | 0.137 → 0.155 | — | — |

### 4.3 B: pooled comparison and gate power

See F7 and F8, and `out/b-pooled-power.json`.

Family A pooled against its exposure-matched EW comparator: −0.51 bp/day (CI includes 0). Against the vol-capped EW: Sharpe 1.12 vs 1.17. This agrees with "ranking adds nothing".

## 5. Prior numbers reproduced exactly

- **Breakout 4h:** all 12 `run-1/<segment>/<cost>/<arm>/metrics.json` are identical as serialized JSON. This includes:
  - net, PF and drawdown;
  - bootstrap 1/5/10 blocks;
  - quarterly and monthly figures;
  - test base net **7.463568755668508329**;
  - CI [−0.06302074563108129, 0.16878065157566743] and lower bound −0.05291423.
- **SMA168:** all 3 split `metrics.json` identical: dev +0.4435, validation −6.4507, test **−14.95955**, CI [−0.347469, +0.011686].
- **Strategy Discovery 2026:**
  - 153/153 A/B per-arm JSONs byte-identical.
  - 6/6 inference blocks, including B holdout Sharpe-difference lower bounds **−0.828 / −0.533** and CIs [−0.731, 1.661] / [−0.473, 1.428].
  - A holdout lower bounds −0.1266 % / −0.1228 %.
- **Edge Round 2:** 135/135 JSONs byte-identical and 5/5 inference blocks. Examples: H1 CI [−4.708, 0.503]; H2 [−4.664, +6.096] bp/day.
- **Report tables:** 216 numbers in `STRATEGY-RESEARCH-2026.md`, `EDGE-DISCOVERY-ROUND-2.md` and `PROJECT-VERDICT.md`, plus 27 in `BTCETH-B-VALIDATION.md`, all match. They cover:
  - main tables, benchmarks, neighbors and frictions;
  - yearly figures, regimes and top-5-day concentration;
  - B's 2023 decomposition (gap 416.27 raw, +2.56 friction);
  - breakout expectancy 0.287, win rate 34.62 %, payoff SD 3.32, holding times 68/192 h, best trade 16.18, rest −8.71, 3/9 positive months, 30.9 % exposure.

## 6. Proved vs only possible

**Proved:**

- Exact reproduction of every reported ledger and statistic.
- The timestamp-unit handling.
- No look-ahead under the perturbation and truncation probes.
- The loader cascade, and that it blocked a clean 2024 C holdout.
- C's large negative economics under its frozen rule and cost model on cached data.
- The SMA de-facto admission latch and its dates.
- The fill-delay sensitivities.
- B's pooled relative Sharpe and the gate's low power (normal approximation from the frozen bootstrap widths).

**Possible, not proved:**

- Real executable fills: there is no historical bid/ask, queue or intrabar sequence. Stop fills at the touched level may be optimistic in fast moves.
- Capacity and exchange-grid effects.
- Whether B has a small true edge: the CIs are wide in both directions.
- Whether a maker or near-zero-fee version of C could work: not tested, and outside the frozen specification.
- Project-level selection bias: real but not quantifiable without a full trial inventory.

## 7. Files

Scripts, in order:

| script | what it does | output |
|---|---|---|
| `00_tree_snapshot.py` | before/after snapshot of the project tree | `tree-before.json`, `tree-after.json` |
| `01_units.py` | archive timestamp units | `out/units.txt` |
| `02_breakout_repro.py` | breakout reproduction plus +1h/+2h fill | `out/breakout-repro.json` |
| `03_sma_repro.py` | SMA168 reproduction plus +1h fill | `out/sma-repro.json` |
| `04_sd2026_repro.py` | SD-2026 A/B byte-exact check plus inference | `out/sd2026-repro.json` |
| `05_family_c_exploratory.py` | C per-signal statistic | `out/family-c-exploratory.json` |
| `06_family_c_frozen_engine.py` | frozen C engine on gap-tolerant data | `out/family-c-frozen-engine.json` |
| `07_edge_r2_repro.py` | ED-2 byte-exact check plus look-ahead probe | `out/edge-r2-repro.json` |
| `08_probes.py` | breakout truncation probe plus SMA latch | `out/probes.json` |
| `09_sd_lookahead.py` | A/B feature perturbation | `out/sd-lookahead.json` |
| `10_claims_check.py` | report numbers vs ledgers | `out/claims-check.json` |
| `11_b_pooled_power.py` | pooled B/A comparison and gate power | `out/b-pooled-power.json` |
| `12_boundary_gap.py` | open-vs-previous-close gap at hour boundaries | `out/boundary-gap.json` |
| `13_b_report_check.py` | B validation report tables | `out/b-report-check.txt` |

Scratch journals (SQLite) are under `out/*-journals/`.
