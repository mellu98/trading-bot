"""One explicitly authorized Databento acquisition, using the existing cache gate."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import csv
import hmac
import json
import os
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import databento as db
import numpy as np
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

from databento_planner.cache import Cache, Identity, atomic_json
from databento_planner.gate import Approval, acquisition_digest, execute_approved
from databento_planner.security import MetadataOnly, PlannerError, load_key, quietly
from mnq_data.core import digest, file_hash, iso

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT/'data/databento'
REPORT = ROOT/'reports/real-simulation'
QUOTE = ROOT/'reports/databento/planning/approval-5sessions-20261026/quote.json'
AUTHORIZATION = Path('/Users/locoframe/.codex/attachments/784e8cc3-b2b5-452e-b095-df9823742b55/Testo incollato.txt')


def validate_authorized_scope(report):
    if report.get('dataset') != 'GLBX.MDP3' or report.get('schema') != 'ohlcv-1m':
        raise ValueError('Unapproved dataset or schema')
    cost = Decimal(report['total_cost_usd'])
    if not cost.is_finite() or not 0 <= cost <= Decimal('0.02'):
        raise ValueError('Authorized aggregate budget exceeded')
    expected = {(f'2026-10-{d}',r) for d in range(19,24) for r in ('MNQ','MES')}
    seen = set()
    for p in report['partitions']:
        key=(p['date'],p['root'])
        req={'dataset':'GLBX.MDP3','schema':'ohlcv-1m','symbols':[p['root']+'Z6'],
             'stype_in':'raw_symbol','start':p['date']+'T13:30:00Z','end':p['date']+'T20:00:00Z'}
        if key not in expected or key in seen or p['contract'] != p['root']+'Z6' or p['request'] != req:
            raise ValueError('Exact authorized cash-session contract scope required')
        seen.add(key)
    if seen != expected:
        raise ValueError('All ten exact partitions required')


class AuthorizedBackend:
    """Official SDK stream with fixed host/scope, TLS, no redirects or retries."""
    def __init__(self,key,requests_by_identity):
        self.key=key
        self.client=quietly(db.Historical,key=key)
        self.meta=MetadataOnly(key,max_requests=30,max_seconds=600)
        self.session=requests.Session()
        self.session.trust_env=False
        self.session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
        self.requests=requests_by_identity
        self.trace=[]
        self.active=None

    def quote(self,p):
        req=self.requests[(p['identity']['contract'],p['start_ns'])]
        value=self.meta.call('metadata','get_cost',**req)
        size=self.meta.call('metadata','get_billable_size',**req)
        return {'cost_usd':str(value),'billable_bytes':size,
                'expires_at':iso(datetime.now(timezone.utc)+timedelta(minutes=15))}

    def _post(self,*args,**kwargs):
        url=kwargs.get('url',args[0] if args else '')
        if url != 'https://hist.databento.com/v0/timeseries.get_range' or self.active is None:
            raise PlannerError('paid_transport_scope_blocked')
        auth=kwargs.get('auth')
        if not isinstance(auth,HTTPBasicAuth) or auth.password != '' or not hmac.compare_digest(auth.username,self.key):
            raise PlannerError('paid_credential_transport_mismatch')
        body=kwargs['data']
        for name,value in self.active.items():
            encoded=','.join(value) if isinstance(value,list) else value
            if str(body.get(name)) != str(encoded):
                raise PlannerError('paid_sdk_request_scope_mismatch')
        if body.get('encoding') != 'dbn' or body.get('compression') != 'zstd':
            raise PlannerError('paid_encoding_mismatch')
        item={'endpoint':'/v0/timeseries.get_range','http_status':None,'contract':self.active['symbols'][0],
              'start':self.active['start'],'end':self.active['end'],'automatic_retry':False}
        self.trace.append(item)
        response=self.session.post(url,data=body,headers=kwargs.get('headers'),auth=auth,
                                   stream=True,timeout=(10,60),verify=True,allow_redirects=False)
        item['http_status']=response.status_code
        if response.status_code != 200:
            response.close()
            raise PlannerError('paid_http_not_200')
        return response

    def acquire(self,p,path):
        self.active=self.requests[(p['identity']['contract'],p['start_ns'])]
        try:
            with patch('databento.common.http.requests.post',self._post):
                quietly(self.client.timeseries.get_range,**self.active,path=path)
            with open(path,'rb') as stream:
                os.fsync(stream.fileno())
        finally:
            self.active=None
            atomic_json(REPORT/'acquisition-http.json',{'data_http':self.trace,'metadata_http':self.meta.trace})

    def close(self):
        self.meta.close()
        self.session.close()


def load_completed(cache):
    job=cache.root/'jobs/authorized-oct19-23-2026'
    if (job/'INCOMPLETE.json').exists():
        raise PlannerError('prior_paid_attempt_incomplete_do_not_retry')
    return job,json.loads((job/'provenance.json').read_text()) if (job/'provenance.json').is_file() else None


def acquire_authorized():
    REPORT.mkdir(parents=True,exist_ok=True)
    cache=Cache(CACHE)
    dest,prior=load_completed(cache)
    if prior is not None:
        return normalize(cache,dest,prior)
    report=json.loads(QUOTE.read_text())
    validate_authorized_scope(report)
    if datetime.now(timezone.utc) >= pd.Timestamp(report['local_quote_expires_at']).to_pydatetime():
        raise PlannerError('fresh_official_quote_required_before_acquisition')
    if not AUTHORIZATION.is_file():
        raise PlannerError('human_authorization_evidence_missing')
    source_hash=digest({k:file_hash(p) for k,p in {
        'core':ROOT/'adapters/databento/src/mnq_data/core.py',
        'local':ROOT/'adapters/databento/src/mnq_data/local.py',
        'cache_validator':ROOT/'adapters/databento_planner/src/databento_planner/cache.py'}.items()})
    parts=[];requests_by_identity={}
    for p in report['partitions']:
        identity=Identity('GLBX.MDP3','ohlcv-1m',p['root'],p['contract'],str(p['instrument_id']),1,'unknown','0.1.0',source_hash)
        parts.append({'identity':identity.as_dict(),'start_ns':p['start_ns'],'end_ns':p['end_ns'],
                      'cost_usd':p['cost_usd'],'billable_bytes':p['billable_uncompressed_bytes'],
                      'quote_expires_at':p['local_quote_expires_at']})
        requests_by_identity[(p['contract'],p['start_ns'])]=p['request']
    job={'dataset':'GLBX.MDP3','schema':'ohlcv-1m','partitions':parts,
         'quote_checked_at':min(p['cost_checked_at'] for p in report['partitions']),
         'quote_expires_at':report['local_quote_expires_at']}
    approval=Approval(acquisition_digest(job),'0.02','user-authorized-784e8cc3-oct19-23-2026')
    atomic_json(REPORT/'human-authorization.json',{'scope':job,'authorization_attachment_sha256':file_hash(AUTHORIZATION),
                'explicit_human_cap_usd':'0.02','approval_digest':approval.request_sha256,
                'no_other_period_schema_or_duplicate_acquisitions_authorized':True})
    key,auth=load_key()
    backend=AuthorizedBackend(key,requests_by_identity)
    try:
        result=execute_approved(job,approval,cache,dest,backend,lambda:datetime.now(timezone.utc),configured_cap='0.02')
    finally:
        backend.close()
    atomic_json(REPORT/'acquisition.json',{'result':result,'authentication':auth,'data_calls':len(backend.trace),
                'billing':'Client-side exact-query estimate; not a vendor-enforced spending guarantee',
                'scope':'Only ten approved per-contract/per-cash-session requests'})
    return normalize(cache,dest,result)


def normalize(cache,dest,result):
    records=[];quality=[]
    for item in result['files']:
        p=item['request'];identity=Identity(**p['identity']);path=dest/item['path']
        provenance={'status':'downloaded_unvalidated','request_complete':True,
            'request':{'dataset':identity.dataset,'schema':identity.schema,'symbols':[identity.contract],
                       'stype_in':'raw_symbol','start_ns':p['start_ns'],'end_ns':p['end_ns']},
            'source':'Databento Historical API','synthetic':False,'sha256':item['sha256']}
        if file_hash(path)!=item['sha256']:
            raise PlannerError('download_hash_changed')
        receipt=cache.register(path,identity,(p['start_ns'],p['end_ns']),provenance)
        rows=db.DBNStore.from_file(path).to_ndarray()
        ts=rows['ts_event'].astype('int64')
        expected=np.arange(p['start_ns'],p['end_ns'],60*10**9,dtype=np.int64)
        if not np.array_equal(ts,expected):
            raise PlannerError('actual_minute_gap_or_timestamp_mismatch')
        if np.any(rows['volume']<=0) or any(np.any(rows[name] % 250000000) for name in ('open','high','low','close')):
            raise PlannerError('actual_volume_or_tick_invalid')
        quality.append({'contract':identity.contract,'date':pd.Timestamp(int(ts[0]),unit='ns',tz='UTC').date().isoformat(),
                        'records':len(rows),'missing_minutes':0,'duplicates':0,'publisher_id':1,
                        'volume_total':int(rows['volume'].sum()),'raw_sha256':item['sha256'],
                        'receipt_sha256':digest(receipt)})
        for r,t in zip(rows,ts):
            records.append({'symbol':identity.root,'contract':identity.contract,'ts_event_ns':int(t),
                'start':pd.Timestamp(int(t),unit='ns',tz='UTC').isoformat(),
                'end':pd.Timestamp(int(t)+60*10**9,unit='ns',tz='UTC').isoformat(),
                'available_at':pd.Timestamp(int(t)+60*10**9,unit='ns',tz='UTC').isoformat(),
                **{name:str(Decimal(int(r[name]))/Decimal(10**9)) for name in ('open','high','low','close')},
                'volume':int(r['volume'])})
    records.sort(key=lambda r:(r['ts_event_ns'],r['symbol']))
    target=REPORT/'bars.csv'
    temporary=REPORT/'bars.csv.tmp'
    with temporary.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,target)
    report={'status':'real_raw_and_normalized_structurally_verified','rows':len(records),
            'bars_csv_sha256':file_hash(target),'partitions':quality,'raw_cache':str(cache.root),
            'timestamp_precision':'original integer UNIX nanoseconds retained',
            'availability':'Bar assumed available at interval end for technical replay; feed latency unmeasured',
            'vwap':'One-minute typical-price volume-weighted approximation, not exact trade VWAP',
            'intrabar':'OHLC cannot resolve event sequence; no execution accuracy claim',
            'news':'No externally verified historical news-blackout calendar; technical-only replay',
            'source_revision':'Vendor correction revision unknown; retrieval provenance retained'}
    atomic_json(REPORT/'data-quality.json',report)
    return report


def completed_attempts(state):
    done={p['partition'] for p in state['completed']}
    if len(done)!=len(state['completed']) or len(set(state['attempted']))!=len(state['attempted']) or set(state['attempted'])!=done:
        raise ValueError('Ambiguous paid attempt: never retry without external billing reconciliation')
    return done


def recover_unattempted_authorized():
    """Resolve only verified-complete scopes; acquire only never-attempted partitions.

    Retain original quarantine evidence. An attempted-but-uncompleted stream is
    never retried. The same original human budget covers prior plus new estimates.
    """
    import shutil
    cache=Cache(CACHE);dest=cache.root/'jobs/authorized-oct19-23-2026'
    state=json.loads((dest/'INCOMPLETE.json').read_text())
    done=completed_attempts(state)
    original=json.loads((REPORT/'human-authorization.json').read_text())['scope']
    if not done < set(range(10)): raise PlannerError('unexpected_recovery_scope')
    held=cache.root/'leases'/(acquisition_digest(original)+'.json')
    for item in state['completed']:
        p=item['request'];path=dest/item['path']
        if file_hash(path)!=item['sha256']: raise PlannerError('completed_raw_corrupt_no_repurchase')
        cache._validate_dbn(path,Identity(**p['identity']),(p['start_ns'],p['end_ns']))
    atomic_json(REPORT/'first-attempt-quarantine.json',state)
    atomic_json(REPORT/'first-attempt-lease.json',json.loads(held.read_text()))
    trace_before=json.loads((REPORT/'acquisition-http.json').read_text())
    atomic_json(REPORT/'acquisition-http-first-attempt.json',trace_before)
    old_quote=json.loads(QUOTE.read_text());validate_authorized_scope(old_quote)
    remaining=[];requests_by_identity={}
    key,auth=load_key();backend=AuthorizedBackend(key,requests_by_identity)
    try:
        for i,p in enumerate(original['partitions']):
            if i in done: continue
            source=old_quote['partitions'][i]
            if (source['contract'],source['start_ns'])!=(p['identity']['contract'],p['start_ns']):
                raise PlannerError('recovery_partition_identity_mismatch')
            requests_by_identity[(source['contract'],source['start_ns'])]=source['request']
            fresh=backend.quote(p)
            remaining.append({**p,'cost_usd':fresh['cost_usd'],'billable_bytes':fresh['billable_bytes'],
                              'quote_expires_at':fresh['expires_at']})
        prior_cost=sum((Decimal(p['fresh_estimated_cost_usd']) for p in state['completed']),Decimal(0))
        budget=Decimal('0.02')-prior_cost
        if sum((Decimal(p['cost_usd']) for p in remaining),Decimal(0))>budget:
            raise PlannerError('remaining_aggregate_human_budget_exceeded')
        job={'dataset':'GLBX.MDP3','schema':'ohlcv-1m','partitions':remaining,
             'quote_checked_at':iso(datetime.now(timezone.utc)),
             'quote_expires_at':min(p['quote_expires_at'] for p in remaining)}
        approval=Approval(acquisition_digest(job),str(budget),'user-784e8cc3-only-never-attempted-remainder')
        with cache.lock():
            if json.loads((dest/'INCOMPLETE.json').read_text())!=state:
                raise PlannerError('recovery_state_changed')
            atomic_json(held,{'status':'locally_validated_completed_partition_scopes',
                'request_sha256':acquisition_digest(original),
                'scope':[{'identity':p['identity'],'start_ns':p['start_ns'],'end_ns':p['end_ns']}
                         for i,p in enumerate(original['partitions']) if i in done],
                'resolution':'Only verified completed scopes retained; never-attempted scopes released',
                'evidence_sha256':file_hash(REPORT/'first-attempt-quarantine.json')})
        atomic_json(REPORT/'remaining-authorization.json',{'job':job,'prior_estimated_cost_usd':str(prior_cost),
            'remaining_original_budget_usd':str(budget),'original_human_cap_usd':'0.02'})
        result=execute_approved(job,approval,cache,cache.root/'jobs/authorized-oct19-23-2026-remainder',
                                backend,lambda:datetime.now(timezone.utc),configured_cap=str(budget))
        combined=list(state['completed'])
        for i,item in zip(sorted(set(range(10))-done),result['files']):
            source=cache.root/'jobs/authorized-oct19-23-2026-remainder'/item['path']
            target=dest/(str(i)+'.dbn.zst')
            with source.open('rb') as reader,target.open('xb') as writer:
                shutil.copyfileobj(reader,writer);writer.flush();os.fsync(writer.fileno())
            if file_hash(target)!=item['sha256']: raise PlannerError('recovered_copy_checksum_mismatch')
            combined.append({**item,'partition':i,'path':target.name})
        final={**result,'files':sorted(combined,key=lambda x:x['partition']),
               'estimated_cost_usd':str(prior_cost+Decimal(result['estimated_cost_usd'])),
               'original_authorization_cap_usd':'0.02','recovery':'No paid partition retried; verified complete raw files retained'}
        atomic_json(dest/'provenance.json',final)
        (dest/'INCOMPLETE.json').unlink()
        atomic_json(REPORT/'acquisition-http.json',{'data_http':trace_before['data_http']+backend.trace,
                    'metadata_http':trace_before['metadata_http']+backend.meta.trace})
        atomic_json(REPORT/'acquisition.json',{'result':final,'authentication':auth,
                    'unique_data_requests':len(final['files']),'no_duplicate_paid_scopes':True})
        return normalize(cache,dest,final)
    finally: backend.close()
