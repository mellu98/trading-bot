"""Final bounded check against immutable captured payloads, never network."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import importlib.util,json
import pytest
from mnq_local.capital_candles import parse_candle

ROOT=Path(__file__).resolve().parents[1]

def raw_bar():
    return {'snapshotTimeUTC':'2026-10-26T15:00:00','openPrice':{'bid':100,'ask':101},
        'highPrice':{'bid':120,'ask':121},'lowPrice':{'bid':90,'ask':91},
        'closePrice':{'bid':110,'ask':111},'lastTradedVolume':25}

def test_parser_does_not_compare_bid_high_against_ask_low():
    raw=raw_bar();before=deepcopy(raw)
    assert raw['highPrice']['bid']>raw['lowPrice']['ask']
    parsed=parse_candle('US100','MINUTE',raw)
    assert raw==before and Decimal(parsed['prices']['high']['bid'])==120

@pytest.mark.parametrize('field',['openPrice','closePrice','highPrice','lowPrice'])
def test_only_homologous_field_inversions_are_rejected(field):
    raw=raw_bar();raw[field]['ask']=raw[field]['bid']-Decimal('.1')
    # Keep each side's own OHLC geometry valid so this exercises the pairing.
    if field=='openPrice':raw['openPrice']['bid']=100;raw['openPrice']['ask']=Decimal('99.9')
    with pytest.raises(ValueError,match='Crossed native bid/ask'):parse_candle('US100','MINUTE',raw)

def test_raw_payload_check_is_independent_and_does_not_mutate_evidence():
    spec=importlib.util.spec_from_file_location('capital_final_check',ROOT/'reports/market-data-closeout/capital_final_check.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.analyze(ROOT/'reports/capital-v63/raw-candles.jsonl')
    assert result['responses']==1328 and result['homologous_inverted_responses']==100
    assert result['parser_rejection_disagreements']==0 and result['parser_field_mismatches']==0
    assert result['post_successor_revision_events']==204
    assert result['closed_revision_fields']==['closePrice.ask','highPrice.ask','lowPrice.ask','openPrice.ask']
    assert result['revision_age_seconds']['max']>120
    assert result['source_file_unchanged']
