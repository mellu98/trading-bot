"""A1 configuration: frozen baseline, instrument profiles and config hashing.

BASELINE is a verbatim copy of docs/ict-engine-v1/04_ICT_STRATEGY_CONFIG.yaml.
The strategy geometry is never changed by a profile: profiles only supply
venue/instrument metadata and cost assumptions. Any change to a strategy key
creates a new config hash and therefore a new trial in the registry.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from . import MODE, STRATEGY_VERSION

DOCS = Path(__file__).resolve().parents[2] / "docs" / "ict-engine-v1"

# Verbatim baseline from the ICT package (04_ICT_STRATEGY_CONFIG.yaml).
BASELINE = {
    "version": "1.0", "mode": "simulation", "symbol": "SYNTH", "timeframe_seconds": 300,
    "pivot_left": 2, "pivot_right": 2, "structure_lookback": 60, "atr_period": 14,
    "tick_size": 0.01, "sweep_min_atr": 0.05, "sweep_max_atr": 0.5, "sweep_recovery_ticks": 1,
    "mss_buffer_ticks": 1, "mss_ttl_bars": 6, "body_atr_min": 1.0, "body_ratio_min": 0.65,
    "close_extreme_max": 0.2, "fvg_min_atr": 0.1, "fvg_max_atr": 1.0, "fvg_ttl_bars": 1,
    "entry_fraction": 0.5, "order_ttl_bars": 6, "stop_buffer_atr": 0.1, "stop_buffer_spreads": 2,
    "stop_min_atr": 0.2, "stop_max_atr": 3, "min_net_rr": 1.5, "max_spread_atr": 0.1,
    "max_slippage_atr": 0.05, "max_hold_bars": 24, "session_timezone": "America/New_York",
    "session_start": "07:00", "session_end": "11:00", "weekdays": [0, 1, 2, 3, 4],
    "calendar_max_age_seconds": 86400, "news_before_minutes": 30, "news_after_minutes": 30,
    "risk_fraction": 0.0025, "risk_cap_fraction": 0.01, "daily_loss_fraction": 0.02,
    "weekly_loss_fraction": 0.04, "drawdown_fraction": 0.08, "max_consecutive_losses": 3,
    "max_daily_trades": 3, "max_concurrent": 1, "max_aggregate_risk_fraction": 0.01,
    "quote_max_age_seconds": 5, "api_error_limit": 3, "slippage_price": 0.01, "fee_rate": 0.001,
    "fixed_fee_eur": 0, "unit_fee_eur": 0, "quote_to_eur": 1, "multiplier": 1, "lot_step": 0.001,
    "min_qty": 0.001, "min_notional": 5, "available_cash_eur": 500, "short_allowed": False,
    "synthetic_profile": True, "htf_filter": False, "premium_discount_filter": False,
    "daily_bias_filter": False,
}

# Keys added by the bot integration. Defaults reproduce the reference behaviour.
EXTENSION_DEFAULTS = {
    "venue": "SYNTH",
    "account_currency": "EUR",
    "initial_equity": 500,
    "news_enabled": True,          # reference always checks the calendar
    "spread_mode": "context",      # context | fixed | bps | bar
    "spread_price": 0.0,
    "spread_bps": 0.0,
    "slippage_bps": None,          # when set, slippage_price = price * bps / 1e4 per decision
    "margin_rate": None,           # None = full cash (reference); CFD margin as fraction of notional
    "margin_per_contract": None,   # futures margin per contract in account currency
    "sizing_realistic": True,      # False = research-sized account, R metrics only
    "drawdown_policy": "halt",     # halt (spec) | record (research ledger keeps going, logs breach)
}

# Strategy keys: the A1 hypothesis itself. Changing any of them is a new trial.
STRATEGY_KEYS = (
    "timeframe_seconds", "pivot_left", "pivot_right", "structure_lookback", "atr_period",
    "sweep_min_atr", "sweep_max_atr", "sweep_recovery_ticks", "mss_buffer_ticks", "mss_ttl_bars",
    "body_atr_min", "body_ratio_min", "close_extreme_max", "fvg_min_atr", "fvg_max_atr",
    "fvg_ttl_bars", "entry_fraction", "order_ttl_bars", "stop_buffer_atr", "stop_buffer_spreads",
    "stop_min_atr", "stop_max_atr", "min_net_rr", "max_hold_bars", "session_start", "session_end",
    "weekdays", "news_before_minutes", "news_after_minutes",
)

# Geometric parameters perturbed one at a time (+-10/20 %) in the robustness check.
GEOMETRIC_KEYS = (
    "sweep_min_atr", "sweep_max_atr", "body_atr_min", "body_ratio_min", "close_extreme_max",
    "fvg_min_atr", "fvg_max_atr", "entry_fraction", "stop_buffer_atr", "stop_min_atr",
    "stop_max_atr", "min_net_rr",
)

# Instrument / venue profiles. Values marked "assumption" must be re-checked
# against the venue's exchangeInfo / instrument metadata before any paper run.
PROFILES = {
    "synthetic": {},
    "binance-btcusdt-spot": {
        # Spec primary research market: BTC spot, long-only, full cash.
        "symbol": "BTCUSDT", "venue": "binance-spot", "account_currency": "USDT",
        "synthetic_profile": False, "initial_equity": 500, "available_cash_eur": 500,
        "tick_size": 0.01, "lot_step": 0.00001, "min_qty": 0.00001, "min_notional": 5,  # assumption: exchangeInfo filters
        "fee_rate": 0.001,                 # VIP0 spot taker 0.10 %/side, same as the bot's frozen base scenario
        # Slippage on stop/time exits. The bot's frozen 1 bp would make the package's
        # gate (slippage <= 0.05 ATR) reject every bar with ATR < 0.20 %, i.e. most
        # quiet bars, for a cost that a few-hundred-USDT BTCUSDT order does not pay.
        # 0.2 bp (~120 ticks at 60k) stays conservative; stressed 1.5x/2x/3x.
        "slippage_bps": 0.2,
        "spread_mode": "fixed", "spread_price": 0.01,  # assumption: BTCUSDT top of book ~1 tick
        "short_allowed": False, "multiplier": 1, "quote_to_eur": 1,
    },
    "capital-us100-cfd": {
        # Capital.com DEMO native bid/ask bars; spread from data, no commission.
        "symbol": "US100", "venue": "capital-demo-cfd", "account_currency": "USD",
        "synthetic_profile": False, "initial_equity": 5000, "available_cash_eur": 5000,
        "tick_size": 0.1, "lot_step": 0.01, "min_qty": 0.01, "min_notional": 0,  # assumption: replaced by /markets metadata when downloaded
        "fee_rate": 0.0, "unit_fee_eur": 0, "slippage_bps": 0.5,
        "spread_mode": "bar", "short_allowed": True, "margin_rate": 0.05,
        "multiplier": 1, "quote_to_eur": 1,
    },
    "capital-us500-cfd": {
        "symbol": "US500", "venue": "capital-demo-cfd", "account_currency": "USD",
        "synthetic_profile": False, "initial_equity": 5000, "available_cash_eur": 5000,
        "tick_size": 0.1, "lot_step": 0.01, "min_qty": 0.01, "min_notional": 0,
        "fee_rate": 0.0, "unit_fee_eur": 0, "slippage_bps": 0.5,
        "spread_mode": "bar", "short_allowed": True, "margin_rate": 0.05,
        "multiplier": 1, "quote_to_eur": 1,
    },
    "capital-btcusd-cfd": {
        "symbol": "BTCUSD", "venue": "capital-demo-cfd", "account_currency": "USD",
        "synthetic_profile": False, "initial_equity": 5000, "available_cash_eur": 5000,
        "tick_size": 0.01, "lot_step": 0.0001, "min_qty": 0.0001, "min_notional": 0,
        "fee_rate": 0.0, "unit_fee_eur": 0, "slippage_bps": 1.0,
        "spread_mode": "bar", "short_allowed": True, "margin_rate": 0.5,
        "multiplier": 1, "quote_to_eur": 1,
    },
    "cme-mnq": {
        # Spec benchmark only. Integer contracts: realistic sizing needs a large
        # account, so this profile is research-sized (R metrics, not account P&L).
        "symbol": "MNQ", "venue": "cme", "account_currency": "USD", "synthetic_profile": False,
        "initial_equity": 100000, "available_cash_eur": 100000, "sizing_realistic": False,
        "tick_size": 0.25, "multiplier": 2, "lot_step": 1, "min_qty": 1, "min_notional": 0,
        "fee_rate": 0.0, "unit_fee_eur": 1.22,  # bot's real-simulation config: (0.25+0.35+0.01)*2 per contract round trip
        "slippage_price": 0.25, "spread_mode": "fixed", "spread_price": 0.25,
        "short_allowed": True, "margin_per_contract": 2500, "quote_to_eur": 1,
    },
    "cme-mes": {
        "symbol": "MES", "venue": "cme", "account_currency": "USD", "synthetic_profile": False,
        "initial_equity": 100000, "available_cash_eur": 100000, "sizing_realistic": False,
        "tick_size": 0.25, "multiplier": 5, "lot_step": 1, "min_qty": 1, "min_notional": 0,
        "fee_rate": 0.0, "unit_fee_eur": 1.22,
        "slippage_price": 0.25, "spread_mode": "fixed", "spread_price": 0.25,
        "short_allowed": True, "margin_per_contract": 1500, "quote_to_eur": 1,
    },

    # Capital.com DEMO FX CFDs, native bid/ask. Lot step, minimum size, margin and
    # tick are replaced by the /markets metadata saved at download time.
    "capital-eurusd-cfd": {
        "symbol": "EURUSD", "venue": "capital-demo-cfd", "account_currency": "USD",
        "synthetic_profile": False, "initial_equity": 5000, "available_cash_eur": 5000,
        "tick_size": 0.00001, "lot_step": 1, "min_qty": 100, "min_notional": 0,  # assumption until metadata
        "fee_rate": 0.0, "unit_fee_eur": 0, "slippage_bps": 0.3,  # ~0.3 pip on stop/time exits
        "spread_mode": "bar", "short_allowed": True, "margin_rate": 0.0333,
        "multiplier": 1, "quote_to_eur": 1,
    },
    "capital-gbpusd-cfd": {
        "symbol": "GBPUSD", "venue": "capital-demo-cfd", "account_currency": "USD",
        "synthetic_profile": False, "initial_equity": 5000, "available_cash_eur": 5000,
        "tick_size": 0.00001, "lot_step": 1, "min_qty": 100, "min_notional": 0,
        "fee_rate": 0.0, "unit_fee_eur": 0, "slippage_bps": 0.3,
        "spread_mode": "bar", "short_allowed": True, "margin_rate": 0.0333,
        "multiplier": 1, "quote_to_eur": 1,
    },
    "capital-audusd-cfd": {
        "symbol": "AUDUSD", "venue": "capital-demo-cfd", "account_currency": "USD",
        "synthetic_profile": False, "initial_equity": 5000, "available_cash_eur": 5000,
        "tick_size": 0.00001, "lot_step": 1, "min_qty": 100, "min_notional": 0,
        "fee_rate": 0.0, "unit_fee_eur": 0, "slippage_bps": 0.3,
        "spread_mode": "bar", "short_allowed": True, "margin_rate": 0.0333,
        "multiplier": 1, "quote_to_eur": 1,
    },
    # Full-size CME contracts (24h data via CSV). Research-sized accounts: read R only.
    "cme-nq": {
        "symbol": "NQ", "venue": "cme", "account_currency": "USD", "synthetic_profile": False,
        "initial_equity": 1000000, "available_cash_eur": 1000000, "sizing_realistic": False,
        "tick_size": 0.25, "multiplier": 20, "lot_step": 1, "min_qty": 1, "min_notional": 0,
        "fee_rate": 0.0, "unit_fee_eur": 4.50,  # assumption: retail all-in round trip per contract
        "slippage_price": 0.25, "spread_mode": "fixed", "spread_price": 0.25,
        "short_allowed": True, "margin_per_contract": 20000, "quote_to_eur": 1,
    },
    "cme-es": {
        "symbol": "ES", "venue": "cme", "account_currency": "USD", "synthetic_profile": False,
        "initial_equity": 1000000, "available_cash_eur": 1000000, "sizing_realistic": False,
        "tick_size": 0.25, "multiplier": 50, "lot_step": 1, "min_qty": 1, "min_notional": 0,
        "fee_rate": 0.0, "unit_fee_eur": 4.50,
        "slippage_price": 0.25, "spread_mode": "fixed", "spread_price": 0.25,
        "short_allowed": True, "margin_per_contract": 14000, "quote_to_eur": 1,
    },
}

# Asset class per profile (engine v2 only: A1 configs and hashes are unchanged).
ASSET_CLASS = {
    "synthetic": "index", "binance-btcusdt-spot": "crypto", "capital-btcusd-cfd": "crypto",
    "capital-us100-cfd": "index", "capital-us500-cfd": "index",
    "capital-eurusd-cfd": "fx", "capital-gbpusd-cfd": "fx", "capital-audusd-cfd": "fx",
    "cme-mnq": "future", "cme-mes": "future", "cme-nq": "future", "cme-es": "future",
}

# SMT companion: correlated market compared at every reversal sweep.
COMPANION = {"US100": "US500", "US500": "US100", "EURUSD": "GBPUSD", "GBPUSD": "EURUSD",
             "AUDUSD": "EURUSD", "MNQ": "MES", "MES": "MNQ", "NQ": "ES", "ES": "NQ"}

# ---------------------------------------------------------------- engine v2
# "Full" ICT engine (docs/ict-engine-v1/13 concept catalog). Every number is a
# project convention (P), not an ICT attribution. Windows: (decide_from,
# decide_until, flat_at) in New York time.
_INDEX_PRESET = {
    "windows": [["07:00", "11:00", "12:00"], ["13:30", "15:30", "16:00"]],
    "killzones": [["08:30", "11:00"], ["13:30", "16:00"]],
    "silver_bullet_windows": [["10:00", "11:00"], ["14:00", "15:00"]],
}
_FX_PRESET = {
    "windows": [["02:00", "05:00", "08:00"], ["07:00", "11:00", "12:00"]],
    "killzones": [["02:00", "05:00"], ["07:00", "10:00"]],
    "silver_bullet_windows": [["03:00", "04:00"], ["10:00", "11:00"]],
}
V2_PRESETS = {"index": _INDEX_PRESET, "future": _INDEX_PRESET, "fx": _FX_PRESET, "crypto": _INDEX_PRESET}

V2_DEFAULTS = {
    "engine": "v2",
    "version": "ict2-1.0",
    "asset_class": "index",
    "sessions": {"asia": ["20:00", "24:00"], "london": ["02:00", "05:00"], "nyam": ["07:00", "11:00"]},
    "models": ["reversal", "continuation", "silver_bullet"],
    "pool_types": ["swing", "equal", "h1", "pd", "pw", "asia", "london", "nyam"],
    "equal_tolerance_atr": 0.05,
    "equal_min_separation": 3,
    "equal_lookback_mult": 3,
    "h1_pivot": 2,
    "h1_pool_hours": 120,
    "pd_arrays": ["fvg", "ifvg", "breaker", "ob", "ote"],
    "leg_max_bars": 24,
    "ob_lookback": 5,
    "breaker_lookback": 10,
    "ifvg_lookback": 20,
    "ifvg_retest_bars": 6,
    "ote_low": 0.62,
    "ote_high": 0.79,
    "ote_entry": 0.705,
    "target_mode": "nearest",      # nearest (spec: never skip an obstacle) | nearest_rr | fixed_rr
    "fixed_rr": 2.0,
    "min_confluence": 0,
    "sb_bias": "either",           # h1 | daily | either (non-zero and not contradicting)
    "cont_pullback_z": 0.5,
    "max_cost_risk": 0.25,         # (spread + slippage + fees) / stop distance
    "v2_max_spread_atr": None,     # optional legacy gate; off by default
    "no_entry_before_flat_minutes": 30,
    "max_hold_bars": 48,
    "smt_enabled": True,
}

V2_STRATEGY_KEYS = tuple(k for k in V2_DEFAULTS if k not in ("engine", "version", "asset_class", "smt_enabled")) + (
    "windows", "killzones", "silver_bullet_windows")

# Cost scenarios (protocol 07 stress): multipliers on fees and slippage.
SCENARIOS = {
    "base": {"fees": 1.0, "slippage": 1.0},
    "costs_1.5x": {"fees": 1.5, "slippage": 1.5},
    "costs_2x": {"fees": 2.0, "slippage": 2.0},
    "slippage_3x": {"fees": 1.0, "slippage": 3.0},
}


V2_VERSION = "ICT2-1.0"


def build(profile: str = "synthetic", overrides: dict | None = None, scenario: str = "base",
          engine: str = "a1") -> dict:
    """Build a frozen config. engine="a1" reproduces the package baseline exactly;
    engine="v2" adds the full-ICT keys and the asset-class windows on top."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; available: {sorted(PROFILES)}")
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    if engine not in ("a1", "v2"):
        raise ValueError("engine must be a1 or v2")
    cfg = copy.deepcopy(BASELINE)
    cfg.update(copy.deepcopy(EXTENSION_DEFAULTS))
    cfg.update(copy.deepcopy(PROFILES[profile]))
    cfg["profile"] = profile
    if engine == "v2":
        asset = ASSET_CLASS.get(profile, "index")
        cfg.update(copy.deepcopy(V2_DEFAULTS))
        cfg["asset_class"] = asset
        cfg.update(copy.deepcopy(V2_PRESETS[asset]))
        if asset == "crypto":
            cfg["weekdays"] = [0, 1, 2, 3, 4, 5, 6]
    for key, value in (overrides or {}).items():
        if key not in cfg:
            raise ValueError(f"unknown config key {key!r}")
        cfg[key] = value
    mult = SCENARIOS[scenario]
    cfg["scenario"] = scenario
    cfg["fee_rate"] = cfg["fee_rate"] * mult["fees"]
    cfg["unit_fee_eur"] = cfg["unit_fee_eur"] * mult["fees"]
    cfg["fixed_fee_eur"] = cfg["fixed_fee_eur"] * mult["fees"]
    cfg["slippage_price"] = cfg["slippage_price"] * mult["slippage"]
    if cfg["slippage_bps"] is not None:
        cfg["slippage_bps"] = cfg["slippage_bps"] * mult["slippage"]
    validate(cfg)
    return cfg


def validate(cfg: dict) -> None:
    if cfg["mode"] != MODE:
        raise ValueError("simulation only: no live mode exists")
    if any(cfg[k] for k in ("htf_filter", "premium_discount_filter", "daily_bias_filter")):
        raise ValueError("optional HTF/premium/daily-bias filters are specified but not implemented")
    if cfg["fvg_ttl_bars"] != 1:
        raise ValueError("A1 requires the FVG on the bar immediately after the MSS")
    if cfg.get("engine") == "v2":
        unknown = set(cfg["models"]) - {"reversal", "continuation", "silver_bullet"}
        if unknown or not cfg["models"]:
            raise ValueError(f"unknown models {sorted(unknown)}")
        unknown = set(cfg["pd_arrays"]) - {"fvg", "ifvg", "breaker", "ob", "ote"}
        if unknown or not cfg["pd_arrays"]:
            raise ValueError(f"unknown pd_arrays {sorted(unknown)}")
        unknown = set(cfg["pool_types"]) - {"swing", "equal", "h1", "pd", "pw", "asia", "london", "nyam"}
        if unknown:
            raise ValueError(f"unknown pool_types {sorted(unknown)}")
        if cfg["target_mode"] not in ("nearest", "nearest_rr", "fixed_rr"):
            raise ValueError("target_mode must be nearest|nearest_rr|fixed_rr")
        if cfg["sb_bias"] not in ("h1", "daily", "either"):
            raise ValueError("sb_bias must be h1|daily|either")
        for w in cfg["windows"]:
            if not (len(w) == 3 and w[0] < w[1] <= w[2]):
                raise ValueError(f"window {w} must be [start, end, flat] with start < end <= flat")
    if cfg["spread_mode"] not in ("context", "fixed", "bps", "bar"):
        raise ValueError("spread_mode must be context|fixed|bps|bar")
    if cfg["drawdown_policy"] not in ("halt", "record"):
        raise ValueError("drawdown_policy must be halt|record")
    if cfg["risk_fraction"] > cfg["risk_cap_fraction"] or cfg["risk_cap_fraction"] > 0.01:
        raise ValueError("risk_fraction must stay <= risk_cap_fraction <= 1 %")
    for key in ("tick_size", "lot_step", "multiplier", "quote_to_eur", "initial_equity"):
        if not cfg[key] > 0:
            raise ValueError(f"{key} must be positive")


def version_of(cfg: dict) -> str:
    return V2_VERSION if cfg.get("engine") == "v2" else STRATEGY_VERSION


def config_hash(cfg: dict) -> str:
    canonical = json.dumps({"strategy_version": version_of(cfg), **cfg}, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def strategy_hash(cfg: dict) -> str:
    """Hash of the hypothesis only (strategy keys), independent of venue and costs."""
    keys = STRATEGY_KEYS + (V2_STRATEGY_KEYS if cfg.get("engine") == "v2" else ())
    part = {k: cfg[k] for k in keys}
    canonical = json.dumps({"strategy_version": version_of(cfg), **part}, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def parse_overrides(items: list[str] | None) -> dict:
    """Parse CLI `key=value` pairs; values are JSON when possible (numbers, bools, lists)."""
    out = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"override {item!r} must be key=value")
        key, raw = item.split("=", 1)
        try:
            out[key.strip()] = json.loads(raw)
        except json.JSONDecodeError:
            out[key.strip()] = raw
    return out


def baseline_matches_package() -> bool:
    """True when BASELINE equals the shipped 04 config (guards against silent drift)."""
    path = DOCS / "04_ICT_STRATEGY_CONFIG.yaml"
    if not path.exists():
        return False
    return json.loads(path.read_text()) == BASELINE
