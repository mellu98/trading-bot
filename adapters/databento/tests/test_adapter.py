import copy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import warnings
import pytest
from mnq_data.core import Plan, Adapter, SafeError, digest, iso, utc, safe_call

NOW = datetime(2026, 10, 25, tzinfo=timezone.utc)

class Fake:
    def __init__(self): self.calls = []; self.cost = .01
    def call(self, area, name, **kw):
        self.calls.append((area, name, kw))
        if name == 'list_schemas': return ['ohlcv-1m', 'ohlcv-1s', 'trades', 'mbp-1']
        if name == 'get_dataset_range':
            return {'start':'2010-01-01T00:00:00Z','end':'2026-10-25T00:00:00Z', 'schema':{s:{'start':'2010-01-01T00:00:00Z','end':'2026-10-25T00:00:00Z'} for s in ['ohlcv-1m','ohlcv-1s','trades','mbp-1']}}
        if name == 'get_dataset_condition': return [{'date':'2026-10-23','condition':'available'}]
        if name == 'resolve':
            if kw['stype_in'] == 'continuous':
                return {'result':{s:[{'d0':'2026-01-01','d1':'2027-01-01','s':str(100+i)}] for i,s in enumerate(kw['symbols'])},'partial':[],'not_found':[]}
            return {'result':{s:[{'d0':'2026-01-01','d1':'2027-01-01','s':('MNQZ6' if s=='100' else 'MESZ6')}] for s in kw['symbols']}, 'partial':[],'not_found':[]}
        if name == 'get_cost': return self.cost
        if name == 'get_record_count': return 10
        if name == 'get_billable_size': return 1024
        if name == 'get_range': Path(kw['path']).write_bytes(b'fake-dbn'); return None
        raise AssertionError(name)

@pytest.fixture
def plan(): return Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z')

@pytest.mark.parametrize('start,end', [('2026-10-23','2026-10-24'),('2026-10-24T00:00:00','2026-10-25T00:00:00Z'),('2026-10-25T00:00:00Z','2026-10-24T00:00:00Z'),('2999-01-01T00:00:00Z','2999-01-02T00:00:00Z')])
def test_invalid_intervals(start,end):
    with pytest.raises(SafeError): Plan(start,end)

def test_metadata_only_preflight_and_exact_cost(plan):
    f=Fake(); r=Adapter(f, now=lambda:NOW).preflight(plan)
    assert r['status']=='verified_metadata' and r['total_estimated_cost_usd']==pytest.approx(.08)
    assert r['download_authorized'] is False and r['actual_data_quality']=='not_acquired'
    assert r['request_sha256']==digest(plan.as_dict())
    assert {x['schema'] for x in r['quotes']}==set(plan.schemas)
    assert all(a!='timeseries' for a,n,k in f.calls)
    assert all(k['stype_out']=='instrument_id' for a,n,k in f.calls if n=='resolve' and k['stype_in']=='continuous')
    assert next(x for x in r['mappings']['volume']['intervals'] if x['root']=='MNQ')['contract']=='MNQZ6'
    assert all(x['records'] == 10 for x in r['quotes'])
    assert r['historical_product_first_record']=='not_verified'

@pytest.mark.parametrize('cost',[float('nan'),float('inf'),-1,True])
def test_invalid_cost_fails_closed(plan,cost):
    f=Fake(); f.cost=cost
    with pytest.raises(SafeError): Adapter(f,now=lambda:NOW).preflight(plan)

def test_no_paid_call_without_exact_approval_even_zero(plan,tmp_path):
    f=Fake(); f.cost=0; a=Adapter(f,now=lambda:NOW); r=a.preflight(plan)
    for approval in [None, 'wrong']:
        with pytest.raises(SafeError): a.download(r,tmp_path/'job',approval,0)
    assert not any(n=='get_range' for _,n,_ in f.calls)

def test_quote_tampering_stale_and_cap(plan,tmp_path):
    f=Fake(); a=Adapter(f,now=lambda:NOW); r=a.preflight(plan)
    tampered=copy.deepcopy(r); tampered['plan']['start']='2026-10-22T13:30:00Z'
    with pytest.raises(SafeError): a.download(tampered,tmp_path/'bad',r['request_sha256'],1)
    with pytest.raises(SafeError): Adapter(f,now=lambda:NOW+timedelta(hours=2)).download(r,tmp_path/'old',r['request_sha256'],1)
    with pytest.raises(SafeError): a.download(r,tmp_path/'cap',r['request_sha256'],.001)
    assert not any(n=='get_range' for _,n,_ in f.calls)

def test_existing_destination_rejected_before_paid(plan,tmp_path):
    f=Fake(); a=Adapter(f,now=lambda:NOW); r=a.preflight(plan)
    p=tmp_path/'job'; p.mkdir()
    with pytest.raises(SafeError): a.download(r,p,r['request_sha256'],1)
    assert not any(n=='get_range' for _,n,_ in f.calls)

def test_approved_download_requotes_and_records_provenance(plan,tmp_path):
    f=Fake(); a=Adapter(f,now=lambda:NOW); r=a.preflight(plan)
    out=a.download(r,tmp_path/'job',r['request_sha256'],1)
    assert out['status']=='downloaded_unvalidated' and len(out['files'])==8
    assert all(Path(tmp_path/'job'/x['path']).exists() for x in out['files'])
    assert not out['research_ready']

def test_download_failure_no_retry_quarantine(plan,tmp_path):
    f=Fake(); original=f.call
    def fail(area,name,**kw):
        if name=='get_range':
            f.calls.append((area,name,kw)); raise RuntimeError('secret-key-never-display')
        return original(area,name,**kw)
    f.call=fail; a=Adapter(f,now=lambda:NOW); r=a.preflight(plan)
    with pytest.raises(SafeError,match='download_failed') as e: a.download(r,tmp_path/'job',r['request_sha256'],1)
    assert 'secret' not in str(e.value)
    assert len([n for _,n,_ in f.calls if n=='get_range'])==1
    assert (tmp_path/'job'/'INCOMPLETE.json').exists()

def test_safe_call_hides_backend_exception_and_warning(capsys):
    def failure():
        warnings.warn('secret-key'); print('secret-key'); raise RuntimeError('secret-key')
    with pytest.raises(SafeError) as e: safe_call(failure)
    assert 'secret' not in str(e.value)
    assert 'secret' not in ''.join(capsys.readouterr())

from mnq_data.local import normalize_rows, stage_abc

MAP=[{'root':'MNQ','contract':'MNQZ6','instrument_id':'100','start_date':'2026-10-01','end_date':'2027-01-01'}]
NS=int(datetime(2026,10,23,13,30,tzinfo=timezone.utc).timestamp())*10**9

def bar(**kw):
    return dict(publisher_id=1,ts_event=NS,instrument_id=100,open=20000*10**9,high=20001*10**9,low=19999*10**9,close=20000*10**9,volume=10,**kw)

def test_bar_start_and_ns_precision(tmp_path):
    rows,q=normalize_rows('ohlcv-1m',[bar()],MAP)
    assert rows[0]['ts_event_ns']==str(NS) and rows[0]['end_ns']==str(NS+60*10**9)
    assert rows[0]['open']=='20000' and q['invalid_records']==0
    with pytest.raises(SafeError,match='latency'): stage_abc(rows,tmp_path/'a',None)
    m=stage_abc(rows,tmp_path/'b',5)
    assert m['attested_verified'] is False and m['research_ready'] is False
    assert 'calendar' in ' '.join(m['missing_prerequisites'])
    assert '2026-10-23T13:31:00.005000Z' in (tmp_path/'b'/'bars.csv').read_text()

@pytest.mark.parametrize('field,value',[('volume',-1),('volume',0),('open',9223372036854775807),('close',float('nan')),('close',20000000000001)])
def test_bad_bar_rejected(field,value):
    b=bar(); b[field]=value
    rows,q=normalize_rows('ohlcv-1m',[b],MAP)
    assert not rows and q['invalid_records']==1

def test_gap_unknown_not_filled_and_out_of_order_exchange_allowed():
    b=bar(); b['ts_event']+=120*10**9
    rows,q=normalize_rows('ohlcv-1m',[bar(),b],MAP)
    assert len(rows)==2 and q['gaps'][0]['classification']=='unknown_no_trade_or_closure_or_loss'
    ticks=[dict(publisher_id=1,ts_recv=NS+i,ts_event=NS+10-i,instrument_id=100,price=20000*10**9,size=2,sequence=i,action='T') for i in range(2)]
    rows,q=normalize_rows('trades',ticks,MAP)
    assert len(rows)==2 and q['exchange_clock_regressions']==1 and q['invalid_records']==0

def test_mbp_quotes_sentinel_and_book_size_not_volume():
    t=dict(publisher_id=1,ts_recv=NS+123,ts_event=NS+1,instrument_id=100,price=9223372036854775807,size=3,sequence=1,action='A',flags=12,bid_px_00=9223372036854775807,ask_px_00=20000*10**9,bid_sz_00=8,ask_sz_00=9)
    rows,q=normalize_rows('mbp-1',[t],MAP)
    assert rows[0]['bid_px_00'] is None and 'volume' not in rows[0]
    assert rows[0]['ts_recv_ns']==str(NS+123) and q['suspect_timestamp_flags']==1 and q['suspect_book_flags']==1

def test_mapping_unknown_and_duplicate_minute_fail():
    rows,q=normalize_rows('ohlcv-1m',[{**bar(),'instrument_id':999}],MAP)
    assert not rows and q['invalid_records']==1
    rows,q=normalize_rows('ohlcv-1m',[bar(),bar()],MAP)
    assert q['invalid_records']==1
