"""Prepared read-only prospective recorder. No account, Risk, paper position or order API."""
from pathlib import Path
from types import SimpleNamespace
from collections import deque,Counter
import argparse,asyncio,hashlib,json,os,signal,subprocess,sys,time
import aiohttp
import runner as experiment
from mnq_local.binance_spot import Feed,PublicREST,SpotRuntime,WS,utc
from mnq_local.binance_app import ObservationWorker,PipelineMetrics
OUT=Path(__file__).resolve().parent;H=experiment.H

class ClosedBuilder:
    def __init__(self):self.anchor=None;self.parts=[];self.last=None
    def add(self,k):
        if not k['x']:return None
        t=k['t']*1000000;anchor=t//(4*H)*(4*H)
        if t%60000000000 or k['T']!=k['t']+59999:raise ValueError('Native1m bounds required')
        if self.last is not None and t<=self.last:return None
        self.last=t
        if anchor!=self.anchor:self.anchor=anchor;self.parts=[]
        self.parts.append(k)
        if len(self.parts)!=240:return None
        if any(p['t']*1000000!=anchor+i*60000000000 for i,p in enumerate(self.parts)):return None
        parts=self.parts;self.parts=[]
        return {'start_ns':anchor,'end_ns':anchor+4*H,'open':parts[0]['o'],'high':str(max(experiment.dec(p['h']) for p in parts)),'low':str(min(experiment.dec(p['l']) for p in parts)),'close':parts[-1]['c'],'volume':str(sum(experiment.dec(p['v']) for p in parts)),'source':'ACTUAL_BINANCE_NATIVE_CLOSED_1M_AGGREGATED_CONTIGUOUS_UTC4H'}


def prospective_allowed(origin_seconds,now_seconds,healthy,n):return healthy and n==256 and 0<=now_seconds-origin_seconds<=300


def prepare():
    experiment.validate();p=OUT/'shadow-preparation.json'
    if p.exists():raise ValueError('Prospective preparation already frozen')
    experiment.save(p,{'at_ns':time.time_ns(),'mode':'PREPARED_SIGNALS_ONLY_NO_ORDERS','parent_protocol_sha256':experiment.PH,'parent_execution_freeze_sha256':experiment.sha(OUT/'execution-freeze.json'),'sources':{n:experiment.sha(OUT/n) for n in ['shadow.py','test_shadow.py']},
    'rules':{'native':'Only240contiguous x=true1m bars form4h;256contiguous4h bars required. Restart/gaps do not synthesize bars.', 'warmup':'No new historical acquisition. Existingcache endsSep2026 and cannot be spliced across currentgap. Collection fromnow mayneed~43dayswarmup before first256barforecast, thenatleast90prospectiveUTCdays plus30baseline/20eachfilteredclosedcounterfactualtrades.',
    'issuance':'Actualfreshpublicbarpublication only, forecastissuedwithin300sofclosedorigin. SequentialmodelsubprocessesCPU1 offeventloop, neverbothresident; no late/backfilled job labeledprospective.',
    'decisions':'Raw flatbreakoutcondition only, not portfolioacceptedentry; useoriginalfrozenlag4hstep2gate withactualwallavailability. Feedunhealthy => anomaly/suppresseddecision. Noaccount/order/position state exists; strictnewsblocked and nofinancialpromotion.',
    'evaluation':'Lateroffline originalRisk/Spot counterfactualreplay on this newlyrecordedcohort; futureminimum/Bonferroni gates in parent protocol. No maturefutureoutcome claim now.'}})
    print('SHADOW_PREPARATION',experiment.sha(p))


def check():
    experiment.validate();p=json.loads((OUT/'shadow-preparation.json').read_text())
    if p['parent_protocol_sha256']!=experiment.PH or p['sources']!={n:experiment.sha(OUT/n) for n in ['shadow.py','test_shadow.py']}:raise ValueError('Prepared shadow code changed')


def forecast_job(job,model):
    check();job=Path(job);context=json.loads((job/'context.json').read_text());destination=job/(model+'.json')
    if destination.exists():raise ValueError('Never overwrite prospective prediction')
    if not prospective_allowed(context['origin_ns']/1e9,time.time(),context['feed_healthy'],len(context['closes'])):return
    import numpy as np,torch
    from mnq_timestral.model import OfficialAdapter
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    before=time.time_ns();start=time.monotonic_ns();adapter=OfficialAdapter(model,experiment.ROOT/'data/models'/('Timestral-'+model),max_context=256)
    x=np.array(context['closes'],dtype='<f4')[None,None,:]
    q=adapter.forecaster.forecast(x,prediction_length=15,symmetric_averaging=True,clip_nonnegative=False,past_covariates=None,known_covariates=None).quantiles.detach().cpu().numpy()[0,0]
    available=time.time_ns();valid=experiment.valid_quantiles(q) and prospective_allowed(context['origin_ns']/1e9,available/1e9,True,256)
    value={'status':'ok' if valid else 'invalid_or_late','model':model,'model_revision':experiment.PINS[model].revision,'source_revision':experiment.SOURCE_REVISION,'origin_ns':context['origin_ns'],'input_end_ns':context['origin_ns'],'wall_infer_start_ns':before,'wall_available_ns':available,'latency_seconds':(time.monotonic_ns()-start)/1e9,'input_sha256':hashlib.sha256(x.tobytes()).hexdigest(),'quantiles':q.tolist() if experiment.valid_quantiles(q) else None,'prospective':valid,'availability_semantics':'ACTUAL_WALL_ISSUANCE_BEFORE_TARGET; NOT_HISTORICAL_BACKFILL','no_orders':True}
    with destination.open('x') as f:json.dump(value,f,sort_keys=True,allow_nan=False);f.write('\n')


async def record(folder,seconds):
    check();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);metrics=PipelineMetrics();worker=ObservationWorker(metrics);events=(folder/'events.jsonl').open('a',buffering=65536);counts=Counter();raw=[]
    def emit(kind,value):
        line=json.dumps({'kind':kind,'receipt_wall_ns':time.time_ns(),'value':value},sort_keys=True,allow_nan=False)+'\n'
        worker.submit('append_only_shadow',lambda:events.write(line))
    owner=SimpleNamespace(spot={'last_book_id':None,'last_trade_id':None,'closed_bar':None},quote=None,connected=False,ready=False,trade_fresh=False,certificate={'passed':False})
    owner.quote_fresh=lambda for_exit=False:SpotRuntime.quote_fresh(owner,for_exit)
    owner.request_exit=lambda reason:emit('provider_anomaly_no_position',{'reason':reason})
    owner.journal=SimpleNamespace(save=lambda kind,body=None:emit(kind,body))
    feed=Feed(owner);builder=ClosedBuilder();context=deque(maxlen=256);jobs=[];stop=asyncio.Event();loop=asyncio.get_running_loop();inbox=asyncio.Queue(512)
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
    history=folder/'closed-4h.jsonl'
    if history.exists():
        for line in history.open():
            b=json.loads(line)
            if context and b['start_ns']!=context[-1]['end_ns']:context.clear()
            context.append(b)
    async def models(job):
        for model in ['28M','209M']:
            remaining=300-(time.time_ns()-json.loads((job/'context.json').read_text())['origin_ns'])/1e9
            if remaining<=0:emit('forecast_missed_late',{'job':str(job),'model':model});break
            env=dict(os.environ);env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
            try:
                await asyncio.to_thread(subprocess.run,[sys.executable,str(OUT/'shadow.py'),'forecast','--job',str(job),'--model',model],env=env,check=True,timeout=remaining,stdout=subprocess.DEVNULL)
            except (subprocess.SubprocessError,OSError) as exc:emit('forecast_job_error',{'model':model,'type':type(exc).__name__})
    async def closed_bar(b):
        if context and b['start_ns']!=context[-1]['end_ns']:context.clear();emit('context_gap_reset',b)
        context.append(b);line=json.dumps(b,sort_keys=True)+'\n';worker.submit('closedbar_append',lambda:history.open('a').write(line))
        healthy=feed.certified();origin=b['end_ns'];eligible=prospective_allowed(origin/1e9,time.time(),healthy,len(context))
        emit('closed4h_context',{'origin_ns':origin,'context_length':len(context),'feed_certificate':feed.certificate(),'forecast_eligible':eligible})
        if len(context)>=21:
            bb=[experiment.baseline.Bar(x['start_ns'],x['end_ns'],*[experiment.dec(x[k]) for k in ['open','high','low','close','volume']],'prospective',0,0) for x in context]
            buy,_,_=experiment.baseline.decision(bb)
            if buy:
                for model in ['28M','209M']:
                    old=folder/'jobs'/str(origin-4*H)/(model+'.json');r=json.loads(old.read_text()) if old.exists() else None
                    if r:r={**r,'historical_available_ns':r['wall_available_ns']}
                    allowed,reason=experiment.gate(r,origin,experiment.dec(b['close'])) if healthy else (False,'feed_unhealthy')
                    emit('raw_flat_breakout_filter_only',{'decision_ns':origin,'model':model,'model_filter_allowed':allowed,'reason':reason,'actionable':False,'strict_news':'BLOCKED','not_portfolio_entry':True})
        if eligible:
            job=folder/'jobs'/str(origin)
            if job.exists():emit('duplicate_job_no_backfill',{'origin_ns':origin});return
            job.mkdir(parents=True);experiment.save(job/'context.json',{'origin_ns':origin,'feed_healthy':healthy,'published_wall_ns':time.time_ns(),'closes':[x['close'] for x in context]});jobs.append(asyncio.create_task(models(job)))
        else:emit('forecast_warmup_or_suppressed',{'origin_ns':origin,'context_length':len(context),'healthy':healthy,'no_backfill':True})
    async def consumer():
        while not stop.is_set():
            try:item,wall,mono=await asyncio.wait_for(inbox.get(),.2)
            except asyncio.TimeoutError:continue
            counts['messages']+=1;raw.append(json.dumps({'message':item,'received_ns':wall,'received_mono_ns':mono})+'\n')
            accepted=feed.process(item,wall,mono)
            if accepted and item['stream']=='btcusdt@kline_1m' and item['data']['k']['x']:
                b=builder.add(item['data']['k'])
                if b:await closed_bar(b)
            if len(raw)>=256:
                chunk=''.join(raw);raw.clear();worker.submit('raw_batch',lambda chunk=chunk:events.write(chunk))
    async with aiohttp.ClientSession(trust_env=False,cookie_jar=aiohttp.DummyCookieJar()) as session:
        rest=PublicREST(session,lambda x:emit('public_rest',x));await rest.get('/api/v3/time')
        async def certify():
            while not stop.is_set():
                try:
                    if feed.current_stream_ok:await feed.compare_rest(rest)
                except Exception as exc:emit('rest_unhealthy',{'error':type(exc).__name__})
                await asyncio.sleep(4)
        async def reader():
            delay=1
            while not stop.is_set():
                try:
                    async with session.ws_connect(WS,heartbeat=15,timeout=aiohttp.ClientWSTimeout(ws_receive=15,ws_close=5),autoping=True,max_msg_size=1000000) as ws:
                        feed.connected();delay=1
                        async for msg in ws:
                            if stop.is_set():break
                            if msg.type==aiohttp.WSMsgType.TEXT:
                                wall=time.time_ns();mono=time.monotonic_ns();item=json.loads(msg.data)
                                try:inbox.put_nowait((item,wall,mono))
                                except asyncio.QueueFull:raise ConnectionError('bounded_queue_overflow')
                            elif msg.type==aiohttp.WSMsgType.ERROR:raise ConnectionError('public_ws_error')
                except (aiohttp.ClientError,asyncio.TimeoutError,ConnectionError) as exc:
                    feed.disconnected(type(exc).__name__);emit('reconnect',{'delay':delay});await asyncio.sleep(delay);delay=min(15,delay*2)
        tasks=[asyncio.create_task(f()) for f in [consumer,reader,certify]]
        if seconds>0:loop.call_later(seconds,stop.set)
        waiter=asyncio.create_task(stop.wait());await asyncio.wait(tasks+[waiter],return_when=asyncio.FIRST_COMPLETED);stop.set()
        for task in tasks+[waiter]:task.cancel()
        await asyncio.gather(*tasks,waiter,return_exceptions=True)
        if jobs:await asyncio.gather(*jobs,return_exceptions=True)
    chunk=''.join(raw);worker.submit('last_raw',lambda:events.write(chunk));await asyncio.to_thread(worker.close);events.close()
    experiment.save(folder/'capture-summary.json',{'ended_ns':time.time_ns(),'mode':'SIGNALS_ONLY_NO_ACCOUNT_NO_ORDERS','message_counts':dict(counts),'feed':feed.certificate(),'formed4h_context':len(context),'model_jobs_launched':len(jobs),'no_orders':True,'prospective_mature_outcomes_claimed':False})


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','record','forecast']);p.add_argument('--folder',default=str(experiment.ROOT/'data/binance-spot/timestral-shadow'));p.add_argument('--seconds',type=int,default=0);p.add_argument('--job');p.add_argument('--model',choices=['28M','209M']);a=p.parse_args()
    if a.action=='prepare':prepare()
    elif a.action=='forecast':forecast_job(a.job,a.model)
    else:asyncio.run(record(a.folder,a.seconds))
if __name__=='__main__':main()
