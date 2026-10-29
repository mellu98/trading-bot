"""B3: independent check of forecast alignment and accuracy claims (BTC 4h and MNQ/MES 1m). Read-only."""
import csv, hashlib, io, json, sys, zipfile
from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-locoframe-Desktop-TRADING-BOT/2d482412-acc4-41a5-92e7-3ae12d820bd8/scratchpad/audit-futures')
from common import ROOT, OUT

H = 3_600_000_000_000
res = {}
# ---------- BTC ----------
man = json.loads((ROOT / 'reports/binance-spot/breakout-4h/acquisition.json').read_text())
hours = []
for item in man['archives']:
    y = int(item['month'][:4])
    with zipfile.ZipFile(ROOT / item['path']) as z:
        (m,) = z.infolist()
        for row in csv.reader(io.StringIO(z.read(m).decode())):
            t = int(row[0]); hours.append((t * 1000 if y >= 2025 else t * 1_000_000, float(row[4])))
hours.sort()
ends = [hours[k][0] + 4 * H for k in range(0, len(hours), 4)]
closes = [hours[k + 3][1] for k in range(0, len(hours), 4)]
pos = {e: i for i, e in enumerate(ends)}
lo, hi = 1767225600_000_000_000, 1790812800_000_000_000      # 2026-01-01 .. 2026-10-01 (primary)
for model in ('28M', '209M'):
    rows = [json.loads(l) for l in (ROOT / f'reports/binance-spot/timestral-abc/{model}-forecasts.jsonl').open()]
    ok = [r for r in rows if r.get('status') == 'ok']
    sha_ok = 0; sha_n = 0
    for r in ok[::50]:                                 # sample of origins: context must end exactly at origin
        i = pos[r['origin_ns']]
        t = np.array(closes[i - 255:i + 1], dtype='<f4')[None, None, :]
        sha_n += 1; sha_ok += hashlib.sha256(t.tobytes()).hexdigest() == r['input_sha256']
    acc = {}
    for h in (1, 2, 3, 6):
        err_m = []; err_p = []; err_m_shift = []
        for r in ok:
            o = r['origin_ns']; i = pos[o]
            if not (lo <= o < hi) or o + h * 4 * H >= hi + 0 or i + h >= len(closes):
                continue
            if ends[i + h] >= hi:
                continue
            a = closes[i + h]; med = r['quantiles'][h - 1][10]
            err_m.append(abs(a - med)); err_p.append(abs(a - closes[i]))
            if i + h + 1 < len(closes):
                err_m_shift.append(abs(closes[i + h + 1] - med))
        acc[h] = {'n': len(err_m), 'mae_model': round(float(np.mean(err_m)), 3), 'mae_persistence': round(float(np.mean(err_p)), 3),
                  'mae_model_vs_target_shifted_+1step': round(float(np.mean(err_m_shift)), 3)}
    res[f'BTC_{model}'] = {'input_sha_sample_ok': f'{sha_ok}/{sha_n}', 'accuracy_primary': acc}
    print('BTC', model, res[f'BTC_{model}'])

# ---------- MNQ/MES 28M (fixed 15-min grid, as in timestral_experiment.forecast_scores) ----------
fc = {}
for line in (ROOT / 'reports/timestral-28m-experiment/forecasts.jsonl').open():
    p = json.loads(line)['prediction']; fc[p['symbol'], p['origin'], p['variant']] = p['values']
bars = defaultdict(list)
for r in csv.DictReader((ROOT / 'reports/real-simulation/bars.csv').open()):
    bars[r['symbol'], datetime.fromisoformat(r['start']).date().isoformat()].append(r)
for sym in ('MNQ', 'MES'):
    for variant in ('target_only', 'past_covariates'):
        out = {}
        for hi_, h in enumerate((1, 3, 5, 10, 15)):
            em = []; ep = []
            for (s, d), bb in bars.items():
                if s != sym: continue
                for n in range(20, len(bb), 15):
                    if n + h > len(bb): continue
                    origin = datetime.fromisoformat(bb[n - 1]['end']).isoformat()
                    med = fc[sym, origin, variant][hi_][10]
                    a = float(bb[n + h - 1]['close']); last = float(bb[n - 1]['close'])
                    em.append(abs(a - med)); ep.append(abs(a - last))
            out[h] = {'n': len(em), 'mae_model': round(float(np.mean(em)), 3), 'mae_last_close': round(float(np.mean(ep)), 3)}
        res[f'{sym}_{variant}_28M'] = out
        print(sym, variant, out)
(OUT / 'b3_forecast_quality.json').write_text(json.dumps(res, indent=2))
