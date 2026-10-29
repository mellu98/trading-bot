"""Public-only Spot seam tests. No network or credentials in fixtures."""
from dataclasses import replace
from decimal import Decimal as D
import json,time
import pytest
from mnq_local.binance_spot import (SpotConfig,SpotSpec,SpotRuntime,PublicREST,Feed,ms_ns,local_quote)
from mnq_local.replay import AtomicJournal


def spec():
 return SpotSpec.from_exchange(json.load(open('reports/binance-spot/exchangeInfo-preflight.json')))


def make(tmp_path):
 c=SpotConfig();s=spec();j=AtomicJournal(tmp_path/'state.sqlite',c,[s],lock_root=tmp_path/'locks');r=SpotRuntime(c,s,j)
 return r,j


def ready(r,price='100000',at=1000):
 q=local_quote({'u':at,'s':'BTCUSDT','b':price,'B':'1','a':str(D(price)+D('.01')),'A':'1'},time.time_ns(),time.monotonic_ns())
 r.quote=q;r.trade_fresh=True;r.certificate={'passed':True};r.connected=True;r.ready=True
 return q


def test_private_routes_and_redirects_refused():
 for method,path,params in [('POST','/api/v3/order',{}),('GET','/api/v3/account',{}),('GET','https://evil.invalid',{}),('GET','/api/v3/trades',{'symbol':'ETHUSDT'}),('GET','/api/v3/trades',{'symbol':'BTCUSDT','apiKey':'x'})]:
  with pytest.raises(ValueError):PublicREST.validate(method,path,params)
 assert PublicREST.validate('GET','/api/v3/trades',{'symbol':'BTCUSDT','limit':100})


def test_exchange_grid_zero_market_step_and_budget(tmp_path):
 r,j=make(tmp_path);ready(r)
 assert r.spec.step==D('.00001')
 assert r.submit_technical()
 p=r.spot['position'];qty=D(p['quantity']);cost=D(p['entry_cash'])
 assert qty>0 and qty%r.spec.step==0 and cost<=100
 assert D(r.spot['cash'])==D('1000')-cost
 assert D(p['entry_fee'])==qty*D(p['entry_fill'])*D('.001')
 assert not r.submit_technical()
 j.close()


def test_restart_restores_open_protection_and_one_buy(tmp_path):
 r,j=make(tmp_path);ready(r);r.submit_technical();p=dict(r.spot['position']);j.close()
 r,j=make(tmp_path)
 assert r.spot['position']==p and r.spot['budget_spent']
 assert not r.ready and not r.submit_technical()
 ready(r,at=1001);r.request_exit('time_exit');assert r.protect()
 assert r.spot['position'] is None and r.spot['buy_count']==1 and r.spot['sell_count']==1
 assert not r.submit_technical()
 assert D(r.spot['cash'])-D('1000')==D(r.spot['net'])
 j.close()


def test_stop_and_kill_exit_do_not_require_entry_certificate(tmp_path):
 r,j=make(tmp_path);ready(r);r.submit_technical();r.certificate={'passed':False};r.ready=False
 ready(r,'99000',1001);r.certificate={'passed':False};r.ready=False
 assert r.protect() and r.spot['roundtrip']['exit_reason']=='protective_stop'
 j.close()
 r,j=make(tmp_path/'second');ready(r);r.submit_technical();r.stop('kill');r.certificate={'passed':False};r.ready=False
 assert r.protect() and r.spot['roundtrip']['exit_reason']=='kill';j.close()


def test_stale_quote_never_invents_exit(tmp_path):
 r,j=make(tmp_path);q=ready(r);r.submit_technical();r.request_exit('kill')
 r.quote={**q,'received_mono_ns':time.monotonic_ns()-3_000_000_000}
 assert not r.protect() and r.spot['position'] and r.spot['pending_exit']=='kill'
 ready(r,at=1001);assert r.protect();j.close()


def test_timestamps_closed_bars_dedup_and_book_jumps(tmp_path):
 r,j=make(tmp_path);f=Feed(r);now=time.time_ns();mono=time.monotonic_ns();ms=now//1_000_000
 assert ms_ns(ms)==ms*1_000_000
 with pytest.raises(ValueError):ms_ns(ms*1000)
 b={'u':1,'s':'BTCUSDT','b':'100000','B':'1','a':'100000.01','A':'1'}
 assert f.process({'stream':'btcusdt@bookTicker','data':b},now,mono)
 assert f.process({'stream':'btcusdt@bookTicker','data':{**b,'u':100}},now,mono)
 assert not f.process({'stream':'btcusdt@bookTicker','data':b},now,mono)
 assert f.stats['trade_gaps']==0 and r.quote['source_ns'] is None
 trade={'e':'trade','s':'BTCUSDT','t':10,'E':ms,'T':ms,'p':'100000','q':'.001','m':True}
 assert f.process({'stream':'btcusdt@trade','data':trade},now,mono)
 assert not f.process({'stream':'btcusdt@trade','data':trade},now,mono)
 assert f.process({'stream':'btcusdt@trade','data':{**trade,'t':12}},now,mono)
 assert f.stats['trade_gaps']==1 and not f.certified()
 k={'e':'kline','E':ms,'s':'BTCUSDT','k':{'t':ms//60000*60000-60000,'T':ms//60000*60000-1,'s':'BTCUSDT','i':'1m','o':'1','h':'2','l':'1','c':'2','v':'1','x':False}}
 f.process({'stream':'btcusdt@kline_1m','data':k},now,mono);assert not f.closed
 k['k']['x']=True;f.process({'stream':'btcusdt@kline_1m','data':k},now,mono);assert f.closed
 j.close()


def test_processing_delay_disconnect_blocks_entry_not_exit(tmp_path):
 r,j=make(tmp_path);ready(r);r.submit_technical();f=Feed(r)
 f.disconnected('test_disconnect');assert not r.ready and r.spot['pending_exit']=='feed_disconnect'
 assert not r.protect();ready(r,at=1001);assert r.protect()
 f.process({'stream':'btcusdt@bookTicker','data':{'u':1002,'s':'BTCUSDT','b':'1','B':'1','a':'1.01','A':'1'}},time.time_ns(),time.monotonic_ns()-500_000_000)
 assert f.stats['processing_delay_rejections']==1
 j.close()


def test_wide_spread_blocks_entry_but_not_protective_exit(tmp_path):
 r,j=make(tmp_path);ready(r);r.submit_technical();r.request_exit('kill')
 r.quote={**r.quote,'spread_bps':'20'}
 assert not r.quote_fresh() and r.protect()
 j.close()


def test_atomic_entry_failure_rolls_back_budget_and_fills(tmp_path,monkeypatch):
 r,j=make(tmp_path);ready(r);original=r._fill
 def fail(*args):original(*args);raise RuntimeError('crash_before_atomic_commit')
 monkeypatch.setattr(r,'_fill',fail)
 with pytest.raises(RuntimeError):r.submit_technical()
 assert not r.spot['budget_spent'] and not r.state['executions'] and r.spot['cash']=='1000'
 j.close()


def test_native_closed_bar_validation_and_processing_recertification(tmp_path):
 r,j=make(tmp_path);f=Feed(r);f.connected();old=f.started;time.sleep(.001)
 f.process({'stream':'btcusdt@bookTicker','data':{'u':1,'s':'BTCUSDT','b':'1','B':'1','a':'1.01','A':'1'}},time.time_ns(),time.monotonic_ns()-500_000_000)
 assert f.started>old and not f.rest_checks
 j.close()


def test_existing_dashboard_has_opt_in_spot_renderer():
 from pathlib import Path
 html=Path('src/mnq_local/dashboard.html').read_text()
 assert 'LIVE_PUBLIC_DATA_LOCAL_PAPER' in html and 'entry_certificate' in html
 assert 'HISTORICAL REPLAY' in html and 'Max size: 1 micro' in html


def test_reconnect_discards_buffered_preconnection_receipt(tmp_path):
 r,j=make(tmp_path);ready(r);f=Feed(r)
 received=time.time_ns();mono=time.monotonic_ns();time.sleep(.002);f.connected()
 assert r.quote is None and not r.trade_fresh
 item={'stream':'btcusdt@bookTicker','data':{'u':99999,'s':'BTCUSDT','b':'1','B':'1','a':'1.01','A':'1'}}
 assert not f.process(item,received,mono) and r.quote is None
 assert f.stats['previous_connection_events_discarded']==1
 j.close()


def test_public_burst_coalesces_persistence_but_protects_each_quote(tmp_path,monkeypatch):
 from mnq_local.binance_app import process_public_event,persist_observation
 r,j=make(tmp_path);f=Feed(r);f.connected();r.spot['position']={'quantity':'.001'}
 r.spot['equity']=[{'at':'synthetic','equity':0} for _ in range(3600)]
 calls=[];saved=[];monkeypatch.setattr(r,'protect',lambda:calls.append(r.quote['update_id']))
 monkeypatch.setattr(j,'save',lambda kind,body=None:saved.append(kind))
 def forbidden_transaction():raise AssertionError('Noncritical event must not copy/commit full journal')
 monkeypatch.setattr(j,'bar_transaction',forbidden_transaction)
 for i in range(500):
  item={'stream':'btcusdt@bookTicker','data':{'u':i+1,'s':'BTCUSDT','b':'100000','B':'1','a':'100000.01','A':'1'}}
  assert process_public_event(r,f,item,time.time_ns(),time.monotonic_ns())
 assert len(calls)==500 and not saved and not f.stats['processing_delay_rejections']
 persist_observation(r,f)
 assert saved==['spot_public_batch'] and r.spot['last_quote_snapshot']['update_id']==500
 j.close()
