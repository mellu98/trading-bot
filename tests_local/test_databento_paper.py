from datetime import timedelta
import json
import pytest
from test_databento_live import SPECS,OPEN,mapping,trade,quote
from mnq_local.replay import ReplayOptions,load_session
from mnq_timestral.schema import UTC

def session(tmp_path,technical=False):
 from mnq_local.databento_paper import DatabentoPaperSession
 return DatabentoPaperSession(tmp_path,ReplayOptions(session='2026-10-26'),SPECS,context_start_ns=OPEN,offline=True,technical_simulation=technical)


def test_live_market_session_defaults_readonly_with_same_v3_order_owner(tmp_path):
 s=session(tmp_path)
 try:
  from mnq_paper.core import Runtime
  assert type(s.runtime) is Runtime and s.broker.kind=='LOCAL_SYNTHETIC_EXECUTION_NOT_BROKER_PAPER'
  assert not s.broker.entries_enabled and s.config.mode=='strict_paper'
  assert s.report()['real_money_routing'] is False
 finally:s.close()


def test_real_cme_ohlcv_offline_path_retains_strict_news_and_no_live_claim(tmp_path):
 from mnq_local.databento_paper import DatabentoPaperSession
 bars,_=load_session('2026-10-19')
 s=DatabentoPaperSession(tmp_path,ReplayOptions(),SPECS,context_start_ns=int(bars[0].start.timestamp())*10**9,offline=True)
 try:
  for bar in bars:s.ingest_historical(bar)
  assert s.report()['bars_processed']==780 and s.report()['orders']==0
  assert s.report()['mode']=='OFFLINE_CME_REPLAY_NOT_LIVE'
  assert any(d['reason']=='strict_news_and_strategy_not_certified' for d in s.runtime.state['decisions'])
 finally:s.close()


def test_offline_synthetic_orders_use_existing_brackets_and_kill_survives_restart(tmp_path):
 from mnq_local.databento_paper import DatabentoPaperSession
 bars,_=load_session('2026-10-19');anchor=int(bars[0].start.timestamp())*10**9
 s=DatabentoPaperSession(tmp_path,ReplayOptions(),SPECS,context_start_ns=anchor,offline=True,technical_simulation=True)
 try:
  for bar in bars:
   s.ingest_historical(bar)
   if any(p['quantity'] for p in s.runtime.state['positions'].values()):break
  assert any(p['quantity'] for p in s.runtime.state['positions'].values())
  s.kill();assert not any(p['quantity'] for p in s.runtime.state['positions'].values())
  count=len(s.runtime.state['executions']);assert s.runtime.state['halt']=='kill'
 finally:s.close()
 s=DatabentoPaperSession(tmp_path,ReplayOptions(),SPECS,context_start_ns=anchor,offline=True,technical_simulation=True)
 try:assert len(s.runtime.state['executions'])==count and s.runtime.state['halt']=='kill'
 finally:s.close()


def test_atomic_event_crash_never_advances_volume_or_orders(tmp_path,monkeypatch):
 s=session(tmp_path)
 try:
  for spec in SPECS:s.ingest(mapping(spec),OPEN,OPEN)
  before=json.loads(json.dumps(s.journal.state));real=s.provider.ingest
  def fail(*a,**k):real(*a,**k);raise RuntimeError('injected crash')
  monkeypatch.setattr(s.provider,'ingest',fail)
  with pytest.raises(RuntimeError):s.ingest(trade(),OPEN+1000,OPEN+1000)
  assert s.journal.state==before
 finally:s.close()
 s=session(tmp_path)
 try:
  result=s.ingest(trade(),OPEN+1000,OPEN+1000)
  assert result['status']=='accepted' and s.provider.state['open_bars']['MNQ']['volume']==1
 finally:s.close()


def test_disconnect_latches_entries_and_recovery_does_not_clear_kill(tmp_path):
 s=session(tmp_path)
 try:
  s.disconnected('fixture_disconnect');assert not s.runtime.ready
  assert s.runtime.state['blocked_session']=='2026-10-26'
  s.reconcile();assert not s.broker.entries_enabled
  assert s.provider.state['fault']=='fixture_disconnect'
 finally:s.close()


def test_live_session_cannot_enable_technical_execution_even_in_python(tmp_path):
 from mnq_local.databento_paper import DatabentoPaperSession
 with pytest.raises(ValueError,match='offline_only'):
  DatabentoPaperSession(tmp_path,ReplayOptions(session='2026-10-26'),SPECS,context_start_ns=OPEN,offline=False,technical_simulation=True)


def test_market_events_batch_in_one_sqlite_transaction(tmp_path,monkeypatch):
 from contextlib import contextmanager
 s=session(tmp_path);calls=[]
 try:
  real=s.journal.bar_transaction
  @contextmanager
  def counted():
   calls.append(1)
   with real():yield
  monkeypatch.setattr(s.journal,'bar_transaction',counted)
  s.ingest_batch([(mapping(spec),OPEN,OPEN) for spec in SPECS]+[(trade(OPEN+i+1,i+1),OPEN+i+1000,OPEN+i+1000) for i in range(50)])
  assert len(calls)==1 and s.provider.state['open_bars']['MNQ']['volume']==50
 finally:s.close()


def primed_tick_session(tmp_path,fill=True):
 from mnq_timestral.schema import Bar
 from mnq_local.databento_live import exact_utc,MINUTE
 s=session(tmp_path,technical=True)
 for i in range(20):
  for symbol,price in [('MES',5000),('MNQ',29000)]:
   at=exact_utc(OPEN+i*MINUTE);end=at+timedelta(minutes=1)
   s.ingest_historical(Bar(symbol,symbol+'Z6',at,end,end,price,price,price,price,10))
 for spec in SPECS:s.ingest(mapping(spec),OPEN+20*MINUTE,OPEN+20*MINUTE)
 for spec,price in zip(SPECS,[5000,29000]):
  at=OPEN+20*MINUTE+1000;s.ingest(quote(at,spec=spec,bid=price,ask=price+.25),at+1000,at+1000)
 assert s.runtime.submit_candidate('MNQ',1,29000,s.now,'fixture-local-tick')
 at=OPEN+20*MINUTE+10000
 if fill:
  s.ingest(quote(at,2,bid=28999.75,ask=29000),at+1000,at+1000)
  assert s.runtime.state['positions']['MNQ']['quantity']==1
 return s,at


@pytest.mark.parametrize('exit_kind',['stop','target','kill'])
def test_sdk_quote_fixture_drives_existing_brackets_and_controlled_exit(tmp_path,exit_kind):
 s,at=primed_tick_session(tmp_path)
 try:
  if exit_kind=='kill':s.kill()
  else:
   leg=next(o for o in s.broker.orders.values() if o['role']==exit_kind)
   price=leg['stop']-.5 if exit_kind=='stop' else leg['limit']+.25
   s.ingest(quote(at+10000,3,bid=price,ask=price+.25),at+11000,at+11000)
  assert s.runtime.state['positions']['MNQ']['quantity']==0
  assert s.report()['trades']==1 and not s.report()['working_orders']
  assert s.report()['fees']==1.22
 finally:s.close()


def test_pre_submission_quote_cannot_fill_a_new_order_even_if_received_late(tmp_path):
 s,at=primed_tick_session(tmp_path)
 try:
  s.kill();assert not any(p['quantity'] for p in s.runtime.state['positions'].values())
  # A duplicate or old source event cannot create another fill after the kill.
  before=len(s.runtime.state['executions'])
  s.ingest(quote(at-1,4,bid=28999.5,ask=28999.75),at+30000,at+30000)
  assert len(s.runtime.state['executions'])==before and s.runtime.state['halt']=='kill'
 finally:s.close()


def test_late_arriving_quote_with_pre_submission_source_time_does_not_fill(tmp_path):
 s,at=primed_tick_session(tmp_path,fill=False)
 try:
  from mnq_local.databento_live import MINUTE
  source=OPEN+20*MINUTE+1500
  s.ingest(quote(source,2,bid=28999.75,ask=29000),source+10000,source+10000)
  assert not any(p['quantity'] for p in s.runtime.state['positions'].values())
  entry=next(o for o in s.broker.orders.values() if o['role']=='entry')
  assert entry['status']=='Submitted' and entry['submitted_at_ns']==OPEN+20*MINUTE+2000
 finally:s.close()


def test_quote_staleness_blocks_entries_and_preserves_protective_flatten(tmp_path):
 s,at=primed_tick_session(tmp_path)
 try:
  s.broker.entries_enabled=False
  s.tick(at+6*10**9)
  assert not s.provider.fresh('MNQ',at+6*10**9)
  assert not any(p['quantity'] for p in s.runtime.state['positions'].values())
  assert not s.report()['working_orders'] and s.report()['halt']=='stale_data'
 finally:s.close()


def test_restart_with_open_local_position_reconciles_existing_stop_and_target(tmp_path):
 s,at=primed_tick_session(tmp_path)
 before=len(s.runtime.state['executions']);orders=len(s.runtime.state['orders']);s.close()
 s=session(tmp_path,technical=True)
 try:
  assert s.runtime.state['positions']['MNQ']['quantity']==1
  assert len(s.runtime.state['executions'])==before and len(s.runtime.state['orders'])==orders
  assert {o['role'] for o in s.report()['working_orders']}=={'stop','target'}
  leg=next(o for o in s.broker.orders.values() if o['role']=='stop');price=leg['stop']-.5
  s.ingest(quote(at+10000,3,bid=price,ask=price+.25),at+11000,at+11000)
  assert not any(p['quantity'] for p in s.runtime.state['positions'].values())
  assert not s.report()['working_orders'] and s.report()['trades']==1
 finally:s.close()


def test_dashboard_report_retains_source_and_receipt_ns_without_claiming_network_latency(tmp_path):
 s=session(tmp_path)
 try:
  for spec in SPECS:s.ingest(mapping(spec),OPEN,OPEN)
  at=OPEN+123456789;s.ingest(quote(at),at+333,at+777)
  source=s.report()['source'];q=source['top_of_book']['MNQ']
  assert q['source_event_ns']==at and q['received_ns']==at+333
  assert q['source_age_ns']==777 and q['local_receipt_age_ns']==444
  assert q['bid']==29000 and q['ask']==29000.25
  assert source['transport_latency_measured'] is False
 finally:s.close()
