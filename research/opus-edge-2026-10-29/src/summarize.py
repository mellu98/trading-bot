"""Build markdown tables and the mechanical criteria assessment from saved results (no recomputation).

Usage: python -I summarize.py <research_dir>
"""
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
res = root / "results"
lines, assess = [], {}
pct = lambda v: "n/d" if v is None else f"{v * 100:.2f}%"
num = lambda v, d=2: "n/d" if v is None else f"{v:.{d}f}"

# ---------------- E1 ----------------
e1 = res / "E1"
if e1.exists():
    proto = json.loads((root / "protocol" / "E1-funding-carry.json").read_text())
    for seg in proto["segments"]:
        d = e1 / seg
        if not d.exists():
            continue
        lines.append(f"\n### E1 — {seg}\n")
        lines.append("| Config | Costi | Netto | Annuo | T-bill annuo | Eccesso annuo | Vol | Sharpe ecc. | Max DD | Tempo in mercato | Turnover | Liquidazioni | Min margine |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for cname in proto["configurations"]:
            for k in proto["costs_per_side_per_leg"]:
                m = json.loads((d / f"{cname}-{k}.json").read_text())["metrics"]
                lines.append(f"| {cname} | {k} | {pct(m['net_return'])} | {pct(m['annualised'])} | {pct(m['tbill_annualised'])} | "
                             f"{pct(m['excess_vs_tbill_annualised'])} | {pct(m['vol_annual'])} | {num(m['sharpe_excess'])} | "
                             f"{pct(m['max_drawdown'])} | {pct(m['time_in_market'])} | {num(m['turnover_x'], 1)}x | {m['liquidations']} | {num(m['min_margin_ratio'], 3)} |")
        bh = json.loads((d / "benchmark-buyhold-base.json").read_text())["metrics"]
        lines.append(f"| Buy&hold 50/50 | base | {pct(bh['net_return'])} | {pct(bh['annualised'])} | {pct(bh['tbill_annualised'])} | "
                     f"{pct(bh['excess_vs_tbill_annualised'])} | {pct(bh['vol_annual'])} | {num(bh['sharpe_excess'])} | {pct(bh['max_drawdown'])} | 100% | — | — | — |")
        # decomposition (base)
        lines.append("\n| Config (base) | Funding USDT | P&L prezzi (spot+perp, mid) | Fee | Spread | Slippage | Netto USDT | Beta BTC | Mesi positivi | Top-5 mesi / netto |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for cname in proto["configurations"]:
            m = json.loads((d / f"{cname}-base.json").read_text())["metrics"]
            lines.append(f"| {cname} | {m['total_funding']:.2f} | {m['price_pnl_residual']:.2f} | {m['total_fees']:.2f} | {m['total_spread']:.2f} | "
                         f"{m['total_slip']:.2f} | {m['final_nav'] - proto['capital_per_segment_usdt']:.2f} | {num(m['beta_to_btc'], 3)} | "
                         f"{m['positive_months']} | {num(m['top5_months_share_of_net_pnl'])} |")
        lines.append("\n| Config (base) | Anno | Strategia | T-bill | Eccesso |")
        lines.append("|---|---|---:|---:|---:|")
        for cname in proto["configurations"]:
            m = json.loads((d / f"{cname}-base.json").read_text())["metrics"]
            for y, v in m["calendar_years"].items():
                lines.append(f"| {cname} | {y} | {pct(v['strategy'])} | {pct(v['tbill'])} | {pct(v['excess'])} |")
        # mechanical criteria on segment E
        if seg.startswith("E_"):
            for cname in ("E1A_always_on", "E1B_hysteresis_10_0"):
                g = {k: json.loads((d / f"{cname}-{k}.json").read_text())["metrics"] for k in ("base", "adverse", "severe")}
                b = g["base"]
                yrs = b["calendar_years"]
                c = {
                    "c1": g["base"]["excess_vs_tbill_total"] > 0 and g["adverse"]["excess_vs_tbill_total"] > 0 and g["severe"]["net_return"] > 0,
                    "c2": all(b["bootstrap_mean_daily_excess"][blk]["lower_one_sided"] > 0 for blk in ("7", "30")),
                    "c3": b["max_drawdown"] <= 0.10,
                    "c4": b["liquidations"] == 0,
                    "c5": sum(1 for y in ("2024", "2025", "2026") if yrs[y]["excess"] > 0) >= 2,
                }
                if cname.startswith("E1B"):
                    a = json.loads((d / "E1A_always_on-base.json").read_text())["metrics"]
                    c["c6"] = b["net_return"] >= a["net_return"]
                c["ALL_PASS"] = all(c.values())
                assess[cname] = {"criteria": c, "bootstrap": b["bootstrap_mean_daily_excess"]}
    fd = e1 / "funding-descriptives.json"
    if fd.exists():
        desc = json.loads(fd.read_text())
        lines.append("\n### Funding descrittivo (somma annua dei tassi regolati, scala 365 gg)\n")
        lines.append("| Anno | BTC funding annuo | BTC quota negativi | ETH funding annuo | ETH quota negativi |")
        lines.append("|---|---:|---:|---:|---:|")
        for y in desc["BTCUSDT"]:
            b_, e_ = desc["BTCUSDT"][y], desc["ETHUSDT"].get(y, {})
            lines.append(f"| {y} | {pct(b_['annualised_simple'])} | {pct(b_['share_negative'])} | {pct(e_.get('annualised_simple'))} | {pct(e_.get('share_negative'))} |")

# ---------------- E2 ----------------
e2 = res / "E2" / "results.json"
if e2.exists():
    r2 = json.loads(e2.read_text())
    for v, segs in r2["variants"].items():
        lines.append(f"\n### E2 — {v}\n")
        lines.append("| Segmento | Giorni | TOM bp/g | Altri bp/g | Diff. t NW | Strategia annuo (base) | Eccesso vs T-bill | Sharpe ecc. | B&H Sharpe ecc. | Alpha annuo | t alpha | Placebo p | Anni TOM>altri |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for s, x in segs.items():
            st = x["strategy"]["base"]
            lines.append(f"| {s} ({x['first']}–{x['last']}) | {x['trading_days']} | {x['mean_excess_tom_bp']:.2f} | {x['mean_excess_other_bp']:.2f} | "
                         f"{x['difference_t_nw5']:.2f} | {pct(st['ann_return'])} | {pct(st['excess_ann_vs_tbill'])} | {st['sharpe_excess']:.2f} | "
                         f"{x['buyhold']['sharpe_excess']:.2f} | {pct(st['alpha_ann'])} | {st['alpha_t_nw5']:.2f} | {x['placebo_p_value_tom_mean']:.3f} | {x['years_tom_gt_other']} |")
        s2 = segs.get("S2_post_McConnell_Xu")
        if s2:
            c = {
                "c1": s2["difference_bp"] > 0 and s2["difference_t_nw5"] >= 1.96,
                "c2": all(s2["strategy"][k]["excess_ann_vs_tbill"] > 0 for k in ("base", "adverse", "severe")),
                "c3": s2["strategy"]["base"]["alpha_ann"] > 0 and s2["strategy"]["base"]["alpha_t_nw5"] >= 1.96,
                "c4": s2["strategy"]["base"]["sharpe_excess"] > s2["buyhold"]["sharpe_excess"],
                "c5": all(segs[k]["difference_bp"] > 0 for k in ("S2a", "S2b", "S2c")),
                "c6": s2["placebo_p_value_tom_mean"] < 0.05,
                "c7": s2["bootstrap_mean_daily_excess_base_bp"]["lower_one_sided"] > 0,
            }
            c["ALL_PASS"] = all(c.values())
            assess[f"E2:{v}"] = c

(res / "assessment.json").write_text(json.dumps(assess, indent=1))
(res / "tables.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print(json.dumps(assess, indent=1))
