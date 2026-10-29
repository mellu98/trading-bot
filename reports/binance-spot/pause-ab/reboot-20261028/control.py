"""Finite B/W reboot control. No production edits, observer restore or profiler."""
from pathlib import Path
import hashlib,importlib.util,json,os,socket,sqlite3,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent;BASE=OUT.parent

def load(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def assess(x):
 complete=x['duration']>=300 and x['w_duration']>=300 and x['data_complete']
 processing='INCOMPLETE' if not complete else 'PASS' if not any([x['rejections'],x['w_rejections'],x['overflow'],x['unexpected_disconnects'],x['max_queue']>250,x['w_max_queue']>250]) else 'FAIL'
 freshness='INCOMPLETE' if not x['fresh_initialized'] else 'FAIL' if x['fresh_failures'] else 'PASS'
 feed='BLOCKED' if x['feed_gap_block'] else freshness
 return {'measurement':'PASS' if complete else 'INCOMPLETE','processing':processing,'freshness':freshness,'feed':feed,'overall':'PASS' if processing==freshness=='PASS' and feed!='BLOCKED' else 'FAIL','repeat_local_eligible':processing==freshness=='PASS'}
def should_repeat(result):return result['repeat_local_eligible']
def journal():
 con=sqlite3.connect('file:'+str(ROOT/'data/binance-spot/paper.sqlite')+'?mode=ro',uri=True)
 try:integrity=con.execute('PRAGMA quick_check').fetchone()[0];spot=json.loads(con.execute('SELECT body FROM snapshot WHERE id=1').fetchone()[0])['binance_spot']
 finally:con.close()
 state={k:spot.get(k) for k in ['position','budget_spent','buy_count','sell_count','cash']}
 assert integrity=='ok' and spot['position'] is None and spot['budget_spent'] and spot['buy_count']==spot['sell_count']==1,'Unsafe or incomplete spent journal'
 return {'quick_check':integrity,'state':state}
def listener():
 s=socket.socket();s.settimeout(.2)
 try:return s.connect_ex(('127.0.0.1',8767))==0
 finally:s.close()
def protected():
 before=load(OUT/'protected-before.json');checks={p:(ROOT/p).is_file() and hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in before.items()};assert len(checks)==179 and all(checks.values()),[p for p,v in checks.items() if not v]
 return checks

def get_modules():
 sys.path.insert(0,str(BASE));import pause
 s=importlib.util.spec_from_file_location('reboot_targets',BASE/'targets-v2.py');t=importlib.util.module_from_spec(s);s.loader.exec_module(t);return pause,t

def run_one(index):
 pause,tio=get_modules();folder=OUT/f'run-{index}';assert not folder.exists(),'Never overwrite an attempt';folder.mkdir()
 before=journal();assert not listener(),'Existing observer/listener must remain untouched'
 env=dict(os.environ);env.update(PYTHONPATH=str(ROOT/'src'),PYTHONDONTWRITEBYTECODE='1');children=[]
 def spawn(mode,path):
  path.mkdir(parents=True,exist_ok=True);log=(path/'process.log').open('a');cmd=[sys.executable,str(BASE/'runtime-v2.py'),mode,'--folder',str(path)] if mode!='external' else [sys.executable,str(BASE/'external-v2.py'),'--folder',str(path)]
  child=subprocess.Popen(cmd,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close();children.append(child);return child
 def stop(child):
  if child and child.poll() is None:
   child.terminate()
   try:child.wait(30)
   except subprocess.TimeoutExpired:child.kill();child.wait();forced.append(child.pid)
 forced=[];b=w=external=None;readers={};rows=[];begin=time.monotonic();start_ns=time.time_ns();window_start=None;window_end=None;baseline=None;reason='consumer_exit';raw_covered=False
 try:
  w=spawn('W',folder/'witness');target={'phase':f'B-{index}','pids':[w.pid],'heartbeats':{'witness':{'pid':w.pid,'path':str(folder/'witness/heartbeat.mmap')}},'sampling_enabled':False};tio.atomic_targets(folder/'targets.json',target)
  external=spawn('external',folder);b=spawn('B',folder/'B');target['pids']=[b.pid,w.pid,external.pid];target['heartbeats']['runtime']={'pid':b.pid,'path':str(folder/'B/heartbeat.mmap')};tio.atomic_targets(folder/'targets.json',target)
  save(folder/'start.json',{'at_ns':start_ns,'controller_pid':os.getpid(),'B_pid':b.pid,'W_pid':w.pid,'external_pid':external.pid,'profiler_enabled':False,'restore_services':False})
  while b.poll() is None and w.poll() is None:
   if external.poll() is not None:reason='external_probe_exit';break
   observed={}
   for role in ['runtime','witness']:
    path=target['heartbeats'][role]['path']
    try:
     if role not in readers:readers[role]=pause.Heartbeat(path)
     h=readers[role];vals={slot:h.read(slot) for slot in [0,64,96,128,160]};observed[role]=vals
    except (OSError,ValueError):continue
   now=time.monotonic_ns();row={'at_ns':time.time_ns(),'mono_ns':now,'heartbeats':observed};rows.append(row)
   if 'runtime' in observed and observed['runtime'][128]:assert observed['runtime'][128][1]%16==7,'Flat spent budget invariant failed'
   if baseline is None and all(observed.get(k,{}).get(96) and observed[k][96][1]>0 for k in ['runtime','witness']):
    baseline={k:observed[k][96][1] for k in ['runtime','witness']};window_start=now;save(folder/'window-start.json',{'mono_ns':now,'at_ns':row['at_ns'],'baseline_connected_ns':baseline})
   if baseline:
    duration=min((observed.get(k,{}).get(96) or (0,baseline[k]))[1]-baseline[k] for k in baseline)/1e9
    if duration>=300:
     reason='connected_target_reached';window_end=now;save(folder/'window-end.json',{'mono_ns':now,'at_ns':row['at_ns'],'conservative_connected_seconds':duration});break
   if time.monotonic()-begin>450:reason='wall_cap';break
   if not baseline and time.monotonic()-begin>45:reason='startup_timeout';break
   time.sleep(.25)
  # FIFO receive/consumer/raw writes form a prefix. Wait only for raw proof beyond
  # the fixed window end; any missing shutdown suffix is then OUTSIDE the window.
  grace=time.monotonic()
  while window_end and b.poll() is None and time.monotonic()-grace<5:
   try:
    path=folder/'B/public-ws-events.jsonl'
    with path.open('rb') as f:
     f.seek(max(0,path.stat().st_size-16384));lines=f.read().splitlines()
    last=json.loads(lines[-1]);raw_covered=last['received_mono_ns']>=window_end
    if raw_covered:break
   except (OSError,ValueError,IndexError):pass
   time.sleep(.1)
 finally:
  if b:stop(b)
  if w:stop(w)
  if external:stop(external)
  for reader in readers.values():reader.close()
  save(folder/'controller-samples.json',rows);save(folder/'complete.json',{'started_ns':start_ns,'ended_ns':time.time_ns(),'actual_wall_seconds':time.monotonic()-begin,'stop_reason':reason,'window_start_mono_ns':window_start,'window_end_mono_ns':window_end,'raw_proof_covers_window_end':raw_covered,'forced_pids':forced,'children_returncodes':{str(p.pid):p.returncode for p in children},'no_service_restored':True,'journal_before':before,'journal_after':journal(),'port8767_listener_after':listener()})
 return analyze_one(folder)

def analyze_one(folder):
 complete=load(folder/'complete.json');out={'complete':complete,'status':{'overall':'INCOMPLETE'},'mode':'B_ONLY_NO_PROFILER'}
 required=['B/terminal-metrics.json','B/terminal-proof.json','B/arm-extra.json','witness/result.json','external-summary.json','captures.json']
 missing=[x for x in required if not (folder/x).exists()]
 if missing:out['missing_artifacts']=missing;save(folder/'result.json',out);return out
 metrics=load(folder/'B/terminal-metrics.json');proof=load(folder/'B/terminal-proof.json');extra=load(folder/'B/arm-extra.json');w=load(folder/'witness/result.json');external=load(folder/'external-summary.json');captures=load(folder/'captures.json')
 raw=[];raw_error=None
 try:
  for line in (folder/'B/public-ws-events.jsonl').read_text().splitlines():raw.append(json.loads(line))
 except Exception as exc:raw_error=type(exc).__name__
 rows=load(folder/'controller-samples.json');valid=[r for r in rows if r['heartbeats'].get('runtime',{}).get('96') and r['heartbeats'].get('witness',{}).get('96')]
 start=load(folder/'window-start.json') if (folder/'window-start.json').exists() else None;end=load(folder/'window-end.json') if (folder/'window-end.json').exists() else None
 seen=[False,False];fresh_startup=0;fresh_bad=[0,0];fresh_valid=0
 for row in rows:
  if not start or not end or not start['mono_ns']<=row['mono_ns']<=end['mono_ns']:continue
  value=row['heartbeats'].get('runtime',{}).get('160')
  if not value:continue
  bits=value[1]
  for i in [0,1]:
   if bits&(1<<i):seen[i]=True
   elif seen[i]:fresh_bad[i]+=1
  if all(seen):fresh_valid+=1
  else:fresh_startup+=1
 received=metrics['counters'].get('ws_messages_received',0);counter=metrics['counters'];wc=w['counts'];raw_suffix=received-len(raw);window_rows=[r for r in raw if start and end and start['mono_ns']<=r['received_mono_ns']<=end['mono_ns']]
 osrows=[json.loads(x) for x in (folder/'os-samples.jsonl').read_text().splitlines()];io=[json.loads(x) for x in (folder/'interval-iostat.jsonl').read_text().splitlines()];validio=[x for x in io if x.get('parsed') and x['parsed']['interval_valid']]
 data_complete=bool(start and end and complete['raw_proof_covers_window_end'] and not raw_error and raw_suffix>=0 and wc.get('received',0)==wc.get('processed',0) and not complete['forced_pids'] and len(captures)==0 and all(v==0 for v in complete['children_returncodes'].values()) and len(osrows)>=50 and len(validio)>=50 and not any(x['errors'] for x in osrows) and not counter.get('correlation_events_overwritten',0) and not w['metrics']['counters'].get('correlation_events_overwritten',0))
 gaps=proof['feed']['stats'];q=metrics['stages'].get('queue_wait',{});wq=w['metrics']['stages'].get('receipt_to_processing',{})
 x={'duration':end['conservative_connected_seconds'] if end else 0,'w_duration':w['connected_seconds'],'rejections':gaps.get('processing_delay_rejections',0),'w_rejections':wc.get('delay_ge250ms',0),'max_queue':q.get('max_ms',0),'w_max_queue':wq.get('max_ms',0),'overflow':counter.get('io_queue_overflow',0)+counter.get('ws_queue_overflow',0)+wc.get('queue_overflow',0),'unexpected_disconnects':sum(v for k,v in extra['counts'].items() if k.startswith('disconnect_'))+sum(v for k,v in wc.items() if k.startswith('disconnect_')),'data_complete':data_complete,'fresh_failures':sum(fresh_bad),'fresh_initialized':all(seen) and fresh_valid>0,'feed_gap_block':bool(gaps.get('unrepairable_gap',0) or gaps.get('bar_gaps',0) or proof['feed'].get('rest_comparison',{}).get('missing_trade_ids_remaining',0))}
 rusage=load(folder/'B/process-rusage.json')['rusage'];out.update(inputs=x,status=assess(x),metrics=metrics,feed=proof['feed'],witness=w,external=external,frame_accounting={'received':received,'raw_rows':len(raw),'shutdown_suffix_missing':raw_suffix,'raw_rows_in_window':len(window_rows),'raw_last_receipt_mono_ns':raw[-1]['received_mono_ns'] if raw else None,'raw_covers_window_end':complete['raw_proof_covers_window_end'],'parse_error':raw_error,'reason':'FIFO+no receive overflow means raw prefix covers the finite window; any shutdown suffix is outside it.'},freshness={'book_stale_samples_after_initialization':fresh_bad[0],'trade_stale_samples_after_initialization':fresh_bad[1],'startup_unknown_samples':fresh_startup,'initialized_samples':fresh_valid,'sampling_period_seconds':.25,'book_source_timestamp':'NOT_PROVIDED; receipt freshness only'},cpu={'lifetime_seconds':rusage[0]+rusage[1],'percent_one_core_per_connected_seconds':100*(rusage[0]+rusage[1])/max(x['duration'],1),'peak_rss_mib':rusage[2]/1048576},measurement={'os_samples':len(osrows),'interval_iostat_samples':len(validio),'captures':len(captures),'all_times_uncensored':True,'quantiles':'Bounded last20000; counts/max lifetime; startup/cleanup metrics retained explicitly.'})
 save(folder/'result.json',out);return out

def main():
 checks=protected();protocol=load(OUT/'protocol.json')
 for path,h in protocol['source_sha256'].items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==h,path
 runs=[run_one(1)];save(OUT/'progress.json',{'run1_status':runs[0]['status']})
 if runs[0]['status'].get('repeat_local_eligible'):runs.append(run_one(2))
 after=protected();save(OUT/'results.json',{'at_ns':time.time_ns(),'runs':runs,'protected_count':len(after),'protected_all_unchanged':all(after.values()),'observer_restored':False,'model_jobs':0,'trades_created':0,'repeatability':'PASS' if len(runs)==2 and all(r['status'].get('repeat_local_eligible') for r in runs) else 'NOT_VERIFIED' if len(runs)==1 else 'FAIL'})
 print(json.dumps({'runs':[r['status'] for r in runs],'protected_unchanged':all(after.values())}),flush=True)
if __name__=='__main__':main()
