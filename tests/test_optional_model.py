"""Optional real cached-checkpoint smoke test, not market-performance validation."""
import os
from dataclasses import replace
import pytest
from mnq_timestral.model import OfficialAdapter


@pytest.mark.real_model
@pytest.mark.parametrize('model',['28M','209M'])
def test_explicitly_provisioned_local_checkpoint(req,model):
    path=os.environ.get('TIMESTRAL_CHECKPOINT_'+model.upper())
    if not path:pytest.skip('No explicitly provisioned licensed checkpoint; real inference not evaluated')
    adapter=OfficialAdapter(model,path)
    result=adapter.predict(replace(req,model=model))
    assert len(result.medians)==5 and result.context_length==len(req.bars)
    assert result.latency_seconds>0
