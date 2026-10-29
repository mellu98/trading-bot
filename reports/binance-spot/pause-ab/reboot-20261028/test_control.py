"""Synthetic finite-B controls; never opens a market connection."""
import importlib.util
from pathlib import Path
p=Path(__file__).with_name('control.py');s=importlib.util.spec_from_file_location('reboot_control',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def valid():return {'duration':300,'w_duration':300,'rejections':0,'w_rejections':0,'max_queue':2,'w_max_queue':2,'overflow':0,'unexpected_disconnects':0,'data_complete':True,'fresh_failures':0,'fresh_initialized':True,'feed_gap_block':False}
def test_original_guards_and_separate_freshness():
 x=valid();assert m.assess(x)['processing']=='PASS' and m.assess(x)['overall']=='PASS'
 x['fresh_failures']=1;assert m.assess(x)['processing']=='PASS' and m.assess(x)['overall']=='FAIL'
 assert not m.should_repeat(m.assess(x))
def test_no_pass_with_short_missing_or_delayed_measurement():
 for key,value in [('duration',299),('w_duration',299),('data_complete',False),('rejections',1),('max_queue',251),('overflow',1),('unexpected_disconnects',1)]:
  x=valid();x[key]=value;assert m.assess(x)['overall']!='PASS'
def test_gap_does_not_certify_feed_or_invent_runtime_readiness():
 x=valid();x['feed_gap_block']=True;a=m.assess(x);assert a['processing']=='PASS' and a['feed']=='BLOCKED' and a['overall']=='FAIL'
 assert m.should_repeat(a) # One predefined repeat tests local processing/freshness only, not gap approval.
def test_no_full_observer_restore_and_no_profiler():
 text=p.read_text();assert "sampling_enabled':False" in text
 assert 'run-binance-paper.sh' not in text and "spawn('A'" not in text and 'docker' not in text
