import pytest
from mnq_sim.bulk import validate_request, authorize_total


def req(date='2026-05-05'):
    return {'dataset':'GLBX.MDP3','schema':'ohlcv-1m','symbols':['MNQM6','MESM6'],
            'stype_in':'raw_symbol','start':date+'T13:30:00Z','end':date+'T20:00:00Z'}


def test_reject_cached_days_outside_scope_and_other_schema():
    validate_request(req())
    for r in (req('2026-10-19'),req('2026-05-04'),{**req(),'schema':'trades'},
              {**req(),'symbols':['MNQM6','ESM6']},{**req(),'start':'2026-05-05T00:00:00Z'}):
        with pytest.raises(ValueError):validate_request(r)


def test_aggregate_budget_includes_all_attempts_not_only_successes():
    authorize_total('0.49','0.01')
    with pytest.raises(ValueError):authorize_total('0.49','0.010001')
    with pytest.raises(ValueError):authorize_total('NaN','0')
