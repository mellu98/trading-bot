import importlib.util,sys
from pathlib import Path
import pytest
p=Path(__file__).with_name('recorder.py');s=importlib.util.spec_from_file_location('forward_recorder',p);r=importlib.util.module_from_spec(s);sys.modules[s.name]=r;s.loader.exec_module(r)


def test_closed_native_context_excludes_forming_and_rejects_gap():
    h=r.STEP_MS
    rows=[[i*h,'100','102','99','101','1',i*h+h-1] for i in range(257)]
    bars=r.closed(rows,256*h)
    assert len(bars)==256 and bars[-1].end==256*h*1000000
    with pytest.raises(ValueError):r.closed(rows[:40]+rows[41:],256*h)


def test_no_order_signal_gate_keeps_stability_and_news_blocked():
    assert r.reasons({'observe_only':True,'timestral':'DISABLED','feed_metrics':{'passed':True}},True)==['STABILITY_READINESS_BLOCKED','STRICT_NEWS_UNCERTIFIED','NO_ORDER_CAPABILITY']
    assert 'FEED_CERTIFICATE_BLOCKED' in r.reasons({'feed_metrics':{'passed':False}},True)
    assert 'NOT_CURRENT_PUBLICATION' in r.reasons({},False)
