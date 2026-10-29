from datetime import datetime,timezone
import math
import numpy as np
import pytest
from engine import Bar, Costs, Portfolio, daily_features, target_a, target_b, impulse, schedule_impulses, summarize, paired_bootstrap
from data import parse_row
DAY=86400

def history(n=120,assets=2):
 close=np.tile(np.exp(np.arange(n)*.001)[:,None],(1,assets));volume=np.full_like(close,20e6)
 return close,volume,np.ones_like(close,dtype=bool)

def test_missing_modules_red_marker():assert Costs().fee==.001

def test_timestamp_units_and_inclusive_close():
 for year,scale in [(2024,1000),(2025,1000000)]:
  t=int(datetime(year,1,1,tzinfo=timezone.utc).timestamp());r=[str(t*scale),'1','2','.5','1','10',str((t+3600)*scale-1),'15','1','1','1','0']
  b=parse_row(r,year,3600,'BTCUSDT');assert b.start==t and b.end==t+3600
  r[6]=str((t+3600)*scale)
  with pytest.raises(ValueError):parse_row(r,year,3600,'BTCUSDT')

def test_listing_partial_day_excluded():
 t=1574899200;r=[str(t*1000),'1','2','.5','1','10',str((t+DAY)*1000-1),'15','1','1','1','0']
 assert not parse_row(r,2019,DAY,'BCHUSDT').full

def test_daily_features_full_day_availability():
 c,v,f=history();x=daily_features(c,v,f,110,14)
 c[109:]=1e30;y=daily_features(c,v,f,110,14)
 assert np.array_equal(x['momentum'],y['momentum']);assert x['latest_index']==108

def test_no_future_liquidity_eligibility():
 c,v,f=history();v[79:109,1]=1e6;x=daily_features(c,v,f,110,14)
 v[109:,1]=1e15;assert not x['eligible'][1];assert not daily_features(c,v,f,110,14)['eligible'][1]

def test_missing_asset_does_not_become_eligible():
 c,v,f=history();f[100,1]=False;x=daily_features(c,v,f,110,14);assert not x['eligible'][1]

def test_a_ties_top_two_and_cash_negative():
 c,v,f=history(120,3);x=daily_features(c,v,f,110,14);w=target_a(x,['BTC','ETH','XRP']);assert w[0]==.5 and w[1]==.5 and w[2]==0
 x['momentum'][:]=-1;assert sum(target_a(x,['BTC','ETH','XRP']))==0

def test_b_no_leverage_and_negative_cash():
 c,v,f=history();x=daily_features(c,v,f,110,90);w=target_b(x);assert sum(w)<=1
 x['momentum'][0]=-1;assert target_b(x)[0]==0

def test_zero_vol_is_cash():
 c,v,f=history();c[:]=1;x=daily_features(c,v,f,110,14);assert sum(target_a(x,['BTC','ETH']))==0;assert sum(target_b(x))==0

def test_cash_fees_conserve_and_nonnegative():
 p=Portfolio(2,Costs());p.rebalance(np.array([100.,200.]),np.array([.5,.5]),0)
 assert p.cash>=-1e-9;assert p.cash+np.dot(p.qty,[100,200])<1000
 p.rebalance(np.array([100.,200.]),np.zeros(2),1)
 expected=1000*((1-.0001)*(1-.0001)*(1-.001))/((1+.0001)*(1+.0001)*(1+.001))
 assert abs(p.cash-expected)<1e-8;assert np.all(p.qty==0)

def test_sell_before_buy():
 p=Portfolio(2,Costs());p.rebalance(np.array([100.,100.]),np.array([1.,0.]),0);p.rebalance(np.array([100.,100.]),np.array([0.,1.]),1)
 assert [t['side'] for t in p.orders[-2:]]==['SELL','BUY'];assert p.cash>=-1e-9

def test_missing_held_price_blocks_not_ffill():
 p=Portfolio(2,Costs());p.rebalance(np.array([100.,100.]),np.array([1.,0.]),0)
 with pytest.raises(ValueError,match='untradable'):p.mark(np.array([float('nan'),100.]))

def test_impulse_prior_window_excludes_current():
 r=np.array([(-1)**i*.001 for i in range(170)]+[.02]);assert impulse(r,170)>1
 r[170]=100;assert impulse(r,170)>1
 assert impulse(np.zeros(200),170) is None

def test_full_intervening_hour_delay_and_end_limit():
 r=np.array([(-1)**i*.001 for i in range(200)]);r[170]=.02
 s=schedule_impulses(r,1,200);assert s[172]['signal_index']==170 and s[172]['exit_index']==173
 assert 171 not in s
 assert all(k+1<173 for k in schedule_impulses(r,1,173))

def test_separate_close_reopen_pays_both():
 p=Portfolio(1,Costs());p.rebalance(np.array([100.]),np.ones(1),0);p.rebalance(np.array([100.]),np.zeros(1),1);p.rebalance(np.array([100.]),np.ones(1),1)
 assert [t['side'] for t in p.orders]==['BUY','SELL','BUY'];assert sum(t['fee'] for t in p.orders)>2

def test_drawdown_includes_initial_equity_and_no_false_pf():
 m=summarize([1000,900,990],[0,DAY,2*DAY],[],[0,0,0]);assert m['max_drawdown']==pytest.approx(.1);assert m['daily_pnl_profit_factor']==pytest.approx(.9)

def test_bootstrap_deterministic_and_null():
 a=np.array([.01,-.01]*40);x=paired_bootstrap(a,a,'sharpe_difference',replicates=100);assert x==paired_bootstrap(a,a,'sharpe_difference',replicates=100)
 assert all(b['lower_family3']==0 for b in x['blocks'].values())

def test_family_specific_quality_failure_does_not_block_b_c():
 from runner import family_errors
 q={'errors':{'1d/EOSUSDT':[{'error':'missing'}]}}
 assert family_errors(q,'A') and not family_errors(q,'B') and not family_errors(q,'C')

def test_research_runner_financial_release_gate(tmp_path,monkeypatch):
 import runner
 monkeypatch.setattr(runner,'ROOT',tmp_path);monkeypatch.setattr(runner,'validate_sources',lambda:None)
 with pytest.raises(ValueError,match='root release'):runner.run('development-validation')

def test_holdout_loader_release_gate(tmp_path,monkeypatch):
 import data,json
 monkeypatch.setattr(data,'ROOT',tmp_path);(tmp_path/'acquisition-development-validation.json').write_text(json.dumps({'archives':[]}))
 with pytest.raises(ValueError,match='holdout locked'):data.load_manifest('holdout')

def test_a_portfolio_covariance_cap_not_individual_average():
 from engine import cap
 r=np.array([[.1,.1],[-.1,-.1]]*15);w=cap(np.array([.5,.5]),r)
 assert sum(w)==pytest.approx(.2/(np.std(r[:,0],ddof=1)*np.sqrt(365)))

def test_synthetic_runner_segment_end_and_reentry_costs(monkeypatch):
 import runner
 runner.SEGMENTS['synthetic']=('2020-01-01','2020-01-03');d={}
 daystart=runner.timestamp('2019-09-01')
 for symbol in runner.SYMBOLS:d[('1d',symbol)]=[Bar(daystart+i*DAY,daystart+(i+1)*DAY,100,101,99,100+i*.01,1e6,2e7) for i in range(125)]
 hs=runner.timestamp('2019-12-01');n=(runner.timestamp('2020-01-03')-hs)//3600
 rr=np.array([(-1)**i*.001 for i in range(n)])
 entry=(runner.timestamp('2020-01-01')-hs)//3600
 rr[entry-2]=.03;rr[entry-1]=.04
 closes=100*np.exp(np.cumsum(rr))
 for symbol in runner.SYMBOLS[:2]:d[('1h',symbol)]=[Bar(hs+i*3600,hs+(i+1)*3600,100,200,50,float(closes[i]),1e6,2e7) for i in range(n)]
 result=runner.simulate(d,'synthetic','C','primary',Costs())
 assert result['metrics']['status']=='COMPLETE';orders=result['orders'];assert all(x['at']<=runner.timestamp('2020-01-03') for x in orders)
 same=[x['side'] for x in orders if x['at']==runner.timestamp('2020-01-01')+3600]
 assert same==['SELL','BUY'];assert all(x['metadata'].get('source_event_age_seconds',3600)>=3600 for x in orders)
 assert result['metrics']['capital_final']==pytest.approx(result['metrics']['cash_final'])

def test_incomplete_btc_comparator_does_not_crash_valid_candidate():
 from runner import add_market_diagnostic
 main={'status':'COMPLETE','daily_returns':[.01,-.005]};add_market_diagnostic(main,{'status':'INCOMPLETE_NO_PROMOTION'})
 assert main['status']=='COMPLETE';assert main['market_beta_status']=='UNAVAILABLE_INCOMPLETE_BTC_COMPARATOR'
