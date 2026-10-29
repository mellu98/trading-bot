"""Additive diagnosis only. Existing Runtime/Risk/journal sources are immutable."""
import argparse,asyncio,contextlib,faulthandler,hashlib,importlib.util,json,mmap,os,resource,signal,struct,subprocess,sys,threading,time
from pathlib import Path
from collections import deque
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
STAGES=['idle','raw_write','rest_evidence_write','host_os_sample','observation_publish','sqlite_checkpoint','dashboard_snapshot','filesystem_export']

def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def overlap(a,b,c,d):return max(0,min(b,d)-max(a,c))
class Heartbeat:
 def __init__(self,path,writer=False):
  self.file=open(path,'w+b' if writer else 'rb');self.writer=writer
  if writer:self.file.truncate(4096)
  self.mm=mmap.mmap(self.file.fileno(),4096,access=mmap.ACCESS_WRITE if writer else mmap.ACCESS_READ);self.seq={}
 def write(self,slot,mono,value):
  n=self.seq.get(slot,0)+2;self.seq[slot]=n;struct.pack_into('<Q',self.mm,slot,n-1);struct.pack_into('<QQ',self.mm,slot+8,mono,value);struct.pack_into('<Q',self.mm,slot+24,n);struct.pack_into('<Q',self.mm,slot,n)
 def read(self,slot):
  a,t,v,b=struct.unpack_from('<QQQQ',self.mm,slot)
  return (t,v) if a==b and a>0 and not a%2 else None
 def close(self):self.mm.close();self.file.close()

class CaptureBudget:
 def __init__(self):self.count=0;self.segments=set();self.last=-1000000
 def allowed(self,segment,age_ms,now):return age_ms>100 and self.count<4 and segment not in self.segments and now-self.last>=60
 def used(self,segment,now):self.count+=1;self.segments.add(segment);self.last=now

class NullDashboard:
 def __init__(self,address,*_):self.server_port=address[1];self.stop=threading.Event()
 def serve_forever(self):self.stop.wait()
 def shutdown(self):self.stop.set()
 def server_close(self):pass

def disable_noncritical(app):
 # Raw/REST proof tasks, worker, critical saves, Feed/protection/Risk remain unchanged.
 app.enqueue_observation=lambda *_:None;app.Dashboard=NullDashboard


def load_lab():
 s=importlib.util.spec_from_file_location('frozen_isolation_reuse',ROOT/'reports/binance-spot/stability-isolation/runner-fixed.py');lab=importlib.util.module_from_spec(s);sys.modules[s.name]=lab;s.loader.exec_module(lab);return lab

async def runtime(mode,folder):
 import mnq_local.binance_app as app
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);hb=Heartbeat(folder/'heartbeat.mmap',True);fallback=(folder/'python-stacks.txt').open('a');faulthandler.register(signal.SIGUSR2,file=fallback,all_threads=True);hb.write(192,time.monotonic_ns(),os.getpid());lab=load_lab();G={'worker':None,'feed':None,'monitor':None};metrics=[];proof=deque(maxlen=4096);tls=threading.local()
 base=app.PipelineMetrics
 class ObservedMetrics(base):
  def __init__(self,*a,**k):super().__init__(*a,**k);metrics.append(self)
  def record(self,name,ms):
   if name in ('event_loop_lag','loop_lag'):
    now=time.monotonic_ns();hb.write(0,now,os.getpid())
    mon=G['monitor']
    if mon:hb.write(96,now,int(mon.connected_total()*1e9))
    feed=G['feed']
    if feed:
     r=feed.r;s=r.spot;flags=int(s['position'] is None)+2*int(s['budget_spent'])+4*int(s['buy_count']==s['sell_count']==1);hb.write(128,now,flags+16*feed.stats['processing_delay_rejections']);hb.write(160,now,int(r.quote_fresh(for_exit=True))+2*int(feed.trade_is_fresh()))
   return super().record(name,ms)
  def event(self,name,value):
   if name=='queue_reject_context' or value.get('wall_ms',0)>=100:proof.append({'kind':name,'at_ns':time.time_ns(),'mono_ns':time.monotonic_ns(),**value})
   return super().event(name,value)
  @contextlib.contextmanager
  def measure(self,name):
   w=G['worker'];isworker=w is not None and threading.get_ident()==w.thread.ident
   if isworker:
    stack=getattr(tls,'stack',[]);code=STAGES.index(name) if name in STAGES else 255;stack.append((time.monotonic_ns(),code));tls.stack=stack;hb.write(32,*stack[-1])
   try:
    with super().measure(name):yield
   finally:
    if isworker:
     stack.pop();hb.write(32,*(stack[-1] if stack else (time.monotonic_ns(),0)))
 class TracedWorker(app.ObservationWorker):
  def __init__(self,*a,**k):super().__init__(*a,**k);G['worker']=self
  def submit(self,*a,**k):
   try:return super().submit(*a,**k)
   finally:hb.write(64,time.monotonic_ns(),self.jobs.qsize())
 original_monitor=lab.Monitor
 class TracedMonitor(original_monitor):
  def __init__(self,*a,**k):super().__init__(*a,**k);G['monitor']=self
 class TracedFeed(lab.Feed):
  def __init__(self,r):super().__init__(r);G['feed']=self
 app.PipelineMetrics=ObservedMetrics;lab.PipelineMetrics=ObservedMetrics;app.ObservationWorker=TracedWorker;lab.Monitor=TracedMonitor;lab.Feed=TracedFeed
 if mode=='B':disable_noncritical(app)
 try:
  if mode=='W':await lab.simple('W',0,folder)
  else:await lab.full(folder)
 finally:
  if G['feed']:
   f=G['feed'];r=f.r;save(folder/'terminal-proof.json',{'at_ns':time.time_ns(),'mode':mode,'flat':r.spot['position'] is None,'spent':r.spot['budget_spent'],'buy_count':r.spot['buy_count'],'sell_count':r.spot['sell_count'],'cash':r.spot['cash'],'feed':f.certificate(),'critical_source_unchanged':True})
  for obj in metrics:
   if 'queue_wait' in obj.counts:save(folder/'terminal-metrics.json',obj.snapshot());save(folder/'terminal-events.json',obj.take_events())
  save(folder/'process-rusage.json',{'rusage':list(resource.getrusage(resource.RUSAGE_SELF)),'voluntary_context_switches':resource.getrusage(resource.RUSAGE_SELF).ru_nvcsw,'involuntary_context_switches':resource.getrusage(resource.RUSAGE_SELF).ru_nivcsw});save(folder/'slow-proof.json',list(proof));save(folder/'stage-codes.json',STAGES);faulthandler.unregister(signal.SIGUSR2);fallback.close();hb.close()

def calibration(folder):
 folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True);env={'PATH':os.environ['PATH'],'HOME':os.environ['HOME']};fake=subprocess.Popen([sys.executable,'-c','import time; time.sleep(8)'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);a=time.monotonic_ns();wall=time.time_ns();child=resource.getrusage(resource.RUSAGE_CHILDREN)
 try:
  p=subprocess.run(['/usr/bin/sample',str(fake.pid),'1','10','-file',str(folder/'fake-sample.txt')],capture_output=True,text=True,timeout=15);u=resource.getrusage(resource.RUSAGE_CHILDREN);receipt={'fake_pid':fake.pid,'owned_process':True,'started_ns':wall,'mono_start_ns':a,'mono_end_ns':time.monotonic_ns(),'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'sample_cpu_seconds':u.ru_utime+u.ru_stime-child.ru_utime-child.ru_stime,'sample_file':str((folder/'fake-sample.txt').relative_to(ROOT)),'manual':'Local macOS sample(1): suspends own process at samplinginterval; measurement windows must be censored.'};save(folder/'calibration.json',receipt);print(json.dumps({k:receipt[k] for k in ['fake_pid','returncode','sample_cpu_seconds','mono_start_ns','mono_end_ns']}))
 finally:fake.terminate();fake.wait()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['A','B','W','calibrate']);p.add_argument('--folder',required=True);a=p.parse_args()
 if a.mode=='calibrate':calibration(a.folder)
 else:asyncio.run(runtime(a.mode,a.folder))
