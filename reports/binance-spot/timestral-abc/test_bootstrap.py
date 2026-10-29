"""Synthetic native4h warmup and complete1m reconciliation, no new financial periods."""
import pytest
from bootstrap import select_closed,fold_minutes


def row(i,step=14400000):return [i*step,'100','102','99','101','1',(i+1)*step-1,'1',1,'1','1','0']


def test_native256_closed_contiguous_no_forming_or_gap():
 rows=[row(i) for i in range(301)];bars,excluded=select_closed(rows,300*14400000)
 assert len(bars)==256 and bars[0]['start_ns']==44*14400000000000 and bars[-1]['end_ns']==300*14400000000000 and excluded==1
 with pytest.raises(ValueError):select_closed(rows[:200]+rows[201:],300*14400000)
 broken=[row(i) for i in range(300)];broken[-1][6]-=1
 with pytest.raises(ValueError):select_closed(broken,300*14400000)


def test_reconcile_only_complete240native_minutes():
 bars=[row(i,60000) for i in range(240)]
 b=fold_minutes(bars,14400000000000);assert b['end_ns']==14400000000000 and b['volume']=='240'
 with pytest.raises(ValueError):fold_minutes(bars[:-1],14400000000000)
