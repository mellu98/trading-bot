"""Credential lifecycle regression tests; no real broker is contacted."""
from dataclasses import asdict
import json
import shlex
from types import SimpleNamespace
import pytest
from mnq_local import capital as c, capital_app as app
from test_capital_demo import CREDS,Fixture


@pytest.fixture
def keychain(monkeypatch):
    records={c.SERVICE+'.api-key':CREDS.api_key};calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        if args==['security','-i']:
            parts=shlex.split(kwargs['input']);records[parts[parts.index('-s')+1]]=c.decode_keychain_value(parts[parts.index('-w')+1])
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        name=args[args.index('-s')+1]
        if args[1]=='find-generic-password':return SimpleNamespace(returncode=0 if name in records else 44,stdout=records.get(name,'')+'\n',stderr='')
        if args[1]=='delete-generic-password':records.pop(name,None);return SimpleNamespace(returncode=0,stdout='',stderr='')
        pytest.fail('Unexpected Keychain command')
    monkeypatch.setattr(app.subprocess,'run',run)
    return records,calls


def test_configure_is_offline_readback_and_prompts_only_once(keychain,monkeypatch):
    records,calls=keychain;answers=iter([CREDS.identifier,CREDS.password]);prompts=[]
    def prompt(label):prompts.append(label);return next(answers)
    monkeypatch.setattr(app.getpass,'getpass',prompt)
    monkeypatch.setattr(app,'CapitalHTTP',lambda *a,**kw:pytest.fail('Configuration must not use HTTP'))
    creds=app.configure_credentials()
    assert len(prompts)==2 and creds.api_key==CREDS.api_key
    record=json.loads(records[c.SERVICE+'.pending'])
    assert record['credentials']==asdict(creds) and record['attempted'] is False
    assert app.configure_credentials()==creds and len(prompts)==2
    assert records[c.SERVICE+'.api-key']==CREDS.api_key
    assert all(CREDS.password not in str(args) for args,kw in calls)


@pytest.mark.parametrize('status',[401,403])
def test_failed_diagnostic_retains_all_credentials_and_never_retries(keychain,monkeypatch,capsys,status):
    records,_=keychain;answers=iter([CREDS.identifier,CREDS.password])
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:next(answers))
    app.configure_credentials();requests=[]
    def sender(*args):requests.append(args);return status,{'errorCode':'error.invalid.details'},{}
    monkeypatch.setattr(app,'CapitalHTTP',lambda creds,**kw:c.CapitalHTTP(creds,sender=sender,sleep=lambda _:None,**kw))
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:pytest.fail('No repeated prompts'))
    for _ in range(2):
        with pytest.raises(SystemExit):app.setup(allow_prompt=False,diagnostic_only=True)
        value=json.loads(capsys.readouterr().out)
        assert set(value)=={'http_status','errorCode','phase'}
        assert value['http_status']==status and value['errorCode']=='error.invalid.details'
    record=json.loads(records[c.SERVICE+'.pending'])
    assert record['credentials']['identifier']==CREDS.identifier
    assert record['credentials']['password']==CREDS.password
    assert record['credentials']['api_key']==CREDS.api_key
    assert len(requests)==1 and record['attempted'] is True


def test_readback_failure_stops_before_auth(keychain,monkeypatch,capsys):
    records,_=keychain;answers=iter([CREDS.identifier,CREDS.password])
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:next(answers))
    original=app._keychain_read
    monkeypatch.setattr(app,'_keychain_read',lambda service:None if service==c.SERVICE+'.pending' else original(service))
    monkeypatch.setattr(app,'CapitalHTTP',lambda *a,**kw:pytest.fail('No network before readback'))
    with pytest.raises(c.CapitalError,match='keychain_readback_failed'):app.configure_credentials()
    assert c.SERVICE+'.pending' in records


def test_success_saves_verified_credentials_without_second_login(keychain,monkeypatch,capsys):
    records,_=keychain;answers=iter([CREDS.identifier,CREDS.password]);fixture=Fixture()
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:next(answers))
    app.configure_credentials()
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:pytest.fail('No repeated input'))
    monkeypatch.setattr(app,'CapitalHTTP',lambda creds,**kw:c.CapitalHTTP(creds,sender=fixture,sleep=lambda _:None,**kw))
    http=app.setup(allow_prompt=False,diagnostic_only=True)
    assert http.verified and not http.orders_enabled
    assert json.loads(records[c.SERVICE])==asdict(CREDS)
    assert [p for m,p,b in fixture.calls]==['/session','/session','/accounts']
    assert json.loads(capsys.readouterr().out)['phase']=='AUTHENTICATED_DEMO'


def test_changed_credentials_require_explicit_choice_to_reset_rejection(keychain,monkeypatch):
    records,_=keychain
    records[c.SERVICE+'.pending']=json.dumps({'credentials':asdict(CREDS),'attempted':True,'diagnostic':{'http_status':401,'errorCode':'error.invalid.details','phase':'session_post'}})
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:pytest.fail('Default must reuse saved values'))
    assert app.configure_credentials()==CREDS
    assert json.loads(records[c.SERVICE+'.pending'])['attempted'] is True
    answers=iter([CREDS.identifier,'new-fixture-password'])
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:next(answers))
    changed=app.configure_credentials(replace=True)
    assert changed.api_key==CREDS.api_key and changed.password=='new-fixture-password'
    assert json.loads(records[c.SERVICE+'.pending'])['attempted'] is False


def test_special_character_password_uses_safe_single_token_transport(keychain,monkeypatch):
    records,calls=keychain
    answers=iter([CREDS.identifier,'fixture apostrophe\' double" slash\\ unicode-é'])
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:next(answers))
    creds=app.configure_credentials()
    command=next(kw['input'] for args,kw in calls if args==['security','-i'])
    token=command.split(' -w ',1)[1].strip()
    assert token.startswith('capital-b64-v1:')
    assert all(ch.isascii() and not ch.isspace() and ch not in '\'"\\' for ch in token)
    assert c.decode_keychain_value(token)==json.dumps({'credentials':asdict(creds),'api_key_label':'claude','attempted':False,'diagnostic':None})


@pytest.mark.parametrize('value',['capital-b64-v1:!invalid','capital-b64-v1:/w=='])
def test_invalid_encoded_keychain_record_fails_closed(value):
    with pytest.raises(c.CapitalError,match='malformed_demo_keychain_record'):c.decode_keychain_value(value)


def test_process_interruption_after_attempt_mark_never_reposts(keychain,monkeypatch,capsys):
    records,_=keychain;answers=iter([CREDS.identifier,CREDS.password]);calls=[]
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:next(answers));app.configure_credentials()
    def sender(*a):calls.append(1);raise KeyboardInterrupt()
    monkeypatch.setattr(app,'CapitalHTTP',lambda creds,**kw:c.CapitalHTTP(creds,sender=sender,sleep=lambda _:None,**kw))
    with pytest.raises(KeyboardInterrupt):app.setup(allow_prompt=False,diagnostic_only=True)
    assert json.loads(records[c.SERVICE+'.pending'])['attempted'] is True
    with pytest.raises(SystemExit):app.setup(allow_prompt=False,diagnostic_only=True)
    assert len(calls)==1
    assert json.loads(capsys.readouterr().out)['phase']=='saved_attempt.authentication_retry_blocked'


def test_encoded_verified_record_loads_in_runtime(monkeypatch):
    def run(args,**kw):
        if args[args.index('-s')+1]==c.SERVICE+'.pending':return SimpleNamespace(returncode=44,stdout='')
        return SimpleNamespace(returncode=0,stdout=c.encode_keychain_value(json.dumps(asdict(CREDS)))+'\n')
    monkeypatch.setattr(c.subprocess,'run',run)
    for name in ('API_KEY','IDENTIFIER','PASSWORD','ACCOUNT_ID'):monkeypatch.delenv('CAPITAL_DEMO_'+name,raising=False)
    assert c.Credentials.load()==CREDS


def test_keychain_access_failure_does_not_trigger_new_input(monkeypatch):
    monkeypatch.setattr(app.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=36,stdout=''))
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:pytest.fail('No prompt on locked/inaccessible Keychain'))
    with pytest.raises(c.CapitalError,match='keychain_access_failed'):app.configure_credentials()


def test_setup_cli_hands_same_verified_session_to_order_disabled_monitor(monkeypatch,tmp_path):
    import sys
    captured=[]
    http=c.CapitalHTTP(CREDS,sender=Fixture(),sleep=lambda _:None,orders_enabled=False);http.login()
    monkeypatch.setattr(app,'setup',lambda *a,**kw:http)
    monkeypatch.setattr(app,'app',lambda args,**kw:captured.append((args.mode,args.technical_test,kw['session'])))
    monkeypatch.setattr(sys,'argv',['capital_app','setup','--mode','diagnostic_demo','--technical-test'])
    app.main()
    assert captured==[('signals_only',False,http)]


def test_auth_failure_reports_credentials_already_saved(keychain,monkeypatch,capsys):
    answers=iter([CREDS.identifier,CREDS.password])
    monkeypatch.setattr(app.getpass,'getpass',lambda *a:next(answers))
    app.configure_credentials()
    monkeypatch.setattr(app,'CapitalHTTP',lambda creds,**kw:c.CapitalHTTP(creds,sender=lambda *a:(401,{'errorCode':'error.invalid.details'},{}),sleep=lambda _:None,**kw))
    with pytest.raises(SystemExit):app.setup(allow_prompt=False)
    output=json.loads(capsys.readouterr().out)
    assert output['credentials_saved'] is True
    assert output['status']=='BLOCKED' and output['phase']=='session_post'
