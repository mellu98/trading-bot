"""Local invariant verification, NOT real broker certification."""
import hashlib,json,sqlite3
from mnq_paper.__main__ import protected,ROOT,REPORT
from mnq_paper.ib import IBPaper


def verify():
    result=json.loads((REPORT/'demo-delivery/summary.json').read_text())
    state=json.loads((REPORT/'demo-delivery/state-export.json').read_text())
    assert result['real_broker_connected'] is False and result['financial_validation'] is False
    assert result['bars_received']==3900 and result['executions']==len(state['executions'])
    assert all(p['quantity']==0 for p in state['positions'].values())
    assert all(o['status'] in {'Filled','Cancelled','ApiCancelled','Inactive','Absent'} for o in state['orders'].values())
    assert len(state['executions'])==len(set(state['executions']))
    assert len({o['id'] for o in state['orders'].values()})==len(state['orders'])
    for execution in state['executions'].values():
        o=state['orders'][str(execution['order_id'])]
        assert execution['client_id']==71 and execution['side']==o['side']
    db=sqlite3.connect(REPORT/'demo-delivery/state.sqlite')
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    events=db.execute('SELECT seq,kind,body FROM journal').fetchall();db.close()
    assert any(kind=='bracket_intent' for _,kind,_ in events) and any(kind=='execution' for _,kind,_ in events)
    for o in state['orders'].values():
        if o['role']=='entry':
            assert o['transmit'] is False and o['good_till'].endswith(' UTC')
            legs=[k for k in state['orders'].values() if k['parent_id']==o['id']]
            assert {k['role'] for k in legs}=={'stop','target'} and len(legs)==2
    frozen=protected();prior=json.loads((ROOT/'reports/databento/planning/baseline-integrity.json').read_text())
    old=prior['all_existing_before']
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in old.items())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in prior['primary_37']['files'].items())
    proof={'status':'PASS_LOCAL_ONLY','frozen_v1_v2_files':frozen,'original_paths_unchanged':len(old),'primary37_unchanged':True,
      'official_sdk_source_files_verified':IBPaper.verify_sdk(),'actual_broker_paper_verified':False,
      'sqlite_integrity':'ok','mock_unique_executions':len(state['executions']),'mock_unique_orders':len(state['orders']),
      'new_market_data_acquisitions':0,'new_live_orders':0,'note':'SDK source and serialization tested; no authenticated paper broker session available'}
    (REPORT/'verification.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n');print(json.dumps(proof,indent=2))


if __name__=='__main__':verify()
