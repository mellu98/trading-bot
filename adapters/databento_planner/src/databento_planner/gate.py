"""Future acquisition boundary. No production paid backend or CLI execution exists.

Callers must supply fresh quotes and an explicit per-job human approval. Estimates
are client-side checks, NOT vendor-enforced billing limits. No automatic retries.
"""
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
import re
import shutil

from mnq_data.core import digest, file_hash, iso
from .cache import Identity, atomic_json, interval
from .planner import money, stamp
from .security import PlannerError, quietly
from .paths import contained


@dataclass(frozen=True)
class Approval:
    request_sha256: str
    max_usd: str
    nonce: str


def acquisition_digest(job):
    return digest(job)


def validate_job(job):
    if job.get('dataset')!='GLBX.MDP3' or job.get('schema')!='ohlcv-1m':
        raise PlannerError('unapproved_tier_or_dataset')
    if not isinstance(job.get('partitions'),list): raise PlannerError('invalid_job')
    seen=set()
    for p in job['partitions']:
        identity=Identity(**p['identity']);identity.validate()
        if identity.dataset!=job['dataset'] or identity.schema!=job['schema']:
            raise PlannerError('job_identity_mismatch')
        bounds=interval((p['start_ns'],p['end_ns']))
        if any(x%(60*10**9) for x in bounds): raise PlannerError('unaligned_partition')
        key=(digest(identity.as_dict()),bounds)
        if key in seen: raise PlannerError('duplicate_partition')
        if any(old==key[0] and max(a,bounds[0])<min(b,bounds[1]) for old,(a,b) in seen):
            raise PlannerError('overlapping_job_partitions')
        seen.add(key)
        money(p['cost_usd'])
        if type(p['billable_bytes']) is not int or p['billable_bytes']<0: raise PlannerError('invalid_size')
        stamp(p['quote_expires_at'])
    stamp(job['quote_checked_at']);stamp(job['quote_expires_at'])


def execute_approved(job,approval,cache,destination,backend,now,configured_cap='0'):
    """Injectable future executor tested solely with fake backends.

    A global cache file lock remains held across all charged calls. Durable nonce
    and INCOMPLETE checkpoints survive crashes. Any new cache miss invalidates
    approval; a smaller miss also requires a new exact digest, never broadening it.
    """
    dest=contained(destination,cache.root/'jobs')
    validate_job(job)
    clock=(lambda:stamp(now())) if callable(now) else (lambda:stamp(now))
    with cache.lock():
        misses=[]
        for p in job['partitions']:
            bounds=(p['start_ns'],p['end_ns'])
            remaining=cache.missing(Identity(**p['identity']),bounds)
            if remaining: misses.append((p,remaining))
        if not misses:
            return {'status':'all_cache_hits','charged_calls':0,'network_calls':0}
        if any(left!=[(p['start_ns'],p['end_ns'])] for p,left in misses) or len(misses)!=len(job['partitions']):
            raise PlannerError('cache_changed_replan_and_new_approval_required')
        if not isinstance(approval,Approval) or approval.request_sha256!=acquisition_digest(job):
            raise PlannerError('explicit_exact_job_approval_required')
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',approval.nonce): raise PlannerError('invalid_nonce')
        cap=min(money(configured_cap),money(approval.max_usd))
        if sum((money(p['cost_usd']) for p,_ in misses),Decimal(0))>cap:
            raise PlannerError('cost_cap_exceeded')
        if not stamp(job['quote_checked_at'])<=clock()<stamp(job['quote_expires_at']):
            raise PlannerError('stale_quote')
        nonce_path=cache.root/'nonces'/(digest({'nonce':approval.nonce})+'.json')
        if nonce_path.exists(): raise PlannerError('approval_nonce_already_consumed')
        # Unvalidated/completed or crashed jobs must also block overlap until an
        # operator validates their artifacts or explicitly resolves quarantine.
        # A file lock alone is insufficient once the first process exits.
        for old in (cache.root/'leases').glob('*.json'):
            cache.confined(old)
            try: prior=json.loads(old.read_text())
            except Exception: raise PlannerError('corrupt_lease_manual_resolution_required') from None
            scope=prior.get('scope')
            if not isinstance(scope,list): raise PlannerError('invalid_lease_manual_resolution_required')
            for held in scope:
                for p,_ in misses:
                    if held['identity']==p['identity'] and max(held['start_ns'],p['start_ns'])<min(held['end_ns'],p['end_ns']):
                        raise PlannerError('overlapping_lease_manual_resolution_required')
        contained(dest,cache.root/'jobs')
        if dest.exists() or not dest.parent.is_dir():
            raise PlannerError('output_collision_or_parent_missing')
        size=sum(p['billable_bytes'] for p,_ in misses)
        if shutil.disk_usage(dest.parent).free<max(16*1024*1024,size*3): raise PlannerError('insufficient_disk_capacity')
        lease=cache.root/'leases'/(approval.request_sha256+'.json')
        if lease.exists(): raise PlannerError('existing_lease_manual_resolution_required')
        scope=[{'identity':p['identity'],'start_ns':p['start_ns'],'end_ns':p['end_ns']} for p,_ in misses]
        contained(dest,cache.root/'jobs').mkdir(mode=0o700)
        atomic_json(lease,{'status':'reserved','request_sha256':approval.request_sha256,'scope':scope})
        state={'status':'quarantined_incomplete','request_sha256':approval.request_sha256,
               'attempted':[],'completed':[],'automatic_retry':False,'research_ready':False}
        atomic_json(dest/'INCOMPLETE.json',state)
        consumed=False;spent=Decimal(0)
        try:
            for n,(p,_) in enumerate(misses):
                path=dest/(str(n)+'.dbn.zst')
                if path.exists(): raise PlannerError('output_collision')
                if not stamp(job['quote_checked_at'])<=clock()<min(stamp(job['quote_expires_at']),stamp(p['quote_expires_at'])):
                    raise PlannerError('quote_expired_before_partition')
                fresh=quietly(backend.quote,p)
                if acquisition_digest(job)!=approval.request_sha256:
                    raise PlannerError('approved_scope_mutated')
                cost=money(fresh['cost_usd'])
                if (cost>money(p['cost_usd']) or spent+cost>cap):
                    raise PlannerError('fresh_price_exceeds_approval_or_cap')
                if type(fresh['billable_bytes']) is not int or fresh['billable_bytes']<0:
                    raise PlannerError('invalid_fresh_size')
                if clock()>=stamp(fresh['expires_at']): raise PlannerError('fresh_quote_expired')
                if shutil.disk_usage(dest).free<max(16*1024*1024,fresh['billable_bytes']*3):
                    raise PlannerError('insufficient_disk_capacity')
                if not consumed:
                    # Burn before the first potentially charged invocation, including $0.
                    atomic_json(nonce_path,{'request_sha256':approval.request_sha256,'status':'consumed'})
                    consumed=True
                state['attempted'].append(n)
                atomic_json(dest/'INCOMPLETE.json',state)
                # Check again after disk/checkpoint work; no paid retry after timeout.
                if clock()>=min(stamp(fresh['expires_at']),stamp(job['quote_expires_at']),stamp(p['quote_expires_at'])):
                    raise PlannerError('quote_expired_before_charged_call')
                if acquisition_digest(job)!=approval.request_sha256:
                    raise PlannerError('approved_scope_mutated')
                contained(path,cache.root/'jobs')
                quietly(backend.acquire,p,path)
                if not path.is_file() or path.is_symlink(): raise PlannerError('acquisition_output_missing')
                spent+=cost
                state['completed'].append({'partition':n,'path':path.name,'sha256':file_hash(path),
                    'bytes':path.stat().st_size,'request':p,'fresh_estimated_cost_usd':str(cost)})
                atomic_json(dest/'INCOMPLETE.json',state)
            result={'status':'downloaded_unvalidated','research_ready':False,'vendor_authenticated':False,
                    'request_sha256':approval.request_sha256,'files':state['completed'],
                    'estimated_cost_usd':str(spent),'vendor_hard_spending_cap':False,
                    'cache_registration':'not_automatic_independent_content_validation_required'}
            atomic_json(dest/'provenance.json',result)
            (dest/'INCOMPLETE.json').unlink()
            atomic_json(lease,{'status':'completed_unvalidated','request_sha256':approval.request_sha256,'scope':scope})
            return result
        except Exception:
            state['failure_code']='acquisition_failed_no_automatic_retry'
            atomic_json(dest/'INCOMPLETE.json',state)
            atomic_json(lease,{'status':'incomplete_manual_resolution_required','request_sha256':approval.request_sha256,'scope':scope})
            raise PlannerError('acquisition_failed_quarantined_no_automatic_retry') from None
