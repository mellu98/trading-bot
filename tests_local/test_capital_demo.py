"""Fixture/contract tests only: never reported as authenticated broker tests."""
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from mnq_local.capital import BASE, STREAM, CapitalHTTP, CapitalError, Credentials, CapitalConfig, Quote, CapitalBroker, CFDInstrument, dec

CREDS=Credentials('fixture-key','fixture@example.invalid','fixture-password','DEMO1')

class Fixture:
    def __init__(self):self.calls=[];self.positions=[];self.fail_write=False;self.confirm=False
    def __call__(self,method,path,headers,body):
        self.calls.append((method,path,body))
        if path=='/session' and method=='POST':return 200,{'currentAccountId':'DEMO1','hasActiveDemoAccounts':True,'streamingHost':STREAM.rsplit('/connect',1)[0]+'/'},{'cst':'fixture-cst','x-security-token':'fixture-security'}
        if path=='/session':return 200,{'accountId':'DEMO1','currency':'USD'},{}
        if path=='/accounts':return 200,{'accounts':[{'accountId':'DEMO1','status':'ENABLED','accountType':'CFD','currency':'USD','balance':{'balance':10000,'available':10000,'profitLoss':0}}]},{}
        if path=='/accounts/preferences':return 200,{'hedgingMode':True},{}
        if path=='/positions' and method=='POST':
            if self.fail_write:raise CapitalError('transport_unknown')
            return 200,{'dealReference':'ref1'},{}
        if path.startswith('/confirms/'):
            return 200,{'dealStatus':'ACCEPTED','dealReference':'ref1','dealId':'deal1','status':'OPEN','epic':'EPIC1','affectedDeals':[{'dealId':'deal1','status':'OPENED'}]},{}
        if path=='/positions':return 200,{'positions':self.positions},{}
        if path=='/workingorders':return 200,{'workingOrders':[]},{}
        return 200,{},{}

def instrument_fixture():
    return CFDInstrument.from_api({"instrument":{"epic":"EPIC1","name":"US Tech 100","type":"INDICES","currency":"USD","marginFactor":5,"marginFactorUnit":"PERCENTAGE","openingHours":{"zone":"UTC","mon":["00:00 - 23:59"]},"streamingPricesAvailable":True},"dealingRules":{k:{"unit":"POINTS","value":v} for k,v in [("minDealSize",1),("maxDealSize",10),("minSizeIncrement",1)]},"snapshot":{"delayTime":0,"streamingPricesAvailable":True,"marketStatus":"TRADEABLE"}})

def make(tmp_path):
    f=Fixture();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None);h.login()
    from mnq_local.capital import CapitalJournal
    config=CapitalConfig('DEMO1',mode='technical_test')
    j=CapitalJournal(tmp_path/'journal.sqlite',config)
    b=CapitalBroker(h,j,config);b.reconcile()
    return f,h,j,b

@pytest.mark.parametrize('base',['https://api-capital.backend-capital.com','http://demo-api-capital.backend-capital.com',BASE+'/',BASE+'@evil.invalid'])
def test_production_and_custom_origins_rejected(base):
    with pytest.raises(ValueError):CapitalHTTP(CREDS,base=base)

def test_credentials_redacted():
    assert 'fixture-password' not in repr(CREDS) and 'fixture-key' not in repr(CREDS)

def test_auth_verifies_exact_demo_account_and_session(tmp_path):
    f,h,j,b=make(tmp_path)
    try:
        assert h.verified and b.ready
        h.credentials=Credentials('fixture-key','fixture@example.invalid','fixture-password','OTHER')
        with pytest.raises(CapitalError):h.login()
        assert not h.verified
    finally:j.close()

def test_quote_preserves_unix_ms_and_rejects_stale_future_and_crossed():
    now=datetime(2026,10,26,14,0,tzinfo=timezone.utc)
    payload={'epic':'EPIC1','product':'CFD','bid':100.,'ofr':100.5,'timestamp':1793023200123}
    at=datetime.fromtimestamp(payload['timestamp']/1000,timezone.utc)
    q=Quote.parse(payload,at)
    assert q.timestamp_ms==payload['timestamp'] and q.spread==Decimal('.5')
    for change,received in [({'ofr':99.},at),({},at.replace(minute=1)),({},now)]:
        with pytest.raises(ValueError):Quote.parse({**payload,**change},received)

def test_nonallowlisted_routes_cannot_mutate_settings():
    h=CapitalHTTP(CREDS,sender=Fixture(),sleep=lambda _:None)
    for method,path in [('POST','/accounts/topUp'),('PUT','/session'),('GET','https://evil.invalid'),('PUT','/accounts/preferences')]:
        with pytest.raises(ValueError):h.request(method,path)

def test_unknown_submit_survives_restart_and_is_never_retried(tmp_path):
    f,h,j,b=make(tmp_path)
    f.fail_write=True
    try:
        b.instruments['EPIC1']=instrument_fixture()
        with pytest.raises(CapitalError):b.place('intent1','EPIC1','BUY',Decimal('1'),Decimal('2'),Decimal('4'))
        assert j.cap['intents']['intent1']['state']=='UNKNOWN'
        with pytest.raises(CapitalError):b.place('intent1','EPIC1','BUY',Decimal('1'),Decimal('2'),Decimal('4'))
        assert sum(m=='POST' and p=='/positions' for m,p,_ in f.calls)==1
    finally:j.close()
    from mnq_local.capital import CapitalJournal
    j=CapitalJournal(tmp_path/'journal.sqlite',CapitalConfig('DEMO1',mode='technical_test'))
    try:assert j.cap['intents']['intent1']['state']=='UNKNOWN'
    finally:j.close()

def test_acknowledgement_is_not_a_fill(tmp_path):
    f,h,j,b=make(tmp_path)
    try:
        b.instruments['EPIC1']=instrument_fixture()
        b.place('intent1','EPIC1','BUY',Decimal('1'),Decimal('2'),Decimal('4'))
        assert j.cap['intents']['intent1']['state']=='ACKNOWLEDGED'
        assert not j.cap['fills']
        b.reconcile()
        assert j.cap['intents']['intent1']['state']!='FILLED'
        assert not j.cap['fills']
    finally:j.close()

def test_residual_foreign_positions_block_entries(tmp_path):
    f,h,j,b=make(tmp_path)
    try:
        f.positions=[{'position':{'dealId':'foreign','size':1},'market':{'epic':'EPIC1'}}]
        b.reconcile()
        assert not b.ready and j.cap['halt']=='foreign_or_residual_position'
    finally:j.close()

class Lifecycle(Fixture):
    def __call__(self,method,path,headers,body):
        if method=='POST' and path=='/positions':
            self.calls.append((method,path,body))
            self.positions=[{'position':{'dealId':'deal1','size':body['size'],'direction':body['direction'],
                'level':100,'stopLevel':98,'profitLevel':104,'currency':'USD'},'market':{'epic':body['epic']}}]
            return 200,{'dealReference':'opened'},{}
        if method=='DELETE' and path=='/positions/deal1':
            self.calls.append((method,path,body));self.positions=[]
            return 200,{'dealReference':'closed'},{}
        if path=='/confirms/opened':return 200,{'dealReference':'opened','dealStatus':'ACCEPTED','dealId':'deal1','status':'OPEN','affectedDeals':[{'dealId':'deal1','status':'OPENED'}]},{}
        if path=='/confirms/closed':return 200,{'dealReference':'closed','dealStatus':'ACCEPTED','dealId':'deal1','status':'CLOSED','affectedDeals':[{'dealId':'deal1','status':'DELETED'}]},{}
        return super().__call__(method,path,headers,body)


def test_confirmed_lifecycle_no_duplicate_fills_or_close(tmp_path):
    from mnq_local.capital import CapitalJournal
    f=Lifecycle();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None);h.login()
    cfg=CapitalConfig('DEMO1',mode='technical_test');j=CapitalJournal(tmp_path/'j.sqlite',cfg);b=CapitalBroker(h,j,cfg)
    try:
        b.reconcile();b.instruments['EPIC1']=instrument_fixture()
        b.place('entry','EPIC1','BUY',dec('1'),dec('2'),dec('4'))
        assert not j.cap['fills']
        b.reconcile();b.reconcile()
        assert j.cap['intents']['entry']['state']=='FILLED' and len(j.cap['fills'])==1
        b.close_position('close','deal1');b.reconcile()
        assert j.cap['intents']['close']['state']=='CONFIRMED_CLOSED'
        with pytest.raises(CapitalError):b.close_position('close','deal1')
    finally:j.close()


def test_missing_or_wrong_way_brackets_and_partial_fill_block(tmp_path):
    f,h,j,b=make(tmp_path)
    try:
        b.instruments['EPIC1']=instrument_fixture();b.place('entry','EPIC1','BUY',dec('1'),dec('2'),dec('4'))
        for change in ({'size':.5},{'stopLevel':None},{'stopLevel':102}):
            f.positions=[{'position':{'dealId':'deal1','size':1,'direction':'BUY','level':100,'stopLevel':98,'profitLevel':104,**change},'market':{'epic':'EPIC1'}}]
            j.cap['halt']=None;b.reconcile();assert j.cap['halt'] is not None
    finally:j.close()


def test_daily_loss_latches_and_no_order_after_restart(tmp_path):
    f,h,j,b=make(tmp_path)
    try:
        j.cap['initial_balance']=10000;j.cap['day_baseline']=10000
        original=f.__call__
        def losses(method,path,headers,body):
            code,value,heads=original(method,path,headers,body)
            if path=='/accounts':value['accounts'][0]['balance']['balance']=9970
            return code,value,heads
        h.sender=losses;b.reconcile();assert not b.ready and j.cap['halt']=='daily_max_loss'
    finally:j.close()


def test_kill_switch_is_persistent(tmp_path):
    f,h,j,b=make(tmp_path)
    try:
        b.flatten();assert j.cap['halt']=='kill'
        b.reconcile();assert not b.ready
    finally:j.close()


def test_no_order_in_signals_or_strict_mode(tmp_path):
    from mnq_local.capital import CapitalJournal
    for mode in ('signals_only','strict_demo'):
        f=Fixture();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None);h.login()
        cfg=CapitalConfig('DEMO1',mode=mode);j=CapitalJournal(tmp_path/(mode+'.sqlite'),cfg)
        try:
            b=CapitalBroker(h,j,cfg);b.reconcile();b.instruments['EPIC1']=instrument_fixture()
            with pytest.raises(CapitalError):b.place('entry','EPIC1','BUY',dec('1'),dec('2'),dec('4'))
            assert not any(m=='POST' and p=='/positions' for m,p,_ in f.calls)
        finally:j.close()


def test_root_confirmation_order_id_is_not_the_affected_position_id(tmp_path):
    f,h,j,b=make(tmp_path)
    try:
        b.instruments['EPIC1']=instrument_fixture();b.place('entry','EPIC1','BUY',dec('1'),dec('2'),dec('4'))
        f.positions=[{'position':{'dealId':'actual-position','size':1,'direction':'BUY','level':100,'stopLevel':98,'profitLevel':104},'market':{'epic':'EPIC1'}}]
        original=f.__call__
        def affected(method,path,headers,body):
            if path.startswith('/confirms/'):return 200,{'dealStatus':'ACCEPTED','dealReference':'ref1','dealId':'order-not-position','affectedDeals':[{'dealId':'actual-position','status':'OPENED'}]},{}
            return original(method,path,headers,body)
        h.sender=affected;b.reconcile()
        assert j.cap['intents']['entry']['deal_id']=='actual-position'
        assert j.cap['intents']['entry']['state']=='FILLED'
    finally:j.close()


def test_native_limit_order_cancellation_and_reconcile(tmp_path):
    f,h,j,b=make(tmp_path);orders=[]
    original=f.__call__
    def pending(method,path,headers,body):
        if method=='POST' and path=='/workingorders':
            orders.append({'workingOrderData':{'dealId':'limit1','epic':'EPIC1'}})
            return 200,{'dealReference':'limitref'},{}
        if path=='/workingorders' and method=='GET':return 200,{'workingOrders':orders},{}
        if path=='/workingorders/limit1' and method=='DELETE':
            orders.clear();return 200,{'dealReference':'cancelref'},{}
        if path in ('/confirms/limitref','/confirms/cancelref'):
            return 200,{'dealStatus':'ACCEPTED','dealReference':path.split('/')[-1],'dealId':'limit1','affectedDeals':[]},{}
        return original(method,path,headers,body)
    h.sender=pending
    try:
        b.instruments['EPIC1']=instrument_fixture()
        b.place('limit','EPIC1','BUY',dec('1'),dec('2'),dec('4'),limit_level=dec('90'))
        b.reconcile();assert j.cap['intents']['limit']['state']=='WORKING'
        b.cancel('cancel','limit1');b.reconcile();b.reconcile()
        assert j.cap['intents']['cancel']['state']=='CONFIRMED_CANCELLED'
        assert j.cap['intents']['limit']['state']=='CANCELLED'
        assert not j.cap['fills']
    finally:j.close()


def test_actual_process_crash_after_intent_persists_unknown(tmp_path):
    import subprocess,sys,time,os
    from pathlib import Path
    marker=tmp_path/'posting'
    code='''from test_capital_demo import make,instrument_fixture
from mnq_local.capital import dec
from pathlib import Path
import sys,time
root=Path(sys.argv[1]);f,h,j,b=make(root);b.instruments['EPIC1']=instrument_fixture()
original=h.sender
def blocked(method,path,headers,body):
    if method=='POST' and path=='/positions':
        (root/'posting').write_text('intent_already_committed')
        time.sleep(60)
    return original(method,path,headers,body)
h.sender=blocked
b.place('crash-intent','EPIC1','BUY',dec('1'),dec('2'),dec('4'))
'''
    env={**os.environ,'PYTHONPATH':os.environ.get('PYTHONPATH','')+':'+str(Path(__file__).parent.resolve())}
    process=subprocess.Popen([sys.executable,'-c',code,str(tmp_path)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not marker.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.03)
        assert marker.exists()
        process.kill();process.wait(timeout=5)
        from mnq_local.capital import CapitalJournal
        j=CapitalJournal(tmp_path/'journal.sqlite',CapitalConfig('DEMO1',mode='technical_test'))
        try:assert j.cap['intents']['crash-intent']['state']=='UNKNOWN'
        finally:j.close()
    finally:
        if process.poll() is None:process.kill();process.wait()
