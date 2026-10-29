"""Bounded read-only native candle evidence; no order mutations."""
import time,json,argparse
from pathlib import Path
from datetime import datetime,timezone
from mnq_local.capital import CapitalHTTP,Credentials,CapitalError
p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=720);a=p.parse_args()
out=Path(__file__).resolve().parent;h=CapitalHTTP(Credentials.load(),orders_enabled=False);h.login();start=time.monotonic();count=0;errors=[]
with (out/'raw-candles.jsonl').open('x') as f:
 while time.monotonic()-start<a.seconds:
  cycle=time.monotonic()
  for epic in ('US100','US500'):
   for resolution in ('MINUTE','MINUTE_5'):
    before=time.time_ns();mono=time.monotonic_ns()
    try:
     data=h.request('GET',f'/prices/{epic}?resolution={resolution}&max=10');received=time.time_ns()
     f.write(json.dumps({'epic':epic,'resolution':resolution,'request_started_ns':before,'received_ns':received,
       'request_ms':(time.monotonic_ns()-mono)/1e6,'payload':data})+'\n');count+=1
    except CapitalError as e:errors.append({'epic':epic,'resolution':resolution,**e.diagnostic()})
  f.flush();(out/'raw-progress.json').write_text(json.dumps({'elapsed_s':time.monotonic()-start,'responses':count,'errors':errors}))
  if errors:break
  time.sleep(max(0,2-(time.monotonic()-cycle)))
(out/'raw-completion.json').write_text(json.dumps({'elapsed_s':time.monotonic()-start,'responses':count,'errors':errors,'orders_enabled':h.orders_enabled},indent=2))
print('READONLY_NATIVE_CAPTURE_COMPLETED',count)
