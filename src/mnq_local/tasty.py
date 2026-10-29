"""Sandbox-only REST adapter. Synthetic fills are NEVER financial evidence.

No production host, market-data access, browser login, or automatic order retry.
The unchanged V3 Runtime remains the order/position owner. This module is I/O.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

from mnq_paper.core import PaperConfig, integer, TERMINAL

BASE = 'https://api.cert.tastyworks.com'
USER_AGENT = 'mnq-local-sandbox/5.0'
STATUS = {'Received': 'PendingSubmit', 'Routed': 'PendingSubmit', 'In Flight': 'PendingSubmit',
    'Live': 'Submitted', 'Contingent': 'PreSubmitted', 'Cancel Requested': 'PendingCancel',
    'Replace Requested': 'PendingCancel', 'Filled': 'Filled', 'Cancelled': 'Cancelled',
    'Expired': 'Cancelled', 'Rejected': 'Inactive', 'Removed': 'Inactive', 'Partially Removed': 'Inactive'}


class SandboxError(ConnectionError):
    def __init__(self, message, status=None):
        self.status = status
        super().__init__(message+(' (HTTP '+str(status)+')' if status is not None else ''))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def send(method, url, headers, body):
    if urllib.parse.urlsplit(url).netloc != 'api.cert.tastyworks.com' or not url.startswith(BASE+'/'):
        raise ValueError('Only the exact HTTPS sandbox origin is permitted')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, body, headers, method=method)
    try:
        with opener.open(request, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        # No raw response/URL/header logging: diagnostics can contain credentials.
        return e.code, {}
    except (OSError, ValueError):
        raise SandboxError('Sandbox transport failure; mutation outcome may be unknown') from None


class TokenProvider:
    def __init__(self, refresh_token, client_secret, *, clock=time.monotonic, send=send):
        if not all(isinstance(v, str) and v and not any(c.isspace() for c in v) for v in (refresh_token, client_secret)):
            raise SandboxError('Valid sandbox credentials required')
        self.refresh_token, self.client_secret = refresh_token, client_secret
        self.clock, self.send = clock, send
        self.token, self.expires = None, 0.

    @classmethod
    def from_env(cls):
        return cls(os.environ.get('TASTY_SANDBOX_REFRESH_TOKEN'), os.environ.get('TASTY_SANDBOX_CLIENT_SECRET'))

    def access_token(self):
        if self.token and self.clock() < self.expires-60:
            return self.token
        status, response = self.send('POST', BASE+'/oauth/token',
            {'User-Agent': USER_AGENT, 'Content-Type': 'application/json'},
            json.dumps({'grant_type': 'refresh_token', 'refresh_token': self.refresh_token,
                       'client_secret': self.client_secret}).encode())
        if status != 200:
            raise SandboxError('Sandbox OAuth refresh failed', status)
        token = response.get('access_token')
        ttl = response.get('expires_in')
        if not isinstance(token, str) or not token or response.get('token_type', '').lower() != 'bearer' or type(ttl) not in (int, float) or not 60 < ttl <= 900:
            raise SandboxError('Invalid sandbox OAuth response')
        self.token, self.expires = token, self.clock()+ttl
        # tastytrade does NOT rotate this refresh grant on refresh.
        return token


class SandboxHTTP:
    def __init__(self, tokens, *, base=BASE, sender=send):
        if base != BASE:
            raise ValueError('Production and custom origins are forbidden')
        self.tokens, self.sender = tokens, sender

    def request(self, method, path, body=None):
        if (not re.fullmatch(r'/(?:customers/me/accounts|instruments/futures|accounts/[A-Za-z0-9-]+/(?:positions|orders|complex-orders)(?:/[0-9]+|/dry-run|/live)?)(?:\?[^#]*)?', path)
            or '..' in path or '://' in path or method not in ('GET', 'POST', 'DELETE')):
            raise ValueError('Endpoint is not in the sandbox-only allowlist')
        headers = {'Authorization': 'Bearer '+self.tokens.access_token(), 'User-Agent': USER_AGENT,
                   'Accept': 'application/json', 'Content-Type': 'application/json'}
        status, response = self.sender(method, BASE+path, headers,
            None if body is None else json.dumps(body, allow_nan=False).encode())
        if not 200 <= status < 300:
            if status == 401:
                self.tokens.token = None
            raise SandboxError('Sandbox request rejected; no mutation retry', status)
        return response


@dataclass(frozen=True)
class RuntimeSandboxConfig:
    """V3 configuration interface with a separately allowlisted sandbox account."""
    base: PaperConfig
    account: str

    def __post_init__(self):
        if not re.fullmatch(r'[A-Z0-9-]{1,40}', self.account) or self.base.max_contracts != 1:
            raise ValueError('Exact sandbox account and maximum one micro required')

    def __getattr__(self, name):
        return getattr(self.base, name)


class SandboxBroker:
    kind = 'TASTYTRADE_SANDBOX_ARTIFICIAL_FILLS_NOT_FINANCIAL_SIMULATION'

    def __init__(self, config, specs, path, *, http=None):
        if not isinstance(config, RuntimeSandboxConfig):
            raise ValueError('Explicit sandbox-only configuration required')
        self.config, self.specs = config, {s.symbol: s for s in specs}
        if not self.specs or len(self.specs) != len(specs):
            raise ValueError('Unique micro contract specifications required')
        self.http = http if http is not None else SandboxHTTP(TokenProvider.from_env())
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = path.with_suffix('.lock').open('a+')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise SandboxError('Another sandbox transport owns this state') from None
        self.db = sqlite3.connect(path)
        path.chmod(0o600)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS identity(body TEXT PRIMARY KEY)')
        self.db.execute('CREATE TABLE IF NOT EXISTS intents(ref TEXT PRIMARY KEY, body TEXT, remote TEXT)')
        identity = json.dumps([BASE, config.account, config.client_id, sorted((s.symbol, s.local_symbol, s.expiry) for s in specs)])
        old = self.db.execute('SELECT body FROM identity').fetchone()
        if old and old[0] != identity:
            self.close()
            raise ValueError('Sandbox state account/contract identity changed')
        with self.db:
            if not old:
                self.db.execute('INSERT INTO identity VALUES(?)', (identity,))
        self.connected = False
        self.last_snapshot = 0.

    def _items(self, path):
        rows, seen = [], set()
        for page in range(100):
            sep = '&' if '?' in path else '?'
            value = self.http.request('GET', path+f'{sep}per-page=100&page-offset={page}')
            items = value.get('data', {}).get('items')
            if not isinstance(items, list):
                raise SandboxError('Incomplete sandbox list response')
            fingerprint = json.dumps(items, sort_keys=True)
            if fingerprint in seen and items:
                raise SandboxError('Repeated sandbox pagination; portfolio unknown')
            seen.add(fingerprint)
            rows.extend(items)
            pagination = value.get('pagination')
            if pagination is not None:
                if pagination.get('page-offset') != page or type(pagination.get('total-pages')) is not int:
                    raise SandboxError('Invalid sandbox pagination')
                if page+1 >= pagination['total-pages']:
                    return rows
            elif len(items) < 100:
                return rows
        raise SandboxError('Sandbox page bound exceeded; portfolio unknown')

    def connect(self):
        self.connected = False
        self.last_snapshot = 0.
        response = self.http.request('GET', '/customers/me/accounts')
        accounts = response.get('data', {}).get('items')
        if not isinstance(accounts, list) or self.config.account not in [a.get('account', {}).get('account-number') for a in accounts]:
            raise SandboxError('Authorized sandbox account was not returned by official API')
        for spec in self.specs.values():
            # This endpoint defines singular `symbol`, not the array convention
            # used by some other tastytrade instrument endpoints.
            query = urllib.parse.urlencode({'symbol': '/'+spec.local_symbol})
            response = self.http.request('GET', '/instruments/futures?'+query)
            instruments = response.get('data', {}).get('items', [])
            matches = [i for i in instruments if i.get('symbol') == '/'+spec.local_symbol]
            if len(matches) != 1 or matches[0].get('product-code') != spec.symbol or matches[0].get('expires-at', '')[:10].replace('-', '') != spec.expiry:
                raise SandboxError('Sandbox futures metadata identity not verified')
        self.connected = True

    def _intents(self):
        return [(ref, json.loads(body), json.loads(remote) if remote else None)
            for ref, body, remote in self.db.execute('SELECT ref,body,remote FROM intents')]

    def _payload(self, order):
        if (order['account'] != self.config.account or order['client_id'] != self.config.client_id or
            order['symbol'] not in self.specs or type(order['quantity']) is not int or order['quantity'] != 1 or order['side'] not in (-1, 1)):
            raise SandboxError('Invalid sandbox order identity or quantity')
        payload = {'time-in-force': 'Day' if order['role'] in ('entry', 'flatten') else 'GTC',
            'order-type': 'Stop' if order.get('stop') is not None else 'Limit' if order.get('limit') is not None else 'Market',
            'external-identifier': f'v5-{self.config.client_id}-{order["id"]}-{order["ref"]}',
            'legs': [{'instrument-type': 'Future', 'symbol': '/'+self.specs[order['symbol']].local_symbol,
                      'quantity': 1, 'action': 'Buy' if order['side'] == 1 else 'Sell'}]}
        for source, dest in (('limit', 'price'), ('stop', 'stop-trigger')):
            if order.get(source) is not None:
                value = Decimal(str(order[source]))
                if not value.is_finite() or value <= 0 or value % Decimal('.25'):
                    raise SandboxError('Invalid micro futures tick price')
                payload[dest] = str(value)
        if 'price' in payload:
            payload['price-effect'] = 'Debit' if order['side'] == 1 else 'Credit'
        if order['role'] == 'entry':
            # V3 minute GTD is preserved with the API order-rule, never silently changed to an all-day entry.
            at = datetime.strptime(order['good_till'], '%Y%m%d %H:%M:%S UTC').replace(tzinfo=timezone.utc)
            payload['order-rule'] = {'cancel-at': at.isoformat()}
        return payload

    def submit(self, orders):
        if not self.connected or time.monotonic()-self.last_snapshot > 15:
            raise SandboxError('Fresh reconciled sandbox snapshot required before mutation')
        orders = deepcopy(orders)
        if len(orders) == 3 and [o['role'] for o in orders] == ['entry', 'target', 'stop']:
            parent, target, stop = orders
            if any(o['symbol'] != parent['symbol'] or o['ref'] != parent['ref'] for o in orders) or any(
                o['parent_id'] != parent['id'] or o['side'] != -parent['side'] for o in (target, stop)):
                raise SandboxError('Invalid sandbox bracket')
            if parent['side']*(target['limit']-parent['limit']) <= 0 or parent['side']*(parent['limit']-stop['stop']) <= 0:
                raise SandboxError('Invalid protective sandbox price geometry')
            payload = {'type': 'OTOCO', 'trigger-order': self._payload(parent), 'orders': [self._payload(target), self._payload(stop)]}
            route = f'/accounts/{self.config.account}/complex-orders'
        elif len(orders) == 1 and orders[0]['role'] == 'flatten':
            payload, route = self._payload(orders[0]), f'/accounts/{self.config.account}/orders'
        else:
            raise SandboxError('Only one-micro OTOCO brackets or controlled flatten accepted')
        ref = str(orders[0]['id'])
        if self.db.execute('SELECT 1 FROM intents WHERE ref=?', (ref,)).fetchone():
            raise SandboxError('Intent already exists; never resubmit after uncertain outcome')
        dry = self.http.request('POST', route+'/dry-run', payload)
        data = dry.get('data', {})
        if not isinstance(data.get('buying-power-effect'), dict) or data.get('warnings') or data.get('errors'):
            raise SandboxError('Sandbox dry-run requires manual warning review')
        with self.db:
            self.db.execute('INSERT INTO intents VALUES(?,?,NULL)', (ref, json.dumps({'orders': orders, 'payload': payload, 'route': route})))
        try:
            result = self.http.request('POST', route, payload)['data']
            self._bind(ref, orders, result)
        except Exception:
            self.connected = False
            raise SandboxError('Sandbox submission uncertain; no automatic resend') from None

    def _bind(self, ref, orders, data):
        complex_order = data.get('complex-order')
        if complex_order:
            remote_orders = [complex_order.get('trigger-order', {}), *complex_order.get('orders', [])]
            complex_id = str(complex_order['id'])
            if not complex_id.isdigit():
                raise SandboxError('Invalid remote complex order ID')
        else:
            remote_orders, complex_id = [data.get('order', {})], None
        by_ref = {r.get('external-identifier'): r for r in remote_orders}
        bindings = {}
        for local in orders:
            external = self._payload(local)['external-identifier']
            remote = by_ref.get(external)
            if not remote or not str(remote.get('id', '')).isdigit():
                raise SandboxError('Unresolved remote order IDs')
            bindings[str(local['id'])] = {'id': str(remote['id']), 'complex_id': complex_id, 'external': external}
        with self.db:
            self.db.execute('UPDATE intents SET remote=? WHERE ref=?', (json.dumps(bindings), ref))

    def cancel(self, oid):
        if not self.connected or time.monotonic()-self.last_snapshot > 15:
            raise SandboxError('Fresh sandbox reconciliation required before cancellation')
        for _, _, bindings in self._intents():
            if bindings and str(oid) in bindings:
                remote = bindings[str(oid)]
                path = f'/accounts/{self.config.account}/'+('complex-orders/'+remote['complex_id'] if remote['complex_id'] else 'orders/'+remote['id'])
                self.http.request('DELETE', path)
                return
        raise SandboxError('Unknown or unresolved sandbox order; cancellation not guessed')

    def snapshot(self):
        if not self.connected:
            raise SandboxError('Sandbox disconnected')
        try:
            return self._snapshot()
        except Exception as e:
            self.connected = False
            if isinstance(e, SandboxError):
                raise
            raise SandboxError('Malformed or incomplete sandbox snapshot; portfolio unknown') from None

    def _resolve_binding(self, ref, intent, remote_orders):
        """Read-only recovery of an accepted order whose HTTP response was lost.

        Absence or partial matches NEVER authorize another POST. Every local leg
        must have exactly one corresponding remote external-identifier.
        """
        resolved = []
        for local in intent['orders']:
            external = self._payload(local)['external-identifier']
            matches = [o for o in remote_orders if o.get('external-identifier') == external]
            if len(matches) != 1:
                raise SandboxError('Uncertain submission requires external-identifier review; no retry')
            resolved.append(matches[0])
        if len(resolved) == 3:
            ids = {str(o.get('complex-order-id', '')) for o in resolved}
            if len(ids) != 1 or not next(iter(ids)).isdigit():
                raise SandboxError('Unresolved complex order identity; no retry')
            data = {'complex-order': {'id': next(iter(ids)), 'trigger-order': resolved[0], 'orders': resolved[1:]}}
        else:
            data = {'order': resolved[0]}
        self._bind(ref, intent['orders'], data)
        return json.loads(self.db.execute('SELECT remote FROM intents WHERE ref=?', (ref,)).fetchone()[0])

    def _snapshot(self):
        account = self.config.account
        remote_orders = self._items(f'/accounts/{account}/orders')
        remote_by_id = {str(o['id']): o for o in remote_orders}
        active, executions, known, statuses = [], [], set(), []
        next_id = 1
        for ref, intent, bindings in self._intents():
            if bindings is None:
                bindings = self._resolve_binding(ref, intent, remote_orders)
            for local in intent['orders']:
                binding = bindings[str(local['id'])]
                known.add(binding['id'])
                remote = remote_by_id.get(binding['id'])
                if remote is None:
                    # History windows can omit terminal orders. Resolve by exact ID, not absent=flat.
                    remote = self.http.request('GET', f'/accounts/{account}/orders/{binding["id"]}').get('data')
                if not isinstance(remote, dict) or remote.get('account-number') != account or remote.get('external-identifier') != binding['external']:
                    raise SandboxError('Sandbox order account/reference identity changed')
                payload = self._payload(local)
                for key in ('order-type', 'time-in-force', 'price-effect'):
                    if remote.get(key) != payload.get(key):
                        raise SandboxError('Sandbox remote order attributes changed')
                for key in ('price', 'stop-trigger'):
                    if (key in payload) != (key in remote) or (key in payload and Decimal(str(remote[key])) != Decimal(payload[key])):
                        raise SandboxError('Sandbox remote protective price changed')
                if payload.get('order-rule') != remote.get('order-rule'):
                    # Exact rule preservation is mandatory until real sandbox compatibility is verified.
                    raise SandboxError('Sandbox timed entry cancellation rule changed')
                status = STATUS.get(remote.get('status'))
                if status is None:
                    raise SandboxError('Unknown sandbox order status')
                legs = remote.get('legs', [])
                if len(legs) != 1 or legs[0].get('symbol') != '/'+self.specs[local['symbol']].local_symbol or integer(float(legs[0]['quantity'])) != local['quantity']:
                    raise SandboxError('Sandbox order leg identity changed')
                leg = legs[0]
                if leg.get('action') != ('Buy' if local['side'] == 1 else 'Sell'):
                    raise SandboxError('Sandbox order side changed')
                fills = leg.get('fills', [])
                total = 0
                for fill in fills:
                    quantity = integer(float(fill['quantity']))
                    price = float(fill['fill-price'])
                    at = datetime.fromisoformat(fill['filled-at'].replace('Z', '+00:00'))
                    if not quantity or not math.isfinite(price) or price <= 0 or at.tzinfo is None or not fill.get('fill-id'):
                        raise SandboxError('Invalid sandbox fill')
                    total += quantity
                    executions.append({'exec_id': binding['id']+'-'+str(fill['fill-id']), 'order_id': local['id'],
                        'symbol': local['symbol'], 'account': account, 'client_id': self.config.client_id,
                        'side': local['side'], 'quantity': quantity, 'price': price, 'at': at.astimezone(timezone.utc).isoformat()})
                if total > local['quantity'] or (status == 'Filled' and total != local['quantity']):
                    raise SandboxError('Sandbox fill visibility incomplete; portfolio unknown')
                # Partial is explicitly fed into the V3 conservative partial-fill stop.
                if 0 < total < local['quantity']:
                    status = 'Partial'
                statuses.append({'id': local['id'], 'status': status, 'filled': total})
                if status not in TERMINAL:
                    active.append({**local, 'status': status, 'filled': total})
                next_id = max(next_id, local['id']+1)
        if any(str(o['id']) not in known and STATUS.get(o.get('status')) not in TERMINAL for o in remote_orders):
            raise SandboxError('Foreign or unknown sandbox working order')
        positions = {}
        # Positions is a complete unpaginated endpoint. Do not attach unsupported
        # order-history pagination parameters or infer an empty list on failure.
        position_items = self.http.request('GET', f'/accounts/{account}/positions').get('data', {}).get('items')
        if not isinstance(position_items, list):
            raise SandboxError('Incomplete sandbox position response')
        for p in position_items:
            quantity = integer(float(p['quantity']))
            if not quantity:
                continue
            spec = next((s for s in self.specs.values() if p.get('symbol') == '/'+s.local_symbol), None)
            if spec is None or p.get('account-number') != account or p.get('quantity-direction') not in ('Long', 'Short'):
                raise SandboxError('Foreign sandbox position identity')
            positions[spec.symbol] = quantity*(1 if p['quantity-direction'] == 'Long' else -1)
        self.last_snapshot = time.monotonic()
        return {'accounts': [account], 'next_id': next_id, 'orders': active,
            'executions': executions, 'positions': positions, 'statuses': statuses}

    def poll(self, runtime):
        """REST account updates; a failed read blocks entries before any reconnect."""
        try:
            snapshot = self.snapshot()
            for event in snapshot['statuses']:
                if event['status'] in ('Inactive', 'Partial'):
                    runtime.on_status(event)
            runtime.reconcile(snapshot)
            runtime.watchdog()
        except (ConnectionError, OSError, ValueError, KeyError):
            self.connected = False
            runtime.disconnected()
            raise SandboxError('Sandbox account update failed; entries blocked') from None

    def reconnect(self, runtime, *, attempts=3, sleep=time.sleep):
        if type(attempts) is not int or not 1 <= attempts <= 5:
            raise ValueError('Bounded reconnect attempts required')
        runtime.disconnected()
        for attempt in range(attempts):
            try:
                self.connect()
                self.poll(runtime)
                return
            except (ConnectionError, OSError):
                self.connected = False
                if attempt+1 < attempts:
                    sleep(min(30, 2**attempt))
        raise SandboxError('Sandbox reconnect exhausted; entries remain blocked')

    def close(self):
        self.connected = False
        self.db.close()
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()
