"""Bounded postmeasurement analysis. Never starts a market client or changes financial sources."""
from pathlib import Path
import collections,datetime,hashlib,json,re,sqlite3,subprocess,time
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def load(p):return json.loads(p.read_text())
def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def jl(p):return [json.loads(x) for x in p.read_text().splitlines() if x]
def intersects(a,b,windows):return any(a<=d and b>=c for c,d in windows)
def spans(e):
 t=e.get('mono_ns',e.get('processing_start_ns',0));return e.get('mono_start_ns',e.get('received_mono_ns',t)),e.get('mono_end_ns',t)
def summarize(root):
 caps=load(root/'captures.json');windows=[(x['started_mono_ns'],x['ended_mono_ns']+200000000) for x in caps];out={'attempts':load(root/'complete.json')['attempts'],'capture_windows_mono_ns':windows,'arms':{},'captures':[]}
 for attempt in out['attempts']:
  d=root/attempt['segment'];a={'attempt':attempt};out['arms'][attempt['segment']]=a
  if not (d/'terminal-proof.json').exists():continue
  proof=load(d/'terminal-proof.json');a['proof']=proof;metrics=load(d/'terminal-metrics.json');a['stage_quantiles_raw_including_capture']=metrics;a['raw_counts']=metrics['counters'];events=load(d/'slow-proof.json');rej=[e for e in events if e['kind']=='queue_reject_context'];unc=[e for e in rej if not intersects(*spans(e),windows)];pre=[e for e in rej if windows and spans(e)[1]<windows[0][0]]
  a['uncensored_rejection_tail_only_ms']={q:sorted(e['queue_delay_ms'] for e in unc)[min(len(unc)-1,int((len(unc)-1)*f))] if unc else None for q,f in [('p50',.5),('p95',.95),('p99',.99),('max',1)]};a['uncensored_all_frame_quantiles']='NA_NOT_RETAINED; lifetime raw aggregation cannot be capture-censored retrospectively. Tail-only values are >=250ms rejected contexts, NOT all-frame distribution.'
  a['processing_rejections']={'reported_total':proof['feed']['stats']['processing_delay_rejections'],'retained_contexts':len(rej),'outside_capture_and_receipt_span':len(unc),'capture_overlap_contexts':len(rej)-len(unc),'before_first_capture_contexts':len(pre),'retention_note':'If reported total differs from contexts, missing contexts are not assigned to a censor category.'}
  w_events=load(root/'witness/events.json');os_events=jl(root/'os-samples.jsonl');groups=[]
  for e in rej:
   if not groups or e['mono_ns']-groups[-1][-1]['mono_ns']>1000000000:groups.append([])
   groups[-1].append(e)
  a['reject_clusters']=[{'start_mono_ns':min(e['received_mono_ns'] for e in g),'end_mono_ns':max(e['mono_ns'] for e in g),'count':len(g),'max_queue_ms':max(e['queue_delay_ms'] for e in g),'capture_overlap':intersects(min(e['received_mono_ns'] for e in g),max(e['mono_ns'] for e in g),windows),'witness_loop_stalls_overlapping':[e for e in w_events if e.get('kind')=='loop_stall' and intersects(e['mono_ns']-int(e['lag_ms']*1e6),e['mono_ns'],[(min(z['received_mono_ns'] for z in g),max(z['mono_ns'] for z in g))])],'nearest_OS_sample_mono_ns':min(os_events,key=lambda x:abs(x['mono_ns']-g[0]['mono_ns']))['mono_ns']} for g in groups]
  a['cpu_rusage']=load(d/'process-rusage.json');a['frames_per_connected_second']=metrics['counters'].get('ws_messages_received',0)/max(attempt['last_observed_connected_seconds'],1)
  a['slow_intervals_outside_capture']=[e for e in events if e['kind']=='stage_interval' and not intersects(*spans(e),windows)]
  a['source_age_not_network_latency']=True;a['protection_and_strategy_workload']='NA_FLAT_SPENT_NO_NEW_ECONOMIC_STRATEGY; original hooks retained, no exit exercised'
 w=load(root/'witness/result.json');we=load(root/'witness/events.json');wc=w.get('delay_clusters_mono_ns',[]);out['witness']={'result':w,'delay_clusters_with_capture_overlap':[{'start':a,'end':b,'capture_overlap':intersects(a,b,windows)} for a,b in wc],'loop_stalls_raw_ge250':sum(e.get('kind')=='loop_stall' and e.get('lag_ms',0)>=250 for e in we),'loop_stalls_uncensored_ge250':sum(e.get('kind')=='loop_stall' and e.get('lag_ms',0)>=250 and not intersects(e['mono_ns']-int(e['lag_ms']*1e6),e['mono_ns'],windows) for e in we)}
 for c in caps:
  py=ROOT/c['python_file'];native=ROOT/c['file'];text=native.read_text() if native.exists() else '';m=re.search(r'Date/Time:\s+(.+)',text);onset=None
  if m:
   onset=int(datetime.datetime.strptime(m[1].strip(),'%Y-%m-%d %H:%M:%S.%f %z').timestamp()*1e9)
  end=c.get('first_heartbeat_advance_mono_ns');native_mono=None if onset is None else c['started_mono_ns']+onset-c['started_wall_ns'];mtime=c.get('python_dump_mtime_ns');py_mono=None if mtime is None else c['python_signal_request_mono_ns']+mtime-c['python_signal_request_wall_ns'];out['captures'].append({'record':c,'native_date_time':None if not m else m[1].strip(),'native_onset_mono_estimate_ns':native_mono,'native_onset_after_owner_resume_ms':None if native_mono is None or end is None else (native_mono-end)/1e6,'native_classification':'MISSING' if native_mono is None else 'POSTPAUSE' if end and native_mono>end else 'PARTIAL_START_OVERLAP_AGGREGATE_HAS_NO_PER_FRAME_TIMESTAMPS' ,'python_mtime_before_owner_resume_ms':None if py_mono is None or end is None else (end-py_mono)/1e6,'python_current_thread':py.read_text().split('Current thread')[-1] if py.exists() else None,'interpretation':'Python all-thread snapshot is a location only, not unique OS/GIL/IO mechanism. Native aggregate postpause idle frames do not explain initial pause.'})
 osrows=jl(root/'os-samples.jsonl');io=jl(root/'interval-iostat.jsonl');valid=[x for x in io if x.get('parsed') and x['parsed']['interval_valid']];out['host_interval']={'samples':len(osrows),'first':osrows[0],'last':osrows[-1],'load_minmax':[[min(x['load'][i] for x in osrows),max(x['load'][i] for x in osrows)] for i in range(3)],'sampler_self_cpu_ms':sum(x['sampler_cpu_ms'] for x in osrows),'sampler_child_cpu_ms':sum(x['sampler_children_cpu_ms'] for x in osrows),'interval_iostat_rows':len(valid),'system_user_percent_minmax':[min(x['parsed']['system_cpu_percent']['user'] for x in valid),max(x['parsed']['system_cpu_percent']['user'] for x in valid)],'system_system_percent_minmax':[min(x['parsed']['system_cpu_percent']['system'] for x in valid),max(x['parsed']['system_cpu_percent']['system'] for x in valid)],'first_disk_MBps_minmax':[min(x['parsed']['disk_columns'][2] for x in valid),max(x['parsed']['disk_columns'][2] for x in valid)],'limits':'5s host windows cannot prove exact pause mechanism. ps stat/wchan and pageins not proof of suspension/AppNap/VM causality; first iostat uptime row excluded.'}
 out['host_interval']['vm_counter_deltas']={name:int(re.search(r'^'+name+r':\s+(\d+)',osrows[-1]['commands']['vm_stat'],re.M).group(1))-int(re.search(r'^'+name+r':\s+(\d+)',osrows[0]['commands']['vm_stat'],re.M).group(1)) for name in ['Pageins','Pageouts','Swapins','Swapouts']}
 out['external']=load(root/'external-summary.json');return out
if __name__=='__main__':
 result={'at_ns':time.time_ns(),'cause':'NOT_UNIQUELY_IDENTIFIED','readiness':'FAIL_ORIGINAL250MS_2S_GUARDS; GLOBAL_BLOCK_REMAINS','original_ABBA':summarize(B/'main/live'),'separate_single_AB_opportunity':summarize(B/'opportunity/live'),'calibration':'Original live/ is apparatus calibration, never pooled. Initial17sAdeath/profiler timeout retained.','production_fix':'NONE_THIS_MISSION; no threshold/queue/journal changes justified by single observational contrast.','only_configured_host':'Local(local); no authorized comparison host verified.'}
 before=load(B/'protected-before.json');bad=[p for p,h in before.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h];result['protected']={'checked':len(before),'changed':bad};assert not bad
 result['journal']={'integrity':None,'state':None}
 con=sqlite3.connect('file:'+str(ROOT/'data/binance-spot/paper.sqlite')+'?mode=ro',uri=True);result['journal']['integrity']=con.execute('PRAGMA integrity_check').fetchone()[0];row=con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall();result['journal']['tables']=[x[0] for x in row];con.close()
 save(B/'results.json',result)
