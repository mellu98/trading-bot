from pathlib import Path
import json
import pytest
from mnq_sim.research_v2 import verify_manifest, prior_regimes, robust_intervals


def test_archive_manifest_detects_mutation(tmp_path):
    import hashlib
    p=tmp_path/'x';p.write_text('original')
    manifest={'files':{'x':hashlib.sha256(p.read_bytes()).hexdigest()}}
    assert verify_manifest(tmp_path,manifest)==1
    p.write_text('changed')
    with pytest.raises(ValueError):verify_manifest(tmp_path,manifest)


def test_regimes_only_use_prior_sessions():
    days=[f'2026-06-{i:02d}' for i in range(1,26)]
    widths={d:float(i+1) for i,d in enumerate(days)}
    original=prior_regimes(widths)
    changed=prior_regimes({**widths,days[-1]:100000})
    assert {d:original[d] for d in days[:-1]}=={d:changed[d] for d in days[:-1]}
    assert all(original[d]['label']=='unclassified' for d in days[:20])
    assert original[days[20]]['threshold']==10.5


def test_intervals_do_not_claim_independent_validation():
    result=robust_intervals([1.]*120)
    assert result['independent_evidence'] is False
    assert set(result['by_block_length'])=={'1','5','10'}
    assert all(v['lower_family_adjusted']>0 for v in result['by_block_length'].values())
