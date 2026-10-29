"""Explicit free-metadata / approved-billable boundary for official Databento SDK."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
import io
import json
import logging
import math
import os
import re
import shutil
import time
import warnings

import pandas as pd

SCHEMAS = ('ohlcv-1m', 'ohlcv-1s', 'trades', 'mbp-1')
ROOTS = ('MNQ', 'MES')
DATASET = 'GLBX.MDP3'
UTC = timezone.utc

class SafeError(Exception):
    """Messages are fixed codes: no raw backend errors, requests, or credentials."""

# Accept only explicit instants, not pandas' permissive date/unit inference.
_AWARE_ISO = re.compile(
    r'\d{4}-\d{2}-\d{2}[T ](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d'
    r'(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)'
)

def utc(value):
    """Validate the original input, then preserve its exact int64 UNIX ns instant.

    Numeric epochs are deliberately not accepted: their units are unspecified.
    UTC-offset ISO text, aware datetime, and aware pandas.Timestamp are supported.
    """
    try:
        if isinstance(value, str):
            if not _AWARE_ISO.fullmatch(value) or value.endswith('-00:00'):
                raise ValueError()
        elif isinstance(value, pd.Timestamp):
            if value.tzinfo is None or value.utcoffset() is None: raise ValueError()
        elif isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None: raise ValueError()
            # A local fold/gap needs an explicit offset or an already-resolved Timestamp.
            if value.replace(fold=0).utcoffset() != value.replace(fold=1).utcoffset():
                raise ValueError()
            back=value.astimezone(UTC).astimezone(value.tzinfo)
            if back.replace(tzinfo=None) != value.replace(tzinfo=None): raise ValueError()
        else:
            raise ValueError()
        stamp=pd.Timestamp(value)
        if pd.isna(stamp): raise ValueError()
        stamp=stamp.tz_convert('UTC')
        # .value raises rather than rounding if outside the int64 ns domain.
        nanos=stamp.value
        if nanos == -(2**63): raise ValueError()  # pandas NaT sentinel
        return pd.Timestamp(nanos, unit='ns', tz='UTC')
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise SafeError('invalid_aware_timestamp') from None

def iso(value): return utc(value).isoformat().replace('+00:00', 'Z')

def digest(value): return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def file_hash(path):
    h = sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def dump(path, value):
    with open(path, 'x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')

def safe_call(fn, *args, **kwargs):
    """Drop SDK warnings/logs/stdout and exception text, including Basic-auth username.

    This CLI is single-threaded: global logging suppression is scoped to this call.
    Buffers are deliberately discarded, never written to disk or returned.
    """
    previous = logging.root.manager.disable
    with warnings.catch_warnings(), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        warnings.simplefilter('ignore'); logging.disable(logging.CRITICAL)
        try: return fn(*args, **kwargs)
        except SafeError: raise
        except Exception as exc:
            status = getattr(exc, 'http_status', None)
            if status is None: status = getattr(exc, 'status_code', None)
            raise SafeError('authentication_failed' if status in (401, 403) else 'backend_request_failed') from None
        finally: logging.disable(previous)

@dataclass(frozen=True)
class Plan:
    start: str
    end: str
    roots: tuple = ROOTS
    schemas: tuple = SCHEMAS
    def __post_init__(self):
        start, end = utc(self.start), utc(self.end)
        if start >= end or end > datetime.now(UTC): raise SafeError('invalid_historical_interval')
        if not self.roots or len(set(self.roots)) != len(self.roots) or any(x not in ROOTS for x in self.roots): raise SafeError('unsupported_root')
        if not self.schemas or len(set(self.schemas)) != len(self.schemas) or any(x not in SCHEMAS for x in self.schemas): raise SafeError('unsupported_schema')
        object.__setattr__(self, 'start', iso(start)); object.__setattr__(self, 'end', iso(end))
        object.__setattr__(self, 'roots', tuple(self.roots)); object.__setattr__(self, 'schemas', tuple(self.schemas))
    def as_dict(self):
        return {'dataset':DATASET, 'start':self.start, 'end':self.end, 'roots':list(self.roots), 'schemas':list(self.schemas), 'stype_in':'continuous', 'roll_policy':'previous_day_volume_rank_0', 'price_adjustment':'none'}
    @classmethod
    def from_dict(cls, value):
        p=cls(value['start'], value['end'], tuple(value['roots']), tuple(value['schemas']))
        if p.as_dict()!=value: raise SafeError('invalid_plan')
        return p
    def request(self, root, schema):
        if schema in ('ohlcv-1m','ohlcv-1s'):
            interval=(60 if schema=='ohlcv-1m' else 1)*10**9
            if utc(self.start).value%interval or utc(self.end).value%interval:
                raise SafeError('unaligned_ohlcv_request')
        return {'dataset':DATASET,'symbols':[root+'.v.0'],'stype_in':'continuous','schema':schema,'start':self.start,'end':self.end}

class SDKBackend:
    """Only metadata/symbology and the single explicitly gated historical call exist."""
    def __init__(self):
        key=os.environ.get('DATABENTO_API_KEY')
        if not key or not key.strip(): raise SafeError('missing_DATABENTO_API_KEY')
        import databento as db
        self._client=safe_call(db.Historical, key=key)
        self._last=0.0
    def call(self, area, name, **kwargs):
        allowed={'metadata':{'list_schemas','get_dataset_range','get_dataset_condition','get_cost','get_billable_size','get_record_count'}, 'symbology':{'resolve'}, 'timeseries':{'get_range'}}
        if name not in allowed.get(area,set()): raise SafeError('endpoint_forbidden')
        time.sleep(max(0,.11-(time.monotonic()-self._last)))
        try: return safe_call(getattr(getattr(self._client,area),name),**kwargs)
        finally: self._last=time.monotonic()

class Adapter:
    def __init__(self, backend, now=lambda:datetime.now(UTC)): self.backend=backend; self.now=now
    def call(self, area, name, **kw): return safe_call(self.backend.call,area,name,**kw)
    def resolve(self, roots, start_date, end_date, kind='v'):
        symbols=[r+'.'+kind+'.0' for r in roots]
        first=self.call('symbology','resolve',dataset=DATASET,symbols=symbols,stype_in='continuous',stype_out='instrument_id',start_date=start_date,end_date=end_date)
        ids=sorted({str(i['s']) for intervals in first.get('result',{}).values() for i in intervals})
        second=self.call('symbology','resolve',dataset=DATASET,symbols=ids,stype_in='instrument_id',stype_out='raw_symbol',start_date=start_date,end_date=end_date) if ids else {'result':{}}
        intervals=[]; rejected=[]
        for root, symbol in zip(roots,symbols):
            for one in first.get('result',{}).get(symbol,[]):
                for two in second.get('result',{}).get(str(one['s']),[]):
                    a=max(one['d0'],two['d0'],start_date); b=min(one['d1'],two['d1'],end_date)
                    if a >= b: continue
                    if not re.fullmatch(root+r'[HMUZ]\d{1,2}',two['s']):
                        rejected.append({'root':root,'instrument_id':str(one['s']),'classification':'not_outright_quarter_contract'}); continue
                    intervals.append({'root':root,'contract':two['s'],'instrument_id':str(one['s']),'start_date':a,'end_date':b})
        intervals.sort(key=lambda x:(x['root'],x['start_date']))
        changes=[]
        for root in roots:
            seq=[x for x in intervals if x['root']==root]
            for prev, cur in zip(seq,seq[1:]):
                if prev['contract']!=cur['contract']: changes.append({'root':root,'utc_date':cur['start_date'],'from':prev['contract'],'to':cur['contract'],'previous_interval_end':prev['end_date']})
        return {'intervals':intervals,'rollovers':changes,'partial':first.get('partial',[]),'not_found':first.get('not_found',[]),'raw_partial':second.get('partial',[]),'raw_not_found':second.get('not_found',[]),'rejected':rejected,'policy':'previous_day_volume_rank_0' if kind=='v' else 'expiration_rank_0', 'back_adjustment':False,'date_basis':'UTC, end exclusive','first_mapped_day_is_not_first_record':True}
    def preflight(self, plan, include_history=False):
        # Validate exact bounds for every schema before even free backend calls.
        for root in plan.roots:
            for schema in plan.schemas: plan.request(root,schema)
        now=utc(self.now())
        available=self.call('metadata','list_schemas',dataset=DATASET)
        if any(s not in available for s in plan.schemas): raise SafeError('schema_unavailable')
        ranges=self.call('metadata','get_dataset_range',dataset=DATASET)
        for schema in plan.schemas:
            r=ranges.get('schema',{}).get(schema)
            if not r or utc(plan.start)<utc(r['start']) or utc(plan.end)>utc(r['end']): raise SafeError('request_outside_schema_range')
        a=utc(plan.start).date().isoformat(); b=(utc(plan.end)-pd.Timedelta(1,unit='ns')).date()
        exclusive=(b+timedelta(days=1)).isoformat()
        mappings={key:self.resolve(plan.roots,a,exclusive,kind) for key,kind in [('volume','v'),('calendar','c')]}
        if not self.mapping_complete(mappings['volume'],plan): raise SafeError('incomplete_contract_mapping')
        quotes=[]
        for root in plan.roots:
            for schema in plan.schemas:
                req=plan.request(root,schema)
                cost=self.call('metadata','get_cost',**req)
                size=self.call('metadata','get_billable_size',**req)
                count=self.call('metadata','get_record_count',**req)
                if isinstance(cost,bool) or not isinstance(cost,(int,float)) or not math.isfinite(cost) or cost<0: raise SafeError('invalid_cost_quote')
                if any(isinstance(v,bool) or not isinstance(v,int) or v<0 for v in (size,count)): raise SafeError('invalid_size_or_count')
                quotes.append({'root':root,'schema':schema,'request':req,'estimated_cost_usd':cost,'billable_uncompressed_bytes':size,'records':count,'presence_verified_in_requested_interval':count>0})
        conditions=self.call('metadata','get_dataset_condition',dataset=DATASET,start_date=a,end_date=b.isoformat())
        report={'status':'verified_metadata','adapter_version':'0.1.0','sdk_version':version('databento'),'checked_at':iso(now),'expires_at':iso(now+timedelta(minutes=15)),'plan':plan.as_dict(),'request_sha256':digest(plan.as_dict()),'dataset_range':ranges,'mappings':mappings,'quotes':quotes,'total_estimated_cost_usd':sum(x['estimated_cost_usd'] for x in quotes),'total_billable_uncompressed_bytes':sum(x['billable_uncompressed_bytes'] for x in quotes),'total_records':sum(x['records'] for x in quotes),'dataset_conditions':conditions,'download_authorized':False,'actual_data_quality':'not_acquired','historical_product_first_record':'not_verified','coverage_note':'Dataset-wide bounds and symbology validity do not establish first/last actual MNQ/MES records. Counts prove presence only in the requested interval. Estimates are not a vendor hard spending cap.'}
        if include_history:
            hist_start=utc(ranges['start']).date().isoformat()
            hist_end=(utc(ranges['end'])-pd.Timedelta(1,unit='ns')).date()+timedelta(days=1)
            report['historical_mapping']={key:self.resolve(plan.roots,hist_start,hist_end.isoformat(),kind) for key,kind in [('volume','v'),('calendar','c')]}
        return report
    @staticmethod
    def mapping_complete(mapping, plan):
        if mapping.get('partial') or mapping.get('not_found') or mapping.get('rejected') or mapping.get('raw_partial') or mapping.get('raw_not_found'): return False
        for root in plan.roots:
            day=utc(plan.start).date(); end=(utc(plan.end)-pd.Timedelta(1,unit='ns')).date()
            while day<=end:
                hits=[x for x in mapping['intervals'] if x['root']==root and x['start_date']<=day.isoformat()<x['end_date']]
                if len(hits)!=1: return False
                day+=timedelta(days=1)
        return True
    def download(self, report, destination, approval_sha256, max_usd):
        """Never invoked by preflight; caller must provide explicit exact-request approval.

        Requote all requests before the first charged call. A client-side cap cannot
        guarantee vendor billing; partial output stays quarantined without retries.
        """
        try: plan=Plan.from_dict(report['plan'])
        except (KeyError,TypeError): raise SafeError('invalid_preflight') from None
        request_hash=digest(plan.as_dict())
        if not approval_sha256 or approval_sha256!=request_hash or report.get('request_sha256')!=request_hash: raise SafeError('explicit_exact_request_approval_required')
        now=utc(self.now())
        if not (utc(report['checked_at'])<=now<utc(report['expires_at'])): raise SafeError('stale_quote')
        if isinstance(max_usd,bool) or not isinstance(max_usd,(float,int)) or not math.isfinite(max_usd) or max_usd<0: raise SafeError('invalid_cost_cap')
        if report.get('status')!='verified_metadata' or report['total_estimated_cost_usd']>max_usd: raise SafeError('cost_cap_exceeded')
        dest=Path(destination)
        if dest.exists() or not dest.parent.is_dir(): raise SafeError('destination_exists_or_parent_missing')
        if shutil.disk_usage(dest.parent).free < max(16*1024*1024,report['total_billable_uncompressed_bytes']*3): raise SafeError('insufficient_disk_capacity')
        try: dest.mkdir(mode=0o700)
        except OSError: raise SafeError('destination_admission_failed') from None
        # Exclusive directory is the job lock, held through completion/quarantine.
        attempted=[]; files=[]
        quarantine={'status':'quarantined_incomplete','request_sha256':request_hash,'automatic_retry':False,'attempted_partitions':attempted,'completed_files':files,'attempted_partition_count':0,'completed_partition_count':0}
        dump(dest/'INCOMPLETE.json',quarantine)
        def checkpoint():
            quarantine.update(attempted_partition_count=len(attempted),completed_partition_count=len(files))
            (dest/'INCOMPLETE.json').write_text(json.dumps(quarantine,indent=2,allow_nan=False)+'\n')
        try:
            fresh=self.preflight(plan)
            if fresh['total_estimated_cost_usd']>max_usd: raise SafeError('cost_cap_exceeded')
            if shutil.disk_usage(dest).free < max(16*1024*1024,fresh['total_billable_uncompressed_bytes']*3): raise SafeError('insufficient_disk_capacity')
            if any(q['records']<=0 for q in fresh['quotes']): raise SafeError('empty_requested_partition')
            dump(dest/'preflight.json',fresh)
            (dest/'raw').mkdir()
            paths=[dest/'raw'/f"{q['root']}.{q['schema']}.dbn.zst" for q in fresh['quotes']]
            if any(p.exists() for p in paths): raise SafeError('output_collision')
            for quote,path in zip(fresh['quotes'],paths):
                # Metadata refresh itself or an earlier partition may exhaust TTL.
                # Never silently requote/retry a partially charged job.
                if not utc(fresh['checked_at'])<=utc(self.now())<utc(fresh['expires_at']): raise SafeError('refreshed_quote_expired')
                attempted.append({'root':quote['root'],'schema':quote['schema'],'path':str(path.relative_to(dest))})
                checkpoint()
                if not utc(fresh['checked_at'])<=utc(self.now())<utc(fresh['expires_at']):
                    attempted.pop()
                    raise SafeError('refreshed_quote_expired')
                self.call('timeseries','get_range',**quote['request'],stype_out='instrument_id',path=path)
                if not path.is_file(): raise SafeError('download_output_missing')
                files.append({'path':str(path.relative_to(dest)),'root':quote['root'],'schema':quote['schema'],'sha256':file_hash(path),'bytes':path.stat().st_size,'request':quote['request']})
                checkpoint()
            provenance={'status':'downloaded_unvalidated','source':'Databento Historical API','dataset':DATASET,'retrieved_at':iso(self.now()),'request_sha256':request_hash,'approved_max_usd':max_usd,'quote_is_not_vendor_spending_cap':True,'estimated_cost_usd':fresh['total_estimated_cost_usd'],'sdk_version':version('databento'),'adapter_version':'0.1.0','normalization_version':'0.1.0','mappings':fresh['mappings']['volume'],'files':files,'research_ready':False,'attested_verified':False,'license':'User must independently confirm CME/Databento entitlements and permitted use.'}
            dump(dest/'provenance.json',provenance); (dest/'INCOMPLETE.json').unlink()
            return provenance
        except Exception as exc:
            quarantine['failure_code']=str(exc) if isinstance(exc,SafeError) else 'operation_failed'
            try: checkpoint()
            except OSError: pass
            raise SafeError('download_failed_quarantined_no_automatic_retry') from None
