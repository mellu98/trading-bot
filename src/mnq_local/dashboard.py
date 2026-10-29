"""Loopback dashboard; it has no broker control, credentials, or live switch."""
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading


class View:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = {'phase': 'STARTING', 'report': {}, 'trades': [], 'decisions': [], 'equity': []}

    def update(self, report, trades, decisions, equity, phase='RUNNING'):
        with self.lock:
            self.value = deepcopy({'phase': phase, 'report': report, 'trades': trades,
                'decisions': decisions[-20:], 'equity': equity, 'updated_at': datetime.now(timezone.utc).isoformat()})

    def read(self):
        with self.lock:
            return deepcopy(self.value)


class Dashboard(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, view, commands, folder):
        if address[0] != '127.0.0.1':
            raise ValueError('Dashboard can only bind IPv4 loopback')
        self.view, self.commands, self.folder = view, commands, Path(folder)
        self.control_token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _valid_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def reply(self, status, value, content_type='application/json'):
        encoded = json.dumps(value).encode() if content_type == 'application/json' else value.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type+'; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'nonce-"+self.server.control_token+"'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if not self._valid_host():
            return self.reply(403, {'error': 'Host rejected'})
        if self.path == '/':
            page = Path(__file__).with_name('dashboard.html').read_text().replace('__TOKEN__', self.server.control_token)
            return self.reply(200, page, 'text/html')
        if self.path == '/api/status':
            return self.reply(200, self.server.view.read())
        if self.path == '/download/trades.csv' and (self.server.folder/'trades.csv').is_file():
            return self.reply(200, (self.server.folder/'trades.csv').read_text(), 'text/csv')
        return self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if (not self._valid_host() or self.headers.get('Origin') != origin or
            not secrets.compare_digest(self.headers.get('X-Control-Token', ''), self.server.control_token) or
            self.headers.get('Content-Type') != 'application/json'):
            return self.reply(403, {'error': 'Local origin and control token required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 256:
                raise ValueError()
            action = json.loads(self.rfile.read(length)).get('action')
            if action not in ('pause', 'resume', 'kill'):
                raise ValueError()
        except (ValueError, AttributeError):
            return self.reply(400, {'error': 'Unknown replay action'})
        self.server.commands.put(action)
        return self.reply(202, {'queued': action, 'scope': 'LOCAL_REPLAY_ONLY'})
