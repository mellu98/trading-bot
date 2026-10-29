"""Correlated wall/CPU/GC evidence without relaxing market-data guards."""
import gc,json,time
from mnq_local.binance_app import PipelineMetrics,decode_received,host_sample


def test_sleep_and_busy_have_correlated_cpu_wall_and_bounded_trace():
 m=PipelineMetrics(limit=8)
 with m.measure('blocked_fixture'):time.sleep(.04)
 row=m.take_events()[0]
 assert row['stage']=='blocked_fixture' and row['wall_ms']>=30 and row['thread_cpu_ms']<20
 assert row['mono_end_ns']>=row['mono_start_ns'] and row['process_cpu_ms']>=0
 for _ in range(3000):m.event('fixture',{'received_mono_ns':1})
 assert len(m.take_events())<=2048 and m.snapshot()['counters']['correlation_events_overwritten']>0


def test_receipt_precedes_decode_instrumentation(monkeypatch):
 m=PipelineMetrics();real=m.record
 def slow(*a):time.sleep(.01);return real(*a)
 monkeypatch.setattr(m,'record',slow)
 item,wall,mono=decode_received('{"stream":"fixture"}',m)
 assert item['stream']=='fixture' and time.monotonic_ns()-mono>=10000000 and time.time_ns()>=wall


def test_gc_is_measured_not_disabled():
 m=PipelineMetrics();enabled=gc.isenabled();threshold=gc.get_threshold();m.attach_gc()
 try:gc.collect()
 finally:m.detach_gc()
 assert gc.isenabled()==enabled and gc.get_threshold()==threshold
 assert m.snapshot()['stages']['gc_gen2']['count']>=1


def test_host_sampling_errors_are_explicit_not_feed_failures(monkeypatch):
 import mnq_local.binance_app as app
 monkeypatch.setattr(app.subprocess,'check_output',lambda *a,**k:(_ for _ in ()).throw(FileNotFoundError()))
 x=host_sample();assert x['errors'] and x['process_cpu_seconds']>=0 and x['mono_end_ns']>=x['mono_start_ns']
