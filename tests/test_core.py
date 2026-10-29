from dataclasses import replace
from datetime import timedelta, datetime
import numpy as np
import pytest
from conftest import bars, request, prediction
from mnq_timestral.schema import Request, Prediction, LEVELS, HORIZONS
from mnq_timestral.data import features, horizon_targets, validate_dataset
from mnq_timestral.model import PINS, SOURCE_REVISION, OfficialAdapter
from mnq_timestral.strategy import Filter, Risk, RiskState, Candidate, SignalGenerator, entry_allowed


def test_schema_rejects_future_naive_bad_ohlc_and_gaps(req):
    with pytest.raises(ValueError): replace(req.bars[0], available_at=req.bars[0].start)
    with pytest.raises(ValueError): replace(req.bars[0], start=datetime(2026,10,20))
    with pytest.raises(ValueError): replace(req.bars[0], high=1)
    with pytest.raises(ValueError): replace(req, requested_at=req.origin-timedelta(seconds=1))
    with pytest.raises(ValueError): replace(req, bars=req.bars[:2]+req.bars[3:])
    with pytest.raises(ValueError): replace(req, bars=req.bars+(req.bars[-1],))
    with pytest.raises(ValueError): replace(req, bars=(replace(req.bars[0],contract="MES1!"),)+req.bars[1:])
    with pytest.raises(ValueError): replace(req, bars=bars(20,date="2026-10-21")+req.bars)


def test_causal_historical_residuals_and_shapes(req):
    f=features(req)
    expected=np.cumsum([(b.high+b.low+b.close)/3*b.volume for b in req.bars])/np.cumsum([b.volume for b in req.bars])
    np.testing.assert_allclose(f.vwap,expected)
    np.testing.assert_allclose(f.residual,np.array([b.close for b in req.bars])-expected)
    assert f.z[-1]==pytest.approx(f.residual[-1]/np.std(f.residual[-20:]))
    assert f.context.shape==(1,1,40) and f.past.shape==(1,4,40)
    prefix=features(replace(req,bars=req.bars[:30],requested_at=req.bars[29].available_at))
    np.testing.assert_array_equal(prefix.past,f.past[:,:,:30])
    assert np.isnan(f.z[18]) and np.isfinite(f.z[19])


def test_horizon_uses_clock_not_row_shift(req):
    future=bars(60)
    out=horizon_targets(req,future)
    assert out[1]==future[40].close and out[15]==future[54].close
    gapped=tuple(b for i,b in enumerate(future) if i!=42)
    assert horizon_targets(req,gapped)[5] is None
    assert horizon_targets(req,tuple(replace(b,contract="MESH7") for b in future))[1] is None


def test_quantiles_fail_closed_and_identity(req,pred):
    with pytest.raises(ValueError): replace(pred,values=((float("nan"),)*21,)*5)
    with pytest.raises(ValueError): replace(pred,values=tuple(tuple(reversed(row)) for row in pred.values))
    with pytest.raises(ValueError): replace(pred,levels=(.1,.5,.9))
    flt=Filter(enabled=True,horizon=5,edge=0)
    c=Candidate(req.symbol,req.contract,1,req.origin,req.bars[-1].close,req.key)
    assert flt.evaluate(c,pred,req.requested_at)[0]
    assert not flt.evaluate(c,None,req.requested_at)[0]
    assert not flt.evaluate(c,pred,req.requested_at+timedelta(minutes=3))[0]
    assert not flt.evaluate(c,replace(pred,request_key="wrong"),req.requested_at)[0]
    assert not flt.evaluate(c,replace(pred,available_at=pred.available_at+timedelta(seconds=1)),req.requested_at)[0]
    assert Filter(enabled=False).evaluate(c,None,req.origin)==(True,"disabled")


def test_risk_is_final_and_unrealized_counted(req,pred):
    c=Candidate(req.symbol,req.contract,1,req.origin,req.bars[-1].close,req.key)
    risk=Risk(daily_max_loss=100)
    assert not entry_allowed(c,pred,req.origin,Filter(True),risk,RiskState(kill=True),True)[0]
    assert not risk.allow(RiskState(realized=-50,unrealized=-51))[0]
    assert not risk.allow(RiskState(data_fresh=False))[0]
    assert not risk.allow(RiskState(positions=1))[0]
    assert not entry_allowed(c,pred,req.origin,Filter(False),risk,RiskState(),False)[0]


def test_crossing_does_not_duplicate_and_rearms():
    s=SignalGenerator()
    assert s.direction(-3)==1
    assert s.direction(-4)==0
    assert s.direction(0)==0
    assert s.direction(-3)==1
    assert s.direction(3)==-1


def test_official_pin_and_signature_mock(req,tmp_path,monkeypatch):
    assert SOURCE_REVISION=="a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff"
    assert PINS["28M"].revision=="49b26409ac87b5935539a5d8ffe7f397b720db47"
    assert PINS["209M"].revision=="9874d252ab0aae16f7f7c999f98f98d6ad7d8365"
    calls={}
    class Tensor:
        def detach(self): return self
        def cpu(self): return self
        def numpy(self): return np.full((1,1,15,21),6000.)
    class Fake:
        @classmethod
        def from_pretrained(cls,path,*,revision,device,max_context,local_files_only):
            calls.update(locals()); return cls()
        def forecast(self,context,*,prediction_length,past_covariates,symmetric_averaging,clip_nonnegative):
            assert context.shape==(1,1,40) and past_covariates.shape==(1,4,40)
            assert prediction_length==15 and symmetric_averaging and not clip_nonnegative
            return type("Output",(),{"quantiles":Tensor(),"quantile_levels":LEVELS})()
    monkeypatch.setattr("mnq_timestral.model.verify_checkpoint",lambda *a:None)
    monkeypatch.setattr("mnq_timestral.model.verify_source",lambda:None)
    a=OfficialAdapter("28M",tmp_path,forecaster_class=Fake)
    p=a.predict(req)
    assert p.horizons==HORIZONS and p.model_revision==PINS['28M'].revision
    assert calls['local_files_only'] and calls['device']=='cpu'


def test_checkpoint_tampering_is_rejected(tmp_path):
    from mnq_timestral.model import verify_checkpoint
    (tmp_path/'config.json').write_text('{}')
    (tmp_path/'model.safetensors').write_bytes(b'fake')
    with pytest.raises(ValueError,match='checksum|size'): verify_checkpoint(tmp_path,PINS['28M'])


def test_official_target_only_ablation_has_no_covariates(req,tmp_path,monkeypatch):
    import numpy as np
    class Tensor:
        def detach(self):return self
        def cpu(self):return self
        def numpy(self):return np.full((1,1,15,21),6000.)
    class Fake:
        @classmethod
        def from_pretrained(cls,*args,**kwargs):return cls()
        def forecast(self,context,*,prediction_length,past_covariates,symmetric_averaging,clip_nonnegative):
            assert past_covariates is None
            return type('Output',(),{'quantiles':Tensor(),'quantile_levels':LEVELS})()
    monkeypatch.setattr('mnq_timestral.model.verify_checkpoint',lambda *a:None)
    monkeypatch.setattr('mnq_timestral.model.verify_source',lambda:None)
    pred=OfficialAdapter('28M',tmp_path,forecaster_class=Fake).predict(replace(req,variant='target_only'))
    assert pred.variant=='target_only'


def test_checkpoint_both_pins_config_hashes_and_bytes():
    assert PINS['28M'].config_sha256=='0cdf44b8ea981191de53078e0a5ecbbd437046bd939a546d5dbe17868f71281f'
    assert PINS['28M'].weights_bytes==111296464
    assert PINS['209M'].config_sha256=='1764139bb6d37ee5ff543f470495c086cfa6c373f7134fc61c7e3d844538bfd8'
    assert PINS['209M'].weights_bytes==837271648


def test_source_requires_verified_vcs_revision_and_installed_record(monkeypatch):
    from mnq_timestral.model import verify_source
    class Wrong:
        def read_text(self,path):return '{"vcs_info":{"commit_id":"main"}}'
    monkeypatch.setattr('mnq_timestral.model.importlib.metadata.distribution',lambda name:Wrong())
    with pytest.raises(ValueError,match='pinned Git'):verify_source()
