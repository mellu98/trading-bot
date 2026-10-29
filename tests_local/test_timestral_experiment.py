"""Experiment controls, not evidence of real model inference."""
from dataclasses import replace
from datetime import timedelta
import pytest

from mnq_local.replay import load_session
from mnq_timestral.schema import Request, Prediction, HORIZONS, LEVELS
from mnq_timestral.model import PINS, SOURCE_REVISION
from mnq_local.timestral_experiment import LaggedFilter, forecast_scores, planned_requests, protocol


@pytest.fixture
def context():
    bars, _ = load_session('2026-10-19')
    return tuple(b for b in bars if b.symbol == 'MES')


def prediction(req, latency=.2, offset=2.):
    pin = PINS['28M']
    return Prediction(req.key, req.symbol, req.contract, req.origin,
        req.origin+timedelta(seconds=latency), '28M', pin.revision, SOURCE_REVISION,
        pin.config_sha256, pin.weights_sha256, req.variant, HORIZONS, LEVELS,
        tuple(tuple(req.bars[-1].close+offset for _ in LEVELS) for _ in HORIZONS),
        latency, 'replay', len(req.bars))


class AlwaysLong:
    identity = 'vwap_v1'
    def evaluate(self, bars, now, state):
        return 1, {'count': len(bars)}


def test_filter_waits_one_bar_and_keeps_signal_state(context):
    req = Request(context[:20], context[19].end, variant='target_only')
    records = {req.key: prediction(req, offset=20.)}
    f = LaggedFilter(AlwaysLong(), records, 'target_only')
    assert f.evaluate(context[:20], context[19].end, {}) == (0, {'count': 20})
    side, state = f.evaluate(context[:21], context[20].end, {})
    assert side == 1 and state == {'count': 21}
    assert f.audit[-1]['forecast_origin'] == req.origin.isoformat()
    assert records[req.key].available_at <= context[20].end


@pytest.mark.parametrize('latency', [60.000001, 120.])
def test_not_ready_forecast_blocks_without_invention(context, latency):
    req = Request(context[:20], context[19].end, variant='target_only')
    f = LaggedFilter(AlwaysLong(), {req.key: prediction(req, latency)}, 'target_only')
    assert f.evaluate(context[:21], context[20].end, {})[0] == 0
    assert f.audit[-1]['reason'] == 'not_ready'


def test_missing_identity_and_incoherent_forecasts_block(context):
    req = Request(context[:20], context[19].end, variant='target_only')
    for p, expected in [(None, 'missing'), (prediction(req, offset=-20.), 'distribution_incoherent'),
                        (replace(prediction(req), request_key='wrong'), 'identity')]:
        f = LaggedFilter(AlwaysLong(), {} if p is None else {req.key:p}, 'target_only')
        assert f.evaluate(context[:21], context[20].end, {})[0] == 0
        assert f.audit[-1]['reason'] == expected


def test_accuracy_denominators_and_naive_control(context):
    req = Request(context[:20], context[19].end, variant='target_only')
    p = prediction(req, offset=0.)
    scores = forecast_scores([(req, p)], context)
    for row in scores.values():
        assert row['count'] == 1
        assert row['mae'] == row['random_walk_mae']
        assert row['mae_skill_vs_random_walk'] == (0 if row['random_walk_mae'] else None)
        assert row['directional_calls'] == 0
        assert row['directional_accuracy'] is None
    end = Request(context, context[-1].end, variant='target_only')
    assert all(v['count'] == 0 for v in forecast_scores([(end,prediction(end))], context).values())


def test_requests_are_past_only_and_do_not_cross_session(context):
    requests = list(planned_requests(context, variants=('target_only',), stride=15))
    assert len(requests[0].bars) == 20
    assert len(requests) == 25
    assert all(r.requested_at == r.origin and all(b.available_at <= r.origin for b in r.bars) for r in requests)
    assert protocol()['independent_evidence'] is False
    assert protocol()['filter']['horizon'] == 5
    assert protocol()['live_enabled'] is False


def test_provisioning_not_implicitly_authorized(tmp_path):
    from mnq_local.timestral_experiment import require_license
    with pytest.raises(ValueError, match='eligibility'):
        require_license(False)


def test_real_jsonl_clock_mapping_and_tamper_rejection(context, tmp_path):
    import json
    from mnq_timestral.schema import dumps
    from mnq_local.timestral_experiment import read_records
    req = Request(context[:20], context[19].end, variant='target_only')
    p = replace(prediction(req), clock='wall')
    row = {'request_key': req.key, 'requested_at': req.origin.isoformat(),
           'prediction': json.loads(dumps(p)), 'total_call_seconds': .5,
           'replay_ready_at': (req.origin+timedelta(seconds=.5)).isoformat()}
    path = tmp_path/'forecasts.jsonl'
    path.write_text(json.dumps(row)+'\n')
    groups = {('2026-10-19','MES'):context[:21]}
    records = read_records(path, groups)
    assert records[req.key].clock == 'replay'
    assert records[req.key].available_at == req.origin+timedelta(seconds=.5)
    assert records[req.key].latency_seconds == .5
    path.write_text((json.dumps(row)+'\n')*2)
    with pytest.raises(ValueError, match='duplicate'):
        read_records(path, groups)
    row['replay_ready_at'] = req.origin.isoformat()
    path.write_text(json.dumps(row)+'\n')
    with pytest.raises(ValueError, match='mapping'):
        read_records(path, groups)
    row['total_call_seconds'] = .1
    with path.open('w') as f: json.dump(row,f)
    with pytest.raises(ValueError, match='timing'):
        read_records(path, groups)


def test_coherent_fixture_never_bypasses_final_strict_risk(context, tmp_path):
    from mnq_local.replay import ReplaySession, ReplayOptions
    req = Request(context[:20], context[19].end, variant='target_only')
    s = ReplaySession(tmp_path, ReplayOptions(strict=True))
    wrapper = LaggedFilter(AlwaysLong(), {req.key:prediction(req, offset=20.)}, 'target_only')
    s.runtime.signal_source = wrapper
    try:
        s.run(max_steps=42)
        assert any(a['allowed_by_filter'] for a in wrapper.audit)
        assert not s.runtime.state['orders']
        assert any(d['reason'] == 'strict_news_and_strategy_not_certified'
                   for d in s.runtime.state['decisions'])
    finally:
        s.close()


def test_license_gate_precedes_any_network_or_checkpoint_access(tmp_path, monkeypatch):
    import mnq_local.timestral_experiment as experiment
    monkeypatch.setattr(experiment, 'provision', lambda *a, **k:pytest.fail('Unauthorized provisioning'))
    with pytest.raises(ValueError, match='eligibility'):
        experiment.infer(tmp_path, tmp_path/'missing-checkpoint', False, 4)


def test_naive_reference_computed_without_model(context):
    from mnq_local.timestral_experiment import random_walk_scores
    result = random_walk_scores({('2026-10-19','MES'):context})
    assert result['MES']['1']['count'] == 25
    assert result['MES']['15']['count'] == 24
    assert result['MES']['1']['mae'] >= 0
