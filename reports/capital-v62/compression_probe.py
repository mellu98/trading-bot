"""Read-only compression-disabled control, independent from the runtime."""
import time,json,importlib.util
from pathlib import Path
from websockets.sync.client import connect
from mnq_local.capital import CapitalHTTP,Credentials,STREAM
root=Path(__file__).resolve().parent;spec=importlib.util.spec_from_file_location('compare',root/'compare.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
h=CapitalHTTP(Credentials.load(),orders_enabled=False);h.login();rows=[];start=time.monotonic()
with connect(STREAM,proxy=None,compression=None,open_timeout=12,close_timeout=3,max_size=65536,max_queue=16,ping_interval=20) as ws:
    extensions=ws.response.headers.get('Sec-WebSocket-Extensions');ws.send(h.stream_message('marketData.subscribe',['US100','US500']))
    while time.monotonic()-start<60:
        try:raw=ws.recv(timeout=.25)
        except TimeoutError:continue
        received=time.time_ns();mono=time.monotonic_ns();msg=json.loads(raw)
        if msg.get('destination')=='quote':
            q=msg['payload'];rows.append({'channel':'WS','epic':q['epic'],'source_ms':q['timestamp'],'receipt_ns':received,'monotonic_ns':mono,'bid':str(q['bid']),'ask':str(q['ofr']),'processing_ms':(time.monotonic_ns()-mono)/1e6})
result={'duration_s':time.monotonic()-start,'compression':None,'extensions':extensions,'analysis':m.analyze(rows)}
(root/'compression-none-rows.json').write_text(json.dumps(rows,indent=2));(root/'compression-none-result.json').write_text(json.dumps(result,indent=2))
print(json.dumps({e:result['analysis'][e]['WS']['timestamp_age_ms'] for e in m.EPICS}))
