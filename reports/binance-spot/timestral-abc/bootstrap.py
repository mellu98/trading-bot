"""Two public GETs for prospective context ONLY, never a new financial test period."""
from pathlib import Path
from decimal import Decimal
import argparse,asyncio,json,time
import aiohttp
import runner as e
from mnq_local.binance_spot import PublicREST
STEP_MS=14400000


def parsed(row,step_ms):
    a,z=row[0],row[6]
    if type(a) is not int or type(z) is not int or a%step_ms or z!=a+step_ms-1:raise ValueError('Native UTC bounds/units mismatch')
    o,h,l,c,v=map(e.dec,row[1:6])
    if min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid native OHLCV')
    return {'start_ns':a*1000000,'end_ns':(z+1)*1000000,'open':str(o),'high':str(h),'low':str(l),'close':str(c),'volume':str(v),'source':'ACTUAL_BINANCE_PUBLIC_REST_NATIVE_CLOSED_BAR'}


def select_closed(rows,cutoff_ms):
    if cutoff_ms%STEP_MS:raise ValueError('UTC4h cutoff required')
    closed=[row for row in rows if type(row[0]) is int and row[0]+STEP_MS<=cutoff_ms];excluded=len(rows)-len(closed)
    chosen=closed[-256:]
    if len(chosen)!=256:raise ValueError('256 complete native4h bars required')
    bars=[parsed(row,STEP_MS) for row in chosen]
    if bars[-1]['end_ns']!=cutoff_ms*1000000 or any(a['end_ns']!=b['start_ns'] for a,b in zip(bars,bars[1:])):raise ValueError('Gap/duplicate/stale native4h context')
    return bars,excluded


def fold_minutes(rows,end_ns):
    if len(rows)!=240 or end_ns%(4*e.H):raise ValueError('240complete native minutes required')
    bars=[parsed(row,60000) for row in rows];start=end_ns-4*e.H
    if any(b['start_ns']!=start+i*60000000000 for i,b in enumerate(bars)):raise ValueError('Missing/reordered native minute')
    return {'start_ns':start,'end_ns':end_ns,'open':bars[0]['open'],'high':str(max(e.dec(b['high']) for b in bars)),'low':str(min(e.dec(b['low']) for b in bars)),'close':bars[-1]['close'],'volume':str(sum(e.dec(b['volume']) for b in bars)),'source':'ACTUAL_CLOSED_PUBLIC_REST1M_UTC4H_RECONCILIATION'}


async def bootstrap(folder):
    from shadow import check
    check();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);history=folder/'closed-4h.jsonl'
    if history.exists():raise ValueError('Never overwrite existing prospective/warmup bar records')
    evidence=[]
    async with aiohttp.ClientSession(trust_env=False,cookie_jar=aiohttp.DummyCookieJar()) as session:
        public=PublicREST(session,evidence.append);stamp=await public.get('/api/v3/time');server=stamp['data']['serverTime']
        if type(server) is not int:raise ValueError('Integer Binance milliseconds required')
        cutoff=server//STEP_MS*STEP_MS;started=time.time_ns()
        # Shadow-only fixed public market-data request. Original1m provider guard unchanged.
        params={'symbol':'BTCUSDT','interval':'4h','limit':300,'endTime':cutoff-1}
        async with session.get('https://data-api.binance.vision/api/v3/klines',params=params,allow_redirects=False,timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status!=200:raise ConnectionError('Public warmup HTTP '+str(response.status))
            content=await response.content.read(1000001)
            if len(content)>1000000:raise ValueError('Warmup response byte cap')
            rows=json.loads(content)
        evidence.append({'method':'GET','origin':'https://data-api.binance.vision','path':'/api/v3/klines','params':params,'request_start_ns':started,'received_ns':time.time_ns(),'status':200,'data':rows})
    bars,excluded=select_closed(rows,cutoff)
    with (folder/'warmup-public-rest.jsonl').open('x') as f:
        for item in evidence:f.write(json.dumps(item,sort_keys=True)+'\n')
    with history.open('x') as f:
        for b in bars:f.write(json.dumps({**b,'warmup_only':True,'not_prospective_forecast':True},sort_keys=True)+'\n')
    e.save(folder/'bootstrap-proof.json',{'at_ns':time.time_ns(),'status':'PASS','scope':'WARMUP_ONLY_NOT_NEW_FINANCIAL_TEST_NOT_PROSPECTIVE_PREDICTIONS','requests':2,'native4h_bars':len(bars),'forming_excluded':excluded,'server_time_ms':server,'cutoff_ms':cutoff,'first_start_ns':bars[0]['start_ns'],'last_end_ns':bars[-1]['end_ns'],'contiguous':True,'gaps':0,'source':'Binance public native4h klines; not reconstructed futures or Sep-to-Oct gap splice','clock_midpoint_offset_ms':server-(stamp['request_start_ns']+stamp['response_received_ns'])/2000000,'clock_uncertainty_ms':(stamp['response_received_ns']-stamp['request_start_ns'])/2000000,'source_age_not_network_latency':True,'initial_history_sha256':e.sha(history),'rest_evidence_sha256':e.sha(folder/'warmup-public-rest.jsonl'),'forecasts_issued':0,'no_orders':True})
    print('WARMUP_PASS',len(bars),'last_end',e.iso(bars[-1]['end_ns']),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);a=p.parse_args();asyncio.run(bootstrap(a.folder))
