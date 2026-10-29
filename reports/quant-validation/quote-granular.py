"""Free metadata quotes only; no time-series method is called."""
from datetime import datetime,timezone
from pathlib import Path
import json
from databento_planner.security import load_key,MetadataOnly,quietly
from databento_planner.cache import atomic_json
from mnq_data.core import iso
out=Path(__file__).resolve().parent
key,auth=load_key();b=MetadataOnly(key,max_requests=12,max_seconds=180)
def run():
 rows=[]
 for label,schema,symbols,start,end in [
  ('Both roots, one full cash day,1second bars','ohlcv-1s',['MNQZ6','MESZ6'],'2026-10-23T13:30:00Z','2026-10-23T20:00:00Z'),
  ('MES ambiguous-bracket10minute slice, trades','trades',['MESZ6'],'2026-10-23T13:55:00Z','2026-10-23T14:05:00Z'),
  ('MES same slice, BBO for execution checks','mbp-1',['MESZ6'],'2026-10-23T13:55:00Z','2026-10-23T14:05:00Z')]:
  req={'dataset':'GLBX.MDP3','schema':schema,'symbols':symbols,'stype_in':'raw_symbol','start':start,'end':end}
  value={name:b.call('metadata',name,**req) for name in ('get_cost','get_billable_size','get_record_count')}
  rows.append({'purpose':label,'request':req,'official_metrics':value})
  atomic_json(out/'granular-quote-partial.json',{'completed':rows,'data_calls':0})
 atomic_json(out/'granular-quote.json',{'status':'official_metadata_quote_only','checked_at':iso(datetime.now(timezone.utc)),
  'quotes':rows,'http':b.trace,'data_calls':0,'download_authorized':False,
  'limitation':'1second OHLC still cannot prove subsecond first passage. Trades give ordering; MBP1 adds BBO, not full queue/market impact or live fills.'})
try:quietly(run);print('GRANULAR_OFFICIAL_QUOTE_COMPLETE_NO_DOWNLOAD')
except Exception:print('GRANULAR_QUOTE_INCOMPLETE_NO_DOWNLOAD')
finally:b.close()
