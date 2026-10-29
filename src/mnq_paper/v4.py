"""Read-only-first operational entrypoint. Never self-certifies IB Paper mode."""
import argparse
from dataclasses import asdict,replace
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import time
from .core import PaperConfig
from .ib import IBPaper
from .__main__ import ROOT,protected

OUT=ROOT/'reports/paper-v4';PRIVATE=ROOT/'data/paper-v4';UTC=timezone.utc


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
    temporary.chmod(0o600);temporary.replace(path)


def settings():
    path=PRIVATE/'connection.json';stored=json.loads(path.read_text()) if path.exists() else {}
    account=os.environ.get('IB_PAPER_ACCOUNT') or stored.get('account')
    if not account:raise ValueError('Authorized paper account not configured; complete authenticated PAPER login and account selection first')
    return PaperConfig(account,port=int(os.environ.get('IB_PAPER_PORT',stored.get('port',4002))),
      client_id=int(stored.get('client_id',71)),execution_timezone=stored.get('execution_timezone','UTC'))


def status():
    application=ROOT/'tools/ibgateway/runtime/IB Gateway 10.50.app'
    result={'checked_at':datetime.now(UTC).isoformat(),'scope':'OFFLINE_NO_IB_AUTHENTICATION',
      'gateway_installed':application.is_dir(),'gateway_application':str(application),'sdk_source_files_verified':IBPaper.verify_sdk(),
      'account_configured':False,
      'independent_paper_session_evidence_exists':(PRIVATE/'session.json').is_file(),
      'authenticated_ibkr_tests_passed':0,'paper_orders_accepted':0,'strict_news_entries_blocked':True,
      'timestral_enabled':False,'v1_v2_frozen_paths_unchanged':protected()}
    try:settings();result['account_configured']=True
    except ValueError:pass
    listeners={}
    for port in (4002,7497):
        connection=socket.socket();connection.settimeout(.2)
        try:listeners[str(port)]=connection.connect_ex(('127.0.0.1',port))==0
        finally:connection.close()
    result['local_listeners']=listeners
    read_report=OUT/'read-only-report.json'
    if read_report.exists():
        evidence=json.loads(read_report.read_text())
        if evidence.get('scope')=='ACTUAL_IB_READ_ONLY_RESPONSES' and evidence.get('authenticated_protocol') is True:
            result['authenticated_ibkr_tests_passed']=sum(bool(evidence.get(k)) for k in ('authenticated_protocol','configured_account_matched','api_read_only','account_summary_received'))
            result['read_only_evidence_is_historical']=True
    smoke=OUT/'paper-smoke-attempt.json'
    if smoke.exists():
        evidence=json.loads(smoke.read_text())
        if evidence.get('scope')=='REAL_IB_PAPER_TECHNICAL_NOT_FINANCIAL' and evidence.get('paper_mode_confirmed') is True:
            result['paper_acknowledged_roles']=evidence.get('accepted_roles',[])
            result['paper_orders_accepted']=len(evidence.get('accepted_order_ids',[]))
            result['acceptance_evidence_is_historical']=True
    operational=PRIVATE/'paper/health.json'
    health=operational if operational.exists() else PRIVATE/'health.json'
    if health.exists():
        h=json.loads(health.read_text());age=(datetime.now(UTC)-datetime.fromisoformat(h['checked_at'])).total_seconds()
        result['monitor_health']='STALE' if age<0 or age>15 else h['state']
    else:result['monitor_health']='NOT_STARTED'
    result['status']='BLOCKED_LOGIN_OR_ACCOUNT' if not result['account_configured'] or not any(listeners.values()) else 'READ_ONLY_CHECK_REQUIRED_NOT_CERTIFIED'
    save(OUT/'status.json',result);return result


def inspect(month='202612',proof_path=None):
    cfg=settings();broker=IBPaper(cfg,[],operation='read_only',session_proof=proof_path)
    try:
        broker.connect();inventory=broker.read_only_inventory();specs=broker.discover_contracts(month)
        broker.specs={s.symbol:s for s in specs};market=broker.probe_market_data()
        mode_observed=False
        if broker.paper_proof:
            broker.paper_proof.validate(cfg,broker.accounts);mode_observed=True
        report={'checked_at':datetime.now(UTC).isoformat(),'scope':'ACTUAL_IB_READ_ONLY_RESPONSES',
          'authenticated_protocol':True,'configured_account_matched':broker.accounts==[cfg.account],
          'independent_paper_ui_and_account_verified':mode_observed,'api_read_only':broker.api_config['read_only'],
          'account_summary_received':inventory['account_summary_received'],'account_tags_received':inventory['account_tags'],
          'positions_status':inventory['positions_status'],'orders_status':inventory['orders_status'],
          'inventory_error_codes':inventory['error_codes'],'market_data':market,
          'account_identity':hashlib.sha256(cfg.account.encode()).hexdigest(),'paper_order_tests_executed':False,'orders_sent':0,'subscriptions_purchased':0,
          'note':'Protocol authentication and AccountType do not prove Paper; incomplete readonly order visibility is never flat certification'}
        save(PRIVATE/'read-only-inventory.json',inventory);save(PRIVATE/'contracts.json',[asdict(s) for s in specs])
        save(OUT/'read-only-report.json',report);return report
    finally:broker.close()


def watch(month):
    # Read-only observer only. The V3 Runtime remains the sole order/position owner.
    cfg=replace(settings(),client_id=settings().client_id+1);broker=IBPaper(cfg,[]);stopping=[False]
    import signal
    signal.signal(signal.SIGINT,lambda *_:stopping.__setitem__(0,True));signal.signal(signal.SIGTERM,lambda *_:stopping.__setitem__(0,True))
    delay=2
    try:
        while not stopping[0]:
            try:
                broker.connect();delay=2
                while not stopping[0]:
                    broker.heartbeat()
                    save(PRIVATE/'health.json',{'checked_at':datetime.now(UTC).isoformat(),'state':'READ_ONLY_HEARTBEAT_OK',
                      'broker_server_time':broker.server_time,'api_read_only':broker.api_config['read_only'],
                      'paper_mode_certified':False,'opens_enabled':False})
                    for _ in range(25):
                        if stopping[0]:break
                        time.sleep(.2)
            except (ConnectionError,TimeoutError,OSError):
                save(PRIVATE/'health.json',{'checked_at':datetime.now(UTC).isoformat(),'state':'DISCONNECTED_ENTRIES_BLOCKED','opens_enabled':False})
                broker.close()
                for _ in range(delay*5):
                    if stopping[0]:break
                    time.sleep(.2)
                delay=min(60,delay*2)
    finally:
        broker.close();save(PRIVATE/'health.json',{'checked_at':datetime.now(UTC).isoformat(),'state':'STOPPED','opens_enabled':False})


def main():
    import logging
    logging.disable(logging.CRITICAL)
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('status','read-only','watch','paper-smoke','run'),nargs='?',default='status')
    parser.add_argument('--technical-paper',action='store_true');parser.add_argument('--contracts',default=str(PRIVATE/'contracts.json'));parser.add_argument('--kill-file',default=str(PRIVATE/'KILL'))
    parser.add_argument('--state');parser.add_argument('--seconds',type=int,default=180);parser.add_argument('--month',default='202612');parser.add_argument('--session-proof');args=parser.parse_args()
    try:
        if args.command=='status':result=status()
        elif args.command=='read-only':result=inspect(args.month,args.session_proof)
        elif args.command=='run':
            from .__main__ import run_ib
            if args.state is None:args.state=str(PRIVATE/'paper/state.sqlite')
            run_ib(args);return
        elif args.command=='paper-smoke':
            from .smoke import run
            if not 10<=args.seconds<=300:raise ValueError('Bounded technical test duration required')
            result=run(args.session_proof,args.state,args.seconds)
        else:watch(args.month);return
    except (ValueError,TimeoutError,ConnectionError,OSError) as error:
        # Do not print exception text from external services or account values.
        result={'checked_at':datetime.now(UTC).isoformat(),'status':'BLOCKED_NOT_VERIFIED','stage':args.command,
          'failure_type':type(error).__name__,'orders_sent':0 if args.command not in ('paper-smoke','run') else 'UNVERIFIED_SEE_DURABLE_JOURNAL','real_paper_certified':False,
          'action':'Complete authenticated Gateway PAPER login, local Read-Only API and authorized account configuration; then rerun. See OPERATIONS.md.'}
        save(OUT/'last-block.json',result)
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=='__main__':main()
