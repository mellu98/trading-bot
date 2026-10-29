"""Telemetry-only additive correction: continuous interval iostat, no repeated top."""
from pathlib import Path
import argparse,json,os,resource,signal,subprocess,threading,time

class IntervalRows:
 def __init__(self):self.samples=0
 def add(self,line):
  try:values=[float(v) for v in line.split()]
  except ValueError:return None
  if len(values)<6 or (len(values)-3)%3:return None
  self.samples+=1
  return {'sample_index':self.samples,'interval_valid':self.samples>1,'disk_columns':values[:-3],'system_cpu_percent':dict(zip(['user','system','idle'],values[-3:])),'first_sample_note':'FirstnumericrowuptimeaverageEXCLUDED; subsequentrows5sinterval. PerdiskKB/t,tps,MB/s; do notsumphysical/virtualdisks.'}

def low_commands(pids):
 return {'vm_stat':['vm_stat'],'swap':['sysctl','vm.swapusage'],'pressure':['sysctl','kern.memorystatus_vm_pressure_level'],'processes':['ps','-p',','.join(str(p) for p in pids),'-o','pid=,rss=,%cpu=,time=,pagein=']}

def run(folder):
 folder=Path(folder);stop=threading.Event();started=time.monotonic();count=0
 for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
 diskfile=(folder/'interval-iostat.jsonl').open('a',buffering=1);iostat=subprocess.Popen(['iostat','-C','-d','-w','5'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1);classifier=IntervalRows()
 def collect():
  for line in iostat.stdout:
   wall=time.time_ns();mono=time.monotonic_ns();item=classifier.add(line)
   diskfile.write(json.dumps({'at_ns':wall,'mono_ns':mono,'raw':line.rstrip(),'parsed':item})+'\n')
 thread=threading.Thread(target=collect,daemon=True);thread.start()
 try:
  with (folder/'os-samples.jsonl').open('a',buffering=1) as f:
   while not stop.is_set():
    a=time.monotonic_ns();cpu=time.process_time();child=resource.getrusage(resource.RUSAGE_CHILDREN);targets=json.loads((folder/'targets.json').read_text());row={'at_ns':time.time_ns(),'mono_ns':a,'targets':targets,'load':os.getloadavg(),'commands':{},'errors':{}}
    for k,cmd in low_commands(targets['pids']+[os.getpid(),iostat.pid]).items():
     try:row['commands'][k]=subprocess.check_output(cmd,text=True,timeout=2,stderr=subprocess.DEVNULL)
     except (OSError,subprocess.SubprocessError) as exc:row['errors'][k]=type(exc).__name__
    u=resource.getrusage(resource.RUSAGE_CHILDREN);row['sampler_wall_ms']=(time.monotonic_ns()-a)/1e6;row['sampler_cpu_ms']=(time.process_time()-cpu)*1000;row['sampler_children_cpu_ms']=(u.ru_utime+u.ru_stime-child.ru_utime-child.ru_stime)*1000;row['ongoing_iostat_pid']=iostat.pid;f.write(json.dumps(row,sort_keys=True)+'\n');count+=1
    stop.wait(max(0,5-(time.monotonic_ns()-a)/1e9))
 finally:
  iostat.terminate();iostat.wait(5);thread.join(5);diskfile.close();(folder/'sampler-summary.json').write_text(json.dumps({'samples':count,'actual_seconds':time.monotonic()-started,'self_rusage':list(resource.getrusage(resource.RUSAGE_SELF)),'children_rusage':list(resource.getrusage(resource.RUSAGE_CHILDREN)),'iostat_rows':classifier.samples})+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--folder',required=True);run(p.parse_args().folder)
