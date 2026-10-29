"""Frozen-protocol exploratory quantitative evaluation. Offline, no brokers or data purchases."""
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import numpy as np

from databento_planner.cache import atomic_json
from mnq_data.core import digest, file_hash
from mnq_timestral.schema import Bar, Request, NY
from mnq_timestral.data import features
from mnq_timestral.evaluation import DISTANCES, POINT_VALUE
from .engine import Config, Replay, summarize
from .__main__ import write_rows
from .bulk import OUT, CALENDAR, EXCLUDED


def fee_for_date(date):return .02 if date<'2026-07-01' else .01


def select_validation_arm(scores):
    winner=max(('fixed','vwap'),key=lambda a:(scores[a],a=='fixed'))
    return winner if scores[winner]>0 else 'NO_TRADE'


def bucket(at):
    t=datetime.fromisoformat(at).astimezone(NY);clock=(t.hour,t.minute)
    return 'morning' if clock<(11,30) else 'midday' if clock<(13,30) else 'afternoon'


def block_interval(values,replicates=5000,seed=1729,family=16):
    x=np.asarray(values,dtype=float);n=len(x)
    if n<30:return {'status':'insufficient_sessions','sessions':n,'positive_edge_supported':False}
    if not np.isfinite(x).all():raise ValueError('Finite session values required')
    rng=np.random.default_rng(seed);blocks=(n+4)//5
    starts=rng.integers(0,n,size=(replicates,blocks))
    indices=((starts[:,:,None]+np.arange(5))%n).reshape(replicates,-1)[:,:n]
    means=x[indices].mean(axis=1);lower=float(np.quantile(means,.05/family))
    centered=means-x.mean()
    return {'status':'conditional_exploratory_interval','sessions':n,'mean_daily_net':float(x.mean()),
       'mean_ci95':[float(np.quantile(means,.025)),float(np.quantile(means,.975))],
       'simultaneous_lower_mean':lower,'family_size':family,'block_sessions':5,'replicates':replicates,'seed':seed,
       'centered_bootstrap_p_one_sided':float((1+np.count_nonzero(centered>=x.mean()))/(replicates+1)),
       'positive_edge_supported':bool(lower>0),'limitation':'Circular moving5-session bootstrap, approximate dependence model; not a certified-news or execution validation'}


class QuantReplay(Replay):
    def step(self,start,group):
        self.config=replace(self.config,regulatory_per_side=fee_for_date(start.date().isoformat()))
        super().step(start,group)


def read_bars(path):
    bars=[]
    with Path(path).open(newline='') as stream:
        for row in csv.DictReader(stream):
            ns=int(row.pop('ts_event_ns'))
            if ns%(60*10**9):raise ValueError('Non-minute ns cannot be converted losslessly')
            for name in ('open','high','low','close','volume'):row[name]=float(row[name])
            bars.append(Bar.from_dict(row))
    return bars


def regime_label(date,volatility,threshold,learned_through):
    if date<=learned_through:return 'calibration_unclassified'
    return 'high' if volatility>=threshold else 'low'


def trade_stats(trades):
    net=[t['net'] for t in trades];gains=sum(x for x in net if x>0);loss=-sum(x for x in net if x<0)
    return {'trades':len(trades),'net':sum(net),'gross':sum(t['gross'] for t in trades),
        'fees':sum(t['fees'] for t in trades),'slippage_spread':sum(t['execution_cost'] for t in trades),
        'win_rate':sum(x>0 for x in net)/len(net) if net else None,'profit_factor':gains/loss if loss else None,
        'expectancy':sum(net)/len(net) if net else None,
        'net_R':sum(t['net']/(DISTANCES[t['symbol']][1]*POINT_VALUE[t['symbol']]) for t in trades),
        'gross_positive_net_negative':sum(t['gross']>0 and t['net']<0 for t in trades),
        'ambiguous_intrabar':sum(t['intrabar_ambiguous'] for t in trades)}


def run():
    protocol=json.loads((OUT/'preregistered-protocol.json').read_text());original=dict(protocol);h=original.pop('protocol_sha256')
    if digest(original)!=h:raise ValueError('Frozen protocol changed')
    source=Path(__file__).with_name('engine.py')
    if file_hash(source)!=protocol['baseline_code_sha256']:raise ValueError('Original baseline engine changed')
    quality=json.loads((OUT/'data-quality120.json').read_text());csv_path=OUT/'bars120.csv'
    if file_hash(csv_path)!=quality['csv_sha256']:raise ValueError('Dataset checksum mismatch')
    bars=read_bars(csv_path);dates=[s['date'] for s in CALENDAR]
    groups=defaultdict(list)
    for b in bars:groups[(b.start.date().isoformat(),b.symbol)].append(b)
    if set(groups)!={(d,s) for d in dates for s in ('MNQ','MES')}:raise ValueError('Session/instrument family incomplete')
    thresholds={}
    for symbol in ('MNQ','MES'):
        vv=[]
        for day in protocol['folds'][0]['calibration']:
            bb=groups[(day,symbol)];f=features(Request(tuple(bb),bb[-1].end));vv.extend(f.volatility[19:])
        thresholds[symbol]=float(np.median(vv))
    results=OUT/'results';results.mkdir(exist_ok=True)
    cache={}
    def execute(symbol,target,days,stress=1.,daily_independent=False,save=None):
        key=(symbol,target,tuple(days),stress,daily_independent)
        if key in cache:return cache[key]
        config=Config(**protocol['baseline_config'])
        config=replace(config,news_required=False,exit_variant=target,
                       entry_slippage_ticks=config.entry_slippage_ticks*stress,exit_slippage_ticks=config.exit_slippage_ticks*stress)
        selected=[b for d in days for b in groups[(d,symbol)]]
        if daily_independent:
            rr={'trades':[],'orders':[],'decisions':[],'equity':[],'risk_events':[]};realized=0.;peak=0.
            for d in days:
                replay=QuantReplay(groups[(d,symbol)],config);part=replay.run()
                for t in part['trades']:
                    t['causal_volatility']=replay.indicators[(t['signal_bar_start'],symbol)]['volatility']
                    t['id']=d+'-'+t['id']
                for point in part['equity']:
                    pnl=realized+point['net_pnl'];peak=max(peak,pnl)
                    rr['equity'].append({**point,'net_pnl':pnl,'drawdown':peak-pnl})
                realized+=sum(t['net'] for t in part['trades'])
                rr['trades'].extend(part['trades']);rr['risk_events'].extend(part['risk_events'])
        else:
            replay=QuantReplay(selected,config);rr=replay.run()
            for t in rr['trades']:
                t['causal_volatility']=replay.indicators[(t['signal_bar_start'],symbol)]['volatility']
        for t in rr['trades']:
            t.update(time_bucket=bucket(t['entry_at']),regime=regime_label(t['entry_at'][:10],t['causal_volatility'],thresholds[symbol],protocol['folds'][0]['calibration'][-1]))
        summary=summarize(rr);daily={d:sum(t['net'] for t in rr['trades'] if t['entry_at'].startswith(d)) for d in days}
        summary.update(trade_stats(rr['trades']),daily_net=daily,
            global_halt_latched=False if daily_independent else replay.global_halt,
            last_trade_date=rr['trades'][-1]['entry_at'][:10] if rr['trades'] else None,
            sessions_with_trades=sum(v!=0 for v in daily.values()),
            daily_risk_reset_diagnostic=daily_independent,stress_multiplier=stress,
            commissions_broker=sum(2*config.commission_per_side for t in rr['trades']),
            exchange_fees=sum(2*config.exchange_per_side for t in rr['trades']),
            regulatory_fees=sum(2*fee_for_date(t['entry_at'][:10]) for t in rr['trades']),
            time_buckets={k:trade_stats([t for t in rr['trades'] if t['time_bucket']==k]) for k in ('morning','midday','afternoon')},
            volatility_regimes={k:trade_stats([t for t in rr['trades'] if t['regime']==k]) for k in ('low','high','calibration_unclassified')},
            sides={str(k):trade_stats([t for t in rr['trades'] if t['side']==k]) for k in (-1,1)},
            exits={k:trade_stats([t for t in rr['trades'] if t['reason']==k]) for k in sorted({t['reason'] for t in rr['trades']})})
        if save:
            folder=results/save;folder.mkdir(exist_ok=True)
            atomic_json(folder/'summary.json',summary)
            write_rows(folder/'trades.csv',rr['trades']);write_rows(folder/'equity.csv',rr['equity'])
            write_rows(folder/'sessions.csv',[{'date':d,'net':v} for d,v in daily.items()])
            if not daily_independent:write_rows(folder/'decisions.csv',rr['decisions'])
        small={'summary':summary,'trades':rr['trades'],'equity':rr['equity']}
        cache[key]=small
        return small
    # Validation-only selection is frozen before any test or holdout economic replay.
    validation_scores={s:{a:0. for a in ('fixed','vwap')} for s in ('MNQ','MES')};selections=[]
    for i,fold in enumerate(protocol['folds']):
        for symbol in ('MNQ','MES'):
            scores={a:execute(symbol,a,fold['validation'])['summary']['net'] for a in ('fixed','vwap')}
            for arm,value in scores.items():validation_scores[symbol][arm]+=value
            selections.append({'fold':i,'symbol':symbol,'validation_dates':fold['validation'],
                               'validation_net':scores,'chosen':select_validation_arm(scores),'test_dates':fold['test']})
    final={s:select_validation_arm(scores) for s,scores in validation_scores.items()}
    frozen={'protocol_sha256':h,'amendment_sha256':file_hash(OUT/'protocol-amendment-01.json'),'dataset_sha256':quality['csv_sha256'],'selections':selections,
            'final_validation_aggregate':validation_scores,'final_selected':final,
            'holdout_dates':protocol['holdout'],'regime_thresholds_training_only':thresholds}
    selection_path=OUT/'validation-only-selection.json'
    if selection_path.exists():
        if json.loads(selection_path.read_text())!=frozen:raise ValueError('Selection changed after freeze; stop')
    else:atomic_json(selection_path,frozen)
    access=OUT/'holdout-access.json'
    if not access.exists():atomic_json(access,{'unlocked_after_selection_at':datetime.now(timezone.utc).isoformat(),
                   'selection_sha256':file_hash(selection_path),'external_human_unseen_attestation':False})
    wf={};test_dates=[d for fold in protocol['folds'] for d in fold['test']]
    if len(test_dates)!=len(set(test_dates)) or set(test_dates)&set(protocol['holdout']):raise ValueError('Temporal split leakage')
    for symbol in ('MNQ','MES'):
        for arm in ('fixed','vwap','selected'):
            trades=[];daily={d:0. for d in test_dates};folds=[];combined=0.;peak=0.;drawdown=0.
            for i,fold in enumerate(protocol['folds']):
                chosen=next(x['chosen'] for x in selections if x['fold']==i and x['symbol']==symbol) if arm=='selected' else arm
                if chosen=='NO_TRADE':folds.append({'fold':i,'chosen':chosen,'net':0.});continue
                res=execute(symbol,chosen,fold['test']);trades.extend([{**t,'fold':i,'id':f'fold-{i}-'+t['id']} for t in res['trades']]);daily.update(res['summary']['daily_net'])
                for point in res['equity']:
                    pnl=combined+point['net_pnl'];peak=max(peak,pnl);drawdown=max(drawdown,peak-pnl)
                combined+=res['summary']['net']
                folds.append({'fold':i,'chosen':chosen,'net':res['summary']['net']})
            wf[symbol+'/'+arm]={'metrics':{**trade_stats(trades),'max_drawdown_mark_to_minute_close':drawdown},'daily_net':daily,'folds':folds,
                                'uncertainty':block_interval(list(daily.values())),
                                'account_reset':'Fresh virtual account at each disjoint test fold, explicitly separate from continuous all-session baseline'}
            write_rows(results/(symbol+'-'+arm+'-walkforward-trades.csv'),trades)
    holdout={}
    for symbol in ('MNQ','MES'):
        for arm in ('fixed','vwap','selected'):
            chosen=final[symbol] if arm=='selected' else arm
            if chosen=='NO_TRADE':holdout[symbol+'/'+arm]={'chosen':chosen,'metrics':trade_stats([]),'daily_net':{d:0. for d in protocol['holdout']},'uncertainty':block_interval([0.]*len(protocol['holdout']))}
            else:
                res=execute(symbol,chosen,protocol['holdout']);summary=res['summary']
                holdout[symbol+'/'+arm]={'chosen':chosen,'metrics':summary,'daily_net':summary['daily_net'],
                                       'uncertainty':block_interval(list(summary['daily_net'].values()))}
                write_rows(results/(symbol+'-'+arm+'-holdout-trades.csv'),res['trades'])
    primary={};diagnostic={};stress_results={}
    for symbol in ('MNQ','MES'):
        for arm in ('fixed','vwap'):
            name=symbol+'/'+arm
            for stress in (1.,1.5,2.):
                res=execute(symbol,arm,dates,stress=stress,save=symbol+'-'+arm+'-cost'+str(stress))
                stress_results[name+'/'+str(stress)]=res['summary']
                if stress==1.:primary[name]=res['summary']
            diagnostic[name]=execute(symbol,arm,dates,daily_independent=True,save=symbol+'-'+arm+'-daily-independent')['summary']
    portfolio_replay=QuantReplay(bars,replace(Config(**protocol['baseline_config']),news_required=False))
    portfolio_result=portfolio_replay.run()
    portfolio_summary=summarize(portfolio_result)
    portfolio_summary['news_filter']='OFF_EXPLORATORY'
    portfolio_summary['global_halt_latched']=portfolio_replay.global_halt
    portfolio_summary['last_trade_date']=portfolio_result['trades'][-1]['entry_at'][:10] if portfolio_result['trades'] else None
    portfolio_folder=results/'portfolio-fixed-original-reference';portfolio_folder.mkdir(exist_ok=True)
    atomic_json(portfolio_folder/'summary.json',portfolio_summary)
    write_rows(portfolio_folder/'trades.csv',portfolio_result['trades'])
    write_rows(portfolio_folder/'equity.csv',portfolio_result['equity'])
    del portfolio_result,portfolio_replay
    strict_replay=QuantReplay(bars,Config(**protocol['baseline_config']),news=None)
    strict_result=strict_replay.run()
    if strict_result['trades']:raise ValueError('Strict missing-news mode opened a trade')
    strict_evidence={'status':'blocked','trades':0,'actual_decisions':len(strict_result['decisions']),
       'reason':'Complete CPI/NFP/FOMC point-in-time calendar evidence not certified'}
    del strict_replay,strict_result
    paired={}
    for arm in ('fixed','vwap'):
        differences=[diagnostic['MES/'+arm]['daily_net'][d]-diagnostic['MNQ/'+arm]['daily_net'][d] for d in dates]
        def relative(values):
            interval=block_interval(values)
            interval['positive_relative_difference_supported']=interval.pop('positive_edge_supported')
            return interval
        paired[arm]={'MES_minus_MNQ_daily_usd':relative(differences),
            'walk_forward_paired':relative([wf['MES/'+arm]['daily_net'][d]-wf['MNQ/'+arm]['daily_net'][d] for d in test_dates]),
            'holdout_paired':relative([holdout['MES/'+arm]['daily_net'][d]-holdout['MNQ/'+arm]['daily_net'][d] for d in protocol['holdout']]),
            'exposure_note':'One contract each, different stop-dollar risk; compare netR as well, not equal risk-dollar portfolios'}
    final_report={'status':'exploratory_quantitative_evaluation_complete_not_paper_approval',
       'protocol_sha256':h,'amendment':json.loads((OUT/'protocol-amendment-01.json').read_text()),'dataset_sha256':quality['csv_sha256'],'quant_source_sha256':file_hash(__file__),
       'primary_continuous_account':primary,'original_portfolio_fixed_reference':portfolio_summary,'daily_independent_diagnostic_rule_change':diagnostic,
       'walk_forward':wf,'holdout':holdout,'selection':frozen,'cost_stress':stress_results,'paired_instruments':paired,
       'strict_news':strict_evidence,
       'holdout_external_human_attestation':False,'timestral_enabled':False,'live_or_paper_approval':False,
       'interpretation':'Full120-session results include calibration and5previously inspected days, so are descriptive. Statistical OOS evidence uses frozen WF/holdout only; uncertified-news and minute-execution limits remain.'}
    atomic_json(OUT/'quant-results.json',final_report)
    return {'status':final_report['status'],'primary':{k:{n:v[n] for n in ('trades','net','profit_factor')} for k,v in primary.items()},
            'wf_selected':{s:wf[s+'/selected']['metrics'] for s in ('MNQ','MES')},
            'holdout_selected':{s:holdout[s+'/selected']['metrics'] for s in ('MNQ','MES')}}


if __name__=='__main__':
    print(json.dumps(run(),sort_keys=True))
