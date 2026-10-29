"""Refresh only the exact five-session free metadata quote; never acquire data."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

from databento_planner.cli import baseline_check, secure_write
from databento_planner.planner import sessions, request_for, validate_conditions, stamp, money
from databento_planner.security import MetadataOnly, load_key, quietly, PlannerError
from mnq_data.core import Adapter, digest, file_hash, iso

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DATASET = 'GLBX.MDP3'
SCHEMA = 'ohlcv-1m'
backend = None
key = None
responses = []

def write(name, value):
    secure_write(OUT / name, value, (key, key[3:] if key else None), replace=True)

def call(area, endpoint, **request):
    value = backend.call(area, endpoint, **request)
    if not backend.trace or backend.trace[-1]['http_status'] != 200:
        raise PlannerError('official_http200_required')
    checked = iso(datetime.now(timezone.utc))
    response = {'area': area, 'endpoint': endpoint, 'request': request, 'value': value,
                'checked_at': checked, 'http_status': 200}
    responses.append(response)
    write('responses.json', responses)
    return value, checked

def run():
    global key, backend
    before = baseline_check()
    frozen = json.loads((ROOT/'reports/databento/planning/correction-handoff.json').read_text())['source_sha256']
    if any(file_hash(ROOT/p) != h for p,h in frozen.items()):
        raise PlannerError('frozen_planner_changed')
    key, auth = load_key()
    backend = MetadataOnly(key, max_requests=40, max_seconds=240)
    ss = sessions('2026-10-24T00:00:00Z', 5)
    if [s['date'] for s in ss] != [f'2026-10-{day}' for day in range(19,24)]:
        raise PlannerError('exact_five_session_scope_mismatch')
    schemas,_ = call('metadata','list_schemas',dataset=DATASET)
    if SCHEMA not in schemas:
        raise PlannerError('schema_unavailable')
    ranges,_ = call('metadata','get_dataset_range',dataset=DATASET)
    available = ranges.get('schema',{}).get(SCHEMA)
    if not available or stamp(available['start']) > stamp(ss[0]['start']) or stamp(available['end']) < stamp(ss[-1]['end']):
        raise PlannerError('outside_available_schema_range')
    class Resolver:
        def call(self, area, endpoint, **request):
            return call(area, endpoint, **request)[0]
    mapping = Adapter(Resolver()).resolve(('MNQ','MES'),'2026-10-19','2026-10-24','v')
    if any(mapping.get(k) for k in ('partial','not_found','raw_partial','raw_not_found','rejected')):
        raise PlannerError('incomplete_mapping')
    conditions,_ = call('metadata','get_dataset_condition',dataset=DATASET,start_date='2026-10-19',end_date='2026-10-24')
    conditions = validate_conditions(conditions,[s['date'] for s in ss])
    parts = []
    for s in ss:
        for root in ('MNQ','MES'):
            request,item = request_for(s,root,mapping)
            if item['contract'] != root+'Z6':
                raise PlannerError('contract_differs_from_requested_approval_scope')
            count,_ = call('metadata','get_record_count',**request)
            size,_ = call('metadata','get_billable_size',**request)
            if type(count) is not int or count != 390 or type(size) is not int or size <= 0:
                raise PlannerError('unexpected_metadata_count_or_size')
            parts.append({'date':s['date'],'root':root,'contract':item['contract'],
                          'instrument_id':item['instrument_id'],'request':request,
                          'start_ns':s['start_ns'],'end_ns':s['end_ns'],
                          'records':count,'billable_uncompressed_bytes':size})
    for p in parts:
        value,checked = call('metadata','get_cost',**p['request'])
        p.update(cost_usd=str(money(value)),cost_checked_at=checked,
                 local_quote_expires_at=iso(stamp(checked)+timedelta(minutes=15)))
    per_root = {root: str(sum((money(p['cost_usd']) for p in parts if p['root']==root),Decimal(0))) for root in ('MNQ','MES')}
    total = str(sum((money(p['cost_usd']) for p in parts),Decimal(0)))
    scope = {'dataset':DATASET,'schema':SCHEMA,'partitions':parts,'total_cost_usd':total}
    report = {'status':'official_quote_complete_awaiting_explicit_authorization',
              'generated_at':iso(datetime.now(timezone.utc)), **scope, 'per_root_cost_usd':per_root,
              'scope_sha256':digest(scope),'sessions':ss,'mapping':mapping,'conditions':conditions,
              'dataset_range':ranges,'authentication':auth,'http':backend.trace,
              'http200_count':len(backend.trace),'total_records':sum(p['records'] for p in parts),
              'total_billable_uncompressed_bytes':sum(p['billable_uncompressed_bytes'] for p in parts),
              'local_quote_expires_at':min(p['local_quote_expires_at'] for p in parts),
              'quote_ttl_is_local_safety_policy_not_vendor_price_guarantee':True,
              'selection_rule_source':'https://databento.com/docs/conventions/symbology',
              'selection_rule':'previous-day-volume rank0; fixed raw contracts per cash day, no current-day full-volume selection',
              'retrospective_mapping_is_not_point_in_time_publication_attestation':True,
              'no_roll_in_selected_five_sessions':not mapping['rollovers'],
              'quality':'vendor metadata only; raw data not acquired or validated',
              'download_authorized':False,'data_calls':0,'purchases':0,
              'proposed_manual_cap_usd':'0.02','cap_approved':False,
              'paid_entitlement_license_balance_verified':False,
              'immutability_before':before,'immutability_after':baseline_check(),
              'all_frozen_planner_paths_unchanged':all(file_hash(ROOT/p)==h for p,h in frozen.items())}
    write('quote.json',report)
    print(json.dumps({k:report[k] for k in ('status','generated_at','per_root_cost_usd','total_cost_usd','total_records','total_billable_uncompressed_bytes','http200_count','local_quote_expires_at','scope_sha256','all_frozen_planner_paths_unchanged')}))

try:
    quietly(run)
except Exception:
    if backend is not None:
        write('safe-failure.json',{'status':'failed_closed','http':backend.trace,'responses_persisted':len(responses),'data_calls':0,'purchases':0})
    print(json.dumps({'status':'failed_closed','error':'quote_refresh_failed_without_raw_exception','data_calls':0}))
    raise SystemExit(2)
finally:
    if backend is not None:
        backend.close()
