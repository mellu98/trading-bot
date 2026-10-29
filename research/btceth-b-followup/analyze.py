"""Read-only accounting diagnosis of existing B ledgers. No strategy runs or network."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import defaultdict
import csv,hashlib,io,json,math,socket,sys,time,zipfile
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent;OLD=ROOT/'research/strategy-discovery-2026';DAY=86400

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def iso(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
def group(t,kind):
 d=datetime.fromtimestamp(t-1,timezone.utc)
 return d.strftime('%Y-%m') if kind=='month' else f'{d.year}-Q{(d.month-1)//3+1}' if kind=='quarter' else f'{d.isocalendar().year}-W{d.isocalendar().week:02}'

def period_table(equity,times,kind):
 result=[];groups={}
 for i in range(1,len(equity)):
  key=group(times[i],kind)
  if key not in groups:groups[key]=[i-1,i]
  else:groups[key][1]=i
 for key,(a,b) in groups.items():result.append({'period':key,'start':iso(times[a]),'end':iso(times[b]),'days':b-a,'net_pnl':float(equity[b]-equity[a]),'return':float(equity[b]/equity[a]-1)})
 assert abs(sum(x['net_pnl'] for x in result)-(equity[-1]-equity[0]))<1e-8
 return result

def distribution(values):
 x=np.asarray(values,dtype=float)
 return {'count':len(x),'mean':float(np.mean(x)),'sample_sd':float(np.std(x,ddof=1)) if len(x)>1 else None,'min':float(np.min(x)),'q05_q25_median_q75_q95':np.quantile(x,[.05,.25,.5,.75,.95]).tolist(),'max':float(np.max(x)),'positive_count':int(sum(x>0)),'negative_count':int(sum(x<0)),'zero_count':int(sum(x==0)),'interpretation':'Descriptive dependent observations; no IID inference or new financial trial'}

def drawdown_detail(equity,times):
 x=np.asarray(equity);peak=np.maximum.accumulate(x);dd=1-x/peak;trough=int(np.argmax(dd));pi=int(np.argmax(x[:trough+1]));recovery=next((i for i in range(trough+1,len(x)) if x[i]>=x[pi]),None)
 return {'drawdown':float(dd[trough]),'peak_at':int(times[pi]),'peak_utc':iso(times[pi]),'trough_at':int(times[trough]),'trough_utc':iso(times[trough]),'peak_to_trough_days':(times[trough]-times[pi])/DAY,'recovery_at':int(times[recovery]) if recovery is not None else None,'recovery_utc':iso(times[recovery]) if recovery is not None else None,'underwater_days_to_recovery_or_end':(times[recovery if recovery is not None else -1]-times[pi])/DAY,'daily_liquidation_NAV_not_intraday':True}

def cost_totals(orders,n=2):
 assets=[{k:0. for k in ['fee','spread','slippage','total']} for _ in range(n)]
 for order in orders:
  a=assets[order['asset_index']]
  for k in ['fee','spread','slippage']:a[k]+=order[k]
 for a in assets:a['total']=sum(a[k] for k in ['fee','spread','slippage'])
 return {'assets':assets,'all':{k:sum(a[k] for a in assets) for k in assets[0]}}

def attribute(equity,times,orders,bars,liquidation_factor):
 n=len(bars);qty=np.zeros(n);cash=float(equity[0]);previous_liq=np.zeros(n);previous_raw=np.zeros(n);daily=[];byday=defaultdict(list)
 for order in orders:
  at=order['at'];terminal=str(order.get('metadata',{}).get('reason','')).startswith('EXPLICIT_FINITE_SEGMENT_TERMINAL_CLOSE')
  if terminal:
   assert at==times[-1];day=at-DAY
  else:
   assert times[0]<=at<times[-1];day=at-at%DAY
  byday[day].append(order)
 for i in range(1,len(times)):
  start=times[i-1];end=times[i];flow=np.zeros(n);rawflow=np.zeros(n);friction=np.zeros(n);regular=[];terminal=[]
  for order in byday[start]:
   (terminal if order['at']==end else regular).append(order)
  def execute(order):
   nonlocal cash
   j=order['asset_index'];q=order['quantity'];buy=order['side']=='BUY';sign=1 if buy else -1
   delta=-sign*q*order['fill']-order['fee'];rawdelta=-sign*q*order['raw'];cash+=delta;flow[j]+=delta;rawflow[j]+=rawdelta;friction[j]+=order['fee']+order['spread']+order['slippage'];qty[j]+=sign*q
   if abs(qty[j])<1e-12:qty[j]=0
   assert abs(rawdelta-delta-(order['fee']+order['spread']+order['slippage']))<1e-8
  for order in regular:execute(order)
  opens=np.array([b[start]['open'] for b in bars]);closes=np.array([b[start]['close'] for b in bars]);nav_open=cash+float(qty@opens);exposure=float(qty@opens)/nav_open
  opening_quantity=qty.copy()
  for order in terminal:execute(order)
  marked_raw=qty*closes;marked_liq=marked_raw*liquidation_factor;net=flow+marked_liq-previous_liq;gross=rawflow+marked_raw-previous_raw;reserve_delta=(marked_raw-marked_liq)-(previous_raw-previous_liq)
  assert np.allclose(net,gross-friction-reserve_delta,atol=1e-8,rtol=0)
  assert abs(cash+sum(marked_liq)-equity[i])<1e-7
  assert abs(sum(net)-(equity[i]-equity[i-1]))<1e-7
  daily.append({'date':iso(start)[:10],'start':start,'end':end,'asset_net_pnl':net.tolist(),'asset_raw_marked_pnl':gross.tolist(),'actual_execution_cost':friction.tolist(),'exit_reserve_delta':reserve_delta.tolist(),'opening_quantity':opening_quantity.tolist(),'opening_exposure':exposure,'opening_cash_fraction':1-exposure,'orders':len(byday[start])})
  previous_liq=marked_liq;previous_raw=marked_raw
 return {'daily':daily,'asset_net_pnl':np.sum([d['asset_net_pnl'] for d in daily],axis=0).tolist(),'asset_raw_marked_pnl':np.sum([d['asset_raw_marked_pnl'] for d in daily],axis=0).tolist(),'exposure_average':float(np.mean([d['opening_exposure'] for d in daily])),'exposure_max':float(max(d['opening_exposure'] for d in daily)),'cash_fraction_average':float(np.mean([d['opening_cash_fraction'] for d in daily])),'days_fully_cash':sum(d['opening_exposure']<1e-12 for d in daily),'costs':cost_totals(orders,n),'attribution_definition':'Net contribution = asset trade cashflows + change in liquidation-valued inventory. No FIFO, no claim of causal alpha. Exact cash/NAV reconciliation; changes in hypothetical exit reserve shown separately.'}

def bars_read():
 series=[{},{}];names=['BTCUSDT','ETHUSDT']
 for name in ['acquisition-development-validation.json','acquisition-holdout.json']:
  for a in load(OLD/name)['archives']:
   if a['interval']!='1d' or a['symbol'] not in names:continue
   p=OLD/a['path'];c=OLD/a['checksum_path'];assert sha(p)==a['sha256'] and sha(c)==a['checksum_sha256'];assert c.read_text().split()==[a['sha256'],p.name]
   with zipfile.ZipFile(p) as z:rows=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
   for row in rows:
    t=int(row[0])//1000;assert t<1733011200 # No December2024 or2025/26 prices.
    series[names.index(a['symbol'])][t]={'open':float(row[1]),'close':float(row[4]),'quote_volume':float(row[7])}
 return series

def input_paths():
 p=[Path('reports/PROJECT-VERDICT.md'),Path('reports/STRATEGY-RESEARCH-2026.md')]
 for q in ['source-freeze.json','protocol.json','config.json','data-freeze-development-validation.json','data-freeze-holdout.json','acquisition-development-validation.json','acquisition-holdout.json','assessment.json','results-development-validation/results.json','results-holdout/results.json']:p.append((OLD/q).relative_to(ROOT))
 for phase in ['results-development-validation','results-holdout']:
  p += [x.relative_to(ROOT) for x in (OLD/phase).glob('*-B-*.json')]
 for name in ['acquisition-development-validation.json','acquisition-holdout.json']:
  for a in load(OLD/name)['archives']:
   if a['interval']=='1d' and a['symbol'] in ['BTCUSDT','ETHUSDT']:p += [(OLD/a[k]).relative_to(ROOT) for k in ['path','checksum_path']]
 for name in ['research/execution-freeze.json','research/acquisition.json','research/run-1/results.json','breakout-4h/protocol.json','breakout-4h/execution-freeze.json','breakout-4h/acquisition.json','breakout-4h/run-1/results.json','timestral-abc/execution-freeze.json','timestral-abc/run-1/results.json']:p.append(Path('reports/binance-spot')/name)
 return sorted(set(p))

def freeze():
 p=OUT/'analysis-freeze.json';assert not p.exists();m=load(ROOT/'reports/binance-spot/pause-ab/protected-before.json');assert all(sha(ROOT/q)==h for q,h in m.items());save(p,{'at_ns':time.time_ns(),'inputs':{str(q):sha(ROOT/q) for q in input_paths()},'analysis_sources':{q:sha(OUT/q) for q in ['analyze.py','test_analysis.py','prospective-protocol.json']},'protected':m,'no_2025_2026_evaluation':'Provenance-only metadata read; no price archive or B economic run for2025/26; project-level history already observed before B freeze.','scope':'Transform existing B ledgers only, no optimization/strategy replay/benchmark variant/network.'});print('FROZEN',sha(p))

def provenance():
 b=load(OLD/'source-freeze.json');br=load(ROOT/'reports/binance-spot/breakout-4h/acquisition.json');tf=load(ROOT/'reports/binance-spot/timestral-abc/execution-freeze.json');sr=load(ROOT/'reports/binance-spot/research/acquisition.json')
 return {'pristine_2025_2026_project_holdout':False,'run_2025_2026_authorized_here':False,'B_optimized_on_2025_claim':'NOT_ESTABLISHED; do not make it. B frozen calculations exclude2025/26; prior project observation motivated strategy change, which prevents untouched-project-holdout status.','old_SMA_freeze':load(ROOT/'reports/binance-spot/research/execution-freeze.json')['frozen_at'],'old_SMA_2025_acquisition_completed':sr['completed_at'],'old_breakout_2026_acquisition_completed_ns':br['completed_at_ns'],'old_breakout_completed_utc':iso(br['completed_at_ns']/1e9),'old_Timestral_freeze_ns':tf['at_ns'],'old_Timestral_already_observed':load(ROOT/'reports/binance-spot/timestral-abc/run-1/results.json')['historical_only_already_observed'],'B_freeze_ns':b['at_ns'],'B_freeze_utc':iso(b['at_ns']/1e9),'B_protocol_history':load(OLD/'protocol.json')['history'],'metadata_chronology_limits':'Embedded original receipts and unchanged source/result hashes, not independent external timestamp notarization. File mtime not used as evidence.'}

def run():
 f=load(OUT/'analysis-freeze.json')
 for p,h in f['inputs'].items():assert sha(ROOT/p)==h,p
 for p,h in f['analysis_sources'].items():assert sha(OUT/p)==h,p
 oldf=load(OLD/'source-freeze.json');assert sha(OLD/'source-freeze.json')=='17d58cc404464ff6e812755cf514f98e14eaa7e29ae608310d03f073b1e0b410';assert all(sha(OLD/p)==h for p,h in oldf['sources'].items());assert all(sha(ROOT/p)==h for p,h in f['protected'].items())
 bars=bars_read();config=load(OLD/'config.json');results={};compact=[];details2023={}
 for segment,folder in [('development','results-development-validation'),('validation','results-development-validation'),('holdout','results-holdout')]:
  results[segment]={}
  for scenario in ['base','adverse','severe']:
   results[segment][scenario]={};cost=config['costs'][scenario];factor=(1-cost['spread']/2)*(1-cost['slip'])*(1-cost['fee'])
   for label in ['primary_strategy','neighbor_strategy','primary_riskcap','primary_uncapped','primary_bh_btc','primary_bh_eth','primary_matched','primary_cash']:
    source=f'{folder}/{segment}-B-{scenario}-{label}.json';x=load(OLD/source);m=x['metrics'];selected={k:m.get(k) for k in ['net_return','net_pnl','cagr','daily_sharpe_365','daily_sortino_365_rf0_all_day_downside_rms','max_drawdown','daily_pnl_profit_factor','average_exposure','maximum_exposure','two_way_turnover','annualized_two_way_turnover','fees','spread','slippage','order_count','days','capital_initial','capital_final']};selected.update(source=source,scenario=scenario,label=label,segment=segment);compact.append(selected)
    if label not in ['primary_strategy','primary_riskcap'] or (label=='primary_riskcap' and segment!='validation'):continue
    eq=x['equity'];ts=x['times'];att=attribute(eq,ts,x['orders'],bars,factor);assert abs(att['exposure_average']-m['average_exposure'])<1e-9
    for a,b in [('fee','fees'),('spread','spread'),('slippage','slippage')]:assert abs(att['costs']['all'][a]-m[b])<1e-9
    weekly=period_table(eq,ts,'week');monthly=period_table(eq,ts,'month');quarters=period_table(eq,ts,'quarter');daily_return=np.diff(eq)/np.array(eq[:-1]);pnl=np.diff(eq)
    info={'metrics':selected,'realized_daily_vol_annualized_sqrt365':float(np.std(daily_return,ddof=1)*math.sqrt(365)),'mean_daily_return':float(np.mean(daily_return)),'median_daily_return':float(np.median(daily_return)),'best_daily_return':float(np.max(daily_return)),'worst_daily_return':float(np.min(daily_return)),'positive_month_count':sum(z['return']>0 for z in monthly),'negative_month_count':sum(z['return']<0 for z in monthly),'mean_bottom_empirical5pct_daily_returns_descriptive_not_future_VaR':float(np.mean(np.sort(daily_return)[:max(1,math.ceil(len(daily_return)*.05))])),'net_attribution_BTC_ETH':att['asset_net_pnl'],'gross_raw_marked_attribution_BTC_ETH':att['asset_raw_marked_pnl'],'actual_costs_BTC_ETH':att['costs'],'cash_fraction_mean':att['cash_fraction_average'],'fully_cash_days':att['days_fully_cash'],'monthly':monthly,'quarterly':quarters,'distribution_daily_returns':distribution(daily_return),'distribution_weekly_returns':distribution([z['return'] for z in weekly]),'distribution_monthly_returns':distribution([z['return'] for z in monthly]),'best_days':[{'date':iso(ts[i+1]-1)[:10],'net_pnl':float(pnl[i]),'return':float(daily_return[i])} for i in np.argsort(pnl)[-5:][::-1]],'worst_days':[{'date':iso(ts[i+1]-1)[:10],'net_pnl':float(pnl[i]),'return':float(daily_return[i])} for i in np.argsort(pnl)[:5]],'best_month':max(monthly,key=lambda z:z['return']),'worst_month':min(monthly,key=lambda z:z['return']),'net_without_best_day_fixed_ledger_diagnostic':float(sum(pnl)-max(pnl)),'net_without_best5_days_fixed_ledger_diagnostic':float(sum(pnl)-sum(sorted(pnl,reverse=True)[:5])),'daily_drawdown_detail':drawdown_detail(eq,ts),'attribution_definition':att['attribution_definition']}
    results[segment][scenario][label]=info
    if segment=='validation':details2023[scenario+'_'+label]={'attribution':att,'original_events':x['events'],'original_orders':x['orders']}
  if segment=='holdout':results[segment]['original_base_paired_inference']=load(OLD/'results-holdout/results.json')['results']['holdout']['B']['base']['inference']
 # Dated 2023 signal diagnosis, using frozen target events and closed cached bars only.
 base=details2023['base_primary_strategy'];passive=details2023['base_primary_riskcap'];benchmark={e['at']:e for e in passive['original_events']};weekly=[]
 for event in base['original_events']:
  t=event['at'];end=event['metadata']['feature_end_max'];assert t-end==DAY;latest=end-DAY;mom=[];vol=[];elig=[]
  for k in range(2):
   closes=np.array([bars[k][latest-j*DAY]['close'] for j in range(30,-1,-1)]);returns=np.diff(np.log(closes));vol.append(float(np.std(returns,ddof=1)*math.sqrt(365)));mom.append(bars[k][latest]['close']/bars[k][latest-90*DAY]['close']-1);volumes=[bars[k][latest-j*DAY]['quote_volume'] for j in range(30)];elig.append(float(np.median(volumes))>=1e7)
  expected=[.5*int(mom[k]>0)*min(1,.2/vol[k]) if elig[k] and vol[k]>0 else 0 for k in range(2)];assert np.allclose(event['weights_requested'],expected,atol=1e-12,rtol=0)
  weekly.append({'execution_utc':iso(t),'feature_cutoff_utc':iso(end),'last_daily_bar_start_utc':iso(latest),'momentum90_BTC_ETH':mom,'annual_vol30_BTC_ETH':vol,'eligible_BTC_ETH':elig,'target_weights_BTC_ETH':event['weights_requested'],'riskcap_without_trend_weights':benchmark[t]['weights_requested']})
 monthly_comparison=[]
 for c,p in zip(results['validation']['base']['primary_strategy']['monthly'],results['validation']['base']['primary_riskcap']['monthly']):monthly_comparison.append({'period':c['period'],'B_net_pnl':c['net_pnl'],'passive_net_pnl':p['net_pnl'],'pathwise_difference_not_causal_effect':c['net_pnl']-p['net_pnl'],'B_return':c['return'],'passive_return':p['return']})
 asset_months={}
 for label,x in [('B',base),('riskcap',passive)]:
  month=defaultdict(lambda:np.zeros(2))
  for d in x['attribution']['daily']:month[d['date'][:7]]+=np.array(d['asset_net_pnl'])
  asset_months[label]={k:v.tolist() for k,v in month.items()}
 diagnosis={'weekly_causal_targets':weekly,'monthly_comparison':monthly_comparison,'asset_monthly_attribution':asset_months,'B_costs_by_scenario':{s:results['validation'][s]['primary_strategy']['actual_costs_BTC_ETH'] for s in ['base','adverse','severe']},'definitions':'Observed fixed-ledger accounting, not an alternative strategy or causal estimated treatment effect. Both sleeves start cash and use Monday schedule/full-day lag. Weekly EW without cap is NOT static initial BTCETH buy-and-hold.','first_nonzero_target_by_asset':{asset:next((w['execution_utc'] for w in weekly if w['target_weights_BTC_ETH'][k]>0),None) for k,asset in enumerate(['BTC','ETH'])},'zero_target_weeks_by_asset':{asset:sum(w['target_weights_BTC_ETH'][k]==0 for w in weekly) for k,asset in enumerate(['BTC','ETH'])},'weekly_decisions':len(weekly)}
 save(OUT/'diagnosis-2023.json',diagnosis);save(OUT/'attribution-2023.json',details2023)
 save(OUT/'findings.json',{'scope':'Frozen B2020–Nov2024 ledgers only; zero new strategy/backtest variants, no2025/26 financial test, no network.','provenance':provenance(),'results':results,'comparators':'primary_uncapped = weekly50/50 EW, NOT static BTCETH B&H. Individual BTC/ETH initial buyhold are frozen existing arms. No separate static BTCETH B&H arm exists; none invented in this followup. Matched uses requested target exposure not exactly realized exposure after costs.','interpretation':'2024positive/risk-adjusted point estimate remains unpromoted: both original family3-adjusted Sharpe-difference lower bounds negative; no alpha/seed/gate revision when focusing on B.','original_inference_not_retested':True,'original_sources_results_179_unchanged':True})
 with (OUT/'metrics.csv').open('w',newline='') as fcsv:w=csv.DictWriter(fcsv,fieldnames=list(compact[0]));w.writeheader();w.writerows(compact)
 for p,h in f['inputs'].items():assert sha(ROOT/p)==h,p
 assert all(sha(ROOT/p)==h for p,h in f['protected'].items());print('PASS:72existingBarm/cost/segment metrics; exactNAV/asset/cost/exposure reconciliation; causal2023targets; source/results/179unchanged; no2025/26test')
 print('2023firsttarget',diagnosis['first_nonzero_target_by_asset'],'zeroTargetWeeks',diagnosis['zero_target_weeks_by_asset']);print('2023netBTCETH',results['validation']['base']['primary_strategy']['net_attribution_BTC_ETH']);print('2023costs',results['validation']['base']['primary_strategy']['actual_costs_BTC_ETH']['all'])
if __name__=='__main__':
 def denied(*a,**k):raise RuntimeError('Offline B followup: network forbidden')
 socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
 freeze() if sys.argv[1:]==['freeze'] else run()
