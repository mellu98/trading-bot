"""Synthetic pre-data regressions, no archive access."""
from decimal import Decimal as D
from pathlib import Path
from datetime import datetime,timezone
import pytest
from runner import Bar,H,aggregate4,decision,atr14,engine,simulate,archive_ns,quote
BASE=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp())*10**9

def bars(n=100):
 return [Bar(BASE+i*H,BASE+(i+1)*H,D(100),D(101),D(99),D(100),D(1),'fixture',0,0) for i in range(n)]

def test_complete_contiguous_utc_4h_and_strict_channels_no_cross_required():
 b=bars(85);four=aggregate4(b);assert len(four)==21 and four[-1].end==BASE+84*H
 assert decision(four)==(False,False,D(2))
 last=four[-1];four[-1]=Bar(last.start,last.end,D(100),D(103),D(99),D(102),D(1),'fixture',0,0)
 assert decision(four)[0] and decision(four)[2]==D(30)/14
 assert decision(four[:-1])==(False,False,None)
 with pytest.raises(ValueError):aggregate4(b[:3]+b[4:])


def test_next_hour_open_not_same_close_no_future(tmp_path):
 b=bars(90);old=b[83];b[83]=Bar(old.start,old.end,D(100),D(103),D(99),D(102),D(1),'fixture',0,0)
 b[84]=Bar(b[84].start,b[84].end,D(104),D(105),D(103),D(104),D(1),'fixture',0,0)
 r,j=engine(tmp_path);out=simulate(r,b,0,len(b))
 assert out['trades'][0]['entry_ns']==b[84].start
 assert D(out['trades'][0]['entry_fill'])==D(104)*D('1.0001')**2
 assert out['signals'][0]['at']==b[83].end
 assert D(out['trades'][0]['initial_modeled_risk_usdt'])<=1
 j.close()


def test_two_cycles_historical_days_cost_cash_and_gap_priority(tmp_path):
 r,j=engine(tmp_path)
 for n in range(2):
  r.now=BASE+n*24*H;r.set_quote(D(100));assert r.enter(D('.5'))
  p=dict(r.spot['position']);assert D(p['stop'])==D('99.02')
  assert D(p['entry_cash'])<=100 and D(p['initial_modeled_risk_usdt'])<=1
  r.now+=H;r.set_quote(D(90));r.spot['pending_exit']='adverse_stop_gap';assert r.exit_or_protect()
 assert len(r.closed)==2 and all(t['exit_reason']=='adverse_stop_gap' for t in r.closed)
 assert D(r.spot['cash'])-1000==sum(D(t['net']) for t in r.closed)==D(r.spot['net'])
 assert abs(D(str(r.net(day=True)))-D(r.closed[-1]['net']))<D('1e-12')
 assert r.state['date']=='2025-01-02'
 j.close()


def test_stress_fully_resizes_not_arithmetic_subtraction(tmp_path):
 a,ja=engine(tmp_path/'a','base');b,jb=engine(tmp_path/'b','adverse')
 for r in (a,b):r.now=BASE;r.set_quote(D(100));assert r.enter(D('.5'))
 assert D(b.spot['position']['quantity'])<D(a.spot['position']['quantity'])
 ja.close();jb.close()


def test_2024_ms_2026_us_explicit_units_and_original_integers():
 t=int(datetime(2024,12,1,tzinfo=timezone.utc).timestamp())
 assert archive_ns(t*1000,2024)==t*10**9
 t26=int(datetime(2026,1,1,tzinfo=timezone.utc).timestamp())
 assert archive_ns(t26*1000000,2026)==t26*10**9
 with pytest.raises(ValueError):archive_ns(t26*1000,2026)


def test_gap_stop_precedes_queued_channel_sell_at_next_open(tmp_path):
 b=bars(94)
 old=b[83];b[83]=Bar(old.start,old.end,D(100),D(103),D(99),D(102),D(1),'fixture',0,0)
 # Entry84; tight synthetic ATR signal sets stop near95.73. Hour87 closes below
 # previous10 lows99 but ABOVE stop, scheduling channel SELL. Hour88 gaps lower.
 for i in range(84,88):
  old=b[i];b[i]=Bar(old.start,old.end,D(100),D(101),D(98),D(98),D(1),'fixture',0,0)
 old=b[88];b[88]=Bar(old.start,old.end,D(90),D(91),D(89),D(90),D(1),'fixture',0,0)
 r,j=engine(tmp_path);out=simulate(r,b,0,len(b));assert out['trades'][0]['exit_reason']=='adverse_stop_gap'
 assert out['trades'][0]['exit_ns']==b[88].start
 j.close()


def test_prefix_signals_unchanged_by_future_prices_and_no_terminal_entry(tmp_path):
 b=bars(92);old=b[83];b[83]=Bar(old.start,old.end,D(100),D(103),D(99),D(102),D(1),'fixture',0,0)
 r,j=engine(tmp_path/'prefix');a=simulate(r,b[:88],0,88);j.close()
 old=b[91];b[91]=Bar(old.start,old.end,D(100),D(999),D(1),D(900),D(1),'fixture',0,0)
 r,j=engine(tmp_path/'full');c=simulate(r,b,0,92);j.close()
 assert a['signals']==[s for s in c['signals'] if s['at']<b[87].end]
 r,j=engine(tmp_path/'terminal');last=simulate(r,b[:85],0,85);assert not last['trades'];j.close()


def test_missing_complete_bucket_not_silently_aggregated():
 b=bars(100)
 with pytest.raises(ValueError):aggregate4(b[:40]+b[44:])
