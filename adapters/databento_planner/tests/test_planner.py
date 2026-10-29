"""Synthetic metadata/receipts only. Never network or production cache."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest
from databento_planner.planner import sessions, comparison, request_for, validate_conditions
from databento_planner.security import load_key, MetadataOnly, PlannerError
from databento_planner.cache import Identity, Cache, subtract
from databento_planner.gate import Approval, acquisition_digest, execute_approved

NOW='2026-10-25T20:00:00Z'

def test_calendar_actual_sessions():
    ss=sessions(NOW,60)
    assert len(ss)==60 and ss[0]['date']=='2026-07-31' and ss[-1]['date']=='2026-10-23'
    assert '2026-09-07' not in [x['date'] for x in ss]
    assert '2026-10-12' in [x['date'] for x in ss]
    assert ss[-20]['date']=='2026-09-28' and ss[-5]['date']=='2026-10-19'
    assert all(x['expected_minutes']==390 for x in ss)

def test_calendar_halfday_dst_and_open_session():
    assert sessions('2026-11-27T18:00:00Z',1)[0]['expected_minutes']==210
    assert sessions('2026-11-27T17:59:59Z',1)[0]['date']=='2026-11-25'
    assert sessions('2026-11-02T22:00:00Z',1)[0]['start'].startswith('2026-11-02T14:30')
    with pytest.raises(PlannerError): sessions('2026-10-25',1)

class Backend:
    def __init__(self): self.calls=[]
    def call(self,area,name,**kw):
        self.calls.append((area,name,kw))
        if name=='list_schemas': return ['ohlcv-1m']
        if name=='get_dataset_range': return {'schema':{'ohlcv-1m':{'start':'2020-01-01T00:00:00Z','end':'2026-10-25T00:00:00Z'}}}
        if name=='get_dataset_condition':
            import pandas as pd
            return [{'date':str(d.date()),'condition':'available','last_modified_date':'2026-10-24'} for d in pd.date_range(kw['start_date'],kw['end_date'])]
        if name=='resolve':
            if kw['stype_in']=='continuous':
                return {'result':{s:[{'s':str(100+i),'d0':kw['start_date'],'d1':kw['end_date']}] for i,s in enumerate(kw['symbols'])},'partial':[],'not_found':[]}
            return {'result':{s:[{'s':('MNQ' if s=='100' else 'MES')+'Z6','d0':kw['start_date'],'d1':kw['end_date']}] for s in kw['symbols']},'partial':[],'not_found':[]}
        return {'get_cost':0.000123,'get_record_count':390,'get_billable_size':21840}[name]

def test_comparison_real_partition_shape_no_tier2():
    b=Backend(); report=comparison(b,NOW)
    assert report['preflight_passed'] and len(report['partitions'])==120
    assert len([x for x in b.calls if x[1]=='get_cost'])==120
    assert report['scenarios']['5']['total_cost_usd']=='0.001230'
    assert report['scenarios']['1']['roots']['MNQ']['records']==390
    for _,name,kw in b.calls:
        if name in ('get_cost','get_record_count','get_billable_size'):
            assert kw['schema']=='ohlcv-1m' and kw['stype_in']=='raw_symbol'
            assert kw['start'][:10]==kw['end'][:10] and kw['end'].endswith('20:00:00Z')
    assert report['data_acquisition_calls']==0 and not report['download_authorized']
    assert report['tier2']['status']=='configured_only_not_quoted'

def test_mapping_partial_rejected():
    class Partial(Backend):
        def call(self,a,n,**kw):
            out=super().call(a,n,**kw)
            if n=='resolve': out['partial']=['MNQ.v.0']
            return out
    with pytest.raises(PlannerError,match='mapping'): comparison(Partial(),NOW)

@pytest.mark.parametrize('condition',['degraded','unavailable','unknown'])
def test_conditions_not_available(condition):
    with pytest.raises(PlannerError): validate_conditions([{'date':'2026-10-23','condition':condition}],['2026-10-23'])

def test_conditions_missing_duplicate():
    with pytest.raises(PlannerError): validate_conditions([],['2026-10-23'])
    with pytest.raises(PlannerError): validate_conditions([{'date':'2026-10-23','condition':'available'}]*2,['2026-10-23'])

@pytest.mark.parametrize('value',[True,float('nan'),float('inf'),-1,None])
def test_unknown_bad_cost_fails(value):
    class Bad(Backend):
        def call(self,a,n,**kw): return value if n=='get_cost' else super().call(a,n,**kw)
    with pytest.raises(PlannerError): comparison(Bad(),NOW)

def test_keychain_normalization_no_secret_leak():
    body='X'*29
    key,evidence=load_key(lambda: (body+'\n').encode(),{})
    assert key=='db-'+body and not evidence['stored_complete'] and evidence['used_complete']
    assert evidence['normalization_applied'] and body not in json.dumps(evidence)
    key,evidence=load_key(lambda: ('db-'+body+'\n').encode(),{})
    assert evidence['stored_complete'] and not evidence['normalization_applied']
    for bad in (body+' \n',body+'\n\n',body+'\t\n'):
        with pytest.raises(PlannerError): load_key(lambda: bad.encode(),{})

def test_network_denies_paid_before_any_transport():
    backend=MetadataOnly('db-'+'X'*29)
    for area,name in [('timeseries','get_range'),('batch','submit_job'),('metadata','list_publishers')]:
        with pytest.raises(PlannerError,match='endpoint_forbidden'): backend.call(area,name)
    assert backend.trace==[]

def identity(contract='MNQZ6',schema='ohlcv-1m'):
    return Identity('GLBX.MDP3',schema,'MNQ',contract,'100',1,'revision-unknown','normalizer-test','source-test')

def test_interval_union_exact_nanoseconds():
    assert subtract((1,100),[(1,20),(20,30),(50,80),(70,90)])==[(30,50),(90,100)]
    assert subtract((10,11),[(1,10)])==[(10,11)]
    assert subtract((10,11),[(11,20)])==[(10,11)]

def test_empty_cache_never_trusts_synthetic_or_partial(tmp_path):
    c=Cache(tmp_path)
    assert c.missing(identity(),(0,60_000_000_000))==[(0,60_000_000_000)]
    (tmp_path/'receipts'/'fake.json').write_text(json.dumps({'status':'synthetic','identity':identity().as_dict(),'start_ns':0,'end_ns':60_000_000_000}))
    assert c.missing(identity(),(0,60_000_000_000))==[(0,60_000_000_000)]

def test_cache_untrusted_registration_and_path_escape(tmp_path):
    c=Cache(tmp_path); f=tmp_path/'fake.dbn'; f.write_bytes(b'SYNTHETIC NOT DBN')
    with pytest.raises(PlannerError): c.register(f,identity(),(0,60_000_000_000),{'status':'complete'})
    link=tmp_path/'escape.dbn'; link.symlink_to('/etc/hosts')
    with pytest.raises(PlannerError): c.register(link,identity(),(0,60_000_000_000),{})

def job():
    return {'dataset':'GLBX.MDP3','schema':'ohlcv-1m','partitions':[{'identity':identity().as_dict(),'start_ns':60_000_000_000,'end_ns':120_000_000_000,'cost_usd':'0.0001','billable_bytes':100,'quote_expires_at':'2026-10-25T20:15:00Z'}],'quote_checked_at':NOW,'quote_expires_at':'2026-10-25T20:15:00Z'}

class FakePaid:
    def __init__(self,cost='0.0001'): self.cost=cost;self.calls=0
    def quote(self,part): return {'cost_usd':self.cost,'billable_bytes':100,'expires_at':'2026-10-25T20:15:00Z'}
    def acquire(self,part,path): self.calls+=1;path.write_bytes(b'TEST ONLY')

def test_gate_manual_even_zero_and_cap_and_replay(tmp_path):
    j=job();j['partitions'][0]['cost_usd']='0'; b=FakePaid('0');c=Cache(tmp_path/'cache')
    with pytest.raises(PlannerError): execute_approved(j,None,c,c.root/'jobs'/'job',b,now=NOW)
    a=Approval(acquisition_digest(j),'0','nonce-one')
    result=execute_approved(j,a,c,c.root/'jobs'/'job',b,now=NOW)
    assert b.calls==1 and result['status']=='downloaded_unvalidated'
    with pytest.raises(PlannerError): execute_approved(j,a,c,c.root/'jobs'/'job2',b,now=NOW)
    assert b.calls==1

def test_gate_fresh_price_each_partition_cumulative_cap(tmp_path):
    j=job();j['partitions']*=2; b=FakePaid('0.0002');c=Cache(tmp_path/'cache')
    a=Approval(acquisition_digest(j),'0.0002','cap-nonce')
    with pytest.raises(PlannerError): execute_approved(j,a,c,c.root/'jobs'/'job',b,now=NOW)
    assert b.calls<=1

def test_gate_stale_unknown_or_output_collision(tmp_path):
    j=job();b=FakePaid();c=Cache(tmp_path/'cache'); a=Approval(acquisition_digest(j),'1','unique')
    with pytest.raises(PlannerError): execute_approved(j,a,c,c.root/'jobs'/'exists',b,now='2026-10-25T20:16:00Z')
    (c.root/'jobs'/'exists').mkdir()
    with pytest.raises(PlannerError): execute_approved(j,a,c,c.root/'jobs'/'exists',b,now=NOW)
    assert b.calls==0

def synthetic_dbn(cache, ident=None, bounds=(60_000_000_000,120_000_000_000), bad_publisher=False):
    """SDK-encoded SYNTHETIC fixture in pytest temp only, never production cache."""
    import databento_dbn as dbn
    import databento as db
    from mnq_data.core import file_hash
    ident=ident or identity()
    path=cache.root/'objects'/'SYNTHETIC-fixture.dbn'
    meta=dbn.Metadata(dataset=ident.dataset,start=bounds[0],end=bounds[1],
        stype_in=db.SType.RAW_SYMBOL,stype_out=db.SType.INSTRUMENT_ID,
        schema=db.Schema.OHLCV_1M,symbols=[ident.contract])
    record=dbn.OHLCVMsg(rtype=dbn.RType.OHLCV_1M,publisher_id=2 if bad_publisher else ident.publisher_id,
        instrument_id=int(ident.instrument_id),ts_event=bounds[0],
        open=10**9,high=2*10**9,low=10**9,close=10**9,volume=5)
    path.write_bytes(meta.encode()+bytes(record))
    provenance={'status':'downloaded_unvalidated','source':'Databento Historical API',
        'synthetic':False,'request_complete':True,'sha256':file_hash(path),
        'request':{'dataset':ident.dataset,'schema':ident.schema,'symbols':[ident.contract],
            'stype_in':'raw_symbol','start_ns':bounds[0],'end_ns':bounds[1]}}
    # Deliberately exercises local integrity admission with synthetic bytes: no
    # cryptographic vendor authentication exists; all cache receipts say FALSE.
    return path,provenance


def test_cache_valid_sdk_structure_overlap_isolation_tamper(tmp_path):
    c=Cache(tmp_path); path,provenance=synthetic_dbn(c)
    receipt=c.register(path,identity(),(60_000_000_000,120_000_000_000),provenance)
    assert not receipt['vendor_authenticated'] and not receipt['research_ready']
    assert c.missing(identity(),(60_000_000_000,120_000_000_000))==[]
    assert c.missing(identity(),(0,300_000_000_000))==[(0,60_000_000_000),(120_000_000_000,300_000_000_000)]
    assert c.missing(identity('MNQU6'),(60_000_000_000,120_000_000_000))==[(60_000_000_000,120_000_000_000)]
    assert c.missing(identity(schema='ohlcv-1s'),(60_000_000_000,120_000_000_000))==[(60_000_000_000,120_000_000_000)]
    path.write_bytes(path.read_bytes()+b'TAMPER')
    with pytest.raises(PlannerError,match='quarantine'): c.missing(identity(),(0,300_000_000_000))


def test_cache_mismatched_publisher_and_partial_dbn(tmp_path):
    c=Cache(tmp_path);p,provenance=synthetic_dbn(c,bad_publisher=True)
    with pytest.raises(PlannerError): c.register(p,identity(),(60_000_000_000,120_000_000_000),provenance)
    (p.parent/'INCOMPLETE.json').write_text('{}')
    with pytest.raises(PlannerError): c.register(p,identity(),(60_000_000_000,120_000_000_000),provenance)


def test_gate_stale_fresh_quote_reflection_no_charged_retry(tmp_path):
    j=job();c=Cache(tmp_path/'cache'); a=Approval(acquisition_digest(j),'1','manual-nonce')
    class Broken(FakePaid):
        def acquire(self,part,path):
            self.calls+=1
            raise RuntimeError('db-'+'SECRET'*5)
    b=Broken()
    with pytest.raises(PlannerError) as e:
        execute_approved(j,a,c,c.root/'jobs'/'first',b,now=NOW,configured_cap='1')
    assert 'SECRET' not in str(e.value) and b.calls==1
    assert (c.root/'jobs'/'first'/'INCOMPLETE.json').exists()
    with pytest.raises(PlannerError): execute_approved(j,a,c,c.root/'jobs'/'retry',b,now=NOW,configured_cap='1')
    assert b.calls==1


def test_each_partition_refreshed_burn_before_first_call(tmp_path):
    j=job();j['partitions'].append({**j['partitions'][0],'start_ns':120_000_000_000,'end_ns':180_000_000_000})
    c=Cache(tmp_path/'cache');a=Approval(acquisition_digest(j),'0.0002','each-partition')
    class PerPartition(FakePaid):
        def __init__(self): super().__init__();self.quoted=0
        def quote(self,p):
            self.quoted+=1
            result=super().quote(p)
            if self.quoted==2: result['expires_at']='2026-10-25T19:59:59Z'
            return result
    b=PerPartition()
    with pytest.raises(PlannerError): execute_approved(j,a,c,c.root/'jobs'/'multi',b,now=NOW,configured_cap='0.0002')
    assert b.quoted==2 and b.calls==1
    assert len(list((c.root/'nonces').glob('*.json')))==1


def test_all_cache_hits_zero_network_without_approval(tmp_path):
    c=Cache(tmp_path);p,prov=synthetic_dbn(c)
    c.register(p,identity(),(60_000_000_000,120_000_000_000),prov)
    b=FakePaid()
    result=execute_approved(job(),None,c,c.root/'jobs'/'noop',b,now=NOW)
    assert result['status']=='all_cache_hits' and b.calls==0
    assert not (c.root/'jobs'/'noop').exists()


def test_cache_lock_serializes_process_reservations(tmp_path):
    import multiprocessing as mp
    import time
    c=Cache(tmp_path)
    ctx=mp.get_context('fork');entered=ctx.Event();finished=ctx.Event()
    def worker():
        other=Cache(tmp_path)
        entered.set()
        with other.lock(): finished.set()
    with c.lock():
        process=ctx.Process(target=worker);process.start()
        assert entered.wait(3)
        assert not finished.wait(.15)
    assert finished.wait(3)
    process.join(3);assert process.exitcode==0


def test_sdk_actual_request_transport_shape_offline(monkeypatch):
    import requests
    from requests.auth import HTTPBasicAuth
    key='db-'+'X'*29
    b=MetadataOnly(key)
    seen=[]
    def request(method,url,**kw):
        seen.append((method,url,kw))
        response=requests.Response();response.status_code=200;response._content=b'0.0001';response._content_consumed=True;return response
    monkeypatch.setattr(b._session,'request',request)
    s=sessions(NOW,1)[0]
    req={'dataset':'GLBX.MDP3','schema':'ohlcv-1m','symbols':['MNQZ6'],'stype_in':'raw_symbol','start':s['start'],'end':s['end']}
    assert b.call('metadata','get_cost',**req)==0.0001
    method,url,kw=seen[0]
    assert method=='POST' and url=='https://hist.databento.com/v0/metadata.get_cost'
    assert kw['data']['start']==s['start'] and kw['data']['end']==s['end']
    from mnq_data.core import utc
    assert utc(kw['data']['start']).value==s['start_ns'] and utc(kw['data']['end']).value==s['end_ns']
    assert kw['data']['symbols']=='MNQZ6' and kw['data']['stype_in']=='raw_symbol'
    assert isinstance(kw['auth'],HTTPBasicAuth) and kw['auth'].username==key and kw['auth'].password==''
    assert kw['verify'] is True and kw['allow_redirects'] is False
    assert key not in json.dumps(b.trace)


def test_mapping_changes_on_actual_day_and_boundary():
    s=sessions(NOW,1)[0]
    mapping={'intervals':[
        {'root':'MNQ','contract':'MNQU6','instrument_id':'10','start_date':'2026-09-01','end_date':'2026-10-23'},
        {'root':'MNQ','contract':'MNQZ6','instrument_id':'20','start_date':'2026-10-23','end_date':'2026-12-01'}]}
    request,item=request_for(s,'MNQ',mapping)
    assert item['instrument_id']=='20' and request['symbols']==['MNQZ6']
    for field in ('start','end'):
        bad={**s,field:s[field].replace('00Z','00.000000001Z')}
        with pytest.raises(Exception): request_for(bad,'MNQ',mapping)


def test_public_cli_no_paid_operation(capsys):
    from databento_planner.cli import main
    with pytest.raises(SystemExit): main(['acquire'])
    captured=capsys.readouterr()
    assert 'invalid choice' in captured.err

def test_completed_unvalidated_lease_blocks_overlapping_new_job(tmp_path):
    c=Cache(tmp_path/'cache');j=job();b=FakePaid()
    a=Approval(acquisition_digest(j),'1','first-manual')
    execute_approved(j,a,c,c.root/'jobs'/'first',b,now=NOW,configured_cap='1')
    other=job();other['partitions'][0]['end_ns']=180_000_000_000
    new=Approval(acquisition_digest(other),'1','second-manual')
    with pytest.raises(PlannerError,match='lease'):
        execute_approved(other,new,c,c.root/'jobs'/'second',b,now=NOW,configured_cap='1')
    assert b.calls==1

def test_fresh_backend_cannot_mutate_approved_scope(tmp_path):
    c=Cache(tmp_path/'cache');j=job();a=Approval(acquisition_digest(j),'1','scope-mutation')
    class Mutating(FakePaid):
        def quote(self,p):
            p['end_ns']+=60_000_000_000
            return super().quote(p)
    b=Mutating()
    with pytest.raises(PlannerError): execute_approved(j,a,c,c.root/'jobs'/'mutated',b,now=NOW,configured_cap='1')
    assert b.calls==0
