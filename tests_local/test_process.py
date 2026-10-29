"""Actual process crash and HTTP controls, not merely object reconstruction."""
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.request

from mnq_local.replay import ROOT, ReplaySession


def test_real_process_sigkill_then_exact_resume(tmp_path):
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    run_dir = tmp_path/'crash'
    log = (tmp_path/'process.txt').open('w')
    process = subprocess.Popen([str(ROOT/'run-local.sh'), 'app', '--run-dir', str(run_dir),
        '--port', str(port), '--delay', '.02'], stdout=log, stderr=log)
    url = f'http://127.0.0.1:{port}'
    def get(path):
        with urllib.request.urlopen(url+path, timeout=2) as response:
            return response.read()
    try:
        deadline = time.monotonic()+30
        while True:
            try:
                status = json.loads(get('/api/status'))
                if status['report'].get('bars_processed', 0) >= 100:
                    break
            except (OSError, ValueError):
                pass
            assert time.monotonic() < deadline
            time.sleep(.05)
        page = get('/').decode()
        token = re.search("const token='([^']+)'", page)[1]
        def control(action):
            request = urllib.request.Request(url+'/api/control', json.dumps({'action': action}).encode(),
                headers={'Origin': url, 'X-Control-Token': token, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=2):
                pass
        control('pause')
        for _ in range(50):
            if json.loads(get('/api/status'))['phase'] == 'PAUSED':
                break
            time.sleep(.02)
        else:
            raise AssertionError('HTTP pause not applied')
        cursor = json.loads(get('/api/status'))['report']['bars_processed']
        time.sleep(.1)
        assert json.loads(get('/api/status'))['report']['bars_processed'] == cursor
        control('resume')
        time.sleep(.1)
        process.kill()  # SIGKILL: no finally block or artificial graceful recovery.
        process.wait(timeout=10)
        with sqlite3.connect(run_dir/'state.sqlite') as db:
            assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
            committed = json.loads(db.execute('SELECT body FROM snapshot WHERE id=1').fetchone()[0])
        assert 100 <= committed['local_replay']['cursor'] < 780
        completed = subprocess.run([str(ROOT/'run-local.sh'), 'app', '--headless', '--run-dir', str(run_dir)],
            capture_output=True, text=True, timeout=40)
        assert completed.returncode == 0, completed.stderr
        actual = json.loads((run_dir/'summary.json').read_text())
        baseline = ReplaySession(tmp_path/'reference')
        baseline.run()
        expected = baseline.report()
        baseline.close()
        for key in ('net', 'gross', 'fees', 'max_drawdown', 'trades', 'ambiguities', 'orders'):
            assert actual[key] == expected[key]
        assert (run_dir/'trades.csv').read_bytes() == (tmp_path/'reference/trades.csv').read_bytes()
        assert actual['complete'] and actual['bars_processed'] == 780
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        log.close()
