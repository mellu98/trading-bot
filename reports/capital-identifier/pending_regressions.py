"""Dummy-only terminal paste regressions; no broker requests."""
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
import pytest
from mnq_local import capital as c,capital_app as app

ID='fixture+tag.o\'name@example.invalid'
PW=' \tFïxture\' " \\ 日本😀\u00a0 '


@pytest.mark.parametrize('value',[ID+'\n',ID+'\r\n',' \t'+ID+'\u00a0\r\n'])
def test_identifier_boundary_normalization_only(value):
    assert app.normalize_identifier_input(value)==ID


@pytest.mark.parametrize('value',['\x01'+ID,ID+'\x01',ID.replace('@','\t@'),ID.replace('@','\n@'),ID.replace('@','\x85@')])
def test_real_internal_controls_are_rejected_not_removed(value):
    with pytest.raises(c.CapitalError,match='credential_identifier_control_character'):
        c.validate_credential_field('identifier',app.normalize_identifier_input(value))


CASES=[
 pytest.param((ID+'\n').encode(),True,False,ID,id='typed_lf'),
 pytest.param((ID+'\n').encode(),False,False,ID,id='paste_lf'),
 pytest.param((ID+'\r\n').encode(),False,False,ID,id='paste_crlf'),
 pytest.param((' \t'+ID+'\u00a0\r\n').encode(),False,False,ID,id='paste_outer_whitespace'),
 pytest.param(b'\x1b[200~'+ID.encode()+b'\x1b[201~\r',False,False,ID,id='bracketed_paste'),
 pytest.param(b'\x1b[200~'+ID.encode()+b'\n\x1b[201~\r',False,False,ID,id='bracketed_paste_trailing_lf'),
 pytest.param(b'\x1b[200~'+ID.encode()+b'\r\n\x1b[201~\r\n',False,False,ID,id='bracketed_paste_trailing_crlf'),
 pytest.param(b'\x1b[200~'+ID.encode().replace(b'@',b'\t@')+b'\x1b[201~\r',False,True,ID,id='reject_pasted_internal_tab'),
 pytest.param(b'\x1b[200~'+ID.encode().replace(b'@',b'\n@')+b'\x1b[201~\r',False,True,ID,id='reject_pasted_internal_newline'),
 pytest.param(b'\x1b[200~'+ID.encode().replace(b'@',b'\x01@')+b'\x1b[201~\r',False,True,ID,id='reject_pasted_internal_control'),
 pytest.param(ID.encode().replace(b'@',b'\x1b[31m@')+b'\r',False,True,ID,id='reject_unknown_escape_sequence'),
]


@pytest.mark.parametrize('identifier_bytes,typed,rejected,expected',CASES)
def test_real_pty_paste_to_password_to_real_keychain(identifier_bytes,typed,rejected,expected,request):
    if sys.platform!='darwin':pytest.skip('macOS Keychain required')
    service=c.SERVICE+'.identifier-paste-probe';key='fixturekey'
    cmd='add-generic-password -U -a trading-bot -s '+shlex.quote(service+'.api-key')+' -w '+c.encode_keychain_value(key)+'\n'
    assert subprocess.run(['security','-i'],input=cmd,capture_output=True,text=True).returncode==0
    transcript=b'';pid=None;fd=None
    result={'phase':request.node.callspec.id,'dummy_only':True,'authentication_not_attempted':True}
    try:
        child='''import json
from mnq_local import capital_app as a
from mnq_local.capital import CapitalError
a.SERVICE='''+repr(service)+'''
def no_http(*args,**kwargs):raise RuntimeError('unexpected_http')
a.CapitalHTTP=no_http
try:
 a.configure_credentials()
 print(json.dumps({'phase':'local_verified','saved':True}),flush=True)
except CapitalError as e:
 print(json.dumps({'phase':e.code,'saved':False}),flush=True)
 raise SystemExit(1)
'''
        pid,fd=pty.fork()
        if pid==0:os.execve(sys.executable,[sys.executable,'-c',child],dict(os.environ))
        deadline=time.monotonic()+12
        def until(*markers):
            nonlocal transcript
            while not any(m in transcript for m in markers):
                assert time.monotonic()<deadline,'Terminal test timed out'
                ready,_,_=select.select([fd],[],[],.1)
                if ready:
                    try:block=os.read(fd,8192)
                    except OSError:break
                    if not block:break
                    transcript+=block
        until(b'Capital login identifier: ')
        result['identifier_echo_disabled']=not bool(termios.tcgetattr(fd)[3]&termios.ECHO)
        assert result['identifier_echo_disabled']
        if typed:
            for byte in identifier_bytes:os.write(fd,bytes([byte]))
        else:os.write(fd,identifier_bytes)
        until(b'API key CUSTOM password (not login password): ',b'"saved": false')
        if not rejected:
            assert b'API key CUSTOM password (not login password): ' in transcript,'Identifier did not reach password prompt'
            result['password_echo_disabled']=not bool(termios.tcgetattr(fd)[3]&termios.ECHO)
            assert result['password_echo_disabled']
            os.write(fd,(PW+'\n').encode())
            until(b'"saved": true',b'"saved": false')
        else:assert b'API key CUSTOM password (not login password): ' not in transcript
        _,status=os.waitpid(pid,0);pid=None
        result['expected_exit']=os.waitstatus_to_exitcode(status)==(1 if rejected else 0)
        raw=subprocess.run(['security','find-generic-password','-a','trading-bot','-s',service+'.pending','-w'],capture_output=True,text=True)
        if rejected:
            result['suspicious_input_rejected_without_save']=raw.returncode==44
        else:
            data=json.loads(c.decode_keychain_value(raw.stdout.removesuffix('\n')))
            result['identifier_exact_readback']=data['credentials']['identifier']==expected
            result['password_exact_readback']=data['credentials']['password']==PW
            result['api_key_exact_readback']=data['credentials']['api_key']==key
            result['authentication_not_attempted']=data['attempted'] is False
        result['input_not_echoed']=ID.encode() not in transcript and PW.encode() not in transcript
        assert all(v for v in result.values() if isinstance(v,bool))
    finally:
        if pid is not None:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
        if fd is not None:os.close(fd)
        for suffix in ('.api-key','.pending',''):
            subprocess.run(['security','delete-generic-password','-a','trading-bot','-s',service+suffix],capture_output=True)
        result['disposable_records_removed']=all(subprocess.run(['security','find-generic-password','-a','trading-bot','-s',service+x,'-w'],capture_output=True).returncode==44 for x in ('.api-key','.pending',''))
        folder=Path(__file__).resolve().parents[1]/'reports/capital-identifier/pty'
        folder.mkdir(parents=True,exist_ok=True)
        (folder/(request.node.callspec.id+'.json')).write_text(json.dumps(result,indent=2)+'\n')
