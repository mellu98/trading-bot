"""Sequential bounded orchestration only; no change to financial or vendor code."""
from pathlib import Path
import json,os,signal,subprocess,sys,time,urllib.request,hashlib
ROOT=Path(__file__).resolve().parents[3];BASE=Path(__file__).resolve().parent;OUT=BASE/'main';RUN=BASE/'runner.py'
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def status():
 a=time.monotonic_ns()
 with urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=5) as f:x=json.load(f)
 r=x['report'];assert r['observe_only'] and r['budget_spent'] and r['position'] is None and r['buy_count']==r['sell_count']==1 and r['cash']=='999.76609237980375000000000' and r['timestral']=='DISABLED'
 return x,(time.monotonic_ns()-a)/1e6

def stop(p):
 if p.poll() is None:
  p.send_signal(signal.SIGTERM)
  try:p.wait(30)
  except subprocess.TimeoutExpired:p.kill();p.wait()

def launch(mode,folder,seconds=0):
 folder.mkdir(parents=True,exist_ok=True);log=(folder/'process.log').open('a');command=([str(ROOT/'.venv/bin/python'),str(BASE/'sampler-v2.py'),'--folder',str(folder)] if mode=='sample' else [str(ROOT/'.venv/bin/python'),str(RUN),mode,'--folder',str(folder),'--seconds',str(seconds)]);p=subprocess.Popen(command,cwd=ROOT,env=ENV,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);save(folder/'launch.json',{'pid':p.pid,'at_ns':time.time_ns(),'mode':mode,'seconds':seconds});return p

if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True);protocol=json.loads((BASE/'protocol.json').read_text())
 addendum=json.loads((BASE/'telemetry-addendum.json').read_text())
 for path,digest in addendum['sources'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
 for path,digest in protocol['sources'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
 for path,digest in json.loads((BASE/'protected-before.json').read_text()).items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
 ENV=dict(os.environ);ENV.update(PYTHONPATH=str(ROOT/'src'),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1')
 old,status_ms=status();save(OUT/'before-stop-state.json',old)
 for pid in [int((ROOT/'reports/binance-spot/stability-v3/observer.pid').read_text()),int((ROOT/'reports/binance-spot/forward-signals/recorder.pid').read_text())]:
  os.kill(pid,signal.SIGTERM)
  for _ in range(100):
   try:os.kill(pid,0)
   except ProcessLookupError:break
   time.sleep(.1)
 start=time.time_ns();save(OUT/'mission-start.json',{'at_ns':start,'expected_minimum_seconds':4302,'order':protocol['order'],'no_concurrent_tests_models_backtests':True,'old_pids_stopped':'Currentownedobserver/forwardPIDfiles; seebefore-stop-state'})
 witness=launch('W',OUT/'witness');save(OUT/'targets.json',{'phase':'startup','pids':[witness.pid]});sampler=launch('sample',OUT)
 ledger=[]
 try:
  for i,arm in enumerate(protocol['order']):
   folder=OUT/f'{i+1:02d}-{arm}';p=launch(arm,folder,300 if arm!='D' else 0);save(OUT/'targets.json',{'phase':f'{i+1:02d}-{arm}','pids':[p.pid,witness.pid,sampler.pid]});samples=[];begin=time.monotonic()
   while p.poll() is None:
    if arm=='D':
     try:
      x,ms=status();samples.append({'at_ns':time.time_ns(),'http_ms':ms,'phase':x['phase'],'report':x['report']})
      if x['report'].get('isolation_connected_seconds',0)>=301:break
     except Exception as exc:samples.append({'at_ns':time.time_ns(),'not_ready':type(exc).__name__})
    if time.monotonic()-begin>450:break
    time.sleep(1)
   stop(p);save(folder/'controller-samples.json',samples)
   result=json.loads((folder/('arm-extra.json' if arm=='D' else 'result.json')).read_text());ledger.append({'segment':i+1,'arm':arm,'pid':p.pid,'result':result});save(OUT/'progress.json',{'at_ns':time.time_ns(),'completed_segments':len(ledger),'ledger':ledger})
   if result['connected_seconds']<300:raise RuntimeError('Actual connected duration insufficient; partial evidence preserved')
  # Two sequential950connected-second fullD portions provide>=1800excluding restartdown time.
  soak=[]
  for j in [1,2]:
   folder=OUT/f'soak-{j}';p=launch('D',folder);save(OUT/'targets.json',{'phase':f'soak-{j}','pids':[p.pid,witness.pid,sampler.pid]});samples=[];begin=time.monotonic()
   while p.poll() is None:
    try:
     x,ms=status();samples.append({'at_ns':time.time_ns(),'http_ms':ms,'phase':x['phase'],'report':x['report']})
     if x['report'].get('isolation_connected_seconds',0)>=951:break
    except Exception as exc:samples.append({'at_ns':time.time_ns(),'not_ready':type(exc).__name__})
    if time.monotonic()-begin>1300:break
    time.sleep(1)
   stop(p);save(folder/'controller-samples.json',samples);r=json.loads((folder/'arm-extra.json').read_text());soak.append({'pid':p.pid,'result':r});save(OUT/'soak-progress.json',{'at_ns':time.time_ns(),'portions':soak,'planned_flat_restart':True})
  save(OUT/'complete.json',{'started_ns':start,'ended_ns':time.time_ns(),'ledger':ledger,'soak':soak,'soak_connected_seconds':sum(x['result']['connected_seconds'] for x in soak),'no_new_orders':True})
 finally:
  stop(witness);stop(sampler)
  # Restore only our original observing processes with the same spent journal.
  log=(ROOT/'reports/binance-spot/stability-v3/observer.log').open('a');p=subprocess.Popen([str(ROOT/'run-binance-paper.sh'),'--report',str(ROOT/'reports/binance-spot/stability-v3')],cwd=ROOT,env=ENV,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);(ROOT/'reports/binance-spot/stability-v3/observer.pid').write_text(str(p.pid)+'\n')
  log2=(ROOT/'reports/binance-spot/forward-signals/recorder.log').open('a');f=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'reports/binance-spot/forward-signals/recorder.py'),'record'],cwd=ROOT,env=ENV,stdin=subprocess.DEVNULL,stdout=log2,stderr=subprocess.STDOUT,start_new_session=True);(ROOT/'reports/binance-spot/forward-signals/recorder.pid').write_text(str(f.pid)+'\n');save(OUT/'restored.json',{'at_ns':time.time_ns(),'observer_pid':p.pid,'forward_pid':f.pid,'same_spent_journal':True,'actionable':False})
