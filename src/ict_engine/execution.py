"""Conservative OHLC execution simulator (ported from reference/execution_adapter.py).

Reference rules kept: no fill on the generating bar, limit needs >= 1 tick
penetration on the executable side, stop before target in the same bar, no
target credited on the entry bar, gap through stop filled at the worse open
minus slippage, time exit after max_hold_bars, one exposure at a time,
idempotent creation with ID-conflict detection.

Added (normative in spec 01/05/06, missing from the reference harness):
- CANCEL_SESSION_END: pending order cancelled once a bar starts at/after the cutoff;
- SESSION_END exit: open position closed at the close of the bar ending at the cutoff;
- CANCEL_TARGET_CONSUMED: pending order cancelled if price reaches the target first;
- CANCEL_DATA_INVALID on a data gap (positions keep their stop; next bar decides);
- optimistic=True: target-first on same-bar ambiguity, reported only as a bound.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .sizing import slippage_for

# Signal metadata copied onto the trade record (engine v2 audit fields).
PASS_THROUGH = ("model", "score", "confluence", "array", "pool_type", "smt")


class SimulationAdapter:
    def __init__(self, cfg, *, optimistic=False):
        if cfg["mode"] != "simulation":
            raise ValueError("simulation only")
        self.cfg = cfg
        self.optimistic = optimistic
        self.tz = ZoneInfo(cfg["session_timezone"])
        self.orders = {}
        self.active = {}  # PENDING/OPEN only; keeps per-bar work O(1) on long runs
        self.fills = []
        self.cancels = []
        self.new_fills = []

    # ------------------------------------------------------------ lifecycle
    def create(self, signal):
        sid = signal["signal_id"]
        if sid in self.orders:
            if self.orders[sid]["signal"] != signal:
                raise ValueError("ID conflict")
            return self.orders[sid]
        if self.exposure():
            raise ValueError("one exposure only")
        if signal["qty"] <= 0:
            raise ValueError("qty")
        row = {"signal": dict(signal), "status": "PENDING", "held": 0,
               "known_at": datetime.fromisoformat(signal["known_at"]),
               "expires_at": datetime.fromisoformat(signal["expires_at"]),
               "flat_at": datetime.fromisoformat(signal["flat_at"]) if signal.get("flat_at") else None}
        self.orders[sid] = row
        self.active[sid] = row
        return row

    def exposure(self):
        return bool(self.active)

    def cancel(self, sid, reason="CANCEL_REQUESTED", at=None):
        x = self.orders[sid]
        if x["status"] == "PENDING":
            x["status"] = "CANCELLED"
            x["cancel_reason"] = reason
            self.active.pop(sid, None)
            self.cancels.append({"signal_id": sid, "reason": reason, "at": at})
        return x

    def on_gap(self, at=None):
        for sid, x in list(self.active.items()):
            if x["status"] == "PENDING":
                self.cancel(sid, "CANCEL_DATA_INVALID", at)

    def reconcile(self):
        return list(self.orders.values())

    def flatten(self, b, spread, reason="ROLL"):
        """Close every open position at bar b's close (market, with slippage); cancel pending orders.

        Used at a futures roll: prices of the next contract must never settle the old one.
        """
        out = []
        c = self.cfg
        for sid, x in list(self.active.items()):
            if x["status"] == "PENDING":
                self.cancel(sid, "CANCEL_" + reason, b.ts.isoformat())
                continue
            s, d = x["signal"], x["signal"]["direction"]
            side = -spread / 2 if d == 1 else spread / 2
            slip = s["slippage"] if "slippage" in s else slippage_for(s["entry"], c)
            exit_price = b.c + side - d * slip
            q, m, fx = s["qty"], c["multiplier"], c["quote_to_eur"]
            gross = d * (exit_price - x["entry_fill"]) * q * m * fx
            fees = c["fee_rate"] * (exit_price + x["entry_fill"]) * q * m * fx + c["fixed_fee_eur"] + q * c["unit_fee_eur"]
            result = {
                "signal_id": sid, "direction": d, "known_at": s["known_at"], "filled_at": x["filled_at"],
                "exit_at": b.ts.isoformat(), "entry": x["entry_fill"], "stop": s["stop"], "target": s["target"],
                "exit_price": exit_price, "reason": reason, "qty": q, "held_bars": x["held"],
                "gross_eur": gross, "fees_eur": fees, "net_eur": gross - fees, "risk_eur": s["risk_eur"],
                "R": (gross - fees) / s["risk_eur"] if s["risk_eur"] > 0 else 0.0,
                "ambiguous_bar": False, "atr_lag": s.get("atr_lag"), "slippage": slip,
                **{k: s[k] for k in PASS_THROUGH if k in s},
            }
            x["status"] = "CLOSED"
            self.active.pop(sid, None)
            self.fills.append(result)
            out.append(result)
        return out

    # ------------------------------------------------------------ per bar
    def _clock(self, ts):
        local = ts.astimezone(self.tz)
        return f"{local.hour:02d}:{local.minute:02d}"

    def on_bar(self, b, spread):
        out = []
        self.new_fills = []
        c = self.cfg
        tick = c["tick_size"]
        end_clock = self._clock(b.ts)
        start_clock = self._clock(b.ts - timedelta(seconds=c["timeframe_seconds"]))
        cutoff = c["session_end"]
        # Positions exist only inside the session window, so the first bar ending
        # at/after the cutoff closes them; a bar starting at/after it cancels orders.
        session_reaches = end_clock >= cutoff
        session_starts_after = start_clock >= cutoff
        bar_start = b.ts - timedelta(seconds=c["timeframe_seconds"])
        for sid, x in list(self.active.items()):
            s = x["signal"]
            d = s["direction"]
            new = False
            if b.ts <= x["known_at"]:
                continue
            flat = x.get("flat_at")
            if flat is not None:  # per-signal flat time (multi-window engines)
                reaches_cutoff, starts_after_cutoff = b.ts >= flat, bar_start >= flat
            else:
                reaches_cutoff, starts_after_cutoff = session_reaches, session_starts_after
            if x["status"] == "PENDING":
                if b.ts >= x["expires_at"]:
                    x["status"] = "EXPIRED"
                    self.active.pop(sid, None)
                    self.cancels.append({"signal_id": sid, "reason": "CANCEL_EXPIRED", "at": b.ts.isoformat()})
                    continue
                if starts_after_cutoff:
                    self.cancel(sid, "CANCEL_SESSION_END", b.ts.isoformat())
                    continue
                # Entry ask for long, bid for short; require penetration by one tick.
                touched = b.l + spread / 2 <= s["entry"] - tick if d == 1 else b.h - spread / 2 >= s["entry"] + tick
                if not touched:
                    consumed = b.h - spread / 2 >= s["target"] if d == 1 else b.l + spread / 2 <= s["target"]
                    if consumed:
                        self.cancel(sid, "CANCEL_TARGET_CONSUMED", b.ts.isoformat())
                    continue
                x["status"] = "OPEN"
                x["entry_fill"] = s["entry"]
                x["filled_at"] = b.ts.isoformat()
                self.new_fills.append(sid)
                new = True
            if x["status"] != "OPEN":
                continue
            x["held"] += 1
            side = -spread / 2 if d == 1 else spread / 2
            lo, hi, op = b.l + side, b.h + side, b.o + side
            slip = s["slippage"] if "slippage" in s else slippage_for(s["entry"], c)
            hitstop = lo <= s["stop"] if d == 1 else hi >= s["stop"]
            hittarget = hi >= s["target"] + tick if d == 1 else lo <= s["target"] - tick
            ambiguous = hitstop and hittarget
            exit_price = None
            why = None
            if self.optimistic and hittarget and (hitstop or new):
                exit_price, why = s["target"], "TARGET"
            elif hitstop:
                exit_price = (min(op, s["stop"]) if d == 1 else max(op, s["stop"])) - d * slip
                why = "STOP"
            elif hittarget and not new:
                exit_price, why = s["target"], "TARGET"
            elif x["held"] >= c["max_hold_bars"]:
                exit_price, why = b.c + side - d * slip, "TIME"
            elif reaches_cutoff:
                exit_price, why = b.c + side - d * slip, "SESSION_END"
            if exit_price is not None:
                q = s["qty"]
                m = c["multiplier"]
                fx = c["quote_to_eur"]
                gross = d * (exit_price - x["entry_fill"]) * q * m * fx
                fees = c["fee_rate"] * (exit_price + x["entry_fill"]) * q * m * fx + c["fixed_fee_eur"] + q * c["unit_fee_eur"]
                net = gross - fees
                result = {
                    "signal_id": sid, "direction": d, "known_at": s["known_at"], "filled_at": x["filled_at"],
                    "exit_at": b.ts.isoformat(), "entry": x["entry_fill"], "stop": s["stop"], "target": s["target"],
                    "exit_price": exit_price, "reason": why, "qty": q, "held_bars": x["held"],
                    "gross_eur": gross, "fees_eur": fees, "net_eur": net, "risk_eur": s["risk_eur"],
                    "R": net / s["risk_eur"] if s["risk_eur"] > 0 else 0.0,
                    "ambiguous_bar": ambiguous, "atr_lag": s.get("atr_lag"), "slippage": slip,
                    **{k: s[k] for k in PASS_THROUGH if k in s},
                }
                x["status"] = "CLOSED"
                self.active.pop(sid, None)
                self.fills.append(result)
                out.append(result)
        return out
