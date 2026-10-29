"""F1-F5 frozen audit regressions; synthetic-only temp files and fake backends."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import json
import pytest
from test_planner import Backend, FakePaid, NOW, identity, job, synthetic_dbn
from databento_planner.cache import Cache
from databento_planner.gate import Approval, acquisition_digest, execute_approved
from databento_planner.planner import comparison
from databento_planner.security import PlannerError, MetadataOnly

@pytest.mark.parametrize('kind',['traversal','symlink'])
def test_F1_compare_path_escape_zero_metadata(tmp_path,monkeypatch,kind):
    import databento_planner.cli as cli
    allowed=tmp_path/'reports'/'databento'/'planning';allowed.mkdir(parents=True)
    outside=tmp_path/'outside';outside.mkdir()
    if kind=='symlink':
        (allowed/'link').symlink_to(outside,target_is_directory=True)
        destination=allowed/'link'/'escaped'
    else: destination=allowed/'..'/'..'/'..'/'escaped'
    b=Backend();monkeypatch.setattr(cli,'ROOT',tmp_path)
    monkeypatch.setattr(cli,'baseline_check',lambda:{})
    monkeypatch.setattr(cli,'load_key',lambda:('db-'+'X'*29,{}))
    b.trace=[];b.close=lambda:None
    monkeypatch.setattr(cli,'MetadataOnly',lambda *a,**kw:b)
    with pytest.raises(PlannerError): cli.quote_command(SimpleNamespace(output=str(destination),as_of=NOW))
    assert b.calls==[] and not (outside/'escaped').exists() and not (tmp_path/'escaped').exists()

@pytest.mark.parametrize('kind',['traversal','symlink'])
def test_F1_gate_path_escape_zero_backend(tmp_path,kind):
    c=Cache(tmp_path/'cache');outside=tmp_path/'outside';outside.mkdir()
    if kind=='symlink':
        (c.root/'jobs'/'link').symlink_to(outside,target_is_directory=True)
        destination=c.root/'jobs'/'link'/'escaped'
    else: destination=c.root/'jobs'/'..'/'..'/'escaped'
    class Spy(FakePaid):
        def quote(self,p): self.calls+=1;return super().quote(p)
    j=job();b=Spy();a=Approval(acquisition_digest(j),'1','escape-test')
    with pytest.raises(PlannerError):execute_approved(j,a,c,destination,b,now=NOW,configured_cap='1')
    assert b.calls==0 and not (tmp_path/'escaped').exists() and not list((c.root/'leases').glob('*'))

def test_F2_foreign_matching_publisher_never_admitted(tmp_path):
    c=Cache(tmp_path);foreign=replace(identity(),publisher_id=2)
    path,provenance=synthetic_dbn(c,foreign)
    with pytest.raises(PlannerError): c.register(path,foreign,(60_000_000_000,120_000_000_000),provenance)
    assert not list((c.root/'receipts').glob('*.json'))

def test_F3_checkpoint_per_endpoint_resumes_partial_partition(tmp_path):
    b=Backend();first=comparison(b,NOW,now=NOW,checkpoint=tmp_path/'study',max_calls=6)
    assert first['status']=='partial_metadata' and first['scenarios']['1']['total_cost_usd'] is None
    assert len(b.calls)==6  # five discovery endpoints, then genuine cost response
    entries=list((tmp_path/'study').glob('*.json'))
    assert any('get_cost' in p.read_text() for p in entries)
    second=comparison(b,NOW,now=NOW,checkpoint=tmp_path/'study',max_calls=5)
    assert len(b.calls)==11 and second['scenarios']['1']['total_cost_usd']=='0.000246'
    assert len([x for x in b.calls if x[1]=='get_cost' and x[2]['symbols']==['MNQZ6']])==1
    assert all('2026-10-23' in x[2]['start'] for x in b.calls if x[1].startswith('get_') and 'symbols' in x[2])
    with pytest.raises(PlannerError): comparison(b,'2026-10-22T22:00:00Z',now=NOW,checkpoint=tmp_path/'study',max_calls=1)

def test_F3_network_failure_keeps_prior_typed_response(tmp_path):
    class Fails(Backend):
        def call(self,a,n,**kw):
            if n=='get_billable_size':raise PlannerError('synthetic_interruption')
            return super().call(a,n,**kw)
    b=Fails()
    with pytest.raises(PlannerError): comparison(b,NOW,now=NOW,checkpoint=tmp_path/'study',max_calls=10)
    cost=[json.loads(p.read_text()) for p in (tmp_path/'study').glob('*.json') if 'get_cost' in p.read_text()]
    assert len(cost)==1 and cost[0]['value']=='0.000123' and cost[0]['checked_at'] and cost[0]['expires_at']
    resumed=Backend();r=comparison(resumed,NOW,now=NOW,checkpoint=tmp_path/'study',max_calls=5)
    assert r['scenarios']['1']['total_cost_usd']=='0.000246'
    assert len([x for x in resumed.calls if x[1]=='get_cost'])==1

def test_F4_batches_newest_first_keep_expired_historical_estimates(tmp_path):
    b=Backend();r=None
    for _ in range(7): r=comparison(b,NOW,now='2026-10-26T01:00:00Z',checkpoint=tmp_path/'study',max_calls=60)
    assert r['status']=='verified_metadata' and len(b.calls)==365
    assert [x for x in b.calls if x[1]=='get_cost'][0][2]['start'].startswith('2026-10-23')
    assert r['scenarios']['60']['total_cost_usd']=='0.014760'
    later=comparison(b,NOW,now='2026-10-26T02:00:00Z',checkpoint=tmp_path/'study',max_calls=0)
    assert later['scenarios']['60']['total_cost_usd']==r['scenarios']['60']['total_cost_usd']
    assert not later['acquisition_quotes_all_current'] and len(b.calls)==365 and not later['download_authorized']

def test_F4_remaining_deadline_bounds_transport_timeout(monkeypatch):
    import requests
    import databento_planner.security as security
    b=MetadataOnly('db-'+'X'*29,max_seconds=2)
    b._started=100;b._last=0
    monkeypatch.setattr(security.time,'monotonic',lambda:101.5)
    seen=[]
    def request(method,url,**kw):
        seen.append(kw['timeout'])
        response=requests.Response();response.status_code=200;response._content=b'0.0001';response._content_consumed=True;return response
    monkeypatch.setattr(b._session,'request',request)
    b.call('metadata','get_cost',dataset='GLBX.MDP3',schema='ohlcv-1m',symbols=['MNQZ6'],start='2026-10-23T13:30:00Z',end='2026-10-23T20:00:00Z')
    assert sum(seen[0])<=.5


def test_F5_same_identity_overlap_rejected_before_quote_or_lease(tmp_path):
    c=Cache(tmp_path/'cache');j=job();j['partitions'][0]['end_ns']=180_000_000_000
    j['partitions'].append({**j['partitions'][0],'start_ns':120_000_000_000,'end_ns':240_000_000_000})
    class Spy(FakePaid):
        def quote(self,p):self.calls+=1;return super().quote(p)
    b=Spy();a=Approval(acquisition_digest(j),'1','overlap-test')
    with pytest.raises(PlannerError):execute_approved(j,a,c,c.root/'jobs'/'overlap',b,now=NOW,configured_cap='1')
    assert b.calls==0 and not list((c.root/'leases').glob('*'))

def test_F3_wrong_exact_identity_checkpoint_rejected_without_requery(tmp_path):
    from mnq_data.core import digest
    b=Backend();comparison(b,NOW,now=NOW,checkpoint=tmp_path/'study',max_calls=6)
    path=next(p for p in (tmp_path/'study').glob('*.json') if 'get_cost' in p.read_text())
    value=json.loads(path.read_text());value['identity']['request']['symbols']=['MNQU6']
    path.write_text(json.dumps(value))
    with pytest.raises(PlannerError,match='checkpoint'):comparison(b,NOW,now=NOW,checkpoint=tmp_path/'study',max_calls=60)
    assert len(b.calls)==6

def test_F5_adjacent_intervals_allowed_without_merging_approval():
    from databento_planner.gate import validate_job
    j=job();j['partitions'].append({**j['partitions'][0],'start_ns':120_000_000_000,'end_ns':180_000_000_000})
    before=acquisition_digest(j);validate_job(j)
    assert acquisition_digest(j)==before
