import json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from execution_adapter import SimulationAdapter
cfg=json.loads(Path(__file__).with_name('strategy_config.yaml').read_text())
from market_data import Bar
now=datetime(2026,1,5,14,tzinfo=timezone.utc)
s={'signal_id':'synthetic-only','known_at':now.isoformat(),'expires_at':(now+timedelta(hours=1)).isoformat(),'direction':1,'entry':100.,'stop':98.,'target':104.,'qty':0.5}
a=SimulationAdapter(cfg);a.create(s)
a.on_bar(Bar(now+timedelta(minutes=5),101,102,99,101),.02)
a.on_bar(Bar(now+timedelta(minutes=10),102,105,101,104),.02)
print(json.dumps({'label':'SYNTHETIC EXECUTION DEMO — NOT A BACKTEST','trades':a.fills},indent=2))
