"""Deterministic buffered-frame burst regression; no live connection or orders."""
import asyncio
import pytest
from mnq_local.binance_app import cooperative_enqueue

class MeasuredQueue(asyncio.Queue):
 def __init__(self):super().__init__(512);self.peak=0
 def put_nowait(self,value):
  super().put_nowait(value);self.peak=max(self.peak,self.qsize())

async def burst(enqueue,n):
 q=MeasuredQueue();seen=[]
 async def consumer():
  while True:
   x=await q.get();seen.append(x);q.task_done()
 c=asyncio.create_task(consumer())
 try:
  for i in range(n):await enqueue(q,i)
  await q.join();return q,seen
 finally:c.cancel();await asyncio.gather(c,return_exceptions=True)

@pytest.mark.parametrize('n',[513,10000])
def test_old_buffered_pump_overflows_but_fair_pump_keeps_every_frame(n):
 async def greedy(q,x):q.put_nowait(x)
 with pytest.raises(asyncio.QueueFull):asyncio.run(burst(greedy,n))
 q,seen=asyncio.run(burst(cooperative_enqueue,n))
 assert q.maxsize==512 and q.peak<=32 and seen==list(range(n))

def test_full_queue_still_fails_closed_without_capacity_or_threshold_change():
 async def scenario():
  q=MeasuredQueue()
  for i in range(512):q.put_nowait(i)
  with pytest.raises(asyncio.QueueFull):await cooperative_enqueue(q,'overflow')
  assert q.qsize()==512
 asyncio.run(scenario())
