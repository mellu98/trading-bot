from copy import deepcopy
from dataclasses import dataclass
import json
import pytest

from mnq_local.tasty import SandboxHTTP, SandboxBroker, SandboxError, TokenProvider, BASE
from mnq_paper.core import PaperConfig, ContractSpec, Journal, Runtime


class FakeHTTP:
    """Contract-shaped fixtures only; NEVER evidence of an authenticated broker."""
    def __init__(self):
        self.calls = []
        self.orders = []
        self.positions = []
        self.uncertain = False

    def request(self, method, path, body=None):
        self.calls.append((method, path, deepcopy(body)))
        if path == '/customers/me/accounts':
            return {'data': {'items': [{'account': {'account-number': 'SANDBOX1'}}]}}
        if path.startswith('/instruments/futures'):
            return {'data': {'items': [{'symbol': '/MESZ6', 'product-code': 'MES', 'expires-at': '2026-12-18T14:30:00Z'}]}}
        if '/positions' in path:
            return {'data': {'items': self.positions}}
        if method == 'GET' and '/orders' in path:
            return {'data': {'items': deepcopy(self.orders)}}
        if path.endswith('/dry-run'):
            return {'data': {'warnings': [], 'buying-power-effect': {}}}
        if method == 'POST':
            if self.uncertain:
                raise ConnectionError('ambiguous post')
            orders = [body['trigger-order'], *body['orders']] if 'trigger-order' in body else [body]
            self.orders.extend({**deepcopy(o), 'id': i+101, 'status': 'Live', 'account-number': 'SANDBOX1'} for i, o in enumerate(orders))
            return {'data': {'complex-order': {'id': 99, 'trigger-order': self.orders[0], 'orders': self.orders[1:]}}}
        if method == 'DELETE':
            for o in self.orders:
                o['status'] = 'Cancelled'
            return {'data': {}}
        raise AssertionError(path)


def make(tmp_path):
    cfg = PaperConfig('DU000001', mode='technical_paper')
    # Runtime's exact sandbox account is a duck-typed configuration facade;
    # no fake DU namespace is ever sent to tastytrade.
    from mnq_local.tasty import RuntimeSandboxConfig
    cfg = RuntimeSandboxConfig(cfg, 'SANDBOX1')
    spec = ContractSpec('MES', 'MESZ6', 1, '20261218')
    http = FakeHTTP()
    broker = SandboxBroker(cfg, [spec], tmp_path/'sandbox.sqlite', http=http)
    return cfg, spec, http, broker


def test_sandbox_endpoint_cannot_reach_production_or_follow_redirects():
    with pytest.raises(ValueError):
        SandboxHTTP(TokenProvider('a', 'b'), base='https://api.tastyworks.com')
    h = SandboxHTTP(TokenProvider('a', 'b'))
    for path in ('https://api.tastyworks.com/orders', '//api.tastyworks.com', '/market-data', '/foo/../orders'):
        with pytest.raises(ValueError):
            h.request('GET', path)


def test_missing_credentials_fail_before_network(monkeypatch):
    monkeypatch.delenv('TASTY_SANDBOX_REFRESH_TOKEN', raising=False)
    monkeypatch.delenv('TASTY_SANDBOX_CLIENT_SECRET', raising=False)
    with pytest.raises(SandboxError, match='credentials'):
        TokenProvider.from_env()


def test_token_refresh_nonrotation_and_safe_errors():
    now = [100.]
    calls = []
    def send(method, url, headers, body):
        calls.append((method, url, json.loads(body)))
        return 200, {'access_token': 'private', 'expires_in': 900, 'token_type': 'Bearer'}
    p = TokenProvider('refresh', 'secret', clock=lambda: now[0], send=send)
    assert p.access_token() == p.access_token() == 'private'
    assert len(calls) == 1 and calls[0][1] == BASE+'/oauth/token'
    now[0] += 850
    assert p.access_token() == 'private' and len(calls) == 2
    assert p.refresh_token == 'refresh'
    p = TokenProvider('SECRET_A', 'SECRET_B', send=lambda *a: (403, {'error': {'message': 'SECRET_A'}}))
    with pytest.raises(SandboxError) as e:
        p.access_token()
    assert 'SECRET_A' not in str(e.value) and e.value.status == 403


def test_contract_bracket_cancel_and_persistent_duplicate_guard(tmp_path):
    cfg, spec, http, broker = make(tmp_path)
    broker.connect()
    from urllib.parse import urlsplit, parse_qs
    query = parse_qs(urlsplit(next(p for m, p, _ in http.calls if p.startswith('/instruments/futures'))).query)
    assert query['symbol'] == ['/MESZ6'] and 'symbol[]' not in query
    journal = Journal(tmp_path/'runtime.sqlite', cfg, [spec], lock_root=tmp_path/'locks')
    from datetime import datetime, timezone
    now = datetime(2026, 10, 19, 14, tzinfo=timezone.utc)
    runtime = Runtime(cfg, [spec], journal, broker, clock=lambda: now)
    runtime.reconcile(broker.snapshot())
    runtime.last_data = now
    assert runtime.submit_candidate('MES', 1, 100, now, 'controlled')
    post = [x for x in http.calls if x[0] == 'POST' and not x[1].endswith('dry-run')]
    assert len(post) == 1 and post[0][2]['type'] == 'OTOCO'
    assert post[0][2]['trigger-order']['legs'][0]['symbol'] == '/MESZ6'
    snapshot = broker.snapshot()
    runtime.reconcile(snapshot)
    assert runtime.state['halt'] is None
    broker.cancel(1)
    assert any(m == 'DELETE' and '/complex-orders/99' in p for m, p, _ in http.calls)
    broker.close()
    broker = SandboxBroker(cfg, [spec], tmp_path/'sandbox.sqlite', http=http)
    broker.connect()
    with pytest.raises(SandboxError):
        broker.submit(list(runtime.state['orders'].values()))
    broker.close()
    journal.close()


def test_ambiguous_submission_never_auto_retried(tmp_path):
    cfg, spec, http, broker = make(tmp_path)
    broker.connect()
    broker.snapshot()
    http.uncertain = True
    orders = [{'id': 1, 'symbol': 'MES', 'side': 1, 'quantity': 1, 'role': 'flatten', 'ref': 'one',
               'parent_id': 0, 'limit': None, 'stop': None, 'account': cfg.account, 'client_id': cfg.client_id, 'good_till': None}]
    with pytest.raises(SandboxError):
        broker.submit(orders)
    broker.close()
    broker = SandboxBroker(cfg, [spec], tmp_path/'sandbox.sqlite', http=http)
    broker.connect()
    with pytest.raises(SandboxError):
        broker.submit(orders)
    assert len([c for c in http.calls if c[0] == 'POST' and not c[1].endswith('dry-run')]) == 1
    broker.close()


def test_foreign_positions_missing_pages_and_unknown_orders_fail_closed(tmp_path):
    cfg, spec, http, broker = make(tmp_path)
    broker.connect()
    http.positions = [{'account-number': 'SANDBOX1', 'symbol': 'AAPL', 'quantity': '1', 'quantity-direction': 'Long'}]
    with pytest.raises(SandboxError):
        broker.snapshot()
    http.positions = []
    http.orders = [{'id': 999, 'status': 'Live', 'external-identifier': 'foreign'}]
    with pytest.raises(SandboxError):
        broker.snapshot()
    broker.close()


def fixture_bracket(cfg):
    common = dict(symbol='MES', quantity=1, ref='fixture', account=cfg.account,
                  client_id=cfg.client_id, good_till=None, filled=0, status='Reserved')
    return [dict(common, id=1, side=1, role='entry', parent_id=0, limit=100.25, stop=None,
                 good_till='20261019 14:01:00 UTC'),
            dict(common, id=2, side=-1, role='target', parent_id=1, limit=104.25, stop=None),
            dict(common, id=3, side=-1, role='stop', parent_id=1, limit=None, stop=98.25)]


def test_fill_updates_dedupe_and_reconnect_to_same_runtime(tmp_path):
    from datetime import datetime, timezone
    cfg, spec, http, broker = make(tmp_path)
    broker.connect()
    j = Journal(tmp_path/'runtime.sqlite', cfg, [spec], lock_root=tmp_path/'locks')
    now = datetime(2026, 10, 19, 14, tzinfo=timezone.utc)
    runtime = Runtime(cfg, [spec], j, broker, clock=lambda: now)
    runtime.reconcile(broker.snapshot())
    runtime.last_data = now
    assert runtime.submit_candidate('MES', 1, 100, now, 'update')
    entry = http.orders[0]
    entry['status'] = 'Filled'
    entry['legs'][0]['fills'] = [{'fill-id': 'abc', 'quantity': '1', 'fill-price': '1', 'filled-at': now.isoformat()}]
    http.positions = [{'account-number': cfg.account, 'symbol': '/MESZ6', 'quantity': '1', 'quantity-direction': 'Long'}]
    broker.poll(runtime)
    broker.poll(runtime)
    assert len(runtime.state['executions']) == 1
    assert runtime.state['positions']['MES']['quantity'] == 1
    assert runtime.state['positions']['MES']['average'] == 1  # sandbox artificial, NOT CME price
    broker.connected = False
    with pytest.raises(SandboxError):
        broker.poll(runtime)
    assert not runtime.ready
    broker.connect()
    broker.poll(runtime)
    assert runtime.state['blocked_session'] == '2026-10-19'
    j.close()
    broker.close()


def test_snapshot_does_not_mask_changed_protection_or_late_fills(tmp_path):
    cfg, spec, http, broker = make(tmp_path)
    broker.connect()
    broker.snapshot()
    broker.submit(fixture_bracket(cfg))
    http.orders[-1]['stop-trigger'] = '1'
    with pytest.raises(SandboxError, match='protective'):
        broker.snapshot()
    broker.connect()
    http.orders[-1]['stop-trigger'] = '98.25'
    http.orders[0]['status'] = 'Filled'
    with pytest.raises(SandboxError, match='visibility'):
        broker.snapshot()
    broker.close()


def test_restart_resolves_accepted_response_lost_by_reference_without_resending(tmp_path):
    cfg, spec, http, broker = make(tmp_path)
    broker.connect()
    broker.snapshot()
    original = http.request
    def lost_reply(method, path, body=None):
        response = original(method, path, body)
        if method == 'POST' and not path.endswith('dry-run'):
            for order in http.orders:
                order['complex-order-id'] = 99
            raise TimeoutError('accepted but reply lost')
        return response
    http.request = lost_reply
    with pytest.raises(SandboxError):
        broker.submit(fixture_bracket(cfg))
    broker.close()
    http.request = original
    broker = SandboxBroker(cfg, [spec], tmp_path/'sandbox.sqlite', http=http)
    broker.connect()
    assert len(broker.snapshot()['orders']) == 3
    with pytest.raises(SandboxError):
        broker.submit(fixture_bracket(cfg))
    assert len([c for c in http.calls if c[0] == 'POST' and not c[1].endswith('dry-run')]) == 1
    broker.close()


def test_pagination_and_read_failure_do_not_imply_flat(tmp_path):
    cfg, spec, http, broker = make(tmp_path)
    broker.connect()
    original = http.request
    calls = []
    def paged(method, path, body=None):
        if '/orders?' in path:
            page = int(path.rsplit('=', 1)[1])
            calls.append(page)
            return {'data': {'items': []}, 'pagination': {'page-offset': page, 'total-pages': 2}}
        return original(method, path, body)
    http.request = paged
    assert broker.snapshot()['positions'] == {}
    assert calls == [0, 1]
    def missing(method, path, body=None):
        if '/orders?' in path:
            return {'error': {'message': 'unknown'}}
        return original(method, path, body)
    http.request = missing
    with pytest.raises(SandboxError):
        broker.snapshot()
    assert broker.connected is False
    broker.close()


def test_bounded_reconnect_requires_new_snapshot_and_blocks_day(tmp_path):
    cfg, spec, http, broker = make(tmp_path)
    broker.connect()
    j = Journal(tmp_path/'runtime.sqlite', cfg, [spec], lock_root=tmp_path/'locks')
    from datetime import datetime, timezone
    now = datetime(2026, 10, 19, 14, tzinfo=timezone.utc)
    runtime = Runtime(cfg, [spec], j, broker, clock=lambda: now)
    runtime.reconcile(broker.snapshot())
    original = http.request
    failures = [0]
    def transient(method, path, body=None):
        if path == '/customers/me/accounts' and failures[0] == 0:
            failures[0] += 1
            raise ConnectionError('one connection outage')
        return original(method, path, body)
    http.request = transient
    sleeps = []
    broker.reconnect(runtime, sleep=sleeps.append)
    assert sleeps == [1]
    assert runtime.state['blocked_session'] == '2026-10-19'
    assert broker.connected and broker.last_snapshot > 0
    broker.connect()
    assert broker.last_snapshot == 0
    with pytest.raises(SandboxError, match='Fresh'):
        broker.submit(fixture_bracket(cfg))
    broker.close()
    j.close()


@pytest.mark.parametrize('http_status', [401, 403, 429, 500, 302])
def test_http_status_is_real_code_without_unsafe_retry(http_status):
    p = TokenProvider('refresh', 'secret')
    p.token, p.expires = 'private', 1e20
    calls = []
    def sender(*args):
        calls.append(args)
        return http_status, {'error': {'message': 'private'}}
    h = SandboxHTTP(p, sender=sender)
    with pytest.raises(SandboxError) as error:
        h.request('POST', '/accounts/SANDBOX1/orders', {})
    assert error.value.status == http_status and len(calls) == 1
    assert 'private' not in str(error.value)
