"""B2: BTC 4h breakout + Timestral 28M/209M veto (reports/binance-spot/timestral-abc). Prove whether the
0/79 acceptance is a property of the model or of the gate geometry. Read-only: zips are read in memory."""
import csv, io, json, sys, zipfile
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-futures')
from common import ROOT, OUT

H = 3_600_000_000_000
ABC = ROOT / 'reports/binance-spot/timestral-abc'
HURDLE = 0.002402882974988590390614641      # runner.py:9

# 1h bars from the frozen archives (same manifest the baseline loader uses), parsed in memory
man = json.loads((ROOT / 'reports/binance-spot/breakout-4h/acquisition.json').read_text())
hours = []
for item in man['archives']:
    y = int(item['month'][:4])
    with zipfile.ZipFile(ROOT / item['path']) as z:
        (m,) = z.infolist()
        for row in csv.reader(io.StringIO(z.read(m).decode())):
            t = int(row[0]); start_ns = t * 1000 if y >= 2025 else t * 1_000_000
            hours.append((start_ns, float(row[1]), float(row[2]), float(row[3]), float(row[4])))
hours.sort()
assert len(hours) == 16056, len(hours)
four = {}   # end_ns -> (high, close)
for k in range(0, len(hours), 4):
    blk = hours[k:k + 4]
    assert blk[0][0] % (4 * H) == 0 and all(blk[j + 1][0] - blk[j][0] == H for j in range(3))
    four[blk[0][0] + 4 * H] = (max(b[2] for b in blk), blk[-1][4])
ends = sorted(four)
close = {e: four[e][1] for e in ends}

fc = {}
for model in ('28M', '209M'):
    fc[model] = {}
    for line in (ABC / f'{model}-forecasts.jsonl').open():
        r = json.loads(line)
        fc[model][r['origin_ns']] = r

res = {'hurdle': HURDLE}
# all-origin distribution of the model's own predicted step-2 (8h) return from its anchor P[O]
for model in fc:
    r2 = []; r1 = []
    for o, r in fc[model].items():
        if r.get('status') == 'ok' and o >= 1767225600_000_000_000 and o in close:   # 2026 origins
            r2.append(r['quantiles'][1][10] / close[o] - 1); r1.append(r['quantiles'][0][10] / close[o] - 1)
    r2 = np.array(r2); r1 = np.array(r1)
    res[f'{model}_all_2026_origins'] = {'n': len(r2), 'step2_median_return_p01_p50_p99': [float(np.quantile(r2, q)) for q in (.01, .5, .99)],
                                        'step2_frac_above_hurdle': float(np.mean(r2 > HURDLE)), 'step2_max': float(r2.max()),
                                        'step1_frac_above_hurdle': float(np.mean(r1 > HURDLE))}

for model, arm in (('28M', 'B'), ('209M', 'C')):
    for seg in ('primary', 'secondary'):
        for scen in ('base', 'adverse', 'severe'):
            dec = list(csv.DictReader((ABC / f'run-1/{seg}/{scen}/{arm}/filter-decisions.csv').open()))
            out = Counter(); rb = []; rm = []
            for d in dec:
                T = int(d['decision_ns']); O = T - 4 * H
                cT = float(d['current_close']); pO = close[O]
                assert abs(cT - close[T]) < 1e-6
                med = float(d['median_step2']) if d['median_step2'] else None
                rec = fc[model].get(O)
                out['decisions'] += 1
                out['reason:' + d['reason']] += 1
                if med is None or 'quantiles' not in (rec or {}):
                    out['no_forecast_available'] += 1
                    continue
                assert abs(rec['quantiles'][1][10] - med) < 1e-6
                out['recorded_allowed'] += d['allowed'] == 'True'
                out['close_T_gt_P_O'] += cT > pO
                out['close_T_gt_prior20_high'] += cT > max(four[e][0] for e in ends[ends.index(T) - 20:ends.index(T)])
                out['recomputed_allowed'] += med > cT * (1 + HURDLE)
                out['persistence_forecaster_allowed'] += pO > cT * (1 + HURDLE)
                out['own_anchor_allowed(median_O/P_O-1>hurdle)'] += med / pO - 1 > HURDLE
                fresh = fc[model].get(T)
                if fresh and fresh.get('status') == 'ok':
                    out['fresh_origin_T_step1_allowed'] += fresh['quantiles'][0][10] / cT - 1 > HURDLE
                    out['fresh_origin_T_step2_allowed'] += fresh['quantiles'][1][10] / cT - 1 > HURDLE
                rb.append(cT / pO - 1); rm.append(med / pO - 1)
            if seg == 'primary' and scen == 'base':
                res[f'{model}_primary_base_returns'] = {
                    'breakout_bar_return_close_T_over_P_O_min_median': [float(min(rb)), float(np.median(rb))],
                    'model_own_return_median_O_over_P_O_min_median_max': [float(min(rm)), float(np.median(rm)), float(max(rm))]}
            res[f'{model}/{seg}/{scen}'] = dict(out)
            print(model, seg, scen, dict(out))

# matched A-ledger outcomes (descriptive only): which of the 26 primary/base A trades would pass a non-stale rule
A = list(csv.DictReader((ABC / 'run-1/primary/base/A/trades.csv').open()))
for model in fc:
    passed = defaultdict(list)
    for t in A:
        T = int(t['entry_ns']); O = T - 4 * H; cT = close[T]; pO = close[O]
        med = fc[model][O]['quantiles'][1][10]; fresh = fc[model][T]
        net = float(Decimal(t['net']))
        passed['own_anchor' if med / pO - 1 > HURDLE else 'own_anchor_veto'].append(net)
        passed['fresh_T_step2' if fresh['quantiles'][1][10] / cT - 1 > HURDLE else 'fresh_T_step2_veto'].append(net)
    res[f'{model}_matched_A_trades'] = {k: {'n': len(v), 'sum_net': round(sum(v), 4)} for k, v in passed.items()}
    print(model, res[f'{model}_matched_A_trades'])
for k in ('28M_all_2026_origins', '209M_all_2026_origins', '28M_primary_base_returns', '209M_primary_base_returns'):
    print(k, res[k])
(OUT / 'b2_btc_abc_filter.json').write_text(json.dumps(res, indent=2))
