import numpy as np
import pytest
from signals import h1_features,h2_features,target,h1_schedule,h2_feature_index,paired_bootstrap
from data import parse_row,validate_hour_window
from runner import execute,screen,run
from datetime import datetime,timezone
DAY=86400

def fixture(n=80,k=2):
 r=np.array([.001 if i%2 else -.002 for i in range(n)]);c=np.tile((100*np.exp(np.cumsum(r)))[:,None],(1,k));q=np.full((n,k),2e7);full=np.ones((n,k),bool);return c,q,full

def test_h1_negative_shock_low_volume_and_excluding_current_baselines():
 c,q,f=fixture();j=60;c[j,:]=c[j-1,:]*np.exp(-.1);q[j,:]=1e7
 x=h1_features(c,q,f,j);r=np.diff(np.log(c[:,0]));prior=r[j-31:j-1]
 assert x['z'][0]==pytest.approx((-.1-np.mean(prior))/np.std(prior,ddof=1));assert x['L'][0]==pytest.approx(np.log(.5));assert np.all(x['trigger'])

def test_h1_positive_or_high_volume_not_trigger():
 c,q,f=fixture();j=60;c[j]=c[j-1]*np.exp(-.1);q[j]=4e7;assert not np.any(h1_features(c,q,f,j)['trigger'])
 q[j]=1e7;c[j]=c[j-1]*np.exp(.1);assert not np.any(h1_features(c,q,f,j)['trigger'])

def test_risk_includes_current_feature_return():
 c,q,f=fixture();j=60;c[j]=c[j-1]*np.exp(-.1);q[j]=1e7;x=h1_features(c,q,f,j)
 assert x['risk_returns'][-1,0]==pytest.approx(-.1);w=target(x,['BTC','ETH'],'H1');vol=np.std(x['risk_returns']@np.array([.5,.5]),ddof=1)*np.sqrt(365);assert np.sum(w)==pytest.approx(min(1,.2/vol))

def test_h2_lowest_negative_ties_lexical_and_single_cash():
 c,q,f=fixture(k=4);j=60;q[j]=[1e7,1e7,1e7,3e7];x=h2_features(c,q,f,j);w=target(x,['BBB','AAA','CCC','DDD'],'H2');assert w[0]>0 and w[1]>0 and w[2]==0 and w[3]==0
 q[j]=[2e7,1e7,2e7,2e7];x=h2_features(c,q,f,j);w=target(x,['BBB','AAA','CCC','DDD'],'H2');assert sum(w)<=.5 and w[1]>0

def test_future_price_and_volume_do_not_change_prior_features():
 c,q,f=fixture();j=60;x=h1_features(c,q,f,j);y=h2_features(c,q,f,j);c[j+1:]=1e30;q[j+1:]=1e40
 assert np.allclose(x['L'],h1_features(c,q,f,j)['L']);assert np.allclose(x['z'],h1_features(c,q,f,j)['z']);assert np.allclose(y['risk_returns'],h2_features(c,q,f,j)['risk_returns'])

def test_full_history_and_past_liquidity_fail_closed():
 c,q,f=fixture();f[55,0]=False;q[31:61,1]=1e6
 assert not np.any(h2_features(c,q,f,60)['eligible']);assert np.sum(target(h2_features(c,q,f,60),['BTC','ETH'],'H2'))==0

def test_same_boundary_forbidden_and_neighbor_lag():
 assert h1_schedule(86400+3600,1) and not h1_schedule(86400,1)
 assert h1_schedule(86400+7200,2);assert h2_feature_index(60,1)==58;assert h2_feature_index(60,2)==57

def test_zero_vol_cash_and_no_infinite_statistics():
 c,q,f=fixture();c[:]=1;q[60]=1e7;x=h2_features(c,q,f,60);assert sum(target(x,['BTC','ETH'],'H2'))==0
 b=paired_bootstrap(np.zeros(200),np.ones(200)*.001,'sharpe_difference',100);assert all(z['lower_family2'] is None for z in b['blocks'].values())

def test_cash_costs_netdelta_no_forced_roundtrip():
 from reuse import Portfolio,Costs
 p=Portfolio(2,Costs());execute(p,np.array([100.,100.]),np.array([.5,.5]),0,{})
 n=len(p.orders);execute(p,np.array([100.,100.]),np.array([.5,.5]),DAY,{});assert len(p.orders)==n
 assert p.cash>=0 and p.mark(np.array([100.,100.]),True)<1000
 execute(p,np.array([100.,100.]),np.zeros(2),2*DAY,{});assert np.all(p.qty==0)


def test_sell_before_buy_and_missing_held_rejected():
 from reuse import Portfolio,Costs
 p=Portfolio(2,Costs());execute(p,np.array([100.,100.]),np.array([1.,0.]),0,{})
 with pytest.raises(ValueError,match='untradable'):execute(p,np.array([np.nan,100]),np.zeros(2),DAY,{})
 execute(p,np.array([100.,100.]),np.array([0.,1.]),DAY,{});assert [x['side'] for x in p.orders[-2:]]==['SELL','BUY']

def test_exact_ms_us_and_activity_bounds():
 for y,mul in [(2024,1000),(2025,1000000)]:
  t=int(datetime(y,1,1,tzinfo=timezone.utc).timestamp());r=[str(t*mul),'1','2','.5','1','10',str((t+3600)*mul-1),'20','2','4','8','0'];assert parse_row(r,y,3600,'BTCUSDT')['start']==t
  r[10]='21'
  with pytest.raises(ValueError):parse_row(r,y,3600,'BTCUSDT')

def test_period_local_quality_not_poisoned_by_earlier_gap():
 rows={0:{'end':3599},3600:{'end':7200},7200:{'end':10800}}
 assert validate_hour_window(rows,3600,10800)==[];assert validate_hour_window(rows,0,10800)

def test_bootstrap_family2_same_indices_seed():
 a=np.array([.01,-.01]*100);x=paired_bootstrap(a,a,'mean_excess',100)
 assert all(z['lower_family2']==0 for z in x['blocks'].values());assert x['alpha']==.025 and x['seed']==20261028

def test_release_required_before_actual_data_load(tmp_path,monkeypatch):
 import runner
 monkeypatch.setattr(runner,'OUT',tmp_path);monkeypatch.setattr(runner,'verify',lambda:None)
 with pytest.raises(ValueError,match='release'):runner.run()

def test_auxiliary_tradecount_or_taker_fields_never_select_h2():
 c,q,f=fixture(k=3);q[60]=1e7;x=h2_features(c,q,f,60);w=target(x,['CCC','AAA','BBB'],'H2');x['number_trades']=np.array([1,1e9,0]);x['taker_buy_share']=np.array([1,0,.5]);assert np.array_equal(w,target(x,['CCC','AAA','BBB'],'H2'));assert w[0]==0 and w[1]>0 and w[2]>0

def test_h1_synthetic_full_loop_hour_lag_and_terminal_cost():
 import runner
 from reuse import Costs
 from data import timestamp
 runner.SEGMENTS['H1']['synthetic']=('2022-01-01','2022-01-03');start=timestamp('2022-01-01');cache={};lo=start-110*DAY
 c,q,f=fixture(112,2);c[109]=c[108]*np.exp(-.1);q[109]=1e7;c[110]=c[109]*np.exp(-.1);q[110]=1e7
 for k,s in enumerate(['BTCUSDT','ETHUSDT']):
  cache[('1d',s)]={lo+i*DAY:{'start':lo+i*DAY,'end':lo+(i+1)*DAY,'open':100.,'close':float(c[i,k]),'quote':float(q[i,k]),'full':True} for i in range(112)}
  cache[('1h',s)]={t:{'start':t,'end':t+3600,'open':100.,'close':100.} for t in range(start,start+2*DAY,3600)}
 x=runner.simulate(cache,'H1','synthetic','primary',Costs(),'strategy');assert x['metrics']['status']=='COMPLETE_EXPLORATORY'
 assert x['orders'][0]['at']==start+3600;assert x['orders'][-1]['at']==start+2*DAY;assert x['orders'][-1]['metadata']['reason'].startswith('FINITE_SEGMENT')
 assert all(e['metadata']['availability_lag_seconds']==3600 for e in x['events']);assert x['equity'][-1]<1000
