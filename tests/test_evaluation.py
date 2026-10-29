from dataclasses import replace
from datetime import timedelta, datetime, timezone
import json
import subprocess
import sys
import numpy as np
import pytest
from conftest import bars, prediction
from mnq_timestral.evaluation import Costs, simulate_trade, metrics, forecast_metrics, block_bootstrap, split_sessions, select_threshold
from mnq_timestral.data import session_window


def costs(): return Costs(.2,.1,.05,1,1,1,'test-only synthetic cost evidence')


def test_costs_gap_stop_and_ambiguity():
    bs=bars(2)
    b=replace(bs[1],open=6000,high=6010,low=5990,close=6000)
    t=simulate_trade('MES',1,[b],6000,costs(),tp=4,sl=2)
    assert t.reason=='stop' and t.raw_exit==5998
    assert t.gross==-10 and t.fees==pytest.approx(.7)
    assert t.execution_cost==pytest.approx(3.75) and t.net==pytest.approx(-14.45)
    gap=replace(b,open=5995,high=5997,low=5994,close=5996)
    assert simulate_trade('MES',1,[gap],6000,costs(),tp=4,sl=2).raw_exit==5995
    with pytest.raises(ValueError): Costs(-1,0,0,0,0,0,'bad')


def test_metrics_calibration_bootstrap_and_insufficient(req,pred):
    fm=forecast_metrics([(pred,{h:row[10] for h,row in zip(pred.horizons,pred.values)})])
    assert fm['5']['mae']==0 and fm['5']['coverage']['0.5']==1
    assert fm['5']['count']==1
    assert block_bootstrap([1,2,3])['status']=='insufficient_evidence'
    b=block_bootstrap([1]*40,seed=7,replicates=1000)
    assert b['lower_bound']==1 and b['research_improvement']
    assert b==block_bootstrap([1]*40,seed=7,replicates=1000)
    assert metrics([])['profit_factor'] is None


def test_session_split_and_test_labels_cannot_change_selection():
    sessions=[f'2026-01-{x:02d}' for x in range(1,16)]
    folds,holdout=split_sessions(sessions,calibration=4,validation=3,test=2,holdout=2)
    assert holdout==sessions[-2:]
    for f in folds:
        assert max(f['calibration'])<min(f['validation'])<min(f['test'])<min(holdout)
        assert not set(f['test']) & set(f['validation'])
    validation=[(.2,1),(.6,-1),(.8,2)]
    selected=select_threshold(validation,[0,.5,1])
    unrelated_test=[(x, -999) for x in range(10)]
    assert select_threshold(validation,[0,.5,1])==selected


def test_calendar_dst_unknown_news_and_early_close():
    def record(date,open_hour,close_hour):
        return {'open':f'{date}T{open_hour}:30:00+00:00','close':f'{date}T{close_hour}:00:00+00:00',
                'known_at':f'{date}T00:00:00+00:00','news_complete':True,'news_blocks':[]}
    cal={'2026-03-06':record('2026-03-06','14','21'),'2026-03-09':record('2026-03-09','13','20')}
    assert session_window('2026-03-06',cal)[0].hour==14
    assert session_window('2026-03-09',cal)[0].hour==13
    assert session_window('2026-03-07',cal) is None
    cal['2026-03-09']['news_complete']=False
    assert session_window('2026-03-09',cal) is None
    early={'2026-11-27':record('2026-11-27','14','18')}
    assert session_window('2026-11-27',early)[1].hour==17


def test_cli_missing_data_honest_report(tmp_path):
    report=tmp_path/'report.json'
    p=subprocess.run([sys.executable,'-m','mnq_timestral.cli','compare','--output',str(report)],capture_output=True,text=True)
    assert p.returncode==2
    r=json.loads(report.read_text())
    assert r['status']=='not_evaluated' and r['filter_enabled'] is False
    assert 'pnl' not in r and r['execution_quality_gate'] is False
