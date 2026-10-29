"""Hidden input/validation regressions using dummy credentials only."""
import getpass
import warnings
import pytest
from mnq_local import capital as c,capital_app as app


@pytest.mark.parametrize('password',[" leading",'trailing ', ' both ', '\tfixture\t', '\u00a0fixture\u00a0', 'é日本😀', "quote' double\" slash\\", 'line\nfeed', 'carriage\rreturn'])
def test_password_is_not_stripped_normalized_or_arbitrarily_rejected(password):
    creds=c.Credentials('fixturekey','fixture@example.invalid',password,'UNBOUND')
    assert creds.password==password
    assert c.decode_keychain_value(c.encode_keychain_value(password))==password


@pytest.mark.parametrize('field,value,code',[
    ('api_key','', 'credential_api_key_empty'),
    ('identifier','', 'credential_identifier_empty'),
    ('password','', 'credential_password_empty'),
    ('identifier',' fixture@example.invalid','credential_identifier_boundary_whitespace'),
    ('identifier','fixture\n@example.invalid','credential_identifier_control_character'),
    ('password',None,'credential_password_wrong_type'),
    ('api_key','fixture key','credential_api_key_invalid_character'),
])
def test_validation_identifies_exact_field_without_exposing_values(field,value,code):
    args={'api_key':'fixturekey','identifier':'fixture@example.invalid','password':'fixture password','account':'UNBOUND'}
    args[field]=value
    with pytest.raises(c.CapitalError) as caught:c.Credentials(**args)
    assert caught.value.code==code
    assert 'fixture' not in str(caught.value)


@pytest.mark.parametrize('field',['identifier','password'])
def test_getpass_echo_fallback_is_blocked_before_reading(monkeypatch,field):
    def insecure(*a,**kw):
        warnings.warn('dummy warning',getpass.GetPassWarning)
        pytest.fail('Must stop before echoed input')
    monkeypatch.setattr(app.getpass,'getpass',insecure)
    with pytest.raises(c.CapitalError,match='hidden_input_unavailable_'+field):app.hidden_input(field)


@pytest.mark.parametrize('field',['identifier','password'])
@pytest.mark.parametrize('error,code',[(EOFError,'hidden_input_eof_'),(KeyboardInterrupt,'hidden_input_cancelled_'),(UnicodeError,'hidden_input_encoding_failed_')])
def test_input_failures_are_not_misreported_as_empty_credentials(monkeypatch,field,error,code):
    def fail(*a,**kw):raise error()
    monkeypatch.setattr(app.getpass,'getpass',fail)
    with pytest.raises(c.CapitalError,match=code+field):app.hidden_input(field)


def test_hidden_input_preserves_exact_unicode_and_boundary_whitespace(monkeypatch):
    value=' \t日本😀é\u00a0 '
    monkeypatch.setattr(app.getpass,'getpass',lambda *a,**kw:value)
    assert app.hidden_input('password')==value


def test_actual_hidden_tty_and_real_keychain_roundtrip():
    """macOS local integration only; dummy input, zero Capital HTTP requests."""
    import json
    import os
    from pathlib import Path
    import pty
    import select
    import shlex
    import signal
    import subprocess
    import sys
    import termios
    import time
    if sys.platform!='darwin':pytest.skip('macOS Keychain integration')
    service=c.SERVICE+'.hidden-input-probe'
    identifier='fixture-pty@example.invalid'
    password=' \tFïxture\' " \\ 日本😀\u00a0 '
    key='fixturekey'
    command='add-generic-password -U -a trading-bot -s '+shlex.quote(service+'.api-key')+' -w '+c.encode_keychain_value(key)+'\n'
    write=subprocess.run(['security','-i'],input=command,text=True,capture_output=True)
    assert write.returncode==0
    transcript=b'';pid=None;fd=None;report={'phase':'hidden_tty_keychain','dummy_only':True}
    try:
        child='''import json
from mnq_local import capital_app as a
from mnq_local.capital import CapitalError
a.SERVICE='''+repr(service)+'''
def no_http(*args,**kwargs):raise RuntimeError('unexpected_http')
a.CapitalHTTP=no_http
try:
 a.configure_credentials()
 print(json.dumps({'phase':'local_configuration_verified','credentials_saved':True}),flush=True)
except CapitalError as e:
 print(json.dumps({'phase':e.code,'credentials_saved':False}),flush=True)
 raise SystemExit(1)
'''
        pid,fd=pty.fork()
        if pid==0:
            env=dict(os.environ)
            os.execve(sys.executable,[sys.executable,'-c',child],env)
        deadline=time.monotonic()+15
        def until(marker):
            nonlocal transcript
            while marker not in transcript:
                assert time.monotonic()<deadline,'Hidden-input probe timed out'
                ready,_,_=select.select([fd],[],[],.1)
                if ready:
                    block=os.read(fd,4096)
                    assert block,'Hidden-input probe ended before prompt'
                    transcript+=block
        until(b'Capital login identifier: ')
        report['identifier_echo_disabled']=not bool(termios.tcgetattr(fd)[3]&termios.ECHO)
        assert report['identifier_echo_disabled']
        os.write(fd,(identifier+'\n').encode('utf-8'))
        until(b'API key CUSTOM password (not login password): ')
        report['password_echo_disabled']=not bool(termios.tcgetattr(fd)[3]&termios.ECHO)
        assert report['password_echo_disabled']
        os.write(fd,(password+'\n').encode('utf-8'))
        until(b'"credentials_saved": true')
        _,status=os.waitpid(pid,0);pid=None
        report['child_succeeded']=os.waitstatus_to_exitcode(status)==0
        report['input_values_not_echoed']=identifier.encode() not in transcript and password.encode() not in transcript
        record=subprocess.run(['security','find-generic-password','-a','trading-bot','-s',service+'.pending','-w'],capture_output=True,text=True)
        decoded=json.loads(c.decode_keychain_value(record.stdout.removesuffix('\n')))
        actual=decoded['credentials']
        report['identifier_exact_readback']=actual['identifier']==identifier
        report['password_exact_readback']=actual['password']==password
        report['api_key_exact_readback']=actual['api_key']==key
        report['authentication_not_attempted']=decoded['attempted'] is False
        assert all(value for value in report.values() if isinstance(value,bool))
    finally:
        if pid is not None:
            os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
        if fd is not None:os.close(fd)
        for suffix in ('.api-key','.pending',''):
            subprocess.run(['security','delete-generic-password','-a','trading-bot','-s',service+suffix],capture_output=True)
        report['dummy_records_removed']=all(subprocess.run(['security','find-generic-password','-a','trading-bot','-s',service+x,'-w'],capture_output=True).returncode==44 for x in ('.api-key','.pending',''))
        path=Path(__file__).resolve().parents[1]/'reports/capital-input/tty-keychain-probe.json'
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n')


def test_bad_stored_key_fails_before_any_hidden_prompt(monkeypatch):
    monkeypatch.setattr(app,'_keychain_read',lambda service:'invalid fixture key' if service==c.SERVICE+'.api-key' else None)
    monkeypatch.setattr(app.getpass,'getpass',lambda *a,**kw:pytest.fail('Validate key before asking for input'))
    with pytest.raises(c.CapitalError,match='credential_api_key_invalid_character'):app.load_setup_credentials()


def test_empty_identifier_fails_before_password_prompt(monkeypatch):
    monkeypatch.setattr(app,'_keychain_read',lambda service:'fixturekey' if service==c.SERVICE+'.api-key' else None)
    calls=[]
    def prompt(label):
        calls.append(label)
        assert len(calls)==1,'Invalid identifier must not trigger a password prompt'
        return ''
    monkeypatch.setattr(app.getpass,'getpass',prompt)
    with pytest.raises(c.CapitalError,match='credential_identifier_empty'):app.load_setup_credentials()
    assert len(calls)==1


def test_actual_no_tty_cannot_fall_back_to_echoed_input():
    import json
    import subprocess
    import sys
    code='''import json
from mnq_local.capital_app import hidden_input
from mnq_local.capital import CapitalError
try:hidden_input('password')
except CapitalError as e:print(json.dumps({'phase':e.code,'input_unavailable':True}))
'''
    result=subprocess.run([sys.executable,'-c',code],stdin=subprocess.DEVNULL,capture_output=True,text=True,start_new_session=True,timeout=5)
    value=json.loads(result.stdout)
    assert value=={'phase':'hidden_input_unavailable_password','input_unavailable':True}
    assert 'Warning' not in result.stderr and 'echoed' not in result.stderr


@pytest.mark.parametrize('code,phase',[
    ('hidden_input_eof_password','credential_input'),
    ('credential_password_empty','credential_validation'),
    ('keychain_storage_failed','keychain_configuration'),
    ('keychain_readback_failed','keychain_configuration'),
])
def test_setup_reports_distinct_pre_http_failure_phase(monkeypatch,capsys,code,phase):
    import json
    def fail(*args,**kwargs):raise c.CapitalError(code)
    monkeypatch.setattr(app,'configure_credentials',fail)
    with pytest.raises(SystemExit):app.setup(allow_prompt=False)
    report=json.loads(capsys.readouterr().out)
    assert report['phase']==phase and report['reason']==code
    assert report['authentication_requests']==0
