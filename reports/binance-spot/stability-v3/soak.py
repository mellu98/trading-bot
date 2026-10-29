"""Bounded real observer soak; controlled flat restart, never resets its journal."""
from pathlib import Path
import json,time,urllib.request,subprocess,os,signal,hashlib
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
start=time.monotonic();restarted=False;count=0;errors=[];durations=[];pids=[]
def save(name,x):(OUT/name).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def state():
 a=time.monotonic_ns()
 with urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=3) as f:x=json.load(f)
 durations.append((time.monotonic_ns()-a)/1e6)
 r=x['report']
 assert r['budget_spent'] and r['buy_count']==1 and r['sell_count']==1 and r['position'] is None
 assert r['cash']=='999.76609237980375000000000'
 return x
pids.append(int((OUT/'observer.pid').read_text()));save('soak-start.json',{'at_ns':time.time_ns(),'pid':pids[0],'duration_target_seconds':620,'controlled_restart_after_seconds':300,'concurrent_work':'QUIET control: no tests, model inference, backtests or strategy jobs. Parent source review/read-only portal work may occur; OS load from other applications is not controlled.'})
with (OUT/'soak-samples.jsonl').open('w',buffering=1) as f:
 while time.monotonic()-start<620:
  elapsed=time.monotonic()-start
  try:
   x=state();r=x['report'];fm=r['feed_metrics'];count+=1
   f.write(json.dumps({'elapsed_seconds':elapsed,'at_ns':time.time_ns(),'phase':x['phase'],'updated_at':x['updated_at'],'certificate':r['certificate'],'feed':fm,'flat_spent':r['observe_only'],'cash':r['cash'],'http_client_ms':durations[-1]})+'\n')
  except Exception as exc:errors.append({'elapsed':elapsed,'type':type(exc).__name__,'message':str(exc)})
  if not restarted and elapsed>=300:
   save('pre-restart-state.json',state());save('pre-restart-metrics.json',json.loads((OUT/'pipeline-metrics.json').read_text()))
   os.kill(pids[-1],signal.SIGTERM)
   for _ in range(50):
    try:os.kill(pids[-1],0)
    except ProcessLookupError:break
    time.sleep(.1)
   log=(OUT/'observer.log').open('a')
   p=subprocess.Popen([str(ROOT/'run-binance-paper.sh'),'--report',str(OUT)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);pids.append(p.pid);(OUT/'observer.pid').write_text(str(p.pid)+'\n')
   save('controlled-restart.json',{'at_ns':time.time_ns(),'pids':pids,'same_journal':str(ROOT/'data/binance-spot/paper.sqlite'),'flat_before_restart':True,'no_budget_reset':True,'cause':'Planned public websocket process shutdown/restart, not a provider fault'})
   restarted=True;time.sleep(4)
  time.sleep(1)
final=state();save('post-soak-state.json',final);save('post-soak-metrics.json',json.loads((OUT/'pipeline-metrics.json').read_text()))
durations.sort();n=len(durations)
save('soak-summary.json',{'actual_seconds':time.monotonic()-start,'samples':count,'errors':errors,'pids':pids,'controlled_restart':restarted,'client_response_ms':{k:durations[int((n-1)*p)] for k,p in [('p50',.5),('p95',.95),('p99',.99),('max',1)]},'final_flat_spent':final['report']['observe_only']})
