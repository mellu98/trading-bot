"""Transient telemetry targets: atomic publication and last-valid reads, not journal."""
import json,os
from pathlib import Path

def atomic_targets(path,value):
 path=Path(path);tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(value,sort_keys=True)+'\n');os.replace(tmp,path)

def read_targets(path,last):
 try:
  doc=json.loads(Path(path).read_text())
  if not isinstance(doc,dict) or not all(k in doc for k in ['phase','pids','heartbeats']):return last
  return doc
 except (OSError,ValueError):return last

def probe_alive(process):return process.poll() is None
