"""Verify two bounded native minute-bar reads; no order or settings calls."""
import json,time
from pathlib import Path
from datetime import datetime,timezone
from mnq_local.capital import CapitalHTTP,Credentials,CapitalError
out=Path(__file__).resolve().parent;h=CapitalHTTP(Credentials.load(),orders_enabled=False);h.login();raw={};report={};rows=json.loads((out/'benchmark/rows.json').read_text())
for epic in ('US100','US500'):
    before=time.monotonic_ns();received=datetime.now(timezone.utc)
    try:
        data=h.request('GET','/prices/'+epic+'?resolution=MINUTE&max=10');received=datetime.now(timezone.utc);raw[epic]={'received_at':received.isoformat(),'payload':data}
        closed=[]
        for b in data.get('prices',[]):
            at=datetime.fromisoformat(b['snapshotTimeUTC'])
            if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)  # Explicit documented UTC field.
            assert at.second==0 and at.microsecond==0
            assert all(b['lowPrice'][side]<=min(b['openPrice'][side],b['closePrice'][side])<=max(b['openPrice'][side],b['closePrice'][side])<=b['highPrice'][side] for side in ('bid','ask'))
            if at.timestamp()+60<=received.timestamp():closed.append((at,b))
        gaps=[(b[0]-a[0]).total_seconds() for a,b in zip(closed,closed[1:])]
        compared=[]
        for at,b in closed:
            ms=int(at.timestamp())*1000
            rs=[r for r in rows if r['channel']=='REST' and r['epic']==epic and ms<=r['source_ms']<ms+60000 and 0<=r['receipt_ns']/1e6-r['source_ms']<=5000]
            if not rs:continue
            sampled_high=max(float(r['bid']) for r in rs);sampled_low=min(float(r['bid']) for r in rs)
            compared.append({'source_minute_utc':at.isoformat(),'samples':len(rs),'native_bid_high':b['highPrice']['bid'],'sampled_bid_high':sampled_high,
                'native_bid_low':b['lowPrice']['bid'],'sampled_bid_low':sampled_low,
                'sample_missed_native_extrema':sampled_high<b['highPrice']['bid'] or sampled_low>b['lowPrice']['bid']})
        report[epic]={'http_status':200,'request_ms':(time.monotonic_ns()-before)/1e6,'returned':len(data.get('prices',[])),
            'closed':len(closed),'utc_minute_contiguous':all(g==60 for g in gaps),'same_window_comparison':compared,
            'usage':'Broker-native closed minute bars, received now. Not available retrospectively for decisions before this receipt; no order/execution certification.'}
    except CapitalError as e:report[epic]={**e.diagnostic(),'phase':'native_bar_read'}
(out/'native-bars-raw.json').write_text(json.dumps(raw,indent=2));(out/'native-bars-validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
