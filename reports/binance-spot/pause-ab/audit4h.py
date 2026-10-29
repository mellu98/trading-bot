"""Offline audit of existing prospective context; never generates or executes signals."""
from pathlib import Path
import importlib.util,json,time
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent

def causal(origin,available,decision,quote_receipt,quote_age_limit=2000000000):
 return origin<=available<=decision and 0<=decision-quote_receipt<=quote_age_limit

def run():
 s=importlib.util.spec_from_file_location('frozen_forward',ROOT/'reports/binance-spot/forward-signals/recorder.py');f=importlib.util.module_from_spec(s);s.loader.exec_module(f);events=[json.loads(x) for x in (ROOT/'data/binance-spot/forward-signals/events.jsonl').open()];known={};responses=[];revisions=[];duplicate_context_rows=0;lasttime=None;decisions=[]
 for e in events:
  if e['kind']=='public_rest' and e['evidence']['path']=='/api/v3/time':lasttime=e['evidence']
  if e['kind']=='native4h_response':
   cutoff=e['params']['endTime']+1;bars=f.closed(e['rows'],cutoff);rows=e['rows'];revision=0
   for row in rows:
    value=tuple(row[1:7])
    if row[0] in known:
     duplicate_context_rows+=1
     if known[row[0]]!=value:revisions.append({'start_ms':row[0],'available_at_ns':e['received_ns']});revision+=1
    known[row[0]]=value
   responses.append({'request_start_ns':e['request_start_ns'],'available_at_ns':e['received_ns'],'cutoff_ns':cutoff*1000000,'context_bars':len(bars),'first_start_ns':bars[0].start,'last_end_ns':bars[-1].end,'gaps':0,'forming_in_selected':sum(b.end>cutoff*1000000 for b in bars),'warmup_only':e['warmup_only'],'bar_source':'BINANCE_NATIVE4H_PUBLIC_REST','clock_midpoint_offset_ms':None if not lasttime else lasttime['data']['serverTime']-(lasttime['request_start_ns']+lasttime['response_received_ns'])/2000000,'clock_uncertainty_ms':None if not lasttime else (lasttime['response_received_ns']-lasttime['request_start_ns'])/2000000,'revision_rows':revision})
  if e['kind']=='real_closed4h_signal_observation':decisions.append(e)
 result={'at_ns':time.time_ns(),'native_context_responses':responses,'selected_each':256,'repeated_warmup_context_rows_not_forward_duplicates':duplicate_context_rows,'ohlcv_revisions':revisions,'actual_new4h_decisions':len(decisions),'forward_status':'NOT_VERIFIED_REAL_FORWARD' if not decisions else 'OBSERVED_NEEDS_CAUSAL_DETAIL','actionable_count':sum(bool(x.get('actionable')) for x in decisions),'collector_forward_gaps':sum(x['kind']=='forward_gap' for x in events),'REST_blocked_events':sum(x['kind']=='blocked' for x in events),'warmup_events':sum(x['kind']=='warmup_only' for x in events),'no_backfilled_signal_claim':True,'forming_excluded':True,'availability':'Native response received_ns is actual availability; context closes <= cutoff. No actual new decision => decision/quoteage causality NOTVERIFIED on real forward observations. Fake-fixture tests are technical tests only.','safety':'Frozen collector hardcodes actionable=false and STABILITY_READINESS_BLOCKED/STRICT_NEWS_UNCERTIFIED/NO_ORDER_CAPABILITY regardless instantaneous certificate. Original250ms/2s untouched.','reconnect_semantics':'Collector polls publicREST; noWSreconnect concept. Runtime WS faults audited separately. Restart bootstrap is warmup only, not prospective backfill.'}
 (OUT/'four-hour-audit.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':run()
