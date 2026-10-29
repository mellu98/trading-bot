"""Read-only future collection controls, no simulated orders or model fixture PnL."""
from shadow import ClosedBuilder,prospective_allowed


def minute(i,final=True):return {'t':i*60000,'T':i*60000+59999,'x':final,'o':'100','h':'102','l':'99','c':'101','v':'1'}

def test_only_240_contiguous_closed_minutes_form_utc4h():
 b=ClosedBuilder();assert b.add(minute(0,False)) is None
 for i in range(239):assert b.add(minute(i)) is None
 out=b.add(minute(239));assert out['start_ns']==0 and out['end_ns']==14400000000000 and out['close']=='101'
 b=ClosedBuilder()
 for i in list(range(100))+list(range(101,240)):assert b.add(minute(i)) is None
 assert b.add(minute(240)) is None


def test_older_backfill_not_prospective_and_unhealthy_suppressed():
 assert prospective_allowed(1000,1010,True,256)
 assert not prospective_allowed(1000,1301,True,256)
 assert not prospective_allowed(1000,1010,False,256)
 assert not prospective_allowed(1000,1010,True,255)
 assert not prospective_allowed(1000,999,True,256)
