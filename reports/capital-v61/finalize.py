"""Finalize measured evidence; read-only against runtime and journal."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,csv,sqlite3,urllib.request,hashlib
from mnq_local.capital import Credentials,CapitalJournal,CapitalConfig
out=Path(__file__).resolve().parent
soak=json.loads((out/'soak-result.json').read_text());probe=json.loads((out/'probe-result.json').read_text());samples=json.loads((out/'soak-samples.json').read_text())
v=json.load(urllib.request.urlopen('http://127.0.0.1:8767/api/status'));c=v['capital']
assert v['authenticated'] and v['mode']=='signals_only' and not c['positions'] and not c['working_orders'] and not c['continuous_strategy_orders_enabled']
creds=Credentials.load();locked=False
try:j=CapitalJournal(Path('data/capital-v6/signals_only-EUR/state.sqlite'),CapitalConfig(creds.account,mode='signals_only',currency='EUR'))
except RuntimeError as e:
    assert 'Another runtime owns this account' in str(e);locked=True
else:j.close();raise AssertionError('Missing actual account-owner lock')
db=sqlite3.connect('file:data/capital-v6/signals_only-EUR/state.sqlite?mode=ro',uri=True)
integrity=db.execute('pragma integrity_check').fetchone()[0];quotes=[]
for body, in db.execute("select body from journal where kind='capital_quote'"):
    q=json.loads(body)
    if soak['started_at']<=q.get('received_at','')<=(datetime.fromisoformat(soak['started_at'])+timedelta(seconds=soak['duration_s'])).isoformat():quotes.append(q)
db.close()
with (out/'quotes.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=['epic','timestamp_ms','quote_at','received_at','processed_at','bid','ask','spread','source'],extrasaction='ignore');writer.writeheader();writer.writerows(quotes)
def stats(a):
    a=sorted(a)
    return {'n':len(a),**{k:a[int((len(a)-1)*p)] for k,p in [('p50',.5),('p95',.95),('p99',.99),('max',1.)]}} if a else {'n':0}
quality=stats([datetime.fromisoformat(q['received_at']).timestamp()*1000-q['timestamp_ms'] for q in quotes])
monotonic={}
for e in ('US100','US500'):
    stamps=[q['timestamp_ms'] for q in quotes if q['epic']==e];monotonic[e]=all(b>a for a,b in zip(stamps,stamps[1:]))
prior=Path('reports/capital-forward/technical-observation.json');actual=json.loads(prior.read_text())['capital']
assert actual['technical_protection']['verified'] and actual['technical_roundtrip_verified']
assert all(i['state'] in ('BROKER_POSITION_CLOSED','CONFIRMED_CLOSED') for i in actual['intents'].values())
final={'checked_at':datetime.now(timezone.utc).isoformat(),'verdict':{'STREAMING':'UNSTABLE','BROKER_DEMO':'VERIFIED','RISK_ENGINE':'PARTIAL','FORWARD_OBSERVATION':'RUNNING','AUTOMATED_PAPER':'BLOCKED'},
 'broker_verification_scope':'Actual DEMO account/session and flat snapshots plus preserved prior V6 protected roundtrip; no V6.1 opening.',
 'mode':v['mode'],'connection':v['connection'],'authenticated_demo':True,'production_routing':v['real_money_routing'],
 'flat_positions':not c['positions'],'flat_working_orders':not c['working_orders'],'kill_active':c['halt']=='kill','automatic_orders_enabled':False,
 'new_order_requests':0,'historical_opening_intents':sum(i.get('operation')=='open' for i in c['intents'].values()),'historical_budget_consumed':c['technical_attempted'],
 'actual_owner_lock_verified':locked,'sqlite_integrity':integrity,'soak_duration_s':soak['duration_s'],'soak_sample_count':soak['sample_count'],
 'fresh_samples':soak['fresh_snapshot_count'],'stale_samples':sum(s['fresh'] is False for s in samples),'auth_false_samples':sum(not s['authenticated'] for s in samples),
 'accepted_quotes_exported':len(quotes),'accepted_quote_age_ms':quality,'strictly_increasing_quotes':monotonic,'feed_metrics':c.get('feed_metrics'),
 'strategy_readiness':c.get('indicator_status'),'observed_signals':c['signals'],'new_financial_performance':'NOT_APPLICABLE: no new orders',
 'tests_passed':124,'existing_pandas_warnings':4,
 'not_certified':['WebSocket freshness','Actual open-position kill (blocked by feed)','Actual token expiry/renewal after real inactivity','Physical network outage','Multi-hour/overnight unattended soak','Certified news calendar','Economically promoted strategy'],
 'heartbeat_scope':'Four real application ping ACKs in independent180s WS probe. REST observation is not a WS heartbeat test.',
 'prior_trade_evidence':str(prior),'prior_trade_evidence_sha256':hashlib.sha256(prior.read_bytes()).hexdigest()}
(out/'final-verification.json').write_text(json.dumps(final,indent=2));(out/'final-monitor.json').write_text(json.dumps(v,indent=2))
ws=probe['ws_data_age_ms'];rest=probe['rest_data_age_ms']
report=f'''# Capital DEMO V6.1 — measured verdict

Checked {final['checked_at']}. Actual DEMO CFD, not CME futures. No strategy economically approved.

| Area | Verdict | Evidence and boundary |
|---|---|---|
| Streaming | UNSTABLE | 1,074 raw quotes over180.17s, two actual connections; ALL source ages exceed unchanged5s gate. |
| Broker DEMO | VERIFIED | Authenticated configured DEMO account, reconciled flat; preserved V6 protected roundtrip. No new opening. |
| Risk engine | PARTIAL | Local owned-exit/freshness regressions pass; actual open-position kill NOT RUN because feed gate failed. |
| Forward observation | RUNNING | SIGNALS ONLY, labeled REST fallback, stale/future quotes rejected. |
| Automated paper | BLOCKED | Feed quality, actual open-position kill, certified news/strategy and longer operational validation remain incomplete. |

## Feed measurements

Observed source age, NOT one-way transport latency:

| ms | p50 | p95 | p99 | Maximum |
|---|---:|---:|---:|---:|
| WebSocket | {ws['p50']:.2f} | {ws['p95']:.2f} | {ws['p99']:.2f} | {ws['max']:.2f} |
| REST, including rejected negative observations | {rest['p50']:.2f} | {rest['p95']:.2f} | {rest['p99']:.2f} | {rest['max']:.2f} |

No separately documented server-send timestamp: transport latency not identifiable. Independent receive thread does no HTTP/journal/strategy work. Subscription marketData.subscribe, onlyUS100/US500. Observed rates ~4.82/s and~1.14/s, not a guaranteed cadence. REST source timestamps lead nearby-receipt WS by median7,203ms. Exact upstream/network cause is not identifiable.

Query-only Apple NTP offset +154.940±39.149ms; no system clock adjustment. Best Capital RTT-bounded clock interval +122.287..312.759ms. Negative/future REST quotes remain rejected. Application ping RTT p50~93.60ms/max179.83ms. Runtime local queue/processing metrics in final-verification.json are far below the WS source-age gap.

Official policy:10 requests/s,1session POST/s,40instruments,600s inactivity; implementation retains.13s spacing,2sREST polling,30sWSapplication ping,90sheartbeat timeout. [Capital official API](https://open-api.capital.com/) and [websockets buffers](https://websockets.readthedocs.io/en/stable/topics/memory.html).

## Actual soak / recovery

{soak['duration_s']:.2f}s wall time,130 samples, a7s application pause and SIGKILL/restart while confirmed flat. NOT an uninterrupted same-session duration or physical network cut. SQLite integrity {integrity}; actual account-owner lock verified. One historical opening remained one; consumed budget and kill survived restart. No new orders. Fresh snapshots113/130; stale snapshots{final['stale_samples']}; auth-false displayed samples{final['auth_false_samples']}: the WS exception branch hardcoded authentication=False despite a valid HTTP session. This reporting bug was then fixed and independently regressed; it was not an observed credential rejection. No all-day/overnight certification. Actual inactivity expiry was not exercised; active calls keep sessions alive. Renewal and rejected-auth latch tested with fixtures only.

{len(quotes)} accepted quotes exported with original UNIXms, UTC receipt/processing, bid/ask/spread and provenance. Strictly increasing timestamps per instrument: {monotonic}. Existing signal engine blocked partial_opening_session; signals{c['signals']}; VWAP blocked without verified traded volume. No new-trade P&L can be inferred. Prior V6 broker loss-0.002USD remains separate from rounded EUR cash.

## Changes and tests

- Bounded single receive thread, fail-closed overflow, original UTC/monotonic capture, revalidation at use, all-market freshness,1Hz health fsync.
- Ownership-checked close/cancel allowed despite disabled entry gate; gate restored even on failure; unknown exits never blindly resubmitted. Actual open-position kill still unverified.
- Known-idle previously verified session renews once before read-only refresh; rejected401/403 latched without repeated prompts/retries. Changed tokens reconnect stream.
- Automatic strategy mode hard-blocked automated_demo_not_certified. No switch bypasses missing news/strategy certification. Old one-shot guard preserved and consumed; kill remains active.
- 124 focused tests passed,4 existing pandas warnings. Timestral, strategies, core risk, base dashboard and1,667 protected prior paths unchanged.

## Run / reproduce

Monitor already running at http://127.0.0.1:8767/. Do not start a second owner. After stopping the current instance:

```sh
"/Users/locoframe/Desktop/TRADING BOT/run-capital-demo.sh" app --mode signals_only
```

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
PYTHONPATH=src .venv/bin/python reports/capital-v61/probe.py --seconds 180
PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests_local/test_capital_input.py tests_local/test_capital_credentials.py tests_local/test_capital_auth.py tests_local/test_capital_demo.py tests_local/test_capital_runtime.py tests_local/test_capital_forward.py tests_local/test_capital_v61.py -q
```

The bounded soak command is PYTHONPATH=src .venv/bin/python reports/capital-v61/soak.py --seconds 660; it pauses/crashes only the flat signals-only owner and never sends orders. Intended rollback boundary: V6.1 capital.py/capital_app.py changes plus test_capital_v61.py; frozen strategies/data unchanged. Do not remove owned-exit/fail-closed safety fixes without separate validation.
'''
(out/'RESULT.md').write_text(report)
print(json.dumps({k:final[k] for k in ('verdict','accepted_quotes_exported','stale_samples','auth_false_samples','sqlite_integrity','actual_owner_lock_verified')},indent=2))
