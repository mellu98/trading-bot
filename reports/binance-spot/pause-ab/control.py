"""One frozen ABBA attempt sequence; no retries or financial state reset."""
from pathlib import Path
import hashlib,json,os,signal,sqlite3,subprocess,sys,time,urllib.request
import pause
ROOT=pause.ROOT;OUT=Path(__file__).resolve().parent

def spawn(mode,folder):
 folder.mkdir(parents=True,exist_ok=True);log=(folder/'process.log').open('a');cmd=[sys.executable,str(OUT/'pause.py'),mode,'--folder',str(folder)]
 if mode=='external':cmd=[sys.executable,str(OUT/'external.py'),'--folder',str(folder)]
 p=subprocess.Popen(cmd,cwd=ROOT,env=ENV,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);pause.save(folder/'launch.json',{'at_ns':time.time_ns(),'pid':p.pid,'mode':mode});return p

def stop(p):
 if p.poll() is None:
  p.terminate()
  try:p.wait(30)
  except subprocess.TimeoutExpired:p.kill();p.wait()

if __name__=='__main__':
 protocol=json.loads((OUT/'protocol.json').read_text())
 for k,h in protocol['sources'].items():assert hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==h
 for k,h in json.loads((OUT/'protected-before.json').read_text()).items():assert hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==h
 ENV=dict(os.environ);ENV.update(PYTHONPATH=str(ROOT/'src'),PYTHONDONTWRITEBYTECODE='1')
 # Existing main observer is already failed-closed; only owned forward collector stopped.
 try:os.kill(90259,signal.SIGTERM)
 except ProcessLookupError:pass
 time.sleep(1);start=time.time_ns();w=spawn('W',OUT/'live/witness');dummy={'path':str(OUT/'live/not-ready.mmap'),'pid':0};pause.save(OUT/'live/targets.json',{'phase':'startup','pids':[w.pid],'heartbeats':{'witness':{'pid':w.pid,'path':str(OUT/'live/witness/heartbeat.mmap')}},'sampling_enabled':False});external=spawn('external',OUT/'live');results=[];current=None
 pause.save(OUT/'live/start.json',{'at_ns':start,'order':list('ABBA'),'connected_target_per_attempt_seconds':600,'wall_cap_per_attempt_seconds':900,'no_retries':True,'no_concurrent_tests_models_backtests':True})
 try:
  for i,arm in enumerate('ABBA',1):
   folder=OUT/'live'/f'{i:02d}-{arm}';current=spawn(arm,folder);target={'phase':f'{i:02d}-{arm}','pids':[current.pid,w.pid,external.pid],'heartbeats':{'runtime':{'pid':current.pid,'path':str(folder/'heartbeat.mmap')},'witness':{'pid':w.pid,'path':str(OUT/'live/witness/heartbeat.mmap')}},'sampling_enabled':True};pause.save(OUT/'live/targets.json',target);samples=[];reader=None;begin=time.monotonic();reason='consumer_process_exit';connected=0
   while current.poll() is None:
    try:
     if reader is None:reader=pause.Heartbeat(folder/'heartbeat.mmap')
     hb=reader.read(96);flags=reader.read(128);fresh=reader.read(160);owner=reader.read(0)
     if hb:connected=hb[1]/1e9
     if flags:assert flags[1]%16==7
     row={'at_ns':time.time_ns(),'mono_ns':time.monotonic_ns(),'connected_seconds':connected,'owner_heartbeat':owner,'flags_and_rejections':flags,'fresh_bits':fresh}
     if arm=='A':
      try:
       a=time.monotonic_ns()
       with urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=2) as response:doc=json.load(response)
       row['http_ms']=(time.monotonic_ns()-a)/1e6;row['certificate']=doc['report']['feed_metrics']
      except Exception as exc:row['ui_error']=type(exc).__name__
     samples.append(row)
    except (OSError,ValueError):pass
    if connected>=600:reason='connected_target_reached';break
    if time.monotonic()-begin>900:reason='wall_cap_reached';break
    if time.monotonic()-begin>45 and not connected:reason='startup_timeout';break
    time.sleep(1)
   target['sampling_enabled']=False;pause.save(OUT/'live/targets.json',target);stop(current)
   if reader:reader.close()
   pause.save(folder/'controller-samples.json',samples);record={'segment':folder.name,'arm':arm,'pid':current.pid,'stop_reason':reason,'returncode':current.returncode,'actual_controller_wall_seconds':time.monotonic()-begin,'last_observed_connected_seconds':connected};results.append(record);pause.save(OUT/'live/progress.json',results);current=None
 finally:
  if current:stop(current)
  stop(w);stop(external)
  log=(OUT/'observer/observer.log').open('a');p=subprocess.Popen([str(ROOT/'run-binance-paper.sh'),'--report',str(OUT/'observer')],cwd=ROOT,env=ENV,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);(OUT/'observer/observer.pid').write_text(str(p.pid)+'\n')
  log2=(ROOT/'reports/binance-spot/forward-signals/recorder.log').open('a');f=subprocess.Popen([sys.executable,str(ROOT/'reports/binance-spot/forward-signals/recorder.py'),'record'],cwd=ROOT,env=ENV,stdin=subprocess.DEVNULL,stdout=log2,stderr=subprocess.STDOUT,start_new_session=True);(ROOT/'reports/binance-spot/forward-signals/recorder.pid').write_text(str(f.pid)+'\n');pause.save(OUT/'live/complete.json',{'started_ns':start,'ended_ns':time.time_ns(),'attempts':results,'observer_pid':p.pid,'forward_pid':f.pid,'same_spent_journal':True,'actionable':False})
