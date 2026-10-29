"""Bounded public Binance isolation; no new execution/runtime/provider implementation."""
import argparse,asyncio,hashlib,importlib.util,json,os,resource,signal,subprocess,sys,time,urllib.request
from collections import Counter,deque
from pathlib import Path
from types import SimpleNamespace
import aiohttp
from mnq_local.binance_spot import Feed,PublicREST,SpotRuntime,WS
from mnq_local.binance_app import PipelineMetrics,cooperative_enqueue
from mnq_timestral.strategy import Risk,RiskState
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
ORDER=list('ABCDDCBA');SEGMENT_SECONDS=300;SOAK_CONNECTED_SECONDS=1800

def save(p,x):Path(p).write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def clusters(stamps):
 result=[]
 for n in stamps:
  if not result or n-result[-1][1]>1000000000:result.append([n,n])
  else:result[-1][1]=n
 return result

def connected_seconds(intervals):return sum(b-a for a,b in intervals)
def externalize_os_probe(app):app.host_sample=lambda:{'isolation_external_sampler':True,'at_ns':time.time_ns()}

class ReadOnlyFeedOwner:
 def __init__(self):
  self.spot={'last_book_id':None,'last_trade_id':None,'closed_bar':None};self.quote=None;self.connected=False;self.ready=False;self.trade_fresh=False;self.certificate={'passed':False};self.journal=SimpleNamespace(save=lambda *a:None);self.risk=Risk(10,20,10,3);self.exit_notices=Counter()
 def quote_fresh(self,for_exit=False):return SpotRuntime.quote_fresh(self,for_exit)
 def request_exit(self,reason):self.exit_notices[reason]+=1

class ClosedStrategy:
 def __init__(self):
  loader=importlib.util.spec_from_file_location('isolation_forward_reuse',ROOT/'reports/binance-spot/forward-signals/recorder.py');module=importlib.util.module_from_spec(loader);sys.modules[loader.name]=module;loader.loader.exec_module(module);self.baseline=module.baseline;self.context=[];self.evaluations=0;self.records=[]
  # Existing native4h warmup is context only, never a prospective evaluation.
  for line in (ROOT/'data/binance-spot/forward-signals/events.jsonl').open():
   row=json.loads(line)
   if row['kind']=='native4h_response':
    cutoff=row['params']['endTime']+1;self.context=module.closed(row['rows'],cutoff)
 def consider(self,k,minutes):
  if not k['x'] or (k['T']+1)%14400000:return None
  if len(minutes)!=240 or any(b['t']!=minutes[0]['t']+i*60000 or not b['x'] for i,b in enumerate(minutes)):return None
  end=(k['T']+1)*1000000;start=end-14400000000000
  if minutes[0]['t']*1000000!=start or not self.context or self.context[-1].end!=start:return None
  dec=self.baseline.dec;b=self.baseline.Bar(start,end,dec(minutes[0]['o']),max(dec(x['h']) for x in minutes),min(dec(x['l']) for x in minutes),dec(k['c']),sum(dec(x['v']) for x in minutes),'ACTUAL_CLOSED_240_NATIVE1M',minutes[0]['t'],k['T']);self.context=(self.context+[b])[-256:]
  buy,exit_signal,atr=self.baseline.decision(self.context);self.evaluations+=1;row={'origin_ns':end,'buy_condition':buy,'exit_condition':exit_signal,'atr14':str(atr),'actionable':False,'no_orders':True};self.records.append(row);return row

class Monitor:
 def __init__(self,arm):
  self.arm=arm;self.metrics=PipelineMetrics();self.counts=Counter();self.rejects=[];self.last=None;self.matches=deque(maxlen=512);self.connected=[];self.active_since=None;self.started_ns=time.time_ns();self.started_mono=time.monotonic_ns()
 def arrival(self,mono,size):
  if self.last is not None:self.metrics.record('arrival_gap_idle_included',(mono-self.last)/1e6)
  self.last=mono;self.counts['received']+=1;self.counts['bytes']+=size
 def process(self,text,wall,mono):
  delay=time.monotonic_ns()-mono;self.metrics.record('receipt_to_processing',delay/1e6)
  if delay>=250000000:self.counts['delay_ge250ms']+=1;self.rejects.append(mono);return None
  self.counts['processed']+=1
  if self.arm=='A' or self.arm=='W':return None
  with self.metrics.measure('json_parse'):item=json.loads(text)
  self.counts['json_decodes']+=1;d=item.get('data',{})
  if item.get('stream')=='btcusdt@trade':
   self.matches.append({'id':d['t'],'price':d['p'],'qty':d['q'],'source_ms':d['T'],'receipt_ns':wall,'receipt_mono_ns':mono})
   self.metrics.record('source_age_uncorrected_not_network',(wall-d['T']*1000000)/1e6)
  return item
 def connected_total(self):
  return connected_seconds(self.connected)+(0 if self.active_since is None else (time.monotonic_ns()-self.active_since)/1e9)
 def summary(self):
  now=time.monotonic_ns();u=resource.getrusage(resource.RUSAGE_SELF)
  return {'arm':self.arm,'pid':os.getpid(),'started_ns':self.started_ns,'ended_ns':time.time_ns(),'actual_wall_seconds':(now-self.started_mono)/1e9,'connected_intervals_seconds':self.connected,'connected_seconds':self.connected_total(),'counts':dict(self.counts),'metrics':self.metrics.snapshot(),'delay_clusters_mono_ns':clusters(self.rejects),'trade_identity_samples':list(self.matches),'rusage':{'user_cpu_seconds':u.ru_utime,'system_cpu_seconds':u.ru_stime,'peak_rss_bytes':u.ru_maxrss,'minor_faults':u.ru_minflt,'major_faults':u.ru_majflt,'input_blocks':u.ru_inblock,'output_blocks':u.ru_oublock},'notes':'A/W source-age/freshnessNA(noJSON). Other sourceageuncorrected/notnetwork. No account/order capability inA/B/C. GC enabled unchanged.'}

async def simple(arm,seconds,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);m=Monitor(arm);m.metrics.attach_gc();stop=asyncio.Event();loop=asyncio.get_running_loop();inbox=asyncio.Queue(512);samples=[];raw_anomalies=deque(maxlen=128);owner=ReadOnlyFeedOwner() if arm=='C' else None;feed=Feed(owner) if owner else None;strategy=ClosedStrategy() if arm=='C' else None;closed_minutes=[]
 for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
 async def probe():
  target=loop.time()+.02
  while not stop.is_set():
   await asyncio.sleep(max(0,target-loop.time()));lag=max(0,loop.time()-target)*1000;m.metrics.record('loop_lag',lag)
   if lag>=25:m.metrics.event('loop_stall',{'lag_ms':lag,'queue_depth':inbox.qsize()})
   target=loop.time()+.02
 async def consume():
  while not stop.is_set():
   try:text,wall,mono=await asyncio.wait_for(inbox.get(),.2)
   except asyncio.TimeoutError:continue
   item=m.process(text,wall,mono)
   if arm=='C' and item is not None:
    with m.metrics.measure('existing_feed'):accepted=feed.process(item,wall,mono)
    if accepted and item['stream']=='btcusdt@kline_1m' and item['data']['k']['x']:
     k=item['data']['k'];closed_minutes.append(k);closed_minutes[:]=closed_minutes[-240:]
     with m.metrics.measure('frozen_strategy_closedbar_hook'):observed=strategy.consider(k,closed_minutes)
     if (k['T']+1)%14400000==0 and observed is None:
      async def reconcile(k=dict(k)):
       try:
        rows=(await rest.get('/api/v3/klines',symbol='BTCUSDT',interval='1m',startTime=k['T']+1-14400000,endTime=k['T'],limit=240))['data']
        parts=[{'t':v[0],'T':v[6],'o':v[1],'h':v[2],'l':v[3],'c':v[4],'v':v[5],'x':True} for v in rows]
        with m.metrics.measure('frozen_strategy_actual_boundary_reconcile'):strategy.consider(k,parts)
       except Exception as exc:m.counts['strategy_reconcile_'+type(exc).__name__]+=1
      tasks.append(asyncio.create_task(reconcile()))
    with m.metrics.measure('original_risk_readonly'):owner.risk.allow(RiskState(data_fresh=feed.certified()))
 async def snapshots():
  while not stop.is_set():
   samples.append({'at_ns':time.time_ns(),'mono_ns':time.monotonic_ns(),'process_cpu_seconds':time.process_time(),'thread_cpu_seconds':time.thread_time(),'queue_depth':inbox.qsize(),'feed':feed.certificate() if feed else None,'counts':dict(m.counts)})
   await asyncio.sleep(1)
 async with aiohttp.ClientSession(trust_env=False,cookie_jar=aiohttp.DummyCookieJar()) as session:
  rest=PublicREST(session,lambda x:None)
  async def certify():
   while not stop.is_set():
    if feed and feed.current_stream_ok:
     try:await feed.compare_rest(rest)
     except Exception as exc:m.counts['rest_error_'+type(exc).__name__]+=1
    await asyncio.sleep(4)
  async def receive():
   delay=1
   while not stop.is_set():
    began=None
    try:
     async with session.ws_connect(WS,heartbeat=15,timeout=aiohttp.ClientWSTimeout(ws_receive=15,ws_close=5),autoping=True,max_msg_size=1000000) as ws:
      began=time.monotonic_ns();m.active_since=began;m.counts['connections']+=1
      if feed:feed.connected()
      async for msg in ws:
       wall=time.time_ns();mono=time.monotonic_ns()
       if stop.is_set():break
       if msg.type==aiohttp.WSMsgType.TEXT:
        m.arrival(mono,len(msg.data))
        try:await cooperative_enqueue(inbox,(msg.data,wall,mono))
        except asyncio.QueueFull:m.counts['queue_overflow']+=1;raise ConnectionError('bounded_queue')
       elif msg.type==aiohttp.WSMsgType.ERROR:raise ConnectionError('ws_error')
    except (aiohttp.ClientError,asyncio.TimeoutError,ConnectionError) as exc:
     if began is not None:m.connected.append(((began-m.started_mono)/1e9,(time.monotonic_ns()-m.started_mono)/1e9));m.active_since=None;began=None
     m.counts['disconnect_'+type(exc).__name__]+=1
     if feed:feed.disconnected(type(exc).__name__)
     await asyncio.sleep(delay);delay=min(15,delay*2)
    finally:
     if began is not None:m.connected.append(((began-m.started_mono)/1e9,(time.monotonic_ns()-m.started_mono)/1e9));m.active_since=None
  tasks=[asyncio.create_task(f()) for f in [probe,consume,snapshots,receive,certify]]
  async def budget():
   while not stop.is_set():
    if seconds and m.connected_total()>=seconds:stop.set()
    await asyncio.sleep(.2)
  tasks.append(asyncio.create_task(budget()))
  waiter=asyncio.create_task(stop.wait());done,_=await asyncio.wait(tasks+[waiter],return_when=asyncio.FIRST_COMPLETED)
  for t in done:
   if t is not waiter and not t.cancelled() and t.exception():m.counts['task_failure_'+type(t.exception()).__name__]+=1
  stop.set();waiter.cancel()
  for t in tasks:t.cancel()
  await asyncio.gather(*tasks,return_exceptions=True)
 m.metrics.detach_gc();result=m.summary();result['strategy_evaluations']=strategy.evaluations if strategy else 0;result['strategy_records']=strategy.records if strategy else [];result['active_strategy_workload']='NA_NO_ACTUAL_COMPLETE4H_CLOSE' if not strategy or not strategy.evaluations else 'ACTUAL_CLOSED4H';result['feed']=feed.certificate() if feed else None
 save(folder/'result.json',result);save(folder/'samples.json',samples);save(folder/'events.json',m.metrics.take_events())

async def full(folder):
 import mnq_local.binance_app as app
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);app.freeze(folder);externalize_os_probe(app)
 # Extra observation only, captured before existing decoder. Financial/core source unchanged.
 m=Monitor('D');original=app.decode_received;original_report=app.report
 class ConnectionFeed(Feed):
  def connected(self):
   super().connected();m.active_since=time.monotonic_ns();m.counts['connections']+=1
  def disconnected(self,reason):
   if m.active_since is not None:m.connected.append(((m.active_since-m.started_mono)/1e9,(time.monotonic_ns()-m.started_mono)/1e9));m.active_since=None
   m.counts['disconnect_'+reason]+=1;return super().disconnected(reason)
 app.Feed=ConnectionFeed
 def observed_report(*a):return {**original_report(*a),'isolation_connected_seconds':m.connected_total(),'isolation_receipts':dict(m.counts)}
 app.report=observed_report
 def decode(text,metrics):
  wall=time.time_ns();mono=time.monotonic_ns();m.arrival(mono,len(text));return original(text,metrics)
 app.decode_received=decode
 try:await app.run(SimpleNamespace(report=str(folder),journal=str(ROOT/'data/binance-spot/paper.sqlite'),port=8767))
 finally:
  if m.active_since is not None:m.connected.append(((m.active_since-m.started_mono)/1e9,(time.monotonic_ns()-m.started_mono)/1e9));m.active_since=None
  save(folder/'arm-extra.json',m.summary())

def sample_os(folder):
 folder=Path(folder);stop=False
 def done(*_):
  nonlocal stop;stop=True
 for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,done)
 started=time.monotonic();n=0
 with (folder/'os-samples.jsonl').open('a',buffering=1) as f:
  while not stop:
   a=time.monotonic_ns();cpu=time.process_time();child=resource.getrusage(resource.RUSAGE_CHILDREN);targets=json.loads((folder/'targets.json').read_text());pids=','.join(str(v) for v in targets['pids']);row={'at_ns':time.time_ns(),'mono_ns':a,'targets':targets,'load':os.getloadavg(),'commands':{},'errors':{}}
   cmds={'vm_stat':['vm_stat'],'swap':['sysctl','vm.swapusage'],'pressure':['sysctl','kern.memorystatus_vm_pressure_level'],'processes':['ps','-p',pids,'-o','pid=,rss=,%cpu=,time=,pagein='],'system_cpu':['top','-l','1','-n','0'],'disk':['iostat','-d','-c','1']}
   for k,cmd in cmds.items():
    try:row['commands'][k]=subprocess.check_output(cmd,text=True,timeout=3,stderr=subprocess.DEVNULL)[:12000]
    except (OSError,subprocess.SubprocessError) as exc:row['errors'][k]=type(exc).__name__
   u=resource.getrusage(resource.RUSAGE_CHILDREN);row['sampler_wall_ms']=(time.monotonic_ns()-a)/1e6;row['sampler_cpu_ms']=(time.process_time()-cpu)*1000;row['sampler_children_cpu_ms']=(u.ru_utime+u.ru_stime-child.ru_utime-child.ru_stime)*1000;f.write(json.dumps(row,sort_keys=True)+'\n');n+=1
   time.sleep(max(0,5-(time.monotonic_ns()-a)/1e9))
 save(folder/'sampler-summary.json',{'samples':n,'actual_seconds':time.monotonic()-started,'rusage':list(resource.getrusage(resource.RUSAGE_SELF))})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['A','B','C','W','D','sample']);p.add_argument('--seconds',type=int,default=0);p.add_argument('--folder',required=True);a=p.parse_args()
 if a.mode=='D':asyncio.run(full(a.folder))
 elif a.mode=='sample':sample_os(a.folder)
 else:asyncio.run(simple(a.mode,a.seconds,a.folder))
