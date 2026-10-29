"""Completed NY cash research sessions, not full CME Globex sessions."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
import re

import exchange_calendars as xcals
import pandas as pd
from mnq_data.core import Adapter, Plan, digest, iso, utc, file_hash
from pathlib import Path
from .checkpoints import StudyBackend, BatchComplete
from .security import PlannerError

DATASET='GLBX.MDP3'
SCHEMA='ohlcv-1m'
ROOTS=('MNQ','MES')
SAMPLES=(1,5,20,60)


def stamp(value):
    try: return utc(value)
    except Exception: raise PlannerError('invalid_aware_timestamp') from None


def money(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):
        raise PlannerError('invalid_cost_quote')
    try: out=Decimal(str(value))
    except InvalidOperation: raise PlannerError('invalid_cost_quote') from None
    if not out.is_finite() or out<0: raise PlannerError('invalid_cost_quote')
    return out


def sessions(as_of, count=60):
    now=stamp(as_of)
    if type(count) is not int or not 1<=count<=1000:
        raise PlannerError('invalid_session_count')
    # XNYS supplies cash holidays/half days and timezone transitions, NOT a CME calendar.
    cal=xcals.get_calendar('XNYS',start=(now-pd.Timedelta(days=count*3+30)).date(),
                           end=(now+pd.Timedelta(days=3)).date(),side='left')
    completed=cal.schedule[cal.schedule['close']<=now].tail(count)
    if len(completed)!=count: raise PlannerError('insufficient_calendar_history')
    return [{'date':str(day.date()),'start':iso(row['open']),'end':iso(row['close']),
             'start_ns':int(row['open'].value),'end_ns':int(row['close'].value),
             'expected_minutes':int((row['close']-row['open']).total_seconds()//60)}
            for day,row in completed.iterrows()]


def validate_conditions(values, dates):
    if not isinstance(values,list): raise PlannerError('conditions_invalid')
    selected=[]
    for day in dates:
        hits=[x for x in values if isinstance(x,dict) and x.get('date')==day]
        if len(hits)!=1: raise PlannerError('conditions_missing_or_conflicting')
        condition=hits[0].get('condition')
        if condition not in ('available',):
            raise PlannerError('conditions_'+condition if condition in ('degraded','unavailable') else 'conditions_unknown')
        selected.append(hits[0])
    return selected


def request_for(session, root, mapping):
    hits=[x for x in mapping['intervals'] if x['root']==root and x['start_date']<=session['date']<x['end_date']]
    if len(hits)!=1: raise PlannerError('incomplete_contract_mapping')
    item=hits[0]
    if not re.fullmatch(root+r'[HMUZ]\d{1,2}',item['contract']):
        raise PlannerError('non_outright_contract')
    # Existing parser validates exact ns and OHLCV alignment, but quote actual raw identity.
    plan=Plan(session['start'],session['end'],(root,),(SCHEMA,))
    req=plan.request(root,SCHEMA)
    req.update(symbols=[item['contract']],stype_in='raw_symbol')
    return req,item


def comparison(backend, as_of, now=None, checkpoint=None, max_calls=None):
    ss=sessions(as_of,60)
    snapshot={'dataset':DATASET,'schema':SCHEMA,'roots':list(ROOTS),'sessions':ss,
              'sdk':version('databento'),'calendar':version('exchange-calendars'),
              'source':{name:file_hash(Path(__file__).with_name(name)) for name in ('planner.py','checkpoints.py')},
              'provider_revision':'frozen_discovery_snapshot_not_latest_attestation'}
    backend=StudyBackend(backend,snapshot,checkpoint,max_calls,now)
    a=ss[0]['date']; b=(pd.Timestamp(ss[-1]['date'])+pd.Timedelta(days=1)).date().isoformat()
    ranges=mapping=conditions=None;parts=[];requests=[];discovery_complete=False
    try:
        available=backend.call('metadata','list_schemas',dataset=DATASET)
        if SCHEMA not in available: raise PlannerError('schema_unavailable')
        ranges=backend.call('metadata','get_dataset_range',dataset=DATASET)
        r=ranges.get('schema',{}).get(SCHEMA)
        if not r or stamp(ss[0]['start'])<stamp(r['start']) or stamp(ss[-1]['end'])>stamp(r['end']):
            raise PlannerError('outside_schema_range')
        try: mapping=Adapter(backend).resolve(ROOTS,a,b,'v')
        except BatchComplete: raise
        except Exception: raise PlannerError('mapping_resolution_failed') from None
        if any(mapping.get(k) for k in ('partial','not_found','raw_partial','raw_not_found','rejected')):
            raise PlannerError('incomplete_contract_mapping')
        requests=[(s,root,*request_for(s,root,mapping)) for s in reversed(ss) for root in ROOTS]
        conditions=validate_conditions(backend.call('metadata','get_dataset_condition',
            dataset=DATASET,start_date=a,end_date=b),[x['date'] for x in ss])
        discovery_complete=True
        backend.revision=digest({'mapping':mapping,'conditions':conditions,'ranges':ranges})
        for session,root,request,item in requests:
            cost=money(backend.call('metadata','get_cost',**request))
            size=backend.call('metadata','get_billable_size',**request)
            count=backend.call('metadata','get_record_count',**request)
            if any(type(x) is not int or x<0 for x in (size,count)):
                raise PlannerError('invalid_size_or_count')
            if count==0: raise PlannerError('empty_required_session')
            if count>session['expected_minutes']: raise PlannerError('record_count_exceeds_single_contract_grid')
            metrics={name:backend.evidence(name,request) for name in ('get_cost','get_billable_size','get_record_count')}
            parts.append({'date':session['date'],'root':root,'schema':SCHEMA,'contract':item['contract'],
                'instrument_id':item['instrument_id'],'request':request,'request_sha256':digest(request),
                'start_ns':session['start_ns'],'end_ns':session['end_ns'],
                'estimated_cost_usd':str(cost),'records':count,'billable_uncompressed_bytes':size,
                'expected_minutes':session['expected_minutes'],'metric_evidence':metrics,
                'count_matches_minute_grid':count==session['expected_minutes'],
                'actual_gap_free_quality':'not_acquired_not_verified'})
    except BatchComplete: pass
    generated=stamp(backend.clock())
    evidence=[m for p in parts for m in p['metric_evidence'].values()]
    checked=min((stamp(m['checked_at']) for m in evidence),default=generated)
    expires=min((stamp(m['expires_at']) for m in evidence),default=generated)
    for p in parts:
        p['quote_age_seconds']=(generated-stamp(p['metric_evidence']['get_cost']['checked_at'])).total_seconds()
    scenarios={}
    for days in SAMPLES:
        selected=ss[-days:]; dates={x['date'] for x in selected};roots={}
        for root in ROOTS:
            ps=[p for p in parts if p['date'] in dates and p['root']==root];ready=len(ps)==days
            roots[root]={'cost_usd':str(sum((money(p['estimated_cost_usd']) for p in ps),Decimal(0))) if ready else None,
                         'records':sum(p['records'] for p in ps) if ready else None,
                         'billable_uncompressed_bytes':sum(p['billable_uncompressed_bytes'] for p in ps) if ready else None,
                         'expected_minutes':sum(s['expected_minutes'] for s in selected),
                         'completed_partitions':len(ps)}
        ready=all(v['completed_partitions']==days for v in roots.values())
        scenarios[str(days)]={'sessions':days,'first_session':selected[0]['date'],'last_session':selected[-1]['date'],
            'roots':roots,'status':'complete' if ready else 'unknown_partial',
            'total_cost_usd':str(sum((money(v['cost_usd']) for v in roots.values()),Decimal(0))) if ready else None,
            'total_records':sum(v['records'] for v in roots.values()) if ready else None,
            'total_billable_uncompressed_bytes':sum(v['billable_uncompressed_bytes'] for v in roots.values()) if ready else None,
            'abc_ready':False}
    complete=discovery_complete and len(parts)==120
    return {'status':'verified_metadata' if complete else 'partial_metadata','preflight_passed':complete,'as_of':iso(stamp(as_of)),
        'checked_at':iso(checked),'expires_at':iso(expires),'generated_at':iso(generated),'dataset':DATASET,'schema':SCHEMA,
        'acquisition_quotes_all_current':complete and generated<expires,
        'historical_study_estimates_may_be_expired':True,'checkpoint_snapshot_sha256':backend.snapshot,
        'checkpoint_values_loaded':len(backend.entries),'new_metadata_calls':backend.calls,'reused_metadata_values':backend.reused,
        'http_evidence':{'checkpoint_responses':len(backend.entries),'all_observed_http200':all(e.get('http_status')==200 for e in backend.entries.values())},
        'sdk_version':version('databento'),'dbn_version':version('databento-dbn'),
        'calendar':{'library':'exchange_calendars','version':version('exchange-calendars'),
            'name':'XNYS','side':'left','scope':'09:30 NY to actual cash close; not full Globex',
            'timezone':'America/New_York','official_cash_validation':'https://www.nyse.com/trade/hours-calendars',
            'separate_globex_crosscheck':'https://www.cmegroup.com/trading-hours.html'},
        'sessions':ss,'mapping':mapping,'mapping_sha256':digest(mapping) if mapping is not None else None,'dataset_range':ranges,
        'conditions':conditions,'conditions_end_date_defensive_next_day':b,
        'partitions':parts,'scenarios':scenarios,'request_set_sha256':digest([p['request'] for p in parts]),
        'download_authorized':False,'data_acquisition_calls':0,'cache_actual_objects':0,
        'quality':'vendor_conditions_and_counts_only; no raw data acquired or validated',
        'entitlements':'actual metadata requests accepted; paid acquisition, license terms and balance not tested',
        'quote_size_note':'Uncompressed billable bytes, not compressed disk/download bytes.',
        'cap':{'default_max_usd':'0','approved_budget':False,'vendor_hard_spending_cap':False},
        'tier2':{'schemas':['ohlcv-1s','mbp-1'],'status':'configured_only_not_quoted',
                 'bid_ask':'BBO/execution validation; preserve event and receive clocks; no quote-volume inference',
                 'requires_new_scope_quote_and_manual_approval':True},
        'recommendation':{'minimum_useful_technical_sample_sessions':5,'cheapest_smoke_sessions':1,
            'abc_minimum_joint_sessions':70,'both_statistical_count_floors_sessions':90,
            'all_current_scenarios_insufficient_for_default_abc':True,
            'no_performance_or_signal_guarantee':True},
        'roll_note':'Provider previous-day volume rank0; concrete instrument ID/raw contract preserved. No back adjustment, spread, guessed year, or universal third-Friday expiry.'}
