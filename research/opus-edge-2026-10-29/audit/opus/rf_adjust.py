"""Re-express prior A/B/H2 results in excess of the 3m T-bill (DTB3). Read-only on prior results."""
import json, glob, csv, math, datetime as dt, bisect, sys
ROOT = "/Users/locoframe/Desktop/TRADING BOT/"
rf_d, rf_v = [], []
for r in csv.DictReader(open(ROOT + "research/opus-edge-2026-10-29/cache/fred/DTB3.csv")):
    if r["DTB3"] in ("", "."):
        continue
    rf_d.append(r["observation_date"]); rf_v.append(float(r["DTB3"]) / 100 / 360)
def rf_for(day):
    return rf_v[bisect.bisect_left(rf_d, day) - 1]
def stats(path):
    d = json.load(open(path))
    eq, ts = d["equity"], d["times"]
    rets = [b / a - 1 for a, b in zip(eq, eq[1:])]
    days = [dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%d") for t in ts[:-1]]
    rfs = [rf_for(x) for x in days]
    ex = [r - f for r, f in zip(rets, rfs)]
    m = lambda x: sum(x) / len(x)
    sd = lambda x: math.sqrt(sum((v - m(x)) ** 2 for v in x) / (len(x) - 1))
    tb = 1.0
    for f in rfs: tb *= 1 + f
    return {"net": eq[-1] / eq[0] - 1, "tbill": tb - 1, "sharpe_raw": m(rets) / sd(rets) * math.sqrt(365),
            "sharpe_excess": m(ex) / sd(ex) * math.sqrt(365), "vol": sd(rets) * math.sqrt(365), "n": len(rets)}
out = {}
for seg, pat in (("2023-validation", "results-development-validation/validation-{f}-base-primary_{a}.json"),
                 ("2024-test", "results-holdout/holdout-{f}-base-primary_{a}.json")):
    for fam in ("A", "B"):
        for arm in ("strategy", "riskcap", "matched", "bh_btc"):
            p = ROOT + "research/strategy-discovery-2026/" + pat.format(f=fam, a=arm)
            try:
                s = stats(p)
            except FileNotFoundError:
                continue
            out[f"{seg}:{fam}:{arm}"] = s
            print(f"{seg:16s} {fam} {arm:9s} net {s['net']*100:7.2f}%  tbill {s['tbill']*100:5.2f}%  SR_raw {s['sharpe_raw']:5.2f}  SR_excess {s['sharpe_excess']:5.2f}  vol {s['vol']*100:5.1f}%  n={s['n']}")
json.dump(out, open(sys.argv[1], "w"), indent=1)
