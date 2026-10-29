"""One preregistered 4h channel experiment; reuse Spot cash/fills and original Risk.

Offline research only. No active observer files, journal, settings or orders.
"""
from dataclasses import replace,asdict
from decimal import Decimal,ROUND_DOWN
from pathlib import Path
import argparse,asyncio,calendar,csv,hashlib,importlib.util,io,json,math,re,socket,sys,time,zipfile
import aiohttp
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;RAW=ROOT/'data/binance-spot/breakout-4h'
PH='70bea1510b04f67cfb65db7881ed6319534fbf009b71b514afd07d49918fd3c4'
# Reuse the already-tested offline historical clock / multi-cycle seam, not a new fill engine.
oldpath=ROOT/'reports/binance-spot/research/runner.py';loader=importlib.util.spec_from_file_location('frozen_sma_reuse',oldpath)
old=importlib.util.module_from_spec(loader);sys.modules[loader.name]=old;loader.loader.exec_module(old)
from mnq_local.binance_spot import SpotRuntime,SpotSpec,dec
from mnq_local.replay import AtomicJournal
Bar,H,archive_ns,parse_row,iso,day,sha,save,rows,bootstrap,summarize=(getattr(old,k) for k in ('Bar','H','archive_ns','parse_row','iso','day','sha','save','rows','bootstrap','summarize'))
COSTS={'base':('.001','.0001','.0002'),'adverse':('.0015','.0005','.001'),'severe':('.002','.001','.002')}


def aggregate4(bars):
    result=[];bucket=[];previous=None
    for b in bars:
        if previous is not None and b.start!=previous:raise ValueError('Noncontiguous native hours')
        previous=b.end
        if bucket and b.start!=bucket[-1].end:raise ValueError('Noncontiguous native hours')
        if not bucket and b.start%(4*H):raise ValueError('4h UTC anchor required')
        bucket.append(b)
        if len(bucket)==4:
            result.append(Bar(bucket[0].start,b.end,bucket[0].open,max(x.high for x in bucket),min(x.low for x in bucket),b.close,sum(x.volume for x in bucket),'4h_from_native1h',bucket[0].original_open,b.original_close));bucket=[]
    return result


def atr14(history):
    if len(history)<15:return None
    return sum((max(b.high-b.low,abs(b.high-p.close),abs(b.low-p.close)) for p,b in zip(history[-15:-1],history[-14:])),Decimal(0))/14


def decision(history):
    if len(history)<21:return False,False,None
    b=history[-1]
    return b.close>max(x.high for x in history[-21:-1]),b.close<min(x.low for x in history[-11:-1]),atr14(history)


def quote(raw,ns,spread):
    q=old.quote(raw,ns);half=dec(spread)/2
    q.update(bid=str(raw*(1-half)),ask=str(raw*(1+half)),spread_bps=str(dec(spread)*10000))
    return q


class ChannelSpot(old.HistoricalSpot):
    def __init__(self,config,spec,journal,scenario='base',benchmark=False):
        self.scenario=scenario;self.half=dec(COSTS[scenario][2])/2;self.benchmark=benchmark
        super().__init__(config,spec,journal)
    def set_quote(self,raw):self.quote=quote(dec(raw),self.now,COSTS[self.scenario][2]);self._roll_day(None)
    def enter(self,atr):
        self.spot['budget_spent']=False;self.cycle_base=dec(self.spot['cash']);original=self.config
        risk=self._mark_risk();allowed,reason=self.config.risk().allow(risk)
        if not allowed:self.rejections[reason]+=1;return False
        price=dec(self.quote['ask'])*(1+dec(original.slippage_rate));fee=dec(original.fee_rate);slip=dec(original.slippage_rate)
        stop=((price-2*atr)/self.spec.tick).to_integral_value(rounding=ROUND_DOWN)*self.spec.tick if not self.benchmark else Decimal(0)
        if stop<0 or (not self.benchmark and stop==0):self.rejections['nonpositive_stop']+=1;return False
        unit_cost=price*(1+fee);stop_net=stop*(1-slip)*(1-fee);unit_risk=unit_cost-stop_net
        cap=min(dec(original.entry_cash_cap),dec(self.spot['cash']))
        qty_cap=cap/unit_cost
        if not self.benchmark:qty_cap=min(qty_cap,Decimal(1)/unit_risk)
        qty=(qty_cap/self.spec.step).to_integral_value(rounding=ROUND_DOWN)*self.spec.step
        if qty<self.spec.min_qty or qty*price<self.spec.min_notional:self.rejections['cash_risk_grid_min_notional']+=1;return False
        # Place original fixed-fraction helper safely inside the exact desired tick cell.
        fraction=(price-(stop+self.spec.tick/2))/price if not self.benchmark else Decimal(1)
        budget=min(cap,(qty+self.spec.step/2)*unit_cost)
        self.config=replace(original,stop_fraction=str(fraction),entry_cash_cap=str(budget))
        try:
            with self.clocked():ok=SpotRuntime.submit_technical(self)
        finally:self.config=original
        if not ok:self.rejections['original_risk_initial_admission']+=1;return False
        p=self.spot['position'];assert dec(p['quantity'])==qty and dec(p['stop'])==stop
        assert self.benchmark or dec(p['initial_modeled_risk_usdt'])<=1
        p.update(deadline_ns=2**63-1,research_raw_entry=self.quote['raw_reference'],signal_atr14=str(atr),research_scenario=self.scenario)
        self.journal.save('offline_channel_atr_stop',{'stop':str(stop),'signal_atr14':str(atr),'initial_modeled_risk':p['initial_modeled_risk_usdt']})
        return True
    def exit_or_protect(self):
        if not self.spot['position']:return False
        original=self.config;self.config=replace(original,virtual_cash=str(self.cycle_base))
        try:
            with self.clocked():closed=SpotRuntime.protect(self)
        finally:self.config=original
        if closed:
            t=self.spot['roundtrip'];t.update(exit_ns=self.now,exit_raw_reference=self.quote['raw_reference'],execution='OFFLINE_CHANNEL_RESEARCH_NOT_LIVE_TECHNICAL_TRADE')
            qty=dec(t['quantity']);a=dec(t['research_raw_entry']);b=dec(t['exit_raw_reference']);slip=dec(original.slippage_rate)
            t.update(gross_raw=str(qty*(b-a)),spread_cost=str(qty*(a+b)*self.half),slippage_cost=str(qty*(a*(1+self.half)+b*(1-self.half))*slip))
            self.spot['net']=str(dec(self.spot['cash'])-dec(original.virtual_cash));self.closed.append(json.loads(json.dumps(t)))
            assert abs(dec(t['gross_raw'])-dec(t['spread_cost'])-dec(t['slippage_cost'])-dec(t['gross']))<dec('1e-20')
            assert dec(self.spot['net'])==sum((dec(t['net']) for t in self.closed),Decimal(0))
        if self.state['halt'] and self.state['halt']!=self.previous_halt:self.halts.append({'at':iso(self.now),'reason':self.state['halt']})
        self.previous_halt=self.state['halt'];return closed


def engine(path,scenario='base',benchmark=False):
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    if (path/'state.sqlite').exists():raise ValueError('Never overwrite a research run journal')
    fee,slip,_=COSTS[scenario];cfg=replace(old.ResearchConfig(),account='OFFLINE_BTC_CHANNEL_RESEARCH',fee_rate=fee,slippage_rate=slip)
    if benchmark:cfg=replace(cfg,daily_max_loss=1e12,max_drawdown=1e12)
    spec=SpotSpec('BTCUSDT','.01','.00001','.00001','9000','5');j=AtomicJournal(path/'state.sqlite',cfg,[spec],lock_root=path/'locks')
    return ChannelSpot(cfg,spec,j,scenario,benchmark),j


def simulate(r,bars,start,end):
    four=aggregate4(bars);completed={b.end:b for b in four};history=[b for b in four if b.end<=bars[start].start]
    pending_atr=None;pending_sell=False;equity=[];signals=[];exposure=0
    for i in range(start,end):
        b=bars[i];r.now=b.start;r.set_quote(b.open)
        if r.spot['position']:
            if dec(r.quote['bid'])<=dec(r.spot['position']['stop']):r.spot['pending_exit']='adverse_stop_gap'
            elif pending_sell:r.request_exit('channel_exit')
            r.exit_or_protect()
        if pending_atr is not None and not r.spot['position'] and i<end-1:r.enter(pending_atr)
        if r.benchmark and i==start:r.enter(Decimal(0))
        pending_atr=None;pending_sell=False;exposure+=int(r.spot['position'] is not None)
        if r.spot['position'] and not r.benchmark and b.low*(1-r.half)<=dec(r.spot['position']['stop']):
            stop=dec(r.spot['position']['stop']);r.now=b.end;r.set_quote(stop/(1-r.half));r.quote['bid']=str(stop)
            r.request_exit('intrabar_stop');r.exit_or_protect();r.closed[-1]['exit_timestamp_is_hour_bound']=True
        r.now=b.end;r.set_quote(b.close)
        if i==end-1 and r.spot['position']:r.request_exit('split_terminal_close')
        r.exit_or_protect()
        if b.end in completed:
            history.append(completed[b.end]);buy,sell,atr=decision(history)
            if i<end-1 and not r.benchmark:
                if r.spot['position'] and sell:pending_sell=True
                elif not r.spot['position'] and buy:
                    pending_atr=atr;signals.append({'at':b.end,'side':'LONG_NEXT_NATIVE_HOUR_OPEN','atr14':str(atr)})
        risk=r._mark_risk();equity.append({'at':iso(b.end),'net':r.net()+risk.unrealized,'drawdown':risk.drawdown,'cash':r.spot['cash']})
    return {'trades':r.closed,'equity':equity,'signals':signals,'rejections':dict(r.rejections),'risk_halts':r.halts,'final_cash':r.spot['cash'],'global_halt':r.state['halt']=='max_drawdown','exposure_hours_upper_bound':exposure}


def frozen_sources():
    names=[str((OUT/'runner.py').relative_to(ROOT)),str((OUT/'test_breakout.py').relative_to(ROOT)),str(oldpath.relative_to(ROOT)),
           'src/mnq_local/binance_spot.py','src/mnq_local/replay.py','src/mnq_paper/core.py','src/mnq_timestral/strategy.py']
    return {p:sha(ROOT/p) for p in names}


def freeze():
    if sha(OUT/'protocol.json')!=PH:raise ValueError('Parent protocol changed')
    if (OUT/'execution-freeze.json').exists():raise ValueError('Already frozen')
    save(OUT/'execution-freeze.json',{'at_ns':time.time_ns(),'protocol_sha256':PH,'sources':frozen_sources(),'costs':COSTS,
      'fixed_interpretations':{'source_units':'2024ms;2025and2026us;originalintegersretained',
      'precision_bridge':'Use original Spot fixed-fraction helper with fraction mapping into desired stop tick cell; resulting stop asserted exactly floor(entryaskfill-2ATR14), qty asserted exact risk/cash grid floor. No copied accounting engine.',
      'initial_risk':'One USDT all-in entrycash minus stopbid netexit; quantitylargestgrid satisfyingcash100and1risk, original Risk admission also unchanged.',
      'terminal':'No entry at final nativehour; cancel pending terminal BUY; final held position liquidation at last nativehourclose only.',
      'risk_time':'Historical UTC clock/cumulative cash seam reused from frozen SMA research; original Risk unchanged. Dailyflat10USDT/3losses resets UTC; global20 drawdown remains split.',
      'benchmark':'100USDTentrycashinclfee,900idle, same model/grid; no1risk/daily10/DD20control, not deployable under active risk guard.',
      'intrabar':'Only native1hstopbidtouch, noTP; stop timestamp is hourbound, not observedsequence or tick time. Exposurehourcount upperbound.',
      'test':'JanSep2026 only project-unseen historical; no prospective independence. Missing/incomplete month => BLOCKED/INCONCLUSIVE without substitution.'},
      'new_test_data_not_acquired_or_opened':True,'parameter_search':False})
    print('CODE_FREEZE',sha(OUT/'execution-freeze.json'))


def validate():
    f=json.loads((OUT/'execution-freeze.json').read_text())
    if sha(OUT/'protocol.json')!=PH or f['sources']!=frozen_sources() or f['costs']!={k:list(v) for k,v in COSTS.items()}:raise ValueError('Immutable research code/protocol/config changed')


async def acquire():
    validate();RAW.mkdir(parents=True,exist_ok=True);requests=[];archives=[];last=0.
    # Reuse original verified2025/Dec24 cache, no duplicate requests/data purchase.
    previous=json.loads((old.OUT/'acquisition.json').read_text())
    archives.extend(previous['archives'])
    async with aiohttp.ClientSession(trust_env=False,cookie_jar=aiohttp.DummyCookieJar()) as session:
        for month in ['2026-'+str(m).zfill(2) for m in range(1,10)]:
            name='BTCUSDT-1h-'+month+'.zip';url='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1h/'+name
            for suffix,cap in [('.CHECKSUM',4096),('',10000000)]:
                target=RAW/(name+suffix)
                if target.exists():continue
                address=url+suffix
                if not re.fullmatch(r'https://data\.binance\.vision/data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2026-0[1-9]\.zip(\.CHECKSUM)?',address):raise ValueError('Public archive GET allowlist')
                for attempt in range(3):
                    await asyncio.sleep(max(0,1-(time.monotonic()-last)));last=time.monotonic();started=time.time_ns()
                    try:
                        async with session.get(address,allow_redirects=False,timeout=aiohttp.ClientTimeout(total=20)) as response:
                            if response.status!=200:raise ConnectionError('Archive HTTP '+str(response.status))
                            chunks=[];size=0
                            async for part in response.content.iter_chunked(65536):
                                size+=len(part)
                                if size>cap:raise ValueError('Archive byte cap')
                                chunks.append(part)
                        temp=target.with_suffix(target.suffix+'.tmp');temp.write_bytes(b''.join(chunks));temp.replace(target)
                        requests.append({'url':address,'method':'GET','status':200,'start_ns':started,'received_ns':time.time_ns(),'bytes':size,'sha256':sha(target)});break
                    except (ConnectionError,aiohttp.ClientError,asyncio.TimeoutError):
                        if attempt==2:
                            save(OUT/'acquisition-blocked.json',{'status':'BLOCKED_INCONCLUSIVE','month':month,'url':address,'requests':requests,'no_substitution':True});raise
                        await asyncio.sleep(2**attempt)
            archive=RAW/name;checksum=RAW/(name+'.CHECKSUM');fields=checksum.read_text().split()
            if len(fields)!=2 or fields[1]!=name or sha(archive)!=fields[0].lower():raise ValueError('Original CHECKSUM mismatch')
            archives.append({'month':month,'path':str(archive.relative_to(ROOT)),'sha256':sha(archive),'bytes':archive.stat().st_size,'unit':'us','checksum_path':str(checksum.relative_to(ROOT)),'checksum_sha256':sha(checksum),'url':url})
    save(OUT/'acquisition.json',{'completed_at_ns':time.time_ns(),'archives':archives,'requests':requests,'reused_2025_acquisition_sha256':sha(old.OUT/'acquisition.json'),
         'documents':previous['documents'],'license':'Binance Vision dataCCBY-NC-SA4.0; purely personal nonproduction research. CodeMIT is not dataMIT.','attribution':'Binance Spot public BTCUSDT native1h klines, Binance Vision','cost':0,'private_or_account_access':False})


def load():
    validate();manifest=json.loads((OUT/'acquisition.json').read_text());bars=[];quality=[];digest=hashlib.sha256()
    for item in manifest['archives']:
        p=ROOT/item['path'];checksum=ROOT/item['checksum_path'];fields=checksum.read_text().split()
        if sha(p)!=item['sha256'] or sha(checksum)!=item['checksum_sha256'] or fields!=[item['sha256'],p.name]:raise ValueError('Archive/checksum changed')
        with zipfile.ZipFile(p) as z:
            members=z.infolist()
            if len(members)!=1 or members[0].filename!=p.stem+'.csv' or members[0].file_size>10000000 or members[0].is_dir():raise ValueError('Unsafe ZIP member')
            content=z.read(members[0])
        part=[parse_row(row,item['month']) for row in csv.reader(io.StringIO(content.decode('utf-8')))];year,month=map(int,item['month'].split('-'))
        if len(part)!=calendar.monthrange(year,month)[1]*24:raise ValueError('Incomplete month, no period substitution')
        for b in part:
            if bars and b.start!=bars[-1].end:raise ValueError('Gap/duplicate/reordered hours')
            bars.append(b);digest.update((json.dumps({k:str(v) if isinstance(v,Decimal) else v for k,v in asdict(b).items()},sort_keys=True)+'\n').encode())
        quality.append({'month':item['month'],'hours':len(part),'unit':item['unit'],'csv_sha256':hashlib.sha256(content).hexdigest(),'csv_bytes':len(content),'first':iso(part[0].start),'last_end':iso(part[-1].end)})
    if len(bars)!=16056:raise ValueError('Expected744Dec24+8760year2025+6552JanSep2026')
    proof={'status':'PASS','hours':len(bars),'contiguous4h_bars':len(aggregate4(bars)),'reserved_test_hours':6552,'dataset_sha256':digest.hexdigest(),'gaps':0,'duplicates':0,'months':quality,'provenance_sha256':sha(OUT/'acquisition.json')}
    save(OUT/'data-quality.json',proof);return bars,proof


def additional_metrics(result,m):
    monthly={};quarters={};durations=[]
    for d,n in m['daily_marked_net'].items():
        monthly[d[:7]]=monthly.get(d[:7],0)+n;q=d[:4]+'-Q'+str((int(d[5:7])-1)//3+1);quarters[q]=quarters.get(q,0)+n
    for t in result['trades']:durations.append((t['exit_ns']-t['entry_ns'])/H)
    close_peak=0.;close_dd=0.
    for e in result['equity']:
        close_peak=max(close_peak,e['net']);close_dd=max(close_dd,close_peak-e['net'])
    m['original_risk_max_drawdown_at_hour_close']=m['max_drawdown_hour_close_including_liquidation_costs']
    m['max_drawdown_hour_close_including_liquidation_costs']=close_dd
    m.update(monthly_marked_net=monthly,quarterly_marked_net=quarters,monthly_closed_trades=dict(old.Counter(t['exit_at'][:7] for t in result['trades'])),
      exposure_hours_upper_bound=result['exposure_hours_upper_bound'],total_hours=len(result['equity']),holding_hours={'values':durations,'median':float(old.np.median(durations)) if durations else None,'max':max(durations,default=0)},
      win_rate=sum(dec(t['net'])>0 for t in result['trades'])/len(result['trades']) if result['trades'] else None,
      stop_ambiguity='Native1hOHLC cannot timestamp stop or order intrabar extremes. Stop-only noTP, adversegapfirst; no complete exitbar MFE/MAE claimed.')
    return m


def run(tag):
    validate();bars,quality=load();folder=OUT/tag;folder.mkdir(exist_ok=True);results={}
    for segment,lo,hi in [('observed_development','2025-01','2026-01'),('reserved_test','2026-01','2026-10')]:
        start=next(i for i,b in enumerate(bars) if iso(b.start)[:7]>=lo);end=next((i for i,b in enumerate(bars) if iso(b.start)[:7]>=hi),len(bars));results[segment]={}
        for scenario in COSTS:
            pairs={}
            for name,benchmark in [('strategy',False),('buy_hold_100',True)]:
                r,j=engine(RAW/tag/segment/scenario/name,scenario,benchmark)
                try:
                    result=simulate(r,bars,start,end);metrics=additional_metrics(result,summarize(result));pairs[name]=metrics
                    dest=folder/segment/scenario/name;dest.mkdir(parents=True,exist_ok=True)
                    save(dest/'metrics.json',metrics);rows(dest/'trades.csv',result['trades']);rows(dest/'equity.csv',result['equity']);rows(dest/'daily.csv',[{'date':d,'net':n} for d,n in metrics['daily_marked_net'].items()]);rows(dest/'signals.csv',result['signals']);rows(dest/'executions.csv',list(r.state['executions'].values()))
                finally:j.close()
            a,b=pairs['strategy'],pairs['buy_hold_100'];daily=[n-b['daily_marked_net'][d] for d,n in a['daily_marked_net'].items()]
            pairs['paired_daily_strategy_minus_buy_hold']=bootstrap(daily);pairs['cash']={'capital':'1000','net':'0','drawdown':0,'operations':0}
            results[segment][scenario]=pairs
            print(segment,scenario,'N',a['trades'],'net',a['net'],'PF',a['profit_factor'],'DD',a['max_drawdown_hour_close_including_liquidation_costs'],'BHnet',b['net'],flush=True)
    t=results['reserved_test']['base']['strategy'];adverse=results['reserved_test']['adverse']['strategy'];positive_quarters=sum(x>0 for x in t['quarterly_marked_net'].values())
    latched=any(h['reason']=='max_drawdown' for h in t['risk_halts'])
    reject=dec(t['net'])<=0 or dec(adverse['net'])<0 or latched
    candidate=not reject and t['trades']>=20 and (t['profit_factor'] or 0)>=1.15 and t['max_drawdown_hour_close_including_liquidation_costs']<=20 and positive_quarters>=2 and t['uncertainty']['blocks']['5']['one_sided95_lower']>0
    verdict='RESPINTA' if reject else 'CANDIDATA_A_FORWARD_TEST_SIGNALS_ONLY' if candidate else 'INCONCLUDENTE_NOT_PROMOTED'
    save(folder/'results.json',{'verdict':verdict,'protocol_sha256':PH,'execution_freeze_sha256':sha(OUT/'execution-freeze.json'),'dataset_sha256':quality['dataset_sha256'],'results':results,'positive_test_quarters':positive_quarters,'parameter_search':False,'technical_trade_included':False,'financially_approved':False,'live_observer_changed':False,'test_independence':'Project-unseen historical only, not prospective future validation'})
    print('VERDICT',verdict,'RESULTS_SHA',sha(folder/'results.json'),flush=True);validate()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','acquire','run']);p.add_argument('--tag',default='run-1');args=p.parse_args()
    if args.action=='freeze':freeze()
    elif args.action=='acquire':asyncio.run(acquire())
    else:
        def denied(*a,**kw):raise RuntimeError('Offline research replay: network forbidden')
        socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied;run(args.tag)
if __name__=='__main__':main()
