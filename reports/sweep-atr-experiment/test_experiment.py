"""Synthetic-only preregistration tests: never inspect economic sample here."""
from datetime import datetime,timedelta,timezone
from dataclasses import replace
import pytest
from mnq_timestral.schema import Bar,NY
from mnq_sim.engine import Config
from experiment import atr20,stop_distance,admit,first_candidate,exit_event,excursion_bounds


def bars(n=21):
    t=datetime(2026,5,5,9,30,tzinfo=NY).astimezone(timezone.utc)
    return [Bar('MNQ','MNQM6',t+timedelta(minutes=i),t+timedelta(minutes=i+1),t+timedelta(minutes=i+1),100.,101.,99.,100.,1.) for i in range(n)]


def test_atr_completed_same_session_causal():
    bb=bars();assert atr20(bb[:20]) is None
    assert atr20(bb)==2
    future=replace(bb[-1],high=10000.)
    assert atr20(bb)==2 and atr20(bb[:-1]+[future])>2
    assert atr20(bb[:-1]+[replace(bb[-1],start=bb[-1].start+timedelta(days=1),end=bb[-1].end+timedelta(days=1),available_at=bb[-1].end+timedelta(days=1))]) is None


def test_tick_rounding():
    assert stop_distance(2.01)==3.25
    assert stop_distance(2.)==3.


def test_one_micro_cap_and_available_budgets():
    assert admit(48.75,2.24,0,0,0,1)[0]
    assert not admit(49.,2.24,0,0,0,1)[0]
    assert not admit(1.,2.24,0,0,0,0)[0]
    assert not admit(1.,2.24,0,0,0,2)[0]
    assert not admit(20.,2.24,-180.,0,-180.,1)[0]
    assert not admit(20.,2.24,0,500.,30.,1)[0]


def test_first_signal_consumed_even_rejected():
    used=set();t=datetime(2026,5,5,10,tzinfo=NY)
    assert first_candidate(t,1,True,used)
    assert not first_candidate(t+timedelta(minutes=1),-1,True,used)
    assert not first_candidate(t+timedelta(days=1,hours=5),1,True,used)


def test_gap_stop_collision_and_deadline_priority():
    b=bars()[0];p={'side':1,'raw_entry':100.,'stop':98.,'target':104.,'entry_at':b.start.isoformat()}
    assert exit_event(replace(b,open=97.,high=105.,low=96.),p,None)[0:2]==('stop',97.)
    assert exit_event(replace(b,high=105.,low=97.),p,None)==('stop',98.,True,False)
    deadline=b.start+timedelta(minutes=5)
    d=replace(b,start=deadline,end=deadline+timedelta(minutes=1),available_at=deadline+timedelta(minutes=1),open=101.,high=105.,low=97.)
    assert exit_event(d,p,deadline)==('time_exit',101.,False,True)
    assert exit_event(replace(d,open=97.),p,deadline)[0]=='stop'


def test_exit_open_never_uses_later_extrema():
    bb=bars(2);t={'side':1,'raw_entry':100.,'raw_exit':100.5,'entry_at':bb[0].start.isoformat(),'exit_at':bb[1].start.isoformat(),'exit_timestamp_is_bar_bound':False,'reason':'time_exit'}
    bb[1]=replace(bb[1],open=100.5,high=999.,low=1.)
    q=excursion_bounds(t,bb)
    assert q['mfe_possible_usd']==2 and q['mae_possible_usd']==2
    t.update(exit_at=bb[1].end.isoformat(),exit_timestamp_is_bar_bound=True,reason='stop')
    q=excursion_bounds(t,bb)
    assert q['mfe_guaranteed_usd']==2 and q['mfe_possible_usd']==1798
    assert q['excursion_censored']


def test_replay_first_rejection_consumes_day(monkeypatch):
    from experiment import H1Replay
    from mnq_sim.strategies import PriceStrategy,StrategyConfig
    monkeypatch.setattr(PriceStrategy,'_sweep',lambda s,b: 1 if len(s.history) in (29,31) else 0)
    bb=[replace(b,high=140.,low=60.) for b in bars(40)]
    r=H1Replay(bb,Config(news_required=False),StrategyConfig('sweep_mss'),'B');out=r.run()
    assert len(r.candidates)==1 and not out['trades']
    assert r.candidates[0]['reason']=='initial_risk_cap_100'


def test_replay_signal_available_next_open_and_five_minutes(monkeypatch):
    from experiment import H1Replay
    from mnq_sim.strategies import PriceStrategy,StrategyConfig
    monkeypatch.setattr(PriceStrategy,'_sweep',lambda s,b: 1 if len(s.history)==29 else 0)
    r=H1Replay(bars(40),Config(news_required=False),StrategyConfig('sweep_mss'),'B');out=r.run()
    t=out['trades'][0]
    assert t['signal_at']==t['entry_at']
    assert datetime.fromisoformat(t['exit_at'])-datetime.fromisoformat(t['entry_at'])==timedelta(minutes=5)
    assert t['reason']=='time_exit' and not t['exit_timestamp_is_bar_bound']
    assert t['atr20_signal']==2 and t['stop']==97. and t['target']==106.


def test_original_fixed_bracket_and_risk_seams_match(monkeypatch):
    from experiment import H1Replay
    from mnq_sim.strategies import PriceStrategy,StrategyConfig,StrategyReplay
    monkeypatch.setattr(PriceStrategy,'_sweep',lambda s,b: 1 if len(s.history)==29 else 0)
    bb=bars(40);bb[31]=replace(bb[31],low=91.)
    config=Config(news_required=False);spec=StrategyConfig('sweep_mss')
    r=H1Replay(bb,config,spec,'A_matched');a=r.run()
    frozen=StrategyReplay(bb,config,spec);b=frozen.run()
    assert len(a['trades'])==len(b['trades'])==1
    for key in ('net','gross','fees','execution_cost','raw_entry','raw_exit','stop','target','entry_at','exit_at','reason'):
        assert a['trades'][0][key]==b['trades'][0][key]
    assert a['equity']==b['equity']
    assert r.entry_permission()==frozen.entry_permission()


def test_short_exit_symmetry_and_at_open_excursion():
    b=bars()[0];p={'side':-1,'raw_entry':100.,'stop':102.,'target':96.,'entry_at':b.start.isoformat()}
    assert exit_event(replace(b,open=103.,high=104.,low=95.),p,None)==('stop',103.,False,True)
    assert exit_event(replace(b,high=103.,low=95.),p,None)==('stop',102.,True,False)


def test_session_safety_open_precedes_range():
    b=bars()[0];t=b.start+timedelta(hours=6)
    b=replace(b,start=t,end=t+timedelta(minutes=1),available_at=t+timedelta(minutes=1),high=110.,low=90.)
    p={'side':1,'raw_entry':100.,'stop':98.,'target':104.,'entry_at':b.start.isoformat()}
    assert exit_event(b,p,None)==('session_close',100.,False,True)
