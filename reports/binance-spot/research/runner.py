"""One locked BTC Spot hypothesis; offline use of existing Spot accounting/Risk.

No live journal access, adapter change, private route, strategy search or remote
order. Historical clock binding is process-local and restored after each call.
"""
from collections import Counter,defaultdict
from contextlib import contextmanager
from dataclasses import dataclass,replace,asdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal,ROUND_DOWN
from pathlib import Path
from types import SimpleNamespace
import argparse,asyncio,calendar,csv,hashlib,io,json,math,re,socket,time,zipfile
import aiohttp,numpy as np
import mnq_local.binance_spot as core
from mnq_local.binance_spot import SpotRuntime,SpotSpec,dec
from mnq_local.replay import AtomicJournal
from mnq_timestral.strategy import Risk
UTC=timezone.utc;H=3_600_000_000_000;ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
RAW=ROOT/'data/binance-spot/research';PH='8230d5ad3d7f0e11133c515020aca348b04656d452735dc530a55aca54304653'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).parent.mkdir(parents=True,exist_ok=True);Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def iso(ns):return (datetime(1970,1,1,tzinfo=UTC)+timedelta(microseconds=ns//1000)).isoformat()
def day(ns):return iso(ns)[:10]
def sma(x):return sum(x[-168:],Decimal(0))/168 if len(x)>=168 else None
def cross(x):return len(x)>=169 and x[-1]>sma(x) and x[-2]<=sma(x[:-1])

@dataclass(frozen=True)
class Bar:
    start:int;end:int;open:Decimal;high:Decimal;low:Decimal;close:Decimal;volume:Decimal;unit:str;original_open:int;original_close:int

def archive_ns(value,year):
    if type(value) is not int:raise ValueError('Integer timestamp required')
    ns=value*(1000 if year>=2025 else 1_000_000)
    at=datetime(1970,1,1,tzinfo=UTC)+timedelta(seconds=ns//1_000_000_000)
    if at.year!=year:raise ValueError('Timestamp unit/year mismatch; no guessing')
    return ns

def parse_row(row,month):
    y,m=map(int,month.split('-'));unit='us' if y>=2025 else 'ms';a,b=int(row[0]),int(row[6]);start=archive_ns(a,y);close=archive_ns(b,y)
    if start%H or close!=start+H-(1000 if y>=2025 else 1_000_000) or iso(start)[:7]!=month:raise ValueError('Hour/calendar/inclusive close mismatch')
    o,h,l,c,v=map(dec,row[1:6])
    if min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid OHLCV')
    return Bar(start,start+H,o,h,l,c,v,unit,a,b)

@dataclass(frozen=True)
class ResearchConfig:
    account:str='OFFLINE_BTC_RESEARCH';mode:str='technical_paper';strategy_id:str='btcusdt_technical_once';client_id:int=0
    max_contracts:int=1;stale_seconds:float=2.;daily_max_loss:float=10.;max_drawdown:float=20.;max_trades:int=10;max_consecutive_losses:int=3
    virtual_cash:str='1000';entry_cash_cap:str='100';fee_rate:str='0.001';slippage_rate:str='0.0001';stop_fraction:str='0.05';deadline_seconds:int=604800
    def risk(self):return Risk(self.daily_max_loss,self.max_drawdown,self.max_trades,self.max_consecutive_losses)

def quote(raw,ns):
    return {'symbol':'BTCUSDT','bid':str(raw*dec('.9999')),'ask':str(raw*dec('1.0001')),'bid_qty':'1000000000','ask_qty':'1000000000',
      'received_ns':ns,'received_mono_ns':ns,'received_at':iso(ns),'source_ns':ns,'raw_reference':str(raw),'spread_bps':'2',
      'origin':'HISTORICAL_TRADE_OHLC_ASSUMED_BBO_NOT_OBSERVED','size_assumption':'Unbounded synthetic displayed size for cash<=100; no historical queue/liquidity evidence'}

class HistoricalSpot(SpotRuntime):
    """Offline clock/scheduling/multi-cycle seam; no duplicate cash/fill engine."""
    def __init__(self,config,spec,journal):
        self.now=0;self.closed=[];self.cycle_base=dec(config.virtual_cash);self.rejections=Counter();self.halts=[];self.previous_halt=None
        super().__init__(config,spec,journal);self.connected=True;self.ready=True;self.trade_fresh=True;self.certificate={'passed':True,'scope':'OFFLINE_ASSUMED_EXECUTION_NOT_A_LIVE_FEED_CERTIFICATE'}
    @contextmanager
    def clocked(self):
        old_time,old_utc=core.time,core.utc
        core.time=SimpleNamespace(time_ns=lambda:self.now,monotonic_ns=lambda:self.now)
        core.utc=lambda ns=None:iso(self.now if ns is None else ns)
        try:yield
        finally:core.time,core.utc=old_time,old_utc
    def _roll_day(self,_now):
        d=day(self.now)
        if d!=self.state['date']:
            if self.state['halt'] in ('daily_max_loss','consecutive_losses') and not self.spot['position']:
                self.state['halt']=None;self.state['stopping']=False
            self.state.update(date=d,day_gross=0.,day_trades=0,consecutive=0)
    def net(self,day=False):
        return float(sum((dec(e['gross_exact'])-dec(e['fee_exact']) for e in self.state['executions'].values() if not day or e['date']==globals()['day'](self.now)),Decimal(0)))
    def quote_fresh(self,for_exit=False):return self.quote is not None and self.quote['received_ns']==self.now
    def set_quote(self,raw):self.quote=quote(dec(raw),self.now);self._roll_day(None)
    def enter(self):
        self.spot['budget_spent']=False;self.cycle_base=dec(self.spot['cash'])
        risk=self._mark_risk();allowed,reason=self.config.risk().allow(risk)
        if not allowed:self.rejections[reason]+=1;return False
        with self.clocked():ok=super().submit_technical()
        if ok:
            self.spot['position']['deadline_ns']=self.now+168*H;self.spot['position']['research_raw_entry']=self.quote['raw_reference']
            self.journal.save('offline_168h_deadline',{'deadline_ns':self.spot['position']['deadline_ns']})
        else:self.rejections['initial_cost_risk_or_size_admission']+=1
        return ok
    def exit_or_protect(self,ignore_time=False):
        p=self.spot['position']
        if not p:return False
        deadline=p['deadline_ns'];original=self.config
        # Existing one-shot protect reconciles cycle PnL against cash-origin.
        # Supply this cycle's original cash, then restore full portfolio origin.
        self.config=replace(original,virtual_cash=str(self.cycle_base))
        if ignore_time:p['deadline_ns']=2**63-1
        try:
            with self.clocked():closed=super().protect()
        finally:
            self.config=original
            if self.spot['position']:self.spot['position']['deadline_ns']=deadline
        if closed:
            t=self.spot['roundtrip'];t['deadline_ns']=deadline;t['exit_ns']=self.now;t['exit_raw_reference']=self.quote['raw_reference']
            t['gross_raw']=str(dec(t['quantity'])*(dec(t['exit_raw_reference'])-dec(t['research_raw_entry'])))
            qty=dec(t['quantity']);raw_in=dec(t['research_raw_entry']);raw_out=dec(t['exit_raw_reference'])
            t['spread_cost']=str(qty*(raw_in+raw_out)*dec('.0001'))
            t['slippage_cost']=str(qty*(raw_in*dec('1.0001')+raw_out*dec('.9999'))*dec('.0001'))
            t['execution']='OFFLINE_HISTORICAL_MODEL_NOT_LIVE_TECHNICAL_TRADE'
            self.spot['net']=str(dec(self.spot['cash'])-dec(original.virtual_cash));self.closed.append(json.loads(json.dumps(t)))
            assert abs(dec(t['gross_raw'])-dec(t['spread_cost'])-dec(t['slippage_cost'])-dec(t['gross']))<dec('1e-20')
            assert dec(self.spot['net'])==sum((dec(x['net']) for x in self.closed),Decimal(0))
        if self.state['halt'] and self.state['halt']!=self.previous_halt:self.halts.append({'at':iso(self.now),'reason':self.state['halt']})
        self.previous_halt=self.state['halt'];return closed

def simulate(r,bars,start,end):
    closes=[b.close for b in bars[:start]];pending_buy=False;equity=[];signals=[]
    for i in range(start,end):
        b=bars[i];r.now=b.start;r.set_quote(b.open)
        if r.spot['position']:
            if dec(r.quote['bid'])<=dec(r.spot['position']['stop']):r.spot['pending_exit']='adverse_stop_gap'
            r.exit_or_protect()
        if pending_buy and not r.spot['position']:r.enter()
        pending_buy=False
        if r.spot['position'] and b.low*dec('.9999')<=dec(r.spot['position']['stop']):
            # Stop is a modeled bid threshold. Hourly OHLC cannot timestamp it.
            stop=dec(r.spot['position']['stop']);r.now=b.end;r.set_quote(stop/dec('.9999'));r.quote['bid']=str(stop)
            r.request_exit('intrabar_stop');r.exit_or_protect(ignore_time=True)
            r.closed[-1]['exit_timestamp_is_hour_bound']=True
        r.now=b.end;r.set_quote(b.close)
        if i==end-1 and r.spot['position']:r.request_exit('split_terminal_close')
        r.exit_or_protect(ignore_time=True)
        closes.append(b.close);long_cross=cross(closes);ma=sma(closes)
        if i<end-1:
            if r.spot['position'] and ma is not None and b.close<ma:r.request_exit('sma_exit')
            elif not r.spot['position'] and long_cross:pending_buy=True;signals.append({'at':iso(b.end),'side':'LONG_NEXT_OPEN'})
        risk=r._mark_risk();equity.append({'at':iso(b.end),'net':r.net()+risk.unrealized,'drawdown':risk.drawdown,'cash':r.spot['cash']})
    return {'trades':r.closed,'equity':equity,'signals':signals,'rejections':dict(r.rejections),'risk_halts':r.halts,'final_cash':r.spot['cash'],'global_halt':r.state['halt']=='max_drawdown'}

MONTHS=['2024-12']+['2025-'+str(m).zfill(2) for m in range(1,13)]
DOCS={'README.md':'https://raw.githubusercontent.com/binance/binance-public-data/master/README.md',
      'TERMS_AND_CONDITIONS.md':'https://raw.githubusercontent.com/binance/binance-public-data/master/TERMS_AND_CONDITIONS.md'}
async def acquire():
    RAW.mkdir(parents=True,exist_ok=True);proof=[];last=0.
    async with aiohttp.ClientSession(trust_env=False,cookie_jar=aiohttp.DummyCookieJar()) as session:
        async def get(url,path,cap):
            nonlocal last
            if path.exists():return
            if not (url in DOCS.values() or re.fullmatch(r'https://data\.binance\.vision/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-(2024-12|2025-(0[1-9]|1[0-2]))\.zip(\.CHECKSUM)?',url)):raise ValueError('Historical public GET allowlist')
            for attempt in range(3):
                await asyncio.sleep(max(0,1-(time.monotonic()-last)));last=time.monotonic();started=time.time_ns()
                try:
                    async with session.get(url,allow_redirects=False,timeout=aiohttp.ClientTimeout(total=20)) as response:
                        if response.status!=200:raise ConnectionError('Archive HTTP '+str(response.status))
                        chunks=[];size=0
                        async for part in response.content.iter_chunked(65536):
                            size+=len(part)
                            if size>cap:raise ValueError('Response byte cap')
                            chunks.append(part)
                    temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(b''.join(chunks));temp.replace(path)
                    proof.append({'url':url,'method':'GET','status':200,'request_start_ns':started,'received_ns':time.time_ns(),'bytes':size,'sha256':sha(path)});return
                except (aiohttp.ClientError,ConnectionError,asyncio.TimeoutError):
                    if attempt==2:raise
                    await asyncio.sleep(2**attempt)
        for name,url in DOCS.items():await get(url,RAW/name,2_000_000)
        archives=[]
        for month in MONTHS:
            name=f'BTCUSDT-1h-{month}.zip';url='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/'+name
            checksum=RAW/(name+'.CHECKSUM');archive=RAW/name
            await get(url+'.CHECKSUM',checksum,4096);await get(url,archive,10_000_000)
            fields=checksum.read_text().split()
            if len(fields)!=2 or not re.fullmatch('[0-9a-fA-F]{64}',fields[0]) or Path(fields[1]).name!=name or sha(archive)!=fields[0].lower():raise ValueError('Original archive CHECKSUM mismatch')
            archives.append({'month':month,'url':url,'path':str(archive.relative_to(ROOT)),'bytes':archive.stat().st_size,'sha256':sha(archive),'checksum_path':str(checksum.relative_to(ROOT)),'checksum_sha256':sha(checksum),'unit':'us' if month.startswith('2025') else 'ms','unpacked_before_code_freeze':False})
    save(OUT/'acquisition.json',{'completed_at':iso(time.time_ns()),'archives':archives,'requests':proof,'cost':0,'license':'CC BY-NC-SA4.0 personal non-production research; codeMIT is not dataMIT',
      'attribution':'Binance Vision Spot BTCUSDT native1h historical klines','documents':{name:{'url':url,'path':str((RAW/name).relative_to(ROOT)),'sha256':sha(RAW/name)} for name,url in DOCS.items()},'credentials':False})


def load_archives():
    provenance=json.loads((OUT/'acquisition.json').read_text());bars=[];quality=[];normalized=hashlib.sha256()
    for item in provenance['archives']:
        path=ROOT/item['path']
        if sha(path)!=item['sha256']:raise ValueError('Archive changed')
        with zipfile.ZipFile(path) as z:
            infos=z.infolist();expected=path.stem+'.csv'
            if len(infos)!=1 or infos[0].filename!=expected or infos[0].file_size>10_000_000 or infos[0].is_dir():raise ValueError('Unsafe/unbounded archive member')
            content=z.read(infos[0])
        part=[parse_row(row,item['month']) for row in csv.reader(io.StringIO(content.decode('utf-8')))]
        y,m=map(int,item['month'].split('-'));expected_count=calendar.monthrange(y,m)[1]*24
        if len(part)!=expected_count:raise ValueError('Incomplete monthly calendar')
        for b in part:
            if bars and b.start!=bars[-1].end:raise ValueError('Gap/reorder/duplicate')
            bars.append(b);normalized.update((json.dumps({**asdict(b),'open':str(b.open),'high':str(b.high),'low':str(b.low),'close':str(b.close),'volume':str(b.volume)},sort_keys=True)+'\n').encode())
        quality.append({'month':item['month'],'bars':len(part),'expected':expected_count,'unit':item['unit'],'csv_sha256':hashlib.sha256(content).hexdigest(),'csv_bytes':len(content),'first':iso(part[0].start),'last_end':iso(part[-1].end)})
    if len(bars)!=9504:raise ValueError('Expected744warmup+8760year2025hours')
    proof={'status':'PASS','bars':len(bars),'warmup':744,'year2025':8760,'gaps':0,'duplicates':0,'unit_loss':False,'dataset_sha256':normalized.hexdigest(),'months':quality,'archive_provenance_sha256':sha(OUT/'acquisition.json')}
    save(OUT/'data-quality.json',proof);return bars,proof


def bootstrap(values):
    x=np.asarray(values,dtype=float);n=len(x);result={}
    for k in (1,5,10):
        rng=np.random.default_rng(1729);starts=rng.integers(0,n,(10000,math.ceil(n/k)));ix=((starts[:,:,None]+np.arange(k))%n).reshape(10000,-1)[:,:n]
        means=x[ix].mean(axis=1);result[str(k)]={'mean_daily_net':float(x.mean()),'ci95':np.quantile(means,[.025,.975]).tolist(),'one_sided95_lower':float(np.quantile(means,.05))}
    return {'replicates':10000,'seed':1729,'family':1,'blocks':result,'limitation':'Conditional daily marked-equity block resampling; not re-simulated path-dependent Risk or independent future proof'}


def summarize(result):
    trades=result['trades'];nets=[dec(t['net']) for t in trades];gains=sum((n for n in nets if n>0),Decimal(0));losses=-sum((n for n in nets if n<0),Decimal(0))
    daily={};previous=0.
    # Equity at hour end is assigned to the closed hour's UTC calendar date.
    closes={}
    for e in result['equity']:
        ns=int(datetime.fromisoformat(e['at']).timestamp())*1_000_000_000;closes[day(ns-1)]=e['net']
    for d,value in closes.items():daily[d]=value-previous;previous=value
    m={'trades':len(trades),'gross_raw':str(sum((dec(t['gross_raw']) for t in trades),Decimal(0))),
      'gross_after_modeled_execution':str(sum((dec(t['gross']) for t in trades),Decimal(0))),
      'spread_cost':str(sum((dec(t['spread_cost']) for t in trades),Decimal(0))),'slippage_cost':str(sum((dec(t['slippage_cost']) for t in trades),Decimal(0))),
      'fees':str(sum((dec(t['fees']) for t in trades),Decimal(0))),'net':str(sum(nets,Decimal(0))),'final_cash':result['final_cash'],
      'profit_factor':float(gains/losses) if losses else None,'expectancy':float(sum(nets)/len(nets)) if nets else None,
      'max_drawdown_hour_close_including_liquidation_costs':max((e['drawdown'] for e in result['equity']),default=0),
      'risk_halts':result['risk_halts'],'rejections':result['rejections'],'global_halt':result['global_halt'],'daily_marked_net':daily,
      'exit_reasons':dict(Counter(t['exit_reason'] for t in trades)),'intrabar_stop_hour_bound_exits':sum(t.get('exit_timestamp_is_hour_bound',False) for t in trades),
      'uncertainty':bootstrap(list(daily.values()))}
    assert abs(sum(daily.values())-float(dec(m['net'])))<1e-9
    assert dec(result['final_cash'])-1000==dec(m['net'])
    return m


def rows(path,items):
    with Path(path).open('w',newline='') as f:
        if items:
            keys=list(dict.fromkeys(k for x in items for k in x));w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
            w.writerows([{k:json.dumps(v,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in x.items()} for x in items])


def frozen_sources():
    names=[str(Path(__file__).relative_to(ROOT)),str((OUT/'test_research.py').relative_to(ROOT)),'src/mnq_local/binance_spot.py','src/mnq_paper/core.py','src/mnq_local/replay.py','src/mnq_timestral/strategy.py']
    return {p:sha(ROOT/p) for p in names}


def freeze():
    if sha(OUT/'protocol.json')!=PH:raise ValueError('Parent protocol changed')
    if (OUT/'execution-freeze.json').exists():raise ValueError('Already frozen')
    save(OUT/'execution-freeze.json',{'frozen_at':iso(time.time_ns()),'protocol_sha256':PH,'sources':frozen_sources(),'config':asdict(ResearchConfig()),
      'fixed_technical_interpretations':{'risk_count_defaults':'Original Risk defaults10trades/day,3consecutive losses; dailyhaltresetsUTCwhenflat; globaldrawdownhaltpersists withinsplit',
       'stop':'Stop is modeled bid threshold, frozen5%below actual modeled entryfill tickdown. Adverse bid gap open first; intrabar modeled bid low touch fills stop*(1-slip), hourbound timestamp. NoTP collision.',
       'daily_bootstrap':'UTC daily changes of hour-close marked equity incl liquidation reserve; realized filldate ledger retained separately; terminalclose uses lastsegmentbarclose only',
       'one_shot_override':'Researchonlyreset entrybudget per newcausal candidate; historicalclock context binds only isolatedprocessmodule; cyclecashorigin supplied toexistingone-shotPNLassert thenrestorecumulative1000origin. No livefile/journal edits.',
       'unobserved_size':'Synthetic size unbounded for<=100USDT historicalfillmodel; no measured2025BBO/queue/liquidity claim','split':'No pending signal carried from warmup/previoussplit, pricesonlywarmup; terminalpendingentrycanceled, no nextsplitprice used'},
      'data_not_opened':True,'unit_policy':'2024ms,2025us explicitly; originalintsretained;exactns','parameter_search':False})
    print('RESEARCH_CODE_FROZEN',sha(OUT/'execution-freeze.json'),flush=True)


def validate():
    f=json.loads((OUT/'execution-freeze.json').read_text())
    if sha(OUT/'protocol.json')!=PH or f['sources']!=frozen_sources() or f['config']!=asdict(ResearchConfig()):raise ValueError('Immutable research source/config changed')


def run(tag):
    validate();bars,quality=load_archives();folder=OUT/tag;folder.mkdir(exist_ok=True);all_results={}
    spans={'development':('2025-01','2025-07'),'validation':('2025-07','2025-10'),'test':('2025-10','2026-01')}
    for name,(lo,hi) in spans.items():
        start=next(i for i,b in enumerate(bars) if iso(b.start)[:7]>=lo);end=next((i for i,b in enumerate(bars) if iso(b.start)[:7]>=hi),len(bars))
        path=RAW/tag/name;path.mkdir(parents=True,exist_ok=True)
        if (path/'state.sqlite').exists():raise ValueError('Never reuse economic journal; repeat with separatetag, same frozen sources/config')
        cfg=ResearchConfig();spec=SpotSpec('BTCUSDT','.01','.00001','.00001','9000','5');j=AtomicJournal(path/'state.sqlite',cfg,[spec],lock_root=path/'locks');r=HistoricalSpot(cfg,spec,j)
        try:
            result=simulate(r,bars,start,end);metrics=summarize(result);all_results[name]=metrics
            dest=folder/name;dest.mkdir(exist_ok=True);save(dest/'metrics.json',metrics);rows(dest/'trades.csv',result['trades']);rows(dest/'equity.csv',result['equity']);rows(dest/'daily.csv',[{'date':d,'net':n} for d,n in metrics['daily_marked_net'].items()]);rows(dest/'executions.csv',list(r.state['executions'].values()));save(dest/'state.json',r.state)
        finally:j.close()
        print(name,'trades',metrics['trades'],'net',metrics['net'],'PF',metrics['profit_factor'],'halts',metrics['risk_halts'],flush=True)
    t=all_results['test'];passed=dec(t['net'])>0 and t['trades']>=20 and t['profit_factor'] is not None and t['profit_factor']>=1.15 and not t['risk_halts'] and t['max_drawdown_hour_close_including_liquidation_costs']<=20 and t['uncertainty']['blocks']['5']['one_sided95_lower']>0
    verdict='REJECT_EXACT_CONFIGURATION' if dec(t['net'])<0 else 'EXPLORATORY_CANDIDATE_NEEDS_FUTURE_FORWARD_VALIDATION' if passed else 'INCONCLUSIVE_NOT_PROMOTED'
    output={'verdict':verdict,'protocol_sha256':PH,'execution_freeze_sha256':sha(OUT/'execution-freeze.json'),'dataset_sha256':quality['dataset_sha256'],'bars':len(bars),'results':all_results,'financially_approved':False,'technical_live_trade_included':False,'parameter_search':False,'historical_book_costs_measured':False}
    save(folder/'results.json',output);print('RESULTS_SHA',sha(folder/'results.json'),'VERDICT',verdict,flush=True);validate()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','acquire','run']);p.add_argument('--tag',default='run-1');a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='acquire':validate();asyncio.run(acquire())
    else:
        def denied(*_a,**_kw):raise RuntimeError('Offline economic replay: network disabled')
        socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied;run(a.tag)
if __name__=='__main__':main()
