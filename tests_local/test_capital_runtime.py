"""Offline CFD coordinator tests. None establish a real Capital broker session."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
from pathlib import Path
import queue
import socket
import subprocess
import threading
import urllib.request
import pytest
from mnq_local.capital import Quote
from mnq_local.capital_app import CFDSignals,DemoRuntime,DemoView,DemoHandler,JS,status
from mnq_local.dashboard import Dashboard
from test_capital_demo import make,instrument_fixture

UTC=timezone.utc


def test_dashboard_javascript_parses(tmp_path):
    path=tmp_path/'app.js';path.write_text(JS)
    result=subprocess.run(['/Users/locoframe/.local/node/bin/node','--check',str(path)],capture_output=True)
    assert result.returncode==0,result.stderr.decode()


def test_partial_cash_opening_and_unknown_tick_block_signals():
    now=datetime(2026,10,26,14,10,tzinfo=UTC)
    spec=instrument_fixture()
    s=CFDSignals(spec,now)
    q=Quote('EPIC1',Decimal('100'),Decimal('100.2'),int(now.timestamp()*1000),now)
    assert s.on_quote(q)==[] and s.blocked=='partial_opening_session'


def test_live_quote_bar_orb_is_causal_and_vwap_not_invented():
    start=datetime(2026,10,26,13,30,tzinfo=UTC)
    spec=instrument_fixture();spec.raw['discovery']={'tickSize':.1}
    s=CFDSignals(spec,start-timedelta(seconds=1));signals=[]
    for minute in range(18):
        at=start+timedelta(minutes=minute,seconds=1)
        price=Decimal('100') if minute<15 else Decimal('102')
        q=Quote('EPIC1',price,price+Decimal('.2'),int(at.timestamp()*1000),at)
        signals.extend(s.on_quote(q))
    orb=[e for e in signals if e['strategy']=='orb']
    assert len(orb)==1 and orb[0]['side']==1
    assert orb[0]['received_at']>orb[0]['bar_end']
    assert all(e['strategy']!='vwap' for e in signals)
    with pytest.raises(ValueError):s.on_quote(q)


def test_tick_gap_rejects_continuity():
    start=datetime(2026,10,26,13,30,tzinfo=UTC)
    spec=instrument_fixture();spec.raw['discovery']={'tickSize':.1}
    s=CFDSignals(spec,start-timedelta(seconds=1))
    for n in (0,2):
        at=start+timedelta(minutes=n,seconds=1)
        s.on_quote(Quote('EPIC1',Decimal('100'),Decimal('100.1'),int(at.timestamp()*1000),at))
    assert s.blocked=='quote_bar_gap'


def test_runtime_staleness_duplicate_quote_and_reconnect(tmp_path):
    f,h,j,b=make(tmp_path)
    try:
        b.instruments['EPIC1']=instrument_fixture()
        at=[datetime(2026,10,26,12,0,tzinfo=UTC)]
        runtime=DemoRuntime(b,clock=lambda:at[0]);runtime.connected=True
        payload={'epic':'EPIC1','product':'CFD','timestamp':int(at[0].timestamp()*1000),'bid':100,'ofr':100.1}
        runtime.on_quote(payload)
        with pytest.raises(ValueError):runtime.on_quote(payload)
        at[0]+=timedelta(seconds=6)
        with pytest.raises(Exception,match='stale'):runtime.watchdog()
        assert not b.ready
        runtime.disconnect();assert not runtime.connected and runtime.fresh_quotes==0
    finally:j.close()


def test_dashboard_http_real_unknown_values_and_host_guard(tmp_path):
    view=DemoView();view.publish(status(error='missing_demo_credentials_in_keychain'))
    server=Dashboard(('127.0.0.1',0),view,queue.Queue(),tmp_path);server.RequestHandlerClass=DemoHandler
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urllib.request.urlopen(base) as response:
            text=response.read().decode();assert response.status==200
            assert 'Timestral actual inference' in text and 'BROKER' not in text[:1]
            assert 'CAPITAL LIVE DATA / DEMO ONLY' in text
        with urllib.request.urlopen(base+'/api/status') as response:
            value=json.load(response);assert not value['authenticated'] and value['capital']=={}
        request=urllib.request.Request(base+'/api/control',data=b'{"action":"kill"}',headers={'Content-Type':'application/json'},method='POST')
        with pytest.raises(urllib.error.HTTPError):urllib.request.urlopen(request)
    finally:server.shutdown();server.server_close();thread.join()
