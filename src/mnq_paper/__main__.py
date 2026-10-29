"""Explicit paper-only commands. Missing credentials never become mock success."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import queue
import signal
import time

from mnq_timestral.schema import Bar
from .core import PaperConfig, ContractSpec, Journal, Runtime, TERMINAL
from .mock import MockBroker
from .ib import IBPaper
from .feed import MinuteFeed

ROOT=Path(__file__).resolve().parents[2];REPORT=ROOT/'reports/paper-v3';UTC=timezone.utc


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')


def config(technical=False):
    local=ROOT/'data/paper-v4/connection.json'
    stored=json.loads(local.read_text()) if local.exists() else {}
    account=os.environ.get('IB_PAPER_ACCOUNT') or stored.get('account','')
    if not account:raise ValueError('Set IB_PAPER_ACCOUNT to the exact DU paper account; log into Gateway/TWS paper manually. No password belongs in source/config/logs.')
    return PaperConfig(account=account,port=int(os.environ.get('IB_PAPER_PORT',stored.get('port',7497))),
      client_id=int(os.environ.get('IB_PAPER_CLIENT_ID',stored.get('client_id',71))),execution_timezone=os.environ.get('IB_PAPER_EXECUTION_TIMEZONE',stored.get('execution_timezone')),mode='technical_paper' if technical else 'strict_paper')


def protected():
    manifest=json.loads((REPORT/'frozen-inputs.json').read_text())
    bad=[p for p,h in manifest['files'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    if bad:raise ValueError('Frozen V1/V2 changed: '+bad[0])
    return len(manifest['files'])


def demo(folder):
    """Cached real1m bars, originalVWAP candidate logic, mock external broker."""
    folder=Path(folder)
    if (folder/'state.sqlite').exists() or (folder/'mock-broker.json').exists():
        raise ValueError('Demo output already exists; choose a fresh --output directory (never delete state automatically)')
    source=ROOT/'reports/real-simulation/bars.csv';bars=[]
    for row in csv.DictReader(source.open()):
        ns=int(row.pop('ts_event_ns'))
        if ns%(60*10**9):raise ValueError('Lossy timestamp conversion refused')
        for key in ('open','high','low','close','volume'):row[key]=float(row[key])
        bars.append(Bar.from_dict(row))
    specs=[ContractSpec('MNQ','MNQZ6',1,'20261218'),ContractSpec('MES','MESZ6',2,'20261218')]
    #1/2 are MOCK contract IDs, NOT Databento instrument IDs or real IB conIds.
    cfg=PaperConfig('DU000000',mode='technical_paper');broker=MockBroker(cfg,specs,folder/'mock-broker.json')
    at=[bars[0].start];clock=lambda:at[0]
    journal=Journal(folder/'state.sqlite',cfg,specs);runtime=Runtime(cfg,specs,journal,broker,clock=clock)
    runtime.reconcile(broker.snapshot());restarts=0
    for i,bar in enumerate(bars):
        at[0]=bar.end;broker.match(bar);runtime.reconcile(broker.snapshot());runtime.on_bar(bar)
        runtime.reconcile(broker.snapshot())
        if i==len(bars)//2:
            before=json.loads(json.dumps(runtime.state));journal.close()
            broker=MockBroker(cfg,specs,folder/'mock-broker.json')
            journal=Journal(folder/'state.sqlite',cfg,specs);runtime=Runtime(cfg,specs,journal,broker,clock=clock)
            assert runtime.state==before and not runtime.ready
            runtime.reconcile(broker.snapshot());restarts+=1
    runtime.stop('demo_shutdown');runtime.reconcile(broker.snapshot())
    if any(p['quantity'] for p in runtime.state['positions'].values()):
        raise ValueError('Demo ended with outstanding position; inspect state, no fabricated close')
    result={'status':'MOCK_END_TO_END_ONLY_NOT_IB_PAPER_CERTIFICATION','bars_received':len(bars),
      'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'strategy':'Unchanged V1 VWAP/Z-score2.5, unapproved technical test only',
      'decisions':len(runtime.state['decisions']),'accepted_decisions':sum(d['accepted'] for d in runtime.state['decisions']),
      'executions':len(runtime.state['executions']),'orders':len(runtime.state['orders']),
      'exit_fills':{role:sum(e['quantity'] for e in runtime.state['executions'].values() if runtime.state['orders'][str(e['order_id'])]['role']==role) for role in ('stop','target','flatten')},
      'restarts_verified':restarts,'ending_positions':{s:p['quantity'] for s,p in runtime.state['positions'].items()},
      'halt':runtime.state['halt'],'v1_v2_frozen_files_unchanged':protected(),'real_broker_connected':False,
      'live_orders':0,'purchases':0,'financial_validation':False,'mock_conids_not_real':True}
    write(folder/'state-export.json',runtime.state);write(folder/'summary.json',result);journal.close()
    print(json.dumps(result,indent=2))


def discover(args):
    cfg=config();broker=IBPaper(cfg,[])
    try:
        broker.connect()
        from ibapi.contract import Contract
        for i,symbol in enumerate(('MNQ','MES'),1000):
            c=Contract();c.symbol=symbol;c.secType='FUT';c.exchange='CME';c.currency='USD';c.lastTradeDateOrContractMonth=args.month
            broker.app.reqContractDetails(i,c)
        broker._wait(lambda:all(i in broker.details_done for i in (1000,1001)))
        specs=[]
        for i,symbol in enumerate(('MNQ','MES'),1000):
            details=broker.details.get(i,[])
            if len(details)!=1:raise ValueError('Expected exactly one dated quarterly contract per root')
            c=details[0].contract
            specs.append(asdict(ContractSpec(symbol,c.localSymbol,c.conId,c.lastTradeDateOrContractMonth[:8])))
        if Path(args.contracts).exists():raise ValueError('Refuse to overwrite contract identity file')
        write(args.contracts,specs)
        print(json.dumps({'status':'OFFICIAL_CONTRACT_METADATA_ONLY','file':str(Path(args.contracts).resolve()),'orders':0}))
    finally:broker.close()


def rearm_ib(args):
    cfg=config(args.technical_paper);specs=[ContractSpec(**s) for s in json.loads(Path(args.contracts).read_text())]
    if not Path(args.state).is_file():raise ValueError('Existing persistent state required; never create a reset account')
    journal=Journal(args.state,cfg,specs);broker=IBPaper(cfg,specs,operation='paper_orders' if args.technical_paper else 'read_only',session_proof=args.session_proof)
    try:
        broker.connect()
        if broker.paper_proof is None:raise ValueError('Independent Paper UI/account proof required for rearm')
        broker.paper_proof.validate(cfg,broker.accounts)
        runtime=Runtime(cfg,specs,journal,broker,kill_path=args.kill_file)
        runtime.rearm(broker.snapshot())
        print('Paper re-armed explicitly after flat/no-orders snapshot; all risk counters preserved; no order sent')
    finally:broker.close();journal.close()


def run_ib(args):
    cfg=config(args.technical_paper);specs=[ContractSpec(**s) for s in json.loads(Path(args.contracts).read_text())]
    if {s.symbol for s in specs}!={'MNQ','MES'} or len(specs)!=2:raise ValueError('Exactly one contract perMNQ/MES required')
    journal=Journal(args.state,cfg,specs);broker=IBPaper(cfg,specs,operation='paper_orders' if args.technical_paper else 'read_only',session_proof=args.session_proof)
    runtime=Runtime(cfg,specs,journal,broker,kill_path=args.kill_file);feed=MinuteFeed(specs)
    stop=[False]
    signal.signal(signal.SIGINT,lambda *_:stop.__setitem__(0,True));signal.signal(signal.SIGTERM,lambda *_:stop.__setitem__(0,True))
    backoff=2;last_snapshot=0;last_heartbeat=0;connected=False
    try:
        while not stop[0]:
            try:
                if not connected:
                    broker.connect();runtime.reconcile(broker.snapshot());broker.subscribe();connected=True;backoff=2;feed=MinuteFeed(specs)
                    print('Authenticated API identity matched; independent Paper evidence required for orders; strategy UNAPPROVED; mode='+cfg.mode,flush=True)
                needs_snapshot=False
                try:event=broker.events.get(timeout=.2)
                except queue.Empty:event=None
                if event:
                    kind=event['type']
                    if kind=='disconnect':raise ConnectionError('Connection closed')
                    if kind=='execution':
                        runtime.ready=False;needs_snapshot=True
                        order=runtime.state['orders'].get(str(event['value']['order_id']))
                        if order and event['value']['quantity']<order['quantity']:runtime.stop('partial_fill')
                    elif kind=='commission':runtime.on_commission(event['value']);needs_snapshot=True
                    elif kind=='status':runtime.on_status(event);needs_snapshot=True
                    elif kind=='error':
                        code=event['code']
                        if code in (1100,1101,1102,1300,502,504):raise ConnectionError('IB connectivity changed')
                        runtime.stop('broker_error_'+str(code));needs_snapshot=True
                    elif kind=='five_seconds':
                        try:bar=feed.push(event,datetime.now(UTC))
                        except ValueError:runtime.stop('data_gap');bar=None;needs_snapshot=True
                        if bar:runtime.on_bar(bar);needs_snapshot=True
                if time.monotonic()-last_heartbeat>5:
                    broker.heartbeat();last_heartbeat=time.monotonic()
                runtime.watchdog()
                if needs_snapshot or time.monotonic()-last_snapshot>5 or runtime.state['stopping']:
                    runtime.reconcile(broker.snapshot());last_snapshot=time.monotonic()
                if not broker.app.isConnected():raise ConnectionError('Lost IB socket')
            except (ConnectionError,TimeoutError,OSError):
                runtime.disconnected();broker.close();connected=False
                print('Paper disconnected: entries blocked; reconnect delay='+str(backoff)+'s',flush=True)
                deadline=time.monotonic()+backoff
                while time.monotonic()<deadline and not stop[0]:time.sleep(.2)
                backoff=min(60,backoff*2)
            write(Path(args.state).parent/'health.json',{'checked_at':datetime.now(UTC).isoformat(),'runtime_pid':os.getpid(),
              'state':'PAPER_PROTOCOL_READY' if connected and runtime.ready else 'BLOCKED_ENTRIES','mode':cfg.mode,'broker_protocol_connected':connected,'reconciled_ready':runtime.ready,
              'halt':runtime.state['halt'],'last_data':runtime.last_data.isoformat() if runtime.last_data else None,
              'open_positions':sum(abs(p['quantity']) for p in runtime.state['positions'].values()),'strategy_approved':False})
    finally:
        runtime.stop('operator_shutdown')
        # Best-effort close only after broker confirms cancellations; never claim
        # flat when disconnected. Native protective orders must remain visible.
        deadline=time.monotonic()+10;shutdown_flat=False
        while connected and time.monotonic()<deadline:
            try:
                snapshot=broker.snapshot();runtime.reconcile(snapshot)
            except Exception:break
            if snapshot['accounts']==[cfg.account] and not any(snapshot['positions'].values()) and not snapshot['orders']:
                shutdown_flat=True;break
            time.sleep(.2)
        write(Path(args.state).parent/'shutdown.json',{'halt':runtime.state['halt'],'positions_known':runtime.state['positions'],
          'flat_confirmed':shutdown_flat,
          'instruction':'If not flat-confirmed, inspect ONLY the paper TWS account manually; never assume local shutdown closed remote exposure'})
        write(Path(args.state).parent/'health.json',{'checked_at':datetime.now(UTC).isoformat(),'runtime_pid':os.getpid(),'state':'STOPPED','opens_enabled':False})
        broker.close();journal.close()


def main():
    logging.disable(logging.CRITICAL)
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    demo_parser=sub.add_parser('demo');demo_parser.add_argument('--output',default=str(REPORT/'demo'))
    sub.add_parser('preflight')
    discovery=sub.add_parser('ib-contracts');discovery.add_argument('--month',required=True);discovery.add_argument('--contracts',required=True)
    ib=sub.add_parser('ib-paper');ib.add_argument('--contracts',required=True);ib.add_argument('--technical-paper',action='store_true')
    ib.add_argument('--session-proof');ib.add_argument('--state',default=str(ROOT/'data/paper-v3/ib/state.sqlite'));ib.add_argument('--kill-file',default=str(ROOT/'data/paper-v3/KILL'))
    rearm=sub.add_parser('ib-rearm');rearm.add_argument('--contracts',required=True);rearm.add_argument('--state',required=True)
    rearm.add_argument('--session-proof');rearm.add_argument('--technical-paper',action='store_true');rearm.add_argument('--kill-file',default=str(ROOT/'data/paper-v3/KILL'))
    args=parser.parse_args()
    if args.command=='demo':demo(args.output)
    elif args.command=='preflight':
        present=bool(os.environ.get('IB_PAPER_ACCOUNT'))
        if present:config()
        print(json.dumps({'status':'BLOCKED_REAL_PAPER_NOT_VERIFIED','paper_account_configured':present,
          'sdk':'official1051.01','real_broker_verified':False,'no_purchase':True,'frozen_files_verified':protected(),
          'next':'Log into TWS/Gateway PAPER; set exactDUaccount; enable local API; discover actualIBconIds. DatabentoIID is NOT an IBconId.'},indent=2))
    elif args.command=='ib-contracts':discover(args)
    elif args.command=='ib-rearm':rearm_ib(args)
    else:run_ib(args)


if __name__=='__main__':main()
