import pytest
from mnq_sim.quant import select_validation_arm, block_interval, fee_for_date, bucket
from datetime import datetime


def test_select_only_validation_and_cash_if_both_lose():
    assert select_validation_arm({'fixed':-1,'vwap':-2})=='NO_TRADE'
    assert select_validation_arm({'fixed':1,'vwap':1})=='fixed'
    assert select_validation_arm({'fixed':1,'vwap':2})=='vwap'


def test_insufficient_sample_cannot_claim_edge():
    assert block_interval([10]*5)['positive_edge_supported'] is False


def test_fee_date_and_time_bucket():
    assert fee_for_date('2026-06-30')==.02 and fee_for_date('2026-07-01')==.01
    assert bucket('2026-10-19T14:00:00+00:00')=='morning'
    assert bucket('2026-10-19T18:00:00+00:00')=='afternoon'


def test_block_bootstrap_reproducible_and_negative_edge():
    a=block_interval([-1.]*50);b=block_interval([-1.]*50)
    assert a==b and a['simultaneous_lower_mean']<0 and not a['positive_edge_supported']


def test_regime_threshold_is_not_backdated_into_calibration():
    from mnq_sim.quant import regime_label
    assert regime_label('2026-05-05',.5,.1,'2026-06-01')=='calibration_unclassified'
    assert regime_label('2026-06-02',.5,.1,'2026-06-01')=='high'
