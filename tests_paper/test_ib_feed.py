from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from decimal import Decimal
import time
import pytest
from mnq_paper.core import PaperConfig, ContractSpec
from mnq_paper.ib import IBPaper, _Client
from mnq_paper.feed import MinuteFeed
from test_runtime import make, candidate, NOW, SPEC


def allow_explicit_mock_paper_session(adapter):
    # Test fixture only: verifies real SDK encoding, NOT real broker certification.
    adapter.operation='paper_orders'
    adapter.paper_proof=SimpleNamespace(validate=lambda *args:True)
    adapter.api_config={'read_only':False,'received_at':time.monotonic()}
    adapter.last_heartbeat=time.monotonic()


def test_actual_official_sdk_builds_native_bracket(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    adapter=IBPaper(engine.config,[SPEC]);adapter.accounts=[engine.config.account];adapter.verified=True;allow_explicit_mock_paper_session(adapter)
    sent=[];adapter.app=SimpleNamespace(isConnected=lambda:True,placeOrder=lambda oid,c,o:sent.append((oid,c,o)))
    adapter.submit(list(engine.state['orders'].values()))
    assert len(sent)==3
    assert [o.transmit for _,_,o in sent]==[False,False,True]
    assert [o.orderType for _,_,o in sent]==['LMT','LMT','STP']
    assert all(o.account=='DU12345' and isinstance(o.totalQuantity,Decimal) for _,_,o in sent)
    assert all(c.secType=='FUT' and c.conId==SPEC.con_id and c.exchange=='CME' for _,c,_ in sent)
    assert sent[-1][2].parentId==sent[0][0]
    assert sent[1][2].ocaGroup==sent[2][2].ocaGroup
    journal.close()


def test_actual_sdk_encodes_order_messages_without_network(tmp_path):
    from ibapi.server_versions import MAX_CLIENT_VER
    engine,broker,journal=make(tmp_path);candidate(engine)
    adapter=IBPaper(engine.config,[SPEC]);adapter.accounts=[engine.config.account];adapter.verified=True;allow_explicit_mock_paper_session(adapter)
    app=_Client(adapter);app.isConnected=lambda:True;app.serverVersion=lambda:MAX_CLIENT_VER
    messages=[];app.sendMsg=lambda msgid,msg:messages.append((msgid,msg));app.sendMsgProtoBuf=lambda msgid,msg:messages.append((msgid,msg))
    adapter.app=app;adapter.submit(list(engine.state['orders'].values()))
    assert len(messages)==3
    assert all(message for _,message in messages)
    assert adapter.events.empty()
    journal.close()


def test_paper_guard_requires_actual_managed_account_identity():
    cfg=PaperConfig('DU12345');adapter=IBPaper(cfg,[SPEC]);adapter.verified=True;adapter.accounts=['U12345']
    adapter.app=SimpleNamespace(isConnected=lambda:True)
    with pytest.raises(ConnectionError):adapter.submit([])


def test_current_sdk_error_signature_is_sanitized():
    adapter=IBPaper(PaperConfig('DU12345'),[SPEC]);app=_Client(adapter)
    app.error(1,1234,201,'sensitive diagnostic should not leave adapter','sensitive JSON')
    event=adapter.events.get_nowait()
    assert event=={'type':'error','code':201,'request_id':1}


def test_execution_time_rejects_ambiguous_timezone():
    assert IBPaper.execution_time('20261019 14:00:00 UTC')=='2026-10-19T14:00:00+00:00'
    with pytest.raises(ValueError):IBPaper.execution_time('20261019 14:00:00')


def five(i):
    ns=int(datetime(2026,10,19,13,30,tzinfo=timezone.utc).timestamp())*10**9+i*5*10**9
    return {'symbol':'MES','start_ns':ns,'open':100.,'high':101.,'low':99.,'close':100.,'volume':1.}


def test_complete_minute_uses_exact_ns_and_actual_volume():
    feed=MinuteFeed([SPEC]);now=NOW
    for i in range(11):assert feed.push(five(i),now) is None
    bar=feed.push(five(11),now)
    assert bar.volume==12 and bar.start.isoformat()=='2026-10-19T13:30:00+00:00'
    assert bar.available_at==now


def test_missing_5seconds_never_filled():
    feed=MinuteFeed([SPEC])
    for i in range(10):feed.push(five(i),NOW)
    with pytest.raises(ValueError):feed.push(five(11),NOW)


def test_duplicate_conflict_and_noninteger_ns_rejected():
    feed=MinuteFeed([SPEC]);feed.push(five(0),NOW);assert feed.push(five(0),NOW) is None
    with pytest.raises(ValueError):feed.push({**five(0),'volume':2.},NOW)
    with pytest.raises(ValueError):MinuteFeed([SPEC]).push({**five(0),'start_ns':float(five(0)['start_ns'])},NOW)


def test_no_partial_bracket_is_sent_if_validation_fails(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    adapter=IBPaper(engine.config,[SPEC]);adapter.accounts=[engine.config.account];adapter.verified=True;allow_explicit_mock_paper_session(adapter)
    sent=[];adapter.app=SimpleNamespace(isConnected=lambda:True,placeOrder=lambda *args:sent.append(args))
    orders=[dict(o) for o in engine.state['orders'].values()];orders[-1]['quantity']=2
    with pytest.raises(ValueError):adapter.submit(orders)
    assert not sent
    journal.close()


def test_explicit_operator_utc_is_required_for_broker_zone_less_times():
    assert IBPaper.execution_time('20261019 14:00:00','UTC')=='2026-10-19T14:00:00+00:00'


def test_ambiguous_execution_callback_emits_safe_error_not_reader_exception():
    adapter=IBPaper(PaperConfig('DU12345'),[SPEC]);app=_Client(adapter)
    app.execDetails(1,SimpleNamespace(conId=SPEC.con_id),SimpleNamespace(time='20261019 14:00:00'))
    assert adapter.events.get_nowait()['code']==1000001


def test_server_side_parent_expiry_and_persistent_protection(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    adapter=IBPaper(engine.config,[SPEC]);adapter.accounts=[engine.config.account];adapter.verified=True;allow_explicit_mock_paper_session(adapter)
    sent=[];adapter.app=SimpleNamespace(isConnected=lambda:True,placeOrder=lambda oid,c,o:sent.append(o))
    adapter.submit(list(engine.state['orders'].values()))
    assert sent[0].tif=='GTD' and sent[0].goodTillDate=='20261019 14:01:00 UTC'
    assert all(o.tif=='GTC' for o in sent[1:])
    journal.close()
