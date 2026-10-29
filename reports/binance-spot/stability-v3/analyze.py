"""Bounded post-soak evidence summary; no feed/Risk/model changes."""
from pathlib import Path
import hashlib,json,re
from datetime import datetime,timezone
P=Path(__file__).resolve().parent;ROOT=P.parents[2]
def read(n):return json.loads((P/n).read_text())
def lines(n):return [json.loads(x) for x in (P/n).open()]
def save(n,v):(P/n).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
start=read('soak-start.json');summary=read('soak-summary.json');restart=read('controlled-restart.json');samples=lines('soak-samples.jsonl');end=start['at_ns']+int(summary['actual_seconds']*1e9)
host=[x for x in lines('host-samples.jsonl') if start['at_ns']<=x['at_ns']<=end]
events=[x for x in lines('correlated-events.jsonl') if start['at_ns']<=x['at_ns']<=end]
reject=[e for e in events if e['kind']=='queue_reject_context'];spans=[e for e in events if e['kind']=='stage_interval'];gc=[e for e in spans if e['stage'].startswith('gc_')]
stages={phase:read(path) for phase,path in [('before_restart','pre-restart-metrics.json'),('after_restart','post-soak-metrics.json')]};save('stage-quantiles.json',stages)
a=reject[0]['received_mono_ns'] if reject else 0;b=reject[-1]['processing_start_ns'] if reject else 0
intersection=[s for s in spans if s['mono_start_ns']<=b and s['mono_end_ns']>=a]
def vm(x):return {k:int(v) for k,v in re.findall(r'^([^:\n]+):\s+(\d+)\.',x['vm_stat'],re.M)}
def swap(x):return float(re.search(r'used = ([\d.]+)M',x['swap'])[1])
vmfirst,vmlast=vm(host[0]),vm(host[-1]);swapvals=[swap(x) for x in host];rss=[int(x['resident']) for x in host];cpus={}
for name,selected in [('before_restart',[x for x in host if x['at_ns']<restart['at_ns']]),('after_restart',[x for x in host if x['at_ns']>=restart['at_ns']])]:
 cpus[name]={'samples':len(selected),'process_cpu_start_seconds':selected[0]['process_cpu_seconds'],'process_cpu_end_seconds':selected[-1]['process_cpu_seconds'],'sampled_wall_seconds':(selected[-1]['mono_start_ns']-selected[0]['mono_start_ns'])/1e9}
 cpus[name]['process_cpu_delta_seconds']=cpus[name]['process_cpu_end_seconds']-cpus[name]['process_cpu_start_seconds']
valid=[s['feed']['passed'] for s in samples];runs=[];cur=0
for ok in valid:
 if ok:cur+=1
 else:runs.append(cur);cur=0
runs.append(cur)
coverage={'valid_samples':sum(valid),'total_samples':len(valid),'sample_valid_percent':100*sum(valid)/len(valid),'longest_valid_sample_run':max(runs),'not_continuous_duration_claim':True,'failure_flags':{k:sum(not s['feed'].get(k,False) for s in samples) for k in ['book_receipt_fresh','trade_fresh']},'processing_delay_rejections_by_process':[read(n)['report']['feed_metrics']['stats'].get('processing_delay_rejections',0) for n in ['pre-restart-state.json','post-soak-state.json']],'trade_gaps_by_process':[read(n)['report']['feed_metrics']['stats'].get('trade_gaps',0) for n in ['pre-restart-state.json','post-soak-state.json']]}
verification={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in read('protected-before.json').items()};save('protected-after.json',verification)
proof={'scope':'Actual quiet two-process620s observation; no tests/models/backtests/strategy jobs during window. OS other-app load not controlled. Flat protection/strategy active-work timing N/A; no new orders.','verdict':'BLOCKED_ACTIONABLE_READINESS','soak':summary,'start_utc_from_integer':datetime.fromtimestamp(start['at_ns']/1e9,timezone.utc).isoformat(),'coverage':coverage,'correlation':{'reject_count':len(reject),'first_reject':reject[0] if reject else None,'last_reject':reject[-1] if reject else None,'first_reject_after_start_seconds':(reject[0]['at_ns']-start['at_ns'])/1e9 if reject else None,'intersecting_stage_intervals':intersection,'gc_intersects_reject_cluster':any(g['mono_start_ns']<=b and g['mono_end_ns']>=a for g in gc),'critical_save_intersects_reject_cluster':any(s['stage'].startswith('critical_') for s in intersection),'event_overwrite_counters':{k:v['counters'].get('correlation_events_overwritten',0) for k,v in stages.items()},'causality':'Measured local wall delays with low executing CPU; no overlapping GC/critical save at35-reject cluster. Worker filesystem wait and owner wait overlap, but scheduling vs pagefault vs storage/GIL causal contribution is not uniquely identified. Provider latency and original22-reject cause NOT established.'},'host':{'samples':len(host),'first':host[0],'last':host[-1],'rss_kib_min':min(rss),'rss_kib_max':max(rss),'swap_used_mib_min':min(swapvals),'swap_used_mib_max':max(swapvals),'system_vm_counter_deltas':{k:vmlast[k]-vmfirst[k] for k in ['Pageins','Pageouts','Swapins','Swapouts']},'vm_page_bytes':16384,'counter_scope':'system-wide cumulative counters, NOT bot-specific; temporal5s sampling cannot resolve individual faults','process_cpu_by_phase':cpus},'financial_protected_paths':len(verification),'financial_protected_all_unchanged':all(verification.values()),'stage_quantiles':'stage-quantiles.json: both process-lifetime stages; rolling last20000 samples, lifetime count/max. Unitsms. thread/processCPU vswall explicit; workerCPU not wall. Some boot/teardown outside controllerwindow included.','source_age':'Sourceeventage uses serveroffset/uncertainty, not networklatency; book source timestamp unavailable. WSreceivewait includes idle, not transport delay.','recovery':'plannedflat45907→46903, originalsamejournal1BUY1SELLspent/cash999.76609237980375. No openposition testedagain; originalactualSIGKILLproof preserved.'}
save('analysis.json',proof)
print('analysis',proof['verdict'],'protected',proof['financial_protected_all_unchanged'],len(verification),'coverage',coverage)
print('host',len(host),'rss',min(rss),max(rss),'swap',min(swapvals),max(swapvals),'VMdelta',proof['host']['system_vm_counter_deltas']);print('CPU',cpus)
