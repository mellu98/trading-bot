# Decision — no strategy promoted

No tested V2 configuration merits promotion to autonomous paper trading. All120development sessions have been observed, including V1's old holdout. No independent validation has occurred.

The daily-reset research account is useful for covering every session, but removes cross-session risk suspension and is not a deployable strategy. All continuous new-strategy accounts latch the original$500drawdown halt. Dollar drawdown may overshoot the threshold through a gap or next bar; reported minute-close drawdown is not tick-level worst-case risk.

## Economic diagnosis

- MNQ Sweep/MSS:294trades, gross$275, fees$360.42, assumed slippage$294, net−$379.42, PF0.888, expectancy−$1.29/trade. Friction$654.42 exceeds gross. Even eliminating assumed slippage alone leaves−$85.42 after fees.
- MES Sweep/MSS:241trades, gross$68.75, fees$295.20, slippage$602.50, net−$828.95. Positive gross does not survive even fees alone.
- ORB: negative gross already (MNQ−$700; MES−$50), so lower friction alone does not establish an edge under these frozen exits.
- MNQ Sweep/MSS loses in both classified volatility regimes: high−$253.22/130trades; low−$162.64/120trades. The first20sessions are unclassified rather than backdated using future thresholds.
- MNQ Sweep/MSS has only2/6positive20session blocks and2/6positive calendar months. Its5-session-block95%mean-daily CI is[−$8.743,$2.156]; family-adjusted lower bound−$9.861. A CI crossing zero does NOT prove equivalence or positive edge. Moving-block sensitivity1/5/10 remains unsupported.
- Increased slippage to1.5/2ticks each side gives MNQ Sweep/MSS−$526.42/−$673.42. No scenario search was used to select a production model.

These results reject promotion of these exact implementations, not every possible ORB or liquidity/structure hypothesis. The common fixed exits intentionally isolate entry logic and may not capture a range-scaled ORB. Changing exits would create a new hypothesis; it would need a separately frozen specification and fresh independent data, not relabeling these120sessions as unseen.

## Next independent experiment (optional, not a current promotion)

The protocol froze four new instrument/strategy candidates before their V2 results were generated. All four may be falsified together on60prospective full cash sessions with family4correction, minimum60trades/candidate, PF≥1.15, positive stressed net, positive adjusted lower daily mean, at least2/3positive20session blocks, no global risk halt. No winner is selected from current diagnostic returns. See protocol.json and unseen-data-plan.json. No purchase is authorized, and no current quotation for future data is asserted.

Earlier-year data can add regime diversity, but is independent only with verified prior-unseen provenance; absence from local disk alone is insufficient. Strict-news, actual account cost and finer execution validation remain mandatory before any autonomous paper approval, regardless of exploratory results.

## Verification

48local tests passed (27preexisting +21new). Original protected90/37paths and459archivedV1files unchanged; baseline fixed economic outputs reproduce V1 for both instruments/account rules. Independent arithmetic checks cover7968trade rows across36replays,1964signal timing checks,665stop-first collisions (repeated scenarios, not unique trades). Real data are unchanged:93600bars/120sessions.

No agent, data request, purchase, account connection, live order or AI filter was added. Timestral remains optional/off; license eligibility for pinned real weights is unverified. LEAN runtime/native export/broker reconciliation remain unimplemented rather than presented as tested. There is no certified full PITnews calendar; strict replay remains blocked.
