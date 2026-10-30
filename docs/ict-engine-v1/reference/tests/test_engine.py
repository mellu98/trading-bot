import unittest,json,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_data import Bar,atr,validate_append
from market_structure import confirmed_pivots,Pivot
from liquidity_detector import sweep
from mss_detector import mss
from fvg_detector import fvg
from position_sizing import size
from news_filter import Event,blocked
from risk_manager import gate,RiskState
from ict_strategy import Engine,Context
from execution_adapter import SimulationAdapter
C=json.loads(Path(__file__).resolve().parents[1].joinpath('strategy_config.yaml').read_text())
T=datetime(2026,1,5,13,tzinfo=timezone.utc)
def b(i,o,h,l,c):return Bar(T+timedelta(minutes=5*i),o,h,l,c)
def sig():return {'signal_id':'x','known_at':T.isoformat(),'expires_at':(T+timedelta(hours=1)).isoformat(),'direction':1,'entry':100,'stop':98,'target':104,'qty':1}
class Tests(unittest.TestCase):
 def test_invalid_ohlc(self):
  with self.assertRaises(ValueError):b(0,10,9,8,9)
 def test_nan(self):
  with self.assertRaises(ValueError):b(0,10,float('nan'),8,9)
 def test_duplicate(self):
  x=b(0,10,11,9,10)
  with self.assertRaises(ValueError):validate_append([x],x,300)
 def test_atr_lag(self):self.assertEqual(atr([b(i,10,11,9,10) for i in range(4)],3),2)
 def test_pivot_delay(self):
  bars=[b(i,10,h,9,10) for i,h in enumerate([11,12,15,12,11])]
  self.assertEqual(confirmed_pivots(bars[:4],2,2),[])
  self.assertEqual(confirmed_pivots(bars,2,2)[0].known_at,4)
 def test_tie_rejected(self):self.assertEqual(confirmed_pivots([b(i,10,12,9,10) for i in range(5)],2,2),[])
 def test_sweep(self):self.assertTrue(sweep(b(0,100,101,99.8,100.1),Pivot(0,0,'LOW',100),1,1,C))
 def test_sweep_no_recovery(self):self.assertFalse(sweep(b(0,100,101,99.8,99.9),Pivot(0,0,'LOW',100),1,1,C))
 def test_mss_requires_displacement(self):self.assertFalse(mss(b(0,100.1,102,99,100.2),100,1,1,C))
 def test_mss_long(self):self.assertTrue(mss(b(0,100,102.1,99.9,102),101,1,1,C))
 def test_fvg(self):self.assertEqual(fvg([b(0,99,100,98,99),b(1,99,102,99,102),b(2,101,102,100.5,101)],1,1,C),(100,100.5))
 def test_short_fvg(self):self.assertEqual(fvg([b(0,102,103,101,102),b(1,102,102,99,99),b(2,100,100.5,99,100)],-1,1,C),(100.5,101))
 def test_size_both_accounts(self):
  for e in (500,5000):
   cfg={**C,'available_cash_eur':e,'risk_fraction':.01}
   s=size(e,100,98,105,1,cfg);self.assertGreater(s['qty'],0);self.assertLessEqual(s['risk_eur'],e*.01)
 def test_minimum_no_roundup(self):self.assertEqual(size(500,100,98,105,1,{**C,'min_qty':10})['qty'],0)
 def test_no_short_spot(self):self.assertEqual(size(500,100,102,95,-1,C)['reason'],'SKIP_SHORT_UNSUPPORTED')
 def test_fixed_fees(self):self.assertEqual(size(500,100,98,105,1,{**C,'fixed_fee_eur':10})['qty'],0)
 def test_calendar_stale(self):self.assertEqual(blocked(T,[],None,['USD'],C),'SKIP_CALENDAR_STALE')
 def test_calendar_point_in_time(self):
  e=Event(T,T+timedelta(seconds=1),('USD',),3,'CPI')
  self.assertIsNone(blocked(T,[e],T,['USD'],C))
 def test_news_boundary(self):
  e=Event(T,T-timedelta(days=1),('USD',),3,'CPI')
  self.assertEqual(blocked(T+timedelta(minutes=30),[e],T,['USD'],C),'SKIP_NEWS_BLACKOUT')
 def test_risk(self):self.assertEqual(gate(RiskState(day_return=-.02),C),'SKIP_DAILY_LOSS')
 def test_live_forbidden(self):
  with self.assertRaises(ValueError):Engine({**C,'mode':'live'})
 def test_idempotence(self):
  a=SimulationAdapter(C);self.assertIs(a.create(sig()),a.create(sig()));self.assertEqual(len(a.orders),1)
 def test_id_conflict(self):
  a=SimulationAdapter(C);a.create(sig())
  with self.assertRaises(ValueError):a.create({**sig(),'qty':2})
 def test_no_same_bar_fill(self):
  a=SimulationAdapter(C);a.create(sig());a.on_bar(b(0,100,105,97,100),.02);self.assertEqual(a.orders['x']['status'],'PENDING')
 def test_stop_first(self):
  a=SimulationAdapter(C);a.create(sig());out=a.on_bar(b(1,100,105,97,101),.02);self.assertEqual(out[0]['reason'],'STOP')
 def test_gap_stop(self):
  a=SimulationAdapter(C);a.create(sig());a.on_bar(b(1,101,102,99,101),.02)
  out=a.on_bar(b(2,95,96,94,95),.02);self.assertLess(out[0]['exit_price'],98)
 def test_no_target_on_entry_bar(self):
  a=SimulationAdapter(C);a.create(sig());self.assertEqual(a.on_bar(b(1,100,105,99,104),.02),[])
 def test_cancel(self):
  a=SimulationAdapter(C);a.create(sig());a.cancel('x');self.assertEqual(a.on_bar(b(1,100,105,97,100),.02),[])
 def test_expiry(self):
  a=SimulationAdapter(C);a.create(sig());a.on_bar(b(12,100,105,99,100),.02);self.assertEqual(a.orders['x']['status'],'EXPIRED')
 def test_dst(self):
  from zoneinfo import ZoneInfo
  self.assertEqual(datetime(2026,1,5,13,tzinfo=timezone.utc).astimezone(ZoneInfo('America/New_York')).hour,8)
  self.assertEqual(datetime(2026,7,6,12,tzinfo=timezone.utc).astimezone(ZoneInfo('America/New_York')).hour,8)
 def test_prefix_invariance(self):
  bars=[b(i,100,101+(i%4)*.1,99,100) for i in range(40)]
  def run(xs):
   e=Engine(C)
   for bar in xs:e.on_bar(bar,Context(500,.01,bar.ts,bar.ts))
   return e.log
  self.assertEqual(run(bars[:30]),run(bars)[:30])
 def test_end_to_end_long_and_mirror_short(self):
  xs=[(101,102,100,101),(102,106,101,102),(102,103,100,101),(100,101,99,100),(100,101.2,99.8,100.5),(100.5,100.8,99.8,100),(99.8,100,98.8,99.5),(99.5,102.2,99.4,102),(101.5,102,100.7,101.5)]
  cfg={**C,'atr_period':3,'pivot_left':1,'pivot_right':1,'fee_rate':0,'slippage_price':0,'body_atr_min':.5,'body_ratio_min':.6,'fvg_min_atr':.05,'sweep_max_atr':1,'min_notional':0,'short_allowed':True}
  for d in (1,-1):
   e=Engine(cfg);signals=[]
   for i,(o,h,l,c) in enumerate(xs):
    bar=b(i,o,h,l,c) if d==1 else b(i,200-o,200-l,200-h,200-c)
    out=e.on_bar(bar,Context(500,.01,bar.ts,bar.ts))
    if out:signals.append(out)
   self.assertEqual(len(signals),1);self.assertEqual(signals[0]['direction'],d)
   self.assertLessEqual(signals[0]['risk_eur'],1.25)
   a=SimulationAdapter(cfg);a.create(signals[0])
   entry=signals[0]['entry'];stop=signals[0]['stop'];target=signals[0]['target']
   # Following bar trades through entry but not stop. Then target is crossed.
   if d==1:
    a.on_bar(b(9,entry+.2,entry+.3,entry-.1,entry+.2),.01)
    out=a.on_bar(b(10,target-.2,target+.1,entry+.1,target),.01)
   else:
    a.on_bar(b(9,entry-.2,entry+.1,entry-.3,entry-.2),.01)
    out=a.on_bar(b(10,target+.2,entry-.1,target-.1,target),.01)
   self.assertEqual(out[0]['reason'],'TARGET');self.assertGreater(out[0]['net_eur'],0)
 def test_nonfinite_context(self):
  e=Engine(C)
  with self.assertRaises(ValueError):e.on_bar(b(0,100,101,99,100),Context(float('nan'),.01,T,T))
if __name__=='__main__':unittest.main()
