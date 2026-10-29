"""Adversarial software tests; all fixtures and monetary examples are synthetic."""
from dataclasses import replace
from datetime import timedelta
from threading import Event
import time
import pytest
from conftest import prediction, bars
from mnq_timestral.schema import Prediction, Request, dumps, loads
from mnq_timestral.provider import AsyncPredictionProvider
from mnq_timestral.strategy import Risk, RiskState, Candidate, Filter
from mnq_timestral.evaluation import simulate_trade, Costs, validate_plan, DEFAULT_PLAN
from mnq_timestral.data import session_window


def test_not_yet_ready_prediction_is_retained(req):
    p=AsyncPredictionProvider(lambda r:prediction(r,delay=5))
    try:
        p.submit(req);time.sleep(.05)
        assert p.latest(req,req.origin) is None
        assert p.latest(req,req.origin+timedelta(seconds=6)) is not None
    finally:p.close()


def test_risk_rejects_nonfinite_state_and_invalid_limits():
    with pytest.raises(ValueError): Risk(daily_max_loss=-1)
    with pytest.raises(ValueError): Risk(max_trades=0)
    for field in ('realized','unrealized','drawdown'):
        with pytest.raises(ValueError): RiskState(**{field:float('nan')})


def test_request_rejects_late_context_and_non_cash_next_day(req):
    future=replace(req.bars[-1],available_at=req.origin+timedelta(seconds=2))
    with pytest.raises(ValueError): replace(req,bars=req.bars[:-1]+(future,))
    with pytest.raises(ValueError): replace(req,bars=req.bars[1:])
    assert Request(bars(20,date='2026-11-02',hour=14),bars(20,date='2026-11-02',hour=14)[-1].end).origin.hour==14


def test_wire_explicit_medians_and_duplicate_nan_rejection(pred):
    wire=loads(dumps(pred))
    assert wire['medians']==list(pred.medians)
    assert Prediction.from_dict(wire)==pred
    wire['medians'][0]+=1
    with pytest.raises(ValueError): Prediction.from_dict(wire)
    for text in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
        with pytest.raises(ValueError): loads(text)


def test_short_stop_gap_and_gap_data_block():
    fee=Costs(0,0,0,0,0,0,'synthetic zero-cost mathematical test')
    bs=bars(3)
    gap=replace(bs[0],open=6005,high=6006,low=6004,close=6005)
    trade=simulate_trade('MES',-1,[gap],6000,fee)
    assert trade.raw_exit==6005 and trade.net==-25
    with pytest.raises(ValueError,match='gap'):
        simulate_trade('MES',1,[bs[0],bs[2]],6000,fee,tp=100,sl=100)


def test_unknown_late_calendar_and_news_fail_closed():
    rec={'open':'2026-10-20T13:30:00+00:00','close':'2026-10-20T20:00:00+00:00',
         'known_at':'2026-10-20T13:31:00+00:00','news_complete':True,'news_blocks':[]}
    assert session_window('2026-10-20',{'2026-10-20':rec}) is None
    rec['known_at']='2026-10-20T00:00:00+00:00'
    rec['news_blocks']=[{'start':'2026-10-20T14:00:00+00:00','end':'2026-10-20T14:10:00+00:00','known_at':'2026-10-20T14:01:00+00:00'}]
    assert session_window('2026-10-20',{'2026-10-20':rec}) is None


def test_plan_cannot_reduce_evidence_floor_or_accept_nonfinite_threshold():
    p=dict(DEFAULT_PLAN,holdout_previously_unseen_attestation=True)
    for changes in ({'minimum_sessions':1},{'thresholds':[float('nan')]},{'family_size':1}):
        with pytest.raises(ValueError): validate_plan(dict(p,**changes))


def test_invalid_filter_or_candidate_configuration_cannot_loosen_gate(req):
    for kw in ({'ttl':float('nan')},{'ttl':-1},{'enabled':'false'}):
        with pytest.raises(ValueError): Filter(**kw)
    for kw in ({'side':0},{'price':float('nan')},{'origin':req.origin.replace(tzinfo=None)}):
        base=dict(symbol=req.symbol,contract=req.contract,side=1,origin=req.origin,price=req.bars[-1].close,request_key=req.key)
        base.update(kw)
        with pytest.raises(ValueError): Candidate(**base)


def test_raw_trade_contract_cannot_accept_nonsense():
    fee=Costs(0,0,0,0,0,0,'synthetic test')
    for kw in ({'sl':-1},{'tp':float('nan')},{'stress':-1}):
        with pytest.raises(ValueError): simulate_trade('MES',1,bars(2),6000,fee,**kw)


def test_contract_tick_and_integer_volume_enforced(req):
    with pytest.raises(ValueError):replace(req.bars[0],volume=1.5)
    with pytest.raises(ValueError):replace(req.bars[0],close=6000.1)


def test_filter_future_origin_and_tail_symmetric(req):
    c=Candidate(req.symbol,req.contract,-1,req.origin,req.bars[-1].close,req.key)
    short=prediction(req,delta=-3)
    assert Filter(True).evaluate(c,short,req.origin)[0]
    assert not Filter(True).evaluate(c,short,req.origin-timedelta(seconds=1))[0]


@pytest.mark.parametrize('horizon',[1,3,5,10,15])
def test_audit_f2_forecast_target_maturity_is_a_hard_boundary(req,horizon):
    from dataclasses import replace
    short_req=replace(req,bars=req.bars[:20],requested_at=req.bars[19].available_at)
    c=Candidate(short_req.symbol,short_req.contract,1,short_req.origin,short_req.bars[-1].close,short_req.key)
    p=prediction(short_req,delta=3)
    f=Filter(True,horizon=horizon)
    # The TTL is independent and may expire earlier; target maturity must always reject.
    assert f.evaluate(c,p,p.origin+timedelta(seconds=59))[0]
    for offset in (0,1):
        assert not f.evaluate(c,p,p.origin+timedelta(minutes=horizon,seconds=offset))[0]
    if horizon==1:
        assert f.evaluate(c,p,p.origin+timedelta(seconds=59))[0]
        assert f.evaluate(c,p,p.origin+timedelta(seconds=60))==(False,'target_expired')


def test_audit_f1_preregistered_model_evidence_floor():
    assert DEFAULT_PLAN['minimum_usable_forecasts']>=30
    assert 0<DEFAULT_PLAN['minimum_forecast_coverage']<=1
    assert DEFAULT_PLAN['require_positive_filtered_net'] is True


def test_audit_f1_profitability_and_coverage_are_required_for_attribution():
    from mnq_timestral.evaluation import model_statistical_screen, validate_plan
    part={'daily_difference':[1.]*30,'model_evidence':{'usable_forecasts':30,'opportunities':30},
          'arms':{'B':{'net':-1.}},'selected_on_validation':{'status':'selected'}}
    plan=dict(DEFAULT_PLAN,holdout_previously_unseen_attestation=True,bootstrap_replicates=1000)
    result=model_statistical_screen([part],plan)
    assert result['lower_bound']>0 and not result['research_improvement']
    assert 'positive net' in result['reason']
    part['arms']['B']['net']=1.
    part['model_evidence']['opportunities']=100
    result=model_statistical_screen([part],plan)
    assert result['status']=='insufficient_model_evidence' and not result['research_improvement']
    for values in ({'minimum_usable_forecasts':0},{'minimum_forecast_coverage':0.},
                   {'require_positive_filtered_net':False}):
        with pytest.raises(ValueError):validate_plan(dict(plan,**values))
