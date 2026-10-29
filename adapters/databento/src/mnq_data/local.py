"""Lossless clock/fixed-price normalization and deliberately non-attested staging."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from numbers import Integral
from pathlib import Path
import csv
import json
import math
import re
from databento import Publisher
from .core import SafeError, SCHEMAS, ROOTS, utc, iso, dump, file_hash, safe_call

UNDEF_PRICE=9223372036854775807
SCALE=10**9
TICK=250_000_000
GLBX_PUBLISHER_ID=Publisher.GLBX_MDP3_GLBX.to_int()

def integer(value):
    if isinstance(value,bool) or not isinstance(value,Integral): raise SafeError('integer_required')
    return int(value)

def price(value, nullable=False):
    value=integer(value)
    if value==UNDEF_PRICE:
        if nullable: return None
        raise SafeError('undefined_price')
    if value<=0 or value%TICK: raise SafeError('invalid_price_or_tick')
    return str(Decimal(value)/SCALE)

def ns_date(value): return datetime.fromtimestamp(value//SCALE,timezone.utc).date().isoformat()
def ns_iso(value):
    seconds, nanos=divmod(integer(value),SCALE)
    base=datetime.fromtimestamp(seconds,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    return base+(f'.{nanos:09d}'.rstrip('0') if nanos else '')+'Z'
def ns_utc(value):
    # Shared input validation must precede parsing; never pass through datetime.
    return utc(value).value


def requested_bar_gaps(rows, mappings, request, interval):
    start,end=ns_utc(request['start']),ns_utc(request['end'])
    if start>=end or start%interval or end%interval: raise SafeError('unaligned_ohlcv_request')
    symbols=request.get('symbols',[])
    if len(symbols)!=1 or symbols[0] not in [r+'.v.0' for r in ROOTS]: raise SafeError('ambiguous_ohlcv_partition')
    root=symbols[0].split('.')[0]
    segments=[]; boundaries={start,end}
    for m in mappings:
        if m['root']!=root: continue
        a=max(start,ns_utc(m['start_date']+'T00:00:00Z'))
        b=min(end,ns_utc(m['end_date']+'T00:00:00Z'))
        if a<b: segments.append((a,b,m)); boundaries.update((a,b))
    observed=sorted({int(r['ts_event_ns']) for r in rows})
    missing=[]; cursor=start
    for stamp in observed:
        if stamp>cursor: missing.append((cursor,stamp))
        cursor=max(cursor,stamp+interval)
    if cursor<end: missing.append((cursor,end))
    gaps=[]
    for a,b in missing:
        cuts=sorted({a,b}|{t for t in boundaries if a<t<b})
        for left,right in zip(cuts,cuts[1:]):
            matches=[m for x,y,m in segments if x<=left<y]
            mapping=matches[0] if len(matches)==1 else None
            gaps.append({'symbol':root,'contract':mapping['contract'] if mapping else None,'instrument_id':mapping['instrument_id'] if mapping else None,'mapping_status':'verified' if mapping else ('unmapped' if not matches else 'ambiguous'),'start_ns':str(left),'end_ns':str(right),'absent_intervals':(right-left)//interval,'classification':'unknown_no_trade_or_closure_or_loss'})
    return gaps, (end-start)//interval


def normalize_rows(schema, records, mappings, request=None):
    if schema not in SCHEMAS: raise SafeError('unsupported_schema')
    result=[]; seen=set(); prev_bar={}; prev_exchange={}; prev_receive={}
    interval=(60 if schema=='ohlcv-1m' else 1)*SCALE
    if request:
        start,end=ns_utc(request['start']),ns_utc(request['end'])
        if start>=end: raise SafeError('invalid_historical_interval')
        if schema.startswith('ohlcv'): requested_bar_gaps([],mappings,request,interval)
    q={'schema':schema,'total_records':0,'valid_records':0,'invalid_records':0,'errors':{},'gaps':[],'exchange_clock_regressions':0,'receive_clock_regressions':0,'suspect_timestamp_flags':0,'suspect_book_flags':0,'timestamp_timezone':'UTC','nanoseconds_preserved':True,'gap_calendar_verified':False,'requested_grid_complete':None,'gap_inventory_scope':'requested_ohlcv_interval' if request and schema.startswith('ohlcv') else ('observed_ohlcv_interior_only' if schema.startswith('ohlcv') else 'not_applicable_event_stream'),'gap_note':'No records are synthesized. Missing OHLCV bars may mean no trades, exchange closure, or loss. No authoritative session calendar was supplied.'}
    for rec in records:
        q['total_records']+=1
        try:
            publisher=integer(rec['publisher_id'])
            if publisher!=GLBX_PUBLISHER_ID: raise SafeError('foreign_publisher')
            ts=integer(rec['ts_event']); instrument=str(integer(rec['instrument_id']))
            recv=integer(rec['ts_recv']) if schema in ('trades','mbp-1') else None
            clock=ts if recv is None else recv
            if ts<=0 or clock<=0: raise SafeError('invalid_timestamp')
            if request and not start<=clock<end: raise SafeError('outside_requested_interval')
            day=ns_date(clock)
            hits=[m for m in mappings if m['instrument_id']==instrument and m['start_date']<=day<m['end_date']]
            if len(hits)!=1: raise SafeError('unknown_or_ambiguous_contract')
            m=hits[0]
            if m['root'] not in ROOTS: raise SafeError('unsupported_root')
            if not re.fullmatch(m['root']+r'[HMUZ]\d{1,2}',m['contract']): raise SafeError('invalid_actual_quarter_contract')
            if request and request.get('symbols') != [m['root']+'.v.0']: raise SafeError('partition_contract_mismatch')
            row={'symbol':m['root'],'contract':m['contract'],'instrument_id':instrument,'publisher_id':publisher,'ts_event_ns':str(ts)}
            key=(m['root'],instrument)
            if schema.startswith('ohlcv'):
                interval=(60 if schema=='ohlcv-1m' else 1)*SCALE
                if ts%interval: raise SafeError('bar_timestamp_misaligned')
                prices={k:price(rec[k]) for k in ('open','high','low','close')}
                volume=integer(rec['volume'])
                if volume<=0: raise SafeError('invalid_volume')
                if not Decimal(prices['low'])<=min(Decimal(prices['open']),Decimal(prices['close']))<=max(Decimal(prices['open']),Decimal(prices['close']))<=Decimal(prices['high']): raise SafeError('invalid_ohlc')
                unique=(instrument,ts)
                if unique in seen: raise SafeError('duplicate_bar')
                old=prev_bar.get(key)
                if old is not None and ts<=old: raise SafeError('nonchronological_bars')
                if old is not None and ts>old+interval: q['gaps'].append({'symbol':m['root'],'contract':m['contract'],'after_ns':str(old),'before_ns':str(ts),'absent_intervals':(ts-old)//interval-1,'classification':'unknown_no_trade_or_closure_or_loss'})
                row.update(prices,volume=volume,interval_seconds=interval//SCALE,end_ns=str(ts+interval))
                prev_bar[key]=ts; seen.add(unique)
            else:
                size=integer(rec['size']); flags=integer(rec.get('flags',0))
                if size<0: raise SafeError('negative_event_size')
                action=rec.get('action'); action=action.decode('ascii') if isinstance(action,bytes) else str(action)
                side=rec.get('side'); side=side.decode('ascii') if isinstance(side,bytes) else str(side)
                row.update(ts_recv_ns=str(recv),price=price(rec['price'],nullable=schema=='mbp-1'),size=size,action=action,side=side,flags=flags,sequence=integer(rec.get('sequence',0)),ts_in_delta=integer(rec.get('ts_in_delta',0)))
                if schema=='trades' and (size==0 or action!='T'): raise SafeError('invalid_trade')
                if schema=='mbp-1':
                    for field in ('bid_px_00','ask_px_00'): row[field]=price(rec[field],nullable=True)
                    for field in ('bid_sz_00','ask_sz_00','bid_ct_00','ask_ct_00'):
                        row[field]=integer(rec.get(field,0))
                        if row[field]<0: raise SafeError('negative_book_size')
                    if row['bid_px_00'] is not None and row['ask_px_00'] is not None and Decimal(row['bid_px_00'])>Decimal(row['ask_px_00']): row['crossed_book']=True
                if key in prev_exchange and ts<prev_exchange[key]: q['exchange_clock_regressions']+=1
                if key in prev_receive and recv<prev_receive[key]: q['receive_clock_regressions']+=1
                prev_exchange[key]=ts; prev_receive[key]=recv
                q['suspect_timestamp_flags']+=bool(flags&8); q['suspect_book_flags']+=bool(flags&4)
            result.append(row)
        except (SafeError,KeyError,TypeError,ValueError,OverflowError,OSError) as exc:
            code=str(exc) if isinstance(exc,SafeError) else 'malformed_record'
            q['invalid_records']+=1; q['errors'][code]=q['errors'].get(code,0)+1
    if request and schema.startswith('ohlcv'):
        q['gaps'],q['expected_interval_starts']=requested_bar_gaps(result,mappings,request,interval)
        q['requested_grid_complete']=not q['gaps'] and not q['invalid_records']
    q['valid_records']=len(result)
    q['status']='empty_partition' if not q['total_records'] else ('failed' if q['invalid_records'] else ('passed_with_unverified_gaps' if q['gaps'] else 'structural_checks_passed'))
    return result,q

def stage_abc(rows, destination, bar_latency_ms):
    if bar_latency_ms is None: raise SafeError('explicit_bar_publication_latency_assumption_required')
    if isinstance(bar_latency_ms,bool) or not isinstance(bar_latency_ms,int) or bar_latency_ms<0: raise SafeError('invalid_latency_assumption')
    if not rows or any(r.get('interval_seconds')!=60 for r in rows): raise SafeError('one_minute_bars_required')
    dest=Path(destination)
    try: dest.mkdir(mode=0o700)
    except OSError: raise SafeError('staging_destination_exists_or_invalid') from None
    fields=['symbol','contract','start','end','available_at','open','high','low','close','volume']
    with open(dest/'bars.csv','x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader()
        for row in sorted(rows,key=lambda x:(int(x['ts_event_ns']),x['symbol'])):
            writer.writerow({**{k:row[k] for k in ('symbol','contract','open','high','low','close','volume')},'start':ns_iso(int(row['ts_event_ns'])),'end':ns_iso(int(row['end_ns'])),'available_at':iso(utc(ns_iso(int(row['end_ns'])))+timedelta(milliseconds=bar_latency_ms))})
    manifest={'source':'Databento GLBX.MDP3 (see acquisition provenance)','attested_verified':False,'research_ready':False,'sha256':file_hash(dest/'bars.csv'),'timestamp_convention':'bar_start_utc','interval_seconds':60,'price_adjustment':'none','bar_latency_ms_assumption':bar_latency_ms,'availability_is_assumption_not_vendor_attestation':True,'missing_prerequisites':['independent source/license and integrity audit','authoritative exchange calendar and point-in-time news','documented and attested commission/slippage per symbol','active contracts by New York session date verified from UTC mapping','actual historical bar publication latency evidence','sufficient out-of-sample walk-forward sessions (baseline needs 70 joint cash sessions)'],'sessions':{},'active_contracts':{},'costs':{},'roll_policy':'previous_day_volume_rank_0, unadjusted actual contracts','lean_status':'raw DBN, event clocks and mappings retained; no LEAN converter or live execution implemented'}
    dump(dest/'manifest.staging.json',manifest)
    return manifest

def normalize_job(job, destination, bar_latency_ms=None):
    import databento as db
    job=Path(job); dest=Path(destination)
    if (job/'INCOMPLETE.json').exists(): raise SafeError('quarantined_input')
    try: provenance=json.loads((job/'provenance.json').read_text())
    except (OSError,ValueError): raise SafeError('invalid_provenance') from None
    if provenance.get('status')!='downloaded_unvalidated' or provenance.get('dataset')!='GLBX.MDP3': raise SafeError('invalid_provenance')
    files=provenance.get('files',[])
    if not files: raise SafeError('missing_source_files')
    for source in files:
        path=(job/source['path']).resolve()
        if not path.is_relative_to(job.resolve()) or not path.is_file() or file_hash(path)!=source['sha256']: raise SafeError('source_hash_or_path_mismatch')
    try: dest.mkdir(mode=0o700)
    except OSError: raise SafeError('normalization_destination_exists_or_invalid') from None
    dump(dest/'INCOMPLETE.json',{'status':'normalization_incomplete'})
    reports=[]; minutes=[]
    for source in files:
        store=safe_call(db.DBNStore.from_file,job/source['path'])
        if store.metadata.dataset!='GLBX.MDP3' or str(store.schema)!=source['schema']: raise SafeError('dbn_metadata_mismatch')
        frame=safe_call(store.to_df,price_type='fixed',pretty_ts=False,map_symbols=False)
        records=frame.reset_index().to_dict(orient='records')
        rows,quality=normalize_rows(source['schema'],records,provenance['mappings']['intervals'],source['request'])
        name=f"{source['root']}.{source['schema']}.jsonl"
        with open(dest/name,'x') as stream:
            for row in rows: stream.write(json.dumps(row,allow_nan=False)+'\n')
        quality.update(root=source['root'],source_sha256=source['sha256'],normalized_sha256=file_hash(dest/name),normalized_file=name)
        reports.append(quality)
        if source['schema']=='ohlcv-1m': minutes.extend(rows)
    report={'status':'failed' if any(q['invalid_records'] or not q['total_records'] for q in reports) else 'structural_checks_only','source_provenance_sha256':file_hash(job/'provenance.json'),'normalization_version':'0.1.0','partitions':reports,'research_ready':False,'attested_verified':False,'no_data_filled':True,'economic_performance':'not_evaluated'}
    if report['status']!='failed' and minutes and bar_latency_ms is not None:
        manifest=stage_abc(minutes,dest/'abc-staging',bar_latency_ms)
        manifest['source_provenance_sha256']=file_hash(job/'provenance.json')
        # Keep acquisition proof alongside staging rather than claiming an audit.
        dump(dest/'abc-staging'/'acquisition-reference.json',{'source_job':str(job.resolve()),'provenance_sha256':manifest['source_provenance_sha256']})
        report['abc_staging']='abc-staging/bars.csv'
    dump(dest/'quality.json',report); (dest/'INCOMPLETE.json').unlink()
    return report
