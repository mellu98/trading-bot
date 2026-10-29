"""Synthetic heartbeat/gating and isolated critical-journal proof; no market data."""
import importlib.util,sys,struct,time,json
from pathlib import Path
from types import SimpleNamespace
import pytest
s=importlib.util.spec_from_file_location('pause_diag',Path(__file__).with_name('pause.py'));m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)


def test_shared_heartbeat_rejects_torn_write_and_retains_last_valid(tmp_path):
 h=m.Heartbeat(tmp_path/'hb',True);h.write(0,1000,7);assert h.read(0)==(1000,7)
 struct.pack_into('<Q',h.mm,0,99);assert h.read(0) is None
 h.close()


def test_trigger_budget_cooldown_and_instrumentation_windows():
 b=m.CaptureBudget()
 assert not b.allowed('A1',99,1000)
 assert b.allowed('A1',101,1000);b.used('A1',1000)
 assert not b.allowed('A1',200,2000)
 assert not b.allowed('B1',200,1040)
 assert b.allowed('B1',101,1061)
 assert m.overlap(100,200,150,250)==50 and m.overlap(100,200,201,250)==0


def test_B_disables_only_noncritical_publish_and_dashboard():
 original={k:object() for k in ['ObservedJournal','SpotRuntime','process_public_event','ObservationWorker','Feed','MeasuredView','export']};a=SimpleNamespace(**original,enqueue_observation=lambda:None,Dashboard=object())
 m.disable_noncritical(a)
 for k,v in original.items():assert getattr(a,k) is v
 assert a.enqueue_observation(None,None,None,None,None,None,None) is None


def test_actual_critical_FULL_journal_is_unchanged_under_B(tmp_path):
 import mnq_local.binance_app as app
 from mnq_local.binance_spot import SpotConfig,SpotSpec
 before=app.ObservedJournal;spec=SpotSpec.from_exchange(json.load(open('reports/binance-spot/exchangeInfo-preflight.json')))
 fake=SimpleNamespace(enqueue_observation=None,Dashboard=None,ObservedJournal=before)
 m.disable_noncritical(fake);j=fake.ObservedJournal(tmp_path/'paper.sqlite',SpotConfig(),[spec],metrics=app.PipelineMetrics(),lock_root=tmp_path/'locks')
 try:
  with j.bar_transaction():j.state['diagnostic_fixture']=17;j.save('critical_fixture',{'safe':True})
  assert j.db.execute('PRAGMA synchronous').fetchone()[0]==2
  assert json.loads(j.db.execute('SELECT body FROM snapshot WHERE id=1').fetchone()[0])['diagnostic_fixture']==17
  assert j.db.execute("SELECT count(*) FROM journal WHERE kind='critical_fixture'").fetchone()[0]==1
 finally:j.close()


def test_four_hour_gap_future_and_global_fail_closed_fixtures():
 s=importlib.util.spec_from_file_location('audit4h',Path(__file__).with_name('audit4h.py'));a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
 assert a.causal(100,110,120,115)
 assert not a.causal(100,121,120,115)
 assert not a.causal(100,110,3000000120,115)
 p=Path('reports/binance-spot/forward-signals/recorder.py');s=importlib.util.spec_from_file_location('audit_forward',p);f=importlib.util.module_from_spec(s);s.loader.exec_module(f);step=f.STEP_MS
 rows=[[i*step,'100','102','99','101','1',(i+1)*step-1] for i in range(257)]
 bars=f.closed(rows,256*step);assert len(bars)==256 and bars[-1].end==256*step*1000000
 with pytest.raises(ValueError):f.closed(rows[:90]+rows[91:],256*step)
 with pytest.raises(ValueError):f.closed(rows[:90]+[rows[89]]+rows[90:],256*step)
 assert 'STABILITY_READINESS_BLOCKED' in f.reasons({'feed_metrics':{'passed':True}},True)
