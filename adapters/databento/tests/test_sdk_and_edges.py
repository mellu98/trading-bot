"""Real pinned SDK serialization, offline boundary tests; never contact the network."""
import copy
import inspect
import json
import os
from datetime import timedelta
from pathlib import Path
import pytest
import databento as db
import databento_dbn as dbn
from mnq_data.core import Adapter, Plan, SafeError, SDKBackend, dump, file_hash, safe_call
from mnq_data.local import normalize_job, normalize_rows, ns_iso
from test_adapter import Fake, NOW, NS, MAP, bar

@pytest.mark.parametrize('schema',['ohlcv-1m','ohlcv-1s','trades','mbp-1'])
def test_genuine_dbn_sdk_normalization(schema,tmp_path):
    metadata=dbn.Metadata(dataset='GLBX.MDP3',start=NS,end=NS+60*10**9,stype_in=dbn.SType.CONTINUOUS,stype_out=dbn.SType.INSTRUMENT_ID,schema=dbn.Schema(schema),symbols=['MNQ.v.0'])
    if schema.startswith('ohlcv'):
        record=dbn.OHLCVMsg(rtype=getattr(dbn.RType,schema.upper().replace("-","_")),publisher_id=1,instrument_id=100,ts_event=NS,open=20000*10**9,high=20001*10**9,low=19999*10**9,close=20000*10**9,volume=10)
    elif schema=='trades':
        record=dbn.TradeMsg(publisher_id=1,instrument_id=100,ts_event=NS+123,price=20000*10**9,size=2,action=dbn.Action.TRADE,side=dbn.Side.BID,depth=0,ts_recv=NS+987,sequence=1)
    else:
        record=dbn.MBP1Msg(publisher_id=1,instrument_id=100,ts_event=NS+123,price=20000*10**9,size=2,action=dbn.Action.ADD,side=dbn.Side.BID,depth=0,ts_recv=NS+987,sequence=1,levels=dbn.BidAskPair(bid_px=20000*10**9,ask_px=20001*10**9,bid_sz=8,ask_sz=9,bid_ct=1,ask_ct=1))
    job=tmp_path/'job'; job.mkdir(); raw=job/'raw.dbn'; raw.write_bytes(bytes(metadata)+bytes(record))
    provenance={'status':'downloaded_unvalidated','dataset':'GLBX.MDP3','mappings':{'intervals':MAP},'files':[{'path':'raw.dbn','schema':schema,'root':'MNQ','sha256':file_hash(raw),'request':Plan('2026-10-23T13:30:00Z','2026-10-23T13:31:00Z').request('MNQ',schema)}]}
    dump(job/'provenance.json',provenance)
    result=normalize_job(job,tmp_path/'normalized',5)
    assert result['status']=='structural_checks_only'
    p=result['partitions'][0]
    assert p['valid_records']==1 and p['invalid_records']==0
    rows=[json.loads(s) for s in (tmp_path/'normalized'/p['normalized_file']).read_text().splitlines()]
    if schema in ('trades','mbp-1'): assert rows[0]['ts_recv_ns']==str(NS+987)
    if schema=='mbp-1': assert rows[0]['bid_sz_00']==8 and 'volume' not in rows[0]
    if schema=='ohlcv-1m':
        assert not json.loads((tmp_path/'normalized'/'abc-staging'/'manifest.staging.json').read_text())['attested_verified']

def test_pinned_sdk_signatures():
    from importlib.metadata import version
    from databento.historical.api.metadata import MetadataHttpAPI
    from databento.historical.api.symbology import SymbologyHttpAPI
    from databento.historical.api.timeseries import TimeseriesHttpAPI
    assert version('databento')=='0.88.0'
    for method in ('get_cost','get_record_count','get_billable_size'):
        params=inspect.signature(getattr(MetadataHttpAPI,method)).parameters
        assert {'dataset','symbols','stype_in','schema','start','end'}<=set(params)
    assert 'path' in inspect.signature(TimeseriesHttpAPI.get_range).parameters
    assert {'stype_in','stype_out','start_date','end_date'}<=set(inspect.signature(SymbologyHttpAPI.resolve).parameters)

def test_environment_key_required_no_client_created(monkeypatch):
    monkeypatch.delenv('DATABENTO_API_KEY',raising=False)
    with pytest.raises(SafeError,match='missing_DATABENTO_API_KEY'): SDKBackend()

def test_auth_failure_redacted(monkeypatch,capsys):
    class AuthError(Exception): http_status=401
    def fail(*a,**kw): raise AuthError('credential-revealing-message')
    monkeypatch.setenv('DATABENTO_API_KEY','test-secret-only')
    monkeypatch.setattr(db,'Historical',fail)
    with pytest.raises(SafeError,match='authentication_failed') as e: SDKBackend()
    assert 'credential' not in str(e.value) and not ''.join(capsys.readouterr())

def test_two_stage_intersection_and_rollover():
    class Rolling(Fake):
        def call(self,area,name,**kw):
            if name=='resolve':
                if kw['stype_in']=='continuous': return {'result':{'MNQ.v.0':[{'d0':'2026-09-01','d1':'2026-09-11','s':'101'},{'d0':'2026-09-11','d1':'2026-10-01','s':'102'}]}}
                return {'result':{'101':[{'d0':'2026-08-01','d1':'2026-09-12','s':'MNQU6'}],'102':[{'d0':'2026-09-01','d1':'2027-01-01','s':'MNQZ6'}]}}
            return super().call(area,name,**kw)
    r=Adapter(Rolling()).resolve(['MNQ'],'2026-09-02','2026-09-30')
    assert r['intervals'][0]['start_date']=='2026-09-02'
    assert r['intervals'][0]['end_date']=='2026-09-11'
    assert r['intervals'][1]['start_date']=='2026-09-11'
    assert r['rollovers'][0]['to']=='MNQZ6'

@pytest.mark.parametrize('failure',['partial','not_found','raw_partial','rejected','overlap'])
def test_incomplete_mapping_never_approved(failure):
    p=Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z',roots=('MNQ',))
    mapping={'intervals':copy.deepcopy(MAP),'partial':[],'not_found':[],'raw_partial':[],'raw_not_found':[],'rejected':[]}
    if failure=='overlap': mapping['intervals']*=2
    else: mapping[failure]=['MNQ']
    assert not Adapter.mapping_complete(mapping,p)

def test_requote_cost_increase_prevents_any_data_call(tmp_path):
    p=Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z'); f=Fake(); a=Adapter(f,now=lambda:NOW); report=a.preflight(p)
    f.cost=5
    with pytest.raises(SafeError): a.download(report,tmp_path/'job',report['request_sha256'],1)
    assert not any(n=='get_range' for _,n,_ in f.calls)
    assert (tmp_path/'job'/'INCOMPLETE.json').exists()

@pytest.mark.parametrize('cap',[float('nan'),float('inf'),-1,True])
def test_bad_cap_no_data(cap,tmp_path):
    p=Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z'); f=Fake(); a=Adapter(f,now=lambda:NOW); report=a.preflight(p)
    with pytest.raises(SafeError): a.download(report,tmp_path/'job',report['request_sha256'],cap)
    assert not any(n=='get_range' for _,n,_ in f.calls)

def test_request_clock_bounds_and_precision():
    req=Plan('2026-10-23T13:30:00Z','2026-10-23T13:31:00Z').request('MNQ','trades')
    record=dict(publisher_id=1,ts_recv=NS+1,ts_event=NS-500,instrument_id=100,price=20000*10**9,size=2,action='T')
    rows,q=normalize_rows('trades',[record],MAP,req)
    assert len(rows)==1 and rows[0]['ts_event_ns']==str(NS-500)
    record['ts_recv']=NS+60*10**9
    assert normalize_rows('trades',[record],MAP,req)[1]['invalid_records']==1
    assert ns_iso(NS+123)=='2026-10-23T13:30:00.000000123Z'

def test_ohlcv_second_gap_not_one_minute():
    b=bar(); b['ts_event']+=2*10**9
    rows,q=normalize_rows('ohlcv-1s',[bar(),b],MAP)
    assert q['gaps'][0]['absent_intervals']==1
    assert rows[0]['interval_seconds']==1

@pytest.mark.parametrize('contract',['MNQZ6-MNQH7','MESZ6','MNQA6','MNQ.FUT'])
def test_bad_actual_quarter_contract_rejected(contract):
    mapping=copy.deepcopy(MAP); mapping[0]['contract']=contract
    rows,q=normalize_rows('ohlcv-1m',[bar()],mapping)
    assert not rows and q['invalid_records']==1

def test_empty_partition_is_not_structural_quality_pass():
    rows,q=normalize_rows('ohlcv-1m',[],MAP)
    assert not rows and q['status']=='empty_partition'

@pytest.mark.parametrize('bad',[('roots',('NQ',)),('roots',('MNQ','MNQ')),('schemas',('definition',)),('schemas',('ohlcv-1m','ohlcv-1m'))])
def test_plan_scope_rejects_unrequested_endpoints(bad):
    with pytest.raises(SafeError): Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z',**{bad[0]:bad[1]})
