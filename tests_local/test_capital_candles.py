"""Native candle contracts: no broker orders, no CME volume assumptions."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import pytest
from mnq_local.capital import CapitalHTTP
from test_capital_demo import Fixture,CREDS
UTC=timezone.utc


def bar(at='2026-10-26T15:00:00',close=101):
    return {'snapshotTimeUTC':at,'openPrice':{'bid':100,'ask':101},'highPrice':{'bid':102,'ask':103},
        'lowPrice':{'bid':99,'ask':100},'closePrice':{'bid':close,'ask':close+1},'lastTradedVolume':25}


def test_native_5m_and_bounded_context_reads_cannot_enable_orders():
    h=CapitalHTTP(CREDS,sender=Fixture(),sleep=lambda _:None,orders_enabled=False);h.login()
    for resolution in ('MINUTE','MINUTE_5'):
        for size in (10,500):h.request('GET',f'/prices/US100?resolution={resolution}&max={size}')
    assert not h.orders_enabled
    with pytest.raises(ValueError):h.request('GET','/prices/US100?resolution=MINUTE&max=1000')


def test_native_parser_rejects_ambiguous_unaligned_invalid_ohlc_before_conversion():
    from mnq_local.capital_candles import parse_candle
    assert parse_candle('US100','MINUTE',bar())['volume_kind']=='BROKER_REPORTED_NOT_CME_VERIFIED'
    for change in ({'snapshotTimeUTC':1793026800},{'snapshotTimeUTC':'2026-10-26T15:00:00.000000001'},
                   {'snapshotTimeUTC':'2026-10-26T15:00:01'},{'snapshotTimeUTC':'2026-10-26T15:00:00+01:00'},
                   {'closePrice':{'bid':105,'ask':104}},{'lastTradedVolume':-1}):
        with pytest.raises(ValueError):parse_candle('US100','MINUTE',{**bar(),**change})
    with pytest.raises(ValueError):parse_candle('US100','MINUTE_5',bar('2026-10-26T15:01:00'))


def ns(text):return int(datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp())*10**9


def provider():
    from mnq_local.capital_candles import NativeCandleProvider
    state={};events=[];return NativeCandleProvider(state,lambda k,v:events.append((k,v))),state,events


def test_open_bars_never_emit_and_closed_bar_needs_distinct_stable_observations():
    p,state,events=provider();data={'prices':[bar(),bar('2026-10-26T15:01:00')]}
    assert not p.observe('US100','MINUTE',data,ns('2026-10-26T15:00:59'))
    assert not p.observe('US100','MINUTE',data,ns('2026-10-26T15:01:01'))
    ready=p.observe('US100','MINUTE',data,ns('2026-10-26T15:01:03'))
    assert len(ready)==1 and ready[0]['verified_at_ns']==ns('2026-10-26T15:01:03')
    assert ready[0]['publication_delay_upper_s']==1 and ready[0]['tracked_before_close']
    assert not p.observe('US100','MINUTE',data,ns('2026-10-26T15:01:05'))


def test_revisions_after_close_quarantine_context_not_emit_an_alternative_signal():
    p,state,_=provider();data={'prices':[bar(),bar('2026-10-26T15:01:00')]}
    p.observe('US100','MINUTE',data,ns('2026-10-26T15:00:59'))
    p.observe('US100','MINUTE',data,ns('2026-10-26T15:01:01'))
    p.observe('US100','MINUTE',data,ns('2026-10-26T15:01:03'))
    assert not p.observe('US100','MINUTE',{'prices':[bar(close=100),bar('2026-10-26T15:01:00')]},ns('2026-10-26T15:01:05'))
    group=p.group('US100','MINUTE');assert group['quarantined_days'] and group['revisions_after_verification']==1
    assert not p.observe('US100','MINUTE',{'prices':[bar(close=100),bar('2026-10-26T15:01:00')]},ns('2026-10-26T15:01:07'))


def test_restart_preserves_confirmation_state_and_never_duplicates_ready_bar():
    import json
    from mnq_local.capital_candles import NativeCandleProvider
    p,state,_=provider();data={'prices':[bar(),bar('2026-10-26T15:01:00')]}
    p.observe('US100','MINUTE',data,ns('2026-10-26T15:01:01'))
    other=NativeCandleProvider(json.loads(json.dumps(state)),lambda *_:None)
    assert len(other.observe('US100','MINUTE',data,ns('2026-10-26T15:01:03')))==1
    assert not other.observe('US100','MINUTE',data,ns('2026-10-26T15:01:05'))


def test_duplicate_or_invalid_batch_is_rejected_before_any_cache_mutation():
    p,state,_=provider();p.group('US100','MINUTE');import copy
    before=copy.deepcopy(state)
    with pytest.raises(ValueError):p.observe('US100','MINUTE',{'prices':[bar(),bar()]},ns('2026-10-26T15:01:01'))
    assert state==before


def test_five_minute_bar_is_not_closed_at_one_minute_and_bootstrap_is_not_forward_latency():
    p,_,_=provider();data={'prices':[bar(),bar('2026-10-26T15:05:00')]}
    assert not p.observe('US100','MINUTE_5',data,ns('2026-10-26T15:01:01'))
    assert not p.observe('US100','MINUTE_5',data,ns('2026-10-26T15:05:01'))
    ready=p.observe('US100','MINUTE_5',data,ns('2026-10-26T15:05:03'))
    assert ready[0]['end_ms']-ready[0]['start_ms']==300000
    p,_,_=provider();p.observe('US100','MINUTE',data,ns('2026-10-26T16:00:00'),bootstrap=True)
    ready=p.observe('US100','MINUTE',data,ns('2026-10-26T16:00:02'),bootstrap=True)
    assert all(r['publication_delay_upper_s'] is None for r in ready)


def test_equivalent_utc_serializations_are_not_financial_revisions_and_empty_is_invalid():
    from mnq_local.capital_candles import parse_candle
    assert parse_candle('US100','MINUTE',bar())['hash']==parse_candle('US100','MINUTE',bar('2026-10-26T15:00:00.000Z'))['hash']
    p,_,_=provider()
    with pytest.raises(ValueError):p.observe('US100','MINUTE',{'prices':[]},ns('2026-10-26T15:01:00'))


def seeded_native_broker(tmp_path,resolution='MINUTE'):
    from test_capital_demo import make,instrument_fixture
    from mnq_local.capital_candles import NativeCandleProvider,parse_candle
    from mnq_local.capital import dec
    f,h,j,b=make(tmp_path);spec=instrument_fixture();spec.raw['instrument']['lotSize']=1;spec.raw['discovery']={'tickSize':.1};b.instruments={'US100':spec}
    # Fixture identity is replaced explicitly; no network is used.
    from dataclasses import replace
    b.instruments['US100']=replace(spec,epic='US100')
    p=NativeCandleProvider(b.state,j.save);g=p.group('US100',resolution);g['bootstrapped']=True
    step=60 if resolution=='MINUTE' else 300;n=15 if step==60 else 3
    anchor=datetime(2026,10,26,13,30,tzinfo=UTC)
    for i in range(n+1):
        at=anchor+timedelta(seconds=i*step);raw=bar(at.replace(tzinfo=None).isoformat())
        if i==n:raw.update(highPrice={'bid':104,'ask':105},closePrice={'bid':103,'ask':104})
        r=parse_candle('US100',resolution,raw);r.update(verified_at_ns=(r['end_ms']+3000)*10**6,tracked_before_close=i==n,
            publication_delay_upper_s=1,verification_delay_s=3,revised_after_close=False)
        g['bars'][str(r['start_ms'])]=r
    final=max(g['bars'].values(),key=lambda r:r['start_ms']);now=final['verified_at_ns']
    b.state['quotes']['US100']={'bid':'103','ask':'104','spread':'1','timestamp_ms':now//10**6,'source':'REST_SNAPSHOT'}
    return j,b,p,now


@pytest.mark.parametrize('resolution',['MINUTE','MINUTE_5'])
def test_native_strategy_uses_closed_bid_bars_real_availability_and_no_broker_orders(tmp_path,resolution):
    from mnq_local.capital_candles import NativeStrategyEngine
    j,b,p,now=seeded_native_broker(tmp_path,resolution)
    try:
        engine=NativeStrategyEngine(p,b.state,j.save);events=engine.process(b,now)
        signal=next(e for e in events if e['strategy']=='orb')
        assert signal['side']==1 and signal['available_at_ns']==now and signal['decided_at_ns']==now
        assert signal['price_basis']=='NATIVE_BID' and signal['order_requested'] is False
        assert signal['opening_range_bars']==(15 if resolution=='MINUTE' else 3)
        assert signal['reason']=='uncertified_news_and_strategy'
        assert engine.process(b,now+2*10**9)==[]
    finally:j.close()


def test_native_context_gap_or_revision_blocks_signals(tmp_path):
    from mnq_local.capital_candles import NativeStrategyEngine
    j,b,p,now=seeded_native_broker(tmp_path)
    try:
        g=p.group('US100','MINUTE');g['bars'].pop(min(g['bars'],key=int))
        engine=NativeStrategyEngine(p,b.state,j.save);assert not engine.process(b,now)
        assert 'opening' in b.state['native_strategy_status']['US100|MINUTE']['blocked']
    finally:j.close()


def test_last_source_bar_is_not_final_just_because_local_clock_passed_end():
    p,_,_=provider();data={'prices':[bar()]}
    assert not p.observe('US100','MINUTE',data,ns('2026-10-26T15:01:01'))
    assert not p.observe('US100','MINUTE',data,ns('2026-10-26T15:01:03'))
    assert p.group('US100','MINUTE')['bars'][str(1793026800000)]['first_closed_seen_ns'] is None


def test_native_runtime_never_builds_signals_from_rest_snapshot_extrema(tmp_path):
    from mnq_local.capital_app import DemoRuntime
    from test_capital_demo import make
    _,_,j,b=make(tmp_path)
    try:
        from test_capital_demo import instrument_fixture
        spec=instrument_fixture();b.instruments={spec.epic:spec}
        now=datetime(2026,10,26,15,tzinfo=UTC);r=DemoRuntime(b,clock=lambda:now);r.native_provider=True
        class Trap:
            blocked=None;strategies=[];tick=Decimal('.1')
            def on_quote(self,q):raise AssertionError('Snapshot OHLC must not be built')
        r.sources={spec.epic:Trap()}
        assert r.on_quote({'epic':spec.epic,'product':'CFD','bid':100,'ofr':101,'timestamp':int(now.timestamp()*1000)})==[]
    finally:j.close()


def test_public_status_omits_private_native_cache_but_keeps_summaries():
    from mnq_local.capital_app import status
    cap={'native_candles':{'groups':{'large':'private'}},'native_processed':{'x':'y'},'native_summary':{'US100|MINUTE':{'cached':500}}}
    result=status(cap)['capital']
    assert 'native_candles' not in result and 'native_processed' not in result
    assert result['native_summary']==cap['native_summary'] and 'native_candles' in cap


def test_native_cycle_uses_readonly_clock_bounded_native_context_and_blocks_bad_ohlc(tmp_path):
    from mnq_local.capital_candles import NativeObservationCycle
    from mnq_local.capital_app import DemoRuntime
    from test_capital_demo import make,instrument_fixture
    _,h,j,b=make(tmp_path)
    calls=[];now=ns('2026-10-26T15:01:03')
    def request(method,path):
        calls.append((method,path))
        if path=='/time':return {'serverTime':now//10**6}
        if '/prices/' in path:return {'prices':[bar(),bar('2026-10-26T15:05:00')]}
        raise AssertionError(path)
    try:
        h.request=request;h.orders_enabled=False;b.instruments={'US100':instrument_fixture()}
        runtime=DemoRuntime(b);cycle=NativeObservationCycle(runtime,clock_ns=lambda:now)
        cycle.poll()
        assert runtime.native_provider and all(m=='GET' for m,_ in calls)
        assert any('MINUTE_5&max=500' in p for _,p in calls)
        assert b.state['native_candles']['clock']['checked_at_ns']==now
        assert not h.orders_enabled
    finally:j.close()


def test_server_clock_behind_client_cannot_close_a_source_bar_early():
    p,_,_=provider();data={'prices':[bar(),bar('2026-10-26T15:01:00')]}
    at=ns('2026-10-26T15:01:03')
    assert not p.observe('US100','MINUTE',data,at,safe_received_ms=ns('2026-10-26T15:00:59')//10**6)
    assert p.group('US100','MINUTE')['bars'][str(1793026800000)]['first_closed_seen_ns'] is None


def test_invalid_batch_blocks_group_and_preserves_rejected_source_evidence(tmp_path):
    from mnq_local.capital_candles import NativeObservationCycle
    from mnq_local.capital_app import DemoRuntime
    from test_capital_demo import make,instrument_fixture
    _,h,j,b=make(tmp_path);now=ns('2026-10-26T15:01:03')
    bad={**bar(),'closePrice':{'bid':101,'ask':100}}
    def request(method,path):
        return {'serverTime':now//10**6} if path=='/time' else {'prices':[bad,bar('2026-10-26T15:05:00')]}
    try:
        h.request=request;h.orders_enabled=False;b.instruments={'US100':instrument_fixture()}
        cycle=NativeObservationCycle(DemoRuntime(b),clock_ns=lambda:now);assert cycle.poll()==[]
        assert all(g['quarantined_days'] for g in cycle.provider.state['groups'].values())
        assert b.state['native_errors'] and not b.ready and not h.orders_enabled
        assert b.state['native_signal_count']==0
    finally:j.close()


def test_new_provider_after_restart_preserves_quarantine_and_decision_deduplication(tmp_path):
    from mnq_local.capital_candles import NativeStrategyEngine,NativeCandleProvider
    import json
    j,b,p,now=seeded_native_broker(tmp_path)
    try:
        assert len(NativeStrategyEngine(p,b.state,j.save).process(b,now))==2
        restored=json.loads(json.dumps(b.state));b.journal.cap=restored
        other=NativeCandleProvider(restored,j.save)
        assert NativeStrategyEngine(other,restored,j.save).process(b,now+10**9)==[]
        other.group('US100','MINUTE')['quarantined_days']['2026-10-26']='closed_native_bar_revision'
        assert NativeStrategyEngine(other,restored,j.save).process(b,now+2*10**9)==[]
    finally:j.close()


def test_native_price_must_match_verified_cfd_tick_grid(tmp_path):
    from mnq_local.capital_candles import NativeStrategyEngine
    j,b,p,now=seeded_native_broker(tmp_path)
    try:
        next(iter(p.group('US100','MINUTE')['bars'].values()))['prices']['close']['bid']='100.03'
        assert not NativeStrategyEngine(p,b.state,j.save).process(b,now)
        assert b.state['native_strategy_status']['US100|MINUTE']['blocked']=='native_price_off_tick_grid'
    finally:j.close()


def test_dashboard_labels_native_quality_and_real_availability():
    from mnq_local.capital_app import JS
    assert 'native_summary' in JS and 'native_strategy_status' in JS and 'feed_metrics' in JS


@pytest.mark.parametrize('fault',['kill','stale','loss_limit','position_limit'])
def test_native_decisions_obey_existing_risk_without_order_capability(tmp_path,fault):
    from mnq_local.capital_candles import NativeStrategyEngine
    j,b,p,now=seeded_native_broker(tmp_path)
    try:
        if fault=='kill':b.state['halt']='kill'
        elif fault=='stale':b.state['quotes']['US100']['timestamp_ms']=now//10**6-6000
        elif fault=='loss_limit':b.state['consecutive_losses']=100
        else:b.state['positions']=[{'position':{'size':1}}]*100
        events=NativeStrategyEngine(p,b.state,j.save).process(b,now)
        signal=next(e for e in events if e['side'])
        assert not signal['risk_allowed'] and not signal['execution_eligible'] and not signal['order_requested']
        assert not signal['strict_news_certified']
    finally:j.close()


def test_app_defers_retryable_market_bootstrap_to_guarded_native_loop(tmp_path,monkeypatch):
    import mnq_local.capital_app as app
    from test_capital_demo import make,CREDS
    from types import SimpleNamespace
    _,h,j,b=make(tmp_path);h.orders_enabled=False;calls=[]
    class Server:
        server_port=0
        def __init__(self,*args):pass
        def serve_forever(self):pass
        def shutdown(self):pass
        def server_close(self):pass
    monkeypatch.setattr(app,'Dashboard',Server);monkeypatch.setattr(app.signal,'signal',lambda *_:None)
    monkeypatch.setattr(app.Credentials,'load',lambda:CREDS);monkeypatch.setattr(app,'CapitalHTTP',lambda *a,**k:h)
    monkeypatch.setattr(app,'CapitalJournal',lambda *a,**k:j);monkeypatch.setattr(app,'CapitalBroker',lambda *a,**k:b)
    monkeypatch.setattr(app,'ROOT',tmp_path)
    monkeypatch.setattr(b,'reconcile',lambda:(_ for _ in ()).throw(AssertionError('Must run inside retry guard')))
    monkeypatch.setattr(app,'native_observer',lambda *args:calls.append(args))
    app.app(SimpleNamespace(mode='signals_only',port=0,strategy='orb',technical_test=False))
    assert len(calls)==1
