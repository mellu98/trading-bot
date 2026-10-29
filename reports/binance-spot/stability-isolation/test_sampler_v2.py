import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('sampler_v2',Path(__file__).with_name('sampler-v2.py'));m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)


def test_iostat_first_numeric_sample_is_not_interval():
 c=m.IntervalRows()
 assert c.add(' KB/t tps MB/s us sy id') is None
 first=c.add(' 10.0 50 0.5 20 10 70')
 second=c.add(' 20.0 100 2.0 30 20 50')
 assert first['interval_valid'] is False and second['interval_valid'] is True
 assert second['system_cpu_percent']=={'user':30.,'system':20.,'idle':50.}
 assert second['disk_columns']==[20.,100.,2.]


def test_equal_low_probe_policy_has_no_top_or_single_iostat():
 commands=m.low_commands([1,2])
 assert len(commands)==4 and all('top' not in cmd and 'iostat' not in cmd for cmd in commands.values())
 assert commands['processes'][-1]=='pid=,rss=,%cpu=,time=,pagein='
