import pytest
from mnq_sim.acquire import validate_authorized_scope


def scope():
    return {'dataset':'GLBX.MDP3','schema':'ohlcv-1m','total_cost_usd':'0.014238059520',
        'partitions':[{'root':root,'contract':root+'Z6','date':f'2026-10-{d}',
        'request':{'dataset':'GLBX.MDP3','schema':'ohlcv-1m','symbols':[root+'Z6'],
                   'stype_in':'raw_symbol','start':f'2026-10-{d}T13:30:00Z','end':f'2026-10-{d}T20:00:00Z'}}
        for d in range(19,24) for root in ('MNQ','MES')]}


def test_only_exact_authorized_scope():
    validate_authorized_scope(scope())


@pytest.mark.parametrize('field,value',[('dataset','XNAS.ITCH'),('schema','trades'),('total_cost_usd','0.0200001')])
def test_forbid_scope_or_cap_expansion(field,value):
    s=scope();s[field]=value
    with pytest.raises(ValueError): validate_authorized_scope(s)


def test_forbid_duplicate_missing_and_overnight():
    for mode in ('duplicate','missing','overnight','contract'):
        s=scope()
        if mode=='duplicate': s['partitions'][1]=s['partitions'][0]
        elif mode=='missing': s['partitions'].pop()
        elif mode=='overnight': s['partitions'][0]['request']['start']='2026-10-19T00:00:00Z'
        else: s['partitions'][0]['request']['symbols']=['MNQU6']
        with pytest.raises(ValueError): validate_authorized_scope(s)


def test_paid_transport_blocks_wrong_host_and_body_before_network(monkeypatch):
    from mnq_sim.acquire import AuthorizedBackend
    from databento_planner.security import PlannerError
    backend=AuthorizedBackend('db-'+'A'*29,{})
    calls=[]
    monkeypatch.setattr(backend.session,'post',lambda *a,**k:calls.append(1))
    try:
        with pytest.raises(PlannerError): backend._post(url='https://evil.example/v0/timeseries.get_range')
        backend.active=scope()['partitions'][0]['request']
        from requests.auth import HTTPBasicAuth
        with pytest.raises(PlannerError):
            backend._post(url='https://hist.databento.com/v0/timeseries.get_range',
                auth=HTTPBasicAuth('db-'+'A'*29,''),data={'dataset':'XNAS.ITCH'})
        assert calls==[]
        assert backend.session.get_adapter('https://').max_retries.total==0
    finally: backend.close()


def test_recovery_refuses_any_ambiguous_paid_attempt():
    from mnq_sim.acquire import completed_attempts
    assert completed_attempts({'attempted':[0,1],'completed':[{'partition':0},{'partition':1}]})=={0,1}
    with pytest.raises(ValueError): completed_attempts({'attempted':[0,1],'completed':[{'partition':0}]})
