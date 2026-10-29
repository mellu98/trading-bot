# Reject the locked BTCUSDT hourly SMA168 configuration

The predeclared chronological test loses **14.95955 USDT**, including a raw trade-price loss before modeled friction. No parameters were selected or retuned. The real 2026 technical paper roundtrip is excluded completely. No strategy is economically approved.

## One configuration, three separate accounts

Each split starts flat with 1000 virtual USDT and its own original Risk budget. Prior prices are used solely for causal SMA warmup; no pending signals cross split boundaries. Do not pool these accounts into a purported continuous portfolio.

| Split | Trades | Gross before spread/slip | Spread | Slippage | Fees | Net USDT | PF | Expectancy | Hour-close DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Development: Jan–Jun 2025 | 14 | 3.78849 | 0.27875 | 0.27875 | 2.78748 | **0.44352** | 1.0505 | 0.03168 | 14.96146 |
| Validation: Jul–Sep 2025 | 28 | 0.22737 | 0.55651 | 0.55651 | 5.56506 | **-6.45070** | 0.5544 | -0.23038 | 14.86021 |
| Chronological test: Oct–Dec 2025 | 19 | -10.44209 | 0.37645 | 0.37645 | 3.76455 | **-14.95955** | 0.1366 | -0.78734 | 15.03043 |

Test final cash: **985.040449674274708373 USDT**. Its 19 exits are SMA exits, with no actual simulated stop/time exit in this test. Validation has 27 SMA exits and one time exit; development has 14 SMA exits.

No latched risk halts occurred, but risk admission materially constrained coverage: combined initial-cost/risk/size rejections were 74 / 25 / 22 across development / validation / test, with another 1 validation and 5 test consecutive-loss rejections. The inherited path aggregates the initial-admission reasons; do not label all of them as one specific cause without additional instrumentation. An absent halt is NOT an unconstrained trading sample.

## Decision and uncertainty

**REJECT_EXACT_CONFIGURATION**: negative test net fails the frozen absolute criterion. Test N=19 also falls below the minimum 20, PF is below 1.15, and no positive lower confidence bound is supported. Development's tiny positive result is not a selected replacement strategy.

Test marked daily mean: **-0.162604 USDT**. Circular five-day bootstrap, 10,000 replicates, seed 1729, family one: 95% CI **[-0.347469, +0.011686]**, one-sided 95% lower **-0.317492**. Sensitivity block one CI [-0.341292, -0.001371]; block ten [-0.312422, -0.026779]. The primary interval crosses zero: this is a failed economic acceptance test, not proof of a universally negative population mean. Blocks resample observed marked daily equity changes; they do not reconstruct path-dependent risk decisions.

## Data and preregistration

- Parent protocol SHA256: `8230d5ad3d7f0e11133c515020aca348b04656d452735dc530a55aca54304653` — unchanged.
- Code/config/test freeze SHA256: `5a8be80c1541cf2e865b4042d11b6bc92aecf55559afa2a2a19ec5f240aee77d`, before the first historical request and before opening any prices.
- 13 official Binance Vision monthly ZIPs and their original SHA256 CHECKSUM files: December 2024 warmup plus all 12 months of 2025. Total ZIP bytes: **565,780**. Twenty-eight successful public GETs include README and terms; no account, key, purchase or paid request.
- **9504 continuous UTC hourly bars**: 744 warmup + 8760 in 2025. Explicit 2024 milliseconds / 2025 microseconds, original integer timestamps retained, exact integer ns conversion, calendar/inclusive-close/OHLCV validation, no gaps or duplicates. ZIP member paths and sizes checked before decoding; SHA verified before unpacking.
- Normalized dataset SHA256: `0cc25d36104554342a2980af2a119c32f287a0f2636b7d0acbc6c68fb0189771`.
- Two identical frozen-source/data replays produced results SHA256 `e09be315fde5d63e5ae0b304d65f085a90e492443b1c95b29d9d66e2fb1d86d6`. Trade, execution, equity, daily, metric and state files also match byte-for-byte.

The test period was fixed before acquisition and was not previously inspected by this project according to current cache/memory evidence. This is a predeclared historical temporal test, not new future-forward validation. All downloaded periods are now observed and cannot be relabeled as untouched later.

## Existing accounting, explicit assumptions

The offline HistoricalSpot seam calls the existing SpotRuntime entry/protect/fill arithmetic and unchanged original Risk. It binds a process-local historical clock, uses historical fill dates for daily risk, supplies a cycle-local cash origin to the original one-shot PnL assertion, then restores cumulative portfolio accounting. Regression tests prove two roundtrips conserve cash cumulatively. No live module, settings, journal or lifetime budget was changed by research.

Fixed assumptions: long/flat; SMA168 closed-hour cross, next open; 5% frozen stop tick-rounded down; 168-hour deadline; no target/trailing/short; at most 100 USDT initial cash including fee; quantity down to 0.00001 BTC, min notional 5 USDT, current grid modeled rather than certified 2025 exchange metadata. Original Risk uses daily 10 / drawdown 20 USDT, with its default 10 trades/day and 3 consecutive losses frozen before prices.

Trade OHLC is NOT historical bid/ask. The model assumes full spread 2 bp, slippage 1 bp each side and 0.1% USDT-settled fee each side, without BNB discount. Synthetic displayed size is unbounded for this small cash-budget model; volume does not prove queue/fill quality. Gap stops precede pending signal/time exits; intrabar modeled-bid low triggers the stop first and is hour-bound, not a known tick timestamp. Terminal liquidation uses only the last split bar close. Hour-close drawdown excludes unseen intrahour equity paths. No production execution, news or liquidity certification follows from this backtest.

## Reproduce

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
export PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src:reports/binance-spot/research
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -m pytest reports/binance-spot/research/test_research.py tests_local/test_binance_spot.py -q
.venv/bin/python reports/binance-spot/research/runner.py run --tag reproduction-check
```

Use an unused output tag: existing economic journals intentionally cannot be reused. This repeats exactly the frozen configuration, not a new search. Do not repeat freeze or acquisition: preserve the original acquisition/provenance manifest and the already cached checksum-verified archives. No more download is necessary.

## Live observer remains separate

PID **64007**, port **8767**, same technical journal: flat, budget spent, exactly one technical BUY/SELL. Its source hashes were rechecked unchanged by research. Entry eligibility is deliberately intermittent under strict freshness/processing gates. The 595-second transport monitor recorded 22 late processing-delay rejections (max 883.646 ms), three repaired trade gaps, and no 180-second continuous eligible window; neither that window nor uninterrupted transport is claimed PASS. Full qualification is in technical/batched-health-verification.json. No thresholds were loosened to manufacture readiness.

## Attribution and license

Historical data: [Binance Vision](https://data.binance.vision/), [official README](https://github.com/binance/binance-public-data/blob/master/README.md), [public-data terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md). README and terms are preserved with retrieval times and hashes in acquisition.json and data/binance-spot/research/. The data terms specify CC BY-NC-SA 4.0 for the permitted personal, non-production research scope; code MIT licensing does NOT make the data MIT. No commercial, redistribution or live proprietary execution permission is inferred here.
