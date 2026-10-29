"""Runner for E1 (funding carry). Usage: python -I run_e1.py <research_dir> <segment|all>

Refuses to overwrite existing result files (one-shot evaluation per segment).
"""
import bisect
import csv
import datetime as dt
import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from carry import DAY_MS, simulate  # noqa: E402
from common import (HOUR_MS, circular_block_bootstrap, iso, load_funding, load_klines, max_drawdown,  # noqa: E402
                    mean, ols_alpha_beta_hac, quantile, sharpe, sortino, stdev)

root = pathlib.Path(sys.argv[1])
which = sys.argv[2]
proto = json.loads((root / "protocol" / "E1-funding-carry.json").read_text())
cache = root / "cache" / "binance" / "data"
SYMS = proto["common_mechanics"]["symbols"]


def parse_iso(s):
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


bars_s = {s: load_klines(cache / f"spot/monthly/klines/{s}/1h") for s in SYMS}
bars_f = {s: load_klines(cache / f"futures/um/monthly/klines/{s}/1h") for s in SYMS}
funding = {s: load_funding(cache / f"futures/um/monthly/fundingRate/{s}") for s in SYMS}

# --- risk-free: DTB3, value of the last business day strictly before the accrual day ---
rf_days, rf_vals = [], []
with open(root / "cache" / "fred" / "DTB3.csv") as fh:
    for row in csv.DictReader(fh):
        v = row.get("DTB3") or row.get("dtb3")
        d = row.get("observation_date") or row.get("DATE")
        if v in (None, "", "."):
            continue
        rf_days.append(parse_iso(d + "T00:00:00Z"))
        rf_vals.append(float(v) / 100.0 / 360.0)


def rf_daily(day_start_ms):
    i = bisect.bisect_left(rf_days, day_start_ms) - 1
    if i < 0:
        raise ValueError("no T-bill observation before " + iso(day_start_ms))
    return rf_vals[i]


def buy_hold(start, end, capital, cost):
    """50/50 BTC/ETH spot bought at the first execution open, held, liquidated at the end."""
    fs, hs, sp = cost["spot_fee"], cost["half_spread"], cost["slippage"]
    t0 = start
    qty = {}
    for s in SYMS:
        o = bars_s[s][t0][0]
        qty[s] = capital * 0.5 / (o * (1 + hs + sp) * (1 + fs))
    navs = [{"t": start, "nav": capital}]
    t = start - start % DAY_MS + DAY_MS
    while t <= end:
        v = 0.0
        for s in SYMS:
            b = bars_s[s].get(t - HOUR_MS)
            if b is None:
                raise ValueError("missing bar for buy&hold mark " + iso(t - HOUR_MS))
            v += qty[s] * b[3] * (1 - hs - sp) * (1 - fs)
        navs.append({"t": t, "nav": v})
        t += DAY_MS
    return navs


def btc_daily_returns(records):
    out = []
    for a, b in zip(records, records[1:]):
        pa = bars_s["BTCUSDT"].get(a["t"] - HOUR_MS) if a["t"] % DAY_MS == 0 else bars_s["BTCUSDT"].get(a["t"])
        pb = bars_s["BTCUSDT"].get(b["t"] - HOUR_MS)
        pa_px = pa[3] if a["t"] % DAY_MS == 0 else pa[0]
        out.append(pb[3] / pa_px - 1)
    return out


def metrics(records, capital, rf_list):
    navs = [r["nav"] for r in records]
    rets = [b / a - 1 for a, b in zip(navs, navs[1:])]
    days = (records[-1]["t"] - records[0]["t"]) / DAY_MS
    tb = 1.0
    for r in rf_list:
        tb *= 1 + r
    exc = [r - f for r, f in zip(rets, rf_list)]
    total = navs[-1] / capital - 1
    ann = (navs[-1] / capital) ** (365 / days) - 1 if navs[-1] > 0 else -1.0
    tb_ann = tb ** (365 / days) - 1
    return {
        "days": round(days, 3), "final_nav": navs[-1], "net_return": total, "annualised": ann,
        "tbill_return": tb - 1, "tbill_annualised": tb_ann,
        "excess_vs_tbill_total": (1 + total) - tb, "excess_vs_tbill_annualised": ann - tb_ann,
        "vol_annual": stdev(rets) * math.sqrt(365), "sharpe_vs0": sharpe(rets, 365),
        "sharpe_excess": sharpe(exc, 365), "sortino_vs0": sortino(rets, 365),
        "max_drawdown": max_drawdown(navs), "worst_day": min(rets), "best_day": max(rets),
        "mean_daily_excess_bp": mean(exc) * 1e4,
    }, rets, exc


def period_excess(records, rf_list, y0, y1):
    """Compounded strategy return minus compounded T-bill within [y0, y1)."""
    s = tb = 1.0
    navs = [r["nav"] for r in records]
    for i in range(1, len(records)):
        t = records[i]["t"] - 1
        if y0 <= t < y1:
            s *= navs[i] / navs[i - 1]
            tb *= 1 + rf_list[i - 1]
    return {"strategy": s - 1, "tbill": tb - 1, "excess": s - tb}


def monthly_pnl(records):
    out = {}
    for a, b in zip(records, records[1:]):
        k = iso(b["t"] - 1)[:7]
        out[k] = out.get(k, 0.0) + (b["nav"] - a["nav"])
    return out


def run_segment(seg_name):
    seg = proto["segments"][seg_name]
    start, end = parse_iso(seg["start"]), parse_iso(seg["end"])
    capital = proto["capital_per_segment_usdt"]
    outdir = root / "results" / "E1" / seg_name
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for cname, ccfg in proto["configurations"].items():
        for kname, cost in proto["costs_per_side_per_leg"].items():
            path = outdir / f"{cname}-{kname}.json"
            if path.exists():
                raise SystemExit(f"refusing to overwrite {path}")
            cfg = dict(proto["common_mechanics"], **ccfg)
            daily, sleeves, gaps = simulate(cfg, bars_s, bars_f, funding, start, end, cost, capital, rf_daily)
            records = [{"t": start, "nav": capital}] + daily
            rf_list = [rf_daily(r["t"] - DAY_MS) if r["t"] % DAY_MS == 0 else rf_daily(r["t"]) for r in records[1:]]
            m, rets, exc = metrics(records, capital, rf_list)
            btc = btc_daily_returns(records)
            a, b, ta = ols_alpha_beta_hac(rets, btc, 7)
            m["beta_to_btc"] = b
            m["corr_to_btc"] = (sum((x - mean(rets)) * (y - mean(btc)) for x, y in zip(rets, btc))
                                / ((len(rets) - 1) * stdev(rets) * stdev(btc)))
            m["time_in_market"] = mean([mean([1.0 if r["open"][s] else 0.0 for s in SYMS]) for r in daily])
            tot = {k: sum(getattr(sl, k) for sl in sleeves.values())
                   for k in ("fees", "spread", "slip", "funding", "basis_pnl", "traded")}
            m.update({f"total_{k}": v for k, v in tot.items()})
            # spot+perp price P&L at mid (incl. any liquidation loss) = net - funding + execution costs
            m["price_pnl_residual"] = (records[-1]["nav"] - capital) - tot["funding"] + tot["fees"] + tot["spread"] + tot["slip"]
            m["turnover_x"] = tot["traded"] / mean([r["nav"] for r in records])
            m["trades"] = sum(sl.trades for sl in sleeves.values())
            m["entries_rebalances"] = sum(sl.rebalances for sl in sleeves.values())
            m["liquidations"] = sum(sl.liquidations for sl in sleeves.values())
            m["min_margin_ratio"] = min(sl.min_margin_ratio for sl in sleeves.values())
            m["missing_hours"] = gaps
            years = {}
            for y in range(int(iso(start)[:4]), int(iso(end - 1)[:4]) + 1):
                y0 = parse_iso(f"{y}-01-01T00:00:00Z")
                y1 = parse_iso(f"{y + 1}-01-01T00:00:00Z")
                years[str(y)] = period_excess(records, rf_list, max(y0, start), min(y1, end))
            m["calendar_years"] = years
            mp = monthly_pnl(records)
            pos = sorted(mp.values(), reverse=True)
            net = records[-1]["nav"] - capital
            m["top5_months_share_of_net_pnl"] = (sum(pos[:5]) / net) if net > 0 else None
            m["positive_months"] = f"{sum(v > 0 for v in mp.values())}/{len(mp)}"
            if kname == "base":
                alpha = 0.05 / 3
                boot = {}
                for blk in (7, 30):
                    dist = circular_block_bootstrap(exc, blk, 10000, 20261029)
                    boot[str(blk)] = {"lower_one_sided": quantile(dist, alpha),
                                      "ci95": [quantile(dist, 0.025), quantile(dist, 0.975)]}
                m["bootstrap_mean_daily_excess"] = boot
            m["events_sample"] = {s: sleeves[s].events[:6] + (["..."] if len(sleeves[s].events) > 12 else []) +
                                  sleeves[s].events[-6:] for s in SYMS}
            m["events_count"] = {s: len(sleeves[s].events) for s in SYMS}
            m["nav_daily"] = [[iso(r["t"]), round(r["nav"], 6)] for r in records]
            path.write_text(json.dumps({"config": cname, "cost": kname, "segment": seg_name, "metrics": m}, indent=1))
            rows.append({"segment": seg_name, "config": cname, "cost": kname,
                         **{k: m[k] for k in ("net_return", "annualised", "tbill_annualised", "excess_vs_tbill_annualised",
                                              "vol_annual", "sharpe_excess", "max_drawdown", "time_in_market",
                                              "turnover_x", "liquidations", "min_margin_ratio", "beta_to_btc")}})
    # benchmarks
    for kname, cost in proto["costs_per_side_per_leg"].items():
        if kname != "base":
            continue
        bh = buy_hold(start, end, capital, cost)
        rf_list = [rf_daily(r["t"] - DAY_MS) if r["t"] % DAY_MS == 0 else rf_daily(r["t"]) for r in bh[1:]]
        m, rets, exc = metrics(bh, capital, rf_list)
        m["calendar_years"] = {str(y): period_excess(bh, rf_list, max(parse_iso(f"{y}-01-01T00:00:00Z"), start),
                                                     min(parse_iso(f"{y + 1}-01-01T00:00:00Z"), end))
                               for y in range(int(iso(start)[:4]), int(iso(end - 1)[:4]) + 1)}
        (outdir / "benchmark-buyhold-base.json").write_text(json.dumps({"metrics": m}, indent=1))
        rows.append({"segment": seg_name, "config": "BUYHOLD_50_50", "cost": kname,
                     **{k: m[k] for k in ("net_return", "annualised", "tbill_annualised", "excess_vs_tbill_annualised",
                                          "vol_annual", "sharpe_excess", "max_drawdown")}})
    with open(outdir / "summary.csv", "w", newline="") as fh:
        keys = sorted({k for r in rows for k in r})
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


def funding_descriptives():
    """Per calendar year: annualised mean funding (sum of settled rates scaled to 365d), share negative."""
    out = {}
    for s in SYMS:
        by = {}
        for (c, ih, r) in funding[s]:
            by.setdefault(iso(c)[:4], []).append((r, ih))
        out[s] = {y: {"settlements": len(v), "annualised_simple": sum(r for r, _ in v) * 365 /
                      (sum(ih for _, ih in v) / 24.0),
                      "share_negative": sum(1 for r, _ in v if r < 0) / len(v),
                      "max_rate": max(r for r, _ in v), "min_rate": min(r for r, _ in v)}
                  for y, v in sorted(by.items())}
    return out


if which == "descriptives":
    (root / "results" / "E1").mkdir(parents=True, exist_ok=True)
    (root / "results" / "E1" / "funding-descriptives.json").write_text(json.dumps(funding_descriptives(), indent=1))
else:
    for s in (list(proto["segments"]) if which == "all" else [which]):
        run_segment(s)
