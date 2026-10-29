# Real-data simulation delivered

The authorized five-session sample was downloaded and structurally verified. The offline end-to-end replay works; the fixed-target technical baseline loses money after the declared costs. This is NOT statistical, AI, LEAN, or broker-paper certification.

## Start

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
./run-simulation.sh --verbose
```

This command is offline: it reads and revalidates local DBN, logs decisions, creates simulated trades/orders, and writes reports. It never downloads data, reads an API key, or contacts a broker. Existing completed outputs are reproducibly regenerated.

Reports: `reports/real-simulation/baseline-fixed/{report.md,summary.json,trades.csv,orders.csv,decisions.csv,equity.csv,risk_events.csv}`. Permanent raw cache: `data/databento/jobs/authorized-oct19-23-2026/`; normalized `reports/real-simulation/bars.csv` preserves integer UNIX nanoseconds.

## Actual technical outcomes

| Run | Trades | Gross USD | Fees USD | Execution cost USD | Net USD | Win rate | Profit factor | Minute-close drawdown USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed target baseline | 39 | 44.00 | 47.58 | 73.50 | -77.08 | 38.46% | 0.7965 | 163.60 |
| Frozen signal-VWAP target | 23 | -37.25 | 28.06 | 41.00 | -106.31 | 17.39% | 0.6573 | 166.24 |
| Fixed target / 2x slippage | 39 | 44.00 | 47.58 | 147.00 | -150.58 | 38.46% | 0.6434 | 220.60 |

The primary result is the predeclared fixed-target baseline, not whichever variant performs best. No thresholds were tuned on these five days. Fixed-target baseline: MNQ16 trades/net-$61.52, MES23/net-$15.56. One same-bar stop/target collision was flagged and resolved stop-first (MES October23, order00032).

## Data and acquisition safety

- GLBX.MDP3/ohlcv-1m; MNQZ6 and MESZ6; October19–23,2026; separate09:30–16:00America/New_York cash windows. 3900 bars, zero missing minutes/duplicate bars in the acquired sample, correct UTC minute grid, quarter ticks, positive futures volumes, contract IDs and publisher1. Raw DBN request bounds and SHA256 verified before normalization.
- Ten unique paid API queries completed, allHTTP200; fresh official estimated aggregate$0.014238059520 below the explicitly authorized$0.02. The provider invoice/account balance was not independently queried; this is not a vendor-enforced billing cap.
- A free pre-partition check interrupted the first job after seven fully completed downloads. Durable attempted/completed records proved the remaining three were never requested. Only those three were newly quoted/acquired; the original evidence remains in first-attempt-* files. No paid query was retried.
- The volume rule uses the previous day, per official Databento symbology; raw contracts are frozen and no roll occurs during this sample. Historical mapping does not independently attest publication timing. No raw data should be redistributed without checking vendor/exchange terms.

## Strategy and controls

- Existing unchanged `mnq_timestral` features, SignalGenerator, Risk, Costs and conservative simulate_trade helpers are reused. Session VWAP uses one-minute typical price×volume, reset09:30; residual standard deviation20bars, ddof0; Z thresholds±2.5; first19bars warm-up. This is not exact trade VWAP.
- Decisions occur after a closed bar; pending entries use the following bar open under an explicit zero-extra-feed-latency assumption. Entry window09:45–15:30NewYork; flat by15:30. One contract/trade and a stricter portfolio cap of one position total, deterministic MNQ-first tie priority.
- Fixed brackets: MES target4/stop2points, MNQ target15/stop8points. The separate VWAP variant freezes signal-time VWAP rounded to the nearest valid tick; it does not implement a moving VWAP target. Stops are never widened. Adverse open gaps use the adverse open, targets receive no favorable gap improvement.
- Fees per side: broker$0.25 + exchange$0.35 + NFA$0.01=$0.61, using public schedules. These are not verified account-specific historical charges. Baseline spread0 and one tick slippage per entry/exit are explicit assumptions, not observed bid/ask fills. Cost inputs are configurable in config.json; stress doubles slippage.
- Deterministic risk gates: daily loss$200 including open marks, global drawdown$500,10daily trades,3consecutive losses; latched daily/global stops. Gaps/slippage can exceed loss limits. Risk drills cover one-trade daily cap, unrealized loss and drawdown halts.
- `touch reports/real-simulation/KILL` latches the kill switch and flattens at the next available replay open. This is a local replay control, not a guarantee for an external broker. Remove the file before a fresh independent replay.
- Atomic checkpoint every30events; resume an interrupted output with `./run-simulation.sh --output <same-output> --resume`. A real-data interruption at event250 reproduced identical summary/trade/order/decision/equity hashes. Synthetic tests also restart an open reconciled bracket.

## Important limits

- News protection is bounded to the explicitly configured CPI/NFP/FOMC/BLS releases in news-calendar.json, checked against current official BLS/Fed schedules. It is not a complete global economic/speech/unscheduled-news calendar or an independently archived point-in-time snapshot. The primary result is a technical replay under this declared schedule assumption.
- `./run-simulation.sh --strict-unattested-news --output reports/real-simulation/strict-news` correctly produces zero trades because archived point-in-time calendar attestation is absent. Missing calendar always blocks entries; no fake known_at/calendar attestation was inserted into the verified ABC pipeline.
- OHLC cannot determine exact intrabar order, latency, order queue, partial fills or tick-level maximum drawdown. Ambiguous brackets use stop-first and are flagged. No live execution accuracy or profitable advantage is claimed.
- Five days cannot establish statistical robustness. All configurations remain in simulation. Timestral source is unchanged and optional; no real checkpoint inference or AI economic performance was claimed.
- Pinned28M LICENSE was retrieved. Eligibility depends on the company/employer consolidated monthly revenue condition; eligibility is unknown, so weights were not downloaded under an invented license attestation.
- Docker CLI exists, but a read-only daemon probe did not succeed within10seconds; no verified LEAN runtime or dotnet exists. The small local replay is the bounded alternative for this technical sample, not a LEAN-equivalent execution certification.

## 120-session quote and next validation boundary

Official metadata-only quote: 2026-05-05 through 2026-10-23,120cash sessions, both instruments, total **$0.341713428480**, supported by125persistedHTTP200metadata/symbologyresponses. No additional data downloaded.
Five already acquired sessions are valid cache hits. The sum of exact quotes for only the115missing sessions is **$0.327475368960**; no proportional price estimate or duplicate purchase is needed.
- The quote must be refreshed before a future acquisition and needs a separate explicit scope/budget authorization. `quote120/quote.json` and `validation-readiness.json` contain raw-contract mappings, conditions and the proposed splits.
- The five inspected dates are excluded from untouched evaluation. Remaining115sessions permit five walk-forward folds (50test sessions) and a30-session holdout, subject to complete usable data, frozen preregistration and human previously-unseen attestation. Existing evidence gates were not weakened.
- Interactive Brokers paper remains unconnected: needs an authenticated paper Gateway/TWS session, verified permissions/data rights and account costs, broker-native bracket/partial/reject/disconnect/restart drills. `deployment-readiness.json` records the boundary. No broker/live/withdrawal command was added.

## Verification

- New20tests passed; original54passed+2skipped; original Databento adapter123passed; frozen planner44passed. Total241passed+2skipped. Real offline replay attempted zero network connections. All90pre-existing paths,37primary protected files and20frozen planner files retain their hashes.
- `verification.json`, `restart-validation.json`, `network-proof.json`, `risk-drills.json` and `runtime.json` record actual checks and pinned environment/source/input hashes.
- No new agents, no repeated source audit, no unrelated component rebuild, no external project edits.

## Sources

- Databento symbology: https://databento.com/docs/conventions/symbology
- Broker fees: https://www.interactivebrokers.com/en/pricing/commissions-futures.php
- CME exchange recovery fees: https://www.interactivebrokers.com/en/accounts/fees/CME.php
- NFA2026fee: https://www.nfa.futures.org/rulebooksql/rules.aspx?RuleID=BYLAW+1301&Section=3
- BLS: https://www.bls.gov/schedule/2026/
- FOMC: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- IB/LEAN requirements: https://www.quantconnect.com/docs/v2/lean-cli/live-trading/brokerages/interactive-brokers
