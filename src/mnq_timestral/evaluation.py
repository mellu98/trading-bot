"""Predeclared, session-separated research screening. Never enables trading automatically."""
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
from hashlib import sha256
import math
import platform
import sys
import os
import time
import numpy as np
from .schema import Request, Prediction, NY, UTC, HORIZONS, LEVELS, dumps, loads
from .data import features, horizon_targets, session_window, news_allowed, validate_dataset, file_hash
from .strategy import Candidate, SignalGenerator, Filter, Risk, RiskState, entry_allowed
from .model import PINS, SOURCE_REVISION, OfficialAdapter

POINT_VALUE = {'MES': 5., 'MNQ': 2.}
DISTANCES = {'MES': (4., 2.), 'MNQ': (15., 8.)}
TICK = .25


@dataclass(frozen=True)
class Costs:
    commission_per_side: float
    exchange_per_side: float
    regulatory_per_side: float
    spread_ticks: float
    entry_slippage_ticks: float
    exit_slippage_ticks: float
    evidence: str

    def __post_init__(self):
        values = [getattr(self, k) for k in self.__dataclass_fields__ if k != 'evidence']
        if any(not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in values):
            raise ValueError("cost components must be finite and nonnegative")
        if not self.evidence: raise ValueError("documented cost evidence required")

    @classmethod
    def from_dict(cls, obj): return cls(**{k: obj[k] for k in cls.__dataclass_fields__})
    @property
    def fees(self): return 2*(self.commission_per_side+self.exchange_per_side+self.regulatory_per_side)
    def execution_cost(self, symbol, stress=1):
        return stress*TICK*POINT_VALUE[symbol]*(self.spread_ticks+self.entry_slippage_ticks+self.exit_slippage_ticks)


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: int
    entry_at: datetime
    exit_at: datetime
    raw_entry: float
    raw_exit: float
    gross: float
    fees: float
    execution_cost: float
    net: float
    reason: str
    candidate_key: str = ''
    regime: str = ''
    equity_path: tuple = ()


def simulate_trade(symbol, side, bars, raw_entry, costs, tp=None, sl=None, stress=1,
                   realized=0., peak=0., risk=None):
    """One-minute screen: raw-open-anchored brackets; pessimistic stop-first; costs deducted separately."""
    if not bars or side not in (-1, 1): raise ValueError("trade needs bars and direction")
    tp = DISTANCES[symbol][0] if tp is None else tp
    sl = DISTANCES[symbol][1] if sl is None else sl
    if any(not math.isfinite(v) or v <= 0 for v in (raw_entry,tp,sl,stress)):
        raise ValueError("positive finite entry/distances/cost stress required")
    target, stop = raw_entry+side*tp, raw_entry-side*sl
    point = POINT_VALUE[symbol]
    equity_path = []
    reason, raw_exit = 'time_exit', bars[-1].close
    for i, bar in enumerate(bars):
        if i and (bars[i-1].end != bar.start or bars[i-1].contract != bar.contract):
            raise ValueError("unpriceable gap/roll during open trade; economic run blocked")
        hit_stop = bar.low <= stop if side == 1 else bar.high >= stop
        hit_target = bar.high >= target if side == 1 else bar.low <= target
        if hit_stop:
            raw_exit = min(bar.open, stop) if side == 1 else max(bar.open, stop)
            reason = 'stop'
        elif hit_target:
            raw_exit, reason = target, 'target'  # no favorable gap improvement
        else:
            raw_exit = bar.close
        mark = side*(raw_exit-raw_entry)*point-costs.fees-costs.execution_cost(symbol, stress)
        equity_path.append((bar.end, mark))
        if hit_stop or hit_target: break
        peak = max(peak,realized+mark)
        if risk and (realized+mark <= -risk.daily_max_loss or peak-(realized+mark) >= risk.max_drawdown):
            reason = 'risk_loss'
            break
    gross = side*(raw_exit-raw_entry)*point
    fees, execution = costs.fees, costs.execution_cost(symbol, stress)
    return Trade(symbol, side, bars[0].start, bar.end, raw_entry, raw_exit, gross, fees,
                 execution, gross-fees-execution, reason, equity_path=tuple(equity_path))


def metrics(trades):
    net = np.array([t.net for t in trades], dtype=float)
    gains, losses = net[net > 0], net[net < 0]
    equity, peak, drawdown = 0., 0., 0.
    for trade in trades:
        for _, mark in trade.equity_path:
            peak = max(peak, equity+mark)
            drawdown = max(drawdown, peak-(equity+mark))
        equity += trade.net
        peak = max(peak, equity)
        drawdown = max(drawdown, peak-equity)
    hours = defaultdict(list)
    for t in trades: hours[str(t.entry_at.astimezone(NY).hour)].append(t.net)
    return {'trades': len(trades), 'gross': sum(t.gross for t in trades), 'fees': sum(t.fees for t in trades),
            'execution_cost': sum(t.execution_cost for t in trades), 'net': float(net.sum()),
            'win_rate': float(np.mean(net > 0)) if len(net) else None,
            'profit_factor': float(gains.sum()/-losses.sum()) if len(losses) else None,
            'no_losing_trades': bool(len(trades) and not len(losses)),
            'max_drawdown_mark_to_minute_close': drawdown,
            'expectancy': float(net.mean()) if len(net) else None,
            'average_win': float(gains.mean()) if len(gains) else None,
            'average_loss': float(losses.mean()) if len(losses) else None,
            'average_duration_minutes': float(np.mean([(t.exit_at-t.entry_at).total_seconds()/60 for t in trades])) if trades else None,
            'net_quantiles': {str(q):float(np.quantile(net,q)) for q in (.05,.25,.5,.75,.95)} if len(net) else {},
            'by_entry_hour': {hour:{'trades':len(pnl),'net':sum(pnl)} for hour,pnl in hours.items()}}


def forecast_metrics(rows):
    result = {}
    for h in HORIZONS:
        usable = [(p, truth[h]) for p, truth in rows if truth.get(h) is not None]
        if not usable:
            result[str(h)] = {'count': 0, 'mae': None, 'pinball': {}, 'coverage': {}}
            continue
        values = np.array([p.values[p.horizons.index(h)] for p, _ in usable])
        actual = np.array([t for _, t in usable])[:, None]
        errors = actual-values
        levels = np.array(LEVELS)
        result[str(h)] = {'count': len(usable), 'mae': float(np.mean(abs(actual[:, 0]-values[:, 10]))),
            'pinball': {str(q):float(v) for q,v in zip(LEVELS,np.mean(np.maximum(levels*errors,(levels-1)*errors),axis=0))},
            'coverage': {str(q):float(v) for q,v in zip(LEVELS,np.mean(actual <= values,axis=0))},
            'mean_absolute_calibration_error':float(np.mean(abs(np.mean(actual<=values,axis=0)-levels)))}
    return result


def block_bootstrap(daily_differences, seed=1729, replicates=5000, family_size=4, minimum_sessions=30):
    """Paired daily blocks preserve within-session trade dependence. Bonferroni one-sided bound."""
    x = np.asarray(daily_differences, dtype=float)
    if x.ndim != 1 or not np.isfinite(x).all(): raise ValueError("finite paired session differences required")
    if len(x) < minimum_sessions:
        return {'status': 'insufficient_evidence', 'sessions':len(x), 'required_sessions':minimum_sessions,
                'research_improvement':False, 'filter_enabled':False}
    if family_size < 4 or replicates < 1000: raise ValueError("declared family or replication count too small")
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(x, len(x), replace=True).mean() for _ in range(replicates)])
    lower = float(np.quantile(means,.05/family_size))
    return {'status':'evaluated', 'sessions':len(x), 'mean_daily_net_difference':float(x.mean()),
            'lower_bound':lower, 'alpha':.05, 'family_size':family_size, 'seed':seed,
            'replicates':replicates, 'research_improvement':lower > 0, 'filter_enabled':False,
            'limitation':'Daily IID block assumption; not proof against dependence across sessions or research reuse.'}


def split_sessions(sessions, calibration=20, validation=10, test=10, holdout=30):
    dates = sorted(set(sessions))
    if len(dates) != len(sessions): raise ValueError("unique whole-session labels required")
    if min(calibration, validation, test, holdout) < 1: raise ValueError("positive split lengths required")
    untouched, usable = dates[-holdout:], dates[:-holdout]
    folds, start = [], 0
    while start+calibration+validation+test <= len(usable):
        folds.append({'calibration':usable[start:start+calibration],
                      'validation':usable[start+calibration:start+calibration+validation],
                      'test':usable[start+calibration+validation:start+calibration+validation+test]})
        start += test
    if not folds: raise ValueError("insufficient whole sessions for walk-forward and reserved holdout")
    return folds, untouched


def select_threshold(validation_rows, thresholds):
    """Small deterministic helper: accepts validation evidence ONLY; ties choose larger threshold."""
    return max(thresholds, key=lambda threshold:(sum(net for edge,net in validation_rows if edge >= threshold),threshold))


DEFAULT_PLAN = {'calibration_sessions':20, 'validation_sessions':10, 'test_sessions':10, 'holdout_sessions':30,
                'models':['28M','209M'], 'variants':['target_only','past_covariates'], 'horizons':[1,3,5,10,15],
                'thresholds':[0.,.25,.5,1.], 'seed':1729, 'bootstrap_replicates':5000, 'family_size':4,
                'minimum_sessions':30, 'minimum_usable_forecasts':30, 'minimum_forecast_coverage':.8,
                'require_positive_filtered_net':True, 'ttl_seconds':90, 'cost_stress':[1.,1.5,2.],
                'risk':{'daily_max_loss':200.,'max_drawdown':500.,'max_trades':10,'max_consecutive_losses':3},
                'virtual_capital_per_symbol':10000., 'holdout_previously_unseen_attestation':False}


def validate_plan(plan):
    if set(plan) != set(DEFAULT_PLAN): raise ValueError("plan fields must match explicit template")
    if plan['models'] != ['28M','209M'] or plan['variants'] != ['target_only','past_covariates']:
        raise ValueError("two pinned models and both feature ablations required")
    if plan['horizons'] != list(HORIZONS) or plan['family_size'] != 4: raise ValueError("declared comparison family mismatch")
    if plan['holdout_previously_unseen_attestation'] is not True: raise ValueError("untouched holdout attestation required")
    if len(plan['thresholds']) > 8 or not plan['thresholds'] or any(not math.isfinite(x) or x < 0 for x in plan['thresholds']):
        raise ValueError("small nonnegative finite preregistered threshold grid required")
    if plan['minimum_sessions'] < 30 or plan['bootstrap_replicates'] < 1000: raise ValueError("evidence floor cannot be lowered")
    if (not isinstance(plan['minimum_usable_forecasts'],int) or plan['minimum_usable_forecasts'] < 30
            or not .8 <= plan['minimum_forecast_coverage'] <= 1
            or plan['require_positive_filtered_net'] is not True):
        raise ValueError('preregistered model evidence/profitability floor cannot be lowered')
    if plan['ttl_seconds'] != 90 or plan['virtual_capital_per_symbol'] <= 0: raise ValueError("invalid plan risk/latency")
    Risk(**plan['risk'])


def group_sessions(bars):
    groups = defaultdict(list)
    for b in bars: groups[(b.start.astimezone(NY).date().isoformat(),b.symbol)].append(b)
    return {k:tuple(v) for k,v in groups.items()}


def screen_sessions(groups, manifest):
    """Economic runs fail, rather than fabricate fills, if required cash-window minutes are missing."""
    dates = sorted({d for d,_ in groups})
    for date in dates:
        start,end = session_window(date,manifest['sessions'])
        anchor = start-timedelta(minutes=15)
        for symbol in ('MNQ','MES'):
            required = [b for b in groups.get((date,symbol),()) if anchor <= b.start < end]
            expected = int((end-anchor).total_seconds()/60)
            if len(required) != expected or any(b.start != anchor+timedelta(minutes=i) for i,b in enumerate(required)):
                raise ValueError(f"unpriceable cash-window gaps or missing symbol: {date} {symbol}")


def runtime_provenance():
    result = {'python':sys.version, 'platform':platform.platform(), 'machine':platform.machine(),
              'processor':platform.processor(), 'logical_cpus':os.cpu_count(), 'numpy':np.__version__}
    try:
        import torch
        result.update(torch=torch.__version__, torch_threads=torch.get_num_threads(),
                      interop_threads=torch.get_num_interop_threads())
    except ImportError: result['torch'] = None
    return result


def register_experiment(csv_path, manifest_path, plan_path, registration):
    bars,manifest = validate_dataset(csv_path,manifest_path)
    plan = loads(Path(plan_path).read_text()); validate_plan(plan)
    groups = group_sessions(bars); screen_sessions(groups,manifest)
    dates = sorted({d for d,_ in groups})
    folds,holdout = split_sessions(dates,plan['calibration_sessions'],plan['validation_sessions'],
                                   plan['test_sessions'],plan['holdout_sessions'])
    record = {'schema_version':1,'registered_at':datetime.now(UTC).isoformat(), 'dataset_sha256':file_hash(csv_path),
              'manifest_sha256':file_hash(manifest_path),'plan_sha256':file_hash(plan_path),'plan':plan,
              'plan_fingerprint':sha256(dumps(plan).encode()).hexdigest(),
              'folds':folds,'holdout':holdout,'source_revision':SOURCE_REVISION,
              'purpose':'minute-bar-screening-only','attestation_not_independent_authentication':True}
    with open(registration,'x') as stream: stream.write(dumps(record)+'\n')
    return record


def forecast_dataset(csv_path, manifest_path, checkpoints, destination, threads=1):
    bars,manifest = validate_dataset(csv_path,manifest_path)
    groups=group_sessions(bars)
    import torch
    torch.set_num_threads(threads)
    header = {'kind':'official_local_cpu_forecasts','dataset_sha256':file_hash(csv_path),
              'manifest_sha256':file_hash(manifest_path),'source_revision':SOURCE_REVISION,
              'runtime':runtime_provenance(),'generated_at':datetime.now(UTC).isoformat(),
              'availability':'bar.available_at + measured end-to-end adapter elapsed time',
              'quantile_semantics':'marginal price, NOT first-passage TP-before-SL probability'}
    counts=Counter()
    with open(destination,'x') as stream:
        stream.write(dumps(header)+'\n'); stream.flush()
        for name in ('28M','209M'):
            adapter=OfficialAdapter(name,checkpoints[name])
            for (date,symbol),session in sorted(groups.items()):
                start,end=session_window(date,manifest['sessions'])
                cash=tuple(b for b in session if start-timedelta(minutes=15)<=b.start<end)
                for i in range(19,len(cash)):
                    for variant in ('target_only','past_covariates'):
                        try:
                            req=Request(cash[:i+1],cash[i].available_at,name,variant)
                        except ValueError:
                            counts['invalid_context']+=1; continue
                        try:
                            started=time.perf_counter(); p=adapter.predict(req); elapsed=time.perf_counter()-started
                            p=replace(p,available_at=req.requested_at+timedelta(seconds=elapsed),clock='replay')
                            stream.write(dumps({'prediction':p,'adapter_elapsed_seconds':elapsed,'requested_at':req.requested_at,
                                                'generated_at':datetime.now(UTC)})+'\n')
                            counts['predictions']+=1
                        except Exception as error:
                            stream.write(dumps({'error':type(error).__name__,'request_key':req.key,
                                                'model':name,'variant':variant,'origin':req.origin})+'\n')
                            counts['errors']+=1
                        stream.flush()
            del adapter
    return dict(counts)


def load_forecasts(path, csv_path, manifest_path):
    predictions,failures={},Counter()
    with open(path) as stream:
        header=loads(next(stream))
        if header.get('kind')!='official_local_cpu_forecasts' or header.get('source_revision')!=SOURCE_REVISION:
            raise ValueError("official pinned local inference log required")
        if header.get('dataset_sha256')!=file_hash(csv_path) or header.get('manifest_sha256')!=file_hash(manifest_path):
            raise ValueError("forecast data/provenance mismatch")
        for line in stream:
            row=loads(line)
            if 'error' in row:
                failures[row['error']]+=1; continue
            p=Prediction.from_dict(row['prediction'])
            elapsed=row['adapter_elapsed_seconds']
            if p.clock!='replay' or not math.isfinite(elapsed) or elapsed<0: raise ValueError("invalid replay latency")
            from .schema import timestamp
            if p.available_at != timestamp(row['requested_at'])+timedelta(seconds=elapsed):
                raise ValueError('forecast readiness does not match measured elapsed time')
            if elapsed+1e-6 < p.latency_seconds: raise ValueError('adapter latency smaller than inference latency')
            if p.request_key in predictions: raise ValueError("duplicate forecast")
            predictions[p.request_key]=p
    return predictions,dict(failures),header


def build_records(groups, manifest, predictions):
    records={}; used=set()
    for key,session in sorted(groups.items()):
        date,symbol=key
        start,end=session_window(date,manifest['sessions'])
        cash=tuple(b for b in session if start-timedelta(minutes=15)<=b.start<end)
        generator=SignalGenerator(); rows=[]
        for i in range(19,len(cash)):
            base=Request(cash[:i+1],cash[i].available_at,'28M','target_only')
            f=features(base); side=generator.direction(float(f.z[-1]))
            row={'index':i,'bar':cash[i],'volatility':float(f.volatility[-1]),'side':side,
                 'requests':{},'predictions':{},'targets':horizon_targets(base,session)}
            for model,variant in product(('28M','209M'),('target_only','past_covariates')):
                req=replace(base,model=model,variant=variant); pred=predictions.get(req.key)
                if pred:
                    if (pred.origin,pred.symbol,pred.contract,pred.model,pred.variant)!=(req.origin,symbol,req.contract,model,variant):
                        raise ValueError("forecast identity mismatch")
                    if pred.available_at<req.requested_at or pred.context_length!=len(req.bars): raise ValueError("forecast availability/context mismatch")
                    used.add(req.key)
                row['requests'][(model,variant)]=req;row['predictions'][(model,variant)]=pred
            rows.append(row)
        records[key]=(cash,rows)
    if set(predictions)-used: raise ValueError("forecast log contains unmatched contexts")
    return records


def regime_threshold(records,dates,symbol):
    volatility=[r['volatility'] for d in dates for r in records[(d,symbol)][1]]
    return float(np.median(volatility)) if volatility else 0.


def run_arm(records,dates,symbol,manifest,plan,arm,model='28M',variant='target_only',horizon=5,edge=0.,regime_cut=0.,stress=1.):
    trades=[]; decisions=[]; daily={}; aggregate_realized=0.; aggregate_peak=0.
    costs=Costs.from_dict(manifest['costs'][symbol]);risk=Risk(**plan['risk'])
    for date in dates:
        cash,rows=records[(date,symbol)]
        window=session_window(date,manifest['sessions']);calendar=manifest['sessions'][date]
        busy_until=None;realized=0.;consecutive=0;count=0;c_previous=0
        for row in rows:
            req=row['requests'][(model,variant)];pred=row['predictions'][(model,variant)];side=row['side']
            if arm=='C':
                # Never consume/reset direction from unavailable output. The causal event is
                # the first executable open after readiness, not the forecast's origin.
                if busy_until is not None and req.origin<=busy_until: continue
                ready=max(req.requested_at,pred.available_at) if pred else req.requested_at
                event=next((b.start for b in cash[row['index']+1:] if b.start>ready),None)
                if event is None or not (window[0]<=req.origin<window[1] and window[0]<=event<window[1]): continue
                if not news_allowed(req.origin,calendar) or not news_allowed(event,calendar): continue
                probe=Candidate(symbol,req.contract,1,req.origin,row['bar'].close,req.key)
                if not Filter(True,horizon).prediction_available(probe,pred,event)[0]: continue
                new_side=1 if pred.quantile(horizon,.5)>row['bar'].close else -1 if pred.quantile(horizon,.5)<row['bar'].close else 0
                side=new_side if new_side!=c_previous else 0;c_previous=new_side
            if not side: continue
            candidate=Candidate(symbol,req.contract,side,req.origin,row['bar'].close,req.key)
            key=f'{symbol}:{req.origin.isoformat()}:{side}'
            decision={'candidate_key':key,'date':date,'side':side,'origin':req.origin,'accepted':False}
            decisions.append(decision)
            if busy_until is not None and req.origin<=busy_until:
                decision['reason']='position_open';continue
            ready=max(req.requested_at,pred.available_at) if arm!='A' and pred else req.requested_at
            next_bars=[b for b in cash[row['index']+1:] if b.start>ready]
            if not next_bars:
                decision['reason']='no_next_open';continue
            entry=next_bars[0]
            calendar_ok=(window[0]<=req.origin<window[1] and window[0]<=entry.start<window[1]
                         and news_allowed(req.origin,calendar) and news_allowed(entry.start,calendar))
            state=RiskState(realized=realized,drawdown=max(0,aggregate_peak-aggregate_realized),trades=count,
                            consecutive_losses=consecutive,data_fresh=(entry.start-req.origin).total_seconds()<=plan['ttl_seconds'])
            allowed,reason=entry_allowed(candidate,pred,entry.start,Filter(arm!='A',horizon,edge),risk,state,calendar_ok)
            if not allowed: decision['reason']=reason;continue
            path=[b for b in next_bars if b.start<window[1]]
            # Purge boundaries by forcing every trade flat in its source session.
            trade=simulate_trade(symbol,side,path,entry.open,costs,stress=stress,realized=realized,
                                 peak=max(0,aggregate_peak-aggregate_realized)+realized,risk=risk)
            trade=replace(trade,candidate_key=key,regime='high_volatility' if row['volatility']>regime_cut else 'low_volatility')
            trades.append(trade);decision.update(accepted=True,reason='accepted',entry_at=entry.start)
            aggregate_peak=max(aggregate_peak,*(aggregate_realized+mark for _,mark in trade.equity_path))
            busy_until=trade.exit_at;count+=1;realized+=trade.net;aggregate_realized+=trade.net
            aggregate_peak=max(aggregate_peak,aggregate_realized)
            consecutive=consecutive+1 if trade.net<0 else 0
        daily[date]=realized
    return trades,decisions,daily


def summarize_arm(result):
    trades,decisions,daily=result
    summary=metrics(trades)
    summary.update(daily_net=daily,accepted=sum(d['accepted'] for d in decisions),
                   rejected=sum(not d['accepted'] for d in decisions),reasons=dict(Counter(d['reason'] for d in decisions)),
                   regimes={regime:metrics([t for t in trades if t.regime==regime]) for regime in ('low_volatility','high_volatility')})
    return summary


def model_evidence(records,dates,symbol,model,variant,horizon,manifest,plan):
    """Count price forecasts actionable before maturity; missing/stale cash fallback is not evidence."""
    opportunities=0;usable=0
    for date in dates:
        cash,rows=records[(date,symbol)]
        window=session_window(date,manifest['sessions']);calendar=manifest['sessions'][date]
        for row in rows:
            req=row['requests'][(model,variant)];pred=row['predictions'][(model,variant)]
            baseline_event=next((b.start for b in cash[row['index']+1:] if b.start>req.requested_at),None)
            if (baseline_event is None or row['targets'].get(horizon) is None
                    or not window[0]<=req.origin<window[1] or not window[0]<=baseline_event<window[1]
                    or not news_allowed(req.origin,calendar) or not news_allowed(baseline_event,calendar)):
                continue
            opportunities+=1
            if pred is None: continue
            ready=max(req.requested_at,pred.available_at)
            event=next((b.start for b in cash[row['index']+1:] if b.start>ready),None)
            probe=Candidate(symbol,req.contract,1,req.origin,row['bar'].close,req.key)
            if (event is not None and event<window[1] and news_allowed(event,calendar)
                    and pred.valid_for(req,event,plan['ttl_seconds'])
                    and Filter(True,horizon).prediction_available(probe,pred,event)[0]):
                usable+=1
    return {'opportunities':opportunities,'usable_forecasts':usable,
            'coverage':usable/opportunities if opportunities else 0.}


def model_statistical_screen(slices,plan):
    """Gate attribution before bootstrap: cash-only avoidance cannot establish model value."""
    differences=[value for part in slices for value in part['daily_difference']]
    count=sum(part['model_evidence']['usable_forecasts'] for part in slices)
    opportunities=sum(part['model_evidence']['opportunities'] for part in slices)
    coverage=count/opportunities if opportunities else 0.
    filtered_net=sum(part['arms']['B']['net'] for part in slices)
    evidence={'usable_forecasts':count,'opportunities':opportunities,'coverage':coverage,
              'required_forecasts':plan['minimum_usable_forecasts'],
              'required_coverage':plan['minimum_forecast_coverage'],'filtered_net':filtered_net}
    selection_available=all(part['selected_on_validation']['status']=='selected' for part in slices)
    if (not selection_available or count<plan['minimum_usable_forecasts']
            or coverage<plan['minimum_forecast_coverage']):
        return {'status':'insufficient_model_evidence','sessions':len(differences),
                'research_improvement':False,'filter_enabled':False,'model_evidence':evidence,
                'reason':'Missing/unusable forecasts or unavailable validation selection cannot establish model value.'}
    result=block_bootstrap(differences,plan['seed'],plan['bootstrap_replicates'],plan['family_size'],plan['minimum_sessions'])
    result['model_evidence']=evidence
    if plan['require_positive_filtered_net'] and filtered_net<=0:
        result['research_improvement']=False
        result['reason']='Filtered strategy must have positive net P&L, not merely lose less or remain in cash.'
    return result


def choose_on_validation(records,dates,symbol,model,manifest,plan,regime_cut):
    choices=[];trials=0
    # Strict next-minute-open execution is at/after the one-minute target, so h=1
    # remains a forecast diagnostic only and cannot win an economic selection.
    economic_horizons=[h for h in plan['horizons'] if h>1]
    for variant,horizon in product(plan['variants'],economic_horizons):
        evidence=model_evidence(records,dates,symbol,model,variant,horizon,manifest,plan)
        if not evidence['usable_forecasts'] or evidence['coverage']<plan['minimum_forecast_coverage']: continue
        for edge in plan['thresholds']:
            trials+=1
            result=run_arm(records,dates,symbol,manifest,plan,'B',model,variant,horizon,edge,regime_cut)
            if result[0]: choices.append((sum(result[2].values()),edge,horizon,variant))
    if not choices:
        return {'status':'insufficient_model_evidence','variant':plan['variants'][0],
                'horizon':economic_horizons[0],'edge':plan['thresholds'][0],'validation_net':None,
                'trials':trials,'unavailable_economic_horizons':[1],
                'fallback':'Reporting-only configuration; no model rule selected from cash/failure gains.'}
    score,edge,horizon,variant=max(choices)
    return {'status':'selected','variant':variant,'horizon':horizon,'edge':edge,
            'validation_net':score,'trials':trials,'unavailable_economic_horizons':[1]}


def compare(csv_path,manifest_path,forecast_path,registration_path):
    bars,manifest=validate_dataset(csv_path,manifest_path)
    groups=group_sessions(bars);screen_sessions(groups,manifest)
    registration=loads(Path(registration_path).read_text());plan=registration['plan'];validate_plan(plan)
    if registration.get('plan_fingerprint')!=sha256(dumps(plan).encode()).hexdigest():
        raise ValueError('registered plan changed')
    if registration['dataset_sha256']!=file_hash(csv_path) or registration['manifest_sha256']!=file_hash(manifest_path):
        raise ValueError("registered dataset changed")
    if registration.get('source_revision')!=SOURCE_REVISION: raise ValueError("registration source mismatch")
    predictions,failures,header=load_forecasts(forecast_path,csv_path,manifest_path)
    if not predictions: raise ValueError("no actual model predictions available")
    records=build_records(groups,manifest,predictions)
    expected_folds,expected_holdout=split_sessions(sorted({d for d,_ in groups}),plan['calibration_sessions'],
                               plan['validation_sessions'],plan['test_sessions'],plan['holdout_sessions'])
    if registration['folds']!=expected_folds or registration['holdout']!=expected_holdout:
        raise ValueError("registered splits changed")
    # Consume once before any test label is evaluated; immutable report can be copied for reproduction.
    # This is a local guard, not proof against a human inspecting raw holdout data.
    consumed=Path(str(registration_path)+'.consumed.json')
    identity={'registration_sha256':file_hash(registration_path),'forecasts_sha256':file_hash(forecast_path)}
    if consumed.exists():
        receipt=loads(consumed.read_text())
        if receipt.get('identity')!=identity or 'report' not in receipt:
            raise ValueError("holdout already consumed or interrupted; do not reuse it for selection")
        return receipt['report']
    with open(consumed,'x') as stream: stream.write(dumps({'identity':identity,'state':'consumed_before_evaluation'}))
    result={'status':'screening_evaluated','filter_enabled':False,'execution_quality_gate':False,
            'independent_authenticity_verified':False,'input_attestation':manifest['audit_reference'],
            'limitations':['Minute OHLCV is not tick/LEAN execution validation.','No live or paper-broker execution implemented.',
                          'Quantiles are marginal price forecasts, not TP-before-SL probabilities.',
                          'Holdout freshness is a user attestation plus local one-use guard, not independent proof.',
                          'Regime threshold uses calibration sessions only. Costs are externally attested, not independently verified.'],
            'identity':identity,'runtime':header['runtime'],'models':{},'inference_failures':failures,
            'availability_rule':'first bar open strictly after max(data availability, prediction availability)',
            'source_revision':SOURCE_REVISION,'selection':'validation only; test and holdout never tune thresholds/model variants/horizons'}
    for symbol,model in product(('MNQ','MES'),plan['models']):
        outcomes={'walk_forward':[]};all_diff=[]
        for fold in registration['folds']:
            cut=regime_threshold(records,fold['calibration'],symbol)
            selected=choose_on_validation(records,fold['validation'],symbol,model,manifest,plan,cut)
            outcomes['walk_forward'].append(evaluate_slice(records,fold['test'],symbol,model,selected,cut,manifest,plan))
            all_diff.extend(outcomes['walk_forward'][-1]['daily_difference'])
        # Final choice uses only the final validation block, frozen before reserved holdout is evaluated.
        fold=registration['folds'][-1]
        cut=regime_threshold(records,fold['calibration'],symbol)
        selected=choose_on_validation(records,fold['validation'],symbol,model,manifest,plan,cut)
        outcomes['holdout']=evaluate_slice(records,registration['holdout'],symbol,model,selected,cut,manifest,plan)
        outcomes['walk_forward_statistical_screen']=model_statistical_screen(outcomes['walk_forward'],plan)
        outcomes['holdout_statistical_screen']=model_statistical_screen([outcomes['holdout']],plan)
        outcomes['walk_forward_statistical_screen']['hypothesis_role']='exploratory'
        outcomes['holdout_statistical_screen']['hypothesis_role']='primary_familywise_confirmation'
        result['models'][f'{symbol}/{model}']=outcomes
    result['recommendation']='keep_disabled_pending_execution_validation'
    receipt={'identity':identity,'state':'completed','report':result}
    temp=Path(str(consumed)+'.tmp');temp.write_text(dumps(receipt)+'\n');os.replace(temp,consumed)
    return result


def evaluate_slice(records,dates,symbol,model,selected,cut,manifest,plan):
    kwargs=dict(model=model,variant=selected['variant'],horizon=selected['horizon'],edge=selected['edge'],regime_cut=cut)
    arms={arm:run_arm(records,dates,symbol,manifest,plan,arm,**kwargs) for arm in ('A','B','C')}
    accepted_b={d['candidate_key'] for d in arms['B'][1] if d['accepted']}
    missed=[t for t in arms['A'][0] if t.candidate_key not in accepted_b and t.net>0]
    rejected_by_filter={d['candidate_key'] for d in arms['B'][1] if d['reason'] in ('missing','identity','not_ready','stale','target_expired','distribution_incoherent')}
    missed_filter=[t for t in missed if t.candidate_key in rejected_by_filter]
    forecast_rows=[];latencies=[];missing=0
    ablations={variant:[] for variant in plan['variants']}
    for date in dates:
        for r in records[(date,symbol)][1]:
            for variant in plan['variants']:
                variant_pred=r['predictions'][(model,variant)]
                if variant_pred: ablations[variant].append((variant_pred,r['targets']))
            p=r['predictions'][(model,selected['variant'])]
            if p: forecast_rows.append((p,r['targets']));latencies.append(p.latency_seconds)
            else: missing+=1
    return {'sessions':dates,'selected_on_validation':selected,'regime_calibration_cut':cut,
            'model_evidence':model_evidence(records,dates,symbol,model,selected['variant'],selected['horizon'],manifest,plan),
            'cash_only_reference':{'net':0.,'net_difference_vs_A':-sum(arms['A'][2].values()),'not_model_value':True},
            'unavailable_economic_horizons':[1],
            'arms':{arm:summarize_arm(value) for arm,value in arms.items()},
            'daily_difference':[arms['B'][2][d]-arms['A'][2][d] for d in dates],
            'counterfactual_missed_positive_baseline_trades':len(missed_filter),
            'counterfactual_missed_positive_net':sum(t.net for t in missed_filter),
            'counterfactual_warning':'Same baseline trade outcome, not an additive B portfolio P&L; later exposure paths differ.',
            'forecast_metrics':forecast_metrics(forecast_rows),'missing_predictions':missing,
            'forecast_metrics_by_feature_ablation':{variant:forecast_metrics(rows) for variant,rows in ablations.items()},
            'cpu_latency_seconds':{'count':len(latencies),'p50':float(np.median(latencies)) if latencies else None,
                                   'p95':float(np.quantile(latencies,.95)) if latencies else None,
                                   'max':max(latencies) if latencies else None},
            'cost_stress':{str(stress):{arm:metrics(run_arm(records,dates,symbol,manifest,plan,arm,stress=stress,**kwargs)[0])
                                     for arm in ('A','B','C')} for stress in plan['cost_stress']},
            'C_status':'exploratory_only; configuration inherited from B validation, not independent confirmation'}
