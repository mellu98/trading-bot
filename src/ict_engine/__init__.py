"""ICT Engine A1 — sweep -> MSS/displacement -> FVG, integrated into the trading bot.

Research / simulation only. Ported from the ICT_ENGINE_v1 package
(docs/ict-engine-v1) and extended with the parts a real historical test needs:
data loaders, segment resets, session/news/TTL cancels, a risk ledger, the
validation protocol (splits, sealed holdout, bootstrap, Holm, cost stress) and
a matched random-entry benchmark.

No module in this package can place an order. Every engine and simulator
refuses any mode other than "simulation".
"""

STRATEGY_VERSION = "A1-1.0"
MODE = "simulation"
