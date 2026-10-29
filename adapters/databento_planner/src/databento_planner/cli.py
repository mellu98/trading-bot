"""The public CLI can quote and plan; it has NO data acquisition operation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import os
import uuid
from .paths import contained

from mnq_data.core import digest, file_hash, iso
from .cache import Cache, Identity
from .gate import acquisition_digest
from .planner import comparison, money, stamp
from .security import MetadataOnly, PlannerError, load_key, quietly

ROOT=Path(__file__).resolve().parents[4]


def secure_write(path,value,credentials=(),replace=False):
    rendered=value if isinstance(value,str) else json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n'
    if any(c and c in rendered for c in credentials): raise PlannerError('credential_redaction_guard')
    allowed=ROOT/'reports/databento/planning';path=contained(path,allowed)
    temporary=contained(path.with_name('.'+uuid.uuid4().hex+'.tmp'),allowed) if replace else path
    try:
        with temporary.open('x') as stream:
            stream.write(rendered);stream.flush();os.fsync(stream.fileno())
        if replace: os.replace(temporary,contained(path,allowed))
    finally:
        if replace and temporary.exists(): temporary.unlink()


def baseline_check():
    baseline=json.loads((ROOT/'reports/databento/planning/baseline-integrity.json').read_text())
    hashes=baseline['all_existing_before']
    mismatches=[p for p,h in hashes.items() if not (ROOT/p).is_file() or file_hash(ROOT/p)!=h]
    modes=baseline.get('generated_metadata_before',{})
    # Existing baseline snapshot hashes are authoritative, never rewritten here.
    if mismatches: raise PlannerError('immutable_baseline_mismatch')
    return {'checked_paths':len(hashes),'all_original_hashes_unchanged':True,
            'primary_37_unchanged':all(file_hash(ROOT/p)==h for p,h in baseline['primary_37']['files'].items())}


def compact(report):
    lines=['# Databento cash-session cost comparison','',
        'Free authenticated metadata only. No data was purchased or downloaded.','',
        '| Sessions | First cash date | MNQ USD | MES USD | Total USD | Records | Uncompressed bytes |',
        '|---:|---|---:|---:|---:|---:|---:|']
    for count in ('1','5','20','60'):
        s=report['scenarios'][count]
        fields=[s['roots']['MNQ']['cost_usd'],s['roots']['MES']['cost_usd'],s['total_cost_usd'],s['total_records'],s['total_billable_uncompressed_bytes']]
        lines.append('| '+count+' | '+s['first_session']+' | '+' | '.join('unknown' if v is None else str(v) for v in fields)+' |')
    lines+=['',f"Study status: {report['status']}; completed partitions: {len(report['partitions'])}/120. Unknown totals remain null.",'',f"Quote checked {report['checked_at']}; expires {report['expires_at']} (historical-study estimates may already be expired; NEVER acquisition permission).",
        '','Five sessions is the minimum useful multiday technical sample; one is the cheapest smoke test.',
        'None of these samples satisfies default ABC splits: 70 joint sessions minimum for one fold; 90 for both count floors. No return or signal guarantee.',
        '','Cash research window only: 09:30 America/New_York to actual XNYS close, not full Globex. Each session is requested separately.',
        'Counts and vendor daily conditions do not prove gap-free raw data. License, acquisition entitlement and balance remain untested.',
        '','Future ohlcv-1s + mbp-1 is configured only. No Tier2 quotes or acquisitions were made.',
        'Default acquisition budget is unapproved/0 USD. Every future job requires its exact digest, a new manual approval nonce, a fresh quote and a configurable cap; even a zero-dollar job is not auto-approved.',
        '','The cache currently contains no real data. Hashes prove local consistency, not vendor authenticity or latest source revision.']
    return '\n'.join(lines)+'\n'


def quote_command(args):
    allowed=ROOT/'reports/databento/planning';out=contained(args.output,allowed)
    out.mkdir(parents=True,exist_ok=True)
    names=['cost-comparison-complete.json','cost-comparison-complete.md','metadata-execution-complete.json']
    checkpoint=contained(out/'checkpoints',allowed)
    for name in names:
        target=contained(out/name,allowed)
        if target.exists() and not contained(checkpoint/'snapshot.json',allowed).is_file():
            raise PlannerError('output_collision')
    maximum=getattr(args,'max_calls',60);seconds=getattr(args,'max_seconds',240)
    if type(maximum) is not int or not 1<=maximum<=60 or not 1<=seconds<=300:
        raise PlannerError('invalid_metadata_batch_bound')
    before=baseline_check();key,auth=load_key()
    backend=MetadataOnly(key,max_requests=maximum,max_seconds=seconds)
    checked=iso(datetime.now(timezone.utc));as_of=args.as_of or checked
    report=None;failure=None
    try:
        report=comparison(backend,as_of,checkpoint=checkpoint,max_calls=maximum)
    except PlannerError as exc:
        failure=str(exc)
        if not failure.replace('_','').isalnum(): failure='metadata_planning_failed'
        try: report=comparison(backend,as_of,checkpoint=checkpoint,max_calls=0)
        except PlannerError: pass
    finally:
        if report is not None:
            report.update(authentication=auth,immutability=baseline_check(),skill_resolution='paths-injected',safe_batch_failure_code=failure)
            report['preflight_passed']=report['preflight_passed'] and report['http_evidence']['all_observed_http200']
            secure_write(out/names[0],report,(key,key[3:]),replace=True)
            secure_write(out/names[1],compact(report),(key,key[3:]),replace=True)
        previous=json.loads((out/names[2]).read_text()) if (out/names[2]).exists() else {}
        execution={'checked_at':checked,'completed_at':iso(datetime.now(timezone.utc)),
            'status':report['status'] if report else 'not_verified','safe_failure_code':failure,
            'authentication':auth,'http':previous.get('http',[])+backend.trace,
            'last_batch_http_count':len(backend.trace),'maximum_requests_per_batch':maximum,
            'maximum_seconds_per_batch':seconds,'deadline_aware_connect_read_timeouts':True,
            'billable_data_calls':0,'data_downloads':0,'purchases':0,
            'fixed_host':'hist.databento.com','tls_verified':True,'redirects_allowed':False,
            'rate_limit_rps_max':5,'immutability_before':before,'immutability_after':baseline_check(),
            'account_balance_or_paid_entitlement_checked':False,'keychain_modified':False,
            'credential_material_logged':False}
        batches=contained(out/'batches',allowed);batches.mkdir(exist_ok=True)
        secure_write(batches/(uuid.uuid4().hex+'.json'),{**execution,'http':backend.trace},(key,key[3:]))
        secure_write(out/names[2],execution,(key,key[3:]),replace=True)
        backend.close()
    if failure: raise PlannerError(failure)
    return {'status':report['status'],'report':str(out/names[0]),'data_downloads':0,
            'new_http_responses':len(backend.trace),'completed_partitions':len(report['partitions']),
            'scenarios':{k:v['total_cost_usd'] for k,v in report['scenarios'].items()}}


def offline_cache_plan(report,days,cache):
    if days not in (1,5,20,60) or report.get('status')!='verified_metadata': raise PlannerError('invalid_comparison')
    from databento import Publisher
    source_hash=digest({'core':file_hash(ROOT/'adapters/databento/src/mnq_data/core.py'),
                        'local':file_hash(ROOT/'adapters/databento/src/mnq_data/local.py'),
                        'cache_validator':file_hash(Path(__file__).with_name('cache.py'))})
    dates={x['date'] for x in report['sessions'][-days:]}
    partitions=[];hits=0;unknown=False
    with cache.lock():
        for p in report['partitions']:
            if p['date'] not in dates: continue
            identity=Identity(report['dataset'],p['schema'],p['root'],p['contract'],str(p['instrument_id']),
                Publisher.GLBX_MDP3_GLBX.to_int(),'unknown','0.1.0',source_hash)
            bounds=(p['start_ns'],p['end_ns']);missing=cache.missing(identity,bounds)
            if not missing: hits+=1
            for start,end in missing:
                exact=(start,end)==bounds
                unknown|=not exact
                partitions.append({'identity':identity.as_dict(),'start_ns':start,'end_ns':end,
                    'cost_usd':p['estimated_cost_usd'] if exact else None,
                    'billable_bytes':p['billable_uncompressed_bytes'] if exact else None,
                    'quote_expires_at':report['expires_at']})
    job={'dataset':report['dataset'],'schema':report['schema'],'partitions':partitions,
         'quote_checked_at':report['checked_at'],'quote_expires_at':report['expires_at']}
    return {'status':'fresh_exact_miss_quotes_required' if unknown else 'offline_plan_not_approved',
            'job':job,'request_sha256':acquisition_digest(job),'cache_hit_partitions':hits,
            'missing_partitions':len(partitions),'network_calls':0,'download_authorized':False,
            'default_approved_budget':False,'default_cap_usd':'0',
            'quote_must_be_refreshed_before_each_charged_partition':True,
            'manual_approval_required_for_each_job_even_if_zero':True}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    quote=sub.add_parser('compare',help='Free metadata only: 1/5/20/60 completed cash sessions')
    quote.add_argument('--as-of',help='Explicit aware historical timestamp; default now UTC')
    quote.add_argument('--output',default=str(ROOT/'reports/databento/planning/correction-study'))
    quote.add_argument('--max-calls',type=int,default=60,help='New free calls in this resumable batch,1–60')
    quote.add_argument('--max-seconds',type=float,default=240,help='Per-invocation transport deadline, maximum300s')
    cache=sub.add_parser('cache-plan',help='Offline cache subtraction only; never download')
    cache.add_argument('--comparison',required=True)
    cache.add_argument('--sessions',type=int,choices=(1,5,20,60),default=5)
    cache.add_argument('--cache',required=True)
    cache.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='compare': result=quietly(quote_command,args)
        else:
            result=offline_cache_plan(json.loads(Path(args.comparison).read_text()),args.sessions,Cache(args.cache))
            secure_write(args.output,result)
        print(json.dumps(result if args.command=='compare' else {'status':result['status'],'network_calls':0},sort_keys=True))
        return 0
    except Exception:
        # Even exception values themselves are not printed by the public boundary.
        print(json.dumps({'status':'failed_closed','error':'planning_failed_see_safe_execution_report_if_created'}))
        return 2

if __name__=='__main__': sys.exit(main())
