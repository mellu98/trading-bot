"""Progress transport only; no model or price fixtures."""
import json
from supervisor import ProgressDeadline,watch


def test_partial_absent_and_stale_never_reset_deadline(tmp_path):
 p=tmp_path/'progress.json';d=ProgressDeadline(p,100)
 assert not d.expired(200)
 p.write_text('{');assert not d.expired(300000000099)
 assert d.expired(300000000101)
 p.write_text(json.dumps({'stage':'forecast','started_mono_ns':200}));assert not d.expired(300000000101)
 p.write_text(json.dumps({'stage':'forecast','started_mono_ns':150}));assert d.expired(300000000201)
 p.unlink();assert d.expired(300000000201)


class Process:
 def __init__(self,statuses):self.statuses=iter(statuses);self.terminated=False;self.killed=False;self.returncode=None
 def poll(self):self.returncode=next(self.statuses);return self.returncode
 def terminate(self):self.terminated=True
 def wait(self,timeout=None):return 0
 def kill(self):self.killed=True


def test_completion_and_timeout_no_retry(tmp_path):
 d=ProgressDeadline(tmp_path/'absent',0);p=Process([None,0])
 assert watch(p,d,now=lambda:10,sleep=lambda _:None)==0 and not p.terminated
 p=Process([None]);assert watch(p,d,now=lambda:300000000001,sleep=lambda _:None)==124
 assert p.terminated
 p=Process([2]);assert watch(p,d,now=lambda:0,sleep=lambda _:None)==2
