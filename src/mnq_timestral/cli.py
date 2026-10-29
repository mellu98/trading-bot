"""Explicit local-only commands. Missing audited inputs produce no invented financial metrics."""
import argparse
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import json
import statistics
import sys
import time
from .schema import Request, dumps, loads, UTC
from .evaluation import DEFAULT_PLAN, compare, forecast_dataset, register_experiment, runtime_provenance
from .model import OfficialAdapter, provision, PINS


def output(path, result):
    text=dumps(result)+'\n'
    if path:
        destination=Path(path);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(text)
    print(text,end='')


def parser():
    p=argparse.ArgumentParser(description='Simulation-only MNQ/MES Timestral research. No broker or live capability.')
    commands=p.add_subparsers(dest='command',required=True)
    template=commands.add_parser('plan-template');template.add_argument('--output',required=True)
    register=commands.add_parser('register')
    for flag in ('data','manifest','plan','registration'): register.add_argument('--'+flag,required=True)
    forecast=commands.add_parser('forecast')
    for flag in ('data','manifest','checkpoint-28m','checkpoint-209m','output'): forecast.add_argument('--'+flag,required=True)
    forecast.add_argument('--threads',type=int,default=1)
    research=commands.add_parser('compare')
    for flag in ('data','manifest','forecasts','registration'): research.add_argument('--'+flag)
    research.add_argument('--output',default='reports/comparison.json')
    serve=commands.add_parser('serve');serve.add_argument('--model',choices=PINS,required=True)
    serve.add_argument('--checkpoint',required=True);serve.add_argument('--port',type=int,default=8765)
    serve.add_argument('--threads',type=int,default=1)
    download=commands.add_parser('provision');download.add_argument('--model',choices=PINS,required=True)
    download.add_argument('--destination',required=True)
    download.add_argument('--license-eligibility-reviewed',action='store_true')
    bench=commands.add_parser('benchmark')
    for flag in ('model','checkpoint','request','output'): bench.add_argument('--'+flag,required=True)
    bench.add_argument('--iterations',type=int,default=5);bench.add_argument('--threads',type=int,default=1)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='plan-template': output(args.output,DEFAULT_PLAN);return 0
        if args.command=='register':
            record=register_experiment(args.data,args.manifest,args.plan,args.registration)
            print(dumps({'status':'registered','holdout_sessions':len(record['holdout'])}));return 0
        if args.command=='compare':
            missing=[name for name in ('data','manifest','forecasts','registration') if not getattr(args,name)]
            if missing: raise ValueError('missing required audited inputs: '+', '.join(missing))
            report=compare(args.data,args.manifest,args.forecasts,args.registration)
            output(args.output,report);return 0
        if args.command=='forecast':
            if args.threads<1: raise ValueError('positive CPU thread count required')
            result=forecast_dataset(args.data,args.manifest,{'28M':args.checkpoint_28m,'209M':args.checkpoint_209m},args.output,args.threads)
            print(dumps(result));return 0
        if args.command=='provision':
            print(provision(args.model,args.destination,args.license_eligibility_reviewed));return 0
        if args.command in ('serve','benchmark'):
            if args.threads<1: raise ValueError('positive CPU thread count required')
            import torch
            torch.set_num_threads(args.threads)
            started=time.perf_counter();adapter=OfficialAdapter(args.model,args.checkpoint)
            load_seconds=time.perf_counter()-started
            if args.command=='serve':
                from .service import make_server
                server=make_server(adapter,port=args.port)
                print(f'Simulation-only loopback service on 127.0.0.1:{server.server_port}',flush=True)
                try: server.serve_forever()
                finally: server.server_close()
                return 0
            if args.iterations<1: raise ValueError('positive iteration count required')
            req=Request.from_dict(loads(Path(args.request).read_text()))
            adapter.predict(req)  # explicit warm-up, excluded from latency sample
            results=[adapter.predict(req) for _ in range(args.iterations)]
            times=[p.latency_seconds for p in results]
            output(args.output,{'status':'cpu_benchmark','runtime':runtime_provenance(),'checkpoint':args.model,
                   'model_revision':PINS[args.model].revision,'load_seconds':load_seconds,'warmup_runs':1,
                   'context_length':len(req.bars),'variant':req.variant,'iterations':len(times),
                   'latency_seconds':times,'median_seconds':statistics.median(times),
                   'financial_evidence':False})
            return 0
    except (ValueError,KeyError,TypeError,OSError,ImportError,StopIteration) as error:
        report={'status':'not_evaluated','filter_enabled':False,'execution_quality_gate':False,
                'reason':str(error),'error_type':type(error).__name__,
                'required_evidence':['audited unadjusted actual-contract one-minute MNQ/MES data',
                                     'documented costs and historical calendar/news availability',
                                     'licensed locally verified pinned weights and official forecast logs',
                                     'preregistered session splits and previously untouched holdout'],
                'simulation_only':True}
        # Do not overwrite a forecast log with an error summary after a partially completed run.
        output(args.output if args.command=='compare' else None,report)
        return 2


if __name__=='__main__': sys.exit(main())
