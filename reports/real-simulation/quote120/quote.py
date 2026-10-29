"""One free 120-cash-session quote study; no data download capability."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from databento_planner.cache import atomic_json
from databento_planner.planner import sessions, request_for, validate_conditions, money, stamp
from databento_planner.security import MetadataOnly, load_key, quietly, PlannerError
from mnq_data.core import Adapter, digest, iso

OUT=Path(__file__).resolve().parent
STATE=OUT/'responses.json'
responses=json.loads(STATE.read_text()) if STATE.exists() else {}
key,auth=load_key()
backend=MetadataOnly(key,max_requests=45,max_seconds=200)

def call(area,name,**request):
    identity=digest({'area':area,'name':name,'request':request})
    if identity in responses:
        item=responses[identity]
        if item['request']!=request or item['area']!=area or item['name']!=name:raise PlannerError('checkpoint_identity_mismatch')
        return item['value']
    value=backend.call(area,name,**request)
    responses[identity]={'area':area,'name':name,'request':request,'value':value,
                         'checked_at':iso(datetime.now(timezone.utc)),'http_status':backend.trace[-1]['http_status']}
    atomic_json(STATE,responses)
    return value


def run():
    ss=sessions('2026-10-24T00:00:00Z',120)
    a=ss[0]['date'];b='2026-10-24'
    if 'ohlcv-1m' not in call('metadata','list_schemas',dataset='GLBX.MDP3'):raise PlannerError('schema_unavailable')
    ranges=call('metadata','get_dataset_range',dataset='GLBX.MDP3')['schema']['ohlcv-1m']
    if stamp(ranges['start'])>stamp(ss[0]['start']) or stamp(ranges['end'])<stamp(ss[-1]['end']):raise PlannerError('range_unavailable')
    class Resolver:
        def call(self,area,name,**request):return call(area,name,**request)
    mapping=Adapter(Resolver()).resolve(('MNQ','MES'),a,b,'v')
    if any(mapping.get(k) for k in ('partial','not_found','raw_partial','raw_not_found','rejected')):raise PlannerError('mapping_incomplete')
    conditions=validate_conditions(call('metadata','get_dataset_condition',dataset='GLBX.MDP3',start_date=a,end_date=b),[s['date'] for s in ss])
    parts=[]
    for s in ss:
        req,one=request_for(s,'MNQ',mapping)
        _,two=request_for(s,'MES',mapping)
        req['symbols']=[one['contract'],two['contract']]
        value=money(call('metadata','get_cost',**req))
        parts.append({'date':s['date'],'request':req,'cost_usd':str(value),
                      'expected_minutes_per_root':s['expected_minutes']})
    result={'status':'official_120_session_quote_complete','dataset':'GLBX.MDP3','schema':'ohlcv-1m',
            'sessions':120,'first_session':a,'last_session':ss[-1]['date'],
            'total_cost_usd':str(sum((money(p['cost_usd']) for p in parts),Decimal(0))),
            'partitions':parts,'mapping':mapping,'conditions':conditions,'http200_responses':len(responses),
            'all_observed_http200':all(r['http_status']==200 for r in responses.values()),
            'generated_at':iso(datetime.now(timezone.utc)),
            'scope':'Each actual XNYS cash session09:30NY through actual close; not Globex',
            'expected_clock_slots_combined':2*sum(s['expected_minutes'] for s in ss),
            'record_count_and_size_not_queried':True,'download_authorized':False,'data_calls':0,
            'quote_must_be_refreshed_before_any_future_approved_acquisition':True,
            'abc':'120 calendar sessions sufficient for default70-session split and90-session count floors, subject to actual complete usable data and untouched holdout',
            'holdout':'Five already inspected Oct19–23 sessions cannot be relabeled untouched holdout',
            'entitlements':'Metadata accepted, not a future paid-license/balance attestation'}
    atomic_json(OUT/'quote.json',result)

try:
    quietly(run)
except PlannerError:
    print(json.dumps({'status':'partial_or_blocked_free_quote','responses_persisted':len(responses),'new_http':backend.trace,'data_calls':0}))
    raise SystemExit(3)
finally:
    atomic_json(OUT/'last-batch.json',{'authentication':auth,'http':backend.trace,'responses_persisted':len(responses),'data_calls':0})
    backend.close()
if (OUT/'quote.json').exists():
    result=json.loads((OUT/'quote.json').read_text())
    print(json.dumps({k:result[k] for k in ('status','first_session','last_session','sessions','total_cost_usd','expected_clock_slots_combined','http200_responses')}))
