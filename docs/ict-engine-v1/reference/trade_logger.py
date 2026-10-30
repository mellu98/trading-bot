import json
from hashlib import sha256
class AuditLog:
    def __init__(self,path):self.path=path
    def append(self,event):
        canonical=json.dumps(event,sort_keys=True,separators=(',',':'),allow_nan=False)
        record={'event':event,'sha256':sha256(canonical.encode()).hexdigest()}
        with open(self.path,'a',encoding='utf8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
