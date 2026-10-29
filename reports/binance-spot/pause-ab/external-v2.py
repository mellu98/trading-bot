"""Existing low-overhead OS sampler plus bounded, independent heartbeat triggers."""
import argparse,importlib.util,json,os,resource,signal,subprocess,threading,time
from pathlib import Path
from collections import deque
import pause
import importlib.util
_t=importlib.util.spec_from_file_location('targets_v2',Path(__file__).with_name('targets-v2.py'));tio=importlib.util.module_from_spec(_t);_t.loader.exec_module(tio)
s=importlib.util.spec_from_file_location('existing_sampler',pause.ROOT/'reports/binance-spot/stability-isolation/sampler-v2.py');sampler=importlib.util.module_from_spec(s);s.loader.exec_module(sampler)

def run(folder):
 folder=Path(folder);stop=threading.Event();started=time.monotonic();budget=pause.CaptureBudget();active=[];captures=[];events=deque(maxlen=10000);readers={};last_good={};last_os=0;last_poll=time.monotonic_ns();polls=0;missed=0;last_targets=None
 for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
 io=(folder/'interval-iostat.jsonl').open('a',buffering=1);disk=subprocess.Popen(['iostat','-C','-d','-w','5'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1);classifier=sampler.IntervalRows()
 def collect():
  for line in disk.stdout:io.write(json.dumps({'at_ns':time.time_ns(),'mono_ns':time.monotonic_ns(),'raw':line.rstrip(),'parsed':classifier.add(line)})+'\n')
 thread=threading.Thread(target=collect,daemon=True);thread.start();osfile=(folder/'os-samples.jsonl').open('a',buffering=1)
 def capture(target,role,hb,reason,segment):
  now=time.monotonic_ns();index=len(captures)+len(active)+1;path=folder/'stacks'/f'{index:02d}-{segment}-{role}.txt';path.parent.mkdir(exist_ok=True)
  record={'segment':segment,'pid':target['pid'],'role':role,'reason':reason,'hb_before':hb,'started_wall_ns':time.time_ns(),'started_mono_ns':now,'file':str(path.relative_to(pause.ROOT)),'duration_seconds':1,'sampling_interval_ms':10,'censored':'Entire sampler-process-active window plus200ms; pretrigger evidence retained','first_heartbeat_advance_mono_ns':None}
  registered=last_good.get((target['path'],192));pyfile=Path(target['path']).with_name('python-stacks.txt')
  record['python_signal_registered']=bool(registered and registered[1]==target['pid']);record['python_file']=str(pyfile.relative_to(pause.ROOT));record['python_bytes_before']=pyfile.stat().st_size if pyfile.exists() else 0
  if record['python_signal_registered']:
   try:record['python_signal_request_mono_ns']=time.monotonic_ns();record['python_signal_request_wall_ns']=time.time_ns();os.kill(target['pid'],signal.SIGUSR2)
   except ProcessLookupError:record['python_signal_error']='owned_process_exited'
  child=subprocess.Popen(['/usr/bin/sample',str(target['pid']),'1','10','-file',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);record['capture_pid']=child.pid;active.append((child,record));budget.used(segment if role=='runtime' else segment+'-W',time.monotonic())
 try:
  while not stop.is_set():
   now=time.monotonic_ns();gap=(now-last_poll)/1e6;last_poll=now;polls+=1
   if gap>40:events.append({'kind':'external_poll_delay','at_ns':time.time_ns(),'mono_ns':now,'gap_ms':gap})
   targets=tio.read_targets(folder/'targets.json',last_targets);last_targets=targets
   if targets is None:stop.wait(.02);continue
   observed={}
   for role,target in targets['heartbeats'].items():
    path=target['path']
    if path not in readers:
     try:readers[path]=pause.Heartbeat(path)
     except (OSError,ValueError):continue
    for slot in [0,32,64,96,128,160,192]:
     value=readers[path].read(slot)
     if value is not None:last_good[(path,slot)]=value
    value=last_good.get((path,0))
    if value:observed[role]={'heartbeat':value,'age_ms':max(0,(now-value[0])/1e6),'target':target,'worker':last_good.get((path,32)),'queue':last_good.get((path,64)),'registered':last_good.get((path,192))}
   main=observed.get('runtime');w=observed.get('witness');segment=targets['phase']
   if main and targets.get('sampling_enabled',True):
    stage=main['worker'];depth=main['queue'][1] if main['queue'] else 0;worker_stall=stage is not None and stage[1]!=0 and depth>=8 and now-stage[0]>250000000
    age=max(main['age_ms'],(now-stage[0])/1e6 if worker_stall else 0)
    if budget.allowed(segment,age,time.monotonic()):
     reason='worker_backlog' if worker_stall and main['age_ms']<=100 else 'owner_heartbeat';hb=stage if reason=='worker_backlog' else main['heartbeat'];events.append({'kind':'trigger','at_ns':time.time_ns(),'mono_ns':now,'segment':segment,'runtime':{k:v for k,v in main.items() if k!='target'},'witness':{k:v for k,v in w.items() if k!='target'} if w else None,'external_gap_ms':gap});capture(main['target'],'runtime',hb,reason,segment)
   for child,record in list(active):
    pyfile=pause.ROOT/record['python_file']
    if pyfile.exists() and pyfile.stat().st_size>record['python_bytes_before'] and 'python_dump_observed_mono_ns' not in record:record['python_dump_observed_mono_ns']=time.monotonic_ns();record['python_dump_mtime_ns']=pyfile.stat().st_mtime_ns;record['python_bytes_after']=pyfile.stat().st_size
    key=(str(pause.ROOT/record['file']).split('/stacks/')[0],record['pid'])
    obs=next((x for x in observed.values() if x['target']['pid']==record['pid']),None)
    current=obs['worker'] if obs and record['reason']=='worker_backlog' else obs['heartbeat'] if obs else None
    if current and current!=tuple(record['hb_before']) and record['first_heartbeat_advance_mono_ns'] is None:record['first_heartbeat_advance_mono_ns']=now if record['reason']=='worker_backlog' else current[0]
    if now-record['started_mono_ns']>15000000000 and child.poll() is None:child.kill();record['timeout']=True
    if child.poll() is not None:
     stdout,stderr=child.communicate();record.update(ended_wall_ns=time.time_ns(),ended_mono_ns=time.monotonic_ns(),returncode=child.returncode,stdout=stdout,stderr=stderr);captures.append(record);active.remove((child,record));pause.save(folder/'captures.json',captures)
   if now-last_os>=5000000000:
    a=time.monotonic_ns();cpu=time.process_time();u=resource.getrusage(resource.RUSAGE_CHILDREN);row={'at_ns':time.time_ns(),'mono_ns':a,'targets':targets,'load':os.getloadavg(),'commands':{},'errors':{}}
    commands=sampler.low_commands(targets['pids']+[os.getpid(),disk.pid]);commands['processes'][-1]+=',stat=,wchan='
    for name,cmd in commands.items():
     try:row['commands'][name]=subprocess.check_output(cmd,text=True,timeout=2,stderr=subprocess.DEVNULL)
     except (OSError,subprocess.SubprocessError) as exc:row['errors'][name]=type(exc).__name__
    v=resource.getrusage(resource.RUSAGE_CHILDREN);row.update(sampler_wall_ms=(time.monotonic_ns()-a)/1e6,sampler_cpu_ms=(time.process_time()-cpu)*1000,sampler_children_cpu_ms=(v.ru_utime+v.ru_stime-u.ru_utime-u.ru_stime)*1000,capture_active_pids=[p.pid for p,_ in active]);osfile.write(json.dumps(row,sort_keys=True)+'\n');last_os=now
   stop.wait(max(0,.02-(time.monotonic_ns()-now)/1e9))
 finally:
  for child,record in active:
   if child.poll() is None:child.terminate()
   stdout,stderr=child.communicate(timeout=5);record.update(ended_wall_ns=time.time_ns(),ended_mono_ns=time.monotonic_ns(),returncode=child.returncode,stdout=stdout,stderr=stderr,ended_with_probe=True);captures.append(record)
  for h in readers.values():h.close()
  disk.terminate();disk.wait(5);thread.join(5);io.close();osfile.close();pause.save(folder/'captures.json',captures);pause.save(folder/'external-events.json',list(events));pause.save(folder/'external-summary.json',{'actual_seconds':time.monotonic()-started,'polls':polls,'captures':len(captures),'event_cap':10000,'self_rusage':list(resource.getrusage(resource.RUSAGE_SELF)),'children_rusage':list(resource.getrusage(resource.RUSAGE_CHILDREN))})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--folder',required=True);run(p.parse_args().folder)
