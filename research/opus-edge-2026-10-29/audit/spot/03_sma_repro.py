"""Audit 03: reproduce the frozen SMA168 BTC spot research (reports/binance-spot/research)
with the ORIGINAL simulate/summarize, journals in scratch; plus EXPLORATORY 1h-later fill."""
import sys, json, csv, io, zipfile, calendar, importlib.util, shutil
from pathlib import Path
from decimal import Decimal
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT')
OUT = Path(__file__).resolve().parent / 'out'; WORK = OUT / 'sma-journals'
sys.path.insert(0, str(ROOT / 'src'))
spec = importlib.util.spec_from_file_location('audit_sma_runner', ROOT / 'reports/binance-spot/research/runner.py')
S = importlib.util.module_from_spec(spec); sys.modules[spec.name] = S; spec.loader.exec_module(S)
from mnq_local.binance_spot import SpotSpec, dec
from mnq_local.replay import AtomicJournal
SR = ROOT / 'reports/binance-spot/research'


def load_bars():
    prov = json.loads((SR / 'acquisition.json').read_text()); bars = []
    for item in prov['archives']:
        p = ROOT / item['path']; assert S.sha(p) == item['sha256']
        with zipfile.ZipFile(p) as z: content = z.read(z.infolist()[0])
        part = [S.parse_row(r, item['month']) for r in csv.reader(io.StringIO(content.decode()))]
        y, m = map(int, item['month'].split('-')); assert len(part) == calendar.monthrange(y, m)[1] * 24
        for b in part:
            assert not bars or b.start == bars[-1].end; bars.append(b)
    assert len(bars) == 9504; return bars


def simulate_delayed(r, bars, start, end, delay=1):
    """Copy of S.simulate; entry and SMA-exit executed at the open of hour i+1+delay
    (delay=0 must reproduce the original exactly; asserted in main)."""
    closes = [b.close for b in bars[:start]]; pending_buy = False; due_buy = None; pending_sell = False; due_sell = None; equity = []; signals = []
    for i in range(start, end):
        b = bars[i]; r.now = b.start; r.set_quote(b.open)
        if r.spot['position']:
            if dec(r.quote['bid']) <= dec(r.spot['position']['stop']): r.spot['pending_exit'] = 'adverse_stop_gap'
            elif pending_sell and i >= due_sell: r.request_exit('sma_exit')
            r.exit_or_protect()
        if pending_sell and (i >= due_sell or not r.spot['position']): pending_sell = False
        if pending_buy and i >= due_buy:
            if not r.spot['position']: r.enter()
            pending_buy = False
        if r.spot['position'] and b.low * dec('.9999') <= dec(r.spot['position']['stop']):
            stop = dec(r.spot['position']['stop']); r.now = b.end; r.set_quote(stop / dec('.9999')); r.quote['bid'] = str(stop)
            r.request_exit('intrabar_stop'); r.exit_or_protect(ignore_time=True); r.closed[-1]['exit_timestamp_is_hour_bound'] = True
            pending_sell = False
        r.now = b.end; r.set_quote(b.close)
        if i == end - 1 and r.spot['position']: r.request_exit('split_terminal_close')
        r.exit_or_protect(ignore_time=True)
        if not r.spot['position']: pending_sell = False
        closes.append(b.close); long_cross = S.cross(closes); ma = S.sma(closes)
        if i < end - 1:
            if r.spot['position'] and ma is not None and b.close < ma:
                if not pending_sell: pending_sell = True; due_sell = i + 1 + delay
            elif not r.spot['position'] and long_cross and not pending_buy:
                pending_buy = True; due_buy = i + 1 + delay; signals.append({'at': S.iso(b.end), 'side': 'LONG_DELAYED'})
        risk = r._mark_risk(); equity.append({'at': S.iso(b.end), 'net': r.net() + risk.unrealized, 'drawdown': risk.drawdown, 'cash': r.spot['cash']})
    return {'trades': r.closed, 'equity': equity, 'signals': signals, 'rejections': dict(r.rejections), 'risk_halts': r.halts, 'final_cash': r.spot['cash'], 'global_halt': r.state['halt'] == 'max_drawdown'}


def engine(path):
    if path.exists(): shutil.rmtree(path)
    path.mkdir(parents=True)
    cfg = S.ResearchConfig(); spec = SpotSpec('BTCUSDT', '.01', '.00001', '.00001', '9000', '5')
    j = AtomicJournal(path / 'state.sqlite', cfg, [spec], lock_root=path / 'locks'); return S.HistoricalSpot(cfg, spec, j), j


def main():
    bars = load_bars(); spans = {'development': ('2025-01', '2025-07'), 'validation': ('2025-07', '2025-10'), 'test': ('2025-10', '2026-01')}
    rep = {}
    for name, (lo, hi) in spans.items():
        start = next(i for i, b in enumerate(bars) if S.iso(b.start)[:7] >= lo); end = next((i for i, b in enumerate(bars) if S.iso(b.start)[:7] >= hi), len(bars))
        r, j = engine(WORK / ('orig-' + name))
        try: res = S.simulate(r, bars, start, end); m = S.summarize(res)
        finally: j.close()
        saved = json.loads((SR / 'run-1' / name / 'metrics.json').read_text())
        same = json.dumps(m, sort_keys=True, default=str) == json.dumps(saved, sort_keys=True, default=str)
        rep[name] = {'exact_metrics_equal': same, 'trades': m['trades'], 'net': m['net'], 'pf': m['profit_factor'], 'boot5': m['uncertainty']['blocks']['5'], 'rejections': m['rejections']}
        for d in (0, 1):
            r, j = engine(WORK / (f'delay{d}-' + name))
            try: res = simulate_delayed(r, bars, start, end, d); md = S.summarize(res)
            finally: j.close()
            rep[name][f'delay{d}'] = {'trades': md['trades'], 'net': md['net'], 'pf': md['profit_factor'], 'gross_raw': md['gross_raw'], 'exit_reasons': md['exit_reasons']}
            if d == 0: assert md['net'] == m['net'] and md['trades'] == m['trades'], ('copy mismatch', name, md['net'], m['net'])
        print(name, json.dumps(rep[name], default=str)[:700], flush=True)
    (OUT / 'sma-repro.json').write_text(json.dumps(rep, indent=1, default=str))


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True); main()
