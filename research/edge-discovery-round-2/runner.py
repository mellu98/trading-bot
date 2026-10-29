"""Release-gated exploratory Round2, no operational orders or network."""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import argparse,math,socket,time
import numpy as np
from data import ROOT,OLD,OUT,SYMBOLS,DAY,sha,load,save,timestamp,iso,read_cache,daily_grid,validate_hour_window,selected_archives
from signals import h1_features,h2_features,target,h1_schedule,h2_feature_index,paired_bootstrap
from reuse import Portfolio,Costs,summarize
SEGMENTS={'H1':{'development_2022':('2022-01-01','2023-01-01'),'stress_2024':('2024-01-01','2024-12-01')},'H2':{'development_2020_2022':('2020-01-01','2023-01-01'),'diagnostic_2023':('2023-01-01','2024-01-01'),'stress_2024':('2024-01-01','2024-12-01')}}

def clean(x):
 if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
 if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
 if isinstance(x,(float,np.floating)):return float(x) if np.isfinite(x) else None
 if isinstance(x,np.integer):return int(x)
 if isinstance(x,np.bool_):return bool(x)
 return x

def verify():
 f=load(OUT/'freeze.json')
 for p,h in f['sources'].items():
  if sha(OUT/p)!=h:raise ValueError('frozen Round2 source changed '+p)
 for p,h in f['inputs'].items():
  if sha(ROOT/p)!=h:raise ValueError('frozen input changed '+p)
 for p,h in f['protected'].items():
  if sha(ROOT/p)!=h:raise ValueError('protected changed '+p)
 return f

def execute(portfolio,prices,weights,at,metadata):portfolio.rebalance(np.asarray(prices),np.asarray(weights),at,metadata)

def simulate(cache,family,segment,variant,cost,mode):
 symbols=SYMBOLS[:2] if family=='H1' else SYMBOLS;daily=daily_grid(cache,symbols);start,end=map(timestamp,SEGMENTS[family][segment]);step=3600 if family=='H1' else DAY;lag=1 if variant=='primary' else 2;p=Portfolio(len(symbols),cost);eq=[1000.];times=[start];hour_eq=[1000.];exposure=[];active=set();events=[];regime_pnl=defaultdict(float);previous=1000.
 # Local scored interval checks; never import the old all-history hourly loader.
 if family=='H1':
  bad={s:validate_hour_window(cache[('1h',s)],start,end) for s in symbols}
  if any(bad.values()):return {'status':'INCOMPLETE_NO_PROMOTION','quality':bad,'not_economic_loss':True}
 try:
  for at in range(start,end,step):
   key='1h' if family=='H1' else '1d';raw=[cache[(key,s)].get(at) for s in symbols];prices=np.array([b['open'] if b else np.nan for b in raw]);closes=np.array([b['close'] if b else np.nan for b in raw]);w=None;meta={}
   i=int(np.searchsorted(daily['times'],at-at%DAY));j=i-1 if family=='H1' else h2_feature_index(i,lag)
   if mode=='cash':pass
   elif mode in ('bh_btc','bh_eth','fixed_cohort') and at==start:
    # Initial eligibility is available a whole day before initial BH fill.
    initial=h2_features(daily['close'],daily['quote'],daily['full'],i-2);w=np.zeros(len(symbols))
    if mode=='fixed_cohort':w[initial['eligible']]=1/len(symbols)
    else:
     k=0 if mode=='bh_btc' else 1
     if initial['eligible'][k]:w[k]=1
    meta={'reason':'START_ONLY_BH_INITIAL_KNOWN_ELIGIBILITY','feature_end_max':start-DAY,'execution_at':at}
   elif mode not in ('bh_btc','bh_eth','fixed_cohort') and (h1_schedule(at,lag) if family=='H1' else True):
    x=(h1_features if family=='H1' else h2_features)(daily['close'],daily['quote'],daily['full'],j);candidate=target(x,symbols,family);w=target(x,symbols,family,mode=mode,requested_exposure=float(sum(candidate)));feature_end=int(daily['times'][j])+DAY
    assert at-feature_end==(lag*3600 if family=='H1' else lag*DAY)
    meta={'feature_end_max':feature_end,'execution_at':at,'availability_lag_seconds':at-feature_end,'L':x['L'].tolist(),'eligible':x['eligible'].tolist(),'requested_primary_exposure_for_diagnostic':float(sum(candidate))}
    if family=='H1':meta.update(z=x['z'].tolist(),current_daily_logreturn=x['current_return'].tolist())
   if w is not None:
    if np.any((w>0)&(~np.isfinite(prices)|(prices<=0))):raise ValueError('missing executable target price; no ghostfill')
    execute(p,prices,w,at,meta);events.append({'at':at,'weights_requested':w.tolist(),'metadata':meta})
   nav=p.mark(prices);e=(nav-p.cash)/nav if nav>0 else 0;exposure.append(e)
   if e>1e-12:active.add(at-at%DAY)
   closed=at+step
   if closed==end:execute(p,closes,np.zeros(len(symbols)),closed,{'reason':'FINITE_SEGMENT_TERMINAL_CLOSE_RESEARCH_MODEL'})
   marked=p.mark(closes,True);hour_eq.append(marked)
   if closed%DAY==0:
    eq.append(marked);times.append(closed)
    # Descriptive regime only: BTC90 is known at least a full day beforehand.
    ri=i-2;mom=daily['close'][ri,0]/daily['close'][ri-90,0]-1 if ri>=90 else np.nan;label='BTC90positive' if mom>0 else 'BTC90nonpositive' if np.isfinite(mom) else 'unknown';regime_pnl[label]+=marked-previous;previous=marked
 except (ValueError,KeyError,IndexError) as e:return {'status':'INCOMPLETE_NO_PROMOTION','reason':str(e),'partial_diagnostic_only':True,'not_economic_loss':True}
 m=summarize(eq,times,p.orders,exposure);m.update(status='COMPLETE_EXPLORATORY',family=family,segment=segment,variant=variant,mode=mode,fees=p.fees,spread=p.spread,slippage=p.slippage,two_way_turnover=p.turnover,annualized_two_way_turnover=p.turnover*365/m['days'],active_calendar_days=len(active),cash_fraction_mean=1-m['average_exposure'],exposure_sampling='Arithmetic mean of hourly bar-open marked weights H1/daily bar-open weights H2; not continuously observed exposure',capital_reset=1000.,quantity='Continuous fractional research quantities; no historical exchange-grid certification',regime_pnl=dict(regime_pnl),modeled_liquidation_NAV=True)
 returns=np.array(m['daily_returns']);pnl=np.array(m['daily_pnl']);m['realized_daily_vol_annual_sqrt365']=float(np.std(returns,ddof=1)*math.sqrt(365));m['worst_daily_return']=float(min(returns));m['best_daily_return']=float(max(returns));m['mean_daily_return']=float(np.mean(returns));m['median_daily_return']=float(np.median(returns));m['yearly']={};m['monthly']={}
 for kind in ['yearly','monthly']:
  groups={}
  for n,t in enumerate(times[1:],1):
   key=iso(t-1)[:4 if kind=='yearly' else 7]
   if key not in groups:groups[key]=[n-1,n]
   else:groups[key][1]=n
  for key,(a,b) in groups.items():m[kind][key]={'return':eq[b]/eq[a]-1,'pnl':eq[b]-eq[a]}
 top=np.argsort(pnl)[-5:][::-1];bottom=np.argsort(pnl)[:5];m['best_pnl_days']=[{'date':iso(times[int(n)+1]-1)[:10],'pnl':float(pnl[n]),'return':float(returns[n])} for n in top];m['worst_pnl_days']=[{'date':iso(times[int(n)+1]-1)[:10],'pnl':float(pnl[n]),'return':float(returns[n])} for n in bottom];m['net_without_best5_days_fixedpath_DIAGNOSTIC_NOT_RERUN']=float(sum(pnl)-sum(sorted(pnl,reverse=True)[:5]))
 if family=='H1':m['hourly_drawdown_secondary']=float(max(1-np.array(hour_eq)/np.maximum.accumulate(hour_eq)))
 if mode=='matched':m['matched_definition']='Known requested strategy total target exposure, not exactly realized exposure; H1 inherits timing and is NOT independent timing evidence; H2 only a relative-ranking contrast'
 assert abs(eq[-1]-p.cash)<1e-7 and np.all(p.qty==0)
 return {'metrics':clean(m),'equity':eq,'times':times,'orders':clean(p.orders),'events':clean(events)}

def ok(m):return m.get('status')=='COMPLETE_EXPLORATORY'
def finite(x):return x is not None and np.isfinite(x)
def screen(all_results):
 assessed={}
 for family,segments in all_results.items():
  gates={}
  for segment,costs in segments.items():
   for scenario in ['base','adverse','severe']:
    m=costs[scenario]['primary_strategy'];gates[segment+'_'+scenario+'_primary_net']=ok(m) and (m['net_return']>=0 if scenario=='severe' else m['net_return']>0)
  stress=segments['stress_2024'];m=stress['base']['primary_strategy'];risk=stress['base']['primary_riskcap'];valid=ok(m) and ok(risk)
  for scenario in ['base','adverse']:
   n=stress[scenario]['neighbor_strategy'];gates['stress_neighbor_'+scenario]=ok(n) and n['net_return']>0
  gates['stress_days_180_active_days_30']=valid and m['days']>=180 and m['active_calendar_days']>=30
  gates['stress_daily_DD']=valid and m['max_drawdown']<=risk['max_drawdown']
  a=m.get('daily_sharpe_365');b=risk.get('daily_sharpe_365');gates['stress_base_sharpe']=valid and finite(a) and finite(b) and (a>b if family=='H1' else a>=b)
  if family=='H2':
   matched=stress['base']['primary_matched'];gates['stress_mean_daily_excess_positive']=ok(m) and ok(matched) and sum(m['daily_returns'])>sum(matched['daily_returns'])
  blocks=stress['base'].get('inference',{}).get('blocks',{})
  for k in ['7','30']:
   z=blocks.get(k,{});gates['conditional_bootstrap_lower_block'+k]=z.get('status')=='OK' and finite(z.get('lower_family2')) and z['lower_family2']>0
  assessed[family]={'promising_for_future_observation_ONLY':bool(all(gates.values())),'gates':clean(gates),'not_financial_approval':True,'not_OOS_or_global_significance':True}
 return {'families':assessed,'any_promising_screen':any(m['promising_for_future_observation_ONLY'] for m in assessed.values()),'H3':'EXCLUDED_NOT_EVALUABLE_NO_MAKER_BACKTEST','global_DSR':'NOT_ESTIMABLE_UNKNOWN_PAST_PROJECT_TRIAL_HISTORY','variant_count':4,'all_results_exploratory_seen_history':True}

def run():
 verify();release=OUT/'release.json'
 if not release.exists():raise ValueError('root financial release required')
 permission=load(release)
 if permission.get('freeze_sha256')!=sha(OUT/'freeze.json'):raise ValueError('release freeze mismatch')
 dest=OUT/'results'
 if dest.exists():raise ValueError('Never overwrite results')
 cache,quality=read_cache();dest.mkdir();config=load(OUT/'config.json');results={}
 for family,segments in SEGMENTS.items():
  results[family]={}
  for segment in segments:
   results[family][segment]={}
   for scenario,cc in config['costs'].items():
    arms={};results[family][segment][scenario]=arms
    for variant in ['primary','neighbor']:
     modes=['strategy','riskcap','matched','uncapped','fixed_cohort','bh_btc','bh_eth','cash'] if variant=='primary' else ['strategy']
     for mode in modes:
      result=simulate(cache,family,segment,variant,Costs(**cc),mode);label=variant+'_'+mode;arms[label]=result.get('metrics',result);save(dest/f'{family}-{segment}-{scenario}-{label}.json',clean(result));print(family,segment,scenario,label,arms[label]['status'],flush=True)
   primary=results[family][segment]['base']['primary_strategy'];comparator=results[family][segment]['base']['primary_riskcap' if family=='H1' else 'primary_matched']
   if ok(primary) and ok(comparator):results[family][segment]['base']['inference']=paired_bootstrap(primary['daily_returns'],comparator['daily_returns'],'sharpe_difference' if family=='H1' else 'mean_excess')
 save(dest/'results.json',clean({'results':results,'freeze_sha256':sha(OUT/'freeze.json'),'release':permission,'exploratory_not_independent_OOS':True,'primary_families':2,'variants':4,'costs_and_benchmarks_not_independent_trials':True,'no_B_evaluation':True,'H3_excluded':True}));save(OUT/'assessment.json',screen(results));verify();print('RESULTS_SHA',sha(dest/'results.json'),'ASSESSMENT_SHA',sha(OUT/'assessment.json'))

def freeze():
 p=OUT/'freeze.json'
 if p.exists():raise ValueError('freeze exists')
 transcript=(OUT/'tests-green.txt').read_text()
 if 'passed' not in transcript or 'failed' in transcript or 'ERROR' in transcript:raise ValueError('successful synthetic tests required before freeze')
 inputs={}
 for a in selected_archives():
  for key in ['path','checksum_path']:q=(OLD/a[key]).relative_to(ROOT);inputs[str(q)]=sha(ROOT/q)
 for name in ['acquisition-development-validation.json','acquisition-holdout.json','source-freeze.json','universe.json']:
  q=(OLD/name).relative_to(ROOT);inputs[str(q)]=sha(ROOT/q)
 b=load(OLD/'source-freeze.json')
 for name in b['sources']:
  q=(OLD/name).relative_to(ROOT);inputs[str(q)]=sha(ROOT/q);assert inputs[str(q)]==b['sources'][name]
 for name in ['research/btceth-b-followup/prospective-protocol.json','reports/PROJECT-VERDICT.md','reports/STRATEGY-RESEARCH-2026.md','reports/BTCETH-B-VALIDATION.md','data/binance-spot/research/README.md']:inputs[name]=sha(ROOT/name)
 protected=load(ROOT/'reports/binance-spot/pause-ab/protected-before.json');assert all(sha(ROOT/q)==h for q,h in protected.items())
 names=['reuse.py','data.py','signals.py','runner.py','test_round2.py','config.json','protocol.json','inventory.json'];save(p,{'at_ns':time.time_ns(),'sources':{n:sha(OUT/n) for n in names},'inputs':inputs,'protected':protected,'new_financial_runs_before_freeze':0,'network_downloads':0,'old_B_unchanged':True,'input_archive_pairs':len(selected_archives()),'all_periods_seen_exploratory':True,'test_transcript_sha256':sha(OUT/'tests-green.txt'),'pre_financial_amendment':{'preserved_provisional':'freeze-provisional.json','sha256':sha(OUT/'freeze-provisional.json'),'reason':'Synthetic terminal-liquidation fixture initially made second day inactive, so position was correctly flat before terminal; fixture now keeps second target active. No economic rule change, no financial run. Freeze guard now rejects failed pytest transcripts.'},'C_blind_and_root_release_required':True});print('SOURCE_INPUT_FREEZE',sha(p))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
 def denied(*a,**k):raise RuntimeError('Round2 offline: network forbidden')
 socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
 freeze() if args.action=='freeze' else run()
