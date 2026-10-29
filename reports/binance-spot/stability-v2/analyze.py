"""Summarize measured soak without retroactive stage-causality claims."""
from pathlib import Path
from collections import Counter
import json,hashlib
P=Path(__file__).resolve().parent
rows=[json.loads(x) for x in (P/'soak-samples.jsonl').read_text().splitlines()]
summary=json.loads((P/'soak-summary.json').read_text());stages={k:json.loads((P/n).read_text()) for k,n in [('before_restart','pre-restart-metrics.json'),('after_restart','post-soak-metrics.json')]}
valid=sum(bool(x['certificate']['passed']) for x in rows);reasons=Counter();first_reject={};last_counts={};segments={};split=301.728293
for x in rows:
 f=x['feed'];phase='before_restart' if x['elapsed_seconds']<split else 'after_restart';stats=f['stats'];c=segments.setdefault(phase,{'samples':0,'valid':0,'first_elapsed':x['elapsed_seconds'],'last_elapsed':0,'max_stats':{}})
 c['samples']+=1;c['valid']+=bool(x['certificate']['passed']);c['last_elapsed']=x['elapsed_seconds']
 for k,n in stats.items():c['max_stats'][k]=max(n,c['max_stats'].get(k,0))
 if stats.get('processing_delay_rejections') and phase not in first_reject:first_reject[phase]={'elapsed_seconds':x['elapsed_seconds'],'previous_sample_elapsed_seconds':last_counts.get(phase),'count_at_first_observation':stats['processing_delay_rejections']}
 last_counts[phase]=x['elapsed_seconds']
 if not f['passed']:
  if f['actual_connected_seconds']<60:reasons['warmup_or_rewarm_under60s']+=1
  if not f['native_closed_candles']:reasons['no_native_closed_candle_yet']+=1
  if not f['book_receipt_fresh']:reasons['book_entry_freshness_or_spread_false']+=1
  if not f['trade_fresh']:reasons['trade_receipt_or_source_freshness_false']+=1
  if not f['rest_comparison'].get('passed'):reasons['REST_comparison_not_passed']+=1
  if f['processing_delay_ms']['last']>250:reasons['last_processing_delay_over250ms']+=1
  if stats.get('unrepairable_gap'):reasons['unrepairable_gap']+=1
  if stats.get('bar_gaps'):reasons['bar_gap']+=1
out={'status':'READINESS_BLOCKED_STABILITY_TARGET_NOT_PASSED','actual_soak':summary,'samples':len(rows),'certificate_valid_samples':valid,'certificate_valid_percent':valid/len(rows)*100,'false_predicates_nonexclusive':dict(reasons),'first_observed_rejections':first_reject,'segments':segments,'stage_distributions_by_process':stages,
'source_clock_sample_ranges':{k:{'min':min(values),'max':max(values)} for k in ['clock_offset_ms','clock_uncertainty_ms'] if (values:=[x['feed'][k] for x in rows if x['feed'].get(k) is not None])},
'last_trade_source_age_corrected_ms_range':{'min':min(x['feed']['source_age_ms']['last'] for x in rows if x['feed']['source_age_ms']['last'] is not None),'max':max(x['feed']['source_age_ms']['last'] for x in rows if x['feed']['source_age_ms']['last'] is not None)},
'causality':'Original22rejects/595s had insufficient historical stage telemetry; no retroactive attribution. New loop/queue/stage maxima overlap concurrent work but quantiles do not prove scheduler/GIL/disk causality. Initial queued rejections and later reconnect durable commits must not be conflated. Critical lockwait measured separately; original durable FULL commit can still stall owner, not claimed hardened against stalled storage.',
'limits':'WS receive wait includes provider idle and event-loop scheduling; receipt is application timestamp, not kernel arrival. Sourceage/clockuncertainty are not measured network latency. BookTicker source timestamp absent. Actual flat observation has no active position protection or economic strategy execution timing; synthetic tests only for those hooks.',
'concurrency':'Same-host offline focused tests and public historical acquisition/replays occurred during soak. Not an isolated-load stability estimate.',
'invariants':{'threshold_processing_ms':250,'threshold_fresh_seconds':2,'one_buy_one_sell':True,'flat_spent_preserved':summary['final_flat_spent'],'original_Runtime_Risk_Spot_unchanged':True},
'launch_attempt':'First shell-background launch died with tool command; attempt artifacts preserved as invalid-launch-attempt. Not counted as elapsed soak or provider failure.'}
(P/'verification.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:out[k] for k in ['status','samples','certificate_valid_samples','certificate_valid_percent','first_observed_rejections','segments']},indent=2))
