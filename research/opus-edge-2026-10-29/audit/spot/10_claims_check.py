"""Audit 10: recompute headline numbers printed in the four reports from the frozen ledgers
(results JSON / trades.csv), compare at the displayed precision. Read-only."""
import json, csv, statistics
from pathlib import Path
from decimal import Decimal as Dm
import numpy as np
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT'); SD = ROOT / 'research/strategy-discovery-2026'; ED = ROOT / 'research/edge-discovery-round-2'
BO = ROOT / 'reports/binance-spot/breakout-4h/run-1'
OUT = Path(__file__).resolve().parent / 'out'
res = []


def chk(label, got, want, tol):
    ok = got is not None and abs(got - want) <= tol
    res.append((label, round(float(got), 6) if got is not None else None, want, bool(ok)))


def sd(seg, fam, cost, arm):
    folder = 'results-holdout' if seg == 'holdout' else 'results-development-validation'
    return json.loads((SD / folder / f'{seg}-{fam}-{cost}-{arm}.json').read_text())


def ed(fam, seg, cost, arm): return json.loads((ED / 'results' / f'{fam}-{seg}-{cost}-{arm}.json').read_text())


# ---- STRATEGY-RESEARCH-2026 section 5 main table
T5 = {('development', 'A'): (87.96, 79.80, 70.81, 1.15, 26.33), ('development', 'B'): (66.13, 64.52, 62.67, 1.08, 20.05),
      ('validation', 'A'): (18.51, 15.41, 11.93, 0.97, 17.30), ('validation', 'B'): (3.22, 2.19, 1.02, 0.27, 18.42),
      ('holdout', 'A'): (20.12, 17.57, 14.70, 1.22, 13.06), ('holdout', 'B'): (42.54, 41.67, 40.66, 2.34, 8.71)}
for (seg, fam), (b, a, s, sh, dd) in T5.items():
    m = {c: sd(seg, fam, c, 'primary_strategy')['metrics'] for c in ('base', 'adverse', 'severe')}
    chk(f'SR26 {seg} {fam} net base %', m['base']['net_return'] * 100, b, .006); chk(f'SR26 {seg} {fam} net adverse %', m['adverse']['net_return'] * 100, a, .006)
    chk(f'SR26 {seg} {fam} net severe %', m['severe']['net_return'] * 100, s, .006); chk(f'SR26 {seg} {fam} sharpe', m['base']['daily_sharpe_365'], sh, .006)
    chk(f'SR26 {seg} {fam} DD %', m['base']['max_drawdown'] * 100, dd, .006)
# 2024 detail
for fam, (pnl, orders, pf, sortino, mx, turn, fee, spr, slp) in {'A': (201.18, 110, 1.21, 1.95, 66.24, 16.56, 17.63, 1.76, 1.76), 'B': (425.40, 72, 1.49, 4.21, 61.52, 4.76, 5.99, 0.60, 0.60)}.items():
    m = sd('holdout', fam, 'base', 'primary_strategy')['metrics']
    for lab, g, w, t in (('pnl', m['net_pnl'], pnl, .006), ('orders', m['order_count'], orders, 0), ('PF', m['daily_pnl_profit_factor'], pf, .006), ('sortino', m['daily_sortino_365_rf0_all_day_downside_rms'], sortino, .006),
                         ('maxexp%', m['maximum_exposure'] * 100, mx, .006), ('turnover', m['two_way_turnover'], turn, .006), ('fees', m['fees'], fee, .006), ('spread', m['spread'], spr, .006), ('slip', m['slippage'], slp, .006)):
        chk(f'SR26 2024 {fam} {lab}', g, w, t)
# neighbors
for fam, vals in {'A': (10.83, 7.78, 4.36, 25.33), 'B': (29.75, 28.83, 27.77, 16.54)}.items():
    for c, w in zip(('base', 'adverse', 'severe'), vals[:3]): chk(f'SR26 2024 {fam} neighbor {c}', sd('holdout', fam, c, 'neighbor_strategy')['metrics']['net_return'] * 100, w, .006)
    chk(f'SR26 2024 {fam} neighbor DD', sd('holdout', fam, 'base', 'neighbor_strategy')['metrics']['max_drawdown'] * 100, vals[3], .006)
# benchmarks 2024 base
BM = [('A', 'primary_riskcap', 54.04, 2.04, 14.88, 41.21), ('A', 'primary_matched', 33.39, 1.83, 14.12, 26.10), ('A', 'primary_uncapped', 105.34, 1.66, 36.93, 100), ('A', 'primary_fixed_cohort', 95.47, 1.57, 38.75, 100),
      ('A', 'primary_strategy', 20.12, 1.22, 13.06, 26.06), ('B', 'primary_strategy', 42.54, 2.34, 8.71, 25.79), ('B', 'primary_riskcap', 44.55, 1.91, 13.66, 39.02), ('B', 'primary_matched', 42.44, 2.31, 8.46, 25.78),
      ('B', 'primary_uncapped', 96.20, 1.58, 35.45, 100), ('B', 'primary_bh_btc', 127.46, 1.93, 26.15, 100), ('B', 'primary_bh_eth', 61.92, 1.13, 45.26, 100)]
for fam, arm, n, s, d, e in BM:
    m = sd('holdout', fam, 'base', arm)['metrics']
    chk(f'SR26 bench {fam} {arm} net', m['net_return'] * 100, n, .006); chk(f'SR26 bench {fam} {arm} sharpe', m['daily_sharpe_365'], s, .006)
    chk(f'SR26 bench {fam} {arm} DD', m['max_drawdown'] * 100, d, .006); chk(f'SR26 bench {fam} {arm} avgexp', m['average_exposure'] * 100, e, .006)
# yearly
for fam, ys in {'A': (52.03, 50.58, -17.90), 'B': (48.38, 24.56, -10.11)}.items():
    y = sd('development', fam, 'base', 'primary_strategy')['metrics']['yearly']
    for yr, w in zip(('2020', '2021', '2022'), ys): chk(f'SR26 {fam} year {yr}', y[yr]['net_return'] * 100, w, .006)
# regimes / concentration 2024
for fam, (pos, oth, top5pct, wo5) in {'A': (170.06, 31.12, 85.26, 29.66), 'B': (412.83, 12.57, 54.95, 191.63)}.items():
    m = sd('holdout', fam, 'base', 'primary_strategy')['metrics']; rg = m['causal_BTC_regime_pnl']; pnl = np.array(m['daily_pnl']); top5 = np.sort(pnl)[-5:].sum()
    chk(f'SR26 2024 {fam} regime+', rg.get('BTC_90d_positive', 0), pos, .006); chk(f'SR26 2024 {fam} regime other', sum(v for k, v in rg.items() if k != 'BTC_90d_positive'), oth, .006)
    chk(f'SR26 2024 {fam} top5 % of net', top5 / m['net_pnl'] * 100, top5pct, .006); chk(f'SR26 2024 {fam} net w/o top5', m['net_pnl'] - top5, wo5, .006)
m = sd('validation', 'B', 'base', 'primary_strategy')['metrics']; pnl = np.array(m['daily_pnl'])
chk('B 2023 best day % of net', pnl.max() / m['net_pnl'] * 100, 127, 1.0); chk('B 2023 net w/o best day', m['net_pnl'] - pnl.max(), -8.75, .006)
chk('B 2023 net w/o best5', m['net_pnl'] - np.sort(pnl)[-5:].sum(), -142.83, .006)
mp = sd('validation', 'B', 'base', 'primary_riskcap')['metrics']; chk('B 2023 passive pnl', mp['net_pnl'], 451.05, .006); chk('B 2023 B pnl', m['net_pnl'], 32.22, .006)
fr_b = m['fees'] + m['spread'] + m['slippage']; fr_p = mp['fees'] + mp['spread'] + mp['slippage']
chk('B 2023 extra friction vs passive', fr_b - fr_p, 2.56, .006); chk('B 2023 B total costs', fr_b, 9.40, .006)
chk('B 2023 raw marked gap', (mp['net_pnl'] + fr_p) - (m['net_pnl'] + fr_b), 416.27, .006)

# ---- EDGE-DISCOVERY-ROUND-2
E4 = {('H1', 'development_2022'): (-2.94, -4.10, -5.42), ('H1', 'stress_2024'): (-1.73, -3.60, -5.71), ('H2', 'development_2020_2022'): (-2.88, -26.74, -47.10),
      ('H2', 'diagnostic_2023'): (-7.84, -23.08, -37.58), ('H2', 'stress_2024'): (23.03, 7.43, -8.15)}
for (fam, seg), vals in E4.items():
    for c, w in zip(('base', 'adverse', 'severe'), vals): chk(f'ED2 {fam} {seg} {c}', ed(fam, seg, c, 'primary_strategy')['metrics']['net_return'] * 100, w, .006)
for (fam, seg), (raw, fr, net) in {('H1', 'development_2022'): (-18.47, 10.93, -29.40), ('H1', 'stress_2024'): (0.22, 17.55, -17.33), ('H2', 'development_2020_2022'): (249.52, 278.29, -28.77),
                                   ('H2', 'diagnostic_2023'): (76.72, 155.08, -78.36), ('H2', 'stress_2024'): (366.61, 136.32, 230.29)}.items():
    m = ed(fam, seg, 'base', 'primary_strategy')['metrics']; f = m['fees'] + m['spread'] + m['slippage']
    chk(f'ED2 {fam} {seg} friction', f, fr, .006); chk(f'ED2 {fam} {seg} net pnl', m['net_pnl'], net, .006); chk(f'ED2 {fam} {seg} raw', m['net_pnl'] + f, raw, .006)
for fam, vals in {'H1': (-0.73, -2.62, -4.75), 'H2': (6.93, -6.64, -20.18)}.items():
    for c, w in zip(('base', 'adverse', 'severe'), vals): chk(f'ED2 {fam} neighbor {c}', ed(fam, 'stress_2024', c, 'neighbor_strategy')['metrics']['net_return'] * 100, w, .006)
EB = [('H1', 'primary_strategy', -1.73, -0.40, 2.71, 2.27), ('H1', 'primary_riskcap', 42.78, 1.82, 15.54, 39.90), ('H1', 'primary_matched', -2.61, -0.59, 3.49, 2.27),
      ('H2', 'primary_strategy', 23.03, 1.24, 14.55, 30.40), ('H2', 'primary_riskcap', 49.75, 1.97, 15.41, 40.93), ('H2', 'primary_matched', 21.47, 1.28, 11.03, 30.39), ('H2', 'primary_uncapped', 103.07, 1.64, 36.64, 100)]
for fam, arm, n, s, d, e in EB:
    m = ed(fam, 'stress_2024', 'base', arm)['metrics']
    chk(f'ED2 bench {fam} {arm} net', m['net_return'] * 100, n, .006); chk(f'ED2 bench {fam} {arm} sharpe', m['daily_sharpe_365'], s, .006)
    chk(f'ED2 bench {fam} {arm} DD', m['max_drawdown'] * 100, d, .006); chk(f'ED2 bench {fam} {arm} avgexp', m['average_exposure'] * 100, e, .006)
for fam, (act, orders, mx, vol, worst, turn) in {'H1': (38, 47, 73.59, 4.55, -2.56, 14.72), 'H2': (287, 783, 72.98, 19.77, -3.63, 104.35)}.items():
    m = ed(fam, 'stress_2024', 'base', 'primary_strategy')['metrics']
    for lab, g, w, t in (('active', m['active_calendar_days'], act, 0), ('orders', m['order_count'], orders, 0), ('maxexp', m['maximum_exposure'] * 100, mx, .006), ('vol', m['realized_daily_vol_annual_sqrt365'] * 100, vol, .006),
                         ('worst', m['worst_daily_return'] * 100, worst, .006), ('turnover', m['two_way_turnover'], turn, .006)):
        chk(f'ED2 2024 {fam} {lab}', g, w, t)
m = ed('H1', 'stress_2024', 'base', 'primary_strategy')['metrics']; chk('ED2 H1 hourly DD', m['hourly_drawdown_secondary'] * 100, 4.03, .006)
m = ed('H2', 'stress_2024', 'base', 'primary_strategy')['metrics']; pnl = np.array(m['daily_pnl']); t5 = np.sort(pnl)[-5:].sum()
chk('ED2 H2 2024 top5 pnl', t5, 218.15, .006); chk('ED2 H2 2024 top5 %', t5 / m['net_pnl'] * 100, 94.73, .006); chk('ED2 H2 fees', m['fees'], 113.60, .006)
for yr, w in zip(('2020', '2021', '2022'), (-3.95, 24.37, -18.70)): chk(f'ED2 H2 year {yr}', ed('H2', 'development_2020_2022', 'base', 'primary_strategy')['metrics']['yearly'][yr]['return'] * 100, w, .006)

# ---- breakout PROJECT-VERDICT section C/D
tt = list(csv.DictReader((BO / 'reserved_test/base/strategy/trades.csv').open())); nets = [float(t['net']) for t in tt]
dur = [(int(t['exit_ns']) - int(t['entry_ns'])) / 3.6e12 for t in tt]
chk('BO test expectancy', statistics.mean(nets), 0.287, .0006); chk('BO test win %', sum(n > 0 for n in nets) / len(nets) * 100, 34.62, .006)
chk('BO payoff sd', statistics.stdev(nets), 3.32, .006); chk('BO median hold h', statistics.median(dur), 68, 0); chk('BO max hold h', max(dur), 192, 0)
chk('BO best trade', max(nets), 16.18, .006); chk('BO rest 25', sum(nets) - max(nets), -8.71, .006)
met = json.loads((BO / 'reserved_test/base/strategy/metrics.json').read_text())
chk('BO positive months', sum(v > 0 for v in met['monthly_marked_net'].values()), 3, 0); chk('BO exposure % hours', met['exposure_hours_upper_bound'] / met['total_hours'] * 100, 30.9, .06)
chk('BO gross raw', float(met['gross_raw']), 10.00, .006); chk('BO fees', float(met['fees']), 2.11, .006)

bad = [r for r in res if not r[3]]
(OUT / 'claims-check.json').write_text(json.dumps({'checked': len(res), 'failed': bad, 'all': res}, indent=1))
print('checked', len(res), 'failed', len(bad))
for r in bad: print('FAIL', r)
