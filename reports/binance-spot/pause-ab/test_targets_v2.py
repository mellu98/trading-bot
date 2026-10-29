import importlib.util,sys,json
from pathlib import Path
s=importlib.util.spec_from_file_location('target_io',Path(__file__).with_name('targets-v2.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def test_partial_absent_targets_retain_last_valid(tmp_path):
 p=tmp_path/'targets.json';last={'phase':'A','pids':[1],'heartbeats':{}}
 assert m.read_targets(p,last)==last
 p.write_text('{"phase":');assert m.read_targets(p,last)==last
 m.atomic_targets(p,{'phase':'B','pids':[2],'heartbeats':{}})
 assert m.read_targets(p,last)['phase']=='B' and not p.with_name('targets.json.tmp').exists()
 p.write_text('[]');assert m.read_targets(p,last)==last


def test_external_probe_death_is_failclosed():
 assert m.probe_alive(type('P',(),{'poll':lambda s:None})())
 assert not m.probe_alive(type('P',(),{'poll':lambda s:1})())
