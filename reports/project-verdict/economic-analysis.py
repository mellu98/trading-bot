"""Bounded offline audit of frozen ledgers, not a strategy replay or optimizer."""
from pathlib import Path
from decimal import Decimal as D
from datetime import datetime,timedelta,timezone
from collections import Counter,defaultdict
import calendar,csv,hashlib,io,json,math,statistics,sys,zipfile
import numpy as np
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
B='reports/binance-spot/breakout-4h'; H=3600000000000

def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def read(p):return json.loads((ROOT/p).read_text())
def rows(p):return list(csv.DictReader((ROOT/p).open()))
def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def check_protected():
 m=read('reports/binance-spot/pause-ab/protected-before.json');bad=[p for p,h in m.items() if sha(p)!=h]
 assert not bad,bad
 return {'count':len(m),'matches_original':True,'manifest_sha256':sha('reports/binance-spot/pause-ab/protected-before.json'),'current':{p:sha(p) for p in m}}

def freeze():
 targets=[B+'/'+n for n in ['protocol.json','execution-freeze.json','acquisition.json','data-quality.json','run-1/results.json','run-2/results.json']]
 targets+=list(read(B+'/execution-freeze.json')['sources'])
 targets+=list(read('reports/market-data-research/diagnostics.json')['input_sha256'])
 targets+=['reports/market-data-research/diagnostics.json','reports/binance-spot/timestral-abc/run-1/results.json','reports/binance-spot/research/run-1/results.json']
 targets+=['reports/project-verdict/economic-analysis.py']
 for segment in ('observed_development','reserved_test'):
  for cost in ('base','adverse','severe'):
   for arm in ('strategy','buy_hold_100'):
    targets += [f'{B}/run-1/{segment}/{cost}/{arm}/{name}' for name in ('trades.csv','equity.csv','metrics.json')]
 f={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Existing exact frozen trades only; no new strategy replay, no optimization, no new history. Independent Decimal accounting, concentration/stability/risk diagnostics. Reproduce original circular 1/5/10-day block bootstrap only, 10000 seed1729, not new strategy tests.','inputs':{p:sha(p) for p in targets},'protected_before':check_protected()}
 assert not (OUT/'economic-freeze.json').exists(),'Do not overwrite freeze'
 save(OUT/'economic-freeze.json',f)
 print('FROZEN',len(f['inputs']),'inputs',sha('reports/project-verdict/economic-freeze.json'))

def bootstrap(values,k):
 x=np.asarray(values);n=len(x);rng=np.random.default_rng(1729)
 starts=rng.integers(0,n,(10000,math.ceil(n/k)))
 ix=((starts[:,:,None]+np.arange(k))%n).reshape(10000,-1)[:,:n]
 means=x[ix].mean(axis=1)
 return {'mean_daily_net':float(x.mean()),'ci95':np.quantile(means,[.025,.975]).tolist(),'one_sided95_lower':float(np.quantile(means,.05))}

def audit_data():
 acq=read(B+'/acquisition.json');bars=[];digest=hashlib.sha256();months=[]
 for a in acq['archives']:
  assert sha(a['path'])==a['sha256'];assert sha(a['checksum_path'])==a['checksum_sha256']
  assert (ROOT/a['checksum_path']).read_text().split()==[a['sha256'],Path(a['path']).name]
  with zipfile.ZipFile(ROOT/a['path']) as z:
   assert z.namelist()==[Path(a['path']).stem+'.csv'];content=z.read(z.namelist()[0])
  y,m=map(int,a['month'].split('-'));factor=1000 if y>=2025 else 1000000;part=list(csv.reader(io.StringIO(content.decode())))
  assert len(part)==calendar.monthrange(y,m)[1]*24
  for row in part:
   start=int(row[0])*factor;end=start+H
   assert start%H==0 and int(row[6])*factor==end-factor
   assert not bars or bars[-1]['end']==start
   o,h,l,c,v=map(D,row[1:6]);assert min(o,h,l,c)>0 and v>=0 and l<=min(o,c)<=max(o,c)<=h
   b=dict(start=start,end=end,open=str(o),high=str(h),low=str(l),close=str(c),volume=str(v),unit='us' if y>=2025 else 'ms',original_open=int(row[0]),original_close=int(row[6]))
   digest.update((json.dumps(b,sort_keys=True)+'\n').encode());bars.append(b)
  months.append({'month':a['month'],'hours':len(part),'csv_sha256':hashlib.sha256(content).hexdigest(),'archive_sha256':a['sha256']})
 q=read(B+'/data-quality.json');assert digest.hexdigest()==q['dataset_sha256'];assert len(bars)==16056
 assert all(a['csv_sha256']==b['csv_sha256'] for a,b in zip(months,q['months']))
 return {'status':'PASS','hours':len(bars),'complete_four_hour_bars':len(bars)//4,'gaps':0,'duplicates':0,'dataset_sha256':digest.hexdigest(),'months':months,'start':bars[0]['start'],'end':bars[-1]['end']}

def audit_arm(segment,cost,arm):
 base=f'{B}/run-1/{segment}/{cost}/{arm}';tt=rows(base+'/trades.csv');ee=rows(base+'/equity.csv');m=read(base+'/metrics.json');nets=[D(t['net']) for t in tt]
 gains=sum((x for x in nets if x>0),D(0));losses=-sum((x for x in nets if x<0),D(0))
 sums={k:sum((D(t[k]) for t in tt),D(0)) for k in ('net','gross_raw','gross','fees','spread_cost','slippage_cost')}
 for t in tt:
  q=D(t['quantity']);entry=D(t['entry_fill']);exit=D(t['exit_fill']);f=D('.001') if cost=='base' else D('.0015') if cost=='adverse' else D('.002')
  assert D(t['entry_fee'])==q*entry*f and D(t['exit_fee'])==q*exit*f
  assert D(t['gross'])==q*(exit-entry) and D(t['fees'])==D(t['entry_fee'])+D(t['exit_fee'])
  assert D(t['net'])==q*exit-D(t['exit_fee'])-D(t['entry_cash'])
  assert abs(D(t['gross_raw'])-D(t['spread_cost'])-D(t['slippage_cost'])-D(t['gross']))<D('1e-20')
  assert D(t['entry_cash'])<=100 and q%D('.00001')==0
  if arm=='strategy':assert D(t['initial_modeled_risk_usdt'])<=1
 assert sums['net']==D(m['net'])==D(m['final_cash'])-1000
 assert sums['fees']==D(m['fees']);assert sums['gross']==D(m['gross_after_modeled_execution'])
 pf=float(gains/losses) if losses else None;assert pf==m['profit_factor']
 peak=0.;dd=0.;closes={}
 for e in ee:
  n=float(e['net']);peak=max(peak,n);dd=max(dd,peak-n)
  date=(datetime.fromisoformat(e['at'])-timedelta(microseconds=1)).date().isoformat();closes[date]=n
 assert abs(dd-m['max_drawdown_hour_close_including_liquidation_costs'])<1e-10
 prev=0.;daily={}
 for date,n in closes.items():daily[date]=n-prev;prev=n
 assert all(abs(daily[d]-n)<1e-12 for d,n in m['daily_marked_net'].items())
 monthly=defaultdict(float);quarterly=defaultdict(float)
 for d,n in daily.items():monthly[d[:7]]+=n;quarterly[d[:4]+'-Q'+str((int(d[5:7])-1)//3+1)]+=n
 streak=longest=0
 for n in nets:streak=streak+1 if n<0 else 0;longest=max(longest,streak)
 duration=[(int(t['exit_ns'])-int(t['entry_ns']))/H for t in tt]
 positive=sorted([t for t in tt if D(t['net'])>0],key=lambda t:D(t['net']),reverse=True)
 concentration=[]
 for k in (1,2,3):
  removed=sum((D(t['net']) for t in positive[:k]),D(0));remaining=gains-removed
  concentration.append({'removed_top_winners':k,'removed_net':str(removed),'remaining_net_fixed_ledger':str(sums['net']-removed),'remaining_pf_fixed_ledger':float(remaining/losses) if losses else None})
 result={'segment':segment,'cost':cost,'arm':arm,'trades':len(tt),'net':str(sums['net']),'gross_raw':str(sums['gross_raw']),'gross_after_execution':str(sums['gross']),'fees':str(sums['fees']),'spread':str(sums['spread_cost']),'slippage':str(sums['slippage_cost']),'profit_factor':pf,'win_rate':sum(x>0 for x in nets)/len(nets) if nets else None,'expectancy':float(sums['net']/len(nets)) if nets else None,'payoff_sample_sd':statistics.stdev(map(float,nets)) if len(nets)>1 else None,'max_hour_close_dd':dd,'daily_marked_sample_sd':statistics.stdev(daily.values()),'longest_losing_trade_streak':longest,'positive_months':sum(x>0 for x in monthly.values()),'monthly_marked_net':dict(monthly),'quarterly_marked_net':dict(quarterly),'holding_hours_median':statistics.median(duration) if duration else None,'holding_hours_max':max(duration,default=0),'exposure_hours_upper_bound':m.get('exposure_hours_upper_bound'),'total_hours':len(ee),'entry_cash_min':str(min(D(t['entry_cash']) for t in tt)),'entry_cash_max':str(max(D(t['entry_cash']) for t in tt)),'time_weighted_entry_cash_upper_bound':sum(float(D(t['entry_cash']))*h for t,h in zip(tt,duration))/len(ee),'top_winners':[{k:t[k] for k in ('entry_at','exit_at','net','initial_modeled_risk_usdt','quantity')} for t in positive[:3]],'leave_top_out':concentration,'worst_trade':str(min(nets)),'best_trade':str(max(nets)),'terminal_exits':sum(t['exit_reason']=='split_terminal_close' for t in tt),'intrabar_stop_hour_bounds':sum(t['exit_reason']=='intrabar_stop' for t in tt),'risk_halts':m['risk_halts'],'rejections':m['rejections'],'initial_risk_range':[str(min(D(t['initial_modeled_risk_usdt']) for t in tt)),str(max(D(t['initial_modeled_risk_usdt']) for t in tt))]}
 if segment=='reserved_test' and cost=='base':
  result['bootstrap_recomputed']={str(k):bootstrap(list(daily.values()),k) for k in (1,5,10)}
  assert result['bootstrap_recomputed']==m['uncertainty']['blocks']
  result['daily_marked_net']=daily
 return result

def run():
 f=read('reports/project-verdict/economic-freeze.json')
 assert all(sha(p)==h for p,h in f['inputs'].items()),'Frozen input changed'
 for p,h in read(B+'/execution-freeze.json')['sources'].items():assert sha(p)==h
 assert sha(B+'/protocol.json')==read(B+'/execution-freeze.json')['protocol_sha256']
 assert sha(B+'/run-1/results.json')==sha(B+'/run-2/results.json')
 data=audit_data();arms=[audit_arm(s,c,a) for s in ('observed_development','reserved_test') for c in ('base','adverse','severe') for a in ('strategy','buy_hold_100')]
 futures=read('reports/market-data-research/diagnostics.json');futures_out={}
 for p,h in futures['input_sha256'].items():assert sha(p)==h
 for name,a in futures['arms'].items():
  p=next(p for p in futures['input_sha256'] if p.endswith('trades.csv') and '/'+name+'/' in p);tt=rows(p);keys=list(tt[0]);numeric={}
  for k in ('gross','fees','slippage_spread','net'):
   if k in keys:numeric[k]=sum(float(t[k]) for t in tt)
  assert len(tt)==a['trades'];assert abs(numeric['net']-a['net'])<1e-7
  futures_out[name]={k:a.get(k) for k in ('trades','gross','fees','execution_cost','net','profit_factor','win_rate','expectancy','adverse_cost_scenario_net')};futures_out[name]['ledger_reconciled']=True
 abc=read('reports/binance-spot/timestral-abc/run-1/results.json');abc_metrics={}
 for period,costs in abc['economic_results'].items():
  abc_metrics[period]={}
  for cost,groups in costs.items():abc_metrics[period][cost]={arm:{k:m.get(k) for k in ('trades','net','profit_factor','max_drawdown_hour_close_including_liquidation_costs')} for arm,m in groups.items() if isinstance(m,dict) and 'trades' in m}
 end=check_protected();assert end['current']==f['protected_before']['current'];assert all(sha(p)==h for p,h in f['inputs'].items())
 out={'scope':'Independent frozen-ledger audit; no new backtest/no downloads/no runtime change. No claim of independent out-of-sample from reinspection.','data_audit':data,'arms':arms,'futures_existing_daily_reset_diagnostics':futures_out,'timestral_existing':abc_metrics,'timestral_verdicts':abc['verdicts'],'prior_spot_sma168':{k:{j:v.get(j) for j in ('trades','net','profit_factor','max_drawdown_hour_close_including_liquidation_costs')} for k,v in read('reports/binance-spot/research/run-1/results.json')['results'].items()},'protected_integrity':{k:v for k,v in end.items() if k!='current'},'freeze_sha256':sha('reports/project-verdict/economic-freeze.json'),'recommendation':'CAMBIARE STRATEGIA','recommendation_evidence_strength':'media','future_profitability_evidence_strength':'bassa','independent_oos_available_now':False,'scientific_verdict':'Economic edge not established; reject further complexity investment in the current configuration, not proof the true edge is negative.','parameter_sensitivity':'Not estimated: no grid allowed; three frozen costs resimulations only.','bootstrap_limitation':'Existing circular daily marked-PnL bootstrap conditional on observed path; 26 dependent trades and one regime event, not an IID confidence claim or future probability.','leave_top_out_limitation':'Fixed-ledger sensitivity, not an executable rerun: removing trades changes opportunities/risk/cash.','execution_limitations':['Closed 4h signal is causal, but next-native-hour open is same boundary; backtest assumes zero observation/order latency. Real next executable bid/ask after close availability is unmeasured.','1h OHLC are transactions, not historical L1; spread/depth/queue/slippage/fee grids are modeled not observed account fills.','Stop-gap first and stop-only avoid optimistic target precedence, but one-hour low cannot certify tick path or stop availability. Exposure hours are upper bounds.','Hourly close drawdown can miss worse intrahour marks; modeled 1-USDT risk is not a guaranteed gap-loss limit.','All 2025 and Jan-Sep2026 now spent/observed; recent native4h context is warmup, not prospective economic validation.']}
 save(OUT/'economic.json',out)
 print('PASS',len(arms),'spot ledgers; 6 futures ledgers; official archives; bootstrap exact; protected',end['count'])
 print(json.dumps(arms[6],indent=2)[:6500]);print('TIMESTRAL',abc_metrics['primary']['base'])
if __name__=='__main__':freeze() if sys.argv[1:]==['freeze'] else run()
