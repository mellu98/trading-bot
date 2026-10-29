"""A2: (1) independent causal re-implementation of VWAP-z and ORB signals + V2 risk sequencing, compared
with the frozen ledgers; (2) random-direction null over every eligible minute under the same engine;
(3) first-passage 'fair' resolution of ambiguous bars; (4) side-minus-opposite t-stats; (5) roll-day sensitivity."""
import csv, json, math, sys
from datetime import datetime, timedelta
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-futures')
from common import *

sessions = load_bars120()
days = sorted({d for d, _ in sessions})
ROLL_DAYS = {'MNQ': {'2026-06-15', '2026-06-16', '2026-09-14', '2026-09-15', '2026-09-16'},
             'MES': {'2026-06-15', '2026-06-16', '2026-09-14', '2026-09-15'}}


def vwap_z(s):
    typical = (s.h + s.l + s.c) / 3
    vwap = np.cumsum(typical * s.v) / np.cumsum(s.v)
    resid = s.c - vwap
    z = np.full(len(s.c), np.nan)
    for i in range(19, len(s.c)):
        sd = np.std(resid[i - 19:i + 1])          # causal: bars <= i only
        z[i] = resid[i] / sd if sd > 0 else 0.
    return z


def vwap_signals(s):
    z = vwap_z(s); prev = 0; out = []
    for i in range(len(s.c)):
        if not math.isfinite(z[i]):
            out.append(0); continue
        zone = 1 if z[i] < -2.5 else -1 if z[i] > 2.5 else 0
        out.append(zone if zone != prev else 0); prev = zone
    return out


def orb_signals(s, n=15):
    out = [0] * len(s.c); used = set()
    hi = s.h[:n].max(); lo = s.l[:n].min()
    for i in range(n, len(s.c)):
        side = 1 if s.c[i] >= hi + .25 else -1 if s.c[i] <= lo - .25 else 0
        if side and side not in used:
            used.add(side); out[i] = side
    return out


def replay_day(s, sig):
    """V2 Replay sequencing (engine.py:158-227), daily-reset account, one symbol, stop-first exits."""
    tp, sl = DIST[s.sym]; pv = PV[s.sym]
    fees = 2 * (.25 + .35 + reg_fee(s.date)); execc = 2 * TICK * pv
    tr = []; realized = 0.; consecutive = 0; day_trades = 0; halt = False; pending = None; open_until = -1
    for i in range(len(s.c)):
        if pending is not None:
            side = pending; pending = None
            if not halt and day_trades < 10 and consecutive < 3 and realized > -200:
                rx, reason, ix, amb = simulate_exit(s, i, side, s.o[i], tp, sl, 'stop_first', realized, fees, execc)
                gross = side * (rx - s.o[i]) * pv; net = gross - fees - execc
                tr.append({'entry_at': s.start[i].isoformat(), 'side': side, 'net': net, 'gross': gross})
                day_trades += 1; open_until = ix
        if tr and i == open_until:              # trade closes during bar i -> state updated before bar-i decision
            net = tr[-1]['net']; realized += net
            consecutive = consecutive + 1 if net < 0 else 0
            if realized <= -200 or consecutive >= 3:
                halt = True
        flat = open_until <= i
        if sig[i] and flat and in_window(s.end(i)) and not halt and day_trades < 10 and consecutive < 3 \
                and realized > -200 and pending is None:
            pending = sig[i]
    return tr


summary = {}
for kind, gen in (('vwap_v1_fixed', vwap_signals), ('orb', orb_signals)):
    for sym in ('MNQ', 'MES'):
        mine = []
        for d in days:
            mine.extend(replay_day(sessions[d, sym], gen(sessions[d, sym])))
        path = ROOT / f'reports/research-v2/results/{sym}/{kind}/daily_reset_diagnostic/ticks1.0/trades.csv'
        ledger = list(csv.DictReader(path.open()))
        a = {(t['entry_at'], int(t['side'])) for t in ledger}
        b = {(t['entry_at'], t['side']) for t in mine}
        summary[f'{sym}/{kind}'] = {'independent_trades': len(mine), 'ledger_trades': len(ledger),
                                    'common_entries': len(a & b), 'only_ledger': len(a - b), 'only_independent': len(b - a),
                                    'independent_net': round(sum(t['net'] for t in mine), 2),
                                    'ledger_net': round(sum(float(t['net']) for t in ledger), 2),
                                    'examples_only_ledger': sorted(a - b)[:3], 'examples_only_independent': sorted(b - a)[:3]}
        print(sym, kind, summary[f'{sym}/{kind}'], flush=True)

# (2) random-direction null at every eligible minute, single isolated trade per minute and side
null = {}
for sym in ('MNQ', 'MES'):
    tp, sl = DIST[sym]; pv = PV[sym]
    acc = {p: {'long': [], 'short': []} for p in ('stop_first', 'target_first', 'ohlc_path')}
    namb = 0; ntot = 0
    for d in days:
        s = sessions[d, sym]
        for i in range(1, len(s.c)):
            if not in_window(s.start[i]):
                continue
            for side, lab in ((1, 'long'), (-1, 'short')):
                for p in acc:
                    rx, reason, ix, amb = simulate_exit(s, i, side, s.o[i], tp, sl, p)
                    acc[p][lab].append(side * (rx - s.o[i]) * pv)
                    if p == 'stop_first':
                        namb += amb; ntot += 1
    null[sym] = {p: {'long_mean_gross': round(float(np.mean(v['long'])), 3), 'short_mean_gross': round(float(np.mean(v['short'])), 3),
                     'random_direction_mean_gross': round(float((np.mean(v['long']) + np.mean(v['short'])) / 2), 3)}
                 for p, v in acc.items()}
    null[sym]['n_trades_per_side'] = len(acc['stop_first']['long'])
    null[sym]['ambiguous_fraction'] = round(namb / ntot, 4)
    print('NULL', sym, null[sym], flush=True)

# (3)+(4)+(5) on the frozen ledgers
extra = {}
for sym, kind in [('MNQ', 'vwap_v1_fixed'), ('MNQ', 'orb'), ('MNQ', 'sweep_mss'), ('MES', 'vwap_v1_fixed'), ('MES', 'orb'), ('MES', 'sweep_mss')]:
    tp, sl = DIST[sym]; pv = PV[sym]
    path = ROOT / f'reports/research-v2/results/{sym}/{kind}/daily_reset_diagnostic/ticks1.0/trades.csv'
    ledger = list(csv.DictReader(path.open()))
    fair = []; diff = []; ex_roll_net = 0.; roll_net = 0.; roll_trades = 0
    for t in ledger:
        side = int(t['side']); ent = datetime.fromisoformat(t['entry_at']); d = ent.astimezone(NY).date().isoformat()
        s = sessions[d, sym]; i0 = s.idx[ent]; e = float(t['raw_entry']); g = float(t['gross'])
        if t['intrabar_ambiguous'] == 'True':
            ix = s.idx[datetime.fromisoformat(t['exit_at']) - timedelta(minutes=1)]
            x0 = e if ix == i0 else s.o[ix]          # path start inside the exit bar
            stop = e - side * sl; target = e + side * tp
            d_stop = abs(x0 - stop); d_tgt = abs(target - x0)
            # driftless first-passage probability of touching the stop first from x0
            p_stop = d_tgt / (d_stop + d_tgt) if (d_stop + d_tgt) > 0 else 1.
            fair.append(p_stop * g + (1 - p_stop) * tp * pv)
        else:
            fair.append(g)
        rx_o, _, _, _ = simulate_exit(s, i0, -side, e, tp, sl, 'stop_first')
        diff.append(g - (-side * (rx_o - e) * pv))
        if d in ROLL_DAYS[sym]:
            roll_net += float(t['net']); roll_trades += 1
        else:
            ex_roll_net += float(t['net'])
    cost = sum(float(t['fees']) + float(t['execution_cost']) for t in ledger)
    diff = np.array(diff)
    extra[f'{sym}/{kind}'] = {
        'gross_first_passage_fair_estimate': round(float(np.sum(fair)), 2),
        'net_first_passage_fair_estimate': round(float(np.sum(fair) - cost), 2),
        'side_minus_opposite_mean': round(float(diff.mean()), 3),
        'side_minus_opposite_t': round(float(diff.mean() / (diff.std(ddof=1) / math.sqrt(len(diff)))), 2),
        'roll_day_trades': roll_trades, 'roll_day_net': round(roll_net, 2), 'net_excluding_roll_days': round(ex_roll_net, 2)}
    print('EXTRA', sym, kind, extra[f'{sym}/{kind}'], flush=True)

(OUT / 'a2_null_reimpl.json').write_text(json.dumps({'independent_reimplementation': summary, 'random_direction_null': null,
                                                      'ledger_extras': extra}, indent=2, default=str))
