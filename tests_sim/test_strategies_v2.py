from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import pytest
from mnq_timestral.schema import Bar
from mnq_sim.engine import Config
from mnq_sim.strategies import StrategyConfig, PriceStrategy, StrategyReplay


def bar(i=0,o=100,h=101,l=99,c=100,day=19):
    t=datetime(2026,10,day,13,30,tzinfo=timezone.utc)+timedelta(minutes=i)
    return Bar('MES','MESZ6',t,t+timedelta(minutes=1),t+timedelta(minutes=1),o,h,l,c,10)


def orb_bars():
    return [bar(i) for i in range(15)]+[bar(i,o=101,h=102,l=100,c=101.25) for i in range(15,40)]


def sweep_bars():
    # Confirmed high103 at2, low97 at6; reclaim low at10, MSS at11.
    return [bar(i,h=h,l=l,c=c) for i,(h,l,c) in enumerate([
      (101,99,100),(102,99,100),(103,99,100),(102,99,100),(101,99,100),
      (101,98,100),(101,97,100),(101,98,100),(101,99,100),(101,99,100),
      (101,96.75,98),(104,98,103.25)])]


def test_orb_waits_full_range_and_confirms_close_once_per_side():
    strategy=PriceStrategy(StrategyConfig('orb'))
    bb=orb_bars()
    assert [strategy.on_bar(b) for b in bb[:15]]==[0]*15
    assert strategy.on_bar(bb[15])==1
    assert strategy.on_bar(bb[16])==0
    assert strategy.audit['range_high']==101 and strategy.audit['range_low']==99


def test_orb_wick_not_confirmation_and_short_symmetry():
    strategy=PriceStrategy(StrategyConfig('orb'))
    for i in range(15):strategy.on_bar(bar(i))
    assert strategy.on_bar(bar(15,h=102,c=101))==0
    assert strategy.on_bar(bar(16,l=98,c=98.75))==-1


def test_sweep_requires_confirmed_pivots_and_later_mss():
    strategy=PriceStrategy(StrategyConfig('sweep_mss'))
    bb=sweep_bars()
    signals=[strategy.on_bar(b) for b in bb]
    assert signals==[0]*11+[1]
    assert strategy.audit['mss_level']==103
    assert strategy.audit['sweep_at']==bb[10].end.isoformat()
    assert strategy.audit['pivot_confirmed_at']<=bb[10].start.isoformat()


def test_same_bar_sweep_and_break_cannot_infer_event_order():
    strategy=PriceStrategy(StrategyConfig('sweep_mss'))
    bb=sweep_bars()
    for b in bb[:10]:strategy.on_bar(b)
    assert strategy.on_bar(bar(10,h=104,l=96.75,c=103.25))==0
    assert strategy.pending is None


def test_sweep_pending_invalidated_by_extreme_and_expires():
    strategy=PriceStrategy(StrategyConfig('sweep_mss',mss_timeout=1))
    for b in sweep_bars()[:11]:strategy.on_bar(b)
    assert strategy.pending
    assert strategy.on_bar(bar(11,h=102,l=96.5,c=101))==0
    assert strategy.pending is None
    strategy=PriceStrategy(StrategyConfig('sweep_mss',mss_timeout=1))
    for b in sweep_bars()[:11]:strategy.on_bar(b)
    strategy.on_bar(bar(11,h=102,l=98,c=101))
    assert strategy.on_bar(bar(12,h=104,l=98,c=103.25))==0


@pytest.mark.parametrize('kind',['orb','sweep_mss'])
def test_future_perturbations_cannot_repaint_signals(kind):
    bb=orb_bars();changed=bb[:25]+[bar(i,o=110,h=111,l=109,c=110) for i in range(25,40)]
    a=StrategyReplay(bb,Config(news_required=False),StrategyConfig(kind));a.run(stop_after=25)
    b=StrategyReplay(changed,Config(news_required=False),StrategyConfig(kind));b.run(stop_after=25)
    assert a.decisions==b.decisions and a.orders==b.orders


def test_plugin_restart_identity_and_determinism():
    bb=orb_bars();config=Config(news_required=False);spec=StrategyConfig('orb')
    full=StrategyReplay(bb,config,spec);full.run()
    first=StrategyReplay(bb,config,spec);first.run(stop_after=18)
    state=json.loads(json.dumps(first.state()))
    resumed=StrategyReplay(bb,config,spec,state=state);resumed.run()
    assert resumed.run()==full.run()
    with pytest.raises(ValueError):StrategyReplay(bb,config,StrategyConfig('orb',opening_minutes=20),state=state)
    assert full.trades[0]['entry_at']==bb[16].start.isoformat()


def test_strict_news_and_kill_remain_authoritative():
    assert StrategyReplay(orb_bars(),Config(),StrategyConfig('orb')).run()['trades']==[]
    replay=StrategyReplay(orb_bars(),Config(news_required=False),StrategyConfig('orb'));replay.kill=True
    assert replay.run()['trades']==[]


def test_session_reset_and_invalid_input_fail_closed():
    strategy=PriceStrategy(StrategyConfig('orb'))
    for b in orb_bars():strategy.on_bar(b)
    assert strategy.on_bar(bar(day=20))==0
    assert not strategy.used_sides
    with pytest.raises(ValueError):strategy.on_bar(bar(2,day=20))
    with pytest.raises(ValueError):PriceStrategy(StrategyConfig('orb')).on_bar(bar(1))
    with pytest.raises(ValueError):PriceStrategy(StrategyConfig('orb')).on_bar(replace(bar(),available_at=bar().end+timedelta(seconds=1)))


@pytest.mark.parametrize('kwargs',[{'kind':'bad'},{'kind':'orb','opening_minutes':0},{'kind':'sweep_mss','pivot_left':True},{'kind':'orb','buffer_ticks':-1}])
def test_invalid_parameters(kwargs):
    with pytest.raises(ValueError):StrategyConfig(**kwargs)


def test_previously_breached_pivot_is_not_fresh_liquidity_proxy():
    strategy=PriceStrategy(StrategyConfig('sweep_mss'))
    for b in sweep_bars()[:10]:strategy.on_bar(b)
    # No reclaim on first breach: the old support is consumed, not reusable.
    strategy.on_bar(bar(10,o=97,h=101,l=96.5,c=96.75))
    assert strategy.on_bar(bar(11,h=101,l=96.75,c=98))==0
    assert strategy.pending is None


def test_bearish_sweep_mss_is_symmetric():
    strategy=PriceStrategy(StrategyConfig('sweep_mss'))
    mirrored=[replace(b,open=200-b.open,high=200-b.low,low=200-b.high,close=200-b.close) for b in sweep_bars()]
    assert [strategy.on_bar(b) for b in mirrored]==[0]*11+[-1]


def test_dual_sweep_is_rejected_and_consumed():
    strategy=PriceStrategy(StrategyConfig('sweep_mss'))
    for b in sweep_bars()[:10]:strategy.on_bar(b)
    assert strategy.on_bar(bar(10,h=103.25,l=96.75,c=100))==0
    assert strategy.pending is None
    assert ('low',6) in strategy.consumed and ('high',2) in strategy.consumed


def test_original_global_risk_halt_cannot_be_bypassed():
    replay=StrategyReplay(orb_bars(),Config(news_required=False),StrategyConfig('orb'))
    replay.global_halt=True
    assert replay.run()['trades']==[]
