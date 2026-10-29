"""Frozen family trials; release-file gated, offline-only, no operational integration."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json,math,socket,time
import numpy as np
from data import ROOT,SYMBOLS,load_manifest,save,sha
from engine import Costs,Portfolio,daily_features,target_a,target_b,schedule_impulses,summarize,paired_bootstrap
DAY=86400
SEGMENTS={'development':('2020-01-01','2023-01-01'),'validation':('2023-01-01','2024-01-01'),'holdout':('2024-01-01','2024-12-01')}
def timestamp(date):return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())
def validate_sources():
 f=json.loads((ROOT/'source-freeze.json').read_text())
 for p,h in f['sources'].items():
  if sha(ROOT/p)!=h:raise ValueError('frozen source changed '+p)
 return f

def grid(data,interval,symbols):
 step=DAY if interval=='1d' else 3600;start=min(data[(interval,s)][0].start for s in symbols);end=max(data[(interval,s)][-1].end for s in symbols);ts=np.arange(start,end,step,dtype=np.int64);o=np.full((len(ts),len(symbols)),np.nan);c=o.copy();v=o.copy();full=np.zeros_like(o,dtype=bool)
 for k,s in enumerate(symbols):
  for b in data[(interval,s)]:
   j=(b.start-start)//step;o[j,k]=b.open;c[j,k]=b.close;v[j,k]=b.quote_volume;full[j,k]=b.full
 return {'times':ts,'open':o,'close':c,'volume':v,'full':full,'step':step,'symbols':symbols}

def fday(d,at,lookback):
 i=int(np.searchsorted(d['times'],at));return daily_features(d['close'],d['volume'],d['full'],i,lookback)

def simulate(data,segment,family,variant,cost,mode='strategy'):
 daily=grid(data,'1d',SYMBOLS if family=='A' else SYMBOLS[:2]);hourly=grid(data,'1h',SYMBOLS[:2]) if family=='C' else None;g=hourly if hourly is not None else daily;lo,hi=map(timestamp,SEGMENTS[segment]);start=int(np.searchsorted(g['times'],lo));end=int(np.searchsorted(g['times'],hi));symbols=g['symbols'];p=Portfolio(len(symbols),cost);eq=[1000.];times=[lo];expos=[];events=[];roundtrips=[];open_entry=None;exit_due=None;skipped=0;hourly_eq=[1000.];hourly_at=[lo];regimes=[];base_momentum=14 if family=='A' and variant=='primary' else 7 if family=='A' else 90 if variant=='primary' else 60
 if family=='C':
  with np.errstate(invalid='ignore',divide='ignore'):r=np.concatenate([[np.nan],np.diff(np.log(g['close'][:,0]))])
  signals=schedule_impulses(r,1 if variant=='primary' else 2,end)
 else:signals={}
 try:
  for i in range(start,end):
   at=int(g['times'][i]);prices=g['open'][i];weights=None;meta={}
   if mode=='cash':pass
   elif mode in ('bh_btc','bh_eth','fixed_cohort'):
    if i==start:
     weights=np.zeros(len(symbols))
     if mode=='bh_btc':weights[0]=1
     elif mode=='bh_eth':weights[1]=1
     else:
      x=fday(daily,at,14);weights[x['eligible']]=1/len(symbols)
     meta={'known_identity_at':'2019-12-29','fixed_initial_sleeves_unavailable_stay_cash':True}
   elif family in ('A','B'):
    if datetime.fromtimestamp(at,timezone.utc).weekday()==0:
     x=fday(daily,at,base_momentum);feature_end=at-DAY;meta={'feature_end_max':feature_end,'execution_at':at,'full_bar_lag_seconds':DAY,'latest_feature_index':x['latest_index'],'lookback':base_momentum}
     if family=='A':
      candidate=target_a(x,symbols);weights=target_a(x,symbols,mode='riskcap' if mode=='riskcap' else 'matched' if mode=='matched' else 'uncapped' if mode=='uncapped' else 'strategy',exposure=float(sum(candidate)))
     else:
      candidate=target_b(x);weights=target_b(x,trend=False) if mode=='riskcap' else np.full(2,.5) if mode=='uncapped' else target_b(x,exposure=float(sum(candidate))) if mode=='matched' else candidate
   else:
    if mode=='strategy':
     # Always process a due sell BEFORE a scheduled buy at the same boundary.
     if exit_due is not None and i>=exit_due:
      p.rebalance(prices,np.zeros(2),at,{'reason':'C_scheduled_one_hour_exit'})
      sells=p.orders[-1];roundtrips.append({'entry_at':open_entry['at'],'exit_at':at,'net':p.cash-open_entry['cash_before'],'signal_index':open_entry['signal_index']});exit_due=None;open_entry=None
     if i in signals:
      s=signals[i];meta={'signal_bar_start':int(g['times'][s['signal_index']]),'feature_end':int(g['times'][s['signal_index']])+3600,'execution_at':at,'source_event_age_seconds':at-int(g['times'][s['signal_index']])-3600,'z':s['z'],'delay_hours':1 if variant=='primary' else 2}
      if np.any(p.qty>0):skipped+=1;events.append({**meta,'status':'SKIP_OCCUPIED'})
      elif not np.isfinite(prices[1]) or prices[1]<=0:skipped+=1;events.append({**meta,'status':'SKIP_MISSING_EXECUTION_PRICE'})
      else:
       before=p.cash;p.rebalance(prices,np.array([0.,1.]),at,meta)
       if p.qty[1]>0:exit_due=i+1;open_entry={'at':at,'cash_before':before,'signal_index':s['signal_index']};events.append({**meta,'status':'ENTERED'})
    elif mode=='riskcap' and at%DAY==0:
     x=fday(daily,at,30);vol=x['vol'][1];weights=np.array([0.,min(1,.2/vol) if np.isfinite(vol) and vol>0 else 0.]);meta={'feature_end_max':at-DAY,'execution_at':at,'full_bar_lag_seconds':DAY}
    elif mode=='uncapped' and i==start:weights=np.array([.5,.5])
   if weights is not None:
    for k in np.flatnonzero((weights>0)&(~np.isfinite(prices)|(prices<=0))):events.append({'execution_at':at,'asset':symbols[k],'status':'SKIP_MISSING_EXECUTION_PRICE','target_weight':float(weights[k])})
    p.rebalance(prices,weights,at,meta)
    events.append({'at':at,'weights_requested':weights.tolist(),'metadata':meta})
   nav=p.mark(prices);held_value=nav-p.cash;expos.append(held_value/nav if nav>0 else 0)
   if i==end-1:p.rebalance(g['close'][i],np.zeros(len(symbols)),at+g['step'],{'reason':'EXPLICIT_FINITE_SEGMENT_TERMINAL_CLOSE_NOT_PRODUCTION_FILL'})
   mark=p.mark(g['close'][i],liquidation=True);closed=at+g['step'];hourly_eq.append(mark);hourly_at.append(closed)
   if closed%DAY==0:
    eq.append(mark);times.append(closed)
    x=fday(daily,at-at%DAY,90);mom=x['momentum'][0];regimes.append('BTC_90d_positive' if mom>0 else 'BTC_90d_nonpositive' if np.isfinite(mom) else 'unknown')
 except ValueError as e:
  return {'status':'INCOMPLETE_NO_PROMOTION','error':str(e),'family':family,'variant':variant,'segment':segment,'mode':mode,'orders_count_partial':len(p.orders),'partial_diagnostic_only':True}
 m=summarize(eq,times,p.orders,expos);m.update(status='COMPLETE',family=family,variant=variant,segment=segment,mode=mode,fees=p.fees,spread=p.spread,slippage=p.slippage,two_way_turnover=p.turnover,annualized_two_way_turnover=p.turnover*365/m['days'],cash_final=p.cash,asset_symbols=symbols,maximum_capital_fraction=1.,cash_yield=0.,quantity_assumption='Continuous research fractions, not certified historical exchange grids',initial_final_costs_included=True,skipped_entries=skipped)
 if mode=='matched':m['matched_exposure_definition']='Candidate-known lagged REQUESTED target total exposure, not identical realized exposure after execution costs'
 m['yearly']={}
 for year in sorted({datetime.fromtimestamp(t-1,timezone.utc).year for t in times[1:]}):
  ix=[j for j,t in enumerate(times[1:],1) if datetime.fromtimestamp(t-1,timezone.utc).year==year];m['yearly'][str(year)]={'net_return':eq[ix[-1]]/eq[ix[0]-1]-1,'net_pnl':eq[ix[-1]]-eq[ix[0]-1]}
 m['causal_BTC_regime_pnl']={r:sum(x for x,label in zip(m['daily_pnl'],regimes) if label==r) for r in sorted(set(regimes))}
 top=sorted(enumerate(m['daily_pnl']),key=lambda x:x[1],reverse=True)[:5];m['largest_daily_pnl']=[{'day_end':times[j+1],'pnl':v} for j,v in top];m['net_pnl_without_best_day_diagnostic_not_rerun']=m['net_pnl']-(top[0][1] if top else 0)
 if family=='C':
  rr=np.diff(hourly_eq)/np.array(hourly_eq[:-1]);sd=np.std(rr,ddof=1);m['hourly_sharpe_8760_secondary']=float(np.mean(rr)/sd*math.sqrt(8760)) if sd>0 else None;m['hourly_drawdown_secondary']=float(max(1-np.array(hourly_eq)/np.maximum.accumulate(hourly_eq)));gains=sum(max(0,x['net']) for x in roundtrips);losses=-sum(min(0,x['net']) for x in roundtrips)
  m['roundtrip_count']=len(roundtrips);m['roundtrip_profit_factor']=gains/losses if losses>0 else None;m['top_roundtrips']=sorted(roundtrips,key=lambda x:x['net'],reverse=True)[:5]
 return {'metrics':m,'equity':eq,'times':times,'orders':p.orders,'events':events,'roundtrips':roundtrips}

def family_errors(quality,family):
 required=[('1d',s) for s in (SYMBOLS if family=='A' else SYMBOLS[:2])]+([('1h',s) for s in SYMBOLS[:2]] if family=='C' else [])
 return {a+'/'+b:quality['errors'][a+'/'+b] for a,b in required if a+'/'+b in quality['errors']}

def compact(result):return result['metrics'] if 'metrics' in result else result

def add_market_diagnostic(main,btc):
 if main.get('status')!='COMPLETE' or btc.get('status')!='COMPLETE':
  main['market_beta_status']='UNAVAILABLE_INCOMPLETE_BTC_COMPARATOR';return
 br=np.asarray(btc['daily_returns']);sr=np.asarray(main['daily_returns']);var=float(np.var(br,ddof=1))
 main['descriptive_market_beta_BTC']=float(np.cov(sr,br,ddof=1)[0,1]/var) if var>0 else None
 main['mean_daily_excess_vs_BTC_BH']=float(np.mean(sr-br));main['market_beta_status']='AVAILABLE_DESCRIPTIVE_ONLY'


def run(phase):
 validate_sources();release=ROOT/('financial-holdout-release.json' if phase=='holdout' else 'financial-release.json')
 if not release.exists():raise ValueError('Financial evaluation locked: root release required')
 permission=json.loads(release.read_text())
 if permission.get('source_freeze_sha256')!=sha(ROOT/'source-freeze.json'):raise ValueError('release freeze mismatch')
 inputs=ROOT/('data-freeze-'+phase+'.json')
 if not inputs.exists() or permission.get('data_freeze_sha256')!=sha(inputs):raise ValueError('input freeze/release mismatch')
 for p,h in json.loads(inputs.read_text())['inputs'].items():
  if sha(ROOT/p)!=h:raise ValueError('frozen input changed '+p)
 output=ROOT/('results-'+phase)
 if output.exists():raise ValueError('Never overwrite results; explicit new scope required')
 data,quality=load_manifest(phase);output.mkdir();segments=['holdout'] if phase=='holdout' else ['development','validation'];costs=json.loads((ROOT/'config.json').read_text())['costs'];all_results={}
 for segment in segments:
  all_results[segment]={}
  for family in ('A','B','C'):
   arms={};all_results[segment][family]=arms
   modes=['strategy','riskcap','uncapped','bh_btc','bh_eth','cash']+(['matched','fixed_cohort'] if family=='A' else ['matched'] if family=='B' else [])
   for costname,cc in costs.items():
    arms[costname]={}
    for variant in ('primary','neighbor'):
     # Benchmarks identical across neighbors except exposure-matched diagnostics.
     selected=modes if variant=='primary' else ['strategy']
     for mode in selected:
      bad=family_errors(quality,family)
      result={'status':'INCOMPLETE_NO_PROMOTION','quality_errors':bad,'partial_diagnostic_only':True} if bad else simulate(data,segment,family,variant,Costs(**cc),mode);label=variant+'_'+mode;arms[costname][label]=compact(result);save(output/f'{segment}-{family}-{costname}-{label}.json',result)
      print(segment,family,costname,label,compact(result).get('status'),flush=True)
   main=arms['base']['primary_strategy'];benchmark=arms['base']['primary_matched' if family=='A' else 'primary_riskcap']
   if main.get('status')=='COMPLETE' and benchmark.get('status')=='COMPLETE':
    arms['base']['inference']=paired_bootstrap(main['daily_returns'],benchmark['daily_returns'],'mean_excess' if family=='A' else 'sharpe_difference')
    add_market_diagnostic(main,arms['base']['primary_bh_btc'])
 save(output/'results.json',{'phase':phase,'source_freeze_sha256':sha(ROOT/'source-freeze.json'),'release':permission,'input_manifest_sha256':sha(ROOT/('acquisition-'+phase+'.json')),'results':all_results,'no_parameter_search':True,'trial_primary_families':3,'trial_total_variants':6,'costs_not_independent_trials':True,'global_DSR':'NOT_ESTIMABLE_UNKNOWN_PROJECT_PRIOR_TRIAL_HISTORY','prospective':False,'past_market_public_knowledge_not_excluded':True})
 print('COMPLETE',sha(output/'results.json'))

def main():
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['development-validation','holdout']);a=p.parse_args()
 def denied(*a,**k):raise RuntimeError('Offline evaluation forbids network')
 socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied;run(a.phase)
if __name__=='__main__':main()
