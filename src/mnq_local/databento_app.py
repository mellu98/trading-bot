"""Bounded licensed Databento read-only trial; execution is always local/off."""
import argparse,json,queue,signal,threading,time,subprocess,os,re
from datetime import datetime,timedelta
from pathlib import Path
from mnq_timestral.schema import NY,UTC
from mnq_paper.core import ContractSpec
from .replay import ROOT,ReplayOptions,load_session,atomic_json
from .dashboard import Dashboard,Handler,View
from .databento_live import validate_authorization,connect_sdk
from .databento_paper import DatabentoPaperSession

CONTRACTS=ROOT/'reports/databento-live/contracts.json'
AUTHORIZATION=ROOT/'reports/databento-live/authorization.json'
LIVE_KEY_SERVICE='mnq-databento-personal-live-api-key'

def load_live_key(*,runner=subprocess.run):
    """Dedicated personal live binding only; never historical or environment fallback."""
    try:
        result=runner(['security','find-generic-password','-a',os.environ['USER'],
                       '-s',LIVE_KEY_SERVICE,'-w'],capture_output=True,check=False,timeout=10)
        value=result.stdout
        if value.endswith(b'\n'):value=value[:-1]
        if result.returncode or not re.fullmatch(rb'db-[A-Za-z0-9]{29}',value):
            raise PermissionError('dedicated_personal_live_key_required')
        return value.decode('ascii')
    except (OSError,subprocess.SubprocessError,KeyError):
        raise PermissionError('dedicated_personal_live_key_required') from None


def specs_from_file(path):
    doc=json.loads(Path(path).read_text())
    if doc['dataset']!='GLBX.MDP3':raise ValueError('wrong_dataset')
    return tuple(ContractSpec(**row) for row in doc['contracts'])

def context_start(day):
    at=datetime.strptime(day,'%Y-%m-%d').replace(hour=9,minute=30,tzinfo=NY).astimezone(UTC)
    return int(at.timestamp())*10**9


class LiveHandler(Handler):
    def do_GET(self):
        if self.path!='/':return super().do_GET()
        if not self._valid_host():return self.reply(403,{'error':'Host rejected'})
        page=Path(__file__).with_name('dashboard.html').read_text().replace('__TOKEN__',self.server.control_token)
        for old,new in [('TRADING BOT · Local Replay','TRADING BOT · CME Live / Local Simulation'),
            ('OFFLINE · NO LIVE ROUTING','CME DATA · LOCAL ORDERS ONLY · NO BROKER'),
            ('01 · HISTORICAL REPLAY','01 · DATABENTO CME LIVE DATA'),('Real CME input · historical clock','Authenticated feed · never broker execution'),
            ('Historical UTC clock:','Observed UTC clock:'),('One-minute OHLC cannot prove intrabar execution order.','Live fills are synthetic post-submission BBO observations, not exchange executions.'),
            ('last observed historical price','last observed simulation mark'),('Data: owned GLBX.MDP3 / ohlcv-1m','Data: licensed GLBX.MDP3 / trades + MBP-1'),
            ('el(\'progress\').max=r.bars_total','el(\'progress\').max=Math.max(1,r.bars_processed)'),
            ('${r.bars_processed}/${r.bars_total} bars','${r.bars_processed} completed bars')]:page=page.replace(old,new)
        page=page.replace('Broker: NOT CONNECTED','Broker: NONE / LOCAL SIMULATOR ONLY')
        page=page.replace('Timestral: DISABLED`','Timestral: DISABLED\\nEntries enabled: ${r.simulated_entries_enabled}\\nFeed: ${JSON.stringify(r.source)}`')
        return self.reply(200,page,'text/html')


def main(argv=None,*,clock_ns=time.time_ns):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('preflight','app','offline'))
    parser.add_argument('--contracts',default=str(CONTRACTS));parser.add_argument('--authorization',default=str(AUTHORIZATION))
    parser.add_argument('--session',default=datetime.now(NY).date().isoformat());parser.add_argument('--seconds',type=int,default=600)
    parser.add_argument('--port',type=int,default=8768);parser.add_argument('--run-dir')
    parser.add_argument('--strategy',choices=('vwap_v1','orb_v2','sweep_mss_v2'),default='vwap_v1')
    parser.add_argument('--technical-simulation',action='store_true',help='Offline owned OHLCV only; never accepted for live data')
    args=parser.parse_args(argv)
    if args.technical_simulation and args.command!='offline':parser.error('Technical simulation is offline only')
    specs=specs_from_file(args.contracts);anchor=context_start(args.session)
    if args.command!='offline':
        try:
            grant=json.loads(Path(args.authorization).read_text());validate_authorization(grant,specs,args.seconds,clock_ns())
            if anchor>clock_ns() or clock_ns()-anchor>=86400*10**9:raise PermissionError('current_intraday_cash_context_required')
        except (PermissionError,ValueError,KeyError,OSError,TypeError):
            print(json.dumps({'status':'BLOCKED','phase':'LICENSE_ENTITLEMENT_AND_COST_AUTHORIZATION',
                'reason':'verified_scoped_live_authorization_required','network_connections':0,'simulated_orders_enabled':False,'real_money_routing':False}))
            return 2
        if args.command=='preflight':
            print(json.dumps({'status':'LOCAL_AUTHORIZATION_VALID_NOT_LIVE_VERIFIED','network_connections':0,'simulated_orders_enabled':False,'real_money_routing':False}));return 0
    folder=Path(args.run_dir) if args.run_dir else ROOT/'data/databento-live'/('offline-' if args.command=='offline' else 'live-')/(args.session+'-'+args.strategy)
    options=ReplayOptions(session=args.session,strategy=args.strategy,strict=not args.technical_simulation)
    session=DatabentoPaperSession(folder,options,specs,context_start_ns=anchor,offline=args.command=='offline',technical_simulation=args.technical_simulation)
    client=server=None;stopped=threading.Event()
    try:
        if args.command=='offline':
            for bar in load_session(args.session)[0]:session.ingest_historical(bar)
            session.export();print(json.dumps(session.report()));return 0
        # Gate passed before reading an existing secret or constructing the SDK.
        trial_start=clock_ns()
        client,inbox,failed=connect_sdk(session.provider,grant,args.seconds,trial_start,key_loader=load_live_key)
        view=View();commands=queue.Queue();server=Dashboard(('127.0.0.1',args.port),view,commands,folder);server.RequestHandlerClass=LiveHandler
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stopped.set())
        deadline=min(trial_start+args.seconds*10**9,grant['expires_ns']);last_health=0;paused=False;was_connected=True
        print('CME LIVE DATA / LOCAL SIMULATION — entries OFF; no broker route',flush=True)
        while not stopped.is_set() and clock_ns()<deadline:
            if failed.is_set():session.disconnected('callback_queue_or_sdk_callback_failure');break
            connected=client.is_connected()
            if was_connected and not connected:session.disconnected('sdk_disconnected')
            was_connected=connected
            try:
                items=[inbox.get(timeout=.1)]
                while len(items)<256:
                    try:items.append(inbox.get_nowait())
                    except queue.Empty:break
                batch=[]
                for kind,record,received in items:
                    if kind=='reconnect':
                        if batch:session.ingest_batch(batch);batch=[]
                        session.disconnected('sdk_reconnected_gap_requires_review')
                    else:batch.append((record,received,clock_ns))
                if batch:session.ingest_batch(batch)
            except queue.Empty:pass
            while not commands.empty():
                action=commands.get_nowait()
                if action=='kill':session.kill();paused=True
                elif action=='pause':paused=True
                elif action=='resume':paused=False
            # Pausing never drops raw feed events or disables protective exits.
            session.broker.entries_enabled=False
            if time.monotonic()-last_health>=1:
                session.tick(clock_ns());session.export();report=session.report()
                report.update(feed_connected=connected,entries_paused=paused,actual_live_access_verified=bool(session.provider.state['counts'].get('quote')))
                view.update(report,session.trades(),session.runtime.state['decisions'],session.progress['equity'],'OBSERVING_ENTRIES_DISABLED')
                atomic_json(folder/'health.json',{'pid':__import__('os').getpid(),'report':report,'at_ns':clock_ns()});last_health=time.monotonic()
        return 0
    except Exception:
        print(json.dumps({'status':'BLOCKED','phase':'SDK_OR_RUNTIME','reason':'controlled_failure_no_automatic_auth_retry','real_money_routing':False}));return 2
    finally:
        if client:
            try:client.stop();client.block_for_close(timeout=5)
            except Exception:client.terminate()
        session.export();session.close()
        if server:server.shutdown();server.server_close()

if __name__=='__main__':raise SystemExit(main())
