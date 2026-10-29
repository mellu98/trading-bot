"""Frozen breakout observation only: existing public REST + existing observer health.

No Runtime/account/order/model is constructed. All outputs remain non-actionable.
"""
import argparse,asyncio,hashlib,importlib.util,json,signal,sys,time
from pathlib import Path
import aiohttp
from mnq_local.binance_spot import PublicREST,dec
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('forward_frozen_channel',ROOT/'reports/binance-spot/breakout-4h/runner.py')
baseline=importlib.util.module_from_spec(spec);sys.modules[spec.name]=baseline;spec.loader.exec_module(baseline)
STEP_MS=14400000


def closed(rows,cutoff):
    result=[]
    for row in rows:
        a,z=row[0],row[6]
        if type(a) is not int or type(z) is not int or a%STEP_MS or z!=a+STEP_MS-1:raise ValueError('Native UTC4h bounds required')
        if a+STEP_MS>cutoff:continue
        o,h,l,c,v=map(dec,row[1:6])
        if min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid OHLCV')
        result.append(baseline.Bar(a*1000000,(z+1)*1000000,o,h,l,c,v,'NATIVE_PUBLIC4H_FORWARD_CONTEXT',a,z))
    result=result[-256:]
    if len(result)!=256 or result[-1].end!=cutoff*1000000 or any(a.end!=b.start for a,b in zip(result,result[1:])):raise ValueError('256 contiguous closed current bars required')
    return result


def reasons(status,current):
    # Actual quote certification alone cannot override failed stability readiness.
    result=['STABILITY_READINESS_BLOCKED','STRICT_NEWS_UNCERTIFIED','NO_ORDER_CAPABILITY']
    if not status.get('feed_metrics',{}).get('passed'):result.append('FEED_CERTIFICATE_BLOCKED')
    if not current:result.append('NOT_CURRENT_PUBLICATION')
    return result


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def freeze():
    p=OUT/'preparation.json'
    if p.exists():raise ValueError('Already frozen')
    doc={'at_ns':time.time_ns(),'mode':'SIGNALS_ONLY_NON_ACTIONABLE','timestral':'DISABLED','parent_protocol_sha256':baseline.PH,'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),OUT/'test_recorder.py',ROOT/'reports/binance-spot/breakout-4h/runner.py']},'guards':'No orders/account/portfolio/model; no actionable signals regardless certification. Original20high/10low/ATR14 condition only; existing observer certificate recorded. Raw signal is not Risk-admitted entry. Initial256native4h bars warmup only; forming excluded. Newclose publication must be within300s, otherwise late observation NOT prospective signal. No old Sep-to-Oct splice. No retrospective PnL. Public GET/time and fixedBTCUSDT4h/limit300 only; local statusGET127.0.0.1:8767. Poll60s. No continuous-validity claim.'}
    p.write_text(json.dumps(doc,indent=2,sort_keys=True)+'\n');print(sha(p))


async def record(folder):
    receipt=json.loads((OUT/'preparation.json').read_text())
    if any(sha(ROOT/p)!=h for p,h in receipt['sources'].items()) or sha(baseline.OUT/'protocol.json')!=baseline.PH:raise ValueError('Frozen sources changed')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);stop=asyncio.Event();loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
    def emit(kind,value):
        with (folder/'events.jsonl').open('a') as f:f.write(json.dumps({'kind':kind,'at_ns':time.time_ns(),**value},sort_keys=True)+'\n')
    previous=None
    async with aiohttp.ClientSession(trust_env=False,cookie_jar=aiohttp.DummyCookieJar()) as session:
        public=PublicREST(session,lambda x:emit('public_rest',{'evidence':x,'warmup_context_only':previous is None}))
        while not stop.is_set():
            try:
                stamp=await public.get('/api/v3/time');server=stamp['data']['serverTime'];cutoff=server//STEP_MS*STEP_MS
                if previous is None or cutoff*1000000>previous:
                    started=time.time_ns();params={'symbol':'BTCUSDT','interval':'4h','limit':300,'endTime':cutoff-1}
                    async with session.get('https://data-api.binance.vision/api/v3/klines',params=params,allow_redirects=False,timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status!=200:raise ConnectionError('public_4h_http')
                        raw=await response.content.read(1000001)
                        if len(raw)>1000000:raise ValueError('byte_cap')
                        rows=json.loads(raw)
                    emit('native4h_response',{'params':params,'request_start_ns':started,'received_ns':time.time_ns(),'rows':rows,'warmup_only':previous is None})
                    bars=closed(rows,cutoff);last=bars[-1]
                    if previous is None:emit('warmup_only',{'bars':256,'first_ns':bars[0].start,'last_end_ns':last.end,'no_prospective_signal':True})
                    else:
                        if previous!=last.start:emit('forward_gap',{'previous_end_ns':previous,'latest_start_ns':last.start,'not_backfilled':True})
                        async with session.get('http://127.0.0.1:8767/api/status',allow_redirects=False,timeout=aiohttp.ClientTimeout(total=3)) as response:status=(await response.json())['report']
                        buy,exit_signal,atr=baseline.decision(bars);current=0<=server-cutoff<=300000 and previous==last.start
                        emit('real_closed4h_signal_observation',{'origin_ns':last.end,'close':str(last.close),'raw_flat_breakout':buy,'raw_channel_exit':exit_signal,'atr14':str(atr),'current_publication':current,'actionable':False,'rejections':reasons(status,current),'observer_certificate':status.get('feed_metrics'),'not_portfolio_entry':True})
                    previous=last.end
                emit('heartbeat',{'last_closed_ns':previous,'mode':'SIGNALS_ONLY','timestral':'DISABLED','actionable':False,'no_orders':True})
            except Exception as exc:emit('blocked',{'error_type':type(exc).__name__,'actionable':False,'no_orders':True})
            try:await asyncio.wait_for(stop.wait(),60)
            except asyncio.TimeoutError:pass
    emit('stopped',{'no_orders':True})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','record']);p.add_argument('--folder',default=str(ROOT/'data/binance-spot/forward-signals'));a=p.parse_args()
    if a.action=='freeze':freeze()
    else:asyncio.run(record(a.folder))
