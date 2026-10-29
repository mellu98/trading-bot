"""One bounded quiet-host control, unchanged frozen observer and no strategy runs."""
from pathlib import Path
from collections import Counter
import json,time,urllib.request,subprocess,os
P=Path(__file__).resolve().parent;start=time.monotonic();samples=[];errors=[]
def save(n,x):(P/n).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def resources():
 out={'at_ns':time.time_ns(),'load':os.getloadavg()}
 for name,cmd in [('vm_stat',['vm_stat']),('swap',['sysctl','vm.swapusage']),('pressure',['sysctl','kern.memorystatus_vm_pressure_level']),('observer',['ps','-p',(P/'observer.pid').read_text().strip(),'-o','pid,etime,%cpu,rss'])]:
  try:out[name]=subprocess.check_output(cmd,text=True,timeout=5)
  except Exception as exc:out[name]=type(exc).__name__
 return out
before=json.loads((P/'pipeline-metrics.json').read_text());save('quiet-control-start.json',{'at_ns':time.time_ns(),'metrics':before,'resources':resources(),'scope':'After all92 tests and both economic replays;180seconds no heavy tasks, unchanged source/guards. LocalHTTP1Hz polling itself remains.'})
with (P/'quiet-control-samples.jsonl').open('w',buffering=1) as f:
 while time.monotonic()-start<180:
  elapsed=time.monotonic()-start;sent=time.monotonic_ns()
  try:
   with urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=4) as response:x=json.load(response)
   r=x['report'];assert r['budget_spent'] and r['buy_count']==1 and r['sell_count']==1 and r['position'] is None
   item={'elapsed':elapsed,'at_ns':time.time_ns(),'client_ms':(time.monotonic_ns()-sent)/1e6,'feed':r['feed_metrics'],'flat_spent':r['observe_only']};samples.append(item);f.write(json.dumps(item)+'\n')
  except Exception as exc:errors.append({'elapsed':elapsed,'type':type(exc).__name__})
  time.sleep(1)
after=json.loads((P/'pipeline-metrics.json').read_text());save('quiet-control-end-metrics.json',after)
a=samples[0]['feed']['stats'];b=samples[-1]['feed']['stats'];deltas={k:b.get(k,0)-a.get(k,0) for k in set(a)|set(b)};durations=sorted(x['client_ms'] for x in samples);n=len(samples)
stages={k:{'count_delta':s['count']-before['stages'].get(k,{}).get('count',0),'new_lifetime_max_during_control':s['max_ms']>before['stages'].get(k,{}).get('max_ms',0),'lifetime_max_before_ms':before['stages'].get(k,{}).get('max_ms'),'lifetime_max_after_ms':s['max_ms']} for k,s in after['stages'].items()}
valid=sum(bool(x['feed']['passed']) for x in samples)
save('quiet-control-summary.json',{'actual_seconds':time.monotonic()-start,'sampled_span_seconds':samples[-1]['elapsed']-samples[0]['elapsed'],'samples':n,'errors':errors,'valid_samples':valid,'valid_percent':valid/n*100,'feed_counter_deltas':deltas,'metric_counter_deltas':{k:v-before['counters'].get(k,0) for k,v in after['counters'].items()},'stage_count_and_record_deltas':stages,'client_ms':{k:durations[int((n-1)*v)] for k,v in [('p50',.5),('p95',.95),('p99',.99),('max',1)]},'resources_end':resources(),'readiness':'REMAINS_BLOCKED;180scontrol cannot override failed620s','limits':'No heavy work launched by executor during control; other host tasks not controlled. Stage quantiles are rolling/lifetime, not isolated control distributions; only count/record deltas claimed. Counter first/last endpoints exclude initial request latency.'})
