# BTC 4h breakout: inconclusive, not promoted

One frozen configuration produced positive Jan–Sep 2026 historical test PnL, but failed its preregistered quarterly stability and uncertainty requirements. No forward strategy, parameter rescue or financial approval is enabled.

## Measured outcomes

| Period/scenario | Trades | Net USDT | Profit factor | Hour-close MTM drawdown USDT |
|---|---:|---:|---:|---:|
| observed_development/base | 38 | -4.15169358 | 0.82956 | 10.11324 |
| observed_development/adverse | 38 | -7.31721689 | 0.70695 | 10.05857 |
| observed_development/severe | 39 | -11.75839917 | 0.56235 | 13.70780 |
| reserved_test/base | 26 | +7.46356876 | 1.55765 | 11.69840 |
| reserved_test/adverse | 26 | +4.05591054 | 1.29456 | 12.74268 |
| reserved_test/severe | 27 | -1.40460377 | 0.91371 | 13.66870 |

Test base: raw gross 9.999720898419841984198419854; modeled spread 0.2113461851298419841984198421, slippage 0.2113460851326330000000000000, fees 2.113459872488858671000000; net **7.463568755668508329000000**; final cash 1007.463568755668508329000000. Expectancy 0.28706034/trade; win rate 34.62%. No Risk rejections or halts. 11 stop exits have only an hourly time bound.

Only one positive test quarter: Q1 -2.41233277, Q2 -3.69782851, Q3 +13.57373004 USDT (required at least two). Circular 5-day bootstrap, 10000 replicates, seed1729: mean daily +0.02733908, 95% interval [-0.06302074563108129, 0.16878065157566743], one-sided95 lower -0.05291423 (required positive). Blocks1/10 sensitivity in metrics, not a selection exercise.

Matched base Buy & Hold: net -4.780054831335324453000000, hour-close drawdown 44.42920455; it invests100 cash including entry fee and leaves900 idle, but deliberately ignores active1USDT/10daily/20drawdown controls. Paired daily strategy-minus-BH uncertainty is in results.json. Cash comparator has0 net/0 operations.

## Scope and reproducibility

Parent hypothesis frozen before new historical acquisition; implementation/tests frozen and parent-reviewed before any2026 archive acquired/opened. Eight synthetic tests passed first. Strategy reuses original SpotRuntime entry/fill/protect/cash with historical-clock/cycle seam, original Risk unchanged. Exactly one4h20-high/10-low strict channel configuration, ATR14 arithmetic2x fixed stop,1USDT all-in initial modeled loss,100 entry cash including fee; noTP/short/trailing/time exit. Original Spot step.00001/tick.01/minnotional5 are research assumptions, not point-in-time exchange certification. Gap losses can exceed1USDT. Cost stress scenarios fully resimulate sizing/admission/path.

22 monthly official ZIP/CHECKSUM pairs: 16056 contiguous native1h bars,4014 complete UTC4h buckets;744 Dec2024 millisecond warmup +8760 observed2025 microsecond hours +6552 Jan–Sep2026 microsecond test hours. Original timestamp integers retained. No gaps/duplicates.2025 descriptive development was already observed;2026 is project-unseen historical, NOT prospective future validation. Both are now observed. No missing-period substitution.

Historical trade OHLC is not measured historical bid/ask. Base fees10bps/side, slippage1bp/side, assumed fullspread2bps. Adverse15/5/10bps; severe20/10/20bps. Synthetic displayed size is not evidence of historical queue/liquidity. Stop-only native1h low checks cannot reconstruct intrabar sequence/tick execution; stop timestamps are hour bounds. No exitbar extrema are asserted as realized MFE/MAE. Exposure hours are upper bounds. Hour-close liquidation-reserved DD is separately reported from original Risk sampled-mark DD.

Binance Vision attribution; data CC BY-NC-SA4.0, purely personal noncommercial nonproduction research. Preserved README/terms and retrieval provenance are referenced in acquisition.json. CodeMIT does not imply dataMIT. No accounts, private API, keys, data payment or remote orders. The prior technical live-quote roundtrip is excluded.

Run1 and run2: all73 report artifacts byte-identical. Parent independently checked41 provenance/accounting/reproducibility conditions. Cash conservation is exact Decimal equality. Raw-gross minus modeled costs can differ from net by <=5.87e-26USDT when the stop-to-raw reference bridge is repeating at Decimal28 precision; declared decomposition tolerance is1e-20USDT, not an exact algebraic equality claim. See parent-verification.json. No parameters/source changes after viewing test prices.

```sh
PYTHONPATH=src .venv/bin/python -m pytest -q reports/binance-spot/breakout-4h/test_breakout.py
PYTHONPATH=src .venv/bin/python reports/binance-spot/breakout-4h/runner.py run --tag run-3
```
A fresh tag prevents overwriting any earlier journal; replay denies network. Cached archives/checksums are reverified before unpacking.

| Identity | SHA256 |
|---|---|
| Parent protocol | 70bea1510b04f67cfb65db7881ed6319534fbf009b71b514afd07d49918fd3c4 |
| Execution freeze | 258d555a0b83f8a389e34fe8cc0222bb56fdc4ac238896e0b36041611e4a9c48 |
| Normalized dataset | a32da0e732d8eb1f271e3e55ba42ec916e6fbfc13a68e293e09002d9801880ac |
| Both results.json | b052317d22ad203cd3e25e6a48859ffa35510d58b108bd2be1194e1aea221af0 |

## Boundary

No live observer, paper.sqlite budget or Runtime/Risk change is part of this research. Rollback boundary: remove this isolated report/runner and separate data/binance-spot/breakout-4h cache, without touching technical or rejected-SMA evidence. No Git repository/commits; gentle-ai unavailable and CodeGraph NotInitialized, targeted fallback. skill_resolution: paths-injected.
