# Strategy research V2 — observed-sample exploration

All120sessions were already observed. No result here is independent out-of-sample evidence. News filter OFF; strict mode blocked. Fixed exits intentionally isolate candidate generators, not all possible ORB/sweep implementations. No parameter optimization.

## Comparable net results

|Instrument|Strategy|Account|Trades|Gross USD|Fees USD|Slip USD|Net USD|PF|Expectancy USD|DD USD|Ambiguous|
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|MNQ|vwap_v1_fixed|continuous|65|-350.00|80.60|65.00|-495.60|0.457|-7.62|505.92|9|
|MNQ|vwap_v1_fixed|daily_reset_diagnostic|627|-1844.00|769.00|627.00|-3240.00|0.604|-5.17|3400.58|75|
|MNQ|orb|continuous|68|-352.00|84.18|68.00|-504.18|0.468|-7.41|505.78|19|
|MNQ|orb|daily_reset_diagnostic|176|-700.00|215.94|176.00|-1091.94|0.539|-6.20|1093.54|35|
|MNQ|sweep_mss|continuous|182|43.00|223.78|182.00|-362.78|0.830|-1.99|511.86|21|
|MNQ|sweep_mss|daily_reset_diagnostic|294|275.00|360.42|294.00|-379.42|0.888|-1.29|650.08|23|
|MES|vwap_v1_fixed|continuous|77|-192.50|95.48|192.50|-480.48|0.391|-6.24|504.25|6|
|MES|vwap_v1_fixed|daily_reset_diagnostic|633|-188.75|776.70|1582.50|-2547.95|0.566|-4.03|2571.72|23|
|MES|orb|continuous|142|28.75|174.36|355.00|-500.61|0.609|-3.53|500.61|4|
|MES|orb|daily_reset_diagnostic|173|-50.00|212.18|432.50|-694.68|0.567|-4.02|694.68|6|
|MES|sweep_mss|continuous|51|-300.00|63.24|127.50|-490.74|0.188|-9.62|503.25|1|
|MES|sweep_mss|daily_reset_diagnostic|241|68.75|295.20|602.50|-828.95|0.617|-3.44|862.84|5|

## Robustness (daily-reset diagnostic, not deployable portfolio)

|Arm|Positive20session blocks /6|1.5tick net|2tick net|Mean daily95%CI block5|Adjusted lower block1/5/10|
|---|---:|---:|---:|---|---|
|MNQ/vwap_v1_fixed|0|-3553.50|-3867.00|[-33.621, -20.081]|[-35.292, -35.387, -34.907]|
|MNQ/orb|1|-1179.94|-1267.94|[-14.016, -3.893]|[-14.611, -15.181, -15.072]|
|MNQ/sweep_mss|2|-526.42|-673.42|[-8.743, 2.156]|[-10.063, -9.861, -9.826]|
|MES/vwap_v1_fixed|0|-3339.20|-4130.45|[-27.97, -13.135]|[-27.191, -29.05, -29.314]|
|MES/orb|0|-910.93|-1127.18|[-8.335, -3.272]|[-9.422, -8.881, -8.433]|
|MES/sweep_mss|1|-1130.20|-1431.45|[-10.444, -2.877]|[-11.12, -11.19, -11.794]|

## Interpretation and limitations

Daily reset removes cross-day global halt ONLY for descriptive signal coverage; continuous accounts retain original protection. One contract per arm means unequal dollar stops (MNQ$16 / MES$10); netR is also supplied. Minute-close drawdown understates possible tick-level excursions. Stop-first handles collisions conservatively; trade count/ambiguity are explicit. Costs are scenarios, not actual broker statements. Bootstrap cannot repair strategy-design selection bias on observed data; subgroup results are not independently tested filters.

Full session/month/regime/time/side breakdowns, paired differences and cost replays are in results.json; detailed orders, signals, brackets, trades and equity in results/. No evidence licenses live or autonomous paper trading.

## Frozen next test and data plan

future-independent-test.json freezes all four new instrument-strategy candidates and60prospective full cash sessions after2026-10-26. No purchases authorized. Require official exact-scope cost quote and cache exclusion before manual acquisition approval. A disjoint earlier-year replication needs proof it has never been inspected. If any definition changes, a new unseen test is required.

## Operational blockers

Complete point-in-time macro/news archive remains uncertified: strict mode blocks all four new arms. Timestral stays disabled; modifiedMIT revenue eligibility is not attested, so no weights/inference claim. LEAN runtime/native fills, broker paper adapter, reconnect/reconciliation and tick-level execution validation remain pending; no account or live connection was added.

## Definitions and sources

No ICT2022archive found locally. Sweep/MSS is our price-only hypothesis, not an attributed ICT implementation or proof of real liquidity. Our exact parameters/fixed exits are research choices, not claims made by these sources:
- [Bulkowski opening-range breakout chapter](https://onlinelibrary.wiley.com/doi/10.1002/9781119203933.ch11): general range breakout concept.
- [Fidelity pivot highs/lows](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/pivot-points-high-low): bars on both sides; implemented with delayed confirmation.
- [Fidelity false/failed breakouts](https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/learning-center/Idenitfying-Chart-Patterns.pdf): conceptual failed breakout; our exact state machine is defined in protocol.json.

## Reproduce

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
./run-research-v2.sh
./run-research-v2.sh --tests
```

V1 recoverable snapshot: reports/archive/vwap-v1.tar.gz with per-file and archive SHA256 in vwap-v1-manifest.json. Sources, old reports, configs, raw cache and normalized dataset included. Runtime environment is pinned by archived locks, not bundled virtual environments.
