"""Local integrity-checked raw acquisition coverage, never vendor authenticity.

Unsigned receipts prove local consistency only. Source revision 'unknown' is
explicit; operators must quarantine known-stale artifacts before new approval.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
import uuid

import numpy as np
from mnq_data.core import digest, file_hash
from .security import PlannerError, quietly


def atomic_json(path, value):
    from .paths import contained
    path=contained(path,Path(path).parent)
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x') as stream:
            json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if temporary.exists(): temporary.unlink()


@dataclass(frozen=True)
class Identity:
    dataset: str
    schema: str
    root: str
    contract: str
    instrument_id: str
    publisher_id: int
    provider_revision: str
    normalization_version: str
    source_sha256: str

    def as_dict(self): return asdict(self)

    def validate(self):
        import re
        from databento import Publisher
        if (self.dataset!='GLBX.MDP3' or self.schema not in ('ohlcv-1m','ohlcv-1s','mbp-1')
                or self.root not in ('MNQ','MES')
                or not re.fullmatch(self.root+r'[HMUZ]\d{1,2}',self.contract)
                or not re.fullmatch(r'[1-9][0-9]*',self.instrument_id)
                or type(self.publisher_id) is not int or self.publisher_id!=Publisher.GLBX_MDP3_GLBX.to_int()
                or not all(isinstance(x,str) and x for x in (self.provider_revision,self.normalization_version,self.source_sha256))):
            raise PlannerError('invalid_cache_identity')


def interval(bounds):
    if (not isinstance(bounds,(tuple,list)) or len(bounds)!=2
            or any(type(n) is not int or not -(2**63)<n<2**63 for n in bounds)
            or bounds[0]>=bounds[1]):
        raise PlannerError('invalid_interval')
    return tuple(bounds)


def subtract(bounds, coverage):
    start,end=interval(bounds)
    cursor=start;missing=[]
    for a,b in sorted(interval(c) for c in coverage):
        if b<=cursor or a>=end: continue
        if a>cursor: missing.append((cursor,min(a,end)))
        cursor=max(cursor,min(b,end))
    if cursor<end: missing.append((cursor,end))
    return missing


class Cache:
    def __init__(self, root):
        supplied=Path(root).absolute()
        if supplied.is_symlink() or any(p.is_symlink() for p in supplied.parents):
            raise PlannerError('cache_symlink_forbidden')
        supplied.mkdir(parents=True,exist_ok=True)
        self.root=supplied.resolve()
        for directory in ('receipts','objects','jobs','nonces','leases'):
            p=self.root/directory
            if p.is_symlink(): raise PlannerError('cache_symlink_forbidden')
            p.mkdir(exist_ok=True)
        if (self.root/'.lock').is_symlink(): raise PlannerError('cache_symlink_forbidden')
        self._thread_lock=threading.RLock()
        self._depth=0

    @contextmanager
    def lock(self):
        with self._thread_lock:
            outer=self._depth==0
            handle=None
            if outer:
                handle=open(self.root/'.lock','a+')
                fcntl.flock(handle,fcntl.LOCK_EX)
            self._depth+=1
            try: yield
            finally:
                self._depth-=1
                if outer:
                    fcntl.flock(handle,fcntl.LOCK_UN);handle.close()

    def confined(self,path):
        p=Path(path).absolute()
        try: relative=p.relative_to(self.root)
        except ValueError: raise PlannerError('cache_path_escape') from None
        current=self.root
        for part in relative.parts:
            if part in ('.','..'): raise PlannerError('cache_path_escape')
            current=current/part
            if current.is_symlink(): raise PlannerError('cache_symlink_forbidden')
        if not p.is_file(): raise PlannerError('cache_file_missing')
        return p

    def incomplete_ancestor(self,path):
        return any((parent/'INCOMPLETE.json').exists() for parent in Path(path).parents
                   if parent==self.root or self.root in parent.parents)

    def missing(self, identity, bounds):
        identity.validate();interval(bounds)
        with self.lock():
            covers=[]
            for p in sorted((self.root/'receipts').glob('*.json')):
                self.confined(p)
                try: receipt=json.loads(p.read_text())
                except Exception: raise PlannerError('cache_corrupt_manual_quarantine_required') from None
                # Quote reports, partial and synthetic receipts never establish coverage.
                if receipt.get('status')!='locally_validated_complete_raw': continue
                if p.stem!=digest(receipt):
                    raise PlannerError('cache_corrupt_manual_quarantine_required')
                if receipt.get('identity')!=identity.as_dict(): continue
                if receipt.get('vendor_authenticated') is not False or receipt.get('research_ready') is not False:
                    raise PlannerError('cache_invalid_attestation')
                path=self.confined(self.root/receipt['path'])
                if path.stat().st_size!=receipt.get('bytes') or file_hash(path)!=receipt.get('sha256'):
                    raise PlannerError('cache_corrupt_manual_quarantine_required')
                if self.incomplete_ancestor(path):
                    raise PlannerError('cache_incomplete_manual_quarantine_required')
                covers.append(interval((receipt['start_ns'],receipt['end_ns'])))
            return subtract(bounds,covers)

    def register(self,path,identity,bounds,provenance):
        """Only completed request provenance AND independent SDK content checks count.

        No public caller-supplied 'verified' flag or synthetic inspector is accepted.
        Original DBN stays raw; this does not attest an ABC-ready normalized dataset.
        """
        identity.validate();start,end=interval(bounds)
        with self.lock():
            path=self.confined(path)
            if self.incomplete_ancestor(path): raise PlannerError('partial_job_not_cacheable')
            expected={'dataset':identity.dataset,'schema':identity.schema,
                'symbols':[identity.contract],'stype_in':'raw_symbol',
                'start_ns':start,'end_ns':end}
            if (provenance.get('status')!='downloaded_unvalidated'
                    or provenance.get('request_complete') is not True
                    or provenance.get('request')!=expected
                    or provenance.get('source')!='Databento Historical API'
                    or provenance.get('synthetic') is not False
                    or provenance.get('sha256')!=file_hash(path)):
                raise PlannerError('complete_raw_provenance_required')
            facts=quietly(self._validate_dbn,path,identity,(start,end))
            receipt={'status':'locally_validated_complete_raw','identity':identity.as_dict(),
                'start_ns':start,'end_ns':end,'path':str(path.relative_to(self.root)),
                'bytes':path.stat().st_size,'sha256':file_hash(path),
                'provenance_sha256':digest(provenance),'content_checks':facts,
                'request_coverage':'completed_query_not_full_minute_grid',
                'vendor_authenticated':False,'research_ready':False,
                'source_correction_revision':identity.provider_revision}
            atomic_json(self.root/'receipts'/(digest(receipt)+'.json'),receipt)
            return receipt

    @staticmethod
    def _validate_dbn(path,identity,bounds):
        import databento as db
        store=db.DBNStore.from_file(path)
        if (store.dataset!=identity.dataset or str(store.schema)!=identity.schema
                or str(store.stype_in)!='raw_symbol' or str(store.stype_out)!='instrument_id'
                or list(store.symbols)!=[identity.contract]
                or store.start.value!=bounds[0] or store.end is None or store.end.value!=bounds[1]
                or store.limit not in (None,0) or store.metadata.partial or store.metadata.not_found):
            raise PlannerError('dbn_metadata_mismatch')
        records=store.to_ndarray()
        if len(records)==0: raise PlannerError('empty_dbn_not_cacheable')
        names=set(records.dtype.names or ())
        if not {'instrument_id','publisher_id','ts_event'}<=names:
            raise PlannerError('dbn_record_fields_missing')
        if (np.any(records['instrument_id']!=int(identity.instrument_id))
                or np.any(records['publisher_id']!=identity.publisher_id)):
            raise PlannerError('dbn_instrument_publisher_mismatch')
        clock='ts_recv' if identity.schema=='mbp-1' else 'ts_event'
        if clock not in names: raise PlannerError('dbn_clock_missing')
        times=records[clock].astype('int64')
        if np.any(times<bounds[0]) or np.any(times>=bounds[1]) or np.any(times[1:]<times[:-1]):
            raise PlannerError('dbn_time_bounds_or_order')
        if identity.schema.startswith('ohlcv'):
            grid=(60 if identity.schema=='ohlcv-1m' else 1)*10**9
            if bounds[0]%grid or bounds[1]%grid or np.any(times%grid) or len(np.unique(times))!=len(times):
                raise PlannerError('dbn_bar_grid_or_duplicates')
            for name in ('open','high','low','close'):
                if name not in names or np.any(records[name]<=0) or np.any(records[name]>=2**63-1):
                    raise PlannerError('dbn_price_invalid')
            if np.any(records['low']>records['high']) or np.any(records['low']>records['open']) or np.any(records['low']>records['close']) or np.any(records['high']<records['open']) or np.any(records['high']<records['close']):
                raise PlannerError('dbn_ohlc_invalid')
        return {'records':len(records),'schema_dataset_publisher_bounds_verified':True,
                'quality_scope':'structural_raw_only','gap_free_not_asserted':True}
