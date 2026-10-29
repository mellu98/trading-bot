"""Dedicated live binding tests never query the real Keychain."""
import subprocess
import pytest
from mnq_local.databento_app import load_live_key, LIVE_KEY_SERVICE


def test_live_key_uses_only_dedicated_service(monkeypatch):
    calls=[]
    def fake(cmd,**kwargs):
        calls.append((cmd,kwargs))
        return subprocess.CompletedProcess(cmd,0,b'db-'+b'a'*29+b'\n',b'')
    monkeypatch.setenv('DATABENTO_API_KEY','shared-historical-must-not-be-used')
    assert load_live_key(runner=fake)=='db-'+'a'*29
    assert len(calls)==1 and calls[0][0][-3:]==['-s',LIVE_KEY_SERVICE,'-w']
    assert LIVE_KEY_SERVICE=='mnq-databento-personal-live-api-key'
    assert calls[0][1]['capture_output'] is True


@pytest.mark.parametrize('code,value',[(44,b''),(0,b'a'*29),(0,b'db-'+b'a'*29+b'\n\n'),(0,b'db-'+b'a'*28+b'!')])
def test_missing_or_malformed_live_binding_fails_without_fallback(code,value,monkeypatch):
    monkeypatch.setenv('DATABENTO_API_KEY','db-'+'b'*29)
    with pytest.raises(PermissionError,match='dedicated_personal_live_key_required'):
        load_live_key(runner=lambda *a,**k:subprocess.CompletedProcess([],code,value,b''))
