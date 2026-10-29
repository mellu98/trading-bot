"""A3: is 120 sessions informative? Per-trade gross under three intrabar conventions, 95% CI vs the
per-trade cost hurdle, daily t-stats. Read-only."""
import csv, json, math, sys
from datetime import datetime, timedelta
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-futures')
from common import *

sessions = load_bars120()
days = sorted({d for d, _ in sessions})
res = {}
for sym, kind in [('MNQ', 'vwap_v1_fixed'), ('MNQ', 'orb'), ('MNQ', 'sweep_mss'), ('MES', 'vwap_v1_fixed'), ('MES', 'orb'), ('MES', 'sweep_mss')]:
    tp, sl = DIST[sym]; pv = PV[sym]
    ledger = list(csv.DictReader((ROOT / f'reports/research-v2/results/{sym}/{kind}/daily_reset_diagnostic/ticks1.0/trades.csv').open()))
    conv = {'stop_first': [], 'first_passage': [], 'target_first': []}
    cost = []; dates = []
    for t in ledger:
        side = int(t['side']); ent = datetime.fromisoformat(t['entry_at']); d = ent.astimezone(NY).date().isoformat()
        s = sessions[d, sym]; i0 = s.idx[ent]; e = float(t['raw_entry']); g = float(t['gross'])
        conv['stop_first'].append(g)
        rx_t, _, _, _ = simulate_exit(s, i0, side, e, tp, sl, 'target_first')
        conv['target_first'].append(side * (rx_t - e) * pv)
        if t['intrabar_ambiguous'] == 'True':
            ix = s.idx[datetime.fromisoformat(t['exit_at']) - timedelta(minutes=1)]
            x0 = e if ix == i0 else s.o[ix]
            stop = e - side * sl; target = e + side * tp
            p_stop = abs(target - x0) / (abs(x0 - stop) + abs(target - x0))
            conv['first_passage'].append(p_stop * g + (1 - p_stop) * tp * pv)
        else:
            conv['first_passage'].append(g)
        cost.append(float(t['fees']) + float(t['execution_cost'])); dates.append(d)
    c = float(np.mean(cost)); n = len(ledger)
    out = {'trades': n, 'cost_per_trade': round(c, 3)}
    for k, v in conv.items():
        v = np.array(v); m = v.mean(); se = v.std(ddof=1) / math.sqrt(n)
        daily = np.array([sum(x for x, dd in zip(v, dates) if dd == day) for day in days]) - np.array(
            [sum(cc for cc, dd in zip(cost, dates) if dd == day) for day in days])
        out[k] = {'gross_total': round(float(v.sum()), 2), 'gross_per_trade': round(float(m), 3), 'se': round(float(se), 3),
                  'gross_t': round(float(m / se), 2), 'gross_ci95': [round(float(m - 1.96 * se), 3), round(float(m + 1.96 * se), 3)],
                  'ci_upper_minus_cost': round(float(m + 1.96 * se - c), 3),
                  'net_total': round(float(v.sum() - sum(cost)), 2),
                  'daily_net_t': round(float(daily.mean() / (daily.std(ddof=1) / math.sqrt(len(days)))), 2),
                  'daily_net_block5_ci95': [round(x, 2) for x in block_bootstrap_mean(daily)]}
    res[f'{sym}/{kind}'] = out
    print(sym, kind, json.dumps(out))
(OUT / 'a3_power.json').write_text(json.dumps(res, indent=2))
