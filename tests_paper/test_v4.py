from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
import hashlib,json
import pytest
from mnq_paper.core import PaperConfig
from mnq_paper.ib import IBPaper,_Client
from mnq_paper.session import SessionProof
from test_runtime import make,candidate,SPEC


def test_du_and_paper_port_are_not_order_permission(tmp_path):
    engine,_,journal=make(tmp_path);candidate(engine)
    adapter=IBPaper(engine.config,[SPEC]);adapter.accounts=[engine.config.account];adapter.verified=True
    sent=[];adapter.app=SimpleNamespace(isConnected=lambda:True,placeOrder=lambda *a:sent.append(a))
    with pytest.raises(ConnectionError):adapter.submit(list(engine.state['orders'].values()))
    assert not sent
    journal.close()


def test_read_only_blocks_cancellation_as_well_as_submission():
    adapter=IBPaper(PaperConfig('DU12345'),[SPEC]);adapter.verified=True;adapter.accounts=['DU12345']
    calls=[];adapter.app=SimpleNamespace(isConnected=lambda:True,cancelOrder=lambda *a:calls.append(a))
    with pytest.raises(ConnectionError):adapter.cancel(1)
    assert not calls


def test_actual_sdk_config_response_has_no_paper_mode_flag():
    from ibapi.protobuf.ConfigResponse_pb2 import ConfigResponse
    adapter=IBPaper(PaperConfig('DU12345'),[SPEC]);app=_Client(adapter)
    response=ConfigResponse();response.reqId=8999;response.api.settings.readOnlyApi=True;response.api.settings.socketPort=7497
    app.configResponseProtoBuf(response)
    assert adapter.api_config['read_only'] is True
    assert 'paper_mode' not in adapter.api_config


def proof_file(tmp_path):
    evidence=tmp_path/'ui.txt';evidence.write_text('Authenticated Paper Trading; selected authorized account DU12345')
    process={'pid':123,'started':'immutable-process-start','image':'/official/IBGateway','team':'L6H6D9Q7DY'}
    value={'source':'authenticated_native_ui_observation','account':'DU12345','ui_account':'DU12345',
      'paper_indicator':'Paper Trading','authenticated':True,'port':7497,'process':process,
      'observed_at':datetime.now(timezone.utc).isoformat(),'evidence_path':str(evidence),
      'evidence_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}
    readonly=tmp_path/'read-only.json';readonly.write_text(json.dumps({'scope':'ACTUAL_IB_READ_ONLY_RESPONSES','authenticated_protocol':True,'api_read_only':True,'orders_sent':0,'account_identity':hashlib.sha256(b'DU12345').hexdigest()}))
    value.update(read_only_report_path=str(readonly),read_only_report_sha256=hashlib.sha256(readonly.read_bytes()).hexdigest())
    p=tmp_path/'session.json';p.write_text(json.dumps(value));p.chmod(0o600)
    return p,process,value


def test_session_proof_requires_independent_ui_and_exact_process(tmp_path):
    p,process,value=proof_file(tmp_path)
    proof=SessionProof(p,probe=lambda port:process)
    proof.validate(PaperConfig('DU12345'),['DU12345'])
    with pytest.raises(ValueError):proof.validate(PaperConfig('DU99999'),['DU99999'])
    with pytest.raises(ValueError):SessionProof(p,probe=lambda port:{**process,'pid':456}).validate(PaperConfig('DU12345'),['DU12345'])
    value['paper_indicator']='Live Trading';p.write_text(json.dumps(value))
    with pytest.raises(ValueError):proof.validate(PaperConfig('DU12345'),['DU12345'])


def test_expired_or_modified_evidence_is_not_reused(tmp_path):
    p,process,value=proof_file(tmp_path);value['observed_at']=(datetime.now(timezone.utc)-timedelta(hours=13)).isoformat();p.write_text(json.dumps(value))
    with pytest.raises(ValueError):SessionProof(p,probe=lambda port:process).validate(PaperConfig('DU12345'),['DU12345'])
    value['observed_at']=datetime.now(timezone.utc).isoformat();p.write_text(json.dumps(value));Path(value['evidence_path']).write_text('changed')
    with pytest.raises(ValueError):SessionProof(p,probe=lambda port:process).validate(PaperConfig('DU12345'),['DU12345'])


def test_account_summary_is_response_not_paper_certification():
    adapter=IBPaper(PaperConfig('DU12345'),[SPEC]);app=_Client(adapter)
    app.accountSummary(8000,'DU12345','AccountType','INDIVIDUAL','')
    app.accountSummaryEnd(8000)
    assert adapter.account_values['AccountType']['value']=='INDIVIDUAL'
    assert adapter.paper_proof is None


def test_missing_initial_readonly_report_cannot_enable_orders(tmp_path):
    p,process,value=proof_file(tmp_path)
    Path(value['read_only_report_path']).write_text('{}')
    with pytest.raises(ValueError):SessionProof(p,probe=lambda port:process).validate(PaperConfig('DU12345'),['DU12345'])


def test_operational_connect_without_proof_never_touches_socket(monkeypatch):
    adapter=IBPaper(PaperConfig('DU12345'),[SPEC],operation='paper_orders')
    monkeypatch.setattr(adapter,'verify_sdk',lambda:True)
    with pytest.raises(ValueError):adapter.connect()
    assert adapter.app is None


def test_missing_readonly_order_inventory_is_not_flat(monkeypatch):
    adapter=IBPaper(PaperConfig('DU12345'),[]);adapter.accounts=['DU12345'];adapter.verified=True
    adapter.api_config={'read_only':True}
    def accounts(*args):adapter.account_end=True
    def positions():adapter.ends.add('positions')
    adapter.app=SimpleNamespace(isConnected=lambda:True,reqAccountSummary=accounts,reqPositions=positions,
      reqAllOpenOrders=lambda:None,cancelAccountSummary=lambda *a:None,cancelPositions=lambda:None)
    result=adapter.read_only_inventory(timeout=.01)
    assert result['orders'] is None and result['orders_status'].startswith('unverified')


def test_expired_heartbeat_prevents_every_financial_mutator(tmp_path):
    import time
    engine,_,journal=make(tmp_path);candidate(engine)
    adapter=IBPaper(engine.config,[SPEC],operation='paper_orders');adapter.accounts=[engine.config.account];adapter.verified=True
    adapter.paper_proof=SimpleNamespace(validate=lambda *a:True)
    adapter.api_config={'read_only':False,'received_at':time.monotonic()};adapter.last_heartbeat=time.monotonic()-20
    calls=[];adapter.app=SimpleNamespace(isConnected=lambda:True,placeOrder=lambda *a:calls.append(a),cancelOrder=lambda *a:calls.append(a))
    with pytest.raises(ConnectionError):adapter.submit(list(engine.state['orders'].values()))
    with pytest.raises(ConnectionError):adapter.cancel(1)
    assert not calls
    journal.close()


def test_old_green_health_is_reported_stale(tmp_path,monkeypatch):
    import mnq_paper.v4 as v4
    monkeypatch.setattr(v4,'PRIVATE',tmp_path);monkeypatch.setattr(v4,'OUT',tmp_path/'reports')
    v4.save(tmp_path/'health.json',{'checked_at':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),'state':'READ_ONLY_HEARTBEAT_OK'})
    assert v4.status()['monitor_health']=='STALE'


def test_paper_smoke_without_proof_cannot_connect():
    from mnq_paper.smoke import run
    with pytest.raises(ValueError):run(None)
