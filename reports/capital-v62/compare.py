"""Simultaneous read-only Capital DEMO comparison; no broker mutation routes."""
import argparse,json,time,threading
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from mnq_local.capital import CapitalHTTP,Credentials,CapitalError,STREAM,rest_snapshot_payload
from websockets.sync.client import connect
EPICS=('US100','US500')

def stats(values):
    a=sorted(values)
    return {'n':len(a),**{k:a[int((len(a)-1)*p)] for k,p in [('p50',.5),('p95',.95),('p99',.99),('max',1)]},'min':a[0]} if a else {'n':0}

def price(r):return Decimal(str(r['bid'])),Decimal(str(r['ask']))

def analyze(rows):
    result={'transport_latency':'NOT_IDENTIFIABLE','timestamp_semantics':'Origin/send/price-change semantics not independently certified'}
    for epic in EPICS:
        item={};by={c:sorted([r for r in rows if r['epic']==epic and r['channel']==c],key=lambda r:r['receipt_ns']) for c in ('REST','WS')}
        for channel,rs in by.items():
            item[channel]={'timestamp_age_ms':stats([r['receipt_ns']/1e6-r['source_ms'] for r in rs]),
                'interarrival_ms':stats([(b['monotonic_ns']-a['monotonic_ns'])/1e6 for a,b in zip(rs,rs[1:])]),
                'source_interupdate_ms':stats([b['source_ms']-a['source_ms'] for a,b in zip(rs,rs[1:])]),
                'processing_ms':stats([r['processing_ms'] for r in rs]),
                'unchanged_price_messages':sum(price(a)==price(b) for a,b in zip(rs,rs[1:])),
                'changed_price_messages':sum(price(a)!=price(b) for a,b in zip(rs,rs[1:])),
                'duplicate_source_timestamps':sum(a['source_ms']==b['source_ms'] for a,b in zip(rs,rs[1:])),
                'reversed_source_timestamps':sum(a['source_ms']>b['source_ms'] for a,b in zip(rs,rs[1:])),
                'age_outside_unchanged_gate':sum(not 0<=r['receipt_ns']/1e6-r['source_ms']<=5000 for r in rs)}
        pairs=[];unique=[];ambiguous=0;unmatched=0
        for r in by['REST']:
            if by['WS']:
                w=min(by['WS'],key=lambda w:abs(w['receipt_ns']-r['receipt_ns']))
                if abs(w['receipt_ns']-r['receipt_ns'])<=10**9:pairs.append((r,w))
            matches=[w for w in by['WS'] if abs(w['receipt_ns']-r['receipt_ns'])<=20*10**9 and price(w)==price(r)]
            if len(matches)==1:unique.append((matches[0]['receipt_ns']-r['receipt_ns'])/1e6)
            elif len(matches)>1:ambiguous+=1
            else:unmatched+=1
        item['paired_receipts']={'pairs':len(pairs),'identical_bid_ask':sum(price(r)==price(w) for r,w in pairs),
            'receipt_skew_ms':stats([abs(r['receipt_ns']-w['receipt_ns'])/1e6 for r,w in pairs]),
            'source_timestamp_lead_rest_ms':stats([r['source_ms']-w['source_ms'] for r,w in pairs]),
            'midpoint_difference_rest_minus_ws':stats([float(sum(price(r))/2-sum(price(w))/2) for r,w in pairs])}
        item['price_alignment']={'window_seconds':20,'unique_match_receipt_lag_ms':stats(unique),'ambiguous_matches':ambiguous,'unmatched':unmatched,
            'caution':'An equal price is not a unique causal event; alignments do not certify transport latency or provider responsibility.'}
        # Same instrument, original millisecond timestamp AND bid/ask: compare
        # delivery of identical source events, not recurring price levels.
        groups={channel:defaultdict(list) for channel in by}
        for channel,rs in by.items():
            for r in rs:groups[channel][(r['source_ms'],price(r))].append(r)
        common=groups['REST'].keys() & groups['WS'].keys();lags=[];ambiguous_events=0
        for key in common:
            if len(groups['WS'][key])!=1:ambiguous_events+=1;continue
            r=min(groups['REST'][key],key=lambda r:r['receipt_ns']);w=groups['WS'][key][0]
            lags.append((w['receipt_ns']-r['receipt_ns'])/1e6)
        item['same_source_event']={'unique_events':len(lags),'ambiguous_ws_events':ambiguous_events,
            'ws_minus_first_rest_receipt_ms':stats(lags),'transport_latency_identified':False,
            'meaning':'Relative delivery delay of identical source timestamp + bid/ask, deduplicated across REST polls; common client clock cancels.'}
        result[epic]=item
    return result

def sampled_bars(rows):
    groups=defaultdict(list)
    for r in rows:
        if r['channel']=='REST' and 0<=r['receipt_ns']/1e6-r['source_ms']<=5000:groups[(r['epic'],r['source_ms']//60000)].append(r)
    bars=[]
    for (epic,minute),rs in sorted(groups.items()):
        # Repeated snapshots aren't independent source updates.
        rs=sorted({r['source_ms']:r for r in rs}.values(),key=lambda r:r['source_ms']);mids=[float(sum(price(r))/2) for r in rs]
        bars.append({'epic':epic,'source_minute_ms':minute*60000,'kind':'SAMPLED_REST_MIDPOINT_NOT_COMPLETE_OHLC','tick_complete':False,
            'open_sample':mids[0],'high_sample':max(mids),'low_sample':min(mids),'close_sample':mids[-1],'sample_count':len(rs),
            'first_source_ms':rs[0]['source_ms'],'last_source_ms':rs[-1]['source_ms'],
            'max_source_gap_ms':max([b['source_ms']-a['source_ms'] for a,b in zip(rs,rs[1:])],default=0),
            'available_after_receipt_ns':max(r['receipt_ns'] for r in rs),'usable_for_execution_or_extrema_claims':False})
    return bars

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seconds',type=float,default=240);ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'benchmark');a=ap.parse_args()
    if not 30<=a.seconds<=900:raise ValueError('Bounded 30..900 second diagnostic only')
    a.output.mkdir(parents=True,exist_ok=False)
    rows=[];clocks=[];pings=[];errors=[];requests=[];stop=threading.Event();start=time.monotonic();start_utc=datetime.now(timezone.utc).isoformat()
    h=CapitalHTTP(Credentials.load(),orders_enabled=False);account=h.login()
    original=h.sender
    def measured_sender(method,path,headers,body):
        if method!='GET':raise CapitalError('readonly_diagnostic_route_blocked')
        if path not in ('/session','/accounts','/positions','/workingorders','/time','/markets?searchTerm=US'):raise CapitalError('readonly_diagnostic_route_blocked')
        began=time.monotonic_ns();status,data,rh=original(method,path,headers,body)
        requests.append({'at_monotonic_ns':began,'path':path,'http_status':status,'wire_request_ms':(time.monotonic_ns()-began)/1e6})
        return status,data,rh
    h.sender=measured_sender
    def verify_flat():
        current=h.request('GET','/session');acc=h.request('GET','/accounts')['accounts'];selected=[v for v in acc if v.get('accountId')==h.credentials.account]
        assert current['accountId']==h.credentials.account and len(selected)==1 and selected[0]['status']=='ENABLED' and selected[0]['accountType']=='CFD'
        assert not h.request('GET','/positions')['positions'] and not h.request('GET','/workingorders')['workingOrders']
    verify_flat()
    def append(channel,p,receipt,mono,processing,**extra):
        if len(rows)>=50000:stop.set();raise CapitalError('diagnostic_sample_limit')
        rows.append({'channel':channel,'epic':p['epic'],'source_ms':p['timestamp'],'receipt_ns':receipt,'monotonic_ns':mono,
            'bid':str(p['bid']),'ask':str(p['ofr']),'spread':str(Decimal(str(p['ofr']))-Decimal(str(p['bid']))),'bid_qty':p.get('bidQty'),'ask_qty':p.get('ofrQty'),'processing_ms':processing,**extra})
    def receive():
        try:
            with connect(STREAM,proxy=None,open_timeout=12,close_timeout=3,max_size=65536,max_queue=16,ping_interval=20) as ws:
                ws.send(h.stream_message('marketData.subscribe',list(EPICS)));last=time.monotonic();sent={}
                while not stop.is_set():
                    if time.monotonic()-last>=30:
                        message=h.stream_message('ping');correlation=json.loads(message)['correlationId'];sent[correlation]=time.monotonic_ns();ws.send(message);last=time.monotonic()
                    try:raw=ws.recv(timeout=.25)
                    except TimeoutError:continue
                    receipt=time.time_ns();mono=time.monotonic_ns();m=json.loads(raw);processing=(time.monotonic_ns()-mono)/1e6
                    if m.get('status')!='OK':raise CapitalError('websocket_message_rejected')
                    if m.get('destination')=='quote':
                        p=m['payload']
                        if p.get('epic') not in EPICS or type(p.get('timestamp')) is not int:raise CapitalError('unexpected_quote_identity')
                        append('WS',p,receipt,mono,processing)
                    elif m.get('destination')=='ping' and m.get('correlationId') in sent:
                        pings.append((mono-sent.pop(m['correlationId']))/1e6)
        except Exception as e:errors.append({'phase':'WS','code':e.code if isinstance(e,CapitalError) else type(e).__name__})
    worker=threading.Thread(target=receive,daemon=True);worker.start();last_clock=-1e9
    try:
        while time.monotonic()-start<a.seconds and not stop.is_set():
            cycle=time.monotonic()
            if cycle-last_clock>=15:
                before=time.time_ns();m0=time.monotonic_ns();s=h.request('GET','/time')['serverTime'];m1=time.monotonic_ns();after=time.time_ns()
                clocks.append({'server_time_ms':s,'client_before_ns':before,'client_after_ns':after,'rtt_ms':(m1-m0)/1e6,
                    'offset_interval_ms':[s-after/1e6,s-before/1e6],'wall_step_ms':((after-before)-(m1-m0))/1e6});last_clock=cycle
            begin=time.monotonic_ns();data=h.request('GET','/markets?searchTerm=US');receipt=time.time_ns();mono=time.monotonic_ns()
            for epic in EPICS:
                selected=[m for m in data.get('markets',[]) if m.get('epic')==epic]
                if len(selected)!=1:raise CapitalError('rest_comparison_identity_mismatch')
                processed=time.monotonic_ns();p=rest_snapshot_payload(selected[0])
                append('REST',p,receipt,mono,(time.monotonic_ns()-processed)/1e6,request_ms=(mono-begin)/1e6,request_id=len(requests))
            (a.output/'progress.json').write_text(json.dumps({'duration_s':time.monotonic()-start,'WS':sum(r['channel']=='WS' for r in rows),'REST':sum(r['channel']=='REST' for r in rows),'errors':errors}))
            stop.wait(max(0,1-(time.monotonic()-cycle)))
        verify_flat()
    except Exception as e:errors.append({'phase':'REST','code':e.code if isinstance(e,CapitalError) else type(e).__name__})
    finally:stop.set();worker.join(5)
    duration=time.monotonic()-start;result={'started_at':start_utc,'duration_s':duration,'authenticated_demo':h.verified,'orders_enabled':h.orders_enabled,
        'errors':errors,'clock_checks':clocks,'application_ping_rtt_ms':stats(pings),'http_request_ms':stats([q['wire_request_ms'] for q in requests]),
        'max_diagnostic_requests_in_1s':max([sum(0<=b['at_monotonic_ns']-r['at_monotonic_ns']<10**9 for b in requests) for r in requests],default=0),'analysis':analyze(rows)}
    for name,value in [('rows',rows),('result',result),('sampled-bars',sampled_bars(rows)),('requests',requests)]:
        (a.output/(name+'.json')).write_text(json.dumps(value,indent=2))
    print(json.dumps({'duration_s':duration,'rows':len(rows),'errors':errors,'per_epic':{e:{k:result['analysis'][e][k]['timestamp_age_ms'] for k in ('WS','REST')} for e in EPICS}}))
if __name__=='__main__':main()
