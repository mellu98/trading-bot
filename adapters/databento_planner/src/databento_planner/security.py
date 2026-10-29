"""Secret-safe Keychain loading and a hard metadata-only HTTPS transport boundary."""
from contextlib import redirect_stdout, redirect_stderr
import hmac
import io
import logging
import os
import re
import subprocess
import time
from unittest.mock import patch
from urllib.parse import urlsplit
import warnings

from mnq_data.core import SafeError

class PlannerError(SafeError):
    """Only fixed internal codes, never vendor exception text."""


def quietly(fn, *args, **kwargs):
    previous = logging.root.manager.disable
    with warnings.catch_warnings(), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        warnings.simplefilter('ignore')
        logging.disable(logging.CRITICAL)
        try:
            return fn(*args, **kwargs)
        except PlannerError:
            raise
        except Exception:
            raise PlannerError('operation_failed_without_raw_exception') from None
        finally:
            logging.disable(previous)


def keychain_bytes():
    try:
        result = subprocess.run(['security', 'find-generic-password', '-a', os.environ['USER'],
                                 '-s', 'mnq-databento-api-key', '-w'], capture_output=True,
                                check=False, timeout=10)
        if result.returncode != 0:
            raise PlannerError('keychain_retrieval_failed')
        return result.stdout
    except Exception:
        raise PlannerError('keychain_retrieval_failed') from None


def load_key(reader=keychain_bytes, environ=None):
    """Keychain is authoritative; never silently override it with an environment key.

    Remove only the single security(1) transport newline. A stored bare 29-character
    ASCII body may receive the documented prefix IN MEMORY only for free metadata.
    """
    env = os.environ if environ is None else environ
    raw = quietly(reader)
    if not isinstance(raw, bytes):
        raise PlannerError('invalid_keychain_response')
    transport_lf = raw.endswith(b'\n')
    stored = raw[:-1] if transport_lf else raw
    try:
        key = stored.decode('ascii')
    except UnicodeError:
        raise PlannerError('credential_format_invalid') from None
    complete = bool(re.fullmatch(r'db-[A-Za-z0-9]{29}', key))
    bare = bool(re.fullmatch(r'[A-Za-z0-9]{29}', key))
    if not complete and not bare:
        raise PlannerError('credential_format_invalid')
    selected = key if complete else 'db-' + key
    override = env.get('DATABENTO_API_KEY')
    evidence = {'source':'macOS Keychain', 'retrieval_succeeded':True,
                'stored_complete':complete, 'used_complete':True,
                'normalization_applied':bare, 'normalization':'documented_prefix_in_memory_only' if bare else 'none',
                'transport_single_lf_removed':transport_lf,
                'stored_whitespace_or_controls':False,
                'persistent_keychain_modified':False, 'environment_modified':False,
                'environment_present':override is not None, 'precedence':'keychain_authoritative',
                'environment_matches_selected':hmac.compare_digest(override.encode(),selected.encode()) if override is not None else None,
                'environment_matches_stored':hmac.compare_digest(override.encode(),stored) if override is not None else None,
                'secret_material_reported':False}
    return selected, evidence


class MetadataOnly:
    """No timeseries, batch, definitions or live route can reach HTTP here.

    SDK transport is synchronous and patched only during one call. This object is
    deliberately single-threaded. Trust-env/proxies, redirects and TLS bypass are off.
    """
    ALLOWED = {'metadata': {'list_schemas','get_dataset_range','get_dataset_condition',
                            'get_cost','get_record_count','get_billable_size'},
               'symbology': {'resolve'}}

    def __init__(self, key, max_requests=380, max_seconds=900):
        import databento
        import requests
        self._key = key
        self._client = quietly(databento.Historical, key=key)
        self._session = requests.Session()
        self._session.trust_env = False
        self.trace = []
        self._last = 0.0
        self._started = time.monotonic()
        self._max_requests = max_requests
        self._max_seconds = max_seconds

    def _request(self, expected, method, *args, **kwargs):
        from requests.auth import HTTPBasicAuth
        url = kwargs.get('url', args[0] if args else '')
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'hist.databento.com'
                or parsed.path != '/v0/' + expected or parsed.query or parsed.fragment
                or method not in ('GET','POST') or len(self.trace) >= self._max_requests
                or time.monotonic()-self._started > self._max_seconds):
            raise PlannerError('transport_boundary_blocked')
        auth = kwargs.get('auth')
        if not isinstance(auth, HTTPBasicAuth) or auth.password != '' or not hmac.compare_digest(auth.username,self._key):
            raise PlannerError('credential_transport_mismatch')
        time.sleep(max(0, .21-(time.monotonic()-self._last)))
        remaining=self._max_seconds-(time.monotonic()-self._started)
        if remaining<=.05: raise PlannerError('transport_deadline_reached')
        timeout=(min(10,remaining/2),min(30,remaining/2))
        item = {'endpoint':parsed.path,'method':method,'http_status':None}
        self.trace.append(item)
        try:
            response = self._session.request(method,url,params=kwargs.get('params'),
                data=kwargs.get('data'),headers=kwargs.get('headers'),auth=auth,
                timeout=timeout,verify=True,allow_redirects=False)
            item['http_status'] = response.status_code
            if response.status_code != 200:
                response.close()
                raise PlannerError('metadata_http_not_200')
            return response
        finally:
            self._last = time.monotonic()

    def call(self, area, name, **kwargs):
        if name not in self.ALLOWED.get(area,set()):
            raise PlannerError('endpoint_forbidden')
        expected = area + '.' + name
        with patch('databento.common.http.requests.get',lambda *a,**kw:self._request(expected,'GET',*a,**kw)), \
             patch('databento.common.http.requests.post',lambda *a,**kw:self._request(expected,'POST',*a,**kw)):
            return quietly(getattr(getattr(self._client,area),name),**kwargs)

    def close(self):
        self._session.close()
