"""E2 — turn-of-the-month (TOM) timing on the US equity market (CRSP value-weighted, French library).

Usage: python -I tom.py <research_dir>
Reads protocol/E2-turn-of-month.json; refuses to overwrite results.
"""
import io
import json
import math
import pathlib
import random
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import (circular_block_bootstrap, max_drawdown, mean, newey_west_t, ols_alpha_beta_hac,  # noqa: E402
                    quantile, sharpe, stdev)

root = pathlib.Path(sys.argv[1])
proto = json.loads((root / "protocol" / "E2-turn-of-month.json").read_text())
outdir = root / "results" / "E2"
outdir.mkdir(parents=True, exist_ok=True)
out_path = outdir / "results.json"
if out_path.exists():
    raise SystemExit(f"refusing to overwrite {out_path}")

z = zipfile.ZipFile(root / "cache" / "french" / "F-F_Research_Data_Factors_daily_CSV.zip")
text = z.read(z.namelist()[0]).decode("latin-1")
rows = []
for line in text.splitlines():
    parts = [p.strip() for p in line.split(",")]
    if len(parts) >= 5 and parts[0].isdigit() and len(parts[0]) == 8:
        rows.append((parts[0], float(parts[1]) / 100.0, float(parts[4]) / 100.0))
dates = [r[0] for r in rows]
xm = [r[1] for r in rows]  # market excess return
rf = [r[2] for r in rows]
n = len(rows)


def tom_flags(before, after):
    """before: number of last trading days of month included (1 => day -1); after: first N days of next month."""
    flags = [0] * n
    month = [d[:6] for d in dates]
    for i in range(n):
        # position within month from the end / start
        j = i
        while j + 1 < n and month[j + 1] == month[i]:
            j += 1
        k = i
        while k - 1 >= 0 and month[k - 1] == month[i]:
            k -= 1
        from_end = j - i + 1      # 1 => last trading day
        from_start = i - k + 1    # 1 => first trading day
        if from_end <= before and j + 1 < n:  # needs a next month in the sample to complete the window
            flags[i] = 1
        if from_start <= after and k > 0:     # needs a previous month in sample
            flags[i] = 1
    return flags


def strategy_returns(flags, cost):
    """Hold market on flagged days, T-bill otherwise; cost per side charged on window entry/exit days."""
    s = []
    for i in range(n):
        if flags[i]:
            r = xm[i] + rf[i]
            if i == 0 or not flags[i - 1]:
                r -= cost  # bought at previous close
            if i == n - 1 or not flags[i + 1]:
                r -= cost  # sold at this close
        else:
            r = rf[i]
        s.append(r)
    return s


def segment_idx(a, b):
    return [i for i in range(n) if a <= dates[i] <= b]


def nav_path(r):
    v, out = 1.0, [1.0]
    for x in r:
        v *= 1 + x
        out.append(v)
    return out


def analyse(idx, flags, costs, seed, L):
    res = {"first": dates[idx[0]], "last": dates[idx[-1]], "trading_days": len(idx)}
    on = [xm[i] for i in idx if flags[i]]
    off = [xm[i] for i in idx if not flags[i]]
    res["tom_days"] = len(on)
    res["mean_excess_tom_bp"] = mean(on) * 1e4
    res["mean_excess_other_bp"] = mean(off) * 1e4
    # difference via regression of daily excess on the TOM dummy, HAC (lags 5)
    y = [xm[i] for i in idx]
    d = [float(flags[i]) for i in idx]
    res["tom_days_per_month"] = len(on) / len({dates[i][:6] for i in idx})
    res["difference_bp"] = (mean(on) - mean(off)) * 1e4
    # t-stat of the difference using the NW t of the per-day contrast series
    contrast = [(y[k] / mean(d) if d[k] else -y[k] / (1 - mean(d))) for k in range(len(y))]
    res["difference_t_nw5"] = newey_west_t(contrast, 5)
    total_excess = sum(y)
    res["share_of_market_excess_on_tom_days"] = sum(on) / total_excess if total_excess > 0 else None
    # strategy vs buy & hold
    bh = [xm[i] + rf[i] for i in idx]
    rfi = [rf[i] for i in idx]
    years = len(idx) / 252.0
    bh_nav = nav_path(bh)
    tb_nav = nav_path(rfi)
    res["buyhold"] = {"ann_return": bh_nav[-1] ** (1 / years) - 1, "vol": stdev(bh) * math.sqrt(252),
                      "sharpe_excess": sharpe([xm[i] for i in idx], 252), "max_dd": max_drawdown(bh_nav)}
    res["tbill_ann"] = tb_nav[-1] ** (1 / years) - 1
    res["strategy"] = {}
    for cname, c in costs.items():
        s_all = strategy_returns(flags, c)
        s = [s_all[i] for i in idx]
        ex = [s[k] - rfi[k] for k in range(len(idx))]
        nav = nav_path(s)
        al, be, ta = ols_alpha_beta_hac(ex, [xm[i] for i in idx], 5)
        res["strategy"][cname] = {
            "ann_return": nav[-1] ** (1 / years) - 1, "excess_ann_vs_tbill": nav[-1] ** (1 / years) - tb_nav[-1] ** (1 / years),
            "vol": stdev(s) * math.sqrt(252), "sharpe_excess": sharpe(ex, 252), "max_dd": max_drawdown(nav),
            "alpha_daily_bp": al * 1e4, "alpha_ann": al * 252, "beta": be, "alpha_t_nw5": ta,
            "time_in_market": mean([float(flags[i]) for i in idx]),
        }
    # per-year stability: TOM mean minus other mean
    by_year = {}
    for i in idx:
        yv = dates[i][:4]
        by_year.setdefault(yv, [[], []])[0 if flags[i] else 1].append(xm[i])
    diffs = {yv: (mean(v[0]) - mean(v[1])) * 1e4 for yv, v in by_year.items() if v[0] and v[1]}
    res["years_tom_gt_other"] = f"{sum(1 for v in diffs.values() if v > 0)}/{len(diffs)}"
    res["per_year_difference_bp"] = {k: round(v, 2) for k, v in sorted(diffs.items())}
    # placebo: random contiguous windows of the same length per month, outside TOM days
    rng = random.Random(seed)
    months = {}
    for pos, i in enumerate(idx):
        months.setdefault(dates[i][:6], []).append(i)
    tom_mean = mean(on)
    cand_sums = []  # per month: summed excess of every eligible non-TOM window of length L
    for mlist in months.values():
        sums = [sum(xm[j] for j in mlist[k:k + L]) for k in range(0, len(mlist) - L + 1)
                if not any(flags[j] for j in mlist[k:k + L])]
        if sums:
            cand_sums.append(sums)
    placebo = []
    for _ in range(proto["placebo_reps"]):
        placebo.append(sum(rng.choice(s) for s in cand_sums) / (L * len(cand_sums)))
    placebo.sort()
    res["placebo_p_value_tom_mean"] = sum(1 for v in placebo if v >= tom_mean) / len(placebo)
    res["placebo_mean_bp"] = mean(placebo) * 1e4
    # block bootstrap of the strategy-minus-buyhold Sharpe? report CI of mean excess of TOM strategy
    s_base = strategy_returns(flags, costs["base"])
    ex_base = [s_base[i] - rf[i] for i in idx]
    dist = circular_block_bootstrap(ex_base, 21, proto["bootstrap_reps"], seed)
    res["bootstrap_mean_daily_excess_base_bp"] = {"lower_one_sided": quantile(dist, proto["alpha"]) * 1e4,
                                                  "ci95": [quantile(dist, 0.025) * 1e4, quantile(dist, 0.975) * 1e4]}
    return res


results = {"protocol_id": proto["id"], "data_first": dates[0], "data_last": dates[-1], "variants": {}}
for vname, w in proto["variants"].items():
    flags = tom_flags(w["before"], w["after"])
    vres = {}
    for sname, (a, b) in proto["segments"].items():
        idx = segment_idx(a, b)
        vres[sname] = analyse(idx, flags, proto["costs_per_side"], proto["seed"], w["before"] + w["after"])
    results["variants"][vname] = vres
out_path.write_text(json.dumps(results, indent=1))
for vname, v in results["variants"].items():
    for sname, r in v.items():
        st = r["strategy"]["base"]
        print(vname, sname, r["first"], r["last"], "TOMbp", round(r["mean_excess_tom_bp"], 2), "other",
              round(r["mean_excess_other_bp"], 2), "t", round(r["difference_t_nw5"], 2), "alpha_t",
              round(st["alpha_t_nw5"], 2), "SR", round(st["sharpe_excess"], 2), "BH SR",
              round(r["buyhold"]["sharpe_excess"], 2), "placebo p", r["placebo_p_value_tom_mean"])
