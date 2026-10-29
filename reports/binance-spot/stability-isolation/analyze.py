"""Post-measurement only: bounded summaries and independent-witness correlation."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,re,statistics,time,urllib.request
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent

def read(p):return json.loads(Path(p).read_text())
def jl(p):return [json.loads(x) for x in Path(p).open()]
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def dist(xs):
 xs=sorted(xs);n=len(xs)
 return None if not n else {'n':n,**{k:xs[int((n-1)*q)] for k,q in [('p50',.5),('p95',.95),('p99',.99),('max',1)]}}
def stamp(ns):return datetime.fromtimestamp(ns/1e9,timezone.utc).isoformat()
def psrow(sample,pid):
 for line in sample['commands'].get('processes','').splitlines():
  v=line.split()
  if len(v)>=5 and v[0]==str(pid):return {'rss_kib':int(v[1]),'decayed_cpu_percent_not_interval':float(v[2]),'cumulative_cpu_text':v[3],'pageins':int(v[4])}
 return None

def vm(row):return {k:int(v) for k,v in re.findall(r'^([^:\n]+):\s+(\d+)\.',row['commands'].get('vm_stat',''),re.M)}
def swap(row):
 m=re.search(r'used = ([\d.]+)M',row['commands'].get('swap',''));return float(m[1]) if m else None

def segment(folder,arm):
 extra=read(folder/('arm-extra.json' if arm=='D' else 'result.json'));metrics=read(folder/'pipeline-metrics.json') if arm=='D' else extra['metrics'];samples=read(folder/('controller-samples.json' if arm=='D' else 'samples.json'));feeds=[s['report']['feed_metrics'] if arm=='D' else s['feed'] for s in samples if ('report' in s if arm=='D' else s.get('feed') is not None)]
 keys={'queue':'queue_wait' if arm=='D' else 'receipt_to_processing','loop':'event_loop_lag' if arm=='D' else 'loop_lag'}
 return {'name':folder.name,'arm':arm,'pid':extra['pid'],'connected_seconds':extra['connected_seconds'],'wall_seconds':extra['actual_wall_seconds'],'frames':extra['counts'].get('received',0),'message_rate':extra['counts'].get('received',0)/extra['connected_seconds'],'overflows':metrics['counters'].get('ws_queue_overflow',extra['counts'].get('queue_overflow',0)),'delay_rejections':feeds[-1]['stats'].get('processing_delay_rejections',0) if arm=='D' and feeds else extra['counts'].get('delay_ge250ms',0),'unexpected_disconnects':{k:v for k,v in extra['counts'].items() if k.startswith('disconnect_')},'queue_ms':metrics['stages'][keys['queue']],'loop_ms':metrics['stages'][keys['loop']],'rusage':extra['rusage'],'gc':{k:v for k,v in metrics['stages'].items() if k.startswith('gc_') and '.' not in k},'freshness':{'sample_count':len(feeds),'book_unfresh_samples':sum(not x.get('book_receipt_fresh',False) for x in feeds),'trade_unfresh_samples':sum(not x.get('trade_fresh',False) for x in feeds),'instantaneous_certificate_valid_samples':sum(x['passed'] for x in feeds),'trade_gap_observations':feeds[-1]['stats'].get('trade_gaps',0) if feeds else None,'unrepairable_gap_observations':feeds[-1]['stats'].get('unrepairable_gap',0) if feeds else None,'source_age_not_network':True},'strategy_evaluations':extra.get('strategy_evaluations',0),'stages':metrics['stages'],'raw_metrics':str((folder/'pipeline-metrics.json' if arm=='D' else folder/'result.json').relative_to(ROOT))}

def aggregate(items):
 result={}
 for k in sorted(set(x['arm'] for x in items)):
  selected=[x for x in items if x['arm']==k];secs=sum(x['connected_seconds'] for x in selected);frames=sum(x['frames'] for x in selected)
  result[k]={'connected_seconds':secs,'frames':frames,'message_rate':frames/secs,'overflows':sum(x['overflows'] for x in selected),'delay_rejections':sum(x['delay_rejections'] for x in selected),'max_queue_ms':max(x['queue_ms']['max_ms'] for x in selected),'max_loop_ms':max(x['loop_ms']['max_ms'] for x in selected),'total_process_cpu_seconds':sum(x['rusage']['user_cpu_seconds']+x['rusage']['system_cpu_seconds'] for x in selected),'process_cpu_per_connected_percent_one_core':100*sum(x['rusage']['user_cpu_seconds']+x['rusage']['system_cpu_seconds'] for x in selected)/secs,'peak_rss_mib':max(x['rusage']['peak_rss_bytes'] for x in selected)/1048576,'rusage_input_blocks':sum(x['rusage']['input_blocks'] for x in selected),'rusage_output_blocks':sum(x['rusage']['output_blocks'] for x in selected),'unexpected_disconnects':dict(sum((Counter(x['unexpected_disconnects']) for x in selected),Counter())),'strategy_evaluations':sum(x['strategy_evaluations'] for x in selected),'freshness_samples':sum(x['freshness']['sample_count'] for x in selected),'book_unfresh_samples':sum(x['freshness']['book_unfresh_samples'] for x in selected),'trade_unfresh_samples':sum(x['freshness']['trade_unfresh_samples'] for x in selected)}
 return result

main=[segment(p.parent,p.parent.name[-1]) for p in sorted((OUT/'main').glob('[0-9]*-*/launch.json'))];fixed=[segment(p.parent,p.parent.name[-1]) for p in sorted((OUT/'fixed').glob('[0-9]*-*/launch.json'))];soak=[segment(OUT/'fixed'/name,'D') for name in ['soak-1','soak-2']]
allmetrics={'matrix':main,'fixed_paired':fixed,'fixed_soak':soak};save(OUT/'stage-quantiles.json',allmetrics)
# Every recordedDspan>=250ms, not only rejectionclusters. Witnesslaginterval inferred from recordedlateness/endmono; no kernel-arrival claim.
correlation=[];os_summaries={}
for group,folders in [('main',[x for x in (OUT/'main').glob('[0-9]*-D')]),('fixed',[x for x in (OUT/'fixed').glob('[0-9]*-D')]+[OUT/'fixed/soak-1',OUT/'fixed/soak-2'])]:
 base=OUT/group;witness=read(base/'witness/result.json');we=read(base/'witness/events.json');wl=[x for x in we if x['kind']=='loop_stall'];osrows=jl(base/'os-samples.jsonl');io=[x for x in jl(base/'interval-iostat.jsonl') if x.get('parsed') and x['parsed']['interval_valid']]
 wp=base/'witness/samples.json';wcpu=read(wp)
 for folder in folders:
  pid=read(folder/'launch.json')['pid'];events=jl(folder/'correlated-events.jsonl');slow=[x for x in events if x['kind']=='stage_interval' and x['wall_ms']>=250];reject=[x for x in events if x['kind']=='queue_reject_context'];groups=[]
  for x in reject:
   if not groups or x['mono_ns']-groups[-1][-1]['mono_ns']>1000000000:groups.append([x])
   else:groups[-1].append(x)
  episodes=[{'type':'slow_stage','stage':x['stage'],'start_ns':x['mono_start_ns'],'end_ns':x['mono_end_ns'],'at_ns':x['at_ns'],'wall_ms':x['wall_ms'],'thread_cpu_ms':x['thread_cpu_ms'],'process_cpu_ms':x['process_cpu_ms']} for x in slow]
  episodes += [{'type':'reject_cluster','stage':'receipt_to_processing','start_ns':min(x['received_mono_ns'] for x in g),'end_ns':max(x['processing_start_ns'] for x in g),'at_ns':g[0]['at_ns'],'count':len(g),'max_queue_ms':max(x['queue_delay_ms'] for x in g)} for g in groups]
  for e in episodes:
   a,b=e['start_ns'],e['end_ns'];overlaps=[x for x in wl if x['mono_ns']>=a and x['mono_ns']-int(x['lag_ms']*1e6)<=b]
   wb=[x for x in wcpu if x['mono_ns']<=a];wa=[x for x in wcpu if x['mono_ns']>=b];ob=[x for x in osrows if x['mono_ns']<=a];oa=[x for x in osrows if x['mono_ns']>=b];before=ob[-1] if ob else None;after=oa[0] if oa else None;pb=psrow(before,pid) if before else None;pa=psrow(after,pid) if after else None;vmb=vm(before) if before else {};vma=vm(after) if after else {};ios=[x for x in io if a-5000000000<=x['mono_ns']<=b+5000000000]
   e.update(phase=folder.name,measurement=group,utc=stamp(e['at_ns']),witness_lag_overlaps=[{'at_ns':x['at_ns'],'lag_ms':x['lag_ms'],'mono_ns':x['mono_ns']} for x in overlaps],witness_max_overlapping_lag_ms=max((x['lag_ms'] for x in overlaps),default=0),witness_event_ring_overwritten=witness['metrics']['counters'].get('correlation_events_overwritten',0),pid_pagein_before=pb,pid_pagein_after=pa,pid_pagein_delta=pa['pageins']-pb['pageins'] if pa and pb else None,os_bracket_ms=(after['mono_ns']-before['mono_ns'])/1e6 if before and after else None,os_load_before=before['load'] if before else None,os_load_after=after['load'] if after else None,system_vm_delta={k:vma[k]-vmb[k] for k in ['Pageins','Pageouts','Swapins','Swapouts'] if k in vmb and k in vma},os_sampler_wall_before_ms=before.get('sampler_wall_ms') if before else None,os_sampler_wall_after_ms=after.get('sampler_wall_ms') if after else None,interval_cpu_nearby=[x['parsed']['system_cpu_percent'] for x in ios],interval_disk0_MBps_nearby=[x['parsed']['disk_columns'][2] for x in ios],witness_cpu_bracket_seconds=wa[0]['process_cpu_seconds']-wb[-1]['process_cpu_seconds'] if wa and wb else None,witness_wall_bracket_seconds=(wa[0]['mono_ns']-wb[-1]['mono_ns'])/1e9 if wa and wb else None)
   correlation.append(e)
 vals=[swap(x) for x in osrows];vals=[v for v in vals if v is not None];first,last=vm(osrows[0]),vm(osrows[-1]);rs=[psrow(x,p) for x in osrows for p in x['targets']['pids'] if psrow(x,p)];sampler=read(base/'sampler-summary.json');self_cpu=sampler['self_rusage'][0]+sampler['self_rusage'][1];child_cpu=sampler['children_rusage'][0]+sampler['children_rusage'][1]
 os_summaries[group]={'samples':len(osrows),'sampled_seconds':(osrows[-1]['mono_ns']-osrows[0]['mono_ns'])/1e9,'swap_used_mib_min':min(vals),'swap_used_mib_max':max(vals),'system_vm_counter_deltas':{k:last[k]-first[k] for k in ['Pageins','Pageouts','Swapins','Swapouts']},'load1':dist([x['load'][0] for x in osrows]),'interval_system_busy_percent':dist([100-x['parsed']['system_cpu_percent']['idle'] for x in io]),'interval_disk0_MBps':dist([x['parsed']['disk_columns'][2] for x in io]),'sampler_wall_ms':dist([x['sampler_wall_ms'] for x in osrows]),'sampler_own_cpu_ms':dist([x['sampler_cpu_ms'] for x in osrows]),'sampler_children_cpu_ms':dist([x['sampler_children_cpu_ms'] for x in osrows]),'sampler_total_cpu_seconds_including_children_and_continuous_iostat':self_cpu+child_cpu,'sampler_average_percent_one_core':100*(self_cpu+child_cpu)/sampler['actual_seconds'],'witness_counts':witness['counts'],'witness_connected_seconds':witness['connected_seconds'],'witness_loop_ms':witness['metrics']['stages']['loop_lag'],'witness_receipt_to_processing_ms':witness['metrics']['stages']['receipt_to_processing'],'witness_events_overwritten':witness['metrics']['counters'].get('correlation_events_overwritten',0)}
save(OUT/'slow-span-correlation.json',correlation)
protected=read(OUT/'protected-before.json');checks={k:hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==h for k,h in protected.items()};save(OUT/'protected-after.json',checks)
with urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=5) as f:delivery=json.load(f)
r=delivery['report'];assert r['position'] is None and r['budget_spent'] and r['buy_count']==r['sell_count']==1 and r['cash']=='999.76609237980375000000000' and r['timestral']=='DISABLED';save(OUT/'delivery-state.json',delivery)
conservative=[]
for name in ['soak-1','soak-2']:
 valid=[x['report']['isolation_connected_seconds'] for x in read(OUT/'fixed'/name/'controller-samples.json') if 'report' in x];conservative.append(max(valid)-min(valid))
result={'at_ns':time.time_ns(),'global_stability':'FAIL_BLOCKED','matrix':aggregate(main),'fixed_paired':aggregate(fixed),'fixed_soak':aggregate(soak),'soak_conservative_observed_connected_seconds_excluding_startup_cleanup_restart':sum(conservative),'soak_callback_connected_seconds':read(OUT/'fixed/complete.json')['soak_connected_seconds'],'os':os_summaries,'slow_D_stage_spans':sum(x['type']=='slow_stage' for x in correlation),'slow_D_stage_spans_with_independent_W_lag_overlap':sum(x['type']=='slow_stage' and x['witness_max_overlapping_lag_ms']>0 for x in correlation),'reject_clusters':[x for x in correlation if x['type']=='reject_cluster'],'protected_paths':len(checks),'protected_all_unchanged':all(checks.values()),'restore':read(OUT/'fixed/restored.json'),'causality':'Fairreceivefreshburststarvationdemonstratedsynthetic+actual. ResidualDwallwaitlowCPUwithsomeindependentWloopoverlap establishescommonhosttimingcomponent, butnotuniquepagefaultvsOSscheduler/GIL/storage. NotallDdelayexplainedbyW, no claimalllatencysolved. Old22/35unattributed. OSsystemwidecountersarecontextnotbotfaultproof.04-DreceiveTimeoutError/unrepairablegapUNRESOLVED.','next_discriminating_test':'Onlyifauthorized: same-spentjournalDfull vsDnoncritical-owner-state-export-OFF matchedcontrol, retaincriticalAtomicJournalFULLdurability+guards, sameexternalW/probes. TriggeroneexternalownPIDstackcapture onindependentheartbeatstall>100ms to distinguishJSON/pagefault/GILwait/sqlitewrite; do notraise thresholds/reboot/quitapps. No such extraexperiment run now.','interpretation':'C0actual4hcloses => activeeconomicstrategycostNA. ProtectionNOTEXERCISED(flat). Read-onlyRiskhooknotportfolioexecution. DexternalizedOSprobeinstrumentationcaveat. Sequentialnonrandommarket/hostloadconfoundsremain; ratesnormalizednotcausalperformanceproof.'}
save(OUT/'results.json',result)
print(json.dumps({'matrix':result['matrix'],'fixed_paired':result['fixed_paired'],'soak':result['fixed_soak'],'soak_conservative_connected':sum(conservative),'slow_spans':result['slow_D_stage_spans'],'W_overlap':result['slow_D_stage_spans_with_independent_W_lag_overlap'],'clusters':[(x['count'],x['max_queue_ms'],x['witness_max_overlapping_lag_ms'],x['pid_pagein_delta']) for x in result['reject_clusters']],'protected':result['protected_all_unchanged']},indent=2))
