"""Position sizing, ported from reference/position_sizing.py (Decimal, floor only).

Extensions for the bot integration (defaults reproduce the reference):
- `cash` overrides the static `available_cash_eur` (backtest passes current equity);
- `slippage` overrides `slippage_price` (relative slippage profiles);
- margin modes for CFD (`margin_rate`) and futures (`margin_per_contract`).
  With neither set the reference full-cash rule applies.
"""
from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal


def D(x):
    return Decimal(str(x))


def slippage_for(price: float, cfg: dict) -> float:
    if cfg.get("slippage_bps") is not None:
        return price * cfg["slippage_bps"] / 1e4
    return cfg["slippage_price"]


def size(equity, entry, stop, target, direction, cfg, *, cash=None, slippage=None):
    if direction not in (-1, 1) or min(equity, entry, stop, target) <= 0:
        raise ValueError("inputs")
    if direction == -1 and not cfg["short_allowed"]:
        return {"qty": 0, "reason": "SKIP_SHORT_UNSUPPORTED"}
    if direction * (entry - stop) <= 0 or direction * (target - entry) <= 0:
        return {"qty": 0, "reason": "SKIP_INVALID_GEOMETRY"}
    # Entry, stop, target are executable-side prices. No extra spread charge.
    sl_value = cfg["slippage_price"] if slippage is None else slippage
    x, m, sl, f = map(D, (cfg["quote_to_eur"], cfg["multiplier"], sl_value, cfg["fee_rate"]))
    if x <= 0 or m <= 0 or sl < 0 or f < 0:
        raise ValueError("metadata")
    en, st, tp = map(D, (entry, stop, target))
    fixed = D(cfg["fixed_fee_eur"])
    unit_fee = D(cfg["unit_fee_eur"])
    unit = (abs(en - st) + sl) * m * x + f * (en + st + sl) * m * x + unit_fee
    reward = (abs(tp - en) - sl) * m * x - f * (en + tp + sl) * m * x - unit_fee
    budget = D(equity) * min(D(cfg["risk_fraction"]), D(cfg["risk_cap_fraction"]))
    step = D(cfg["lot_step"])
    if step <= 0 or unit <= 0 or fixed < 0 or budget <= fixed:
        return {"qty": 0, "reason": "SKIP_METADATA_OR_BUDGET"}
    available = D(cfg["available_cash_eur"] if cash is None else cash)
    if cfg.get("margin_per_contract") is not None:
        per_unit_cash = D(cfg["margin_per_contract"]) * x + en * m * x * f + unit_fee
    elif cfg.get("margin_rate") is not None:
        per_unit_cash = en * m * x * (D(cfg["margin_rate"]) + f) + unit_fee
    else:
        per_unit_cash = en * m * x * (1 + f) + unit_fee
    raw = min((budget - fixed) / unit, max(D(0), available - fixed) / per_unit_cash)
    q = (raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
    loss = q * unit + fixed
    gain = q * reward - fixed
    if q < D(cfg["min_qty"]) or q * en * m < D(cfg["min_notional"]):
        return {"qty": 0, "reason": "SKIP_MINIMUM_SIZE"}
    if gain / loss < D(cfg["min_net_rr"]):
        return {"qty": 0, "reason": "SKIP_NET_RR"}
    return {"qty": float(q), "risk_eur": float(loss), "reward_eur": float(gain),
            "net_rr": float(gain / loss), "reason": "SIZE_OK"}
