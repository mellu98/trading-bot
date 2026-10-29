"""Offline authentication regressions; no broker authentication implied."""
import io
import json
from types import SimpleNamespace
import urllib.error
import pytest
from mnq_local import capital as c
from mnq_local import capital_app as app
from test_capital_demo import CREDS, Fixture


def fake_opener(monkeypatch, payload, status=401):
    requests=[]
    def open_(request, timeout):
        requests.append(request)
        raise urllib.error.HTTPError(request.full_url,status,'not logged',{},io.BytesIO(payload))
    monkeypatch.setattr(c.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=open_))
    return requests


def test_http_error_retains_only_safe_code_and_exact_request(monkeypatch):
    calls=fake_opener(monkeypatch,json.dumps({'errorCode':'error.invalid.details','password':'secret','message':'private'}).encode())
    status,result,headers=c.send('POST','/session',{'Content-Type':'application/json','X-CAP-API-KEY':CREDS.api_key},
        {'identifier':CREDS.identifier,'password':CREDS.password,'encryptedPassword':False})
    assert (status,result,headers)==(401,{'errorCode':'error.invalid.details'},{})
    req=calls[0]
    assert req.full_url=='https://demo-api-capital.backend-capital.com/api/v1/session'
    assert req.get_header('Content-type')=='application/json'
    assert req.get_header('X-cap-api-key')==CREDS.api_key
    assert json.loads(req.data)=={'identifier':CREDS.identifier,'password':CREDS.password,'encryptedPassword':False}


@pytest.mark.parametrize('payload',[b'<html>private</html>',b'[]',b'{',b'{"errorCode":"secret password"}',
    b'{"errorCode":"error.invalid.details","private":"'+b'x'*17000+b'"}'])
def test_bad_error_payload_is_not_retained(monkeypatch,payload):
    fake_opener(monkeypatch,payload)
    assert c.send('POST','/session',{},None)==(401,{}, {})


def test_rejection_is_safe_and_latches_authentication():
    calls=[]
    def sender(*args):calls.append(args);return 401,{'errorCode':'error.invalid.details','password':'private'},{}
    h=c.CapitalHTTP(CREDS,sender=sender,sleep=lambda _:None)
    with pytest.raises(c.CapitalError) as e:h.login()
    assert e.value.diagnostic()=={'http_status':401,'errorCode':'error.invalid.details'}
    assert 'private' not in str(e.value)
    with pytest.raises(c.CapitalError,match='authentication_retry_blocked'):h.login()
    assert len(calls)==1 and not h.verified and not h.tokens


def test_secret_in_error_code_is_never_exposed():
    creds=c.Credentials('privatekey','id@example.invalid','custompassword','DEMO1')
    h=c.CapitalHTTP(creds,sender=lambda *a:(401,{'errorCode':'error.privatekey'},{}),sleep=lambda _:None)
    with pytest.raises(c.CapitalError) as e:h.login()
    assert e.value.diagnostic()=={'http_status':401,'errorCode':None}


def test_setup_verifies_existing_session_without_second_post(monkeypatch):
    fixture=Fixture();writes=[]
    monkeypatch.setattr(app,'load_setup_credentials',lambda replace=False:CREDS)
    monkeypatch.setattr(app,'_keychain_read',lambda service:None)
    monkeypatch.setattr(app,'store_setup_credentials',lambda creds,**kw:writes.append((creds,kw)))
    monkeypatch.setattr(app,'CapitalHTTP',lambda creds,**kw:c.CapitalHTTP(creds,sender=fixture,sleep=lambda _:None,**kw))
    app.setup()
    assert sum(m=='POST' for m,p,b in fixture.calls)==1
    assert [p for m,p,b in fixture.calls]==['/session','/session','/accounts']
    assert writes[-1][0]==CREDS and writes[-1][1]['verified'] is True


def test_auth_only_client_cannot_send_orders_after_verified():
    f=Fixture();h=c.CapitalHTTP(CREDS,sender=f,sleep=lambda _:None,orders_enabled=False);h.login()
    for method,path in [('POST','/positions'),('POST','/workingorders'),('DELETE','/positions/any')]:
        with pytest.raises(c.CapitalError,match='orders_disabled'):h.request(method,path,{})
    assert len(f.calls)==3


def test_saved_failed_setup_never_prompts_or_reposts(monkeypatch):
    record={'credentials':{'api_key':CREDS.api_key,'identifier':CREDS.identifier,'password':CREDS.password,'account':CREDS.account},
        'attempted':True,'diagnostic':{'http_status':401,'errorCode':'error.invalid.details'}}
    def run(args,**kwargs):
        return SimpleNamespace(returncode=0 if args[args.index('-s')+1]==c.SERVICE+'.pending' else 44,
            stdout=json.dumps(record),stderr='')
    monkeypatch.setattr(app.subprocess,'run',run)
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:pytest.fail('Repeated credential prompt'))
    assert app.load_setup_credentials()==CREDS
    with pytest.raises(SystemExit):app.setup(allow_prompt=False,diagnostic_only=True)


@pytest.mark.parametrize('key',['fixture key','fixture\tkey','fixture\x00key','fixture\rkey','fixture\nkey'])
def test_key_control_and_whitespace_rejected_before_transport(key):
    with pytest.raises(c.CapitalError):c.Credentials(key,CREDS.identifier,CREDS.password,CREDS.account)


def test_setup_failure_one_post_saved_once_and_only_safe_output(monkeypatch,capsys):
    calls=[];writes=[]
    def sender(*args):calls.append(args);return 401,{'errorCode':'error.invalid.details','message':'private'},{}
    monkeypatch.setattr(app,'load_setup_credentials',lambda replace=False:CREDS)
    monkeypatch.setattr(app,'_keychain_read',lambda service:None)
    monkeypatch.setattr(app,'store_setup_credentials',lambda creds,**kw:writes.append((creds,kw)))
    monkeypatch.setattr(app,'CapitalHTTP',lambda creds,**kw:c.CapitalHTTP(creds,sender=sender,sleep=lambda _:None,**kw))
    with pytest.raises(SystemExit) as e:app.setup()
    assert e.value.code==1 and len(calls)==1
    output=json.loads(capsys.readouterr().out)
    assert output['http_status']==401 and output['errorCode']=='error.invalid.details'
    assert output['status']=='BLOCKED' and output['reason']=='api_request_rejected'
    assert 'private' not in json.dumps(output)
    assert writes[0][1]=={'attempted':False}
    assert writes[1][1]=={'attempted':True}
    assert writes[-1][1]['diagnostic']=={'http_status':401,'errorCode':'error.invalid.details'}


def test_keychain_staging_secrets_only_in_stdin(monkeypatch):
    calls=[]
    def run(args,**kwargs):calls.append((args,kwargs));return SimpleNamespace(returncode=0)
    monkeypatch.setattr(app.subprocess,'run',run)
    monkeypatch.setattr(app,'_keychain_read',lambda service:json.dumps({'credentials':{'api_key':CREDS.api_key,'identifier':CREDS.identifier,'password':CREDS.password,'account':CREDS.account},'api_key_label':'claude','attempted':True,'diagnostic':None}))
    app.store_setup_credentials(CREDS)
    args,kwargs=calls[0]
    assert args==['security','-i'] and kwargs['capture_output'] is True
    assert CREDS.password not in kwargs['input'] and CREDS.api_key not in kwargs['input']
    decoded=c.decode_keychain_value(kwargs['input'].split(' -w ',1)[1].strip())
    assert CREDS.password in decoded and CREDS.api_key in decoded
    assert 'stdout' not in kwargs and 'stderr' not in kwargs


def test_keychain_mismatched_key_blocks_before_auth_or_prompt(monkeypatch):
    def read(service):
        if service==c.SERVICE+'.api-key':return 'different-key'
        if service==c.SERVICE:return json.dumps({'api_key':CREDS.api_key,'identifier':CREDS.identifier,'password':CREDS.password,'account':CREDS.account})
    monkeypatch.setattr(app,'_keychain_read',read)
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:pytest.fail('No prompt'))
    with pytest.raises(c.CapitalError,match='keychain_api_key_mismatch'):app.load_setup_credentials()


def test_pending_rejection_blocks_runtime_keychain_loader(monkeypatch):
    def run(args,**kwargs):
        service=args[args.index('-s')+1]
        record={'attempted':True} if service==c.SERVICE+'.pending' else {'api_key':CREDS.api_key,'identifier':CREDS.identifier,'password':CREDS.password,'account':CREDS.account}
        return SimpleNamespace(returncode=0,stdout=json.dumps(record))
    monkeypatch.setattr(c.subprocess,'run',run)
    for name in ('API_KEY','IDENTIFIER','PASSWORD','ACCOUNT_ID'):monkeypatch.delenv('CAPITAL_DEMO_'+name,raising=False)
    with pytest.raises(c.CapitalError,match='authentication_retry_blocked'):c.Credentials.load()


def test_verified_replacement_updates_standalone_key_without_argv_secrets(monkeypatch):
    calls=[]
    def run(args,**kwargs):calls.append((args,kwargs));return SimpleNamespace(returncode=0)
    monkeypatch.setattr(app.subprocess,'run',run)
    monkeypatch.setattr(app,'_keychain_read',lambda service:CREDS.api_key if service.endswith('.api-key') else json.dumps({'api_key':CREDS.api_key,'identifier':CREDS.identifier,'password':CREDS.password,'account':CREDS.account}))
    app.store_setup_credentials(CREDS,verified=True)
    writes=[kw['input'] for args,kw in calls if args==['security','-i']]
    assert len(writes)==2
    assert any(c.SERVICE+'.api-key' in command and c.decode_keychain_value(command.split(' -w ',1)[1].strip())==CREDS.api_key for command in writes)
    assert all(CREDS.api_key not in str(args) and CREDS.password not in str(args) for args,kw in calls)


def test_setup_reports_local_cause_not_two_unexplained_nulls(monkeypatch,capsys,tmp_path):
    def fail(*args,**kwargs):raise c.CapitalError('missing_identifier_and_custom_api_password')
    monkeypatch.setattr(app,'load_setup_credentials',fail)
    monkeypatch.setattr(app,'_keychain_read',lambda service:None)
    monkeypatch.setattr(app,'ROOT',tmp_path)
    with pytest.raises(SystemExit):app.setup(allow_prompt=False)
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='BLOCKED'
    assert value['reason']=='missing_identifier_and_custom_api_password'
    assert value['phase']=='credentials'
    assert value['authentication_requests']==0
    assert value['http_status'] is None and value['errorCode'] is None
    assert value['orders_enabled'] is False


def test_saved_only_does_not_prompt_when_only_key_exists(monkeypatch):
    monkeypatch.setattr(app,'_keychain_read',lambda service:'fixture-key' if service==c.SERVICE+'.api-key' else None)
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:pytest.fail('Must not ask again'))
    with pytest.raises(c.CapitalError,match='missing_identifier_and_custom_api_password'):
        app.load_setup_credentials(allow_prompt=False)


def test_http_200_missing_tokens_is_recorded_without_tokens():
    h=c.CapitalHTTP(CREDS,sender=lambda *a:(200,{}, {'cst':'private-token'}),sleep=lambda _:None,orders_enabled=False)
    with pytest.raises(c.CapitalError,match='missing_session_tokens'):h.login()
    assert h.session_evidence=={'http_status':200,'cst_present':True,'security_token_present':False}
    assert 'private-token' not in str(h.session_evidence)


def test_setup_200_then_local_validation_failure_preserves_evidence(monkeypatch,capsys,tmp_path):
    monkeypatch.setattr(app,'ROOT',tmp_path)
    monkeypatch.setattr(app,'load_setup_credentials',lambda *a,**kw:CREDS)
    monkeypatch.setattr(app,'_keychain_read',lambda service:None)
    monkeypatch.setattr(app,'store_setup_credentials',lambda *a,**kw:None)
    def sender(*args):return 200,{'hasActiveDemoAccounts':False},{'CST':'private-cst','X-SECURITY-TOKEN':'private-token'}
    monkeypatch.setattr(app,'CapitalHTTP',lambda creds,**kw:c.CapitalHTTP(creds,sender=sender,sleep=lambda _:None,**kw))
    with pytest.raises(SystemExit):app.setup(allow_prompt=False)
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='BLOCKED' and value['reason']=='no_active_demo_account'
    assert value['session_response']=={'http_status':200,'cst_present':True,'security_token_present':True}
    assert value['authentication_requests']==1
    assert 'private' not in json.dumps(value)


def test_keychain_error_has_stage_and_no_auth_attempt(monkeypatch,capsys):
    monkeypatch.setattr(app,'load_setup_credentials',lambda *a,**kw:CREDS)
    monkeypatch.setattr(app,'_keychain_read',lambda service:None)
    def fail(*a,**kw):raise c.CapitalError('keychain_storage_failed')
    monkeypatch.setattr(app,'store_setup_credentials',fail)
    monkeypatch.setattr(app,'CapitalHTTP',lambda *a,**kw:pytest.fail('No POST before secure staging'))
    with pytest.raises(SystemExit):app.setup(allow_prompt=False)
    value=json.loads(capsys.readouterr().out)
    assert value['status']=='BLOCKED' and value['reason']=='keychain_storage_failed'
    assert value['phase']=='keychain_configuration' and value['authentication_requests']==0
    assert value['session_response'] is None
