"""Read-only feed experiment and risk regression tests; no real order submission."""
import importlib.util
from pathlib import Path
import pytest


def diagnostics():
    path=Path(__file__).resolve().parents[1]/'reports/capital-v62/compare.py'
    spec=importlib.util.spec_from_file_location('capital_v62_compare',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def row(channel,ms,receipt_ms,bid='100',ask='101',epic='US100'):
    return {'channel':channel,'epic':epic,'source_ms':ms,'receipt_ns':int(receipt_ms*1e6),'monotonic_ns':int(receipt_ms*1e6),
        'bid':bid,'ask':ask,'processing_ms':.01}


def test_change_only_claim_is_disproved_by_unchanged_price_messages():
    m=diagnostics();r=m.analyze([row('WS',1000,9000),row('WS',1100,9100),row('WS',1200,9200,'101','102')])
    assert r['US100']['WS']['unchanged_price_messages']==1
    assert r['US100']['WS']['timestamp_age_ms']['p50']==8000
    assert r['transport_latency']=='NOT_IDENTIFIABLE'


def test_equal_prices_near_receipt_are_separated_from_source_timestamp_gap():
    m=diagnostics();rows=[row('WS',1000,9000),row('REST',8900,9050)]
    r=m.analyze(rows)['US100']['paired_receipts']
    assert r['pairs']==1 and r['identical_bid_ask']==1 and r['source_timestamp_lead_rest_ms']['p50']==7900
    assert r['receipt_skew_ms']['p50']==50


def test_price_match_does_not_claim_a_unique_causal_event_when_prices_recur():
    m=diagnostics();r=m.analyze([row('WS',1000,9000),row('WS',2000,10000),row('REST',9900,10050)])
    assert r['US100']['price_alignment']['ambiguous_matches']==1
    assert r['US100']['price_alignment']['unique_match_receipt_lag_ms']['n']==0


def test_rest_bars_are_explicitly_sampled_never_tick_complete():
    m=diagnostics();bars=m.sampled_bars([row('REST',60000,60100),row('REST',62000,62100,'105','106'),row('REST',119000,119100,'102','103')])
    assert len(bars)==1 and bars[0]['kind']=='SAMPLED_REST_MIDPOINT_NOT_COMPLETE_OHLC'
    assert bars[0]['tick_complete'] is False and bars[0]['max_source_gap_ms']==57000
    assert bars[0]['sample_count']==3


def test_confirmed_loss_survives_sorted_intents_and_restart_exactly_once(tmp_path):
    from mnq_local.capital import CapitalHTTP,CapitalJournal,CapitalBroker,CapitalConfig,dec
    from test_capital_demo import Lifecycle,CREDS,instrument_fixture
    f=Lifecycle();h=CapitalHTTP(CREDS,sender=f,sleep=lambda _:None);h.login();cfg=CapitalConfig('DEMO1',mode='technical_test');path=tmp_path/'risk.sqlite'
    j=CapitalJournal(path,cfg);b=CapitalBroker(h,j,cfg);b.reconcile();b.instruments['EPIC1']=instrument_fixture()
    b.place('z-entry','EPIC1','BUY',dec(1),dec(2),dec(4));b.reconcile();b.close_position('a-close','deal1');j.close()
    j=CapitalJournal(path,cfg);b=CapitalBroker(h,j,cfg)
    try:
        b.reconcile();assert b.state['consecutive_losses']==1
        b.reconcile();assert b.state['consecutive_losses']==1
        assert b.state['intents']['z-entry']['risk_outcome']['loss_or_unknown'] is True
    finally:j.close()


def test_daily_attempt_limit_is_passed_to_risk_engine_during_reconciliation(tmp_path):
    from test_capital_demo import make
    from datetime import datetime,timezone
    f,h,j,b=make(tmp_path)
    try:
        for n in range(b.config.max_trades):b.state['intents'][str(n)]={'operation':'open','state':'REJECTED','created_at':datetime.now(timezone.utc).isoformat()}
        b.reconcile();assert not b.ready and b.state['halt']=='max_trades'
    finally:j.close()


def test_rest_signal_carries_sampling_limits_and_reconstruction_context(tmp_path):
    from datetime import datetime,timezone
    from mnq_local.capital_app import DemoRuntime
    from test_capital_demo import make,instrument_fixture
    from mnq_local.capital import dec
    f,h,j,b=make(tmp_path)
    try:
        b.instruments['EPIC1']=instrument_fixture();now=datetime.now(timezone.utc);r=DemoRuntime(b,clock=lambda:now)
        class Source:
            blocked=None;tick=dec('.1');strategies=True
            def on_quote(self,q):return [{'strategy':'orb','epic':q.epic,'side':1,'bar_end':q.at.isoformat()}]
        r.sources={'EPIC1':Source()}
        events=r.on_quote({'epic':'EPIC1','product':'CFD','timestamp':int(now.timestamp()*1000),'bid':100,'ofr':101},source='REST_SNAPSHOT')
        assert events[0]['quote_source']=='REST_SNAPSHOT'
        assert events[0]['bar_quality']=='SAMPLED_REST_NOT_COMPLETE_OHLC' and events[0]['execution_eligible'] is False
        assert events[0]['trigger_quote']['bid']=='100' and events[0]['trigger_quote']['spread']=='1'
    finally:j.close()


def test_identical_source_event_matching_deduplicates_rest_polls_and_cancels_clock_offset():
    m=diagnostics();rs=[row('REST',1000,1100),row('REST',1000,2100),row('WS',1000,9100)]
    result=m.analyze(rs)['US100']['same_source_event']
    assert result['unique_events']==1 and result['ws_minus_first_rest_receipt_ms']['p50']==8000
    assert result['transport_latency_identified'] is False


def test_legacy_confirmed_same_day_negative_exit_backfills_once_without_fx_invention(tmp_path):
    from test_capital_demo import make
    from datetime import datetime,timezone
    f,h,j,b=make(tmp_path)
    try:
        at=datetime.now(timezone.utc).isoformat()
        b.state['intents']={'entry':{'operation':'open','state':'BROKER_POSITION_CLOSED','deal_id':'old1','created_at':at,'cash_before':10000},
            'close':{'operation':'close','state':'CONFIRMED_CLOSED','target_id':'old1','created_at':at,'confirmation':{'profit':-.002,'profitCurrency':'USD'}}}
        b.reconcile();b.reconcile()
        assert b.state['consecutive_losses']==1 and b.state['daily_opening_attempts']==1
        outcome=b.state['intents']['entry']['risk_outcome']
        assert outcome['cash_delta_account'] is None and outcome['native_profit']=='-0.002'
    finally:j.close()


def test_native_minute_bar_read_is_narrowly_allowlisted_and_cannot_enable_orders():
    from mnq_local.capital import CapitalHTTP,CapitalError
    from test_capital_demo import Fixture,CREDS
    h=CapitalHTTP(CREDS,sender=Fixture(),sleep=lambda _:None,orders_enabled=False);h.login()
    h.request('GET','/prices/US100?resolution=MINUTE&max=10')
    h.request('GET','/prices/US500?resolution=MINUTE&max=10')
    assert not h.orders_enabled
    for route in ('/prices/OIL?resolution=MINUTE&max=10','/prices/US100?resolution=MINUTE&max=1000'):
        with pytest.raises(ValueError):h.request('GET',route)
    with pytest.raises(CapitalError,match='orders_disabled'):h.request('POST','/positions',{})
