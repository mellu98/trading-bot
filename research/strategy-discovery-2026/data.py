"""Allowlisted public archives; timestamp integrity; no trading endpoints."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,calendar,csv,hashlib,io,json,threading,time,urllib.request,urllib.error,zipfile
from concurrent.futures import ThreadPoolExecutor
from engine import Bar
ROOT=Path(__file__).resolve().parent;LOCK=threading.Lock();NEXT=0.;TOTAL=0
SYMBOLS=['BTCUSDT','ETHUSDT','XRPUSDT','BCHUSDT','LTCUSDT','EOSUSDT','BNBUSDT']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def parse_row(row,year,interval,symbol):
 scale=1000000 if year>=2025 else 1000;a=int(row[0]);z=int(row[6]);start=a//scale
 if a%scale or z!=(start+interval)*scale-1 or start%interval:raise ValueError('timestamp/unit/inclusive close mismatch')
 if datetime.fromtimestamp(start,timezone.utc).year!=year:raise ValueError('timestamp year mismatch')
 o,h,l,c,v=map(float,row[1:6]);quote=float(row[7])
 if not all(map(math_finite,(o,h,l,c,v,quote))) or min(o,h,l,c)<=0 or min(v,quote)<0 or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('invalid OHLCV')
 full=not(symbol=='BCHUSDT' and interval==86400 and start==1574899200)
 return Bar(start,start+interval,o,h,l,c,v,quote,full)
def math_finite(x):return x==x and abs(x)!=float('inf')
def months(lo,hi):
 y,m=map(int,lo.split('-'));result=[]
 while f'{y:04}-{m:02}'<hi:
  result.append(f'{y:04}-{m:02}');m+=1
  if m==13:y+=1;m=1
 return result

def plan(phase):
 end='2024-01' if phase=='development-validation' else '2024-12'
 lo='2019-09' if phase=='development-validation' else '2024-01';p=[]
 for symbol in SYMBOLS:
  for month in months(lo,end):
   if symbol=='BCHUSDT' and month<'2019-11':continue
   p.append((symbol,'1d',month))
 for symbol in SYMBOLS[:2]:
  for month in months('2019-12' if phase=='development-validation' else '2024-01',end):p.append((symbol,'1h',month))
 return p
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**kw):raise ValueError('redirect forbidden')
def fetch(url):
 global NEXT,TOTAL
 if not url.startswith('https://data.binance.vision/data/spot/monthly/klines/'):raise ValueError('public archive allowlist')
 for attempt in range(3):
  with LOCK:
   delay=max(0,NEXT-time.monotonic());NEXT=max(NEXT,time.monotonic())+.25
  time.sleep(delay)
  start=time.time_ns()
  try:
   with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(url,timeout=20) as r:
    body=r.read(2000001)
    if len(body)>2000000:raise ValueError('per object cap')
   with LOCK:
    TOTAL+=len(body)
    if TOTAL>64*1024*1024:raise ValueError('hard total compressed cap')
   return body,{'url':url,'start_ns':start,'received_ns':time.time_ns(),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
  except urllib.error.HTTPError as e:
   if e.code==404:return None,{'url':url,'status':404,'received_ns':time.time_ns()}
   if e.code not in (408,429,500,502,503,504) or attempt==2:raise
  except (TimeoutError,OSError):
   if attempt==2:raise
  time.sleep(2**attempt)
 raise RuntimeError('unreachable')
def acquire_one(item):
 symbol,interval,month=item;name=f'{symbol}-{interval}-{month}.zip';folder=ROOT/'data'/interval/symbol;folder.mkdir(parents=True,exist_ok=True);p=folder/name;c=folder/(name+'.CHECKSUM');url=f'https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{name}'
 if p.exists() and c.exists():
  fields=c.read_text().split();assert fields==[sha(p),name];return {'symbol':symbol,'interval':interval,'month':month,'path':str(p.relative_to(ROOT)),'sha256':sha(p),'checksum_path':str(c.relative_to(ROOT)),'checksum_sha256':sha(c),'cached':True}
 content,cr=fetch(url+'.CHECKSUM')
 if content is None:return {'symbol':symbol,'interval':interval,'month':month,'status':'MISSING_404','request':cr}
 fields=content.decode().split()
 if len(fields)!=2 or fields[1]!=name:raise ValueError('checksum filename')
 body,br=fetch(url)
 if body is None:raise ValueError('archive missing despite checksum')
 if hashlib.sha256(body).hexdigest()!=fields[0].lower():raise ValueError('archive checksum')
 c.write_bytes(content);p.write_bytes(body)
 return {'symbol':symbol,'interval':interval,'month':month,'path':str(p.relative_to(ROOT)),'sha256':sha(p),'checksum_path':str(c.relative_to(ROOT)),'checksum_sha256':sha(c),'requests':[cr,br],'cached':False}
def load_manifest(phase):
 manifests=[json.loads((ROOT/'acquisition-development-validation.json').read_text())]
 if phase=='holdout':
  if not (ROOT/'holdout-release.json').exists():raise ValueError('holdout locked')
  permission=json.loads((ROOT/'holdout-release.json').read_text())
  if permission.get('source_freeze_sha256')!=sha(ROOT/'source-freeze.json'):raise ValueError('holdout source release mismatch')
  manifests.append(json.loads((ROOT/'acquisition-holdout.json').read_text()))
 result={};decoded=0;quality=[];errors={}
 for manifest in manifests:
  for a in manifest['archives']:
   key=(a['interval'],a['symbol']);label='/'.join(key)
   try:
    if a.get('status'):raise ValueError('missing archive '+a['month'])
    p=ROOT/a['path'];c=ROOT/a['checksum_path'];assert sha(p)==a['sha256'] and sha(c)==a['checksum_sha256'];assert c.read_text().split()==[a['sha256'],p.name]
    with zipfile.ZipFile(p) as z:
     if z.namelist()!=[p.stem+'.csv']:raise ValueError('zip member')
     decoded+=z.infolist()[0].file_size
     if decoded>256*1024*1024:raise ValueError('decoded cap')
     contents=z.read(z.namelist()[0]);part=[parse_row(r,int(a['month'][:4]),86400 if a['interval']=='1d' else 3600,a['symbol']) for r in csv.reader(io.StringIO(contents.decode()))]
    year,month=map(int,a['month'].split('-'));expected=calendar.monthrange(year,month)[1]*(1 if a['interval']=='1d' else 24)
    partial=a['symbol']=='BCHUSDT' and a['month']=='2019-11' and a['interval']=='1d'
    first=int(datetime(year,month,28 if partial else 1,tzinfo=timezone.utc).timestamp());last=int(datetime(year+(month==12),1 if month==12 else month+1,1,tzinfo=timezone.utc).timestamp())
    if len(part)!=(3 if partial else expected) or part[0].start!=first or part[-1].end!=last:raise ValueError('monthly first/last/count mismatch '+a['month'])
    series=result.setdefault(key,[])
    for i,b in enumerate(part):
     previous=part[i-1] if i else series[-1] if series else None
     if previous is not None and b.start!=previous.end:raise ValueError('gap/duplicate '+str(key))
    series.extend(part)
    quality.append({'symbol':a['symbol'],'interval':a['interval'],'month':a['month'],'bars':len(part),'first_start':part[0].start,'last_end':part[-1].end,'csv_sha256':hashlib.sha256(contents).hexdigest()})
   except (ValueError,AssertionError,OSError,KeyError,zipfile.BadZipFile) as e:
    errors.setdefault(label,[]).append({'month':a['month'],'error':str(e)})
 return result,{'months':quality,'errors':errors}

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','acquire','quality','freeze-inputs']);p.add_argument('--phase',default='development-validation',choices=['development-validation','holdout']);args=p.parse_args()
 if args.phase=='holdout':
  if not (ROOT/'holdout-release.json').exists():raise ValueError('holdout locked')
  permission=json.loads((ROOT/'holdout-release.json').read_text())
  if permission.get('source_freeze_sha256')!=sha(ROOT/'source-freeze.json'):raise ValueError('holdout source release mismatch')
 if args.action=='plan':print(json.dumps({'pairs':len(plan(args.phase)),'requests_max':2*len(plan(args.phase)),'items':plan(args.phase)},indent=2));return
 if not (ROOT/'source-freeze.json').exists():raise ValueError('source freeze required')
 if args.action=='acquire':
  global TOTAL
  TOTAL=sum(p.stat().st_size for p in (ROOT/'data').rglob('*') if p.is_file()) if (ROOT/'data').exists() else 0
  for f,h in json.loads((ROOT/'source-freeze.json').read_text())['sources'].items():assert sha(ROOT/f)==h
  dest=ROOT/('acquisition-'+args.phase+'.json')
  if dest.exists():raise ValueError('manifest exists; no overwrite')
  with ThreadPoolExecutor(max_workers=4) as pool:archives=list(pool.map(acquire_one,plan(args.phase)))
  save(dest,{'phase':args.phase,'completed_ns':time.time_ns(),'archives':archives,'downloaded_bytes_this_process':TOTAL,'private_access':False,'financial_results_examined':False})
 else:
  _,quality=load_manifest(args.phase)
  if args.action=='quality':
   save(ROOT/('quality-'+args.phase+'.json'),{'quality':quality,'phase':args.phase,'returns_computed':False});print('QUALITY',len(quality['months']),'months;',len(quality['errors']),'affected series')
  else:
   names=['acquisition-development-validation.json']+(['acquisition-holdout.json','holdout-release.json'] if args.phase=='holdout' else [])
   inputs={name:sha(ROOT/name) for name in names}
   for name in names:
    if not name.startswith('acquisition-'):continue
    for a in json.loads((ROOT/name).read_text())['archives']:
     if a.get('status'):continue
     for key in ('path','checksum_path'):inputs[a[key]]=sha(ROOT/a[key])
   dest=ROOT/('data-freeze-'+args.phase+'.json')
   if dest.exists():raise ValueError('data freeze exists, never overwrite')
   save(dest,{'at_ns':time.time_ns(),'source_freeze_sha256':sha(ROOT/'source-freeze.json'),'inputs':inputs,'quality':quality,'prices_used_for_financial_results':False})
   print('INPUT_FREEZE',sha(dest))
if __name__=='__main__':main()
