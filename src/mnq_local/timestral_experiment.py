"""Isolated, fixed-parameter Timestral-28M experiment on V5 historical replay.

No broker, live mode, strategy promotion, independent OOS claim or threshold search.
Use the model environment for `infer`, the existing V5 environment for `prepare`
and `compare`. All model calls use the original checksum-verified official adapter.
"""
import argparse
from collections import defaultdict
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import statistics
import time

import numpy as np
from mnq_timestral.schema import Request, Prediction, HORIZONS, LEVELS, dumps
from mnq_timestral.model import PINS, SOURCE_REVISION, OfficialAdapter, provision
from mnq_timestral.data import horizon_targets, file_hash
from mnq_timestral.strategy import Candidate, Filter
from .replay import ROOT, ReplaySession, ReplayOptions, load_session, atomic_json

OUT = ROOT/'reports/timestral-28m-experiment'
SESSIONS = tuple('2026-10-'+str(n) for n in range(19, 24))
STRATEGIES = ('vwap_v1', 'orb_v2', 'sweep_mss_v2')
VARIANTS = ('target_only', 'past_covariates')
CODE_PATHS = ('src/mnq_local/timestral_experiment.py',
              'tests_local/test_timestral_experiment.py', 'run-timestral-28m.sh')


def protocol():
    return {'version': 1, 'model': '28M', 'revision': PINS['28M'].revision,
        'source_revision': SOURCE_REVISION, 'sessions': list(SESSIONS),
        'strategies': list(STRATEGIES), 'variants': list(VARIANTS),
        'data_status': 'PREVIOUSLY_OBSERVED_EXPLORATORY_ONLY',
        'independent_evidence': False, 'live_enabled': False, 'strategy_promoted': False,
        'scope': 'Initial controlled technical comparison: five complete owned CME sessions, both micros',
        'filter': {'horizon': 5, 'edge': .25, 'tail_level': .5, 'ttl': 90.,
                   'forecast_lag_bars': 1, 'selected_on_test': False},
        'timing': 'At decision close t use forecast from t-1 minute only if measured CPU latency <=60s. '
                  'Synthetic historical ready_at=origin+measured latency; wall timestamps retained separately. '
                  'No inference at t is allowed to fill the open at t. V5 next-bar bounded orders unchanged.',
        'features': 'Close price target; past-only returns, volume, rolling volatility and VWAP distance. No future covariates.',
        'accuracy_grid_stride_minutes': 15, 'forecast_horizons': list(HORIZONS),
        'execution': 'Unchanged V5 conservative stop-first, target penetration and intrabar-entry ambiguity policy',
        'risk': 'Unchanged V3 final authority; V5 daily independent diagnostic accounts, not a continuous deployable portfolio',
        'news': 'UNCERTIFIED_EXPLORATORY_ONLY; strict mode remains blocked',
        'costs': {'fee_per_side': .61, 'adverse_slippage_ticks': 1},
        'limitations': ['Five already observed sessions cannot establish statistical advantage',
            'Quantiles are not TP-before-SL probabilities', 'OHLC1m cannot verify intrabar event sequence',
            'Historical feed and orchestration latency not measured; CPU timing alone is not an operational SLA',
            'All 120 sessions previously studied; no independent test period exists in this local dataset']}


def require_license(reviewed):
    if reviewed is not True:
        raise ValueError('Checkpoint license eligibility requires confirmation of the company/employer revenue condition')


def check_binding(out):
    binding = json.loads((out/'code-binding.json').read_text())
    for path, expected in binding.items():
        if file_hash(ROOT/path) != expected:
            raise ValueError('Frozen experiment implementation changed: '+path)


def preserved():
    checked = {}
    for name in ('prior-evidence-sha256.json', 'delivery-manifest.json'):
        path = ROOT/'reports/local-v5'/name
        for relative, expected in json.loads(path.read_text())['files'].items():
            if file_hash(ROOT/relative) != expected:
                raise ValueError('Previously verified file changed: '+relative)
            checked[relative] = expected
    return len(checked)


def groups_for_sessions():
    groups = {}
    proofs = {}
    for day in SESSIONS:
        bars, proofs[day] = load_session(day)
        for symbol in ('MNQ', 'MES'):
            groups[day, symbol] = tuple(b for b in bars if b.symbol == symbol)
    return groups, proofs


def planned_requests(bars, variants=VARIANTS, stride=1):
    if type(stride) is not int or stride < 1:
        raise ValueError('Positive integral stride required')
    # Last origin is 15:59, permitting the one-bar-lag 16:00 diagnostic.
    for n in range(20, len(bars), stride):
        for variant in variants:
            yield Request(tuple(bars[:n]), bars[n-1].end, model='28M', variant=variant)


class LaggedFilter:
    """Wrap only candidate generation. Never replaces V3 risk or order ownership."""
    def __init__(self, original, records, variant):
        self.original, self.records, self.variant = original, records, variant
        self.identity = original.identity
        self.rule = Filter(enabled=True, **{k:v for k,v in protocol()['filter'].items()
                                           if k in ('horizon','edge','tail_level','ttl')})
        self.audit = []

    def evaluate(self, bars, now, state):
        side, state = self.original.evaluate(bars, now, state)
        if not side:
            return side, state
        p = None
        if len(bars) >= 21:
            req = Request(tuple(bars[:-1]), bars[-2].end, model='28M', variant=self.variant)
            p = self.records.get(req.key)
            candidate = Candidate(req.symbol, req.contract, side, req.origin, bars[-1].close, req.key)
            allowed, reason = self.rule.evaluate(candidate, p, now)
        else:
            allowed, reason = False, 'insufficient_lagged_context'
        self.audit.append({'at': now.isoformat(), 'symbol': bars[-1].symbol, 'side': side,
            'allowed_by_filter': allowed, 'reason': reason,
            'forecast_origin': p.origin.isoformat() if p else None,
            'forecast_ready_at': p.available_at.isoformat() if p else None})
        return side if allowed else 0, state


def forecast_scores(rows, bars):
    """Paired point accuracy, quantile losses and empirical coverage; no financial claim."""
    evaluated = [(r,p,horizon_targets(r,bars)) for r,p in rows]
    result = {}
    for h in HORIZONS:
        usable = [(r,p,t[h]) for r,p,t in evaluated if t[h] is not None]
        if not usable:
            result[str(h)] = {'count': 0, 'mae': None, 'random_walk_mae': None,
                             'mae_skill_vs_random_walk': None}
            continue
        actual = np.array([v for _,_,v in usable])
        forecasts = np.array([p.values[p.horizons.index(h)] for _,p,_ in usable])
        last = np.array([r.bars[-1].close for r,_,_ in usable])
        errors = actual[:,None]-forecasts
        levels = np.array(LEVELS)
        mae = float(np.mean(abs(actual-forecasts[:,10])))
        rw = float(np.mean(abs(actual-last)))
        directions = np.sign(forecasts[:,10]-last)
        calls = (directions != 0) & (actual != last)
        empirical = np.mean(actual[:,None] <= forecasts, axis=0)
        result[str(h)] = {'count': len(usable), 'mae': mae, 'random_walk_mae': rw,
            'mae_skill_vs_random_walk': 1-mae/rw if rw else None,
            'directional_calls': int(calls.sum()),
            'directional_accuracy': float(np.mean(directions[calls] == np.sign(actual[calls]-last[calls]))) if calls.any() else None,
            'pinball': {str(q):float(v) for q,v in zip(LEVELS,np.mean(np.maximum(levels*errors,(levels-1)*errors),axis=0))},
            'coverage': {str(q):float(v) for q,v in zip(LEVELS,empirical)},
            'calibration_error': float(np.mean(abs(empirical-levels))),
            'central80_coverage': float(np.mean((actual>=forecasts[:,2]) & (actual<=forecasts[:,18]))),
            'central80_width': float(np.mean(forecasts[:,18]-forecasts[:,2]))}
    return result


def random_walk_scores(groups):
    """Last observed price forecast. Explicit non-AI reference, no invented quantiles."""
    errors = defaultdict(list)
    for (day,symbol),bars in groups.items():
        for n in range(20,len(bars),15):
            for h in HORIZONS:
                if n+h <= len(bars):
                    errors[symbol,h].append(abs(bars[n+h-1].close-bars[n-1].close))
    return {symbol:{str(h):{'count':len(errors[symbol,h]),
        'mae':float(np.mean(errors[symbol,h])) if errors[symbol,h] else None}
        for h in HORIZONS} for symbol in sorted({s for _,s in groups})}


def aggregate(summaries, trades):
    gains = sum(t['net'] for t in trades if t['net']>0)
    losses = -sum(t['net'] for t in trades if t['net']<0)
    return {'sessions': len(summaries), 'trades': len(trades),
        'gross': round(sum(t['gross'] for t in trades),8),
        'fees': round(sum(t['fees'] for t in trades),8),
        'net': round(sum(t['net'] for t in trades),8),
        'profit_factor': gains/losses if losses else None,
        'expectancy': sum(t['net'] for t in trades)/len(trades) if trades else None,
        'max_session_drawdown': max(s['max_drawdown'] for s in summaries),
        'ambiguities': sum(s['ambiguities'] for s in summaries),
        'by_symbol': {s:{'trades':sum(t['symbol']==s for t in trades),
            'net':sum(t['net'] for t in trades if t['symbol']==s)} for s in ('MNQ','MES')},
        'daily_net': {s['session']:s['net'] for s in summaries},
        'daily_account_reset_diagnostic': True, 'financial_validation': False}


def run_arm(out, strategy, records=None, variant=None):
    summaries, trades = [], []
    audit = []
    for day in SESSIONS:
        session = ReplaySession(out/strategy/(variant or 'without_ai')/day,
                                ReplayOptions(session=day, strategy=strategy))
        try:
            # New comparison folders are immutable: do not resume with a changed filter.
            if session.progress['cursor']:
                raise ValueError('Comparison destination already used; select a fresh --output directory')
            wrapper = None
            if records is not None:
                wrapper = LaggedFilter(session.runtime.signal_source, records, variant)
                session.runtime.signal_source = wrapper
            session.run()
            summaries.append(session.report())
            trades.extend(session.trades())
            if wrapper:
                audit.extend(wrapper.audit)
                atomic_json(session.folder/'filter-decisions.json', wrapper.audit)
        finally:
            session.close()
    value = aggregate(summaries, trades)
    value['filter_candidates'] = len(audit)
    value['filter_accepted'] = sum(a['allowed_by_filter'] for a in audit)
    value['filter_rejected'] = sum(not a['allowed_by_filter'] for a in audit)
    return value, trades


def prepare(out):
    out.mkdir(parents=True, exist_ok=True)
    if (out/'protocol.json').exists():
        raise ValueError('Experiment already prepared; select a fresh --output directory')
    count = preserved()
    groups, proofs = groups_for_sessions()
    atomic_json(out/'protocol.json', protocol())  # freeze before any new result
    atomic_json(out/'code-binding.json', {p:file_hash(ROOT/p) for p in CODE_PATHS})
    atomic_json(out/'data-proof.json', proofs)
    atomic_json(out/'random-walk-reference.json', random_walk_scores(groups))
    baseline = {}
    for strategy in STRATEGIES:
        baseline[strategy], _ = run_arm(out/'replay', strategy)
        print('baseline_complete '+strategy, flush=True)
    atomic_json(out/'baseline.json', baseline)
    summary = {'status': 'BASELINES_COMPLETE_MODEL_NOT_EVALUATED', 'real_inference_performed': False,
        'forecasts': 0, 'accuracy': None, 'filtered_economic_results': None,
        'baseline': baseline, 'preserved_paths': count,
        'blocked_by': 'Modified MIT checkpoint company/employer revenue eligibility unconfirmed',
        'independent_evidence': False, 'live_enabled': False}
    atomic_json(out/'results.json', summary)
    if preserved() != count:
        raise ValueError('Frozen evidence set changed')
    return summary


def infer(out, checkpoint, reviewed, threads):
    require_license(reviewed)
    if not (out/'protocol.json').exists() or json.loads((out/'protocol.json').read_text()) != protocol():
        raise ValueError('Prepare and freeze this exact experiment first')
    check_binding(out)
    preserved()
    if threads != 4:
        raise ValueError('Frozen experiment uses exactly four CPU threads')
    import torch
    torch.set_num_threads(threads)
    if not (checkpoint/'model.safetensors').exists():
        provision('28M', checkpoint, license_eligibility_reviewed=True)
    started = time.perf_counter()
    adapter = OfficialAdapter('28M', checkpoint)
    load_seconds = time.perf_counter()-started
    groups, _ = groups_for_sessions()
    logs = out/'forecasts.jsonl'
    existing = read_records(logs, groups) if logs.exists() else {}
    # JSONL append plus flush allows explicit resume without duplicate inference.
    with logs.open('a') as stream:
        for key, bars in groups.items():
            for req in planned_requests(bars):
                if req.key in existing:
                    continue
                called = time.perf_counter()
                prediction = adapter.predict(req)
                elapsed = time.perf_counter()-called
                row = {'request_key': req.key, 'requested_at': req.requested_at.isoformat(),
                    'prediction': json.loads(dumps(prediction)),
                    'total_call_seconds': elapsed,
                    'replay_ready_at': (req.origin+timedelta(seconds=elapsed)).isoformat()}
                stream.write(json.dumps(row, allow_nan=False, sort_keys=True)+'\n')
                stream.flush()
            print('inference_complete '+str(key), flush=True)
    atomic_json(out/'inference-runtime.json', {'real_inference_performed': True,
        'load_seconds': load_seconds, 'threads': threads, 'torch': torch.__version__,
        'device': 'cpu', 'license_eligibility_reviewed': True,
        'checkpoint_revision': PINS['28M'].revision,
        'weights_sha256': file_hash(checkpoint/'model.safetensors')})


def read_records(path, groups):
    requests = {r.key:r for bars in groups.values() for r in planned_requests(bars)}
    records = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        req = requests.get(row['request_key'])
        if req is None or req.key in records:
            raise ValueError('Unknown/duplicate forecast request')
        p = Prediction.from_dict(row['prediction'])
        if row['requested_at'] != req.requested_at.isoformat() or p.request_key != req.key or p.clock != 'wall' or p.context_length != len(req.bars) or (
                p.symbol,p.contract,p.origin,p.variant,p.model) != (req.symbol,req.contract,req.origin,req.variant,'28M'):
            raise ValueError('Forecast input/model identity mismatch')
        elapsed = row['total_call_seconds']
        if not isinstance(elapsed,(int,float)) or not np.isfinite(elapsed) or elapsed < p.latency_seconds:
            raise ValueError('Invalid total forecast call timing')
        ready = req.origin+timedelta(seconds=elapsed)
        if row['replay_ready_at'] != ready.isoformat():
            raise ValueError('Historical latency mapping changed')
        records[req.key] = replace(p, available_at=ready, latency_seconds=elapsed, clock='replay')
    return records


def compare(out):
    groups, _ = groups_for_sessions()
    if json.loads((out/'protocol.json').read_text()) != protocol():
        raise ValueError('Frozen experiment changed')
    check_binding(out)
    records = read_records(out/'forecasts.jsonl', groups)
    expected = {r.key for bars in groups.values() for r in planned_requests(bars)}
    if set(records) != expected:
        raise ValueError('Incomplete real forecast log; economic comparison blocked')
    accuracy = {}
    for symbol in ('MNQ','MES'):
        for variant in VARIANTS:
            rows = [(r,records[r.key]) for (day,s),bars in groups.items() if s == symbol
                for r in planned_requests(bars, (variant,), stride=15)]
            accuracy[symbol+'/'+variant] = forecast_scores(rows,
                [b for (day,s),bars in groups.items() if s == symbol for b in bars])
    baseline = json.loads((out/'baseline.json').read_text())
    results = {}
    for strategy in STRATEGIES:
        for variant in VARIANTS:
            value, _ = run_arm(out/'replay', strategy, records, variant)
            value['paired_daily_net_delta'] = {d:value['daily_net'][d]-baseline[strategy]['daily_net'][d] for d in SESSIONS}
            value['net_delta_vs_baseline'] = value['net']-baseline[strategy]['net']
            value['statistical_significance'] = 'NOT_ESTABLISHED_FIVE_OBSERVED_SESSIONS'
            results[strategy+'/'+variant] = value
    latencies = [p.latency_seconds for p in records.values()]
    result = {'status': 'EXPLORATORY_COMPARISON_COMPLETE', 'real_inference_performed': True,
        'forecasts': len(records), 'accuracy_nonoverlap_grid': accuracy, 'baseline': baseline,
        'filtered_economic_results': results, 'forecast_log_sha256':file_hash(out/'forecasts.jsonl'),
        'latency_seconds': {'median':statistics.median(latencies),'p95':float(np.quantile(latencies,.95)),
            'max':max(latencies),'fraction_ready_within60s':sum(t<=60 for t in latencies)/len(latencies)},
        'independent_evidence': False, 'live_enabled': False, 'strategy_promoted': False}
    atomic_json(out/'results.json', result)
    preserved()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare','infer','compare','verify'))
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--checkpoint', type=Path, default=ROOT/'data/models/Timestral-28M')
    parser.add_argument('--license-eligibility-reviewed', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args(argv)
    if args.command == 'prepare': print(json.dumps(prepare(args.output), indent=2))
    elif args.command == 'infer': infer(args.output,args.checkpoint,args.license_eligibility_reviewed,args.threads)
    elif args.command == 'compare': print(json.dumps(compare(args.output), indent=2))
    else: print(json.dumps({'unchanged_frozen_paths':preserved()}))


if __name__ == '__main__':
    main()
