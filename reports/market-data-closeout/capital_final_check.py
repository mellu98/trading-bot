"""Final offline source-byte check. No HTTP, accounts, secrets or trading."""
from collections import Counter
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import hashlib,json
from mnq_local.capital_candles import parse_candle
UTC=timezone.utc;EPOCH=datetime(1970,1,1,tzinfo=UTC)
FIELDS=('openPrice','closePrice','highPrice','lowPrice')

def stats(a):
 a=sorted(a)
 return {'n':len(a),**{k:a[int((len(a)-1)*p)] for k,p in [('min',0),('p50',.5),('p95',.95),('max',1)]}} if a else {'n':0}

def analyze(path):
 original=path.read_bytes();hist={};groups={};counts=Counter();inverted_fields=Counter();revised_fields=set();revision_ages=[];spans=[];examples=[];revision_examples=[]
 for line in original.splitlines():
  d=json.loads(line,parse_float=Decimal);epic,res=d['epic'],d['resolution'];step={'MINUTE':60,'MINUTE_5':300}[res]
  received=d['received_ns'];requested=d['request_started_ns'];rows=d['payload']['prices'];starts=[]
  for raw in rows:
   at=datetime.fromisoformat(raw['snapshotTimeUTC']);assert at.tzinfo is None
   starts.append((at.replace(tzinfo=UTC)-EPOCH)//timedelta(milliseconds=1))
  counts['responses']+=1;response_inverted=False
  g=groups.setdefault(epic+'|'+res,{'responses':0,'inverted_responses':0,'revision_events':0,'revised_bars':set(),'revision_ages':[]})
  g['responses']+=1
  for raw,start in zip(rows,starts):
   end=start+step*1000;key=(epic,res,start)
   values=tuple(raw[field][side] for field in FIELDS for side in ('bid','ask'))+(raw['lastTradedVolume'],)
   bad=[f for f in FIELDS if raw[f]['ask']<raw[f]['bid']]
   response_inverted|=bool(bad);counts['rows']+=1
   if bad:
    counts['homologous_inverted_rows']+=1;inverted_fields.update(bad)
    if len(examples)<5:examples.append({'epic':epic,'resolution':res,'bar_start_utc':raw['snapshotTimeUTC'],
     'received_ns':received,'age_after_bar_end_s':(received-end*10**6)/1e9,
     'homologous_fields':{f:{side:str(raw[f][side]) for side in ('bid','ask')} for f in bad}})
   try:
    parsed=parse_candle(epic,res,raw)
    if bad:counts['parser_rejection_disagreements']+=1
    for field in FIELDS:
     for side in ('bid','ask'):
      counts['parser_field_mismatches']+=Decimal(parsed['prices'][field.removesuffix('Price')][side])!=raw[field][side]
    counts['parser_timestamp_mismatches']+=parsed['start_ms']!=start
   except ValueError:
    if not bad:counts['parser_rejection_disagreements']+=1
   # Both source rollover and a request START after nominal closure are needed.
   # Thus response transfer across a minute boundary cannot create a revision.
   closed=requested>=end*10**6 and max(starts)>=end
   h=hist.setdefault(key,{'end_ms':end,'last_closed_values':None,'revision_ages':[],
     'bad_first_ns':None,'bad_last_ns':None,'first_seen_ns':received,'last_seen_ns':received})
   h['last_seen_ns']=received
   if bad:
    if h['bad_first_ns'] is None:h['bad_first_ns']=received
    h['bad_last_ns']=received
   elif h['bad_first_ns'] is not None:
    spans.append({'group':epic+'|'+res,'bar_start_ms':start,'first_bad_ns':h['bad_first_ns'],'last_bad_ns':h['bad_last_ns'],
     'next_valid_ns':received,'observed_bad_span_s':(h['bad_last_ns']-h['bad_first_ns'])/1e9,
     'first_bad_to_next_valid_s':(received-h['bad_first_ns'])/1e9,'right_censored':False})
    h['bad_first_ns']=h['bad_last_ns']=None
   if closed:
    old=h['last_closed_values']
    if old is not None and old!=values:
     age=(received-end*10**6)/1e9;g['revision_events']+=1;g['revised_bars'].add(start);g['revision_ages'].append(age);revision_ages.append(age)
     fields=[field+'.'+side for i,field in enumerate(FIELDS) for j,side in enumerate(('bid','ask')) if old[2*i+j]!=values[2*i+j]]
     if old[-1]!=values[-1]:fields.append('lastTradedVolume')
     revised_fields.update(fields);h['revision_ages'].append(age)
     if len(revision_examples)<5:revision_examples.append({'group':epic+'|'+res,'bar_start_utc':raw['snapshotTimeUTC'],
      'age_after_bar_end_s':age,'request_started_after_bar_end':True,'successor_present':True,'fields':fields})
    h['last_closed_values']=values
  counts['homologous_inverted_responses']+=response_inverted;g['inverted_responses']+=response_inverted
 for (epic,res,start),h in hist.items():
  if h['bad_first_ns'] is not None:
   spans.append({'group':epic+'|'+res,'bar_start_ms':start,'first_bad_ns':h['bad_first_ns'],'last_bad_ns':h['bad_last_ns'],
    'next_valid_ns':None,'observed_bad_span_s':(h['bad_last_ns']-h['bad_first_ns'])/1e9,'right_censored':True})
 result={name:counts[name] for name in ['responses','rows','homologous_inverted_responses','homologous_inverted_rows','parser_rejection_disagreements','parser_field_mismatches','parser_timestamp_mismatches']}
 result.update(source_sha256=hashlib.sha256(original).hexdigest(),source_file_unchanged=path.read_bytes()==original,
  homologous_inversion_field_counts=dict(inverted_fields),post_successor_revision_events=len(revision_ages),
  closed_revision_fields=sorted(revised_fields),revision_age_seconds=stats(revision_ages),inversion_examples=examples,revision_examples=revision_examples,
  anomalous_episode_observed_span_seconds=stats([r['observed_bad_span_s'] for r in spans]),
  max_episode=max(spans,key=lambda r:r['observed_bad_span_s']),right_censored_episodes=sum(r['right_censored'] for r in spans),
  persistence_caveat='Only observed timestamps bound persistence; continuity between polls and stability after capture are not proved.',
  interpretation='Homologous OHLC-side ordering violations; NOT proof of an instantaneous executable crossed order book. Different extrema times alone do not explain homologous high/high or low/low inversion on synchronized equal-interval data.',
  parser_defect_found=any(counts[n] for n in ('parser_rejection_disagreements','parser_field_mismatches','parser_timestamp_mismatches')),capital_verdict='NOT_SUITABLE_FOR_AUTOMATION_OF_CURRENT_STRATEGY',network_requests=0,orders_sent=0)
 result['groups']={key:{k:v for k,v in g.items() if k not in ('revised_bars','revision_ages')}|{'revised_closed_bars':len(g['revised_bars']),'revision_age_seconds':stats(g['revision_ages'])} for key,g in groups.items()}
 return result
if __name__=='__main__':
 out=Path(__file__).resolve().parent;result=analyze(out.parent/'capital-v63/raw-candles.jsonl')
 (out/'capital-final-check.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('inversion_examples','revision_examples','groups')},indent=2))
