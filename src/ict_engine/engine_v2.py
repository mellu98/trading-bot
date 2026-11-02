"""ICT engine v2 ("full"): three entry models over every liquidity pool type.

Models (docs/ict-engine-v1/01 alternatives + 13 catalog):
- reversal (A1 generalised): a bar sweeps a pool (swing, equal, H1, PDH/PDL,
  PWH/PWL, Asia/London/NY-AM range) and closes back; within `mss_ttl_bars` a
  displacement candle closes beyond the last opposite M5 swing (MSS); one bar
  later the entry goes on the best PD array of the leg.
- continuation (B1): H1 trend d, price pulls back beyond the dealing-range
  midpoint (discount for longs) without breaking the origin; MSS in direction
  d from the pullback extreme; same PD-array entry.
- silver_bullet (D1): inside the Silver Bullet windows, a displacement candle
  in the bias direction breaks the last opposite M5 swing; the FVG it leaves
  (middle candle = displacement) is the entry, stop beyond the three bars.

Entry: limit at the zone's CE / mean threshold / OTE 0.705, never already
crossed. Stop beyond the anchor extreme + buffer. Target: draw on liquidity
(nearest opposite pool ahead of entry by default). Confluence score counts
HTF alignment, daily bias, premium/discount, killzone, external pool, SMT,
OTE overlap and stacked arrays; `min_confluence` is the selectivity knob that
the frequency calibration moves.

Strictly causal: pools, pivots and context are those known before the bar;
decisions use the closed bar only; fills happen on later bars (simulator).
"""
from __future__ import annotations

import bisect
from collections import Counter, deque
from datetime import timedelta
from hashlib import sha256
from math import isfinite

from . import arrays, windows
from .context import PRIORITY, MarketContext, PoolBook
from .detectors import mss, sweep
from .engine import ceil_tick, floor_tick
from .news import blocked
from .risk import gate
from .sizing import size, slippage_for

MODEL_PRIORITY = {"reversal": 3, "silver_bullet": 2, "continuation": 1}
HIST = 400


class CompanionSeries:
    """Correlated market (NQ<->ES, EURUSD<->GBPUSD) for SMT divergence. Read-only, as-of."""

    def __init__(self, bars):
        self.ts = [b.ts for b in bars]
        self.h = [b.h for b in bars]
        self.l = [b.l for b in bars]
        self.idx = {t: k for k, t in enumerate(self.ts)}

    def diverges(self, src_ts, now, kind):
        """True = SMT: the companion did NOT take its own extreme printed at src_ts."""
        j = self.idx.get(src_ts)
        if j is None:
            return None
        k = bisect.bisect_right(self.ts, now) - 1
        if k <= j:
            return None
        if kind == "LOW":
            return min(self.l[j + 1:k + 1]) >= self.l[j]
        return max(self.h[j + 1:k + 1]) <= self.h[j]


class _Pivot:
    __slots__ = ("index", "kind", "price", "ts", "broken")

    def __init__(self, index, kind, price, ts):
        self.index, self.kind, self.price, self.ts = index, kind, price, ts
        self.broken = False


class ICTEngine:
    def __init__(self, cfg, *, companion: CompanionSeries | None = None, keep_log=False):
        if cfg["mode"] != "simulation":
            raise ValueError("simulation only")
        if cfg.get("engine") != "v2":
            raise ValueError("ICTEngine needs an engine=v2 config")
        self.cfg = cfg
        self.tf = timedelta(seconds=cfg["timeframe_seconds"])
        self.types = set(cfg["pool_types"])
        self.book = PoolBook()
        self.ctxm = MarketContext(cfg, self.book)
        self.companion = companion if cfg.get("smt_enabled") else None
        self.keep_log = keep_log
        self.log = []
        self.notable = []
        self.counts = Counter()
        self.n = 0
        self.reset_m5()

    # ================================================================ state
    def reset_m5(self):
        c = self.cfg
        self.hist = deque(maxlen=HIST)
        self.atr_buf = deque(maxlen=c["atr_period"] + 1)
        self.piv_buf = deque(maxlen=c["pivot_left"] + c["pivot_right"] + 1)
        self.recent = deque()  # confirmed M5 pivots within lookback (break levels)
        self.setups = {}
        self.last_ts = None
        self.book.drop({"swing", "equal"})

    def on_gap(self, *, full=False):
        """Unexpected data gap (full=True for a futures roll): no stale state survives it."""
        self.reset_m5()
        self.book.clear()
        if full:
            self.ctxm.reset()
        else:
            self.ctxm.mark_incomplete()

    @property
    def lo(self):
        """Global index of the oldest bar still in memory (since the last reset)."""
        return self.n - len(self.hist)

    def get(self, k):
        j = k - self.lo
        if j < 0:
            raise IndexError("bar no longer in memory")
        return self.hist[j]

    def record(self, b, code, model=None):
        key = f"{model}:{code}" if model else code
        self.counts[key] += 1
        if self.keep_log:
            self.log.append({"ts": b.ts.isoformat(), "reason": key})

    # ================================================================ structure
    def _atr(self):
        n = self.cfg["atr_period"]
        if len(self.atr_buf) < n + 1:
            return None
        xs = list(self.atr_buf)
        return sum(max(b.h - b.l, abs(b.h - a.c), abs(b.l - a.c)) for a, b in zip(xs, xs[1:])) / n

    def _confirm_pivot(self, atr):
        c = self.cfg
        left, right = c["pivot_left"], c["pivot_right"]
        if len(self.piv_buf) < left + right + 1:
            return
        win = list(self.piv_buf)
        centre = win[left]
        others = win[:left] + win[left + 1:]
        j = self.n - 1 - right
        known = win[-1].ts
        for kind, value, test in (("HIGH", centre.h, all(centre.h > x.h for x in others)),
                                  ("LOW", centre.l, all(centre.l < x.l for x in others))):
            if not test:
                continue
            pv = _Pivot(j, kind, value, centre.ts)
            if "swing" in self.types:
                self.book.add(kind, value, "swing", known, centre.ts, index=j)
            if "equal" in self.types and atr:
                tol = max(2 * c["tick_size"], c["equal_tolerance_atr"] * atr)
                for q in reversed(self.recent):
                    if (q.kind == kind and not q.broken and j - q.index >= c["equal_min_separation"]
                            and abs(q.price - value) <= tol):
                        level = max(q.price, value) if kind == "HIGH" else min(q.price, value)
                        src = centre.ts if level == value else q.ts
                        self.book.add(kind, level, "equal", known, src, index=j)
                        break
            self.recent.append(pv)

    def _last_pivot(self, kind, before):
        lb = self.cfg["structure_lookback"]
        for p in reversed(self.recent):
            if p.kind == kind and p.index < before and before - p.index <= lb:
                return p
        return None

    # ================================================================ main
    def on_bar(self, b, ctx):
        if not all(isfinite(x) for x in (ctx.equity, ctx.spread)) or ctx.equity <= 0 or ctx.spread < 0:
            raise ValueError("invalid account/quote")
        if self.last_ts is not None and b.ts <= self.last_ts:
            raise ValueError("bars must be strictly increasing")
        atr = self._atr()
        self._confirm_pivot(atr)
        self.hist.append(b)
        self.atr_buf.append(b)
        self.piv_buf.append(b)
        i = self.n
        self.n += 1
        self.last_ts = b.ts
        lb = self.cfg["structure_lookback"] * self.cfg["equal_lookback_mult"]
        while self.recent and i - self.recent[0].index > lb:
            self.recent.popleft()
        intent = None
        if atr is None or atr <= 0:
            self.record(b, "WAIT_WARMUP")
        else:
            intent = self._decide(b, ctx, i, atr)
        self.book.apply_bar(b)
        for pv in self.recent:
            if not pv.broken and ((pv.kind == "HIGH" and b.h >= pv.price) or (pv.kind == "LOW" and b.l <= pv.price)):
                pv.broken = True
        self.ctxm.on_bar(b)
        return intent

    def _decide(self, b, ctx, i, atr):
        c = self.cfg
        reason = gate(ctx.risk, c)
        if not reason and c["news_enabled"]:
            reason = blocked(b.ts, ctx.events, ctx.calendar_updated, ctx.currencies, c)
        flat = windows.flat_at(b.ts, c)
        if flat is None or (flat - b.ts) < timedelta(minutes=c["no_entry_before_flat_minutes"]):
            reason = reason or "SKIP_SESSION"
        age = (b.ts - ctx.quote_time).total_seconds()
        if not 0 <= age <= c["quote_max_age_seconds"]:
            reason = reason or "SKIP_STALE_QUOTE"
        if c["v2_max_spread_atr"] is not None and ctx.spread > c["v2_max_spread_atr"] * atr:
            reason = reason or "SKIP_SPREAD_TOO_HIGH"
        if reason:
            self.setups.clear()
            self.record(b, reason)
            return None
        slip = slippage_for(b.c, c)
        found = []
        for model in c["models"]:
            sig = getattr(self, "_m_" + model)(b, ctx, i, atr, slip, flat)
            if sig:
                found.append(sig)
        if not found:
            self.record(b, "SCAN")
            return None
        found.sort(key=lambda s: (s["score"], MODEL_PRIORITY[s["model"]]), reverse=True)
        for other in found[1:]:
            self.record(b, "SKIP_OTHER_MODEL_CHOSEN", other["model"])
        chosen = found[0]
        self.record(b, "ENTER_LONG" if chosen["direction"] == 1 else "ENTER_SHORT", chosen["model"])
        self.notable.append({"ts": b.ts.isoformat(), "model": chosen["model"], "score": chosen["score"]})
        return chosen

    # ================================================================ models
    def _m_reversal(self, b, ctx, i, atr, slip, flat):
        c, m = self.cfg, "reversal"
        s = self.setups.get(m)
        if s:
            d = s["d"]
            if (b.l < s["extreme"] if d == 1 else b.h > s["extreme"]):
                del self.setups[m]
                self.record(b, "SWEEP_INVALIDATED", m)
                return None
            if s["mss_i"] is None:
                if i - s["anchor_i"] > c["mss_ttl_bars"]:
                    del self.setups[m]
                    self.record(b, "MSS_EXPIRED", m)
                    return None
                if mss(b, s["break_level"], d, atr, c):
                    s["mss_i"] = i
                    self.record(b, "MSS", m)
                return None
            del self.setups[m]
            return self._build(b, ctx, i, atr, slip, flat, s)
        cands = []
        lb = c["structure_lookback"]
        for p in self.book.live(b.ts, self.types):
            if p.used:
                continue
            if p.index is not None:
                limit = lb * (c["equal_lookback_mult"] if p.ptype == "equal" else 1)
                if i - p.index > limit:
                    continue
            d = 1 if p.kind == "LOW" else -1
            if sweep(b, p, d, atr, c):
                opp = self._last_pivot("HIGH" if d == 1 else "LOW", i)
                if opp is not None:
                    cands.append((p, d, opp))
        if not cands:
            return None
        if len({d for _, d, _ in cands}) > 1:
            self.record(b, "DUAL_SWEEP", m)
            return None
        p, d, opp = max(cands, key=lambda x: (PRIORITY[x[0].ptype], x[0].known_at, x[0].pid))
        p.used = True
        smt = self.companion.diverges(p.src_ts, b.ts, p.kind) if self.companion else None
        self.setups[m] = {"model": m, "d": d, "anchor_i": i, "extreme": b.l if d == 1 else b.h,
                          "break_level": opp.price, "mss_i": None, "pool": p, "smt": smt}
        self.record(b, "SWEEP_" + p.ptype.upper(), m)
        return None

    def _m_continuation(self, b, ctx, i, atr, slip, flat):
        c, m = self.cfg, "continuation"
        trend, rng = self.ctxm.trend, self.ctxm.range
        s = self.setups.get(m)
        if s:
            d = s["d"]
            if trend != d:
                del self.setups[m]
                self.record(b, "TREND_CHANGED", m)
                s = None
            elif (b.l < s["origin"] if d == 1 else b.h > s["origin"]):
                del self.setups[m]
                self.record(b, "PULLBACK_INVALIDATED", m)
                return None
            elif s["mss_i"] is None:
                if (b.l < s["extreme"] if d == 1 else b.h > s["extreme"]):
                    opp = self._last_pivot("HIGH" if d == 1 else "LOW", i)
                    if opp is None:
                        del self.setups[m]
                        return None
                    s.update(anchor_i=i, extreme=b.l if d == 1 else b.h, break_level=opp.price)
                    return None
                if i - s["anchor_i"] > c["mss_ttl_bars"]:
                    del self.setups[m]
                    self.record(b, "MSS_EXPIRED", m)
                    return None
                if mss(b, s["break_level"], d, atr, c):
                    s["mss_i"] = i
                    self.record(b, "MSS", m)
                return None
            else:
                del self.setups[m]
                return self._build(b, ctx, i, atr, slip, flat, s)
        if trend == 0 or rng is None or self.ctxm.zone(b.c) is None:
            return None
        lo, hi = rng
        mid = lo + c["cont_pullback_z"] * (hi - lo)
        d = trend
        if d == 1 and lo < b.l <= mid:
            opp = self._last_pivot("HIGH", i)
            extreme, origin = b.l, lo
        elif d == -1 and mid <= b.h < hi:
            opp = self._last_pivot("LOW", i)
            extreme, origin = b.h, hi
        else:
            return None
        if opp is None:
            return None
        self.setups[m] = {"model": m, "d": d, "anchor_i": i, "extreme": extreme, "origin": origin,
                          "break_level": opp.price, "mss_i": None, "pool": None, "smt": None}
        self.record(b, "PULLBACK", m)
        return None

    def _bias(self):
        h1, daily = self.ctxm.trend, self.ctxm.daily_bias
        mode = self.cfg["sb_bias"]
        if mode == "h1":
            return h1
        if mode == "daily":
            return daily
        if h1 and daily and h1 != daily:
            return 0
        return h1 or daily

    def _m_silver_bullet(self, b, ctx, i, atr, slip, flat):
        c, m = self.cfg, "silver_bullet"
        s = self.setups.get(m)
        if s:
            del self.setups[m]
            return self._build(b, ctx, i, atr, slip, flat, s)
        if not windows.in_any(b.ts - self.tf, c, c["silver_bullet_windows"]):
            return None
        d = self._bias()
        if d == 0:
            return None
        opp = self._last_pivot("HIGH" if d == 1 else "LOW", i)
        if opp is None or not mss(b, opp.price, d, atr, c):
            return None
        if i - 1 < self.lo:
            return None
        self.setups[m] = {"model": m, "d": d, "anchor_i": i - 1, "extreme": None, "break_level": opp.price,
                          "mss_i": i, "pool": None, "smt": None, "sb": True}
        self.record(b, "DISPLACEMENT", m)
        return None

    # ================================================================ intent
    def _arrays(self, s, i, atr):
        c, get, d = self.cfg, self.get, s["d"]
        first = max(self.lo + 1, s["anchor_i"] + 1, i - c["leg_max_bars"])
        if s.get("sb"):
            z = arrays.fvg(get, d, s["mss_i"], i, atr, c, middle_only=s["mss_i"])
            return [z] if z else []
        out = []
        for name in c["pd_arrays"]:
            if name == "fvg":
                z = arrays.fvg(get, d, first, i, atr, c)
            elif name == "ifvg":
                z = arrays.ifvg(get, d, i, atr, c) if i - c["ifvg_lookback"] - 1 >= self.lo else None
            elif name == "ob":
                z = arrays.order_block(get, d, s["mss_i"], i, c, self.lo)
            elif name == "breaker":
                z = arrays.breaker(get, d, s["anchor_i"], i, c, self.lo)
            else:
                z = arrays.ote(get, d, s["anchor_i"], s["extreme"], i, c)
            if z:
                out.append(z)
        return out

    def _target(self, d, entry, stop, now):
        c, tick = self.cfg, self.cfg["tick_size"]
        risk = abs(entry - stop)
        if c["target_mode"] == "fixed_rr":
            t = entry + d * c["fixed_rr"] * risk
            return (floor_tick(t, tick) if d == 1 else ceil_tick(t, tick)), "fixed_rr"
        kind = "HIGH" if d == 1 else "LOW"
        ahead = []
        for p in self.book.live(now, self.types):
            if p.kind != kind:
                continue
            x = p.price - d * tick
            if d * (x - entry) > 0:
                ahead.append((d * (x - entry), x, p.ptype))
        ahead.sort()
        if c["target_mode"] == "nearest_rr":
            ahead = [a for a in ahead if a[0] >= c["min_net_rr"] * risk]
        if not ahead:
            return None, None
        _, x, ptype = ahead[0]
        return (floor_tick(x, tick) if d == 1 else ceil_tick(x, tick)), ptype

    def _build(self, b, ctx, i, atr, slip, flat, s):
        c, m, d = self.cfg, s["model"], s["d"]
        tick = c["tick_size"]
        zones = self._arrays(s, i, atr)
        if not zones:
            self.record(b, "NO_PD_ARRAY", m)
            return None
        if s.get("sb"):
            lows = [self.get(k) for k in range(s["mss_i"] - 1, i + 1)]
            extreme = min(x.l for x in lows) if d == 1 else max(x.h for x in lows)
        else:
            extreme = s["extreme"]
        buff = max(c["stop_buffer_atr"] * atr, c["stop_buffer_spreads"] * ctx.spread, tick)
        stop = extreme - d * buff
        stop = floor_tick(stop, tick) if d == 1 else ceil_tick(stop, tick)
        ote_z = None if s.get("sb") else arrays.ote_zone(self.get, d, s["anchor_i"], extreme, i, c)
        last = "NO_VALID_ARRAY"
        for z in zones:
            entry = floor_tick(z["entry"], tick) if d == 1 else ceil_tick(z["entry"], tick)
            if (b.c + ctx.spread / 2 <= entry) if d == 1 else (b.c - ctx.spread / 2 >= entry):
                last = "ENTRY_PASSED"
                continue
            if d * (entry - stop) <= 0:
                last = "INVALID_GEOMETRY"
                continue
            dist = abs(entry - stop) / atr
            if not c["stop_min_atr"] <= dist <= c["stop_max_atr"]:
                last = "STOP_DISTANCE"
                continue
            target, target_type = self._target(d, entry, stop, b.ts)
            if target is None:
                last = "NO_TARGET"
                continue
            unit = c["multiplier"] * c["quote_to_eur"]
            cost = ctx.spread + slip + c["fee_rate"] * (entry + stop) + (c["unit_fee_eur"] / unit if unit else 0)
            if cost / abs(entry - stop) > c["max_cost_risk"]:
                last = "COST_TOO_HIGH"
                continue
            sized = size(ctx.equity, entry, stop, target, d, c, cash=ctx.cash, slippage=slip)
            if not sized["qty"]:
                last = sized["reason"].replace("SKIP_", "")
                continue
            conf = self._confluence(b, s, d, entry, z, zones, ote_z)
            score = sum(1 for v in conf.values() if v)
            if score < c["min_confluence"]:
                last = "LOW_CONFLUENCE"
                continue
            return self._signal(b, s, d, entry, stop, target, target_type, sized, z, conf, score, atr, ctx, slip, flat)
        self.record(b, last, m)
        return None

    def _confluence(self, b, s, d, entry, z, zones, ote_z):
        c, cm = self.cfg, self.ctxm
        zone = cm.zone(entry)
        if zone is not None:
            pd_ok = zone <= 0.5 if d == 1 else zone >= 0.5
        elif cm.midnight_open is not None:
            pd_ok = entry < cm.midnight_open if d == 1 else entry > cm.midnight_open
        else:
            pd_ok = False
        pool = s.get("pool")
        return {
            "htf": cm.trend == d,
            "daily_bias": cm.daily_bias == d,
            "premium_discount": pd_ok,
            "killzone": windows.in_any(b.ts - self.tf, c, c["killzones"]),
            "external_pool": bool(pool is not None and pool.ptype != "swing"),
            "smt": s.get("smt") is True,
            "ote": bool(ote_z and ote_z["lo"] <= entry <= ote_z["hi"]),
            "stacked_arrays": any(o is not z and o["array"] != z["array"] and arrays.overlaps(o, z) for o in zones),
        }

    def _signal(self, b, s, d, entry, stop, target, target_type, sized, z, conf, score, atr, ctx, slip, flat):
        c = self.cfg
        expires = min(b.ts + timedelta(seconds=c["order_ttl_bars"] * c["timeframe_seconds"]), flat)
        pool = s.get("pool")
        sid = sha256(f"{c['version']}|{c['symbol']}|{b.ts.isoformat()}|{d}|{s['model']}|{s['anchor_i']}".encode()).hexdigest()
        return {
            "signal_id": sid, "version": c["version"], "symbol": c["symbol"], "direction": d,
            "known_at": b.ts.isoformat(), "entry": entry, "stop": stop, "target": target,
            "expires_at": expires.isoformat(), "flat_at": flat.isoformat(), **sized,
            "model": s["model"], "score": score, "confluence": conf, "array": z["array"],
            "pool_type": pool.ptype if pool is not None else None, "target_type": target_type,
            "smt": s.get("smt"), "atr_lag": atr, "spread": ctx.spread, "slippage": slip,
            "zone": [z["lo"], z["hi"]],
        }
