"""Free quote for a pre-holdout calibration ambiguity; never downloads data."""
import csv,json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from databento_planner.security import load_key,MetadataOnly,quietly
from databento_planner.cache import atomic_json
from mnq_data.core import iso
p=Path(__file__).resolve().parent
protocol=json.loads((p/'preregistered-protocol.json').read_text())
cal=set(protocol['folds'][0]['calibration'])
rows=list(csv.DictReader((p/'results/MNQ-fixed-daily-independent/trades.csv').open()))
case=next(r for r in rows if r['intrabar_ambiguous']=='True' and r['entry_at'][:10] in cal)
t=datetime.fromisoformat(case['exit_at'])
key,_=load_key();b=MetadataOnly(key,max_requests=6,max_seconds=120)
def run():
 quotes=[]
 for schema in ('trades','mbp-1'):
  req={'dataset':'GLBX.MDP3','schema':schema,'symbols':[case['contract']],'stype_in':'raw_symbol',
       'start':iso(t-timedelta(minutes=5)),'end':iso(t+timedelta(minutes=5))}
  values={name:b.call('metadata',name,**req) for name in ('get_cost','get_billable_size','get_record_count')}
  quotes.append({'request':req,'official_metrics':values})
 atomic_json(p/'granular-mnq-quote.json',{'status':'official_metadata_quote_only','checked_at':iso(datetime.now(timezone.utc)),
  'calibration_case':case,'quotes':quotes,'http':b.trace,'download_authorized':False,'data_calls':0,
  'why':'MNQ fixed diagnostic has75of627ambiguous brackets. Choose a calibration case, not holdout, to validate execution assumptions without selecting a favorable fill.'})
try:quietly(run);print('MNQ_EXECUTION_QUOTE_COMPLETE_NO_DOWNLOAD')
except Exception:print('MNQ_EXECUTION_QUOTE_UNVERIFIED_NO_DOWNLOAD')
finally:b.close()
