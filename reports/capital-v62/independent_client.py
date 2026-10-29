"""Independent Node transport compared with the same DEMO REST quotes."""
import importlib.util,json,subprocess,threading,time,os
from datetime import datetime,timezone
from pathlib import Path
from mnq_local.capital import CapitalHTTP,Credentials,rest_snapshot_payload
root=Path(__file__).resolve().parent;spec=importlib.util.spec_from_file_location('compare',root/'compare.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
h=CapitalHTTP(Credentials.load(),orders_enabled=False);h.login();subscription=json.loads(h.stream_message('marketData.subscribe',['US100','US500']))
rows=[];result={};errors=[];clock=[];t0=time.monotonic();seconds=120
proc=subprocess.Popen(['node',str(root/'node_ws.js')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
 env={**{k:v for k,v in os.environ.items() if k not in ('NODE_USE_ENV_PROXY',)},'NODE_TLS_REJECT_UNAUTHORIZED':'1'})
def receive():
 try:
  text,stderr=proc.communicate(json.dumps({'subscription':subscription,'seconds':seconds}),timeout=seconds+20)
  result.update(json.loads(text));rows.extend(result.pop('rows'))
 except Exception:errors.append('independent_client_failed')
python_rows=[];python_meta={};done=threading.Event()
def python_receive():
 from websockets.sync.client import connect
 from mnq_local.capital import STREAM
 try:
  with connect(STREAM,proxy=None,open_timeout=12,close_timeout=3,max_size=65536,max_queue=16,ping_interval=20) as ws:
   python_meta['extensions']=ws.response.headers.get('Sec-WebSocket-Extensions')
   ws.send(json.dumps(subscription))
   while not done.is_set():
    try:raw=ws.recv(timeout=.25)
    except TimeoutError:continue
    receipt=time.time_ns();mono=time.monotonic_ns();m=json.loads(raw)
    if m.get('destination')=='quote':
     q=m['payload'];python_rows.append({'channel':'WS','epic':q['epic'],'source_ms':q['timestamp'],'receipt_ns':receipt,'monotonic_ns':mono,'bid':str(q['bid']),'ask':str(q['ofr']),'processing_ms':(time.monotonic_ns()-mono)/1e6})
 except Exception as e:python_meta['error']=type(e).__name__
thread=threading.Thread(target=receive);thread.start();pythread=threading.Thread(target=python_receive);pythread.start();last_clock=-1e9
while time.monotonic()-t0<seconds:
 start=time.monotonic()
 if start-last_clock>=15:
  before=time.time_ns();server=h.request('GET','/time')['serverTime'];after=time.time_ns();clock.append({'offset_interval_ms':[server-after/1e6,server-before/1e6]});last_clock=start
 data=h.request('GET','/markets?searchTerm=US');receipt=time.time_ns();mono=time.monotonic_ns()
 for e in ('US100','US500'):
  matches=[m for m in data['markets'] if m['epic']==e];assert len(matches)==1
  p=rest_snapshot_payload(matches[0]);rows.append({'channel':'REST','epic':e,'source_ms':p['timestamp'],'receipt_ns':receipt,'monotonic_ns':mono,'bid':str(p['bid']),'ask':str(p['ofr']),'processing_ms':0})
 time.sleep(max(0,1-(time.monotonic()-start)))
thread.join(20);assert not thread.is_alive();done.set();pythread.join(5);assert not pythread.is_alive()
result.update(duration_s=time.monotonic()-t0,clock_checks=clock,analysis=mod.analyze(rows),errors=result.get('errors',[])+errors,orders_enabled=h.orders_enabled)
result['python_analysis']=mod.analyze([r for r in rows if r['channel']=='REST']+python_rows);result['python_meta']=python_meta
(root/'python-concurrent-rows.json').write_text(json.dumps(python_rows,indent=2))
(root/'independent-rows.json').write_text(json.dumps(rows,indent=2));(root/'independent-result.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'duration_s':result['duration_s'],'client':result.get('client'),'errors':result['errors'],
 'same_event':{e:result['analysis'][e]['same_source_event'] for e in ('US100','US500')}}))
