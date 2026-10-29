"""A1: reconcile the six reported futures ledgers from raw bars; gross vs net; ambiguity bounds;
opposite-side decomposition; t-stats. Read-only on the project."""
import csv, json, math, sys
from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-futures')
from common import *

sessions = load_bars120()
days = sorted({d for d, _ in sessions})
assert len(days) == 120
ARMS = [('MNQ', 'vwap_v1_fixed'), ('MNQ', 'orb'), ('MNQ', 'sweep_mss'),
        ('MES', 'vwap_v1_fixed'), ('MES', 'orb'), ('MES', 'sweep_mss')]
REPORTED = {('MNQ', 'vwap_v1_fixed'): (627, -3240.00), ('MNQ', 'orb'): (176, -1091.94), ('MNQ', 'sweep_mss'): (294, -379.42),
            ('MES', 'vwap_v1_fixed'): (633, -2547.95), ('MES', 'orb'): (173, -694.68), ('MES', 'sweep_mss'): (241, -828.95)}
out = {}
for sym, kind in ARMS:
    path = ROOT / f'reports/research-v2/results/{sym}/{kind}/daily_reset_diagnostic/ticks1.0/trades.csv'
    trades = list(csv.DictReader(path.open()))
    tp, sl = DIST[sym]
    pv = PV[sym]
    chk = defaultdict(int)
    rows = []
    for t in trades:
        side = int(t['side'])
        entry_at = datetime.fromisoformat(t['entry_at'])
        d = entry_at.astimezone(NY).date().isoformat()
        s = sessions[d, sym]
        i0 = s.idx[entry_at]
        raw_entry = float(t['raw_entry'])
        # timing: signal bar ends exactly when entry bar starts (next-bar-open fill; no same-bar fill)
        sig_start = datetime.fromisoformat(t['signal_bar_start'])
        chk['timing_ok'] += (sig_start + timedelta(minutes=1) == entry_at == datetime.fromisoformat(t['signal_at']))
        chk['entry_is_next_open'] += (abs(s.o[i0] - raw_entry) < 1e-9)
        chk['contract_ok'] += (t['contract'] == s.contract)
        # costs
        fee_exp = 2 * (.25 + .35 + reg_fee(d))
        chk['fee_ok'] += abs(float(t['fees']) - fee_exp) < 1e-9
        chk['exec_ok'] += abs(float(t['execution_cost']) - 2 * TICK * pv) < 1e-9
        chk['net_identity_ok'] += abs(float(t['gross']) - float(t['fees']) - float(t['execution_cost']) - float(t['net'])) < 1e-6
        chk['gross_identity_ok'] += abs(side * (float(t['raw_exit']) - raw_entry) * pv - float(t['gross'])) < 1e-6
        chk['brackets_ok'] += (abs(float(t['stop']) - (raw_entry - side * sl)) < 1e-9 and abs(float(t['target']) - (raw_entry + side * tp)) < 1e-9)
        # independent exit re-simulation (stop-first engine convention)
        rx, reason, ix, amb = simulate_exit(s, i0, side, raw_entry, tp, sl, 'stop_first')
        same = (abs(rx - float(t['raw_exit'])) < 1e-9 and reason == t['reason']
                and s.end(ix) == datetime.fromisoformat(t['exit_at']) and amb == (t['intrabar_ambiguous'] == 'True'))
        chk['exit_resim_match'] += same
        if not same:
            chk['exit_mismatch_reasons_' + t['reason']] += 1
        rx_t, reason_t, _, _ = simulate_exit(s, i0, side, raw_entry, tp, sl, 'target_first')
        rx_h, reason_h, _, _ = simulate_exit(s, i0, side, raw_entry, tp, sl, 'ohlc_path')
        # opposite side, same entry/bracket, engine convention
        rx_o, reason_o, _, amb_o = simulate_exit(s, i0, -side, raw_entry, tp, sl, 'stop_first')
        rx_ot, _, _, _ = simulate_exit(s, i0, -side, raw_entry, tp, sl, 'target_first')
        rows.append({'date': d, 'side': side, 'gross': float(t['gross']), 'net': float(t['net']),
                     'fees': float(t['fees']), 'exec': float(t['execution_cost']), 'amb': t['intrabar_ambiguous'] == 'True',
                     'gross_target_first': side * (rx_t - raw_entry) * pv,
                     'gross_ohlc_path': side * (rx_h - raw_entry) * pv,
                     'gross_opposite': -side * (rx_o - raw_entry) * pv,
                     'gross_opposite_target_first': -side * (rx_ot - raw_entry) * pv,
                     'trigger_bar_move': side * (s.c[i0 - 1] - s.o[i0 - 1]) if i0 >= 1 else 0.0})
    n = len(rows)
    g = np.array([r['gross'] for r in rows]); netv = np.array([r['net'] for r in rows])
    cost = np.array([r['fees'] + r['exec'] for r in rows])
    daily_g = np.array([sum(r['gross'] for r in rows if r['date'] == d) for d in days])
    daily_n = np.array([sum(r['net'] for r in rows if r['date'] == d) for d in days])
    gt = np.array([r['gross_target_first'] for r in rows]); gh = np.array([r['gross_ohlc_path'] for r in rows])
    go = np.array([r['gross_opposite'] for r in rows]); got = np.array([r['gross_opposite_target_first'] for r in rows])
    res = {
        'reported_trades_net': REPORTED[sym, kind],
        'ledger_trades': n, 'ledger_net': round(float(netv.sum()), 2),
        'gross': round(float(g.sum()), 2), 'fees': round(sum(r['fees'] for r in rows), 2), 'slippage': round(sum(r['exec'] for r in rows), 2),
        'cost_per_trade': round(float(cost.mean()), 4),
        'checks': {k: int(v) for k, v in chk.items()},
        'gross_per_trade_mean': round(float(g.mean()), 3), 'gross_per_trade_sd': round(float(g.std(ddof=1)), 3),
        'gross_trade_t': round(float(g.mean() / (g.std(ddof=1) / math.sqrt(n))), 2),
        'net_trade_t': round(float(netv.mean() / (netv.std(ddof=1) / math.sqrt(n))), 2),
        'daily_gross_mean': round(float(daily_g.mean()), 3), 'daily_gross_sd': round(float(daily_g.std(ddof=1)), 3),
        'daily_gross_t': round(float(daily_g.mean() / (daily_g.std(ddof=1) / math.sqrt(120))), 2),
        'daily_gross_block5_ci95': [round(v, 3) for v in block_bootstrap_mean(daily_g)],
        'daily_net_t': round(float(daily_n.mean() / (daily_n.std(ddof=1) / math.sqrt(120))), 2),
        'daily_net_block5_ci95': [round(v, 3) for v in block_bootstrap_mean(daily_n)],
        'ambiguous_trades': int(sum(r['amb'] for r in rows)),
        'gross_if_ambiguous_target_first_UPPER_BOUND': round(float(gt.sum()), 2),
        'net_if_ambiguous_target_first_UPPER_BOUND': round(float(gt.sum() - cost.sum()), 2),
        'gross_ohlc_path_heuristic': round(float(gh.sum()), 2),
        'net_ohlc_path_heuristic': round(float(gh.sum() - cost.sum()), 2),
        'opposite_side_same_entries_gross_stop_first': round(float(go.sum()), 2),
        'opposite_side_same_entries_gross_target_first': round(float(got.sum()), 2),
        'convention_bias_estimate_per_trade(avg of side and opposite, stop_first)': round(float((g + go).mean() / 2), 3),
        'directional_signal_value_per_trade(half of side minus opposite)': round(float((g - go).mean() / 2), 3),
        'breakeven_gross_win_rate_TP_vs_SL': round(sl / (tp + sl), 4),
        'breakeven_net_win_rate': round((sl * pv + float(cost.mean())) / ((tp + sl) * pv), 4),
        'observed_target_rate': round(float(np.mean(g > 0)), 4),
        'trigger_bar_in_signal_direction_frac': round(float(np.mean([r['trigger_bar_move'] > 0 for r in rows])), 3),
    }
    out[f'{sym}/{kind}'] = res
    print(sym, kind, json.dumps(res, indent=None))
(OUT / 'a1_ledger_audit.json').write_text(json.dumps(out, indent=2))
