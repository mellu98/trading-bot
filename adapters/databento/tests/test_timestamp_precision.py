"""Lossless public timestamp boundaries; all vendor operations use offline spies."""
import copy
import json
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import databento as db
import pandas as pd
import pytest

from mnq_data.core import Adapter, Plan, SafeError, digest, iso, utc
from mnq_data.local import normalize_rows, ns_iso, ns_utc
from test_adapter import Fake, MAP, NOW, NS


def event_plan(start='2026-10-23T13:30:00.000000001Z', end='2026-10-23T13:30:00.000000003Z'):
    return Plan(start,end,roots=('MNQ',),schemas=('trades','mbp-1'))


def test_public_plan_preserves_original_one_nanosecond_and_digest():
    p=event_plan()
    assert p.start.endswith('.000000001Z')
    assert ns_utc(p.start)==NS+1 and ns_utc(p.end)==NS+3
    assert Plan.from_dict(json.loads(json.dumps(p.as_dict())))==p
    shifted=event_plan('2026-10-23T13:30:00.000000002Z')
    assert digest(p.as_dict())!=digest(shifted.as_dict())


def test_equivalent_offsets_canonicalize_to_same_exact_digest():
    p=event_plan()
    other=event_plan('2026-10-23T15:30:00.000000001+02:00','2026-10-23T08:30:00.000000003-05:00')
    assert p.as_dict()==other.as_dict()
    assert digest(p.as_dict())==digest(other.as_dict())


@pytest.mark.parametrize('start,end',[
    ('2026-10-23T13:30:00.000000003Z','2026-10-23T13:30:00.000000002Z'),
    ('2026-10-23T13:30:00.000000001Z','2026-10-23T15:30:00.000000001+02:00'),
])
def test_interval_order_compares_exact_instants(start,end):
    with pytest.raises(SafeError,match='invalid_historical_interval'): event_plan(start,end)


@pytest.mark.parametrize('value,expected',[
    ('2026-10-23T13:30:00.000000001Z',NS+1),
    ('2026-10-23T13:30:00.123456789Z',NS+123456789),
    ('1969-12-31T23:59:59.999999999Z',-1),
    ('1970-01-01T00:00:00.000000001Z',1),
    ('1677-09-21T00:12:43.145224193Z',-(2**63)+1),
    ('2262-04-11T23:47:16.854775807Z',2**63-1),
    (pd.Timestamp('2026-10-23T15:30:00.123456789+02:00'),NS+123456789),
    (datetime(2026,10,23,15,30,0,123456,tzinfo=timezone(timedelta(hours=2))),NS+123456000),
])
def test_exact_roundtrip_and_internal_ns(value,expected):
    assert ns_utc(value)==expected
    assert utc(value).value==expected
    assert ns_utc(iso(value))==expected
    assert ns_utc(ns_iso(expected))==expected


@pytest.mark.parametrize('value',[
    '2026-10-23T13:30:00.0000000001Z',
    '2026-10-23T13:30:00.1234567890Z',
    '2026-10-23T13:30:00.0000000000Z',
    '2026-10-23T13:30:00', '2026-10-23',
    '2026-10-23T13:30:00-00:00', '2026-10-23T13:30:00EST',
    '2026-10-23T13:30:00+25:00', '2026-10-23T13:30:00+00:60',
    '2026-02-29T13:30:00Z', '2024-02-29T24:00:00Z',
    '2016-12-31T23:59:60Z', 'NaT', None,
    NS, float(NS), True, float('nan'), float('inf'), str(NS),
    '1677-09-21T00:12:43.145224192Z', '2262-04-11T23:47:16.854775808Z',
    datetime(2026,10,23,13,30), pd.Timestamp('2026-10-23T13:30:00'), pd.NaT,
    '2026-10-23T13:30:00Z ', ' 2026-10-23T13:30:00Z',
])
def test_ambiguous_or_lossy_values_rejected_before_conversion(value):
    for convert in (utc,iso,ns_utc):
        with pytest.raises(SafeError): convert(value)
    with pytest.raises(SafeError): event_plan(value)


def test_timezone_dst_ambiguity_and_nonexistent_wall_clock_rejected():
    for hour,month,day in [(1,11,1),(2,3,8)]:
        value=datetime(2026,month,day,hour,30,tzinfo=ZoneInfo('America/New_York'))
        with pytest.raises(SafeError): utc(value)
    valid=datetime(2026,10,23,9,30,tzinfo=ZoneInfo('America/New_York'))
    assert ns_utc(valid)==NS
    assert ns_utc('2024-02-29T00:00:00Z')==pd.Timestamp('2024-02-29T00:00:00Z').value


@pytest.mark.parametrize('schema,stamp',[
    ('ohlcv-1m','2026-10-23T13:30:00.000000001Z'),
    ('ohlcv-1s','2026-10-23T13:30:00.000000001Z'),
    ('ohlcv-1m','2026-10-23T13:30:01Z'),
])
def test_public_request_alignment_rejected_before_backend_call(schema,stamp):
    p=Plan(stamp,'2026-10-23T13:40:00Z',schemas=(schema,))
    backend=Fake()
    with pytest.raises(SafeError,match='unaligned_ohlcv_request'): p.request('MNQ',schema)
    with pytest.raises(SafeError,match='unaligned_ohlcv_request'): Adapter(backend,now=lambda:NOW).preflight(p)
    assert not backend.calls


def test_event_clock_bounds_remain_exact_and_end_exclusive():
    p=event_plan(); req=p.request('MNQ','trades')
    records=[dict(publisher_id=1,ts_recv=NS+n,ts_event=NS+n,instrument_id=100,price=20000*10**9,size=2,action='T') for n in (0,1,2,3)]
    rows,quality=normalize_rows('trades',records,MAP,req)
    assert [r['ts_recv_ns'] for r in rows]==[str(NS+1),str(NS+2)]
    assert quality['errors']=={'outside_requested_interval':2}


def test_preflight_and_approved_offline_download_preserve_ns(tmp_path):
    f=Fake(); a=Adapter(f,now=lambda:NOW); p=event_plan()
    report=a.preflight(p)
    out=a.download(report,tmp_path/'fake-job',report['request_sha256'],1)
    requests=[kw for _,name,kw in f.calls if name in ('get_cost','get_billable_size','get_record_count','get_range')]
    assert requests and all(kw['start']==p.start and kw['end']==p.end for kw in requests)
    assert all(x['request']['start']==p.start for x in out['files'])


def test_official_sdk_serialization_preserves_ns_without_http(monkeypatch):
    from databento.historical.api.metadata import MetadataHttpAPI
    sent=[]
    class Response:
        def json(self): return .01
    def fake_post(self,**kw): sent.append(kw['data']); return Response()
    monkeypatch.setattr(MetadataHttpAPI,'_post',fake_post)
    client=db.Historical(key='offline-placeholder-no-network')
    p=event_plan()
    assert client.metadata.get_cost(**p.request('MNQ','trades'))==.01
    assert ns_utc(sent[0]['start'])==NS+1 and ns_utc(sent[0]['end'])==NS+3


def test_quote_checked_at_compared_at_nanosecond_before_any_call(tmp_path):
    f=Fake(); a=Adapter(f,now=lambda:NOW); report=a.preflight(event_plan())
    report['checked_at']='2026-10-25T00:00:00.000000001Z'
    calls=len(f.calls)
    with pytest.raises(SafeError,match='stale_quote'): a.download(report,tmp_path/'blocked',report['request_sha256'],1)
    assert len(f.calls)==calls and not (tmp_path/'blocked').exists()


def test_mapping_day_for_end_one_nanosecond_after_midnight():
    p=event_plan('2026-10-23T23:59:59.999999999Z','2026-10-24T00:00:00.000000001Z')
    mapping={'intervals':[{**MAP[0],'end_date':'2026-10-24'}]}
    assert not Adapter.mapping_complete(mapping,p)
    f=Fake(); Adapter(f,now=lambda:NOW).preflight(p)
    first=next(kw for _,name,kw in f.calls if name=='resolve')
    assert first['end_date']=='2026-10-25'


def test_cli_public_boundary_never_silently_rounds_ns(monkeypatch,tmp_path,capsys):
    from mnq_data import cli
    f=Fake(); monkeypatch.setattr(cli,'SDKBackend',lambda:f)
    output=tmp_path/'preflight.json'
    monkeypatch.setattr(sys,'argv',['mnq-data','preflight','--start','2026-10-23T13:30:00.000000001Z','--end','2026-10-23T13:40:00Z','--output',str(output)])
    assert cli.main()==2
    result=json.loads(output.read_text())
    assert result['status']=='not_verified' and result['error_code']=='unaligned_ohlcv_request'
    assert result['plan']['start']=='2026-10-23T13:30:00.000000001Z'
    assert not f.calls and 'verified_metadata' not in capsys.readouterr().out


@pytest.mark.parametrize('schema',['trades','mbp-1'])
def test_empty_event_stream_cannot_hide_invalid_request_clock(schema):
    req={'start':'2026-10-23T13:30:00.0000000001Z','end':'2026-10-23T13:40:00Z','symbols':['MNQ.v.0']}
    with pytest.raises(SafeError,match='invalid_aware_timestamp'): normalize_rows(schema,[],MAP,req)


def test_one_ns_plan_change_invalidates_existing_exact_approval(tmp_path):
    f=Fake(); a=Adapter(f,now=lambda:NOW); report=a.preflight(event_plan())
    changed=copy.deepcopy(report)
    changed['plan']['start']='2026-10-23T13:30:00.000000002Z'
    calls=len(f.calls)
    with pytest.raises(SafeError,match='explicit_exact_request_approval_required'):
        a.download(changed,tmp_path/'blocked',report['request_sha256'],1)
    assert len(f.calls)==calls
