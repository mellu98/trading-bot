# Real-data technical replay (simulation only)

| Metric | Value |
|---|---:|
| trades | 0 |
| gross | 0 |
| fees | 0 |
| execution_cost | 0 |
| net | 0 |
| win_rate | None |
| profit_factor | None |
| max_drawdown_mark_to_minute_close | 0.0 |
| ambiguous_intrabar_trades | 0 |

## Limitations
- Five sessions only, not statistical validation or OOS advantage
- One-minute typical-price VWAP, not trade-by-trade VWAP
- Stops before targets if both touched; precise intrabar order unknown
- Minute-close mark-to-market drawdown, not tick-level maximum drawdown
- VWAP exit variant freezes signal-time VWAP rounded to nearest tick; not a moving VWAP target
- Public fee schedule scenario, not account-specific verified historical charges
- Assumed spread/slippage/zero extra bar-close latency, no order-book fills
- Scoped current official news schedules, not archived point-in-time calendar
- Stricter portfolio one-position cap; deterministic MNQ-first tie priority
- This custom replay is not LEAN or an Interactive Brokers paper execution certification
