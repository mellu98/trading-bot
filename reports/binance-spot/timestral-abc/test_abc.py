"""Synthetic preregistration tests; no checkpoint or historical prices read."""
from decimal import Decimal as D
import numpy as np
import pytest
from runner import gate,valid_quantiles,context_at,naive_quantiles,mature,rank,FilteredSpot,baseline,H,HURDLE


def record(origin=100*H,edge='.01',latency=.1):
 q=np.ones((15,21))*101;q[:,10]=101
 return {'origin_ns':origin,'historical_available_ns':origin+int(latency*1e9),'latency_seconds':latency,'quantiles':q.tolist(),'status':'ok','input_end_ns':origin}


def test_lagged_step2_only_equality_late_and_no_instantaneous_forecast():
 origin=100*H;t=origin+4*H;r=record(origin)
 assert gate(r,t,D(100))==(True,'allow')
 fresh=record(t);assert gate(fresh,t,D(100))[1]=='origin_mismatch'
 r['quantiles'][1][10]=str(D(100)*(1+HURDLE));assert not gate(r,t,D(100))[0]
 r=record(origin,latency=301);assert gate(r,t,D(100))[1]=='late'
 r=record(origin);r['historical_available_ns']=t;assert gate(r,t,D(100))[1]=='late'
 assert gate(None,t,D(100))[1]=='missing'


def test_invalid_outputs_block_without_sort_or_clipping():
 q=np.tile(np.arange(1,22),(15,1)).astype(float);assert valid_quantiles(q)
 for broken in [np.full((15,21),np.nan),np.zeros((15,21)),q[:,::-1],np.ones((2,21))]:assert not valid_quantiles(broken)
 r=record();r['quantiles'][0][0]=float('nan');assert gate(r,104*H,D(100))[1]=='invalid'


def test_exact256_past_context_and_maturity_boundary():
 x=list(range(1,301));assert context_at(x,255)==x[:256];assert context_at(x,256)==x[1:257];assert context_at(x,254) is None
 assert mature(100*H,2,109*H) and not mature(100*H,3,109*H)
 past=np.array([100.,101.,99.,102.]);q=naive_quantiles(past,1);assert q.shape==(21,) and np.isfinite(q).all()
 assert np.array_equal(q,naive_quantiles(past.copy(),1))
 assert np.allclose(rank([3,1,1,2]),[4,1.5,1.5,3])


def fixture(n=100):
 B=baseline.Bar;start=1735689600*10**9
 out=[B(start+i*H,start+(i+1)*H,D(100),D(101),D(99),D(100),D(1),'fixture',0,0) for i in range(n)]
 b=out[83];out[83]=B(b.start,b.end,D(100),D(103),D(99),D(102),D(1),'fixture',0,0)
 return out


def test_filtered_hook_preserves_baseline_accounting_and_exits(tmp_path):
 from runner import make_engine
 b=fixture();r,j=baseline.engine(tmp_path/'A');a=baseline.simulate(r,b,0,len(b));j.close()
 decision=b[84].start;origin=decision-4*H;rec=record(origin);rec['quantiles']=(np.ones((15,21))*105).tolist()
 r,j=make_engine(tmp_path/'B','base','28M',{origin:rec},{x.end:x.close for x in baseline.aggregate4(b)})
 out=baseline.simulate(r,b,0,len(b));j.close()
 assert out['trades']==a['trades'] and out['final_cash']==a['final_cash'] and r.filter_audit[0]['allowed']
 # A future-origin forecast must not create an entry; no replacement forecast.
 r,j=make_engine(tmp_path/'veto','base','28M',{decision:record(decision)},{x.end:x.close for x in baseline.aggregate4(b)})
 out=baseline.simulate(r,b,0,len(b));assert not out['trades'] and r.filter_audit[0]['reason']=='missing';j.close()


def test_warmup_missing_is_not_an_origin_mismatch_and_hurdle_fixed():
 assert gate({'status':'missing_warmup'},104*H,D(100))==(False,'missing_warmup')
 exact=(D('1.0001')*D('1.0001')*D('1.001'))/(D('.9999')*D('.9999')*D('.999'))-1
 assert abs(exact-HURDLE)<D('1e-26')
