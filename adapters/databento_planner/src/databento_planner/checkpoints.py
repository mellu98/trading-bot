"""Durable exact-response study checkpoints: not raw coverage or approval."""
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
from mnq_data.core import digest, iso, utc
from .cache import atomic_json
from .paths import contained
from .security import PlannerError

class BatchComplete(PlannerError): pass


class StudyBackend:
    def __init__(self, backend, snapshot, directory=None, max_calls=None, now=None):
        self.backend=backend; self.snapshot=digest(snapshot);self.revision=None
        self.directory=Path(directory).absolute() if directory is not None else None
        self.max_calls=max_calls;self.calls=0;self.reused=0;self.entries={}
        self.clock=now if callable(now) else lambda:utc(now) if now else pd.Timestamp(datetime.now(timezone.utc))
        if self.directory is not None:
            contained(self.directory,self.directory.parent).mkdir(parents=True,exist_ok=True)
            manifest=contained(self.directory/'snapshot.json',self.directory)
            if manifest.exists():
                if json.loads(manifest.read_text())!={'snapshot':snapshot,'sha256':self.snapshot}:
                    raise PlannerError('incompatible_checkpoint_snapshot')
            else: atomic_json(manifest,{'snapshot':snapshot,'sha256':self.snapshot})

    def call(self,area,name,**kwargs):
        identity={'snapshot':self.snapshot,'revision':self.revision,'area':area,'endpoint':name,'request':kwargs}
        key=digest(identity);path=contained(self.directory/(key+'.json'),self.directory) if self.directory else None
        entry=None
        if path is not None and path.exists():
            try:
                entry=json.loads(path.read_text())
                if (entry['identity']!=identity or entry['value_sha256']!=digest(entry['value'])
                        or utc(entry['checked_at'])>utc(self.clock())
                        or utc(entry['expires_at'])!=utc(entry['checked_at'])+pd.Timedelta(minutes=15)):
                    raise ValueError()
            except Exception: raise PlannerError('invalid_checkpoint_manual_resolution_required') from None
            self.reused+=1
        if entry is None:
            if self.max_calls is not None and self.calls>=self.max_calls:
                raise BatchComplete('metadata_batch_limit')
            self.calls+=1
            value=self.backend.call(area,name,**kwargs)
            if name=='get_cost':
                from .planner import money
                value=str(money(value));kind='usd_decimal_string'
            elif name in ('get_billable_size','get_record_count'):
                if type(value) is not int or value<0: raise PlannerError('invalid_size_or_count')
                kind='nonnegative_integer'
            else:
                if not isinstance(value,list if name in ('list_schemas','get_dataset_condition') else dict):
                    raise PlannerError('invalid_discovery_response')
                kind='discovery_json'
            checked=utc(self.clock())
            trace=getattr(self.backend,'trace',[])
            entry={'identity':identity,'value':value,'value_type':kind,'value_sha256':digest(value),
                'checked_at':iso(checked),'expires_at':iso(checked+pd.Timedelta(minutes=15)),
                'http_status':trace[-1]['http_status'] if trace else None,
                'scope':'historical_study_only_not_acquisition_approval'}
            if path is not None: atomic_json(path,entry)
        self.entries[key]=entry
        return entry['value']

    def evidence(self,name,request):
        identity={'snapshot':self.snapshot,'revision':self.revision,'area':'metadata','endpoint':name,'request':request}
        return {k:v for k,v in self.entries[digest(identity)].items() if k!='value'}
