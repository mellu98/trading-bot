"""Offline-only contracts. SDK record fixtures are not live observations."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json,hashlib
import pytest
import databento_dbn as dbn
from mnq_paper.core import ContractSpec
UTC=timezone.utc
SPECS=(ContractSpec('MES','MESZ6',42001581,'20261218'),ContractSpec('MNQ','MNQZ6',42005282,'20261218'))
MINUTE=60*10**9
OPEN=int(datetime(2026,10,26,13,30,tzinfo=UTC).timestamp())*10**9

def trade(at=OPEN+1,seq=1,spec=SPECS[1],price=29000,size=1):
 return dbn.TradeMsg(publisher_id=1,instrument_id=spec.con_id,ts_event=at,ts_recv=at+100,price=int(Decimal(str(price))*10**9),size=size,
  action=dbn.Action.TRADE,side=dbn.Side.ASK,depth=0,sequence=seq)

def quote(at=OPEN+1,seq=1,spec=SPECS[1],bid=29000,ask=29000.25):
 return dbn.MBP1Msg(publisher_id=1,instrument_id=spec.con_id,ts_event=at,ts_recv=at+100,price=int(Decimal(str(bid))*10**9),size=1,
  action=dbn.Action.ADD,side=dbn.Side.BID,depth=0,sequence=seq,levels=dbn.BidAskPair(bid_px=int(Decimal(str(bid))*10**9),ask_px=int(Decimal(str(ask))*10**9),bid_sz=2,ask_sz=3))

def mapping(spec=SPECS[1]):
 return dbn.SymbolMappingMsg(publisher_id=0,instrument_id=spec.con_id,ts_event=OPEN,stype_in=dbn.SType.RAW_SYMBOL,stype_in_symbol=spec.local_symbol,
  stype_out=dbn.SType.RAW_SYMBOL,stype_out_symbol=spec.local_symbol,start_ts=dbn.UNDEF_TIMESTAMP,end_ts=dbn.UNDEF_TIMESTAMP)

def provider():
 from mnq_local.databento_live import DatabentoLiveProvider
 state={};events=[];p=DatabentoLiveProvider(SPECS,state,lambda *e:events.append(e),context_start_ns=OPEN)
 for spec in SPECS:p.ingest(mapping(spec),received_ns=OPEN,now_ns=OPEN)
 return p,state,events

def test_official_sdk_records_keep_exact_nanoseconds_and_fields():
 p,state,_=provider();at=OPEN+123456789
 result=p.ingest(trade(at),received_ns=at+333,now_ns=at+444)
 assert result['event']['ts_event_ns']==at and result['event']['ts_recv_ns']==at+100
 assert result['event']['received_ns']==at+333 and result['event']['price_nano']==29000*10**9
 assert p.state['open_bars']['MNQ']['volume']==1


def test_minute_bars_use_only_trades_not_mbp_trade_copies_and_are_causal():
 p,_,_=provider();p.ingest(trade(),received_ns=OPEN+1000,now_ns=OPEN+1000)
 p.ingest(quote(OPEN+2),received_ns=OPEN+1001,now_ns=OPEN+1001)
 p.ingest(trade(OPEN+30*10**9,2,price=29001,size=3),received_ns=OPEN+30*10**9+1000,now_ns=OPEN+30*10**9+1000)
 at=OPEN+60*10**9+123
 result=p.ingest(trade(at,3,price=29002),received_ns=at+1000,now_ns=at+1000)
 b=result['bars'][0];assert b['start_ns']==OPEN and b['end_ns']==OPEN+60*10**9
 assert b['volume']==4 and b['high']==29001 and b['close']==29001 and b['available_ns']==at+1000
 assert result['event']['ts_event_ns']>b['end_ns']


def test_duplicate_reconnect_replay_and_restart_do_not_inflate_volume():
 from mnq_local.databento_live import DatabentoLiveProvider
 p,state,_=provider();raw=trade();p.ingest(raw,received_ns=OPEN+1000,now_ns=OPEN+1000)
 assert p.ingest(raw,received_ns=OPEN+2000,now_ns=OPEN+2000)['status']=='duplicate'
 other=DatabentoLiveProvider(SPECS,json.loads(json.dumps(state)),lambda *_:None,context_start_ns=OPEN)
 assert other.ingest(raw,received_ns=OPEN+3000,now_ns=OPEN+3000)['status']=='duplicate'
 assert other.state['open_bars']['MNQ']['volume']==1


def test_out_of_order_or_late_trade_is_rejected_without_revising_a_closed_bar():
 p,_,_=provider();p.ingest(trade(OPEN+1000,1),received_ns=OPEN+2000,now_ns=OPEN+2000)
 at=OPEN+60*10**9+1;p.ingest(trade(at,3),received_ns=at+1000,now_ns=at+1000)
 result=p.ingest(trade(OPEN+2000,2),received_ns=at+2000,now_ns=at+2000)
 assert result['status']=='rejected' and p.state['fault']=='out_of_order_source_event'
 assert len(p.state['closed_bars'])==1


@pytest.mark.parametrize('kind',['crossed','off_tick','stale','unknown_id'])
def test_invalid_quotes_never_become_entry_prices(kind):
 p,_,_=provider();at=OPEN+123
 if kind=='crossed':raw=quote(at,bid=29001,ask=29000)
 elif kind=='off_tick':raw=quote(at,bid=29000.1)
 elif kind=='unknown_id':raw=quote(at,spec=ContractSpec('MNQ','MNQZ6',123,'20261218'))
 else:raw=quote(at)
 now=at+(6*10**9 if kind=='stale' else 1000)
 result=p.ingest(raw,received_ns=now,now_ns=now)
 assert not result['quote_fresh'] and not p.fresh('MNQ',now)


def test_quote_freshness_does_not_refresh_on_heartbeat_or_duplicate():
 p,_,_=provider();at=OPEN+1000;p.ingest(quote(at),received_ns=at+1000,now_ns=at+1000)
 assert p.fresh('MNQ',at+1000)
 p.ingest(dbn.SystemMsg(ts_event=at+6*10**9,msg='heartbeat'),received_ns=at+6*10**9,now_ns=at+6*10**9)
 assert not p.fresh('MNQ',at+6*10**9)


def test_bar_conversion_explicitly_rounds_up_legacy_availability_retaining_ns():
 from mnq_local.databento_live import legacy_bar
 r={'symbol':'MNQ','contract':'MNQZ6','start_ns':OPEN,'end_ns':OPEN+60*10**9,'available_ns':OPEN+60*10**9+123,
  'open':29000,'high':29001,'low':29000,'close':29001,'volume':4}
 b=legacy_bar(r)
 assert b.available_at==datetime(2026,10,26,13,31,tzinfo=UTC)+timedelta(microseconds=1)
 assert r['available_ns']==OPEN+60*10**9+123


def grant():
 return {'license_confirmed':True,'live_entitlement_confirmed':True,'spending_authorized':True,'license_reference':'FAKE-OFFLINE-TEST',
  'credential_owner_verified':True,'authorized_key_sha256':hashlib.sha256(b'fake-key').hexdigest(),'authorization_id':'fixture-once','dataset':'GLBX.MDP3','schemas':['trades','mbp-1'],'contracts':[s.local_symbol for s in SPECS],
  'purpose':'READ_ONLY_MARKET_DATA_LOCAL_SIMULATION','max_seconds':600,'not_before_ns':OPEN-10**9,'expires_ns':OPEN+1000*10**9,
  'confirmed_total_monthly_usd':'199','authorized_total_monthly_usd_max':'199'}


def test_no_sdk_construction_or_key_loading_before_license_cost_entitlement_gate():
 from mnq_local.databento_live import connect_sdk
 p,_,_=provider();g=grant();g['license_confirmed']=False;calls=[]
 with pytest.raises(PermissionError):connect_sdk(p,g,600,OPEN,key_loader=lambda:calls.append('key'),factory=lambda **k:calls.append('SDK'))
 assert calls==[]


def test_authorization_is_scoped_bounded_expiring_and_consumed_once():
 from mnq_local.databento_live import connect_sdk
 from queue import Queue
 p,_,_=provider();calls=[]
 class SDK:
  def __init__(self,**kw):calls.append('construct')
  def add_callback(self,*a,**k):pass
  def add_reconnect_callback(self,*a,**k):pass
  def subscribe(self,**kw):calls.append(kw)
  def start(self):calls.append('start')
  def terminate(self):pass
 client,inbox,failed=connect_sdk(p,grant(),600,OPEN,key_loader=lambda:'fake-key',factory=SDK)
 assert len([c for c in calls if isinstance(c,dict)])==2
 assert all(c['dataset']=='GLBX.MDP3' and c['stype_in']=='raw_symbol' for c in calls if isinstance(c,dict))
 assert {c['schema'] for c in calls if isinstance(c,dict)}=={'trades','mbp-1'}
 with pytest.raises(PermissionError):connect_sdk(p,grant(),600,OPEN,key_loader=lambda:'fake-key',factory=SDK)
 assert calls.count('construct')==1


@pytest.mark.parametrize('change',[{'spending_authorized':False},{'live_entitlement_confirmed':False},{'dataset':'OTHER'},
 {'schemas':['mbo']},{'contracts':['MNQZ6']},{'expires_ns':OPEN-1},{'confirmed_total_monthly_usd':'200'},{'max_seconds':0}])
def test_authorization_mismatch_never_contacts_gateway(change):
 from mnq_local.databento_live import validate_authorization
 with pytest.raises((PermissionError,ValueError)):validate_authorization({**grant(),**change},SPECS,600,OPEN)


def test_first_afterhours_trade_closes_last_rth_bar_without_creating_fake_afterhours_bar():
 p,_,_=provider();at=OPEN+(6*60+29)*MINUTE+1
 p.ingest(trade(at,1),received_ns=at+1000,now_ns=at+1000)
 end=at//MINUTE*MINUTE+MINUTE
 result=p.ingest(trade(end+1,2),received_ns=end+1000,now_ns=end+1000)
 assert len(result['bars'])==1 and result['bars'][0]['end_ns']==end
 assert 'MNQ' not in p.state['open_bars'] and p.state['fault'] is None


def test_dedup_eviction_order_survives_sorted_json_snapshot():
 from mnq_local.databento_live import DatabentoLiveProvider
 p,state,_=provider();keys=['z'*64]+[f'{i:064x}' for i in range(8191)]
 p.state['seen']={k:OPEN for k in keys};p.state['seen_order']=keys[:]
 other=DatabentoLiveProvider(SPECS,json.loads(json.dumps(state,sort_keys=True)),lambda *_:None,context_start_ns=OPEN)
 other.ingest(trade(),received_ns=OPEN+1000,now_ns=OPEN+1000)
 assert keys[0] not in other.state['seen'] and keys[1] in other.state['seen']


def test_malformed_cost_never_escapes_as_unredacted_decimal_error():
 from mnq_local.databento_live import validate_authorization
 with pytest.raises(PermissionError):validate_authorization({**grant(),'confirmed_total_monthly_usd':None},SPECS,600,OPEN)


def test_official_live_mapping_uses_header_id_raw_output_and_undefined_bounds():
 p,_,_=provider();m=p.state['mapped'].get('MNQ')
 assert m and m['publisher_id']==0 and m['contract']=='MNQZ6'
 assert m['source_start_ns']==dbn.UNDEF_TIMESTAMP and m['source_end_ns']==dbn.UNDEF_TIMESTAMP
 assert m['bounds_policy']=='UNDEFINED_SOURCE_BOUNDS_SCOPED_TO_CONTEXT_AND_EXPIRY'
 assert m['start_ns']==OPEN and OPEN<m['end_ns']
 assert p.ingest(trade(),received_ns=OPEN+1000,now_ns=OPEN+1000)['status']=='accepted'


@pytest.mark.parametrize('change',[{'publisher_id':2},{'stype_out_symbol':'MNQH7'},{'stype_in_symbol':'MNQ.c.0'},
 {'start_ts':OPEN+1,'end_ts':OPEN}])
def test_mapping_rejects_foreign_or_mismatched_contract_and_bad_bounds(change):
 from mnq_local.databento_live import DatabentoLiveProvider
 values=dict(publisher_id=0,instrument_id=SPECS[1].con_id,ts_event=OPEN,stype_in=dbn.SType.RAW_SYMBOL,
  stype_in_symbol='MNQZ6',stype_out=dbn.SType.RAW_SYMBOL,stype_out_symbol='MNQZ6',start_ts=OPEN,end_ts=OPEN+MINUTE)
 values.update(change);p=DatabentoLiveProvider(SPECS,{},lambda *_:None,context_start_ns=OPEN)
 assert p.ingest(dbn.SymbolMappingMsg(**values),received_ns=OPEN,now_ns=OPEN)['status']=='rejected'
 assert not p.state['mapped']


def test_market_publisher_zero_is_not_allowed_by_mapping_control_exception():
 p,_,_=provider()
 raw=dbn.TradeMsg(publisher_id=0,instrument_id=SPECS[1].con_id,ts_event=OPEN+1,ts_recv=OPEN+2,price=29000*10**9,
  size=1,action=dbn.Action.TRADE,side=dbn.Side.ASK,depth=0,sequence=1)
 assert p.ingest(raw,received_ns=OPEN+1000,now_ns=OPEN+1000)['status']=='rejected'
 assert p.state['fault']=='foreign_publisher'


def test_callback_overflow_is_latched_and_reconnect_never_silently_replays():
 from mnq_local.databento_live import connect_sdk
 p,_,_=provider()
 class SDK:
  def __init__(self,**kw):self.policy=kw['reconnect_policy']
  def add_callback(self,callback,**kw):self.callback=callback
  def add_reconnect_callback(self,callback,**kw):self.reconnect_callback=callback
  def subscribe(self,**kw):pass
  def start(self):pass
  def terminate(self):pass
 client,inbox,failed=connect_sdk(p,grant(),600,OPEN,key_loader=lambda:'fake-key',factory=SDK)
 client.reconnect_callback(OPEN,OPEN+1)
 assert inbox.get_nowait()[0]=='reconnect' and client.policy=='reconnect'
 for _ in range(4097):client.callback(trade())
 assert inbox.qsize()==4096 and failed.is_set()


def test_explicit_mapping_bounds_do_not_accept_earlier_market_event():
 from mnq_local.databento_live import DatabentoLiveProvider
 p=DatabentoLiveProvider(SPECS,{},lambda *_:None,context_start_ns=OPEN)
 raw=dbn.SymbolMappingMsg(publisher_id=0,instrument_id=SPECS[1].con_id,ts_event=OPEN,stype_in=dbn.SType.RAW_SYMBOL,
  stype_in_symbol='MNQZ6',stype_out=dbn.SType.RAW_SYMBOL,stype_out_symbol='MNQZ6',start_ts=OPEN+100,end_ts=OPEN+MINUTE)
 assert p.ingest(raw,received_ns=OPEN+1000,now_ns=OPEN+1000)['status']=='accepted'
 assert p.ingest(trade(OPEN+1),received_ns=OPEN+1000,now_ns=OPEN+1000)['status']=='rejected'
 assert p.state['fault']=='unverified_point_in_time_mapping'
