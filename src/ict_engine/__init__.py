"""ICT research engines integrated into the trading bot (simulation only).

- A1 (engine.py): verbatim port of the ICT_ENGINE_v1 package baseline
  (docs/ict-engine-v1), decision-parity tested against its reference code.
- v2 (engine_v2.py, context.py, arrays.py): the full concept catalog — every
  liquidity pool type, three entry models (reversal, continuation, Silver
  Bullet), FVG/iFVG/OB/breaker/OTE entries, confluence scoring and SMT — with
  a P&L-blind frequency calibration (calibrate.py).

Both run through the same validation protocol (protocol.py): sealed holdout
per market, walk-forward folds, block bootstrap, Holm over the trial registry,
cost stress on the same trades, matched random-entry benchmark, robustness.

No module in this package can place an order. Every engine and simulator
refuses any mode other than "simulation".
"""

STRATEGY_VERSION = "A1-1.0"
MODE = "simulation"
