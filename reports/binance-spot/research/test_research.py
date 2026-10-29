"""Synthetic preregistration regressions; no archive prices accessed."""
from decimal import Decimal as D
from pathlib import Path
from datetime import datetime,timezone
import pytest
from runner import Bar,cross,sma,archive_ns,parse_row,HistoricalSpot,ResearchConfig,quote,simulate
from mnq_local.replay import AtomicJournal
from mnq_local.binance_spot import SpotSpec

H=3_600_000_000_000
BASE=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp())*1_000_000_000


def engine(tmp_path):
 c=ResearchConfig();s=SpotSpec('BTCUSDT','.01','.00001','.00001','9000','5');j=AtomicJournal(tmp_path/'state.sqlite',c,[s],lock_root=tmp_path/'locks')
 return HistoricalSpot(c,s,j),j


def test_cross_requires169_completed_closes_and_no_future():
 assert not cross([D(100)]*168)
 x=[D(100)]*168+[D(101)]
 assert cross(x) and cross(x[:]) and not cross(x+[D(99)])
 assert sma(x)==sum(x[-168:])/168


def test_explicit_2024_ms_2025_us_and_exact_close_units():
 old=int(datetime(2024,12,1,tzinfo=timezone.utc).timestamp())*1000
 assert archive_ns(old,2024)==old*1_000_000
 assert archive_ns(BASE//1000,2025)==BASE
 with pytest.raises(ValueError):archive_ns(BASE//1_000_000,2025)
 row=[str(BASE//1000),'100','101','99','100','1',str((BASE+H)//1000-1),'100','1','1','100','0']
 b=parse_row(row,'2025-01');assert b.start==BASE and b.end==BASE+H
 with pytest.raises(ValueError):parse_row([row[0]]+row[1:6]+[str(BASE//1000)]+row[7:],'2025-01')


def test_two_roundtrips_exact_cumulative_cash_and_historical_daily_net(tmp_path):
 r,j=engine(tmp_path)
 for n,(entry,exit) in enumerate([(100,110),(110,100)]):
  r.now=BASE+n*24*H;r.set_quote(D(entry));assert r.enter()
  assert r.spot['position']['deadline_ns']==r.now+168*H
  r.now+=H;r.set_quote(D(exit));r.request_exit('fixture');assert r.exit_or_protect()
  assert r.state['executions'][str('local-spot-'+str(1+n*4))]['date']==('2025-01-01' if n==0 else '2025-01-02')
 assert len(r.closed)==2
 total=sum(D(t['net']) for t in r.closed)
 assert D(r.spot['cash'])-1000==D(r.spot['net'])==total
 assert abs(D(str(r.net(day=True)))-D(r.closed[-1]['net']))<D('1e-12')
 assert r.state['date']=='2025-01-02'
 j.close()


def test_next_open_not_signal_close_and_future_prefix(tmp_path):
 # Cross on index168 queues entry on169, never on the signal close.
 bb=[Bar(BASE+i*H,BASE+(i+1)*H,D(100),D(101),D(99),D(100),D(1),'synthetic',0,0) for i in range(172)]
 bb[168]=Bar(bb[168].start,bb[168].end,D(100),D(101),D(99),D(101),D(1),'synthetic',0,0)
 bb[169]=Bar(bb[169].start,bb[169].end,D(110),D(111),D(109),D(110),D(1),'synthetic',0,0)
 r,j=engine(tmp_path);out=simulate(r,bb,0,len(bb));assert out['trades'][0]['entry_ns']==bb[169].start
 assert D(out['trades'][0]['entry_fill'])==D(110)*D('1.0001')*D('1.0001')
 j.close()


def test_adverse_gap_stop_before_pending_signal_and_deadline(tmp_path):
 r,j=engine(tmp_path);r.now=BASE;r.set_quote(D(100));assert r.enter()
 r.request_exit('sma_exit');r.now+=H;r.set_quote(D(80))
 if D(r.quote['bid'])<=D(r.spot['position']['stop']):r.spot['pending_exit']='adverse_stop_gap'
 assert r.exit_or_protect() and r.closed[0]['exit_reason']=='adverse_stop_gap'
 assert D(r.closed[0]['exit_fill'])==D(80)*D('.9999')*D('.9999')
 assert D(r.spot['cash'])-1000==D(r.closed[0]['net'])
 j.close()
