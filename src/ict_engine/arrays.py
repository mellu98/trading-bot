"""PD arrays (entry zones) for engine v2, as pure causal functions.

Catalog formalizations (docs/ict-engine-v1/13): FVG, inverse FVG, order block,
breaker block, OTE, consequent encroachment (CE = midpoint). Each finder looks
only at bars with index <= i (the decision bar) and returns the most recent
valid zone that price has NOT yet retraced to (no retroactive fills).

`get(k)` returns the bar with global index k. Direction d = +1 long, -1 short.
Returned dict: {"array", "lo", "hi", "entry", "formed_at"}.
"""
from __future__ import annotations


def _untouched(get, d, after, i, level):
    """No bar in (after, i] traded to `level` from the favourable side."""
    for k in range(after + 1, i + 1):
        b = get(k)
        if (d == 1 and b.l <= level) or (d == -1 and b.h >= level):
            return False
    return True


def _no_close_beyond(get, d, after, i, level):
    """Invalidation: no close beyond the far edge (below lo for longs, above hi for shorts)."""
    for k in range(after + 1, i + 1):
        c = get(k).c
        if (d == 1 and c < level) or (d == -1 and c > level):
            return False
    return True


def _entry(d, lo, hi, r):
    return hi - r * (hi - lo) if d == 1 else lo + r * (hi - lo)


def fvg(get, d, first, i, atr, cfg, *, middle_only=None):
    """Most recent FVG with middle candle in [first, i-1]; `middle_only` forces one middle (A1/D1)."""
    lo_w, hi_w = cfg["fvg_min_atr"] * atr, cfg["fvg_max_atr"] * atr
    mids = [middle_only] if middle_only is not None else range(i - 1, first - 1, -1)
    for m in mids:
        if m < first or m + 1 > i:
            continue
        a, c = get(m - 1), get(m + 1)
        lo, hi = (a.h, c.l) if d == 1 else (c.h, a.l)
        width = hi - lo
        if width <= 0 or not lo_w <= width <= hi_w:
            continue
        entry = _entry(d, lo, hi, cfg["entry_fraction"])
        far = lo if d == 1 else hi
        if _untouched(get, d, m + 1, i, entry) and _no_close_beyond(get, d, m + 1, i, far):
            return {"array": "fvg", "lo": lo, "hi": hi, "entry": entry, "formed_at": m + 1}
    return None


def ifvg(get, d, i, atr, cfg):
    """Opposite FVG closed through (inverted) within the last `ifvg_retest_bars`, retested at CE."""
    lo_w, hi_w = cfg["fvg_min_atr"] * atr, cfg["fvg_max_atr"] * atr
    first = max(1, i - cfg["ifvg_lookback"])
    for m in range(i - 2, first - 1, -1):
        a, c = get(m - 1), get(m + 1)
        # an opposite-direction gap: bearish gap for a long, bullish gap for a short
        lo, hi = (c.h, a.l) if d == 1 else (a.h, c.l)
        width = hi - lo
        if width <= 0 or not lo_w <= width <= hi_w:
            continue
        edge = hi if d == 1 else lo
        inv = None
        for k in range(m + 2, i + 1):
            close = get(k).c
            if (d == 1 and close > edge) or (d == -1 and close < edge):
                inv = k
                break
        if inv is None or i - inv > cfg["ifvg_retest_bars"]:
            continue
        entry = _entry(d, lo, hi, 0.5)
        far = lo if d == 1 else hi
        if _untouched(get, d, inv, i, entry) and _no_close_beyond(get, d, inv, i, far):
            return {"array": "ifvg", "lo": lo, "hi": hi, "entry": entry, "formed_at": inv}
    return None


def order_block(get, d, mss_i, i, cfg, first):
    """Last opposite-close candle in the `ob_lookback` bars before the displacement (MSS) bar."""
    for k in range(mss_i - 1, max(first, mss_i - cfg["ob_lookback"]) - 1, -1):
        b = get(k)
        if (d == 1 and b.c < b.o) or (d == -1 and b.c > b.o):
            lo, hi = b.l, b.h
            entry = (lo + hi) / 2
            far = lo if d == 1 else hi
            if _untouched(get, d, mss_i, i, entry) and _no_close_beyond(get, d, k, i, far):
                return {"array": "ob", "lo": lo, "hi": hi, "entry": entry, "formed_at": mss_i}
            return None
    return None


def breaker(get, d, anchor_i, i, cfg, first):
    """Order block of the move INTO the anchor, invalidated by a close through it, retested.

    Long: last up-close candle before the sell-off into the sweep low; a later
    close above its high turns it into a bullish breaker (and vice versa).
    """
    for k in range(anchor_i - 1, max(first, anchor_i - cfg["breaker_lookback"]) - 1, -1):
        b = get(k)
        if (d == 1 and b.c > b.o) or (d == -1 and b.c < b.o):
            lo, hi = b.l, b.h
            edge = hi if d == 1 else lo
            brk = None
            for j in range(anchor_i + 1, i + 1):
                close = get(j).c
                if (d == 1 and close > edge) or (d == -1 and close < edge):
                    brk = j
                    break
            if brk is None or i - brk > cfg["ifvg_retest_bars"]:
                return None
            entry = (lo + hi) / 2
            far = lo if d == 1 else hi
            if _untouched(get, d, brk, i, entry) and _no_close_beyond(get, d, brk, i, far):
                return {"array": "breaker", "lo": lo, "hi": hi, "entry": entry, "formed_at": brk}
            return None
    return None


def ote_zone(get, d, anchor_i, extreme, i, cfg):
    """OTE of the impulse from the anchor extreme to the leg extreme (0.62-0.79, entry 0.705)."""
    best_k, best = None, None
    for k in range(anchor_i, i + 1):
        b = get(k)
        v = b.h if d == 1 else b.l
        if best is None or (d == 1 and v > best) or (d == -1 and v < best):
            best, best_k = v, k
    rng = (best - extreme) if d == 1 else (extreme - best)
    if best is None or rng <= 0:
        return None
    if d == 1:
        lo, hi = best - cfg["ote_high"] * rng, best - cfg["ote_low"] * rng
        entry = best - cfg["ote_entry"] * rng
    else:
        lo, hi = best + cfg["ote_low"] * rng, best + cfg["ote_high"] * rng
        entry = best + cfg["ote_entry"] * rng
    return {"array": "ote", "lo": lo, "hi": hi, "entry": entry, "formed_at": best_k}


def ote(get, d, anchor_i, extreme, i, cfg):
    z = ote_zone(get, d, anchor_i, extreme, i, cfg)
    if z is None:
        return None
    if not _untouched(get, d, z["formed_at"], i, z["entry"]):
        return None
    return z


def overlaps(a, b) -> bool:
    return a is not None and b is not None and min(a["hi"], b["hi"]) > max(a["lo"], b["lo"])
