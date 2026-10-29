import json
import queue
import threading
import urllib.error
import urllib.request

import pytest
from mnq_local.dashboard import Dashboard, View


def test_dashboard_http_controls_and_isolation(tmp_path):
    view = View()
    view.update({'mode': 'HISTORICAL_REPLAY', 'net': -5}, [], [], [])
    commands = queue.Queue()
    server = Dashboard(('127.0.0.1', 0), view, commands, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        with urllib.request.urlopen(url) as response:
            html = response.read().decode()
            assert 'HISTORICAL REPLAY' in html and 'NOT CONNECTED' in html
            assert 'Content-Security-Policy' in response.headers
        with urllib.request.urlopen(url+'/api/status') as response:
            assert json.load(response)['report']['net'] == -5
        for path in ('/../state.sqlite', '/download/state.sqlite'):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(url+path)
        for headers in ({}, {'Origin': 'http://evil.invalid', 'X-Control-Token': server.control_token}):
            request = urllib.request.Request(url+'/api/control', b'{"action":"kill"}', headers=headers)
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(request)
        headers = {'Origin': url, 'X-Control-Token': server.control_token, 'Content-Type': 'application/json'}
        with urllib.request.urlopen(urllib.request.Request(url+'/api/control', b'{"action":"pause"}', headers=headers)):
            pass
        assert commands.get_nowait() == 'pause'
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(urllib.request.Request(url+'/api/control', b'{"action":"live"}', headers=headers))
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(urllib.request.Request(url, headers={'Host': 'attacker.invalid'}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
