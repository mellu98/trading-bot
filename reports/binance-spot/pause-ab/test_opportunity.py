"""Configuration regression for the single separately frozen missing-contrast opportunity."""
from pathlib import Path
import ast

def test_single_pair_has_no_cache_or_guard_override():
 p=Path(__file__).with_name('control-opportunity.py');source=p.read_text();ast.parse(source)
 assert "enumerate('AB',1)" in source
 assert 'connected>=300' in source and 'begin>450' in source and 'begin>45' in source
 assert "OUT=BASE/'opportunity'" in source
 assert "BASE/'runtime-v2.py'" in source and "BASE/'external-v2.py'" in source
 assert "BASE/'main/live/complete.json'" in source
 assert "opportunity-addendum.json" in source
 assert 'exchangeInfo' not in source and 'PublicREST' not in source
 assert 'probe_alive(external)' in source and 'atomic_targets' in source
