"""Audit 05 -- EXPLORATORY ONLY, on ALREADY-OBSERVED data. Not a new strategy test, not a
selection, no parameter search. Computes the raw statistic behind Strategy-Discovery family C
(as frozen in protocol.json C_rules) that the frozen loader never computed:

  BTC hourly log return r[t]=log(C[t]/C[t-1]); z[t]=(r[t]-mean(r[t-168:t]))/sd(r[t-168:t],ddof=1)
  (168 past hours, current excluded); signal z>1 (strict).
  Feature bar t ends at H. Primary entry = open of bar t+2 (H+1h, one FULL hour after the
  signal bar closes); exit = open of bar t+3 (1h hold). ETH open-to-open return.
  Base round trip: buy raw*(1+s/2)(1+slip)(1+fee), sell raw*(1-s/2)(1-slip)(1-fee); s=2bp,
  slip=1bp, fee=10bp  =>  ~24bp. Adverse/severe also reported.

Gap policy: irregular bars (close_time != open+1h-1ms) or missing hours are NaN on a full
hourly grid; any signal whose 169-close window or ETH entry/exit opens touch a NaN is skipped.
Data: cached official archives (research/strategy-discovery-2026/data/1h), Dec-2019..Nov-2024.
"""
import csv, io, json, math, zipfile, calendar
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT'); SD = ROOT / 'research/strategy-discovery-2026'
OUT = Path(__file__).resolve().parent / 'out'
H = 3600


def months(lo, hi):
    y, m = map(int, lo.split('-')); r = []
    while f'{y:04}-{m:02}' < hi:
        r.append(f'{y:04}-{m:02}'); m += 1
        if m == 13: y += 1; m = 1
    return r


def load(symbol):
    rows = {}; irregular = []; quality = {}
    for mon in months('2019-12', '2024-12'):
        p = SD / 'data/1h' / symbol / f'{symbol}-1h-{mon}.zip'
        with zipfile.ZipFile(p) as z:
            content = z.read(z.namelist()[0]).decode()
        n = 0
        for row in csv.reader(io.StringIO(content)):
            o, c = int(row[0]), int(row[6])
            assert len(str(o)) == 13, 'pre-2025 archives must be milliseconds'
            t = o // 1000
            if o % 1000 or t % H:
                irregular.append((symbol, mon, row[0], row[6], 'unaligned')); continue
            if c != (t + H) * 1000 - 1:
                irregular.append((symbol, mon, datetime.fromtimestamp(t, timezone.utc).isoformat(), (c - o) / 1000, 'irregular_duration')); continue
            rows[t] = (float(row[1]), float(row[4])); n += 1
        y, m = map(int, mon.split('-'))
        quality[mon] = {'regular_bars': n, 'expected': calendar.monthrange(y, m)[1] * 24}
    return rows, irregular, quality


def main():
    btc, irr_b, q_b = load('BTCUSDT'); eth, irr_e, q_e = load('ETHUSDT')
    t0 = int(datetime(2019, 12, 1, tzinfo=timezone.utc).timestamp()); t1 = int(datetime(2024, 12, 1, tzinfo=timezone.utc).timestamp())
    times = np.arange(t0, t1, H); n = len(times)
    cb = np.array([btc.get(int(t), (np.nan, np.nan))[1] for t in times]); oe = np.array([eth.get(int(t), (np.nan, np.nan))[0] for t in times])
    ce = np.array([eth.get(int(t), (np.nan, np.nan))[1] for t in times])
    with np.errstate(invalid='ignore', divide='ignore'):
        r = np.concatenate([[np.nan], np.diff(np.log(cb))])
    # vectorised z with exact 168 window excluding current
    z = np.full(n, np.nan)
    for j in range(168, n):
        past = r[j - 168:j]
        if not np.isfinite(r[j]) or not np.all(np.isfinite(past)): continue
        sd = np.std(past, ddof=1)
        if sd > 0: z[j] = (r[j] - past.mean()) / sd
    costs = {'base': (.001, .0001, .0002), 'adverse': (.0015, .0005, .001), 'severe': (.002, .001, .002)}

    def rt(o_in, o_out, fee, slip, spread):
        return (o_out * (1 - spread / 2) * (1 - slip) * (1 - fee)) / (o_in * (1 + spread / 2) * (1 + slip) * (1 + fee)) - 1

    def label_year(t): return datetime.fromtimestamp(int(t), timezone.utc).year
    segs = {'dev_2020_2022': (datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2023, 1, 1, tzinfo=timezone.utc)),
            'val_2023': (datetime(2023, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 1, tzinfo=timezone.utc)),
            'holdout_2024_JanNov': (datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 12, 1, tzinfo=timezone.utc))}
    out = {'label': 'EXPLORATORY on already-observed data; NOT a promotion test; frozen C rules, no tuning',
           'irregular_bars': {'BTCUSDT': irr_b, 'ETHUSDT': irr_e},
           'missing_hours_2024': {s: int(sum(1 for t in times if t >= segs['holdout_2024_JanNov'][0].timestamp() and int(t) not in d)) for s, d in (('BTCUSDT', btc), ('ETHUSDT', eth))},
           'regular_hours_2024': {s: int(sum(1 for t in times if t >= segs['holdout_2024_JanNov'][0].timestamp() and int(t) in d)) for s, d in (('BTCUSDT', btc), ('ETHUSDT', eth))}}
    # baseline: all valid ETH open->open hourly returns
    for delay, name in ((1, 'primary_entry_H_plus_1h'), (2, 'neighbor_entry_H_plus_2h'), (0, 'DIAGNOSTIC_same_boundary_entry_H')):
        res = {}
        for seg, (a, b) in segs.items():
            a, b = a.timestamp(), b.timestamp()
            idx = [j for j in range(168, n - 2 - delay) if np.isfinite(z[j]) and z[j] > 1 and a <= times[j + 1 + delay] < b and times[j + 2 + delay] < b]
            sig_all = [j for j in range(168, n) if np.isfinite(z[j]) and z[j] > 1 and a <= times[j] < b]
            valid = [j for j in idx if np.isfinite(oe[j + 1 + delay]) and np.isfinite(oe[j + 2 + delay]) and oe[j + 1 + delay] > 0]
            g = np.array([oe[j + 2 + delay] / oe[j + 1 + delay] - 1 for j in valid])
            nets = {c: np.array([rt(oe[j + 1 + delay], oe[j + 2 + delay], *costs[c]) for j in valid]) for c in costs}
            # unconditional baseline over the same segment (all valid consecutive ETH opens)
            base_idx = [j for j in range(n - 1) if a <= times[j] < b and np.isfinite(oe[j]) and np.isfinite(oe[j + 1])]
            ub = np.array([oe[j + 1] / oe[j] - 1 for j in base_idx])
            # coverage: hours where z is computable
            zcov = int(np.sum(np.isfinite(z[(times >= a) & (times < b)])))
            yrs = (b - a) / (365.25 * 86400)
            sd = float(np.std(g, ddof=1)) if len(g) > 1 else float('nan')
            # signal clustering diagnostic and HAC-ish check via non-overlapping holds: holds never overlap (1h), but signals cluster
            consecutive = int(sum(1 for k in range(1, len(valid)) if valid[k] == valid[k - 1] + 1))
            res[seg] = {
                'signals_z_gt_1_with_valid_window': len(sig_all), 'tradable_signals_valid_entry_exit': len(valid),
                'hours_with_computable_z': zcov, 'calendar_years': round(yrs, 4), 'signals_per_calendar_year': round(len(valid) / yrs, 1),
                'signals_per_computable_year': round(len(valid) / (zcov / 8766), 1) if zcov else None,
                'mean_gross_bp': round(float(g.mean()) * 1e4, 3) if len(g) else None, 'median_gross_bp': round(float(np.median(g)) * 1e4, 3) if len(g) else None,
                'sd_gross_bp': round(sd * 1e4, 2), 't_stat_iid_gross': round(float(g.mean() / (sd / math.sqrt(len(g)))), 2) if len(g) > 1 else None,
                'hit_rate_gross_pos': round(float(np.mean(g > 0)), 4) if len(g) else None,
                'mean_net_bp': {c: round(float(v.mean()) * 1e4, 3) for c, v in nets.items()},
                'compounded_net_return_all_signals': {c: round(float(np.prod(1 + v) - 1), 6) for c, v in nets.items()},
                'compounded_gross_return': round(float(np.prod(1 + g) - 1), 6),
                'unconditional_eth_hourly_mean_bp': round(float(ub.mean()) * 1e4, 3), 'unconditional_n': len(ub),
                'consecutive_signal_pairs': consecutive,
                'breakeven_needs_gross_bp_ge': 24.0,
            }
        out[name] = res
    # per calendar year (primary)
    per_year = {}
    for yr in range(2020, 2025):
        a = datetime(yr, 1, 1, tzinfo=timezone.utc).timestamp(); b = min(datetime(yr + 1, 1, 1, tzinfo=timezone.utc).timestamp(), t1)
        valid = [j for j in range(168, n - 3) if np.isfinite(z[j]) and z[j] > 1 and a <= times[j + 2] < b and times[j + 3] < b and np.isfinite(oe[j + 2]) and np.isfinite(oe[j + 3])]
        g = np.array([oe[j + 3] / oe[j + 2] - 1 for j in valid]); nb = np.array([rt(oe[j + 2], oe[j + 3], *costs['base']) for j in valid])
        sd = float(np.std(g, ddof=1))
        per_year[str(yr)] = {'n': len(valid), 'per_year': round(len(valid) / ((b - a) / (365.25 * 86400)), 1), 'mean_gross_bp': round(float(g.mean()) * 1e4, 3),
                             't_iid': round(float(g.mean() / (sd / math.sqrt(len(g)))), 2), 'mean_net_base_bp': round(float(nb.mean()) * 1e4, 3), 'compounded_net_base': round(float(np.prod(1 + nb) - 1), 4)}
    out['primary_per_calendar_year'] = per_year
    # threshold-free check: correlation of z (all hours) with next-next ETH return, to see if any lead-lag survives the 1h delay
    ok = [j for j in range(168, n - 3) if np.isfinite(z[j]) and np.isfinite(oe[j + 2]) and np.isfinite(oe[j + 3])]
    zz = np.array([z[j] for j in ok]); gg = np.array([oe[j + 3] / oe[j + 2] - 1 for j in ok])
    out['diagnostic_corr_z_vs_ETH_ret_H+1_to_H+2'] = round(float(np.corrcoef(zz, gg)[0, 1]), 5)
    ok0 = [j for j in range(168, n - 2) if np.isfinite(z[j]) and np.isfinite(oe[j + 1]) and np.isfinite(oe[j + 2])]
    out['diagnostic_corr_z_vs_ETH_ret_H_to_H+1_same_boundary'] = round(float(np.corrcoef([z[j] for j in ok0], [oe[j + 2] / oe[j + 1] - 1 for j in ok0])[0, 1]), 5)
    (OUT / 'family-c-exploratory.json').write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != 'irregular_bars'}, indent=1, default=str))
    print('irregular BTC', len(irr_b), irr_b[:10]); print('irregular ETH', len(irr_e))


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True); main()
