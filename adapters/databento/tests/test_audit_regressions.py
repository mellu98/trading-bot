"""One scoped offline correction batch for frozen audit findings F1-F3."""
import json
from datetime import timedelta
import pytest
import databento as db
import databento_dbn as dbn
from mnq_data.core import Adapter, Plan, SafeError, dump, file_hash
from mnq_data.local import normalize_rows, normalize_job
from test_adapter import Fake, NOW, NS, MAP, bar


def valid_bar(ts=NS, publisher=1, instrument=100):
    return {**bar(),'ts_event':ts,'publisher_id':publisher,'instrument_id':instrument}


def test_F1_refresh_already_expired_never_admits_paid_partition(tmp_path):
    clock=[NOW]; f=Fake(); a=Adapter(f,now=lambda:clock[0])
    p=Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z'); report=a.preflight(p)
    original=a.preflight
    def delayed(plan):
        fresh=original(plan); clock[0]+=timedelta(minutes=16); return fresh
    a.preflight=delayed
    with pytest.raises(SafeError): a.download(report,tmp_path/'job',report['request_sha256'],1)
    assert not any(n=='get_range' for _,n,_ in f.calls)
    q=json.loads((tmp_path/'job'/'INCOMPLETE.json').read_text())
    assert q['attempted_partition_count']==0 and q['completed_partition_count']==0
    assert q['automatic_retry'] is False


def test_F1_expiry_between_partitions_stops_and_reports_partial_attempt(tmp_path):
    clock=[NOW]; f=Fake(); original=f.call
    def delay_first(area,name,**kw):
        result=original(area,name,**kw)
        if name=='get_range': clock[0]+=timedelta(minutes=16)
        return result
    f.call=delay_first; a=Adapter(f,now=lambda:clock[0])
    p=Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z'); report=a.preflight(p)
    with pytest.raises(SafeError): a.download(report,tmp_path/'job',report['request_sha256'],1)
    assert len([n for _,n,_ in f.calls if n=='get_range'])==1
    q=json.loads((tmp_path/'job'/'INCOMPLETE.json').read_text())
    assert q['attempted_partition_count']==q['completed_partition_count']==1
    assert len(q['attempted_partitions'])==1 and len(q['completed_files'])==1
    assert q['failure_code']=='refreshed_quote_expired'
    assert not (tmp_path/'job'/'provenance.json').exists()


def genuine_record(schema, publisher, ts):
    shared=dict(publisher_id=publisher,instrument_id=100,ts_event=ts)
    if schema.startswith('ohlcv'):
        return dbn.OHLCVMsg(rtype=getattr(dbn.RType,schema.upper().replace('-','_')),**shared,open=20000*10**9,high=20001*10**9,low=19999*10**9,close=20000*10**9,volume=10)
    shared.update(price=20000*10**9,size=2,action=dbn.Action.TRADE if schema=='trades' else dbn.Action.ADD,side=dbn.Side.BID,depth=0,ts_recv=ts+987)
    if schema=='trades': return dbn.TradeMsg(**shared)
    return dbn.MBP1Msg(**shared,levels=dbn.BidAskPair(bid_px=20000*10**9,ask_px=20001*10**9,bid_sz=8,ask_sz=9,bid_ct=1,ask_ct=1))


@pytest.mark.parametrize('schema',['ohlcv-1m','ohlcv-1s','trades','mbp-1'])
def test_F2_genuine_mixed_publishers_fail_without_valid_abc_staging(schema,tmp_path):
    assert db.Publisher.GLBX_MDP3_GLBX.to_int()==1
    assert db.Publisher.from_int(2)!=db.Publisher.GLBX_MDP3_GLBX
    step=(60 if schema=='ohlcv-1m' else 1)*10**9
    metadata=dbn.Metadata(dataset='GLBX.MDP3',start=NS,end=NS+2*step,stype_in=dbn.SType.CONTINUOUS,stype_out=dbn.SType.INSTRUMENT_ID,schema=dbn.Schema(schema),symbols=['MNQ.v.0'])
    job=tmp_path/'job'; job.mkdir(); raw=job/'raw.dbn'
    raw.write_bytes(bytes(metadata)+bytes(genuine_record(schema,1,NS))+bytes(genuine_record(schema,2,NS+step)))
    request=Plan('2026-10-23T13:30:00Z','2026-10-23T13:32:00Z').request('MNQ',schema)
    dump(job/'provenance.json',{'status':'downloaded_unvalidated','dataset':'GLBX.MDP3','mappings':{'intervals':MAP},'files':[{'path':'raw.dbn','schema':schema,'root':'MNQ','sha256':file_hash(raw),'request':request}]})
    out=tmp_path/'normalized'; result=normalize_job(job,out,5)
    assert result['status']=='failed'
    q=result['partitions'][0]
    assert q['valid_records']==q['invalid_records']==1
    rows=[json.loads(s) for s in (out/q['normalized_file']).read_text().splitlines()]
    assert rows[0]['publisher_id']==1
    assert not (out/'abc-staging').exists()


@pytest.mark.parametrize('schema',['ohlcv-1m','ohlcv-1s','trades','mbp-1'])
def test_F2_missing_publisher_is_not_assumed_from_metadata(schema):
    if schema.startswith('ohlcv'): record=bar()
    else:
        record=dict(ts_recv=NS+1,ts_event=NS,instrument_id=100,price=20000*10**9,size=2,action='T' if schema=='trades' else 'A',bid_px_00=20000*10**9,ask_px_00=20001*10**9)
    record.pop('publisher_id',None)
    rows,q=normalize_rows(schema,[record],MAP)
    assert not rows and q['invalid_records']==1


@pytest.mark.parametrize('schema,step',[('ohlcv-1m',60*10**9),('ohlcv-1s',10**9)])
def test_F3_requested_leading_trailing_gap_inventory(schema,step):
    end='2026-10-23T13:40:00Z' if schema=='ohlcv-1m' else '2026-10-23T13:30:10Z'
    request=Plan('2026-10-23T13:30:00Z',end).request('MNQ',schema)
    rows,q=normalize_rows(schema,[valid_bar(NS+2*step)],MAP,request)
    assert len(rows)==1 and q['invalid_records']==0
    assert [g['absent_intervals'] for g in q['gaps']]==[2,7]
    assert q['requested_grid_complete'] is False
    assert q['status']=='passed_with_unverified_gaps'
    assert all(g['classification']=='unknown_no_trade_or_closure_or_loss' for g in q['gaps'])
    assert q['gaps'][0]['start_ns']==str(NS) and q['gaps'][-1]['end_ns']==str(NS+10*step)


def test_F3_empty_requested_partition_retains_full_missing_grid():
    request=Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z').request('MNQ','ohlcv-1m')
    rows,q=normalize_rows('ohlcv-1m',[],MAP,request)
    assert not rows and q['status']=='empty_partition'
    assert sum(g['absent_intervals'] for g in q['gaps'])==10
    assert q['requested_grid_complete'] is False


def test_F3_rollover_missing_span_split_at_mapping_validity_boundary():
    from mnq_data.local import ns_utc
    boundary=ns_utc('2026-10-24T00:00:00Z'); minute=60*10**9
    mapping=[{**MAP[0],'contract':'MNQU6','end_date':'2026-10-24'}, {**MAP[0],'instrument_id':'101','start_date':'2026-10-24'}]
    request=Plan('2026-10-23T23:58:00Z','2026-10-24T00:02:00Z').request('MNQ','ohlcv-1m')
    records=[valid_bar(boundary-2*minute),valid_bar(boundary+minute,instrument=101)]
    rows,q=normalize_rows('ohlcv-1m',records,mapping,request)
    assert len(rows)==2 and q['invalid_records']==0
    assert [g['absent_intervals'] for g in q['gaps']]==[1,1]
    assert [g['contract'] for g in q['gaps']]==['MNQU6','MNQZ6']
    assert q['gaps'][0]['end_ns']==q['gaps'][1]['start_ns']==str(boundary)


def test_F3_unmapped_request_span_is_visible_not_implicitly_clipped():
    request=Plan('2026-09-30T23:59:00Z','2026-10-01T00:01:00Z').request('MNQ','ohlcv-1m')
    rows,q=normalize_rows('ohlcv-1m',[],MAP,request)
    assert len(q['gaps'])==2
    assert q['gaps'][0]['contract'] is None and q['gaps'][0]['mapping_status']=='unmapped'
    assert q['gaps'][1]['contract']=='MNQZ6'


@pytest.mark.parametrize('start,end',[('2026-10-23T13:30:30Z','2026-10-23T13:40:00Z'),('2026-10-23T13:30:00.000000001Z','2026-10-23T13:40:00Z')])
def test_F3_non_aligned_or_unrepresentable_requests_fail_explicitly(start,end):
    req={'start':start,'end':end,'symbols':['MNQ.v.0']}
    with pytest.raises(SafeError): normalize_rows('ohlcv-1m',[],MAP,req)


def test_F3_event_stream_does_not_assume_regular_grid():
    record=dict(publisher_id=1,ts_recv=NS+1,ts_event=NS,instrument_id=100,price=20000*10**9,size=2,action='T')
    req=Plan('2026-10-23T13:30:00Z','2026-10-23T13:40:00Z').request('MNQ','trades')
    rows,q=normalize_rows('trades',[record],MAP,req)
    assert len(rows)==1 and not q['gaps'] and q['requested_grid_complete'] is None
