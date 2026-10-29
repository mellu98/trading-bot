from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest
from mnq_timestral.schema import Bar
from mnq_sim.engine import Config, Replay, exit_bar, load_state


def bar(i=0,o=100,h=101,l=99,c=100):
    start=datetime(2026,10,19,13,30,tzinfo=timezone.utc)+timedelta(minutes=i)
    return Bar('MES','MESZ6',start,start+timedelta(minutes=1),start+timedelta(minutes=1),o,h,l,c,10)


def test_intrabar_collision_is_stop_first_and_flagged():
    result=exit_bar(bar(h=106,l=95),1,100,Config())
    assert result['reason']=='stop' and result['ambiguous'] is True and result['raw_exit']==98


def test_stop_gap_is_adverse_not_stop_price():
    result=exit_bar(bar(o=95,h=99,l=94,c=96),1,100,Config())
    assert result['raw_exit']==95


def test_invalid_costs_rejected():
    with pytest.raises(ValueError): Config(commission_per_side=-1)


def test_signal_enters_next_bar_not_signal_close():
    r=Replay([bar(i=i) for i in range(40)],Config(news_required=False))
    r.force_candidates={bar(20).end.isoformat():('MES',1)}
    result=r.run()
    trade=result['trades'][0]
    assert trade['entry_at']==bar(21).start.isoformat()
    assert trade['signal_bar_start']==bar(20).start.isoformat()


def test_daily_loss_and_kill_cannot_be_overridden():
    r=Replay([bar(i=i) for i in range(40)],Config(daily_max_loss=1))
    r.realized_day=-1
    assert r.entry_permission()[0] is False
    r.realized_day=0;r.kill=True
    assert r.entry_permission()==(False,'kill')


def test_restart_is_deterministic_and_no_duplicate_orders(tmp_path):
    bars=[bar(i=i) for i in range(40)]
    uninterrupted=Replay(bars,Config(news_required=False));uninterrupted.run()
    first=Replay(bars,Config(news_required=False));first.run(stop_after=24)
    state=first.state()
    resumed=Replay(bars,Config(news_required=False),state=state);resumed.run()
    assert resumed.trades==uninterrupted.trades and resumed.decisions==uninterrupted.decisions
    bad=dict(state);bad['config_sha256']='bad'
    with pytest.raises(ValueError): Replay(bars,Config(news_required=False),state=bad)


def test_news_missing_fails_closed():
    r=Replay([bar(i=i) for i in range(40)],Config())
    r.force_candidates={bar(20).end.isoformat():('MES',1)}
    assert r.run()['trades']==[]


def test_restart_with_open_bracket_json_roundtrip():
    import json
    bars=[bar(i=i) for i in range(40)]
    full=Replay(bars,Config(news_required=False))
    full.force_candidates={bar(20).end.isoformat():('MES',1)}
    full.run()
    interrupted=Replay(bars,Config(news_required=False))
    interrupted.force_candidates=full.force_candidates
    interrupted.run(stop_after=24)
    assert interrupted.position is not None
    state=json.loads(json.dumps(interrupted.state()))
    resumed=Replay(bars,Config(news_required=False),state=state)
    resumed.run()
    assert resumed.trades==full.trades and resumed.orders==full.orders and resumed.equity==full.equity


def test_future_bars_cannot_change_previous_decisions():
    bars=[bar(i=i) for i in range(40)]
    changed=bars[:30]+[bar(i=i,o=110,h=111,l=109,c=110) for i in range(30,40)]
    original=Replay(bars,Config(news_required=False));original.run(stop_after=30)
    perturbed=Replay(changed,Config(news_required=False));perturbed.run(stop_after=30)
    assert original.decisions==perturbed.decisions


def test_duplicate_and_gap_data_fail_closed():
    bars=[bar(i=i) for i in range(40)]
    with pytest.raises(ValueError): Replay(bars+bars[:1],Config())
    with pytest.raises(ValueError): Replay(bars[:25]+bars[26:],Config())


def test_kill_file_flattens_open_position_and_latches(tmp_path):
    bars=[bar(i=i) for i in range(40)]
    kill=tmp_path/'KILL'
    replay=Replay(bars,Config(news_required=False),kill_path=kill)
    replay.force_candidates={bar(20).end.isoformat():('MES',1)}
    replay.run(stop_after=24)
    kill.touch();replay.run()
    assert replay.trades[0]['reason']=='kill'
    assert replay.kill and replay.entry_permission()==(False,'kill')
    assert replay.position is None


def test_vwap_bracket_is_on_tradeable_tick_grid():
    r=Replay([bar(i=i) for i in range(40)],Config(exit_variant='vwap',news_required=False))
    r.indicators[(bar(20).start.isoformat(),'MES')]['vwap']=100.13
    r.force_candidates={bar(20).end.isoformat():('MES',1)}
    r.run()
    assert r.trades and r.trades[0]['target'] % .25 == 0


def test_csv_restart_dictionary_order_does_not_change_bytes(tmp_path):
    from mnq_sim.__main__ import write_rows
    import json
    a=tmp_path/'a.csv';b=tmp_path/'b.csv'
    rows=[{'z':1,'a':2}]
    write_rows(a,rows);write_rows(b,json.loads(json.dumps(rows,sort_keys=True)))
    assert a.read_bytes()==b.read_bytes()
