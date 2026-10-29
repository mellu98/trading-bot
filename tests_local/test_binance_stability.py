"""Observer-only persistence isolation; no external data or orders."""
import asyncio,json,sqlite3,threading,time
from mnq_local.binance_app import PipelineMetrics,ObservationWorker,ObservedJournal
from mnq_local.binance_spot import SpotConfig
from test_binance_spot import spec


def test_worker_slow_checkpoint_dashboard_does_not_block_loop():
 async def exercise():
  metrics=PipelineMetrics();worker=ObservationWorker(metrics);protected=[]
  worker.submit('slow_checkpoint',lambda:time.sleep(.12))
  worker.submit('slow_dashboard',lambda:time.sleep(.12))
  start=time.monotonic()
  for i in range(20):
   protected.append(i);await asyncio.sleep(.002)
  elapsed=time.monotonic()-start
  await asyncio.to_thread(worker.close)
  assert len(protected)==20 and elapsed<.15
 asyncio.run(exercise())


def test_old_background_snapshot_cannot_overwrite_critical_state(tmp_path):
 metrics=PipelineMetrics();j=ObservedJournal(tmp_path/'state.sqlite',SpotConfig(),[spec()],lock_root=tmp_path/'locks',metrics=metrics)
 j.state['probe']='old';encoded,revision=j.capture()
 worker=ObservationWorker(metrics);gate=threading.Event()
 worker.submit('wait',lambda:gate.wait(2))
 worker.submit('checkpoint',lambda:j.checkpoint(encoded,revision))
 with j.bar_transaction():
  j.state['probe']='critical_halt';j.save('critical_halt')
 gate.set();worker.close()
 assert json.loads(j.db.execute('select body from snapshot where id=1').fetchone()[0])['probe']=='critical_halt'
 assert metrics.snapshot()['counters']['checkpoint_superseded']==1
 j.close()


def test_metrics_memory_bounded_and_worker_fault_explicit():
 metrics=PipelineMetrics(limit=8)
 for i in range(100):metrics.record('queue_wait',i)
 assert metrics.snapshot()['stages']['queue_wait']['count']==100
 assert metrics.snapshot()['stages']['queue_wait']['retained']==8
 worker=ObservationWorker(metrics)
 worker.submit('bad',lambda:1/0);worker.close()
 assert worker.error is not None


def test_real_feed_queue_protects_every_quote_during_slow_io(tmp_path,monkeypatch):
 from test_binance_spot import make
 from mnq_local.binance_spot import Feed
 from mnq_local.binance_app import process_public_event
 r,j=make(tmp_path);f=Feed(r);f.connected();r.spot['position']={'synthetic':'test_only'}
 protected=[];monkeypatch.setattr(r,'protect',lambda:protected.append(r.quote['update_id']))
 async def exercise():
  metrics=PipelineMetrics();worker=ObservationWorker(metrics);inbox=asyncio.Queue(512)
  worker.submit('slow_checkpoint',lambda:time.sleep(.15))
  worker.submit('slow_dashboard',lambda:time.sleep(.15))
  async def produce():
   for i in range(1,101):
    item={'stream':'btcusdt@bookTicker','data':{'u':i,'s':'BTCUSDT','b':'100','a':'100.01','B':'1','A':'1'}}
    await inbox.put((item,time.time_ns(),time.monotonic_ns()));await asyncio.sleep(.001)
  async def consume():
   for _ in range(100):process_public_event(r,f,*(await inbox.get()),metrics)
  await asyncio.gather(produce(),consume());await asyncio.to_thread(worker.close)
 asyncio.run(exercise())
 assert protected==list(range(1,101)) and not f.stats['processing_delay_rejections']
 # Same250ms guard still rejects actual stale queued data, with no invented quote.
 before=r.quote
 assert not process_public_event(r,f,{'stream':'btcusdt@bookTicker','data':{}},time.time_ns(),time.monotonic_ns()-300_000_000)
 assert r.quote is before and f.stats['processing_delay_rejections']==1
 j.close()


def test_actual_slow_sqlite_checkpoint_measures_critical_wait(tmp_path,monkeypatch):
 import mnq_local.binance_app as app
 metrics=PipelineMetrics();j=ObservedJournal(tmp_path/'state.sqlite',SpotConfig(),[spec()],lock_root=tmp_path/'locks',metrics=metrics)
 encoded,revision=j.capture();entered=threading.Event();real_connect=app.sqlite3.connect
 def slow_connect(*a,**kw):
  entered.set();time.sleep(.08);return real_connect(*a,**kw)
 monkeypatch.setattr(app.sqlite3,'connect',slow_connect)
 worker=ObservationWorker(metrics);worker.submit('checkpoint',lambda:j.checkpoint(encoded,revision));assert entered.wait(2)
 # Durable critical writes serialize with active SQLite writes, not falsely nonblocking.
 with j.bar_transaction():j.state['probe']='latest';j.save('critical')
 worker.close()
 assert metrics.snapshot()['stages']['critical_lock_wait']['max_ms']>=50
 assert json.loads(j.db.execute('select body from snapshot where id=1').fetchone()[0])['probe']=='latest'
 j.close()


def test_bounded_io_queue_overflow_is_explicit_fail_closed():
 import pytest
 metrics=PipelineMetrics();worker=ObservationWorker(metrics);gate=threading.Event();started=threading.Event()
 worker.submit('blocked',lambda:(started.set(),gate.wait(2)));assert started.wait(1)
 for _ in range(16):worker.submit('queued',lambda:None)
 with pytest.raises(ConnectionError,match='bounded_observation'):worker.submit('overflow',lambda:None)
 assert metrics.snapshot()['counters']['io_queue_overflow']==1
 gate.set();worker.close()
