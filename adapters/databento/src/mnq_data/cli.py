"""Command-line entry; no credentials in arguments, output, or exception strings."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
from .core import Adapter, Plan, SDKBackend, SafeError, dump, iso
from .local import normalize_job

def main():
    p=argparse.ArgumentParser(description='Simulation-only Databento historical research adapter')
    sub=p.add_subparsers(dest='command',required=True)
    pre=sub.add_parser('preflight',help='Free metadata/symbology only; never downloads data')
    pre.add_argument('--start',default='2026-10-23T13:30:00Z'); pre.add_argument('--end',default='2026-10-23T13:40:00Z')
    pre.add_argument('--output',required=True); pre.add_argument('--history',action='store_true',help='Also resolve full historical continuous mapping (not record coverage)')
    down=sub.add_parser('download',help='BILLABLE: requires explicit human authorization for the exact request digest')
    down.add_argument('--preflight',required=True); down.add_argument('--output',required=True)
    down.add_argument('--approve-request-sha256',required=True); down.add_argument('--max-usd',required=True,type=float)
    local=sub.add_parser('normalize',help='Local acquired DBN only, structural quality and optional non-attested ABC staging')
    local.add_argument('--job',required=True); local.add_argument('--output',required=True); local.add_argument('--bar-latency-ms',type=int)
    args=p.parse_args()
    try:
        if args.command=='preflight':
            if Path(args.output).exists() or not Path(args.output).parent.is_dir(): raise SafeError('output_exists_or_parent_missing')
            plan=Plan(args.start,args.end)
            try: result=Adapter(SDKBackend()).preflight(plan,args.history)
            except SafeError as e:
                result={'status':'not_verified','error_code':str(e),'checked_at':iso(datetime.now(timezone.utc)),'plan':plan.as_dict(),'estimated_cost_usd':None,'actual_data_quality':'not_acquired','download_authorized':False}
                dump(args.output,result); print(json.dumps(result)); return 2
            dump(args.output,result)
            print(json.dumps({'status':result['status'],'report':args.output,'request_sha256':result['request_sha256'],'estimated_cost_usd':result['total_estimated_cost_usd'],'billable_uncompressed_bytes':result['total_billable_uncompressed_bytes'],'records':result['total_records'],'download_authorized':False}))
        elif args.command=='download':
            report=json.loads(Path(args.preflight).read_text())
            result=Adapter(SDKBackend()).download(report,args.output,args.approve_request_sha256,args.max_usd)
            print(json.dumps({'status':result['status'],'output':args.output,'research_ready':False}))
        else:
            result=normalize_job(args.job,args.output,args.bar_latency_ms)
            print(json.dumps({'status':result['status'],'output':args.output,'research_ready':False}))
            return 2 if result['status']=='failed' else 0
        return 0
    except SafeError as e:
        print(json.dumps({'status':'blocked','error_code':str(e)}),file=sys.stderr); return 2
    except Exception:
        # Never expose raw SDK warning/traceback/credential-containing exceptions.
        print('{"status":"blocked","error_code":"operation_failed"}',file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
