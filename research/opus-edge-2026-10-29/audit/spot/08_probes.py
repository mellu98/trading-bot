"""Audit 08: look-ahead probes + SMA168 de-facto latch diagnostic (read-only, scratch journals).
(a) breakout: rerun ORIGINAL simulate on bars truncated at cut dates; trades closed before the cut
    must be identical to the full-run trades (future bars cannot influence past decisions).
(b) SMA168: when were entries rejected and what was the drawdown budget left at that time?"""
import sys, json, shutil, importlib.util
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
HERE = Path(__file__).resolve().parent; OUT = HERE / 'out'; WORK = OUT / 'probe-journals'
ROOT = Path('/Users/locoframe/Desktop/TRADING BOT'); sys.path.insert(0, str(ROOT / 'src')); sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('repro02', HERE / '02_breakout_repro.py'); M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
R = M.R
spec3 = importlib.util.spec_from_file_location('repro03', HERE / '03_sma_repro.py'); S3 = importlib.util.module_from_spec(spec3); spec3.loader.exec_module(S3)


def ts(s): return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()) * 10**9


def breakout_probe():
    bars = M.load_bars(); start = next(i for i, b in enumerate(bars) if R.iso(b.start)[:7] >= '2026-01'); out = {}
    if (WORK / 'full').exists(): shutil.rmtree(WORK / 'full')
    r, j = R.engine(WORK / 'full', 'base', False)
    try: full = R.simulate(r, bars, start, len(bars))
    finally: j.close()
    for cut in ('2026-03-01', '2026-06-01', '2026-08-20'):
        c = ts(cut); end = next(i for i, b in enumerate(bars) if b.start >= c)
        p = WORK / ('cut-' + cut)
        if p.exists(): shutil.rmtree(p)
        r, j = R.engine(p, 'base', False)
        try: part = R.simulate(r, bars[:end], start, end)
        finally: j.close()
        a = [(t['entry_ns'], t['exit_ns'], t['net']) for t in full['trades'] if t['exit_ns'] < c - 3600 * 10**9]
        b = [(t['entry_ns'], t['exit_ns'], t['net']) for t in part['trades'] if t['exit_reason'] != 'split_terminal_close']
        sa = [s['at'] for s in full['signals'] if s['at'] < c - 3600 * 10**9]; sb = [s['at'] for s in part['signals']]
        out[cut] = {'closed_trades_before_cut_identical': a == b[:len(a)] and len(b) >= len(a), 'n_trades_compared': len(a), 'signals_identical': sa == sb[:len(sa)]}
    return out


def sma_latch():
    bars = S3.load_bars(); spans = {'development': ('2025-01', '2025-07'), 'validation': ('2025-07', '2025-10'), 'test': ('2025-10', '2026-01')}; out = {}
    for name, (lo, hi) in spans.items():
        start = next(i for i, b in enumerate(bars) if S3.S.iso(b.start)[:7] >= lo); end = next((i for i, b in enumerate(bars) if S3.S.iso(b.start)[:7] >= hi), len(bars))
        r, j = S3.engine(WORK / ('sma-' + name)); log = []
        orig_enter = r.enter
        def enter():
            before = dict(r.rejections); ok = orig_enter()
            if not ok:
                risk = r._mark_risk(); reason = [k for k in r.rejections if r.rejections[k] != before.get(k, 0)]
                log.append({'at': S3.S.iso(r.now), 'reason': reason, 'drawdown': round(risk.drawdown, 4), 'dd_budget_left': round(20 - risk.drawdown, 4)})
            return ok
        r.enter = enter
        try: res = S3.S.simulate(r, bars, start, end)
        finally: j.close()
        adm = [x for x in log if 'initial_cost_risk_or_size_admission' in x['reason']]
        out[name] = {'rejections': len(log), 'admission_rejections': len(adm), 'first_admission_rejection': adm[0] if adm else None,
                     'admission_rejections_with_dd_budget_below_5.3': sum(x['dd_budget_left'] < 5.3 for x in adm),
                     'last_trade_exit': res['trades'][-1]['exit_at'] if res['trades'] else None, 'trades': len(res['trades'])}
    return out


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    rep = {'breakout_truncation_probe': breakout_probe(), 'sma_latch': sma_latch()}
    (OUT / 'probes.json').write_text(json.dumps(rep, indent=1, default=str)); print(json.dumps(rep, indent=1, default=str))
