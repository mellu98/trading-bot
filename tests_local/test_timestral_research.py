"""Causality and immutable experiment controls; real model tests run separately."""
from dataclasses import replace
from datetime import timedelta
import pytest
from mnq_local.replay import load_session
from mnq_local.timestral_research import request_spec, filter_side, manifest, combine_scores
from mnq_timestral.schema import Request
from test_timestral_experiment import prediction


def test_request_key_binds_model_variant_origin_and_full_prefix():
    bars,_=load_session('2026-10-19')
    bars=tuple(b for b in bars if b.symbol=='MES')
    spec=request_spec(bars,20,'target_only')
    req=Request(bars[:20],bars[19].end,model='28M',variant='target_only')
    assert spec['request_key']==req.key and spec['n']==20
    assert spec['origin']==req.origin.isoformat()
    assert manifest()['independent_evidence'] is False
    assert manifest()['filter']['horizon']==5


def test_missing_delayed_or_wrong_contract_never_becomes_a_signal():
    bars,_=load_session('2026-10-19');bb=tuple(b for b in bars if b.symbol=='MES')
    req=Request(bb[:20],bb[19].end,model='28M',variant='target_only')
    p=prediction(req,offset=50)
    now=bb[20].end
    assert filter_side(1,bb[20],p,req.key)[0]==1
    assert filter_side(1,bb[20],None,req.key)[0]==0
    assert filter_side(1,bb[20],replace(p,available_at=now+timedelta(seconds=1)),req.key)[0]==0
    assert filter_side(1,bb[20],replace(p,contract='MESU6'),req.key)[0]==0


def test_weighted_metric_denominators():
    a={'1':{'count':1,'mae':2.,'random_walk_mae':4.,'directional_calls':1,'directional_accuracy':1.,'pinball':{'0.5':1.},'coverage':{'0.5':1.},'central80_coverage':1.,'central80_width':2.}}
    b={'1':{'count':3,'mae':6.,'random_walk_mae':4.,'directional_calls':0,'directional_accuracy':None,'pinball':{'0.5':3.},'coverage':{'0.5':0.},'central80_coverage':0.,'central80_width':6.}}
    r=combine_scores([a,b])['1']
    assert r['mae']==5 and r['mae_skill_vs_random_walk']==-.25
    assert r['coverage']['0.5']==.25
    assert r['directional_accuracy']==1
