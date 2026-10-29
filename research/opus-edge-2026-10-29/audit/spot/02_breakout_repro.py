"""Audit 02: reproduce the frozen BTC 4h breakout ledgers with the ORIGINAL code
(imported read-only), journals redirected to the scratch folder, then run an
EXPLORATORY one-hour-later fill sensitivity (not a selection, not a new test).

Nothing is written inside the project tree: we never call runner.load() (it
saves data-quality.json) nor runner.run(); runner.engine() receives a scratch path.
"""
import sys, json, csv, io, zipfile, calendar, importlib.util, shutil, math
from pathlib import Path
from decimal import Decimal
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT')
OUT = Path(__file__).resolve().parent / 'out'
WORK = OUT / 'breakout-journals'
sys.path.insert(0, str(ROOT / 'src'))
spec = importlib.util.spec_from_file_location('audit_breakout_runner', ROOT / 'reports/binance-spot/breakout-4h/runner.py')
R = importlib.util.module_from_spec(spec); sys.modules[spec.name] = R; spec.loader.exec_module(R)
old = R.old
from mnq_local.binance_spot import dec
B = ROOT / 'reports/binance-spot/breakout-4h'


def load_bars():
    manifest = json.loads((B / 'acquisition.json').read_text()); bars = []
    for item in manifest['archives']:
        p = ROOT / item['path']
        assert R.sha(p) == item['sha256']
        with zipfile.ZipFile(p) as z:
            content = z.read(z.infolist()[0])
        part = [old.parse_row(row, item['month']) for row in csv.reader(io.StringIO(content.decode('utf-8')))]
        y, m = map(int, item['month'].split('-'))
        assert len(part) == calendar.monthrange(y, m)[1] * 24
        for b in part:
            assert not bars or b.start == bars[-1].end
            bars.append(b)
    assert len(bars) == 16056
    return bars


def simulate_delayed(r, bars, start, end, delay=1):
    """Copy of runner.simulate; ONLY change: a 4h-close decision is executed at the
    open of native hour i+1+delay instead of i+1 (delay=0 reproduces the original)."""
    four = R.aggregate4(bars); completed = {b.end: b for b in four}; history = [b for b in four if b.end <= bars[start].start]
    pending_atr = None; due_buy = None; pending_sell = False; due_sell = None; equity = []; signals = []; exposure = 0
    for i in range(start, end):
        b = bars[i]; r.now = b.start; r.set_quote(b.open)
        if r.spot['position']:
            if dec(r.quote['bid']) <= dec(r.spot['position']['stop']): r.spot['pending_exit'] = 'adverse_stop_gap'
            elif pending_sell and i >= due_sell: r.request_exit('channel_exit')
            r.exit_or_protect()
        if pending_sell and (i >= due_sell or not r.spot['position']): pending_sell = False
        if pending_atr is not None and i >= due_buy:
            if not r.spot['position'] and i < end - 1: r.enter(pending_atr)
            pending_atr = None
        if r.benchmark and i == start: r.enter(Decimal(0))
        exposure += int(r.spot['position'] is not None)
        if r.spot['position'] and not r.benchmark and b.low * (1 - r.half) <= dec(r.spot['position']['stop']):
            stop = dec(r.spot['position']['stop']); r.now = b.end; r.set_quote(stop / (1 - r.half)); r.quote['bid'] = str(stop)
            r.request_exit('intrabar_stop'); r.exit_or_protect(); r.closed[-1]['exit_timestamp_is_hour_bound'] = True
            pending_sell = False
        r.now = b.end; r.set_quote(b.close)
        if i == end - 1 and r.spot['position']: r.request_exit('split_terminal_close')
        r.exit_or_protect()
        if b.end in completed:
            history.append(completed[b.end]); buy, sell, atr = R.decision(history)
            if i < end - 1 and not r.benchmark:
                if r.spot['position'] and sell: pending_sell = True; due_sell = i + 1 + delay
                elif not r.spot['position'] and buy and pending_atr is None:
                    pending_atr = atr; due_buy = i + 1 + delay; signals.append({'at': b.end, 'side': 'LONG_DELAYED', 'atr14': str(atr)})
        risk = r._mark_risk(); equity.append({'at': R.iso(b.end), 'net': r.net() + risk.unrealized, 'drawdown': risk.drawdown, 'cash': r.spot['cash']})
    return {'trades': r.closed, 'equity': equity, 'signals': signals, 'rejections': dict(r.rejections), 'risk_halts': r.halts,
            'final_cash': r.spot['cash'], 'global_halt': r.state['halt'] == 'max_drawdown', 'exposure_hours_upper_bound': exposure}


def run_arm(tag, bars, start, end, scenario, benchmark, fn):
    path = WORK / tag / scenario / ('bh' if benchmark else 'strategy')
    if path.exists(): shutil.rmtree(path)
    r, j = R.engine(path, scenario, benchmark)
    try:
        res = fn(r, bars, start, end)
        m = R.additional_metrics(res, old.summarize(res))
    finally:
        j.close()
    return res, m


def main():
    bars = load_bars()
    seg = {'observed_development': ('2025-01', '2026-01'), 'reserved_test': ('2026-01', '2026-10')}
    report = {'reproduction': {}, 'delay_1h_exploratory': {}, 'delay_2h_exploratory': {}}
    exact = []
    for segment, (lo, hi) in seg.items():
        start = next(i for i, b in enumerate(bars) if R.iso(b.start)[:7] >= lo)
        end = next((i for i, b in enumerate(bars) if R.iso(b.start)[:7] >= hi), len(bars))
        for scenario in R.COSTS:
            ms = {}
            for name, bench in (('strategy', False), ('buy_hold_100', True)):
                res, m = run_arm('orig-' + segment, bars, start, end, scenario, bench, R.simulate)
                saved = json.loads((B / 'run-1' / segment / scenario / name / 'metrics.json').read_text())
                ok = json.dumps(m, sort_keys=True, default=str) == json.dumps(saved, sort_keys=True, default=str)
                same_net = m['net'] == saved['net'] and m['trades'] == saved['trades']
                exact.append((segment, scenario, name, ok, same_net))
                ms[name] = m
                if not bench:
                    # also check delay=0 version of our copy equals the original
                    res0, m0 = run_arm('copy0-' + segment, bars, start, end, scenario, False, lambda r, b, s, e: simulate_delayed(r, b, s, e, 0))
                    assert m0['net'] == m['net'] and m0['trades'] == m['trades'], ('copy mismatch', segment, scenario)
            report['reproduction'][segment + '/' + scenario] = {k: {'trades': v['trades'], 'net': v['net'], 'pf': v['profit_factor'],
                'dd': v['max_drawdown_hour_close_including_liquidation_costs'], 'boot5': v['uncertainty']['blocks']['5']} for k, v in ms.items()}
            for d, key in ((1, 'delay_1h_exploratory'), (2, 'delay_2h_exploratory')):
                res, m = run_arm(f'delay{d}-' + segment, bars, start, end, scenario, False, lambda r, b, s, e, d=d: simulate_delayed(r, b, s, e, d))
                q = m['quarterly_marked_net']
                report[key][segment + '/' + scenario] = {'trades': m['trades'], 'net': m['net'], 'pf': m['profit_factor'],
                    'dd': m['max_drawdown_hour_close_including_liquidation_costs'], 'gross_raw': m['gross_raw'], 'fees': m['fees'],
                    'positive_quarters': sum(x > 0 for x in q.values()), 'quarters': q, 'boot5': m['uncertainty']['blocks']['5'],
                    'exit_reasons': m['exit_reasons'], 'rejections': m['rejections'], 'halts': m['risk_halts']}
                print(key, segment, scenario, 'N', m['trades'], 'net', float(dec(m['net'])), 'PF', m['profit_factor'], 'grossraw', float(dec(m['gross_raw'])), flush=True)
    report['exact_metrics_json_equal'] = [list(x) for x in exact]
    (OUT / 'breakout-repro.json').write_text(json.dumps(report, indent=1, default=str))
    for x in exact: print('REPRO', *x)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True); main()
