"""Real owned-CME technical regressions; no independent economic validation."""
from dataclasses import replace
from datetime import datetime,timedelta
import math
import pytest
from mnq_local.replay import ReplaySession,ReplayOptions,load_session,FrozenSource
from mnq_timestral.schema import UTC,Request
from mnq_timestral.data import features


def test_configured_simulation_exit_costs_are_reserved_before_risk_decision(tmp_path):
 s=ReplaySession(tmp_path,replace(ReplayOptions(),fee_per_side=2.,slippage_ticks=4))
 try:
  b=s.bars[40];s.now=b.end;s.runtime.last_data=b.end
  assert s.runtime.submit_candidate(b.symbol,1,b.close,b.end,'reserve-fixture')
  entry=next(o for o in s.broker.orders.values() if o['role']=='entry')
  s.broker.fill(entry['id'],1,b.close,'reserve-fill',s.now);s.runtime.reconcile(s.broker.snapshot())
  p=s.runtime.state['positions'][b.symbol];p['mark']=p['average']
  from mnq_timestral.evaluation import POINT_VALUE
  assert s.runtime._mark_risk().unrealized==-(2.+4*.25*POINT_VALUE[b.symbol])
 finally:s.close()


@pytest.mark.parametrize('side',[-1,1])
def test_gap_stop_cannot_fill_at_a_better_price_than_the_observed_open(tmp_path,side):
 s=ReplaySession(tmp_path)
 try:
  b=s.bars[40];s.now=b.end;s.runtime.last_data=b.end
  assert s.runtime.submit_candidate(b.symbol,side,b.close,b.end,'gap-fixture')
  entry=next(o for o in s.broker.orders.values() if o['role']=='entry')
  s.broker.fill(entry['id'],1,b.close,'gap-entry',s.now);s.runtime.reconcile(s.broker.snapshot())
  stop=next(o for o in s.broker.orders.values() if o['role']=='stop')
  gap_open=stop['stop']-side*5.;end=b.end+timedelta(minutes=1)
  gap=replace(b,start=b.end,end=end,available_at=end,open=gap_open,high=gap_open+.25,low=gap_open-.25,close=gap_open)
  s.now=end;s.broker.match(gap);s.runtime.reconcile(s.broker.snapshot())
  fill=next(e for e in s.runtime.state['executions'].values() if e['order_id']==stop['id'])
  assert fill['price']==gap_open-side*.25
  assert s.runtime.state['positions'][b.symbol]['quantity']==0
 finally:s.close()


def test_high_cost_loss_limit_stops_while_the_old_fixed_reserve_would_not(tmp_path):
 s=ReplaySession(tmp_path,replace(ReplayOptions(),fee_per_side=2.,slippage_ticks=4,daily_max_loss=5.))
 try:
  b=s.bars[40];s.now=b.end;s.runtime.last_data=b.end
  assert s.runtime.submit_candidate(b.symbol,1,b.close,b.end,'cost-limit')
  entry=next(o for o in s.broker.orders.values() if o['role']=='entry')
  s.broker.fill(entry['id'],1,b.close,'cost-limit-entry',s.now);s.runtime.reconcile(s.broker.snapshot())
  s.runtime.last_data_by_symbol[b.symbol]=s.now
  s.runtime.watchdog();s.runtime.reconcile(s.broker.snapshot())
  assert s.runtime.state['halt']=='daily_max_loss'
  assert len([o for o in s.broker.orders.values() if o['role']=='flatten'])==1
 finally:s.close()


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1,True])
def test_invalid_broker_exit_reserve_cannot_be_used_for_risk(tmp_path,bad):
 s=ReplaySession(tmp_path)
 try:
  s.runtime.state['positions']['MES']={'quantity':1,'average':100.,'mark':100.}
  s.broker.liquidation_cost_per_contract=lambda _:bad
  with pytest.raises(ValueError):s.runtime._mark_risk()
 finally:s.close()


def test_broker_estimate_can_never_lower_the_original_conservative_risk_floor(tmp_path):
 s=ReplaySession(tmp_path)
 try:
  s.runtime.state['positions']['MES']={'quantity':1,'average':100.,'mark':100.}
  s.broker.liquidation_cost_per_contract=lambda _:0
  assert s.runtime._mark_risk().unrealized==-(.61+.25*5)
 finally:s.close()


@pytest.mark.parametrize('cut',[20,80,200])
def test_future_price_and_volume_corruption_cannot_change_past_features(cut):
 import numpy as np
 bars,_=load_session('2026-10-19');bb=tuple(b for b in bars if b.symbol=='MNQ')
 changed=bb[:cut]+tuple(replace(b,open=b.open*10,high=b.high*10,low=b.low*10,close=b.close*10,volume=b.volume*100) for b in bb[cut:])
 original=features(Request(bb,bb[-1].end));mutated=features(Request(changed,changed[-1].end))
 for name in ('vwap','z','volatility'):
  np.testing.assert_allclose(getattr(original,name)[:cut],getattr(mutated,name)[:cut],rtol=0,atol=0,equal_nan=True)
 assert mutated.vwap[-1]!=original.vwap[-1]


@pytest.mark.parametrize('kind',['vwap_v1','orb_v2','sweep_mss_v2'])
def test_each_existing_signal_source_refuses_future_context(kind):
 from mnq_paper.signals import VwapV1Source
 bars,_=load_session('2026-10-19');bb=tuple(b for b in bars if b.symbol=='MNQ')
 source=VwapV1Source() if kind=='vwap_v1' else FrozenSource(kind)
 side,state=source.evaluate(bb[:80],bb[79].end,{})
 assert side in (-1,0,1)
 with pytest.raises(ValueError):source.evaluate(bb[:81],bb[79].end,{})


def test_forged_news_metadata_cannot_unlock_the_operational_strict_mode(tmp_path):
 s=ReplaySession(tmp_path,replace(ReplayOptions(),strict=True))
 try:
  b=s.bars[40];s.now=b.end;s.runtime.last_data=b.end
  s.runtime.state['news']={'status':'verified_scoped_official_schedule','certified':True,'blocks':[]}
  assert not s.runtime.submit_candidate(b.symbol,1,b.close,b.end,'uncertified-calendar')
  assert not s.broker.orders and s.runtime.state['decisions'][-1]['reason']=='strict_news_and_strategy_not_certified'
 finally:s.close()


@pytest.mark.parametrize('day',['2026-10-19','2026-11-02'])
@pytest.mark.parametrize('hour,minute,allowed',[(9,44,False),(9,45,True),(15,29,True),(15,30,False)])
def test_entry_window_boundaries_follow_new_york_before_and_after_dst(tmp_path,day,hour,minute,allowed):
 from mnq_timestral.schema import NY
 s=ReplaySession(tmp_path)
 try:
  local=datetime.fromisoformat(day).replace(hour=hour,minute=minute,tzinfo=NY)
  s.now=local.astimezone(UTC);s.runtime.last_data=s.now
  assert s.runtime.submit_candidate('MES',1,100.,s.now,'window-fixture') is allowed
  if not allowed:assert s.runtime.state['decisions'][-1]['reason']=='outside_entry_window'
 finally:s.close()


@pytest.mark.parametrize('changes',[{'credential_owner_verified':False},{'authorized_key_sha256':None}])
def test_forward_probe_never_loads_a_key_without_owner_and_key_binding(changes):
 from test_databento_live import provider,grant,OPEN
 from mnq_local.databento_live import connect_sdk
 p,_,_=provider();calls=[]
 with pytest.raises(PermissionError):
  connect_sdk(p,{**grant(),**changes},600,OPEN,key_loader=lambda:calls.append('key'),factory=lambda **k:pytest.fail('SDK constructed'))
 assert not calls


def test_forward_probe_rejects_a_different_saved_key_before_sdk_construction():
 from test_databento_live import provider,grant,OPEN
 from mnq_local.databento_live import connect_sdk
 p,_,_=provider()
 with pytest.raises(PermissionError):
  connect_sdk(p,grant(),600,OPEN,key_loader=lambda:'different-fake-owner-key',factory=lambda **k:pytest.fail('SDK constructed'))
