"""Read-only pinned pure accounting import; never operational Runtime/Risk."""
from pathlib import Path
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];OLD=ROOT/'research/strategy-discovery-2026'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(OLD/'source-freeze.json')=='17d58cc404464ff6e812755cf514f98e14eaa7e29ae608310d03f073b1e0b410'
f=json.loads((OLD/'source-freeze.json').read_text());assert sha(OLD/'engine.py')==f['sources']['engine.py']
spec=importlib.util.spec_from_file_location('round2_pinned_pure_accounting',OLD/'engine.py');module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
Portfolio,Costs,cap,summarize,sharpe=(getattr(module,k) for k in ['Portfolio','Costs','cap','summarize','sharpe'])
