"""One frozen F1-F5 validation; no source edits, credentials or external sockets."""
import os, sys, json, hashlib, subprocess, socket, tempfile, stat
from pathlib import Path
from collections import Counter
from decimal import Decimal
from datetime import datetime, timezone
ROOT=Path('/Users/locoframe/Desktop/TRADING BOT'); P=ROOT/'reports/databento/planning'
def load(n):return json.loads((P/n).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snap(paths):return {x:{'sha256':sha(ROOT/x),'mode':(ROOT/x).stat().st_mode} for x in paths}
baseline=load('baseline-integrity.json');audit=load('audit-probes.json');freeze=load('correction-source-freeze.json');before=load('correction-before.json');handoff=load('correction-handoff.json')
old90=baseline['all_existing_before'];primary37=baseline['primary_37']['files'];oldreports={k:v for k,v in before['files'].items() if k.startswith('reports/')}
paths=set(old90)|set(freeze['files'])|set(oldreports)
paths|={str(x.relative_to(ROOT)) for x in (P/'correction-study').rglob('*') if x.is_file()}
paths|={'reports/databento/planning/'+n for n in ['audit.txt','audit-probes.json','correction-before.json','correction-before-source.json','correction-source-freeze.json','correction-diff-size.json','correction-handoff.json']}
initial=snap(paths)
assert len(old90)==90 and len(primary37)==37 and len(freeze['files'])==20 and len(oldreports)==15
assert all(initial[k]['sha256']==v for k,v in old90.items())
assert all(initial[k]['mode']==audit['before_sha256_and_modes'][k]['mode'] for k in old90)
assert all(initial[k]['sha256']==v for k,v in primary37.items())
assert all(initial[k]['sha256']==v for k,v in freeze['files'].items())
assert all(initial[k]==v for k,v in oldreports.items())
assert all(initial[k]['mode']==v['mode'] for k,v in before['files'].items() if k in freeze['files'])
for k,v in handoff['evidence_sha256'].items():assert sha(ROOT/k)==v
runner='''import socket,ipaddress,sys
connect=socket.socket.connect;connect_ex=socket.socket.connect_ex;getaddrinfo=socket.getaddrinfo
attempts=[]
def allowed(addr):
 if isinstance(addr,str):return True
 host=addr[0]
 if host=='localhost':return True
 try:return ipaddress.ip_address(host).is_loopback
 except ValueError:return False
def guard(self,address):
 if not allowed(address):attempts.append(str(address));raise RuntimeError('external_socket_forbidden')
 return connect(self,address)
def guard_ex(self,address):
 if not allowed(address):attempts.append(str(address));raise RuntimeError('external_socket_forbidden')
 return connect_ex(self,address)
def resolve(host,*a,**kw):
 if host and not allowed((host,0)):attempts.append(str(host));raise RuntimeError('external_dns_forbidden')
 return getaddrinfo(host,*a,**kw)
socket.socket.connect=guard;socket.socket.connect_ex=guard_ex;socket.getaddrinfo=resolve
import pytest
result=pytest.main(['-p','no:cacheprovider','-q',sys.argv[1]])
print('EXTERNAL_SOCKET_ATTEMPTS',len(attempts))
raise SystemExit(result or (90 if attempts else 0))
'''
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR='/private/tmp')
env.pop('DATABENTO_API_KEY',None)
env['PYTHONPATH']=os.pathsep.join(str(ROOT/p) for p in ['adapters/databento_planner/src','adapters/databento/src','src'])
tests={}
for name,python,tests_path in [('new','adapters/databento_planner/.venv/bin/python','adapters/databento_planner/tests'),('existing-adapter','adapters/databento/.venv/bin/python','adapters/databento/tests'),('root','.venv/bin/python','tests')]:
 out=subprocess.run([str(ROOT/python),'-B','-c',runner,tests_path],cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
 (P/('scoped-fix-validation-tests-'+name+'.txt')).write_text(out.stdout+out.stderr)
 tests[name]={'exit_code':out.returncode,'tail':(out.stdout+out.stderr).splitlines()[-3:]}
 assert out.returncode==0,tests[name]
# All further code is offline; prohibit every external socket and no API construction.
def deny(*args,**kwargs):raise RuntimeError('network_forbidden_validator')
socket.create_connection=deny;socket.socket.connect=deny;socket.getaddrinfo=deny
sys.path[:0]=env['PYTHONPATH'].split(os.pathsep)+[str(ROOT/'adapters/databento_planner/tests')]
from mnq_data.core import digest
from databento_planner.planner import sessions,comparison
from databento_planner.security import PlannerError
from databento_planner.paths import contained
from databento_planner.cache import Cache
from databento_planner.gate import validate_job,acquisition_digest
from test_planner import Backend,identity,job,NOW
from dataclasses import replace
probes={}
with tempfile.TemporaryDirectory(prefix='scoped-fix-',dir='/private/tmp') as td:
 t=Path(td); boundary=t/'root';boundary.mkdir();outside=t/'outside';outside.mkdir();(boundary/'link').symlink_to(outside,target_is_directory=True)
 for candidate in [boundary/'..'/'escape',boundary/'link'/'escape',boundary,boundary/'nested'/'..'/'escape']:
  try:contained(candidate,boundary)
  except PlannerError:pass
  else:raise AssertionError('F1 rejection failed')
 assert contained(boundary/'valid',boundary)==boundary/'valid'
 probes['F1']='PASS: traversal, nested traversal, symlink and root-self reject; regression suite verifies zero compare/gate backend calls and leases'
 try:replace(identity(),publisher_id=2).validate()
 except PlannerError:pass
 else:raise AssertionError('F2 foreign publisher accepted')
 identity().validate();probes['F2']='PASS: caller publisher2 independently rejected; publisher1 accepted; encoded foreign-record registration covered by regression'
 b=Backend();r=comparison(b,NOW,now=NOW,checkpoint=t/'study',max_calls=6)
 assert len(b.calls)==6 and r['scenarios']['1']['total_cost_usd'] is None
 costfiles=[x for x in (t/'study').glob('*.json') if json.loads(x.read_text()).get('identity',{}).get('endpoint')=='get_cost']
 assert len(costfiles)==1 and json.loads(costfiles[0].read_text())['value']=='0.000123'
 for _ in range(6):r=comparison(b,NOW,now=NOW,checkpoint=t/'study',max_calls=60)
 assert len(b.calls)==365 and r['status']=='verified_metadata'
 assert len(set(digest([a,n,k]) for a,n,k in b.calls))==365
 later=comparison(b,NOW,now='2026-10-26T12:00:00Z',checkpoint=t/'study',max_calls=0)
 assert len(b.calls)==365 and not later['acquisition_quotes_all_current'] and not later['download_authorized']
 assert next(x for x in b.calls if x[1]=='get_cost')[2]['start'].startswith('2026-10-23')
 probes['F3']='PASS: genuine partial cost survives, incomplete scenario null, exact endpoints resumed once, mismatches/interruption covered by regression'
 probes['F4']='PASS: 6+6x60 bounded requests finish365, newest first, no duplicate endpoint and zero-call expired historical reread; deadline remaining timeout covered by regression'
 j=job();j['partitions'].append({**j['partitions'][0],'start_ns':120_000_000_000,'end_ns':180_000_000_000});d=acquisition_digest(j);validate_job(j);assert d==acquisition_digest(j)
 j['partitions'][0]['end_ns']=180_000_000_000
 try:validate_job(j)
 except PlannerError:pass
 else:raise AssertionError('F5 overlap accepted')
 probes['F5']='PASS: adjacent intervals preserve approval digest; intersecting same identity rejected; zero quote/lease/acquire covered by regression'
# Independently recompute official saved response values, no network or checkpoint edits.
study=load('correction-study/cost-comparison-complete.json');execution=load('correction-study/metadata-execution-complete.json');manifest=load('correction-study/checkpoints/snapshot.json')
assert digest(manifest['snapshot'])==manifest['sha256']==study['checkpoint_snapshot_sha256']
assert study['sessions']==sessions(study['as_of'],60)==manifest['snapshot']['sessions']
entries={};endpoint_counts=Counter()
for f in (P/'correction-study/checkpoints').glob('*.json'):
 if f.name=='snapshot.json':continue
 e=json.loads(f.read_text());i=e['identity'];key=digest(i)
 assert f.stem==key and e['value_sha256']==digest(e['value']) and i['snapshot']==manifest['sha256'] and e['http_status']==200
 assert e['scope']=='historical_study_only_not_acquisition_approval'
 assert i['request']['dataset']=='GLBX.MDP3'
 assert key not in entries;entries[key]=e;endpoint_counts[i['area']+'.'+i['endpoint']]+=1
assert len(entries)==365
assert len(execution['http'])==365 and all(t['http_status']==200 for t in execution['http'])
assert Counter(t['endpoint'].replace('/v0/','') for t in execution['http'])==endpoint_counts
assert endpoint_counts=={'metadata.get_cost':120,'metadata.get_billable_size':120,'metadata.get_record_count':120,'metadata.list_schemas':1,'metadata.get_dataset_range':1,'metadata.get_dataset_condition':1,'symbology.resolve':2}
assert len({digest(p['request']) for p in study['partitions']})==120
for p in study['partitions']:
 req=p['request'];assert req['schema']=='ohlcv-1m' and req['stype_in']=='raw_symbol' and req['symbols']==[p['contract']]
 assert req['start']==p['date']+'T13:30:00Z' and req['end']==p['date']+'T20:00:00Z'
 mappings=[x for x in study['mapping']['intervals'] if x['root']==p['root'] and x['start_date']<=p['date']<x['end_date']]
 assert len(mappings)==1 and mappings[0]['contract']==p['contract'] and mappings[0]['instrument_id']==p['instrument_id']
 for endpoint,field in [('get_cost','estimated_cost_usd'),('get_billable_size','billable_uncompressed_bytes'),('get_record_count','records')]:
  ev=p['metric_evidence'][endpoint];e=entries[digest(ev['identity'])];assert ev['identity']['request']==req
  assert e['value']==p[field]
 assert p['records']==390 and p['billable_uncompressed_bytes']==21840
conditions=[e['value'] for e in entries.values() if e['identity']['endpoint']=='get_dataset_condition'][0]
assert all(next(x for x in conditions if x['date']==s['date'])['condition']=='available' for s in study['sessions'])
assert len(study['conditions'])==60 and all(x['condition']=='available' for x in study['conditions'])
assert study['dataset_range']==next(e['value'] for e in entries.values() if e['identity']['endpoint']=='get_dataset_range')
table=[]
for n in [1,5,20,60]:
 dates={s['date'] for s in study['sessions'][-n:]};row={'sessions':n,'first_session':min(dates),'last_session':max(dates)}
 total=Decimal(0);records=size=0
 for root in ['MNQ','MES']:
  ps=[p for p in study['partitions'] if p['date'] in dates and p['root']==root];assert len(ps)==n
  cost=sum((Decimal(p['estimated_cost_usd']) for p in ps),Decimal(0));nr=sum(p['records'] for p in ps);nb=sum(p['billable_uncompressed_bytes'] for p in ps)
  expected=study['scenarios'][str(n)]['roots'][root]
  assert cost==Decimal(expected['cost_usd']) and nr==expected['records'] and nb==expected['billable_uncompressed_bytes']
  row[root+'_usd']=str(cost);total+=cost;records+=nr;size+=nb
 expected=study['scenarios'][str(n)];assert total==Decimal(expected['total_cost_usd']) and records==expected['total_records'] and size==expected['total_billable_uncompressed_bytes']
 row.update(total_usd=str(total),records=records,billable_uncompressed_bytes=size);table.append(row)
assert not execution['billable_data_calls'] and not execution['data_downloads'] and not execution['purchases']
assert not study['download_authorized'] and not study['data_acquisition_calls'] and study['cache_actual_objects']==0
batch_counts=[]
for f in (P/'correction-study/batches').glob('*.json'):
 b=json.loads(f.read_text());batch_counts.append(len(b['http']));assert len(b['http'])<=60
assert sorted(batch_counts)==[5,60,60,60,60,60,60]
after=snap(paths);assert after==initial
out={'status':'PASS','scope':'ONE read-only frozen F1-F5 fix validation; no fresh review/budget/native receipt','skill_resolution':'paths-injected','checked_at':datetime.now(timezone.utc).isoformat(),'findings':probes,'tests':tests,'immutability':{'preexisting_sha_mode_paths':90,'primary_sha_paths':37,'frozen_package_sha_mode_paths':20,'old_planning_reports_sha_mode':15,'total_before_after_paths':len(paths),'all_unchanged':True,'new_three_path_modes':{k:initial[k]['mode'] for k in freeze['files'] if k not in before['files']}},'study':{'official_persisted_http200_responses':365,'unique_exact_partitions':120,'endpoint_counts':dict(endpoint_counts),'batch_counts':sorted(batch_counts),'table':table,'rollovers':study['mapping']['rollovers'],'dataset_ohlcv1m_range':study['dataset_range']['schema']['ohlcv-1m'],'conditions':'60 selected dates available, vendor declared only','zero_dataendpoint_traces':True,'historical_estimates_not_acquisition_authority':True,'original_study_generated_at':study['generated_at'],'earliest_quote_expires_at':study['expires_at'],'no_keychain_or_credentials_accessed_by_validator':True},'boundaries':['No acquired raw quality/gaps or economic performance verified.','Paid entitlement, license and balance untested; metadataHTTP200 alone not proof.','Stored Keychain key remains incomplete according to safe evidence; complete prefix only in memory, not independently reread.','No production paid backend; future injected gate only.','No native gentle-ai receipt/no Git.','Future acquisition needs fresh exact-scope quote, configured cap and explicit manual approval even at zero USD.'],'all_writes_stopped_after_reports':True}
(P/'scoped-fix-validation.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
text=['SCOPED FIX VALIDATION: PASS','Skill resolution: paths-injected','Scope: F1-F5 only; no native receipt or new review budget.']+[f'{k}: {v}' for k,v in probes.items()]+['Tests: '+json.dumps(tests),'Immutability: '+json.dumps(out['immutability']),'Persisted official quotes independently recomputed: '+json.dumps(table),'365 unique HTTP200 endpoint responses;7 batches; no data endpoints.']+out['boundaries']+['ALL WRITES STOPPED']
(P/'scoped-fix-validation.txt').write_text('\n'.join(text)+'\n')
print(json.dumps(out,indent=2))
