"""Synthetic tests only; never connect while validating the harness."""
import importlib.util,sys,json,time
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('isolation',Path(__file__).with_name('runner.py'));r=importlib.util.module_from_spec(s);sys.modules[s.name]=r;s.loader.exec_module(r)


def test_balanced_order_and_budgets():
 assert r.ORDER==list('ABCDDCBA') and all(r.ORDER.count(k)*r.SEGMENT_SECONDS==600 for k in 'ABCD')
 assert r.SOAK_CONNECTED_SECONDS>=1800


def test_raw_arm_never_decodes_json(monkeypatch):
 m=r.Monitor('A');monkeypatch.setattr(r.json,'loads',lambda *_:pytest.fail('A parsedJSON'))
 assert m.process('not json',time.time_ns(),time.monotonic_ns()) is None
 assert m.counts['processed']==1 and m.counts['json_decodes']==0


def test_receipt_delay_is_failclosed_not_threshold_tuning():
 m=r.Monitor('B');m.process('{"stream":"btcusdt@bookTicker","data":{"u":1}}',time.time_ns(),time.monotonic_ns()-300000000)
 assert m.counts['delay_ge250ms']==1 and m.counts['json_decodes']==0


def test_c_has_no_order_or_account_capability_and_calls_original_risk():
 c=r.ReadOnlyFeedOwner();assert not hasattr(c,'submit_technical') and not hasattr(c,'broker') and not hasattr(c,'state')
 c.connected=True;c.trade_fresh=True;c.ready=True
 allowed,reason=c.risk.allow(r.RiskState(data_fresh=False))
 assert not allowed and reason=='stale_data'


def test_cluster_merge_and_connected_duration_exclude_downtime():
 assert r.clusters([1000000000,1100000000,3000000000])==[[1000000000,1100000000],[3000000000,3000000000]]
 assert r.connected_seconds([(0,300),(310,700)])==690


def test_d_externalization_changes_only_os_probe(monkeypatch):
 import mnq_local.binance_app as app
 before=app.hashes();r.externalize_os_probe(app)
 assert app.host_sample()['isolation_external_sampler'] is True and app.hashes()==before


def test_c_actual_four_hour_helper_reuses_frozen_decision_without_orders():
    strategy=r.ClosedStrategy()
    assert strategy.evaluations==0
    assert strategy.consider({'x':False,'T':14399999},[]) is None
    assert strategy.consider({'x':True,'T':14339999},[]) is None
    assert strategy.evaluations==0 and not hasattr(strategy,'submit')


def test_closed_strategy_synthetic240minutes_calls_frozen_decision_once():
 s=r.ClosedStrategy();b=s.baseline.Bar;d=s.baseline.dec;h=s.baseline.H;end=14400000000000;start=0
 s.context=[b(i*4*h,(i+1)*4*h,d(100),d(102),d(99),d(101),d(1),'fixture',0,0) for i in range(-21,0)]
 minutes=[{'x':True,'t':i*60000,'T':i*60000+59999,'o':'100','h':'103','l':'99','c':'102','v':'1'} for i in range(240)]
 assert s.consider(minutes[-1],minutes)['no_orders'] and s.evaluations==1
