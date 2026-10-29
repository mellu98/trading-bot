# Reject this MNQ H1 configuration on the observed sample

One frozen experiment, no grid, no H2. The ATR/time-exit candidate loses **before costs** and underperforms its matched control. It fails the preregistered economic acceptance criterion. This is not a universal rejection of ATR strategies. All 120 sessions were previously observed: none is independent evidence.

## Primary: continuous original risk

| Arm | Trades | Gross USD | Fees USD | Slippage USD | Net USD | PF | Expectancy USD | Minute-close DD USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A_full | 182 | 43.00 | 223.78 | 182.00 | -362.78 | 0.830 | -1.99 | 511.86 |
| A_matched | 108 | 342.00 | 132.42 | 108.00 | 101.58 | 1.088 | 0.94 | 153.52 |
| B | 86 | -263.50 | 105.42 | 86.00 | -454.92 | 0.730 | -5.29 | 488.22 |

A_full exactly reproduces the original ledger and global halt. B has no latched global halt, but four first candidates were rejected because their modeled stop exceeded the remaining original drawdown budget; 18 others exceeded the $100 cap. A_matched is only a schedule/admission control, NOT a strategy selected for deployment.

## Coverage diagnostic: daily-reset accounts, NOT a deployable portfolio

| Arm | Trades | Gross USD | Fees USD | Slippage USD | Net USD | PF | Expectancy USD | Stitched diagnostic DD USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A_full | 294 | 275.00 | 360.42 | 294.00 | -379.42 | 0.888 | -1.29 | 650.08 |
| A_matched | 108 | 342.00 | 132.42 | 108.00 | 101.58 | 1.088 | 0.94 | 153.52 |
| B | 90 | -427.50 | 110.30 | 90.00 | -627.80 | 0.663 | -6.98 | 661.10 |

- Identical first-signal schedule: 108 candidates in each arm/account. B skips 18 for initial risk, hence 90 trades; A_matched trades 108. All 120 session P&Ls, including zeros, remain in paired intention-to-treat comparisons. Differences include admission and occupancy, not only stop geometry.
- B exits: 21 stops, 2 targets, 67 five-minute exits; zero stop/target-collision bars. Mean duration is bounded 4.322–4.578 minutes; median 5. Mean initial stop exposure $55.41 versus $16 control: one micro each is NOT equal dollar risk. Maximum admitted all-in modeled stop $98.22, cap $100. Real gaps/fills can exceed it.
- B worst trade -$98.22; net fifth percentile -$75.21; median -$8.22; maximum losing streak 7 across sessions (descriptive; original risk resets its consecutive-loss count daily). Net 30-session blocks: -$116.80, -$169.06, +$57.50, -$399.44. Only 1 of 4 positive. Mean net R/trade -0.1413. Occupancy bounded 389–412 minutes versus matched control 117–225.
- Paired B minus A_matched: **-$729.38 total / -$6.078 daily**. Circular five-session bootstrap, 10,000 replicates, seed 1729: daily-delta 95% CI [-$11.707, -$0.587]. Sensitivity block 1: [-$12.425, +$0.294]; block 10: [-$11.443, -$0.905]. Conditional intervals are not independent validation. B absolute daily 95% CI [-$11.162, +$0.590] still crosses zero: do not claim statistically established universal negative expectancy.
- Existing adverse-cost scenario skipped exactly as preregistered because base B net was already negative. No subscription/feed cost included; adding one cannot rescue negative gross.

## Excursions and execution limitations

B diagnostic mean gross MFE: guaranteed $37.51 / possible upper envelope $38.49; MAE: guaranteed $29.84 / possible $31.43. The 23 intrabar stop/target exits are censored. Possible exit-bar extrema can occur AFTER execution and are NOT realized excursions. All 67 open-time exits exclude the subsequent bar high/low completely. Per-trade bounds and duration intervals are in trade CSVs; distribution quantiles are in results.json.

Costs are unverified technical assumptions, not broker statements: $0.25 broker + $0.35 exchange + dated $0.02/$0.01 regulatory per side; one tick adverse entry and exit, zero spread. Stop-first collisions, adverse gap stops, no favorable target-gap improvement. Open deadline precedes later minute OHLC. Full roundtrip costs reserved in open marks. Minute-close DD is not tick-level DD. News OFF for exploration; strict news remains uncertified/blocked.

## Frozen evidence and reproducibility

| Evidence | SHA256 / result |
|---|---|
| protocol.json | a0898682d624abaf7c9f2071502bbc3226e44c430c136490d6317b0fd95b228d |
| freeze-manifest.json | 299665ef17215248cd95ff026daea94dee2247480d477dfe94b74759fad9e24d |
| experiment.py | 02323b65b728bda22fdc534934b7e730cbabed280e1b599f889f7dcca46197ae |
| results.json, two identical locked replays | 699c67eb283668d73c6df2b52d0cd370a2f9c874b62a4652e923552c772eaa6c |
| Existing dataset | b5d3e676d1de881a8bd1a07eedccc14f286a615db0d7b4169f9950fead600ff5 |

Synthetic TDD RED preceded implementation; 11 focused + 39 pertinent existing tests pass. Original A_full per-trade ledgers/economics reconcile in both accounts. verification.json checks matched schedule, quantity/cap, timing, tick rounding, brackets and excursion inequalities. The two replay logs record the same frozen code/configuration, not a search. Inputs: 120 sessions, 46,800 MNQ bars, 93,600 MNQ+MES bars.

All 2,428 prior files and 459 archive-manifest entries verified unchanged before/after. No frozen source, production Risk, V1/V2, Timestral, dashboard or configuration changed. No credentials read, broker connection, purchase or network connection.

Original engine has no variable-stop/time hook: a research-only subclass reuses initialization, unchanged PriceStrategy, entry_permission, close and Config.risk. Inherited preflight: no Git repository/gentle-ai facade and CodeGraph NotInitialized; targeted direct reads only, no lifecycle/admin work. No commits or production review receipt. Rollback: delete only this directory.

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
export PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src:reports/sweep-atr-experiment
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -m pytest reports/sweep-atr-experiment/test_experiment.py tests_sim/test_engine.py tests_sim/test_strategies_v2.py tests_sim/test_quant.py tests_sim/test_research_v2.py -q
.venv/bin/python reports/sweep-atr-experiment/experiment.py
```

Protocol/code/input edits fail closed. Do not repeat `--freeze`: the immutable freeze already exists. Rerunning tests may regenerate unprotected caches but must not overwrite the frozen evidence logs.

## Next step

No promotion, automatic retune, new strategy or data spend. A genuinely new 90-session protocol was frozen in advance and copied to future-independent-protocol.json. Its fixed thresholds do not authorize collection or justify advancing this rejected configuration. Existing 120 sessions remain exploratory forever.
