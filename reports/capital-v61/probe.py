"""Read-only fast-drain diagnostic. No journal writes and no order routes."""
import json,time,threading,statistics,argparse
from pathlib import Path
from datetime import datetime,timezone
from websockets.sync.client import connect
from mnq_local.capital import CapitalHTTP,Credentials,STREAM,CapitalError,rest_snapshot_payload

def stats(a):
    if not a:return {'n':0}
    a=sorted(a)
    def p(q):return a[min(len(a)-1,max(0,int((len(a)-1)*q)))]
    return {'n':len(a),'p50':p(.5),'p95':p(.95),'p99':p(.99),'max':max(a),'min':min(a)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seconds',type=float,default=180);args=ap.parse_args()
    out=Path('reports/capital-v61');h=CapitalHTTP(Credentials.load(),orders_enabled=False);h.login()
    rows=[];rest=[];clocks=[];heartbeats=[];errors=[];connections=[];stop=threading.Event()
    t0=time.monotonic();started=datetime.now(timezone.utc).isoformat()
    def receiver():
        for connection in range(2):
            if stop.is_set():break
            try:
                with connect(STREAM,proxy=None,open_timeout=12,close_timeout=3,max_size=65536,max_queue=16,ping_interval=20) as ws:
                    connections.append({'connection':connection,'opened_after_s':time.monotonic()-t0})
                    ws.send(h.stream_message('marketData.subscribe',['US100','US500']));last_ping=time.monotonic()
                    while not stop.is_set():
                        if time.monotonic()-last_ping>=30:
                            ws.send(h.stream_message('ping'));last_ping=time.monotonic()
                        # Deliberately force one clean reconnect halfway through.
                        if connection==0 and time.monotonic()-t0>=args.seconds/2:break
                        try:raw=ws.recv(timeout=.25)
                        except TimeoutError:continue
                        received_ns=time.time_ns();mono_ns=time.monotonic_ns()
                        m=json.loads(raw);dest=m.get('destination');p=m.get('payload',{})
                        if dest=='quote' and isinstance(p.get('timestamp'),int):
                            rows.append({'epic':p.get('epic'),'timestamp_ms':p['timestamp'],'received_ns':received_ns,'monotonic_ns':mono_ns,
                                'age_ms':received_ns/1e6-p['timestamp'],'bid':p.get('bid'),'ask':p.get('ofr'),'connection':connection})
                        elif dest=='ping':heartbeats.append({'rtt_ms':(time.monotonic()-last_ping)*1000,'connection':connection})
            except Exception as e:errors.append({'phase':'websocket','code':e.code if isinstance(e,CapitalError) else type(e).__name__})
    worker=threading.Thread(target=receiver,daemon=True);worker.start()
    try:
        while time.monotonic()-t0<args.seconds:
            a=time.time_ns();m0=time.monotonic_ns();clock=h.request('GET','/time');m1=time.monotonic_ns();b=time.time_ns()
            server=clock.get('serverTime');rtt=(m1-m0)/1e6
            clocks.append({'rtt_ms':rtt,'offset_interval_ms':[server-b/1e6,server-a/1e6],'wall_step_ms':(b-a-(m1-m0))/1e6})
            for epic in ('US100','US500'):
                a=time.monotonic_ns();data=h.request('GET','/markets?searchTerm='+epic);received=time.time_ns();elapsed=(time.monotonic_ns()-a)/1e6
                matches=[m for m in data.get('markets',[]) if m.get('epic')==epic]
                if len(matches)==1:
                    p=rest_snapshot_payload(matches[0]);rest.append({'epic':epic,'timestamp_ms':p['timestamp'],'received_ns':received,'age_ms':received/1e6-p['timestamp'],'request_ms':elapsed})
            if int(time.monotonic()-t0)%30<6:
                session=h.request('GET','/session');accounts=h.request('GET','/accounts');positions=h.request('GET','/positions');orders=h.request('GET','/workingorders')
                if session.get('accountId')!=h.credentials.account:raise CapitalError('account_mismatch')
                if positions.get('positions') or orders.get('workingOrders'):raise CapitalError('unexpected_exposure')
            stop.wait(5)
    except Exception as e:errors.append({'phase':'rest','code':e.code if isinstance(e,CapitalError) else type(e).__name__})
    finally:
        stop.set();worker.join(6)
    elapsed=time.monotonic()-t0
    result={'started_at':started,'duration_s':elapsed,'authenticated_demo':h.verified,'orders_enabled':h.orders_enabled,'connections':connections,'errors':errors,
        'ws_data_age_ms':stats([r['age_ms'] for r in rows]),'rest_data_age_ms':stats([r['age_ms'] for r in rest]),'rest_request_ms':stats([r['request_ms'] for r in rest]),
        'clock_checks':clocks,'application_ping_rtt_ms':stats([p['rtt_ms'] for p in heartbeats]),'transport_latency':'NOT_IDENTIFIABLE: quote timestamp is not documented as server-send timestamp',
        'per_instrument':{e:{'ws_age_ms':stats([r['age_ms'] for r in rows if r['epic']==e]),'samples_per_second':sum(r['epic']==e for r in rows)/elapsed} for e in ('US100','US500')}}
    for name,data in [('probe-result',result),('probe-ws',rows),('probe-rest',rest)]:
        (out/(name+'.json')).write_text(json.dumps(data,indent=2))
    print(json.dumps({k:result[k] for k in ('duration_s','ws_data_age_ms','rest_data_age_ms','errors')}))
if __name__=='__main__':main()
