"""E1 — delta-neutral funding carry simulator (long spot + short USD-M perpetual).

Pure offline accounting on hourly bars. Rules/parameters come from the frozen
protocol JSON; nothing here is tuned. See protocol/E1-funding-carry.json.
"""
import bisect
import math

from common import HOUR_MS, iso

DAY_MS = 24 * HOUR_MS


class Sleeve:
    """One asset sleeve: cash (USDT), spot qty q, short perp qty p, isolated collateral cf."""

    def __init__(self, cash):
        self.cash, self.q, self.p, self.cf = cash, 0.0, 0.0, 0.0
        self.last_f = None  # perp price at last mark (variation margin reference)
        self.fees = self.spread = self.slip = 0.0
        self.funding = 0.0
        self.basis_pnl = 0.0  # spot + perp price P&L (excluding funding and costs)
        self.traded = 0.0
        self.trades = self.rebalances = self.liquidations = 0
        self.min_margin_ratio = math.inf
        self.events = []

    @property
    def open(self):
        return self.p > 0


def cost_legs(cost):
    return cost["spot_fee"], cost["perp_fee"], cost["half_spread"], cost["slippage"]


def nav_mid(sl, s, f):
    return sl.cash + sl.q * s + (sl.cf - sl.p * (f - sl.last_f) if sl.open else sl.cf)


def nav_liq(sl, s, f, cost):
    """Liquidation value: exit costs of the current position reserved, not charged."""
    fs, fp, hs, sp = cost_legs(cost)
    if not sl.open and sl.q == 0:
        return sl.cash + sl.cf
    spot = sl.q * s * (1 - hs - sp) * (1 - fs)
    cf = sl.cf - sl.p * (f - sl.last_f) if sl.open else sl.cf
    perp_close = sl.p * f * (hs + sp) + fp * sl.p * f * (1 + hs + sp)
    return sl.cash + spot + cf - perp_close


def settle_mark(sl, f):
    """Variation margin: move perp P&L since the last mark into collateral."""
    if sl.open:
        d = -sl.p * (f - sl.last_f)
        sl.cf += d
        sl.basis_pnl += d
        sl.last_f = f


def close_all(sl, s, f, cost, t, why):
    fs, fp, hs, sp = cost_legs(cost)
    settle_mark(sl, f)
    if sl.q > 0:
        px = s * (1 - hs - sp)
        proceeds = sl.q * px
        fee = proceeds * fs
        sl.fees += fee
        sl.spread += sl.q * s * hs
        sl.slip += sl.q * s * sp
        sl.traded += sl.q * s
        sl.cash += proceeds - fee
        sl.basis_pnl += 0.0
        sl.q = 0.0
    if sl.p > 0:
        px = f * (1 + hs + sp)
        cost_px = sl.p * (px - f)  # buy-to-close above mid
        fee = sl.p * px * fp
        sl.fees += fee
        sl.spread += sl.p * f * hs
        sl.slip += sl.p * f * sp
        sl.traded += sl.p * f
        sl.cf -= cost_px + fee
        sl.p = 0.0
    sl.cash += sl.cf
    sl.cf = 0.0
    sl.last_f = None
    sl.trades += 1
    sl.events.append((iso(t), "exit", why))


def target_qty(equity, s, f, m, cost):
    """Hedged quantity affordable from equity: spot at ask + fee, perp execution cost + fee, margin."""
    fs, fp, hs, sp = cost_legs(cost)
    spot_unit = s * (1 + hs + sp) * (1 + fs)
    perp_unit = f * (hs + sp) + f * (1 - hs - sp) * fp
    return equity / (spot_unit + perp_unit + m * f)


def set_position(sl, s, f, m, cost, t, why):
    """Move from the current state to a fully hedged position sized on current equity."""
    fs, fp, hs, sp = cost_legs(cost)
    settle_mark(sl, f)
    equity = sl.cash + sl.q * s + sl.cf
    q_new = target_qty(equity, s, f, m, cost)
    dq = q_new - sl.q
    # spot leg
    if dq > 0:
        px = s * (1 + hs + sp)
        sl.cash -= dq * px * (1 + fs)
    else:
        px = s * (1 - hs - sp)
        sl.cash += -dq * px * (1 - fs)
    sl.fees += abs(dq) * px * fs
    sl.spread += abs(dq) * s * hs
    sl.slip += abs(dq) * s * sp
    sl.traded += abs(dq) * s
    # perp leg (short p = q_new); execution away from mid is a cost charged to collateral
    dp = q_new - sl.p
    if dp != 0:
        px_p = f * (1 - hs - sp) if dp > 0 else f * (1 + hs + sp)
        fee = abs(dp) * px_p * fp
        sl.fees += fee
        sl.spread += abs(dp) * f * hs
        sl.slip += abs(dp) * f * sp
        sl.traded += abs(dp) * f
        sl.cf -= abs(dp) * f * (hs + sp) + fee
    sl.q = sl.p = q_new
    sl.last_f = f
    # move collateral to the m * notional target; remainder stays as spot-wallet cash
    want = m * q_new * f
    sl.cash += sl.cf - want
    sl.cf = want
    if sl.cash < -1e-9 * max(1.0, equity):
        raise AssertionError(f"negative cash {sl.cash} at {iso(t)}")
    sl.events.append((iso(t), "set", why))


def simulate(cfg, bars_s, bars_f, funding, start_ms, end_ms, cost, capital, rf_daily):
    """Run one configuration over [start_ms, end_ms). Returns daily records and sleeve stats.

    bars_s / bars_f: {sym: {open_ms: (o,h,l,c,close_ms)}}; funding: {sym: [(calc_ms, int_h, rate)]}
    """
    syms = cfg["symbols"]
    m = cfg["margin_fraction"]
    band_lo, band_hi = m * cfg["rebalance_band"][0], m * cfg["rebalance_band"][1]
    mmr = cfg["maintenance_margin_rate"]
    rule = cfg["rule"]
    lookback_ms = cfg.get("signal_lookback_days", 7) * DAY_MS
    sleeves = {s: Sleeve(capital * w) for s, w in cfg["weights"].items()}
    fidx = {s: 0 for s in syms}
    last_px = {s: {"s": None, "f": None} for s in syms}
    daily, gaps = [], {s: 0 for s in syms}
    exec_hour = cfg["execution_hour_utc"]
    t = start_ms - start_ms % DAY_MS  # midnight of start day
    first_decision = start_ms
    nav_prev = None
    while t < end_ms:
        hour = (t // HOUR_MS) % 24
        for sym in syms:
            sl = sleeves[sym]
            bs, bf = bars_s[sym].get(t), bars_f[sym].get(t)
            if bs is None or bf is None:
                gaps[sym] += 1
            # 1) funding settlements stamped inside this hour bucket, applied at its start,
            #    before any execution (position must be open at the settlement timestamp)
            fl = funding[sym]
            while fidx[sym] < len(fl) and fl[fidx[sym]][0] < t + HOUR_MS:
                calc, _, rate = fl[fidx[sym]]
                if calc >= t and sl.open and t >= first_decision:
                    mark = bf[0] if bf else last_px[sym]["f"]
                    pay = sl.p * mark * rate
                    sl.cf += pay
                    sl.funding += pay
                fidx[sym] += 1
            if bs is None or bf is None:
                continue
            so, sh, sl_, sc = bs[:4]
            fo, fh, fl_, fc = bf[:4]
            # 2) decision / execution at the open of the execution hour
            if hour == exec_hour and t >= first_decision:
                signal_in = decide(rule, funding[sym], t, lookback_ms, cfg, sl.open)
                if sl.open and not signal_in:
                    close_all(sl, so, fo, cost, t, "signal_off")
                elif signal_in and not sl.open:
                    if sl.q > 0:  # unhedged spot left by a liquidation
                        close_all(sl, so, fo, cost, t, "post_liquidation_flatten")
                    set_position(sl, so, fo, m, cost, t, "enter")
                elif sl.open:
                    settle_mark(sl, fo)
                    ratio = sl.cf / (sl.p * fo)
                    if ratio < band_lo or ratio > band_hi:
                        set_position(sl, so, fo, m, cost, t, f"rebalance ratio={ratio:.3f}")
                        sl.rebalances += 1
                elif sl.q > 0:  # liquidated earlier and signal now off
                    close_all(sl, so, fo, cost, t, "post_liquidation_flatten")
            # 3) intra-hour liquidation check on the perp high (worst case for a short)
            if sl.open:
                worst = sl.cf - sl.p * (fh - sl.last_f)
                ratio_w = worst / (sl.p * fh)
                sl.min_margin_ratio = min(sl.min_margin_ratio, ratio_w)
                if worst < mmr * sl.p * fh:
                    # isolated position liquidated: assume the whole collateral is lost
                    sl.basis_pnl += -sl.cf
                    sl.cf = 0.0
                    sl.p = 0.0
                    sl.last_f = None
                    sl.liquidations += 1
                    sl.events.append((iso(t), "LIQUIDATION", f"high={fh}"))
                else:
                    settle_mark(sl, fc)
            last_px[sym] = {"s": sc, "f": fc}
        # daily NAV at 00:00 UTC (marks with the previous hour close)
        if hour == 23:
            day_end = t + HOUR_MS
            nav = 0.0
            for sym in syms:
                px = last_px[sym]
                nav += nav_liq(sleeves[sym], px["s"], px["f"], cost) if px["s"] else sleeves[sym].cash
            if day_end > first_decision:
                daily.append({"t": day_end, "nav": nav, "rf": rf_daily(day_end - DAY_MS),
                              "open": {s: sleeves[s].open for s in syms}})
            nav_prev = nav
        t += HOUR_MS
    # terminal liquidation at the last available hour close (costs realised once)
    for sym in syms:
        sl, px = sleeves[sym], last_px[sym]
        if (sl.open or sl.q > 0) and px["s"]:
            close_all(sl, px["s"], px["f"], cost, end_ms, "segment_end")
    final = sum(s.cash + s.cf for s in sleeves.values())
    if daily:
        daily[-1]["nav"] = final
    return daily, sleeves, gaps


_PREFIX = {}


def _prefix(fl):
    key = id(fl)
    if key not in _PREFIX:
        times = [c for (c, _, _) in fl]
        csum = [0.0]
        for (_, _, r) in fl:
            csum.append(csum[-1] + r)
        _PREFIX[key] = (times, csum)
    return _PREFIX[key]


def decide(rule, fl, t, lookback_ms, cfg, is_open):
    if rule == "always_on":
        return True
    if rule == "hysteresis":
        # settled rates strictly before the decision time (t is the execution open): lo < calc < t
        times, csum = _prefix(fl)
        i0 = bisect.bisect_right(times, t - lookback_ms)
        i1 = bisect.bisect_left(times, t)
        if i1 <= i0:
            return False
        ann = (csum[i1] - csum[i0]) * (365 * DAY_MS / lookback_ms)
        if is_open:
            return ann > cfg["exit_threshold_annual"]
        return ann >= cfg["entry_threshold_annual"]
    raise ValueError(rule)
