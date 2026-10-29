"""Authorized115-session acquisition and integrity cache; no trading functions."""
from datetime import datetime, timezone
from decimal import Decimal
import csv
import json
import os
from pathlib import Path
import re
from unittest.mock import patch

import databento as db
import numpy as np
import pandas as pd

from databento_planner.cache import Cache, atomic_json
from databento_planner.planner import sessions, request_for, validate_conditions, money, stamp
from databento_planner.security import MetadataOnly, load_key, quietly, PlannerError
from mnq_data.core import Adapter, file_hash, digest, iso
from .acquire import ROOT, CACHE, REPORT, AuthorizedBackend, normalize

OUT=ROOT/'reports/quant-validation'
RAW=CACHE/'bulk120'
EXCLUDED={f'2026-10-{d}' for d in range(19,24)}
CALENDAR=sessions('2026-10-24T00:00:00Z',120)
BOUNDS={s['date']:s for s in CALENDAR}


def validate_request(req):
    date=req.get('start','')[:10]
    if date not in BOUNDS or date in EXCLUDED:raise ValueError('Outside authorized missing115-session scope')
    s=BOUNDS[date]
    if req.get('dataset')!='GLBX.MDP3' or req.get('schema')!='ohlcv-1m' or req.get('stype_in')!='raw_symbol':
        raise ValueError('Unapproved dataset/schema/symbology')
    if req.get('start')!=s['start'] or req.get('end')!=s['end'] or set(req)!={'dataset','schema','symbols','stype_in','start','end'}:
        raise ValueError('Exact cash interval required')
    symbols=req['symbols']
    if not isinstance(symbols,list) or len(symbols)!=2 or not re.fullmatch(r'MNQ[HMUZ]6',symbols[0]) or not re.fullmatch(r'MES[HMUZ]6',symbols[1]):
        raise ValueError('Exactly MNQ/MES dated2026 outrights required')


def authorize_total(reserved,new):
    try:a,b=money(reserved),money(new)
    except PlannerError:raise ValueError('Invalid finite cost') from None
    if a+b>Decimal('0.50'):raise ValueError('Aggregate authorized USD0.50 exceeded')


def prepare():
    """Bounded resumable free requests; never reuse an expired quote for acquisition."""
    OUT.mkdir(parents=True,exist_ok=True)
    state_path=OUT/'preflight-responses.json'
    entries=json.loads(state_path.read_text()) if state_path.exists() else {}
    key,auth=load_key();backend=MetadataOnly(key,max_requests=45,max_seconds=210)
    def call(area,name,**req):
        k=digest({'area':area,'name':name,'request':req})
        if k in entries:return entries[k]['value']
        value=backend.call(area,name,**req)
        entries[k]={'area':area,'name':name,'request':req,'value':value,
                    'checked_at':iso(datetime.now(timezone.utc)),'http_status':backend.trace[-1]['http_status']}
        atomic_json(state_path,entries)
        return value
    try:
        if 'ohlcv-1m' not in call('metadata','list_schemas',dataset='GLBX.MDP3'):raise ValueError('Schema unavailable')
        ranges=call('metadata','get_dataset_range',dataset='GLBX.MDP3')['schema']['ohlcv-1m']
        if stamp(ranges['start'])>stamp(CALENDAR[0]['start']) or stamp(ranges['end'])<stamp(CALENDAR[-1]['end']):raise ValueError('Range unavailable')
        class Resolver:
            def call(self,area,name,**req):return call(area,name,**req)
        mapping=Adapter(Resolver()).resolve(('MNQ','MES'),'2026-05-05','2026-10-24','v')
        if any(mapping.get(k) for k in ('partial','not_found','raw_partial','raw_not_found','rejected')):raise ValueError('Mapping incomplete')
        conditions=validate_conditions(call('metadata','get_dataset_condition',dataset='GLBX.MDP3',start_date='2026-05-05',end_date='2026-10-24'),list(BOUNDS))
        parts=[]
        for s in CALENDAR:
            if s['date'] in EXCLUDED:continue
            req,a=request_for(s,'MNQ',mapping);_,b=request_for(s,'MES',mapping)
            req['symbols']=[a['contract'],b['contract']];validate_request(req)
            value=call('metadata','get_cost',**req)
            parts.append({'date':s['date'],'request':req,'identities':[a,b],
                          'estimated_cost_usd':str(money(value)),'expected_minutes':s['expected_minutes']})
        total=sum((money(p['estimated_cost_usd']) for p in parts),Decimal(0));authorize_total('0',total)
        result={'status':'verified_official_missing115_quote','generated_at':iso(datetime.now(timezone.utc)),
          'total_cost_usd':str(total),'parts':parts,'mapping':mapping,'conditions':conditions,
          'authentication':auth,'http200_count':len(entries),'excluded_dates':sorted(EXCLUDED),
          'human_authorization':'User MISSIONE VALIDAZIONE QUANTITATIVA COMPLETA, GLBX.MDP3ohlcv1mMay5-Oct23cash; original five dates excluded; capUSD0.50',
          'cap_usd':'0.50','source_revision':'Vendor corrections/publication latency unknown; lagged previous-day-volume rule documented',
          'download_authorized_for_exact_scope_only':True}
        atomic_json(OUT/'quote115.json',result)
        return result
    finally:
        atomic_json(OUT/'last-free-batch.json',{'http':backend.trace,'persisted':len(entries),'data_calls':0})
        backend.close()


def validate_group(path,part):
    """Validate original multi-contract DBN bytes before any lossy conversion."""
    store=db.DBNStore.from_file(path);req=part['request'];s=BOUNDS[part['date']]
    if (store.dataset!='GLBX.MDP3' or str(store.schema)!='ohlcv-1m' or str(store.stype_in)!='raw_symbol'
      or str(store.stype_out)!='instrument_id' or set(store.symbols)!=set(req['symbols'])
      or store.start.value!=s['start_ns'] or store.end.value!=s['end_ns'] or store.limit not in (None,0)
      or store.metadata.partial or store.metadata.not_found):raise ValueError('Original DBN metadata mismatch')
    rows=store.to_ndarray();expected_ids={int(i['instrument_id']) for i in part['identities']}
    if set(map(int,rows['instrument_id']))!=expected_ids or np.any(rows['publisher_id']!=1):raise ValueError('Publisher/instrument mismatch')
    checks=[]
    for identity in part['identities']:
        rr=rows[rows['instrument_id']==int(identity['instrument_id'])]
        ts=rr['ts_event'].astype('int64');expected=np.arange(s['start_ns'],s['end_ns'],60*10**9,dtype=np.int64)
        if not np.array_equal(ts,expected):raise ValueError('Minute gaps/duplicates/order/session bounds')
        for name in ('open','high','low','close'):
            if np.any(rr[name]<=0) or np.any(rr[name]>=2**63-1) or np.any(rr[name]%250000000):raise ValueError('Invalid OHLC/tick')
        if np.any(rr['low']>rr['high']) or any(np.any(rr['low']>rr[n]) or np.any(rr['high']<rr[n]) for n in ('open','close')):raise ValueError('Invalid OHLC')
        if np.any(rr['volume']<=0):raise ValueError('Invalid futures volume')
        checks.append({'root':identity['root'],'contract':identity['contract'],'instrument_id':identity['instrument_id'],
                       'records':len(rr),'missing_minutes':0,'duplicates':0,'volume_total':int(rr['volume'].sum())})
    return rows,checks


def acquire_batch(limit=15):
    """Durable single acquisition ledger: attempted-but-incomplete never retried."""
    RAW.mkdir(parents=True,exist_ok=True);cache=Cache(CACHE)
    quote=json.loads((OUT/'quote115.json').read_text());parts=quote['parts']
    if len(parts)!=115 or len({p['date'] for p in parts})!=115:raise ValueError('115 exact dates required')
    for p in parts:validate_request(p['request'])
    authorize_total('0',quote['total_cost_usd'])
    ledger_path=RAW/'ledger.json';ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {
        'scope_sha256':digest([p['request'] for p in parts]),'human_cap_usd':'0.50','entries':{}}
    if ledger['scope_sha256']!=digest([p['request'] for p in parts]):raise ValueError('Authorization scope changed')
    reserved=sum((money(e['cost_reserved_usd']) for e in ledger['entries'].values()),Decimal(0))
    key,auth=load_key();backend=AuthorizedBackend(key,{})
    backend.meta.close();backend.meta=MetadataOnly(key,max_requests=25,max_seconds=600)
    done=0
    try:
        with cache.lock():
            for p in parts:
                k=digest(p['request']);prior=ledger['entries'].get(k);path=RAW/(p['date']+'.dbn.zst')
                if prior:
                    if prior['status']!='complete':raise ValueError('Ambiguous prior paid attempt; no retry')
                    if file_hash(path)!=prior['sha256']:raise ValueError('Raw cache corruption; no repurchase')
                    continue
                if path.exists():raise ValueError('Orphan raw object; manual local reconciliation required')
                fresh=backend.meta.call('metadata','get_cost',**p['request']);cost=money(fresh)
                remaining=sum((money(x['estimated_cost_usd']) for x in parts if digest(x['request']) not in ledger['entries'] and x['date']!=p['date']),Decimal(0))
                authorize_total(reserved,cost+remaining)
                # Reserve the full estimate before the only potentially charged call.
                entry={'status':'attempted_no_automatic_retry','request':p['request'],'cost_reserved_usd':str(cost),
                       'cost_checked_at':iso(datetime.now(timezone.utc)),'automatic_paid_retry':False}
                ledger['entries'][k]=entry;atomic_json(ledger_path,ledger);reserved+=cost
                backend.active=p['request']
                try:
                    with patch('databento.common.http.requests.post',backend._post):
                        quietly(backend.client.timeseries.get_range,**p['request'],path=path)
                    with path.open('rb') as stream:os.fsync(stream.fileno())
                finally:
                    backend.active=None
                    atomic_json(OUT/'last-acquisition-http.json',{'http':backend.trace,'authentication':auth})
                rows,checks=validate_group(path,p)
                entry.update(status='complete',sha256=file_hash(path),bytes=path.stat().st_size,
                             checks=checks,http_status=backend.trace[-1]['http_status'],completed_at=iso(datetime.now(timezone.utc)))
                atomic_json(ledger_path,ledger);done+=1
                if done>=limit:break
        return {'status':'complete' if len(ledger['entries'])==115 and all(e['status']=='complete' for e in ledger['entries'].values()) else 'partial',
                'completed':sum(e['status']=='complete' for e in ledger['entries'].values()),'new_data_calls':done,
                'reserved_cost_usd':str(reserved),'no_duplicate_paid_queries':True}
    finally:backend.close()


def dataset():
    """Combine actual validated raw115 sessions with the original five cache hits."""
    quote=json.loads((OUT/'quote115.json').read_text());ledger=json.loads((RAW/'ledger.json').read_text())
    if len(ledger['entries'])!=115 or any(e['status']!='complete' for e in ledger['entries'].values()):raise ValueError('Real data acquisition incomplete')
    # Revalidate the original cache without network; never relabel a synthetic dataset.
    original=CACHE/'jobs/authorized-oct19-23-2026'
    normalize(Cache(CACHE),original,json.loads((original/'provenance.json').read_text()))
    with (REPORT/'bars.csv').open(newline='') as stream:records=list(csv.DictReader(stream))
    checks=[]
    for p in quote['parts']:
        path=RAW/(p['date']+'.dbn.zst');entry=ledger['entries'][digest(p['request'])]
        if file_hash(path)!=entry['sha256']:raise ValueError('Raw hash changed')
        rows,facts=validate_group(path,p);checks.append({'date':p['date'],'sha256':entry['sha256'],'contracts':facts})
        byid={int(i['instrument_id']):i for i in p['identities']}
        for r in rows:
            t=int(r['ts_event'].astype('int64'));i=byid[int(r['instrument_id'])]
            records.append({'symbol':i['root'],'contract':i['contract'],'ts_event_ns':str(t),
                'start':pd.Timestamp(t,unit='ns',tz='UTC').isoformat(),'end':pd.Timestamp(t+60*10**9,unit='ns',tz='UTC').isoformat(),
                'available_at':pd.Timestamp(t+60*10**9,unit='ns',tz='UTC').isoformat(),
                **{n:str(Decimal(int(r[n]))/Decimal(10**9)) for n in ('open','high','low','close')},'volume':str(int(r['volume']))})
    records.sort(key=lambda r:(int(r['ts_event_ns']),r['symbol']))
    target=OUT/'bars120.csv';temporary=target.with_suffix('.tmp')
    with temporary.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,target)
    result={'status':'real120_sessions_structurally_verified','rows':len(records),'sessions':120,'raw_new115_sessions':checks,
            'original5_cache_hits':sorted(EXCLUDED),'csv_sha256':file_hash(target),'timestamp':'UNIX integer ns retained',
            'new_paid_requests':115,'estimated_reserved_usd':str(sum((money(e['cost_reserved_usd']) for e in ledger['entries'].values()),Decimal(0))),
            'mapping':quote['mapping'],'quality':'Exact minute grid per actual contract, OHLC/ticks/positive volumes/publisher1/hash verified',
            'not_claimed':'Tick-level fills, certified point-in-time news or vendor correction history'}
    atomic_json(OUT/'data-quality120.json',result)
    return result


if __name__=='__main__':
    import sys
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    try:
        if action=='prepare':result=quietly(prepare);result={k:result[k] for k in ('status','total_cost_usd','http200_count')}
        elif action=='acquire':result=quietly(acquire_batch)
        elif action=='dataset':result=quietly(dataset);result={k:result[k] for k in ('status','rows','sessions','estimated_reserved_usd')}
        else:raise ValueError('Use prepare, acquire or dataset')
        print(json.dumps(result))
    except Exception:
        print(json.dumps({'status':'failed_closed','action':action,'no_automatic_paid_retry':True}))
        sys.exit(3)
