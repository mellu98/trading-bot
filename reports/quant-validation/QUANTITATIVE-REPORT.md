# MNQ/MES quantitative validation — actual data, exploratory only

The new115sessions were acquired once within the approved$0.50. All120sessions are locally available. No result below approves paper/live trading: the complete point-in-time news calendar and tick-level execution remain unverified.

## Reproduce offline

```sh
'/Users/locoframe/Desktop/TRADING BOT/run-validation.sh'
```

The command reads validated local CSV/cache only; no credentials, downloads or broker orders. It preserves the frozen selection and fails if protocol/data/selection identity changes. The previously verified five-day simulation remains `run-simulation.sh`.

## Dataset and scope

- 93600 actual1minute bars,120cash sessions May5–October23,2026. The115new daily queries each contained both actual MNQ/MES contracts; original five sessions were cache hits, not downloaded again.
- Fresh official preflight $0.327475368960; actual completed-query reserved estimate $0.327475368960, cap$0.50. Client-side estimate, not an independently checked invoice/vendor hard spending limit.
- Original multi-contract DBN bytes are retained in `data/databento/bulk120`, with durable per-query attempted/completed ledger, checksums and contract/publisher/time-grid/volume/OHLC validation before normalization. `data-quality120.json` records each cash day. No missing bars are fabricated.
- Selection uses the provider previous-day-volume rule, resolved into explicit contract IDs/raw symbols. No contemporaneous full-day volume was used. Vendor publication latency and historical correction lineage are not independently attested.
- Raw data is not redistributed. `bars120.csv` retains original integer UNIXns. `quote115.json` contains actual rollover intervals and daily availability conditions.

## Frozen method and limits

- Threshold±2.5, rolling residual standard deviation20(ddof0), cash typical-price VWAP anchor09:30, original MES4/2point and MNQ15/8point target/stop. Signals at completed bars; following-open fills with assumed zero extra feed latency. Stops first if target and stop touch the same bar; adverse gap stop fills, no favorable gap target improvement.
- Primary four arms use independent per-instrument virtual accounts and the original persistent global drawdown kill. The original combined portfolio (one position total, MNQ-first tie priority) is shown separately. It is not valid to add independent-arm drawdowns or claim they are the same shared-risk portfolio.
- VWAP variant preserves the earlier registered rule: freeze signal-time VWAP rounded to a quarter tick, not a moving VWAP target. It is evaluated separately, never substituted retrospectively for a better result.
- Fee scenario: broker$0.25+exchange$0.35per side; NFA$0.02per side throughJune30 and$0.01fromJuly1,2026. Slippage1tick entry+1tick exit, spread0assumption; stresses1.5x/2x rerun risk gates, not just subtract costs afterwards. These are public schedule assumptions, not verified account statements.
- News OFF is explicitly exploratory. No revised economic value was used as ex-ante data. Strict mode actually processed the full dataset and opened zero trades because complete certifiedPITnews is absent.
- Training threshold for low/high volatility uses only the first20calibration sessions; earlier trades are calibration_unclassified. Regime labels use causal20bar volatility at signal, never whole-day future realized volatility. Predeclared time buckets are09:45–11:30,11:30–13:30,13:30–15:30NY.
- No threshold/time/regime filter was selected from the test outcomes. `preregistered-protocol.json` was frozen before new acquisition/return inspection; statisticalamendment01(before returns) uses conservative family16 one-sided bounds, seed1729,5000circular5session block bootstrap replicates. Subgroups are descriptive, not new significant strategies.


## Original continuous protected accounts — all120sessions

| Arm | Trades | Gross USD | Fees USD | Slippage/spread USD | Net USD | Win % | PF | Expectancy USD | Minute-close DD USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MES/fixed | 77 | -192.50 | 95.48 | 192.50 | -480.48 | 24.68 | 0.39 | -6.24 | 504.25 |
| MES/vwap | 92 | -128.75 | 114.08 | 230.00 | -472.83 | 17.39 | 0.55 | -5.14 | 505.35 |
| MNQ/fixed | 65 | -350.00 | 80.60 | 65.00 | -495.60 | 23.08 | 0.46 | -7.62 | 505.92 |
| MNQ/vwap | 160 | 524.00 | 198.18 | 160.00 | 165.82 | 11.25 | 1.06 | 1.04 | 510.50 |

### Original shared-risk portfolio reference

| Arm | Trades | Gross USD | Fees USD | Slippage/spread USD | Net USD | Win % | PF | Expectancy USD | Minute-close DD USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Combined fixed-target portfolio | 75 | -274.00 | 93.00 | 127.50 | -494.50 | 24.00 | 0.46 | -6.59 | 504.82 |

Global drawdown kills are not reset inside these continuous runs. Zero-trade sessions after a kill remain in daily results.
- MES/fixed: global halt=True, last trade=2026-05-22, sessions with nonzero realized PnL=14.
- MES/vwap: global halt=True, last trade=2026-06-04, sessions with nonzero realized PnL=22.
- MNQ/fixed: global halt=True, last trade=2026-05-22, sessions with nonzero realized PnL=14.
- MNQ/vwap: global halt=True, last trade=2026-07-07, sessions with nonzero realized PnL=43.

## Independent-session diagnostic — explicit account-reset rule change

| Arm | Trades | Gross USD | Fees USD | Slippage/spread USD | Net USD | Win % | PF | Expectancy USD | Minute-close DD USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MES/fixed | 633 | -188.75 | 776.70 | 1582.50 | -2547.95 | 32.23 | 0.57 | -4.03 | 2571.72 |
| MES/vwap | 500 | 318.75 | 613.08 | 1250.00 | -1544.33 | 21.60 | 0.71 | -3.09 | 1649.36 |
| MNQ/fixed | 627 | -1844.00 | 769.00 | 627.00 | -3240.00 | 28.39 | 0.60 | -5.17 | 3400.58 |
| MNQ/vwap | 452 | -468.00 | 554.42 | 452.00 | -1474.42 | 11.50 | 0.80 | -3.26 | 2150.74 |

This diagnostic resets the virtual account at each session to inspect signal/cost economics across all market dates. It is NOT the original persistent account and cannot replace its baseline or be selected using test results. Its aggregate drawdown can exceed the original global cap.

## Walk-forward — disjoint50test sessions

| Arm | Trades | Gross USD | Fees USD | Slippage/spread USD | Net USD | Win % | PF | Expectancy USD | Minute-close DD USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MES/fixed | 256 | 30.00 | 313.14 | 640.00 | -923.14 | 33.59 | 0.60 | -3.61 | 1053.42 |
| MES/selected | 43 | 18.75 | 52.46 | 107.50 | -141.21 | 25.58 | 0.68 | -3.28 | 226.54 |
| MES/vwap | 203 | 413.75 | 248.30 | 507.50 | -342.05 | 24.63 | 0.84 | -1.68 | 709.33 |
| MNQ/fixed | 241 | -958.00 | 294.98 | 241.00 | -1493.98 | 26.14 | 0.54 | -6.20 | 1607.60 |
| MNQ/selected | 75 | 170.50 | 92.20 | 75.00 | 3.30 | 12.00 | 1.00 | 0.04 | 656.26 |
| MNQ/vwap | 176 | -654.00 | 215.42 | 176.00 | -1045.42 | 9.66 | 0.64 | -5.94 | 1430.10 |

Each fold:20calibration/10validation/10test; five folds. Fixed/VWAP selection uses validation-only net and chooses NO_TRADE if both lose. A fresh virtual account starts at each evaluation fold; this is explicitly separate from the120session persistent run.

### Validation-only final choices
- MES: NO_TRADE; aggregate validation scores {'fixed': -1036.6599999999999, 'vwap': -329.24}.
- MNQ: NO_TRADE; aggregate validation scores {'fixed': -1642.62, 'vwap': -471.1999999999997}.

## Temporal holdout —30sessions

| Arm | Trades | Gross USD | Fees USD | Slippage/spread USD | Net USD | Win % | PF | Expectancy USD | Minute-close DD USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MES/fixed | 76 | -220.00 | 92.72 | 190.00 | -502.72 | 23.68 | 0.37 | -6.61 | 502.72 |
| MES/selected | 0 | 0.00 | 0.00 | 0.00 | 0.00 | n/a | n/a | n/a | 0.00 |
| MES/vwap | 83 | -193.75 | 101.26 | 207.50 | -502.51 | 16.87 | 0.47 | -6.05 | 502.51 |
| MNQ/fixed | 125 | -197.50 | 152.50 | 125.00 | -475.00 | 31.20 | 0.70 | -3.80 | 505.48 |
| MNQ/selected | 0 | 0.00 | 0.00 | 0.00 | 0.00 | n/a | n/a | n/a | 0.00 |
| MNQ/vwap | 90 | -31.50 | 109.80 | 90.00 | -231.30 | 16.67 | 0.83 | -2.57 | 506.90 |

Holdout 2026-09-04 through 2026-10-16; selected policy frozen before holdout was unlocked. The five inspected October19–23dates are excluded. The project has not supplied an external human attestation that this holdout was never seen elsewhere. Reproduction reruns do not authorize parameter retuning.

### Conditional out-of-sample uncertainty

| Stage / arm | Mean daily net | Mean95%CI | Simultaneous one-sided lower mean | Positive conditional bound |
|---|---:|---|---:|---|
| WF/MES/fixed | -18.46 | [-30.50935000000001, -2.9287400000000114] | -32.91 | False |
| WF/MES/selected | -2.82 | [-7.845400000000001, 0.3888000000000001] | -10.37 | False |
| WF/MES/vwap | -6.84 | [-23.02581, 10.783605000000001] | -27.85 | False |
| WF/MNQ/fixed | -29.88 | [-40.6354, -18.584440000000008] | -44.17 | False |
| WF/MNQ/selected | 0.07 | [-18.375269999999997, 19.103019999999994] | -26.20 | False |
| WF/MNQ/vwap | -20.91 | [-40.8172, 1.381329999999993] | -46.08 | False |
| Holdout/MES/fixed | -16.76 | [-27.82533333333333, -5.747766666666709] | -31.43 | False |
| Holdout/MES/selected | 0.00 | [0.0, 0.0] | 0.00 | False |
| Holdout/MES/vwap | -16.75 | [-25.979583333333334, -7.299] | -29.41 | False |
| Holdout/MNQ/fixed | -15.83 | [-26.176666666666655, -5.225716666666669] | -30.64 | False |
| Holdout/MNQ/selected | 0.00 | [0.0, 0.0] | 0.00 | False |
| Holdout/MNQ/vwap | -7.71 | [-26.814999999999994, 11.875400000000003] | -34.31 | False |

These approximate moving-block intervals are conditional on this sample, risk rule, costs and exploratory news-OFF mode. They are not proof against nonstationarity, calendar errors, selection reuse, or unknown intrabar fills.

## Cost sensitivity

| Arm / slippage multiplier | Trades | Gross | Fees | Execution | Net |
|---|---:|---:|---:|---:|---:|
| MES/fixed/1.0 | 77 | -192.50 | 95.48 | 192.50 | -480.48 |
| MES/fixed/1.5 | 62 | -170.00 | 76.88 | 232.50 | -479.38 |
| MES/fixed/2.0 | 54 | -150.00 | 66.96 | 270.00 | -486.96 |
| MES/vwap/1.0 | 92 | -128.75 | 114.08 | 230.00 | -472.83 |
| MES/vwap/1.5 | 45 | -247.50 | 55.80 | 168.75 | -472.05 |
| MES/vwap/2.0 | 42 | -217.50 | 52.08 | 210.00 | -479.58 |
| MNQ/fixed/1.0 | 65 | -350.00 | 80.60 | 65.00 | -495.60 |
| MNQ/fixed/1.5 | 64 | -334.00 | 79.36 | 96.00 | -509.36 |
| MNQ/fixed/2.0 | 62 | -302.00 | 76.88 | 124.00 | -502.88 |
| MNQ/vwap/1.0 | 160 | 524.00 | 198.18 | 160.00 | 165.82 |
| MNQ/vwap/1.5 | 159 | 540.00 | 196.96 | 238.50 | 104.54 |
| MNQ/vwap/2.0 | 36 | -388.00 | 44.64 | 72.00 | -504.64 |

### Cost break-even arithmetic (not an estimated win probability)

| Fee period | Instrument | Gross target/stop USD | Roundtrip fees+slippage USD | Required TP win rate | Minimum quarter-tick profitable target distance |
|---|---|---|---:|---:|---:|
| May-June | MES | 20.0/10.0 | 3.74 | 45.8000% | 0.75points |
| May-June | MNQ | 30.0/16.0 | 2.24 | 39.6522% | 1.25points |
| July-October | MES | 20.0/10.0 | 3.72 | 45.7333% | 0.75points |
| July-October | MNQ | 30.0/16.0 | 2.22 | 39.6087% | 1.25points |

This algebra assumes only exact fixed-target/stop outcomes, no gap/time/risk exits, baseline1tick slippage each side and spread0. It is NOT a forecast. The VWAP variant can hit a small gross-profit target yet lose net if its target distance does not cover friction. No cost-aware entry filter was fitted or added after seeing test results.

### Attribution and loss categories

Categories below use the independent-session diagnostic to avoid hiding later regimes behind an early global kill. Never sum overlapping time/regime/side categories together. No category becomes a trading filter merely because it looks better.
Ambiguous bracket counts: MESfixed23/633, MESVWAP3/500, MNQfixed75/627, MNQVWAP2/452 in the daily-independent diagnostic. Stop-first remains the only realized simulation assumption; these are not resolved tick outcomes.

#### MES/fixed
Gross -188.75; broker commissions 316.50; exchange 443.10; regulatory 17.10; slippage/spread 1582.50; net -2547.95. Gross-positive/net-negative trades: 1.
- Time/morning: 473trades, gross-50.00, fees580.34, execution1182.50, net-1812.84, expectancy-3.83,PF0.58.
- Time/midday: 132trades, gross-180.00, fees162.08, execution330.00, net-672.08, expectancy-5.09,PF0.48.
- Time/afternoon: 28trades, gross41.25, fees34.28, execution70.00, net-63.03, expectancy-2.25,PF0.72.
- Volatility/high: 401trades, gross-460.00, fees491.24, execution1002.50, net-1953.74, expectancy-4.87,PF0.50.
- Volatility/calibration_unclassified: 121trades, gross-10.00, fees150.04, execution302.50, net-462.54, expectancy-3.82,PF0.58.
- Volatility/low: 111trades, gross281.25, fees135.42, execution277.50, net-131.67, expectancy-1.19,PF0.85.
- Side/-1: 330trades, gross-470.00, fees405.32, execution825.00, net-1700.32, expectancy-5.15,PF0.47.
- Side/1: 303trades, gross281.25, fees371.38, execution757.50, net-847.63, expectancy-2.80,PF0.68.
- Exit/stop: 427trades, gross-4270.00, fees524.02, execution1067.50, net-5861.52, expectancy-13.73,PF0.00.
- Exit/session_close: 2trades, gross1.25, fees2.44, execution5.00, net-6.19, expectancy-3.09,PF0.00.
- Exit/target: 204trades, gross4080.00, fees250.24, execution510.00, net3319.76, expectancy16.27,PFn/a.

#### MES/vwap
Gross 318.75; broker commissions 250.00; exchange 350.00; regulatory 13.08; slippage/spread 1250.00; net -1544.33. Gross-positive/net-negative trades: 1.
- Time/morning: 380trades, gross108.75, fees466.08, execution950.00, net-1307.33, expectancy-3.44,PF0.69.
- Time/midday: 89trades, gross210.00, fees109.12, execution222.50, net-121.62, expectancy-1.37,PF0.86.
- Time/afternoon: 31trades, gross0.00, fees37.88, execution77.50, net-115.38, expectancy-3.72,PF0.59.
- Volatility/high: 310trades, gross272.50, fees379.50, execution775.00, net-882.00, expectancy-2.85,PF0.74.
- Volatility/calibration_unclassified: 87trades, gross-78.75, fees107.88, execution217.50, net-404.13, expectancy-4.65,PF0.59.
- Volatility/low: 103trades, gross125.00, fees125.70, execution257.50, net-258.20, expectancy-2.51,PF0.72.
- Side/-1: 267trades, gross-331.25, fees327.76, execution667.50, net-1326.51, expectancy-4.97,PF0.56.
- Side/1: 233trades, gross650.00, fees285.32, execution582.50, net-217.82, expectancy-0.93,PF0.91.
- Exit/stop: 390trades, gross-3900.00, fees478.42, execution975.00, net-5353.42, expectancy-13.73,PF0.00.
- Exit/session_close: 4trades, gross72.50, fees4.88, execution10.00, net57.62, expectancy14.41,PF10.31.
- Exit/target: 106trades, gross4146.25, fees129.78, execution265.00, net3751.47, expectancy35.39,PFn/a.

#### MNQ/fixed
Gross -1844.00; broker commissions 313.50; exchange 438.90; regulatory 16.60; slippage/spread 627.00; net -3240.00. Gross-positive/net-negative trades: 0.
- Time/morning: 478trades, gross-1898.00, fees586.06, execution478.00, net-2962.06, expectancy-6.20,PF0.54.
- Time/afternoon: 29trades, gross-96.00, fees35.58, execution29.00, net-160.58, expectancy-5.54,PF0.58.
- Time/midday: 120trades, gross150.00, fees147.36, execution120.00, net-117.36, expectancy-0.98,PF0.91.
- Volatility/high: 442trades, gross-1736.00, fees541.14, execution442.00, net-2719.14, expectancy-6.15,PF0.54.
- Volatility/calibration_unclassified: 101trades, gross-328.00, fees125.24, execution101.00, net-554.24, expectancy-5.49,PF0.58.
- Volatility/low: 84trades, gross220.00, fees102.62, execution84.00, net33.38, expectancy0.40,PF1.04.
- Side/1: 276trades, gross-1012.00, fees338.16, execution276.00, net-1626.16, expectancy-5.89,PF0.56.
- Side/-1: 351trades, gross-832.00, fees430.84, execution351.00, net-1613.84, expectancy-4.60,PF0.64.
- Exit/stop: 449trades, gross-7184.00, fees550.76, execution449.00, net-8183.76, expectancy-18.23,PF0.00.
- Exit/target: 178trades, gross5340.00, fees218.24, execution178.00, net4943.76, expectancy27.77,PFn/a.

#### MNQ/vwap
Gross -468.00; broker commissions 226.00; exchange 316.40; regulatory 12.02; slippage/spread 452.00; net -1474.42. Gross-positive/net-negative trades: 0.
- Time/morning: 366trades, gross-378.50, fees448.72, execution366.00, net-1193.22, expectancy-3.26,PF0.80.
- Time/afternoon: 25trades, gross-112.50, fees30.72, execution25.00, net-168.22, expectancy-6.73,PF0.56.
- Time/midday: 61trades, gross23.00, fees74.98, execution61.00, net-112.98, expectancy-1.85,PF0.87.
- Volatility/high: 317trades, gross-758.00, fees388.10, execution317.00, net-1463.10, expectancy-4.62,PF0.72.
- Volatility/calibration_unclassified: 75trades, gross69.00, fees93.00, execution75.00, net-99.00, expectancy-1.32,PF0.92.
- Volatility/low: 60trades, gross221.00, fees73.32, execution60.00, net87.68, expectancy1.46,PF1.11.
- Side/-1: 235trades, gross-401.00, fees288.36, execution235.00, net-924.36, expectancy-3.93,PF0.75.
- Side/1: 217trades, gross-67.00, fees266.06, execution217.00, net-550.06, expectancy-2.53,PF0.84.
- Exit/stop: 400trades, gross-6400.00, fees490.62, execution400.00, net-7290.62, expectancy-18.23,PF0.00.
- Exit/target: 52trades, gross5932.00, fees63.80, execution52.00, net5816.20, expectancy111.85,PFn/a.

### Paired MNQ versus MES

- fixed, MES-minus-MNQ daily USD mean 5.77,95%CI[-0.7336562500000057, 12.570049999999993], simultaneous lower-3.86. Relative differences are NOT evidence either instrument has positive absolute net edge; one-contract risk differs (MES stop$10,MNQstop$16). NetR is reported in JSON.
- vwap, MES-minus-MNQ daily USD mean -0.58,95%CI[-17.23204375, 14.950183333333323], simultaneous lower-24.36. Relative differences are NOT evidence either instrument has positive absolute net edge; one-contract risk differs (MES stop$10,MNQstop$16). NetR is reported in JSON.
- OOS walk_forward_paired/fixed: MES-minus-MNQ mean11.42,95%CI[1.8515499999999927, 22.205959999999973], multiplicity-adjusted lower-2.38; positive relative difference supported=False.
- OOS holdout_paired/fixed: MES-minus-MNQ mean-0.92,95%CI[-14.122700000000005, 13.281366666666662], multiplicity-adjusted lower-17.45; positive relative difference supported=False.
- OOS walk_forward_paired/vwap: MES-minus-MNQ mean14.07,95%CI[-4.756940000000003, 33.709079999999986], multiplicity-adjusted lower-11.87; positive relative difference supported=False.
- OOS holdout_paired/vwap: MES-minus-MNQ mean-9.04,95%CI[-28.01432500000001, 8.28715833333333], multiplicity-adjusted lower-34.41; positive relative difference supported=False.

### A positive subgroup is not a validated filter

- MNQ fixed/low-volatility walkforward: 28trades, net179.70, mean daily95%CI[0.0, 7.898799999999999], exploratory multiplicity-adjusted lower-0.81.
- MNQ fixed/low-volatility holdout: 30trades, net97.40, mean daily95%CI[-0.8359999999999995, 7.6480000000000015], exploratory multiplicity-adjusted lower-3.34.
The positive point estimates do not establish a robust condition-specific edge. No low-volatility filter was fitted after seeing these results; any such proposal needs new preregistration and untouched evaluation. All120sessions, including this holdout, have now been economically inspected: the same holdout cannot be relabeled untouched for a new rule. Any further data acquisition needs a new explicit scope/budget authorization.


## Strategy assessment

Arms with positive multiplicity-adjusted lower daily mean in BOTH frozen WF and temporal holdout: none.
No certified tradable edge is established. Even a positive exploratory subgroup/result is insufficient to approve autonomous paper/live trading while the calendar/execution/account-cost evidence is incomplete. Negative net after fees/slippage must not be replaced with gross profitability. No live order route was implemented or enabled.

## More-granular data — quotes only

| Scope | Schema | Official USD | Records | Billable uncompressed bytes |
|---|---|---:|---:|---:|
| Both roots, one full cash day,1second bars | ohlcv-1s | 0.167129263282 | 45779 | 2563624 |
| MES ambiguous-bracket10minute slice, trades | trades | 0.03161162138 | 25255 | 1212240 |
| MES same slice, BBO for execution checks | mbp-1 | 0.115189611912 | 858916 | 68713280 |
| MNQ calibration ambiguous-bracket10minute slice | trades | 0.08365470171 | 66833 | 3207984 |
| MNQ calibration ambiguous-bracket10minute slice | mbp-1 | 0.195015639067 | 1454142 | 116331360 |

Quotes checked 2026-10-26T00:57:36.835552Z; refresh and obtain separate explicit approval before any acquisition. None was downloaded. One-second bars still cannot resolve subsecond ordering. Trades+BBO for the known10minuteMEScollision slice are a focused next execution test, not a representative financial validation of120days.

## Remaining blockers before autonomous paper trading

- Complete versioned CPI/NFP/FOMC/other configured event evidence with pre-session known_at/revision lineage. FOMC tentative schedule is verifiable from a dated2024FederalReserve release; current BLS pages alone do not complete the PIT audit. Strict mode remains blocked.
- Account-specific dated transaction fees, spread/latency/slippage estimates from suitably granular data, conservative fill validation, and enough untouched evidence after any new rule selection.
- Authenticated broker paper session/permissions, native bracket/OCO/partial/reject/reconnect/restart reconciliation and continuously authorized data/news watchdog. No real orders or withdrawals.
- Timestral remains optional/off. ModifiedMIT model eligibility under company/employer revenue conditions is unknown; no false legal attestation or synthetic AI economic results. Existing Timestral code is unchanged.

## Evidence

`quote115.json`, `preflight-responses.json`, `data-quality120.json`, `preregistered-protocol.json`, `protocol-amendment-01.json`, `validation-only-selection.json`, `holdout-access.json`, `quant-results.json`, `results/`, `news-pit-assessment.json`, `granular-quote.json`, `tests-local.txt`.
