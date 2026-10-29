"""Offline replay CLI. This entry point cannot download data or place broker orders."""
import argparse
from dataclasses import asdict, replace
import csv
import json
from pathlib import Path
import sys

from databento_planner.cache import Cache, atomic_json
from mnq_data.core import file_hash, digest
from mnq_timestral.schema import Bar
from .engine import Config, Replay, summarize, load_state
from .acquire import ROOT, REPORT, CACHE, normalize


def write_rows(path,rows):
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w',newline='') as stream:
        fields=sorted({k for r in rows for k in r}) or ['no_records']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    temporary.replace(path)


def load_real():
    cache=Cache(CACHE);dest=cache.root/'jobs/authorized-oct19-23-2026'
    if not (dest/'provenance.json').exists():
        raise ValueError('Authorized raw data incomplete; offline replay never starts a download')
    quality=normalize(cache,dest,json.loads((dest/'provenance.json').read_text()))
    if quality['rows']!=3900: raise ValueError('Exact five-day data incomplete')
    bars=[]
    with (REPORT/'bars.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            ns=int(row.pop('ts_event_ns'))
            # Raw ns was independently checked before any datetime conversion.
            if ns % (60*10**9): raise ValueError('Non-minute timestamp cannot be losslessly converted')
            for name in ('open','high','low','close','volume'): row[name]=float(row[name])
            bars.append(Bar.from_dict(row))
    return bars


def run(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(REPORT/'baseline-fixed'))
    parser.add_argument('--config',default=str(REPORT/'config.json'))
    parser.add_argument('--news',default=str(REPORT/'news-calendar.json'))
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--exit-variant',choices=['fixed','vwap'])
    parser.add_argument('--slippage-multiplier',type=float,default=1.)
    parser.add_argument('--strict-unattested-news',action='store_true',help='Fail closed when historical point-in-time schedule is not attested')
    parser.add_argument('--stop-after',type=int,help='Synthetic interruption/restart test in event count')
    parser.add_argument('--kill-file',default=str(REPORT/'KILL'))
    parser.add_argument('--verbose',action='store_true')
    args=parser.parse_args(argv)
    config=Config(**json.loads(Path(args.config).read_text()))
    if args.slippage_multiplier<1: raise ValueError('Cost stress cannot reduce the declared baseline')
    config=replace(config,exit_variant=args.exit_variant or config.exit_variant,
                   entry_slippage_ticks=config.entry_slippage_ticks*args.slippage_multiplier,
                   exit_slippage_ticks=config.exit_slippage_ticks*args.slippage_multiplier)
    news=json.loads(Path(args.news).read_text()) if Path(args.news).is_file() else None
    if args.strict_unattested_news and (not news or news.get('point_in_time_publication_attested') is not True): news=None
    output=Path(args.output).resolve()
    if output==ROOT or ROOT not in output.parents: raise ValueError('Output must remain in project workspace')
    output.mkdir(parents=True,exist_ok=True)
    bars=load_real();state_path=output/'checkpoint.json'
    if state_path.exists() and not args.resume:
        previous=load_state(state_path)
        if previous['index']<1950: raise ValueError('Interrupted replay exists; use --resume or another output')
    prior=load_state(state_path) if args.resume and state_path.exists() else None
    replay=Replay(bars,config,news,state=prior,kill_path=args.kill_file)
    def checkpoint(state):
        if state['index']%30==0 or state['index']==len(replay.events) or (args.stop_after and state['index']==args.stop_after):
            atomic_json(state_path,state)
    result=replay.run(stop_after=args.stop_after,checkpoint=checkpoint)
    if replay.index<len(replay.events):
        atomic_json(state_path,replay.state())
        print(json.dumps({'status':'interrupted_for_test','processed_events':replay.index,'checkpoint':str(state_path)}))
        return 0
    summary=summarize(result)
    summary.update(status='technical_replay_complete',dataset='real_Databento_OHLCV',simulation_only=True,
        config=asdict(config),dataset_sha256=replay.dataset_sha256,config_sha256=replay.config_sha256,
        news_sha256=replay.news_sha256,source_sha256=file_hash(Path(__file__).with_name('engine.py')),
        timestral_enabled=False,final_positions=0,working_orders=0,
        limitations=['Five sessions only, not statistical validation or OOS advantage',
            'One-minute typical-price VWAP, not trade-by-trade VWAP',
            'Stops before targets if both touched; precise intrabar order unknown',
            'Minute-close mark-to-market drawdown, not tick-level maximum drawdown',
            'VWAP exit variant freezes signal-time VWAP rounded to nearest tick; not a moving VWAP target',
            'Public fee schedule scenario, not account-specific verified historical charges',
            'Assumed spread/slippage/zero extra bar-close latency, no order-book fills',
            'Scoped current official news schedules, not archived point-in-time calendar',
            'Stricter portfolio one-position cap; deterministic MNQ-first tie priority',
            'This custom replay is not LEAN or an Interactive Brokers paper execution certification'])
    atomic_json(output/'summary.json',summary)
    for name,rows in result.items():
        write_rows(output/(name+'.csv'),rows)
    atomic_json(output/'reproducibility.json',{'summary_sha256':file_hash(output/'summary.json'),
                'trades_sha256':file_hash(output/'trades.csv'),'orders_sha256':file_hash(output/'orders.csv'),
                'decisions_sha256':file_hash(output/'decisions.csv'),'equity_sha256':file_hash(output/'equity.csv')})
    lines=['# Real-data technical replay (simulation only)','',
           '| Metric | Value |','|---|---:|']
    for key in ('trades','gross','fees','execution_cost','net','win_rate','profit_factor','max_drawdown_mark_to_minute_close','ambiguous_intrabar_trades'):
        lines.append(f'| {key} | {summary[key]} |')
    lines+=['','## Limitations']+['- '+x for x in summary['limitations']]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    if args.verbose:
        for trade in replay.trades: print(json.dumps(trade,sort_keys=True))
    print(json.dumps({k:summary[k] for k in ('status','trades','gross','fees','execution_cost','net','win_rate','profit_factor','max_drawdown_mark_to_minute_close','ambiguous_intrabar_trades')},sort_keys=True))
    print('Reports: '+str(output))
    return 0


if __name__=='__main__':
    try: sys.exit(run())
    except (ValueError,KeyError,OSError) as exc:
        print(json.dumps({'status':'simulation_halted','error_type':type(exc).__name__,'reason':str(exc)}))
        sys.exit(2)
