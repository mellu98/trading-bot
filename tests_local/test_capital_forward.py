"""Forward runtime contracts, fixtures and actual schema regressions only."""
from dataclasses import replace
from datetime import datetime,timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest
from mnq_local.capital import CapitalConfig,CapitalHTTP,CapitalJournal,CapitalBroker,CFDInstrument,CapitalError
from test_capital_demo import Fixture,CREDS,instrument_fixture


def test_eur_demo_config_is_explicit_not_assumed_usd():
    config=CapitalConfig('DEMO1',currency='EUR')
    assert config.currency=='EUR' and config.daily_max_loss==20
    with pytest.raises(ValueError):CapitalConfig('DEMO1',currency='INVALID')


def test_actual_market_schema_missing_snapshot_stream_flag_is_valid():
    path=Path(__file__).resolve().parents[1]/'reports/capital-forward/instruments.json'
    doc=json.loads(path.read_text())
    for epic in ('US100','US500'):
        spec=CFDInstrument.from_api(doc[epic])
        assert spec.currency=='USD' and spec.min_size>0


def test_quote_discovery_does_not_require_account_currency_match(tmp_path):
    class EURFixture(Fixture):
        def __call__(self,method,path,headers,body):
            status,result,h=super().__call__(method,path,headers,body)
            if path=='/session' and method=='GET':result['currency']='EUR'
            if path=='/accounts':result['accounts'][0]['currency']='EUR'
            if path.startswith('/markets?'):
                epic='US100' if 'Tech' in path else 'US500'
                return 200,{'markets':[{'epic':epic,'instrumentType':'INDICES','instrumentName':'US Tech 100' if epic=='US100' else 'US 500','tickSize':.1}]},{}
            if path.startswith('/markets/'):
                spec=instrument_fixture().raw.copy();spec['instrument']={**spec['instrument'],'epic':path.rsplit('/',1)[1]}
                return 200,spec,{}
            return status,result,h
    f=EURFixture();http=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None,orders_enabled=False);http.login()
    cfg=CapitalConfig('DEMO1',currency='EUR');j=CapitalJournal(tmp_path/'state.sqlite',cfg)
    try:
        b=CapitalBroker(http,j,cfg);b.reconcile();assert b.ready
        assert set(b.discover())=={'US100','US500'}
    finally:j.close()


def pilot_broker(tmp_path):
    class PilotFixture(Fixture):
        def __call__(self,m,p,h,b):
            status,data,headers=super().__call__(m,p,h,b)
            if p=='/session' and m=='GET':data['currency']='EUR'
            if p=='/accounts':data['accounts'][0]['currency']='EUR'
            if p=='/markets?searchTerm=EURUSD':
                return 200,{'markets':[{'epic':'EURUSD','marketStatus':'TRADEABLE','bid':1.1,'offer':1.11,'updateTimeUTC':datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}]},{}
            return status,data,headers
    f=PilotFixture();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None,orders_enabled=False);h.login()
    cfg=CapitalConfig('DEMO1',currency='EUR',mode='technical_test');j=CapitalJournal(tmp_path/'pilot.sqlite',cfg)
    b=CapitalBroker(h,j,cfg);b.reconcile()
    doc=json.loads((Path(__file__).resolve().parents[1]/'reports/capital-forward/instruments.json').read_text())['US100']
    doc['discovery']={'tickSize':.1};b.instruments['US100']=CFDInstrument.from_api(doc)
    b.state['quotes']['US100']={'bid':'29000','ask':'29001.8','timestamp_ms':int(datetime.now(timezone.utc).timestamp()*1000)}
    return f,h,j,b


def test_pilot_plan_uses_native_cfd_size_distances_and_fx(tmp_path):
    f,h,j,b=pilot_broker(tmp_path)
    try:
        plan=b.technical_plan('US100')
        assert Decimal(plan['size'])==Decimal('.001')
        assert Decimal(plan['nominal_risk_account'])<Decimal('2')
        assert Decimal(plan['margin_account'])<Decimal('100')
        assert plan['account_currency']=='EUR' and plan['quote_currency']=='USD'
        assert Decimal(plan['stop_distance'])>Decimal('2.9')
        assert not any(m=='POST' and p=='/positions' for m,p,_ in f.calls)
    finally:j.close()


def test_pilot_once_only_and_order_gate_restored(tmp_path):
    f,h,j,b=pilot_broker(tmp_path)
    try:
        b.technical_open('US100')
        assert not h.orders_enabled
        with pytest.raises(CapitalError,match='technical_attempt_already_recorded'):b.technical_open('US100')
        calls=[body for m,p,body in f.calls if m=='POST' and p=='/positions']
        assert len(calls)==1 and 'stopDistance' in calls[0] and 'profitDistance' in calls[0]
        assert 'stopAmount' not in calls[0]
    finally:j.close()


def test_no_pilot_without_fresh_quote_or_verified_fx(tmp_path):
    f,h,j,b=pilot_broker(tmp_path)
    try:
        b.state['quotes']['US100']['timestamp_ms']=1
        with pytest.raises(CapitalError,match='stale_technical_quote'):b.technical_open('US100')
        assert not any(m=='POST' and p=='/positions' for m,p,_ in f.calls)
    finally:j.close()


def test_closed_entry_keeps_bound_id_when_provider_clears_affected_deals(tmp_path):
    from test_capital_demo import make
    f,h,j,b=make(tmp_path)
    try:
        b.instruments['EPIC1']=instrument_fixture()
        b.place('one','EPIC1','BUY',1,2,4)
        f.positions=[{'position':{'dealId':'deal1','direction':'BUY','size':1,'level':100,'stopLevel':98,'profitLevel':104},'market':{'epic':'EPIC1'}}]
        b.reconcile();assert b.state['intents']['one']['state']=='FILLED'
        old=f.__call__
        def sender(m,p,headers,body):
            status,result,rh=old(m,p,headers,body)
            if p.startswith('/confirms/'):result['affectedDeals']=[]
            return status,result,rh
        h.sender=sender;f.positions=[];b.reconcile()
        assert b.state['halt'] is None
        assert b.state['intents']['one']['state']=='BROKER_POSITION_CLOSED'
        assert b.state['intents']['one']['deal_id']=='deal1'
        assert b.state['intents']['one']['confirmation']['affectedDeals']==[{'dealId':'deal1','status':'OPENED'}]
    finally:j.close()


def test_tiny_available_margin_blocks_pilot_before_any_mutation(tmp_path):
    f,h,j,b=pilot_broker(tmp_path)
    try:
        b.state['balance']['available']=.001
        with pytest.raises(CapitalError,match='technical_virtual_risk_or_margin_limit'):b.technical_open('US100')
        assert not b.state.get('technical_attempted')
        assert not any(m=='POST' and p=='/positions' for m,p,_ in f.calls)
    finally:j.close()


def test_stale_fx_blocks_pilot_without_any_entry(tmp_path):
    f,h,j,b=pilot_broker(tmp_path)
    old=h.sender
    def sender(m,p,headers,body):
        status,data,rh=old(m,p,headers,body)
        if p=='/markets?searchTerm=EURUSD':data['markets'][0]['updateTimeUTC']='2000-01-01T00:00:00'
        return status,data,rh
    h.sender=sender
    try:
        with pytest.raises(CapitalError,match='stale_account_fx'):b.technical_open('US100')
        assert not b.state.get('technical_attempted')
        assert not any(m=='POST' and p=='/positions' for m,p,_ in f.calls)
    finally:j.close()


def test_stale_stream_requests_reconnect_but_allows_initial_grace():
    from mnq_local.capital_app import DemoRuntime
    from datetime import timedelta
    runtime=DemoRuntime.__new__(DemoRuntime)
    now=datetime.now(timezone.utc);runtime.clock=lambda:now
    runtime.last_quote=now-timedelta(seconds=7)
    runtime.require_fresh_stream(5)
    with pytest.raises(CapitalError,match='stale_stream_reconnect'):runtime.require_fresh_stream(11)
    runtime.last_quote=now
    runtime.require_fresh_stream(11)


def test_rest_snapshot_keeps_explicit_utc_and_rejects_stale():
    from mnq_local.capital import rest_snapshot_payload,Quote
    from datetime import timedelta
    now=datetime.now(timezone.utc)
    market={'epic':'US100','instrumentType':'INDICES','delayTime':0,'marketStatus':'TRADEABLE','bid':100,'offer':101,'updateTimeUTC':now.replace(tzinfo=None).isoformat(timespec='milliseconds')}
    payload=rest_snapshot_payload(market)
    assert Quote.parse(payload,now).epic=='US100'
    market['updateTimeUTC']=(now-timedelta(seconds=10)).replace(tzinfo=None).isoformat(timespec='milliseconds')
    with pytest.raises(ValueError):Quote.parse(rest_snapshot_payload(market),now)
    market.pop('updateTimeUTC')
    with pytest.raises(CapitalError):rest_snapshot_payload(market)


def test_rest_observation_is_labeled_and_cannot_send_orders(tmp_path):
    from mnq_local.capital_app import DemoRuntime
    f,h,j,b=pilot_broker(tmp_path);old=h.sender
    def sender(m,p,headers,body):
        if p=='/markets?searchTerm=US100':
            return 200,{'markets':[{'epic':'US100','instrumentType':'INDICES','delayTime':0,'marketStatus':'TRADEABLE','bid':29000,'offer':29001.8,'updateTimeUTC':datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec='milliseconds')}]},{}
        return old(m,p,headers,body)
    h.sender=sender;b.state['quotes']={}
    try:
        r=DemoRuntime(b);r.observe_rest()
        assert b.state['quotes']['US100']['source']=='REST_SNAPSHOT'
        assert b.state['data_fresh'] and not r.connected and not h.orders_enabled
        assert b.state['continuous_strategy_orders_enabled'] is False
        assert not any(m=='POST' and p=='/positions' for m,p,_ in f.calls)
    finally:j.close()
