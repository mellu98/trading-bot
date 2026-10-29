import json
import pytest
from test_databento_live import SPECS,OPEN,grant


def test_unlicensed_cli_preflight_reports_block_without_network_or_sdk(monkeypatch,capsys,tmp_path):
 from mnq_local.databento_app import main
 import databento
 monkeypatch.setattr(databento,'Live',lambda **k:pytest.fail('Unlicensed SDK constructed'))
 doc=grant();doc['license_confirmed']=False;path=tmp_path/'grant.json';path.write_text(json.dumps(doc))
 assert main(['preflight','--authorization',str(path),'--session','2026-10-26'],clock_ns=lambda:OPEN)==2
 report=json.loads(capsys.readouterr().out)
 assert report['status']=='BLOCKED' and report['network_connections']==0
 assert report['simulated_orders_enabled'] is False


def test_app_mode_with_no_license_exits_before_keychain_or_socket(tmp_path,monkeypatch,capsys):
 from mnq_local.databento_app import main
 path=tmp_path/'grant.json';path.write_text('{}')
 assert main(['app','--authorization',str(path)],clock_ns=lambda:OPEN)==2
 assert json.loads(capsys.readouterr().out)['status']=='BLOCKED'


def test_live_dashboard_labels_and_api_reuse_existing_loopback_controls(tmp_path):
 import queue,threading,urllib.request,urllib.error
 from mnq_local.dashboard import Dashboard,View
 from mnq_local.databento_app import LiveHandler
 view=View();view.update({'mode':'CME_LIVE_DATA_LOCAL_SIMULATION','simulated_entries_enabled':False,'net':0},[],[],[])
 server=Dashboard(('127.0.0.1',0),view,queue.Queue(),tmp_path);server.RequestHandlerClass=LiveHandler
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 url=f'http://127.0.0.1:{server.server_port}'
 try:
  with urllib.request.urlopen(url) as response:
   html=response.read().decode()
   assert 'DATABENTO CME LIVE DATA' in html and 'LOCAL SIMULATION' in html and 'NO BROKER' in html
   assert 'SYNTHETIC' not in html or 'exchange executions' in html
   assert '${r.simulated_entries_enabled}' in html
   assert "el('progress').max=Math.max(1,r.bars_processed)" in html
   assert 'Content-Security-Policy' in response.headers
  with urllib.request.urlopen(url+'/api/status') as response:
   assert not json.load(response)['report']['simulated_entries_enabled']
  with pytest.raises(urllib.error.HTTPError):urllib.request.urlopen(url+'/download/state.sqlite')
  with pytest.raises(urllib.error.HTTPError):
   urllib.request.urlopen(urllib.request.Request(url+'/api/control',b'{"action":"resume"}',headers={'Content-Type':'application/json'}))
 finally:server.shutdown();server.server_close();thread.join()
