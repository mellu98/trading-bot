"""Cached original archives only; no network client or downloads."""
from pathlib import Path
from datetime import datetime,timezone
import calendar,csv,hashlib,io,json,math,zipfile
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent;OLD=ROOT/'research/strategy-discovery-2026';SYMBOLS=['BTCUSDT','ETHUSDT','XRPUSDT','BCHUSDT','LTCUSDT','EOSUSDT','BNBUSDT'];DAY=86400

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def timestamp(x):return int(datetime.fromisoformat(x).replace(tzinfo=timezone.utc).timestamp())
def iso(t):return datetime.fromtimestamp(int(t),timezone.utc).isoformat()

def parse_row(row,year,step,symbol):
 if len(row)!=12:raise ValueError('12 original fields required')
 mul=1000000 if year>=2025 else 1000;start=int(row[0])//mul;end=start+step
 if int(row[0])!=start*mul or start%step or int(row[6])!=end*mul-1 or datetime.fromtimestamp(start,timezone.utc).year!=year:raise ValueError('timestamp/calendar/unit/closure')
 o,h,l,c,v=map(float,row[1:6]);q=float(row[7]);trades=int(row[8]);tb=float(row[9]);tq=float(row[10])
 if not all(map(math.isfinite,[o,h,l,c,v,q,tb,tq])) or min(o,h,l,c)<=0 or min(v,q,tb,tq)<0 or trades<0 or tb>v+1e-8 or tq>q+1e-8 or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('OHLC/activity field quality')
 return {'start':start,'end':end,'open':o,'close':c,'quote':q,'base_volume':v,'number_trades':trades,'taker_buy_base':tb,'taker_buy_quote':tq,'full':not(symbol=='BCHUSDT' and step==DAY and start==timestamp('2019-11-28'))}

def selected_archives():
 result=[]
 for name in ['acquisition-development-validation.json','acquisition-holdout.json']:
  for a in load(OLD/name)['archives']:
   if a['interval']=='1d' or a['interval']=='1h' and a['symbol'] in SYMBOLS[:2] and (a['month'].startswith('2022-') or '2024-01'<=a['month']<'2024-12'):result.append(a)
 return result

def read_cache():
 result={};quality=[]
 for a in selected_archives():
  p=OLD/a['path'];c=OLD/a['checksum_path'];assert sha(p)==a['sha256'] and sha(c)==a['checksum_sha256'];assert c.read_text().split()==[a['sha256'],p.name]
  with zipfile.ZipFile(p) as z:
   if z.namelist()!=[p.stem+'.csv']:raise ValueError('ZIP member')
   content=z.read(z.namelist()[0]);part=[parse_row(r,int(a['month'][:4]),DAY if a['interval']=='1d' else 3600,a['symbol']) for r in csv.reader(io.StringIO(content.decode()))]
  y,m=map(int,a['month'].split('-'));partial=a['symbol']=='BCHUSDT' and a['interval']=='1d' and a['month']=='2019-11';first=timestamp(f'{y:04}-{m:02}-{28 if partial else 1:02}');last=timestamp(f'{y+1 if m==12 else y:04}-{1 if m==12 else m+1:02}-01');expected=3 if partial else calendar.monthrange(y,m)[1]*(1 if a['interval']=='1d' else 24)
  if len(part)!=expected or part[0]['start']!=first or part[-1]['end']!=last:raise ValueError('monthly exact bounds/count')
  key=(a['interval'],a['symbol']);series=result.setdefault(key,{})
  for b in part:
   if b['start'] in series:raise ValueError('duplicate timestamp')
   series[b['start']]=b
  quality.append({'symbol':a['symbol'],'interval':a['interval'],'month':a['month'],'bars':len(part),'csv_sha256':hashlib.sha256(content).hexdigest()})
 return result,quality

def validate_hour_window(rows,start,end):
 return [t for t in range(start,end,3600) if t not in rows or rows[t]['end']!=t+3600]

def daily_grid(cache,symbols):
 start=min(min(cache[('1d',s)]) for s in symbols);end=max(max(cache[('1d',s)])+DAY for s in symbols);times=np.arange(start,end,DAY,dtype=np.int64);close=np.full((len(times),len(symbols)),np.nan);quote=close.copy();full=np.zeros_like(close,bool)
 for k,s in enumerate(symbols):
  for t,b in cache[('1d',s)].items():j=(t-start)//DAY;close[j,k]=b['close'];quote[j,k]=b['quote'];full[j,k]=b['full']
 return {'times':times,'close':close,'quote':quote,'full':full,'symbols':symbols}
