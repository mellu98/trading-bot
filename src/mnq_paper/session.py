"""Independent Paper UI evidence. The TWS API has no universal Paper-mode flag.

This file is never self-issued from DU/port/AccountType. An authorized human or
native UI inspection must first observe an AUTHENTICATED Paper session and the
selected authorized account. This is external evidence, not cryptographic proof
of broker mode; its provenance must be checked during real acceptance.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def listener_identity(port):
    if port not in (7497,4002):raise ValueError('Non-paper endpoint forbidden')
    result=subprocess.run(['/usr/sbin/lsof','-nP',f'-iTCP:{port}','-sTCP:LISTEN','-Fp'],capture_output=True,text=True,timeout=5)
    pids={int(line[1:]) for line in result.stdout.splitlines() if line.startswith('p')}
    if len(pids)!=1:raise ValueError('Exactly one local Gateway/TWS listener required')
    pid=pids.pop()
    def ps(field):
        return subprocess.check_output(['/bin/ps','-p',str(pid),'-o',field+'='],text=True,timeout=5).strip()
    image=Path(ps('comm')).resolve();started=ps('lstart')
    app=next((p for p in image.parents if p.suffix=='.app'),None)
    if app is None:raise ValueError('Listener is not bound to a signed native IB application')
    verified=subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],capture_output=True,timeout=10)
    signature=subprocess.run(['/usr/bin/codesign','-dv','--verbose=2',str(app)],capture_output=True,text=True,timeout=5)
    if verified.returncode or 'TeamIdentifier=L6H6D9Q7DY' not in signature.stderr:raise ValueError('Official Interactive Brokers application signature required')
    return {'pid':pid,'started':started,'image':str(image),'team':'L6H6D9Q7DY'}


class SessionProof:
    def __init__(self,path,probe=listener_identity):self.path=Path(path);self.probe=probe

    def validate(self,config,accounts):
        if self.path.stat().st_mode&0o077:raise ValueError('Session evidence must be private (0600)')
        value=json.loads(self.path.read_text())
        if value.get('source')!='authenticated_native_ui_observation' or value.get('authenticated') is not True:
            raise ValueError('Independent authenticated Paper UI evidence missing')
        if value.get('paper_indicator') not in ('Paper Trading','Simulated Trading'):
            raise ValueError('Paper session indicator not observed')
        if accounts!=[config.account] or value.get('account')!=config.account or value.get('ui_account')!=config.account:
            raise ValueError('Authorized/UI/API account identities do not agree')
        at=datetime.fromisoformat(value['observed_at'])
        if at.tzinfo is None:raise ValueError('Timezone-aware session observation required')
        age=(datetime.now(timezone.utc)-at).total_seconds()
        if not 0<=age<=12*3600:raise ValueError('Paper UI evidence expired; re-observe session')
        if value.get('port')!=config.port or value.get('process')!=self.probe(config.port):
            raise ValueError('Paper observation does not match current signed listener process')
        readonly=Path(value['read_only_report_path'])
        if hashlib.sha256(readonly.read_bytes()).hexdigest()!=value.get('read_only_report_sha256'):
            raise ValueError('Initial authenticated Read-Only report changed or missing')
        report=json.loads(readonly.read_text())
        if report.get('scope')!='ACTUAL_IB_READ_ONLY_RESPONSES' or report.get('authenticated_protocol') is not True or report.get('api_read_only') is not True or report.get('orders_sent')!=0:
            raise ValueError('Actual initial Read-Only API verification required')
        if report.get('account_identity')!=hashlib.sha256(config.account.encode()).hexdigest():
            raise ValueError('Read-Only verification belongs to another account')
        evidence=Path(value['evidence_path'])
        if hashlib.sha256(evidence.read_bytes()).hexdigest()!=value.get('evidence_sha256'):
            raise ValueError('Paper UI evidence integrity mismatch')
        return value
