"""Reproduce measured source rollover/revisions; no network or secrets."""
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
import json,hashlib
from mnq_local.capital_candles import parse_candle,STEPS
ROOT=Path(__file__).resolve().parent

def stats(values):
 a=sorted(values)
 return {'n':len(a),**{k:a[int((len(a)-1)*p)] for k,p in [('min',0),('p50',.5),('p95',.95),('p99',.99),('max',1)]}} if a else {'n':0}

def analyze(path):
 groups={};examples=[]
 for line in path.open():
  d=json.loads(line);epic,res=d['epic'],d['resolution'];key=epic+'|'+res
  g=groups.setdefault(key,{'responses':0,'invalid_responses':0,'invalid_rows':0,'bars':{},'request_ms':[],'interpoll_s':[],
   'revision_events':0,'revised_closed_bars':set(),'revision_fields':Counter(),'last_received_ns':None,'unique_invalid_bars':set(),'duplicate_or_reordered_responses':0,'noncontiguous_responses':0})
  at=d['received_ns'];g['responses']+=1;g['request_ms'].append(d['request_ms']);invalid=False
  if g['last_received_ns']:g['interpoll_s'].append((at-g['last_received_ns'])/1e9)
  g['last_received_ns']=at
  rows=d['payload']['prices'];starts=[]
  for r in rows:
   t=datetime.fromisoformat(r['snapshotTimeUTC']).replace(tzinfo=timezone.utc);starts.append(int(t.timestamp())*1000)
  g['duplicate_or_reordered_responses']+=starts!=sorted(set(starts))
  g['noncontiguous_responses']+=any(b-a!=STEPS[res]*1000 for a,b in zip(starts,starts[1:]))
  for r,start in zip(rows,starts):
   end=start+STEPS[res]*1000;closed=max(starts)>=end and at>=end*10**6
   values={n:r[n] for n in ('openPrice','highPrice','lowPrice','closePrice','lastTradedVolume')}
   old=g['bars'].get(start)
   if old is None:
    old=g['bars'][start]={'end_ms':end,'first_seen_ns':at,'tracked':not closed,'first_successor_seen_ns':None,'last_without_successor_ns':None,'values':values,'last_closed_values':None,'revisions':0}
   if not closed:old['last_without_successor_ns']=at
   if closed:
    if old['first_successor_seen_ns'] is None:old['first_successor_seen_ns']=at
    previous=old['last_closed_values']
    if previous is not None and values!=previous:
     fields=[]
     for field,v in values.items():
      if v!=previous[field]:
       if isinstance(v,dict):fields.extend(field+'.'+s for s in v if v[s]!=previous[field][s])
       else:fields.append(field)
     g['revision_events']+=1;g['revised_closed_bars'].add(start);g['revision_fields'].update(fields);old['revisions']+=1
     if len(examples)<20:examples.append({'group':key,'bar_start_ms':start,'received_ns':at,'seconds_after_bar_end':(at-end*10**6)/1e9,'fields':fields,'before':previous,'after':values})
    old['last_closed_values']=values
   old['values']=values
   try:parse_candle(epic,res,r)
   except ValueError:
    invalid=True;g['invalid_rows']+=1;g['unique_invalid_bars'].add(start)
  g['invalid_responses']+=invalid
 result={}
 for key,g in groups.items():
  live=[r for r in g['bars'].values() if r['tracked'] and r['first_successor_seen_ns'] is not None]
  result[key]={k:v for k,v in g.items() if k not in ('bars','last_received_ns','request_ms','interpoll_s','revised_closed_bars','unique_invalid_bars')}
  result[key].update(revised_closed_bars=len(g['revised_closed_bars']),unique_invalid_bars=len(g['unique_invalid_bars']),
   observed_rollover_availability_upper_s=stats([(r['first_successor_seen_ns']-r['end_ms']*10**6)/1e9 for r in live]),
   observed_rollover_lower_s=stats([max(0,(r['last_without_successor_ns']-r['end_ms']*10**6)/1e9) for r in live]),
   request_ms=stats(g['request_ms']),interpoll_s=stats(g['interpoll_s']))
 return {'source':str(path),'clock':'CLIENT_UTC_UNCORRECTED_IN_RAW_CAPTURE; runtime separately records official server RTT offset bounds',
  'publication_metric':'First observed source successor bounds availability, not exact broker emission or one-way latency',
  'finality':'NO_PROVIDER_FINALITY_FLAG; historical revisions measured including invalid transient ask values',
  'groups':result,'revision_examples':examples,'orders_sent':0}
if __name__=='__main__':
 result=analyze(ROOT/'raw-candles.jsonl');(ROOT/'native-analysis.json').write_text(json.dumps(result,indent=2));print(json.dumps(result['groups'],indent=2))
