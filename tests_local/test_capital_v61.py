"""V6.1 regressions; fixtures do not certify a real broker."""
from datetime import datetime,timedelta,timezone
import pytest
from mnq_local.capital import CapitalError,CapitalHTTP,CapitalJournal,CapitalConfig,CapitalBroker,dec
from mnq_local.capital_app import DemoRuntime
from test_capital_demo import Lifecycle,CREDS,instrument_fixture


def test_kill_can_close_only_owned_position_with_entry_gate_disabled(tmp_path):
    f=Lifecycle();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None);h.login()
    cfg=CapitalConfig('DEMO1',mode='technical_test');j=CapitalJournal(tmp_path/'state.sqlite',cfg);b=CapitalBroker(h,j,cfg)
    try:
        b.reconcile();b.instruments['EPIC1']=instrument_fixture()
        b.place('entry','EPIC1','BUY',dec(1),dec(2),dec(4));b.reconcile()
        assert b.state['positions'];h.orders_enabled=False
        b.flatten();b.reconcile()
        assert not b.state['positions'] and b.state['halt']=='kill' and not h.orders_enabled
        assert sum(m=='DELETE' for m,p,_ in f.calls)==1
        b.flatten();assert sum(m=='DELETE' for m,p,_ in f.calls)==1
        with pytest.raises(CapitalError,match='orders_disabled'):h.request('POST','/positions',{})
        with pytest.raises(CapitalError,match='foreign_position'):b.close_position('foreign','other')
    finally:j.close()


def test_watchdog_checks_source_age_for_all_instruments_not_last_receipt():
    now=datetime.now(timezone.utc);r=DemoRuntime.__new__(DemoRuntime)
    r.clock=lambda:now;r.last_quote=now;r.sources={'US100':None,'US500':None}
    from types import SimpleNamespace
    r.broker=SimpleNamespace(ready=True,state={'halt':None,'quotes':{
        'US100':{'timestamp_ms':int(now.timestamp()*1000)},
        'US500':{'timestamp_ms':int((now-timedelta(seconds=6)).timestamp()*1000)}}})
    with pytest.raises(CapitalError,match='stale_quote_entries_blocked'):r.watchdog()
    assert not r.broker.ready


def test_quote_receipt_does_not_hide_local_processing_backlog(tmp_path):
    from test_capital_demo import make
    from mnq_local.capital_app import CFDSignals
    f,h,j,b=make(tmp_path)
    try:
        b.instruments['EPIC1']=instrument_fixture();now=datetime.now(timezone.utc)
        r=DemoRuntime(b,clock=lambda:now)
        payload={'epic':'EPIC1','product':'CFD','bid':100,'ofr':101,'timestamp':int((now-timedelta(seconds=7)).timestamp()*1000)}
        with pytest.raises(ValueError):r.on_quote(payload,received_at=now-timedelta(seconds=7))
        assert not b.state['quotes']
    finally:j.close()


def test_stream_inbox_captures_receipt_before_slow_consumer_and_is_bounded():
    from mnq_local.capital_app import StreamInbox
    import time
    class Socket:
        def recv(self,timeout):return '{}'
    inbox=StreamInbox(Socket(),capacity=2)
    with inbox:
        time.sleep(.02)
        with pytest.raises(CapitalError,match='stream_receive_queue_overflow'):inbox.recv(timeout=.01)
        assert inbox.buffer.qsize()<=2


def test_percentile_metrics_include_rejected_old_quotes_without_claiming_transport():
    from mnq_local.capital_app import FeedMetrics
    metrics=FeedMetrics()
    for age in (1,2,3,4,9000):metrics.add('source_age_ms',age)
    report=metrics.snapshot()
    assert report['source_age_ms']['max']==9000 and report['source_age_ms']['n']==5
    assert report['transport_latency']=='NOT_IDENTIFIABLE'


def test_inactive_verified_session_renews_once_before_readonly_request():
    from test_capital_demo import Fixture
    clock=[1.0];f=Fixture();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None,clock=lambda:clock[0],orders_enabled=False)
    h.login();clock[0]=542
    h.request('GET','/accounts');h.request('GET','/session')
    assert h.verified and h.renewals==1 and not h.orders_enabled
    assert sum(m=='POST' and p=='/session' for m,p,_ in f.calls)==2


def test_rejected_auth_is_not_retried_after_inactivity():
    from test_capital_demo import Fixture
    clock=[1.0];f=Fixture();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None,clock=lambda:clock[0],orders_enabled=False);h.login()
    old=h.sender
    h.sender=lambda m,p,headers,body:(401,{'errorCode':'error.security.invalid-token'}, {}) if p=='/ping' else old(m,p,headers,body)
    with pytest.raises(CapitalError):h.request('GET','/ping')
    clock[0]=1000
    with pytest.raises(CapitalError):h.request('GET','/accounts')
    assert sum(m=='POST' and p=='/session' for m,p,_ in f.calls)==1


def test_automatic_demo_strategy_is_disabled_even_after_technical_roundtrip(tmp_path):
    from test_capital_demo import make
    from dataclasses import replace
    from types import SimpleNamespace
    f,h,j,b=make(tmp_path)
    try:
        b.config=replace(b.config,mode='diagnostic_demo');b.state['technical_roundtrip_verified']=True
        b.instruments['EPIC1']=instrument_fixture();now=datetime.now(timezone.utc);r=DemoRuntime(b,clock=lambda:now)
        r.connected=True;r.fresh_quotes=30
        class Signals:
            blocked=None;strategies=True;tick=dec('.1')
            def on_quote(self,q):return [{'strategy':'orb','epic':q.epic,'side':1,'bar_end':q.at.isoformat()}]
        r.sources={'EPIC1':Signals()}
        r.on_quote({'epic':'EPIC1','product':'CFD','bid':100,'ofr':100.5,'timestamp':int(now.timestamp()*1000)})
        assert b.state['decisions'][-1]['reason']=='automated_demo_not_certified'
        assert not any(m=='POST' and p=='/positions' for m,p,_ in f.calls)
    finally:j.close()


def test_accepted_quote_retains_capture_time_in_signal_event(tmp_path):
    from test_capital_demo import make
    f,h,j,b=make(tmp_path)
    try:
        b.instruments['EPIC1']=instrument_fixture();now=datetime.now(timezone.utc);receipt=now-timedelta(seconds=1)
        r=DemoRuntime(b,clock=lambda:now)
        class Signals:
            blocked=None;strategies=True;tick=dec('.1')
            def on_quote(self,q):return [{'strategy':'orb','epic':q.epic,'side':1,'bar_end':q.at.isoformat(),'received_at':q.received_at.isoformat()}]
        r.sources={'EPIC1':Signals()}
        events=r.on_quote({'epic':'EPIC1','product':'CFD','bid':100,'ofr':100.5,'timestamp':int(receipt.timestamp()*1000)},received_at=receipt)
        assert events[0]['received_at']==receipt.isoformat()
    finally:j.close()


def test_kill_failed_close_restores_entry_gate_and_never_resubmits_unknown(tmp_path):
    f=Lifecycle();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None);h.login()
    cfg=CapitalConfig('DEMO1',mode='technical_test');j=CapitalJournal(tmp_path/'state.sqlite',cfg);b=CapitalBroker(h,j,cfg)
    try:
        b.reconcile();b.instruments['EPIC1']=instrument_fixture();b.place('entry','EPIC1','BUY',dec(1),dec(2),dec(4));b.reconcile();h.orders_enabled=False
        old=h.sender;attempts=[]
        def fail(m,p,headers,body):
            if m=='DELETE':attempts.append(p);raise CapitalError('transport_unknown')
            return old(m,p,headers,body)
        h.sender=fail
        with pytest.raises(CapitalError,match='transport_unknown'):b.flatten()
        assert not h.orders_enabled
        b.flatten();assert len(attempts)==1
        assert b.state['intents']['kill-close-deal1']['state']=='UNKNOWN'
    finally:j.close()


def test_owned_working_order_cancel_works_with_entry_gate_disabled(tmp_path):
    from test_capital_demo import make
    f,h,j,b=make(tmp_path)
    try:
        old=h.sender
        def sender(m,p,headers,body):
            if m=='DELETE' and p=='/workingorders/order1':
                f.calls.append((m,p,body));return 200,{'dealReference':'cancel-ref'},{}
            return old(m,p,headers,body)
        h.sender=sender
        b.state['intents']['owned']={'operation':'open','deal_id':'order1','state':'WORKING'}
        h.orders_enabled=False
        b.cancel('cancel-one','order1')
        assert not h.orders_enabled
        assert sum(m=='DELETE' and p=='/workingorders/order1' for m,p,_ in f.calls)==1
        with pytest.raises(CapitalError,match='duplicate_intent'):b.cancel('cancel-one','order1')
        with pytest.raises(CapitalError,match='foreign_order'):b.cancel('cancel-foreign','order2')
        assert not h.orders_enabled
    finally:j.close()


def test_one_failed_idle_renewal_never_becomes_an_authentication_loop():
    from test_capital_demo import Fixture
    clock=[1.];f=Fixture();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None,clock=lambda:clock[0],orders_enabled=False);h.login()
    old=h.sender;attempts=[]
    def reject(m,p,headers,body):
        if m=='POST' and p=='/session':attempts.append(True);return 401,{'errorCode':'error.invalid.details'},{}
        return old(m,p,headers,body)
    h.sender=reject;clock[0]=542.
    with pytest.raises(CapitalError):h.request('GET','/accounts')
    with pytest.raises(CapitalError):h.request('GET','/accounts')
    assert len(attempts)==1 and not h.verified and not h.orders_enabled


@pytest.mark.parametrize('verified',[True,False])
def test_socket_failure_does_not_invent_authentication_failure(verified):
    from mnq_local.capital_app import stream_failure_status
    from types import SimpleNamespace
    b=SimpleNamespace(state={'halt':'kill'},http=SimpleNamespace(verified=verified))
    result=stream_failure_status(b,'stale_stream_reconnect','signals_only')
    assert result['authenticated'] is verified
    assert result['connection']=='RECONNECTING' and result['error']=='stale_stream_reconnect'
