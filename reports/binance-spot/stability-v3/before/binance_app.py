"""Finite one-entry local Spot paper test plus an observation-only dashboard."""
from dataclasses import asdict
from pathlib import Path
import argparse,asyncio,csv,hashlib,json,os,queue,signal,threading,time,sqlite3
from contextlib import contextmanager
from collections import deque
import aiohttp
from .binance_spot import SpotConfig,SpotSpec,SpotRuntime,PublicREST,Feed,WS,SYMBOL,dec,utc
from .replay import AtomicJournal,atomic_json,ROOT
from .dashboard import Dashboard,View

SOURCE_PATHS=('src/mnq_local/binance_spot.py','src/mnq_local/binance_app.py','src/mnq_local/dashboard.html','tests_local/test_binance_spot.py','tests_local/test_binance_stability.py','run-binance-paper.sh')

def hashes():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCE_PATHS}

class PipelineMetrics:
    """Bounded rolling distributions, lifetime counts/max; milliseconds, not network latency."""
    def __init__(self,limit=20000):
        self.limit=limit;self.lock=threading.Lock();self.samples={};self.counts={};self.maxima={};self.counters={}
    def record(self,name,ms):
        with self.lock:
            self.samples.setdefault(name,deque(maxlen=self.limit)).append(ms)
            self.counts[name]=self.counts.get(name,0)+1;self.maxima[name]=max(ms,self.maxima.get(name,0))
    def count(self,name):
        with self.lock:self.counters[name]=self.counters.get(name,0)+1
    def snapshot(self):
        with self.lock:
            samples={k:list(v) for k,v in self.samples.items()};counts=dict(self.counts);maxima=dict(self.maxima);counters=dict(self.counters)
        stages={}
        for k,values in samples.items():
            values.sort();n=len(values)
            stages[k]={'count':counts[k],'retained':n,'p50_ms':values[int((n-1)*.5)],'p95_ms':values[int((n-1)*.95)],'p99_ms':values[int((n-1)*.99)],'max_ms':maxima[k]}
        return {'at':utc(),'stages':stages,'counters':counters,'quantiles':'bounded last samples; counts/max lifetime','limit_per_stage':self.limit}
    @contextmanager
    def measure(self,name):
        start=time.monotonic_ns()
        try:yield
        finally:self.record(name,(time.monotonic_ns()-start)/1e6)


class ObservationWorker:
    """One bounded noncritical I/O lane. Payloads must be immutable owner snapshots."""
    def __init__(self,metrics):
        self.metrics=metrics;self.jobs=queue.Queue(16);self.error=None
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
    def submit(self,name,job):
        if self.error:raise RuntimeError('observation_worker_failed') from self.error
        try:self.jobs.put_nowait((name,job,time.monotonic_ns()))
        except queue.Full:
            self.metrics.count('io_queue_overflow');raise ConnectionError('bounded_observation_queue_overflow') from None
    def _run(self):
        while True:
            value=self.jobs.get()
            try:
                if value is None:return
                name,job,queued=value;self.metrics.record('io_queue_wait',(time.monotonic_ns()-queued)/1e6)
                with self.metrics.measure(name):job()
            except Exception as exc:self.error=exc;self.metrics.count('io_worker_errors')
            finally:self.jobs.task_done()
    def close(self):
        self.jobs.put(None);self.thread.join()


class ObservedJournal(AtomicJournal):
    """Critical writes stay owner-thread AtomicJournal; worker gets its own connection."""
    def __init__(self,path,*args,metrics,**kwargs):
        self.write_lock=threading.RLock();self.revision=0;self.path=Path(path);self.metrics=metrics
        super().__init__(path,*args,**kwargs)
    @contextmanager
    def owner_lock(self):
        start=time.monotonic_ns();self.write_lock.acquire()
        self.metrics.record('critical_lock_wait',(time.monotonic_ns()-start)/1e6)
        try:yield
        finally:self.write_lock.release()
    def save(self,kind,body=None):
        if self.pending is not None:return super().save(kind,body)
        with self.owner_lock(),self.metrics.measure('critical_journal_save'):
            self.revision+=1;return super().save(kind,body)
    @contextmanager
    def bar_transaction(self):
        with self.owner_lock(),self.metrics.measure('critical_atomic_transaction'):
            self.revision+=1
            with super().bar_transaction():yield
    def capture(self):
        with self.metrics.measure('owner_state_encode'):
            return json.dumps(self.state,sort_keys=True,allow_nan=False),self.revision
    def checkpoint(self,encoded,revision):
        # Do not touch owner db/state in this thread. A newer critical revision wins.
        with self.write_lock:
            if revision!=self.revision:
                self.metrics.count('checkpoint_superseded');return False
            with self.metrics.measure('sqlite_checkpoint'):
                db=sqlite3.connect(self.path)
                try:
                    db.execute('PRAGMA synchronous=FULL')
                    with db:
                        db.execute('INSERT OR REPLACE INTO snapshot VALUES(1,?)',(encoded,))
                        db.execute('INSERT INTO journal(kind,body) VALUES(?,?)',('spot_public_batch','{}'))
                finally:db.close()
        return True


class MeasuredView(View):
    def __init__(self,metrics):super().__init__();self.metrics=metrics
    def read(self):
        with self.metrics.measure('dashboard_read'):return super().read()


def enqueue_observation(worker,folder,r,feed,view,phase,metrics):
    with metrics.measure('owner_snapshot_prepare'):
        r.spot['last_quote_snapshot']=dict(r.quote) if r.quote else None
        r.spot['feed_checkpoint']=feed.certificate()
        encoded,revision=r.journal.capture()
        # JSON freezes all references before handing ownership to the worker.
        payload=json.dumps({'report':report(r,feed),'phase':phase,'at':utc(),
            'trades':[r.spot['roundtrip']] if r.spot['roundtrip'] else [],
            'decisions':r.state['decisions'][-20:],'equity':r.spot['equity'][-3600:]},allow_nan=False)
    journal=r.journal
    def publish():
        journal.checkpoint(encoded,revision)
        value=json.loads(payload);rep=value['report']
        with metrics.measure('dashboard_snapshot'):
            view.update(rep,value['trades'],value['decisions'],value['equity'],value['phase'])
            with view.lock:view.value['updated_at']=value['at']
        with metrics.measure('filesystem_export'):
            atomic_json(folder/'status.json',rep);atomic_json(folder/'state-export.json',json.loads(encoded))
            atomic_json(folder/'pipeline-metrics.json',metrics.snapshot())
            if value['trades']:atomic_json(folder/'roundtrip.json',value['trades'][0])
    worker.submit('observation_publish',publish)


def report(r,feed):
    risk=r._mark_risk();p=r.spot['position'];net=dec(str(r.net()));equity=net+dec(str(risk.unrealized));q=r.quote
    return {'mode':'LIVE_PUBLIC_DATA_LOCAL_PAPER','symbol':SYMBOL,'execution':'LOCAL_ONLY_NO_BINANCE_ORDERS','strategy':'ONE_TECHNICAL_TEST_NOT_ECONOMIC_STRATEGY',
      'session':'24/7 UTC Spot','replay_time':utc(),'bars_processed':feed.stats['closed_bars'],'bars_total':feed.stats['closed_bars'],
      'trades':r.spot['sell_count'],'orders':len(r.state['orders']),'gross':r.spot['gross'],'fees':r.spot['fees'],'net':str(net),
      'cash':r.spot['cash'],'virtual_equity':str(dec(r.config.virtual_cash)+equity),'max_drawdown':r.spot['max_drawdown'],
      'positions':r.state['positions'],'position':p,'quote':q,'halt':r.state['halt'],'pending_exit':r.spot['pending_exit'],
      'budget_spent':r.spot['budget_spent'],'buy_count':r.spot['buy_count'],'sell_count':r.spot['sell_count'],'restart_count':r.spot['restart_count'],
      'working_orders':[o for o in r.state['orders'].values() if o['status']=='Submitted'],'events':r.spot['events'][-20:],
      'feed_live':feed.current_stream_ok and r.quote_fresh(for_exit=True),'certificate':r.certificate,'entry_certificate':r.spot.get('entry_certificate'),'feed_metrics':feed.certificate(),
      'strict_news':'BLOCKED_UNCERTIFIED','strategy_approved':False,'timestral':'DISABLED','broker_connected':False,'ambiguities':0,
      'accepted':len(r.state['decisions']),'rejected':0,'observe_only':r.spot['budget_spent'] and p is None,'costs':asdict(r.config),
      'attribution':'Market data: Binance Spot public market-data-only API. Local noncommercial technical paper research only; no commercial/live license claim.'}

def process_public_event(r,feed,item,received_ns,received_mono,metrics=None):
    """Hot path: observe every event, protect every fresh quote, no full snapshot.

    Critical local intents/fills retain their own existing AtomicJournal
    transactions. Noncritical feed progress is coalesced once per second.
    """
    start=time.monotonic_ns();accepted=feed.process(item,received_ns,received_mono)
    if metrics:metrics.record('feed_process',(time.monotonic_ns()-start)/1e6)
    if accepted and item['stream']=='btcusdt@bookTicker' and r.spot['position']:
        start=time.monotonic_ns();r.protect()
        if metrics:metrics.record('protection_hook',(time.monotonic_ns()-start)/1e6)
    return accepted


def persist_observation(r,feed):
    r.spot['last_quote_snapshot']=dict(r.quote) if r.quote else None
    r.spot['feed_checkpoint']=feed.certificate()
    r.journal.save('spot_public_batch',{'at':utc(),'last_book_id':r.spot['last_book_id'],
        'last_trade_id':r.spot['last_trade_id'],'closed_candle':feed.closed['t'] if feed.closed else None})


def export(folder,r,feed,view,phase):
    rep=report(r,feed);trades=[r.spot['roundtrip']] if r.spot['roundtrip'] else []
    view.update(rep,trades,r.state['decisions'],r.spot['equity'][-3600:],phase)
    atomic_json(folder/'status.json',rep);atomic_json(folder/'state-export.json',r.state)
    if trades:
        with (folder/'trades.csv').open('w',newline='') as f:
            rows=[{k:v for k,v in t.items() if not isinstance(v,dict)} for t in trades]
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        atomic_json(folder/'roundtrip.json',r.spot['roundtrip'])

async def run(args):
    folder=Path(args.report).resolve();folder.mkdir(parents=True,exist_ok=True);config=SpotConfig()
    protocol=json.loads((folder/'protocol.json').read_text())
    if protocol['source_sha256']!=hashes() or protocol['config']!=asdict(config):raise ValueError('Locked Spot code/config changed')
    metrics=PipelineMetrics();worker=ObservationWorker(metrics)
    evidence=(folder/'public-rest-evidence.jsonl').open('a',buffering=1);raw=(folder/'public-ws-events.jsonl').open('a',buffering=65536)
    trace=aiohttp.TraceConfig()
    async def reject_redirect(*_):raise ValueError('Public routing redirects forbidden')
    trace.on_request_redirect.append(reject_redirect)
    session=aiohttp.ClientSession(trust_env=False,cookie_jar=aiohttp.DummyCookieJar(),trace_configs=[trace]);journal=None;server=None
    def persist_rest(item):
        with metrics.measure('owner_rest_encode'):encoded=json.dumps(item,sort_keys=True)+'\n'
        worker.submit('rest_evidence_write',lambda:evidence.write(encoded))
    http=PublicREST(session,persist_rest)
    try:
        metadata=await http.get('/api/v3/exchangeInfo',symbol=SYMBOL);spec=SpotSpec.from_exchange(metadata['data'])
        journal=ObservedJournal(args.journal,config,[spec],metrics=metrics,lock_root=Path(args.journal).parent/'locks');r=SpotRuntime(config,spec,journal)
        view=MeasuredView(metrics);commands=queue.Queue();server=Dashboard(('127.0.0.1',args.port),view,commands,folder)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        feed=Feed(r);paused=False;stop=asyncio.Event();loop=asyncio.get_running_loop()
        for sig in (signal.SIGINT,signal.SIGTERM):loop.add_signal_handler(sig,stop.set)
        atomic_json(folder/'process.json',{'pid':os.getpid(),'port':server.server_port,'journal':str(Path(args.journal).resolve()),'started_at':utc(),'restart_count':r.spot['restart_count'],'mode':'LIVE_PUBLIC_DATA_LOCAL_PAPER'})
        print('PUBLIC_SPOT_READY',os.getpid(),server.server_port,'journal',args.journal,flush=True)
        async def consumer(inbox):
            last_export=0;raw_batch=[]
            while not stop.is_set():
                try:item,received,mono=await asyncio.wait_for(inbox.get(),timeout=.2)
                except asyncio.TimeoutError:item=None
                iteration_start=time.monotonic_ns()
                if worker.error:raise RuntimeError('observation_worker_failed') from worker.error
                if item is not None:
                    metrics.record('queue_wait',(time.monotonic_ns()-mono)/1e6)
                    raw_batch.append(json.dumps({'received_ns':received,'received_mono_ns':mono,'message':item},sort_keys=True)+'\n')
                    process_public_event(r,feed,item,received,mono,metrics)
                    if len(raw_batch)>=256:
                        chunk=''.join(raw_batch);raw_batch.clear()
                        worker.submit('raw_write',lambda chunk=chunk:(raw.write(chunk),raw.flush()))
                while not commands.empty():
                    action=commands.get_nowait()
                    if action=='pause':r.spot['paused']=True
                    elif action=='resume':r.spot['paused']=False
                    elif action=='kill':r.stop('kill');r.request_exit('kill')
                    if action=='pause':r.spot['paused']=True
                if r.spot['position']:
                    if (r.quote is not None and not r.quote_fresh(for_exit=True)) or (r.quote is None and time.monotonic_ns()-feed.started>2_000_000_000):r.request_exit('stale_feed')
                    r.protect()
                with metrics.measure('certificate_hook'):r.certificate=feed.certificate()
                r.ready=r.certificate['passed'] and not r.spot.get('paused',False)
                if not r.spot['budget_spent'] and r.ready:
                    if r.submit_technical():
                        chunk=''.join(raw_batch);raw_batch.clear()
                        worker.submit('raw_write',lambda chunk=chunk:(raw.write(chunk),raw.flush(),os.fsync(raw.fileno())))
                        print('LOCAL_BUY_COMMITTED',json.dumps(r.spot['position']),flush=True)
                now=time.monotonic()
                if now-last_export>=1:
                    risk=r._mark_risk();r.spot['equity'].append({'at':utc(),'equity':r.net()+risk.unrealized});r.spot['equity']=r.spot['equity'][-3600:]
                    phase='OBSERVE_ONLY' if r.spot['budget_spent'] and not r.spot['position'] else 'OPEN_PROTECTED' if r.spot['position'] else 'CERTIFYING_FEED'
                    chunk=''.join(raw_batch);raw_batch.clear()
                    worker.submit('raw_write',lambda chunk=chunk:(raw.write(chunk),raw.flush()))
                    enqueue_observation(worker,folder,r,feed,view,phase,metrics);last_export=now
                    if r.spot['roundtrip'] and not r.spot.get('exit_announced'):
                        r.spot['exit_announced']=True;journal.save('spot_roundtrip_completed');print('LOCAL_SELL_FLAT',json.dumps(r.spot['roundtrip']),flush=True)
                metrics.record('consumer_iteration',(time.monotonic_ns()-iteration_start)/1e6)
        async def receive(ws,inbox):
            waiting=time.monotonic_ns()
            async for msg in ws:
                metrics.record('ws_receive_wait_provider_idle_included',(time.monotonic_ns()-waiting)/1e6)
                if msg.type==aiohttp.WSMsgType.TEXT:
                    captured=time.time_ns();mono=time.monotonic_ns();item=json.loads(msg.data)
                    metrics.count('ws_messages_received')
                    metrics.record('ws_decode',(time.monotonic_ns()-mono)/1e6)
                    try:inbox.put_nowait((item,captured,mono))
                    except asyncio.QueueFull:
                        metrics.count('ws_queue_overflow');raise ConnectionError('bounded_queue_overflow') from None
                elif msg.type in (aiohttp.WSMsgType.ERROR,aiohttp.WSMsgType.CLOSED):raise ConnectionError('public_stream_closed')
                waiting=time.monotonic_ns()
        async def certify():
            while not stop.is_set():
                try:
                    if feed.current_stream_ok:
                        start=time.monotonic_ns();await feed.compare_rest(http)
                        metrics.record('rest_compare_network_included',(time.monotonic_ns()-start)/1e6)
                except Exception as exc:
                    feed.rest_checks={'passed':False,'error_type':type(exc).__name__,'checked_at':utc()}
                await asyncio.sleep(4)
        async def loop_probe():
            while not stop.is_set():
                target=loop.time()+.02;await asyncio.sleep(.02)
                metrics.record('event_loop_lag',max(0,loop.time()-target)*1000)
        probe_task=asyncio.create_task(loop_probe())
        inbox=asyncio.Queue(maxsize=512);task=asyncio.create_task(consumer(inbox));cert_task=asyncio.create_task(certify());delay=1
        try:
            while not stop.is_set():
                try:
                    async with session.ws_connect(WS,heartbeat=15,timeout=aiohttp.ClientWSTimeout(ws_receive=15,ws_close=5),autoping=True,max_msg_size=1_000_000) as ws:
                        feed.connected();journal.save('public_stream_connected',{'origin':'wss://data-stream.binance.vision','streams':['trade','bookTicker','kline_1m']});delay=1
                        reader=asyncio.create_task(receive(ws,inbox));waiter=asyncio.create_task(stop.wait())
                        done,_=await asyncio.wait((reader,waiter,task),return_when=asyncio.FIRST_COMPLETED)
                        waiter.cancel()
                        if task in done:
                            try:await task
                            except Exception as exc:raise RuntimeError('public_consumer_failed_closed') from exc
                        if reader in done:await reader
                        else:reader.cancel()
                    if not stop.is_set():raise ConnectionError('public_stream_ended')
                except (ConnectionError,aiohttp.ClientError,asyncio.TimeoutError) as exc:
                    feed.disconnected(type(exc).__name__);journal.save('public_reconnect',{'backoff_seconds':delay});await asyncio.sleep(delay);delay=min(delay*2,15)
        finally:
            stop.set();cert_task.cancel();task.cancel();probe_task.cancel()
            await asyncio.gather(cert_task,task,probe_task,return_exceptions=True)
            await asyncio.to_thread(worker.jobs.join)
            if r.spot['position']:r.request_exit('operator_shutdown');r.protect()
            export(folder,r,feed,view,'STOPPED_PENDING_EXIT' if r.spot['position'] else 'STOPPED')
    finally:
        if server:server.shutdown();server.server_close()
        await asyncio.to_thread(worker.close)
        if journal:journal.close()
        await session.close();raw.close();evidence.close()

def freeze(folder):
    folder=Path(folder);path=folder/'protocol.json'
    if path.exists():raise ValueError('Protocol already frozen')
    atomic_json(path,{'frozen_at':utc(),'source_sha256':hashes(),'config':asdict(SpotConfig()),
      'scope':'Public BTCUSDT Spot data; one local technical long/flat roundtrip only, then OBSERVE_ONLY. No broker account, remote order, key, leverage, short or margin.',
      'certificate':'Actual >=60s stream, >=1 native closed x=true 1m candle, trade and book receipt fresh<=2s, trade sourceage upper bound<=2s with clock uncertainty; positive uncrossed spread<=10bps; event processing<=250ms; coherent timestamped REST trade/book/candle comparisons. Book source timestamp not provided, never transport latency.',
      'execution':'Entry observed ask*(1+1bp), exit observed bid*(1-1bp), modeled taker fee0.1% each side USDT. Qty down to LOT_SIZE actual nonzero grid, totalentrycashincludingfee<=100USDT; publicbestquotesizelimit. Stop0.5% price tickdown,60sdeadline; modeled risk includes bothfees/slip. No guaranteedgaplossbound.',
      'recovery':'Existing Runtime subclass + AtomicJournal + original Risk. Atomic local intents/fills/protection/budget; restart cannot submit secondBUY. Exit freshbook evenuncertifiednews/entry, staleexit remains pending untilfreshquote. One planned SIGKILLwithopenposition thenrestart samejournal.',
      'readiness':'Technical only. Strictnews blocked; no economic strategy or livefinancialapproval. No commercial/live-data license claim.',
      'sources':['https://developers.binance.com/en/docs/products/spot/faqs/market_data_only','https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md','https://www.binance.com/en/fee/trading','https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md'],
      'attribution':'Binance Spot public market data; purely local noncommercial nonproduction technical paper research. No permission for commercial/live proprietary execution inferred.'})
    print('FROZEN_SPOT',hashlib.sha256(path.read_bytes()).hexdigest())

def main():
    p=argparse.ArgumentParser();p.add_argument('--journal',default=str(ROOT/'data/binance-spot/paper.sqlite'));p.add_argument('--report',default=str(ROOT/'reports/binance-spot/technical'));p.add_argument('--port',type=int,default=8767);p.add_argument('--freeze',action='store_true');a=p.parse_args()
    freeze(a.report) if a.freeze else asyncio.run(run(a))
if __name__=='__main__':main()
