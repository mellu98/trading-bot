"""Read-only evidence export; no broker mutations."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,sqlite3,urllib.request,csv
from mnq_local.capital import Credentials
root=Path.cwd();out=root/'reports/capital-v62';b=json.loads((out/'benchmark/result.json').read_text());again=json.loads((out/'benchmark-after/result.json').read_text());independent=json.loads((out/'independent-result.json').read_text());native=json.loads((out/'native-bars-validation.json').read_text())
v=json.load(urllib.request.urlopen('http://127.0.0.1:8767/api/status'));c=v['capital'];assert v['authenticated'] and v['mode']=='signals_only' and not c['positions'] and not c['working_orders'] and c['consecutive_losses']==1 and c['halt']=='kill'
start=json.loads((out/'before-monitor.json').read_text())['updated_at'];db=sqlite3.connect('file:data/capital-v6/signals_only-EUR/state.sqlite?mode=ro',uri=True);quotes=[];rejects=[];signals=[]
for kind,body in db.execute("select kind,body from journal where kind in ('capital_quote','capital_observation_rejected','capital_signal')"):
    r=json.loads(body)
    if r.get('received_at',r.get('trigger_quote',{}).get('received_at',''))>=start:{'capital_quote':quotes,'capital_observation_rejected':rejects,'capital_signal':signals}[kind].append(r)
integrity=db.execute('pragma integrity_check').fetchone()[0];db.close()
with (out/'forward-quotes.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=['epic','timestamp_ms','quote_at','received_at','processed_at','bid','ask','spread','source'],extrasaction='ignore');w.writeheader();w.writerows(quotes)
(out/'forward-rejections.json').write_text(json.dumps(rejects,indent=2));(out/'forward-signals.json').write_text(json.dumps(signals,indent=2));(out/'final-monitor.json').write_text(json.dumps(v,indent=2))
previous=json.loads((out/'before-sha256.json').read_text());allowed={'src/mnq_local/capital.py','src/mnq_local/capital_app.py'}
changed=[p for p,h in previous.items() if not Path(p).is_file() or hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h];assert set(changed)<=allowed
base=json.loads((root/'reports/capital-forward/before-sha256.json').read_text());excluded=set(json.loads((root/'reports/capital-forward/preservation.json').read_text())['authorized_changed_paths']);protected={p:h for p,h in base.items() if p not in excluded}
assert all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in protected.items())
summary={'checked_at':datetime.now(timezone.utc).isoformat(),'verdict':'C_EVIDENCE_INSUFFICIENT_FOR_CERTIFICATION_OR_PROVIDER_ROOT_CAUSE',
 'measured':'WebSocket identical source events arrive materially later than REST across simultaneous independent clients; current feed is unsuitable for automatic entries',
 'missing':'Provider emission telemetry or independent network-path measurement to attribute broker backend versus shared WebSocket/network delay',
 'production_routing':False,'automatic_orders':False,'broker_demo_authenticated':True,'positions_flat':True,'working_orders_flat':True,'new_openings':0,
 'historical_opening_attempts':c['daily_opening_attempts'],'consecutive_losses':c['consecutive_losses'],'old_budget_consumed':c['technical_attempted'],'kill_active':True,
 'forward_mode':v['mode'],'connection':v['connection'],'forward_quotes':len(quotes),'logged_rejections':len(rejects),'signals':len(signals),'sqlite_integrity':integrity,
 'actual_open_position_kill':'NOT_TESTED: feed anomaly prevents openings','tests_passed':134,'existing_warnings':4,
 'protected_paths_unchanged':len(protected),'prior_V6_V61_evidence_unchanged':True,'modified_existing_source':changed,'strict_news_certified':False,
 'native_bars_verified_closed':sum(x['closed'] for x in native.values()),'complete_sampled_minutes_compared':sum(x['complete_minutes_compared'] for x in native.values()),
 'sampled_minutes_missing_native_extrema':sum(x['complete_minutes_with_missed_extrema'] for x in native.values())}
(out/'verification.json').write_text(json.dumps(summary,indent=2))
lines=['# Capital DEMO V6.2 — measured decision','',
'**C — EVIDENCE INSUFFICIENT to certify the operational feed or attribute the fault specifically to the provider backend.** The WebSocket delivery path is demonstrably unsuitable for current entry gates. Missing: server emission telemetry or an independent network path to distinguish provider queueing from shared channel/network delay. No threshold was raised.','',
'## Simultaneous measurements','',
'241.92s; 1,285 WS quotes and474 REST observations, US100/US500 returned in the same REST response. Full original UNIXms, UTC receive ns, monotonic receive ns, parse time, bid/ask/spread retained in benchmark/rows.json.','',
'| Instrument | WS timestamp age p50 / p95 | REST timestamp age p50 / p95 | Identical events | WS after first REST receipt p50 / p95 |',
'|---|---:|---:|---:|---:|']
for e in ('US100','US500'):
    a=b['analysis'][e];w=a['WS']['timestamp_age_ms'];r=a['REST']['timestamp_age_ms'];d=a['same_source_event']['ws_minus_first_rest_receipt_ms']
    lines.append(f"| {e} | {w['p50']/1000:.3f}s / {w['p95']/1000:.3f}s | {r['p50']/1000:.3f}s / {r['p95']/1000:.3f}s | {d['n']} | {d['p50']/1000:.3f}s / {d['p95']/1000:.3f}s |")
lines += ['',
'Identical-event matching requires epic + source timestamp + bid + ask; repeated REST polls are deduplicated. Client clock offset cancels. These are relative delivery differences, NOT one-way network latency. Clock bounds against GET/time: best +42.85..240.09ms. Parse p95 <0.052ms. Update interarrival p50/p95: US100175.7/505.2ms; US500864.5/3175.6ms. Diagnostic maximum4HTTPrequests/s; runtime conservative pacing retained; no observed429. [Official API](https://open-api.capital.com/).','',
'## Controls / repeat benchmark','',
'61.97s repeat still delayed: identical-event median5.13s/5.21s. An isolated60s Node test briefly looked fresh, but simultaneous120.96s Node and Python both reached WS source-age p95~17s/max~22.5s.574matching US100 events reached the two clients at median0.238ms apart;83US500 at0.226ms. Disabling compression also left6–8s source ages. No client/compression change is justified. One application ping RTT reached13.59s; this does not locate the internal cause. A brief fresh window is not certification.','',
'Four US100 and eight US500 WS messages repeated unchanged bid/ask and quantities. Do not assume an exclusively bid/ask-change-only protocol; official documentation does not certify that policy.','',
'## REST and bars','',
'REST is useful for conservatively gated observation, not complete tick-derived OHLC. Snapshot sampling missed native extrema in3of4fully observed instrument-minutes. Native GET /prices/{US100,US500}?resolution=MINUTE&max=10 was authenticated and verified HTTP200:18closed contiguous UTC minute bars. Best same-broker alternative: REST snapshots for observation and broker-native closed minute bars for research. They are available only after actual receipt, not retrospectively for decisions. Neither path certifies intrabar execution.','',
'## Safety / running state','',
f"Fixed a loss-counter recovery bug caused by sorted JSON processing close before entry; idempotent outcomes and daily opening-attempt limits now reach the existing Risk Engine. Actual prior loss is counted once; actual flat SIGKILL/restart preserves counter1, opening count1 and consumed budget; SQLite {integrity}. Kill/protection/unknown-exit handling passed local regressions, not a new open-position broker test. No new orders; historical protected roundtrip unchanged.134focused tests pass,4existing warnings.1,667protected paths unchanged.",
'',f"SIGNALS ONLY remains running at http://127.0.0.1:8767/ ({v['connection']}). {len(quotes)} new accepted quotes exported; {len(rejects)} rejected observations logged; {len(signals)} signals (partial opening-session gate). REST-derived signals are explicitly tagged sampled/not complete OHLC, include triggering quote context, and are execution-ineligible. News remains uncertified and blocking. No economic promotion.",
'', '## Reproduce','', '```sh', 'cd "/Users/locoframe/Desktop/TRADING BOT"',
'PYTHONPATH=src .venv/bin/python reports/capital-v62/compare.py --seconds 240 --output "reports/capital-v62/repro-$(date -u +%Y%m%dT%H%M%SZ)"',
'PYTHONPATH=src:adapters/databento/src:adapters/databento_planner/src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests_local/test_capital_input.py tests_local/test_capital_credentials.py tests_local/test_capital_auth.py tests_local/test_capital_demo.py tests_local/test_capital_runtime.py tests_local/test_capital_forward.py tests_local/test_capital_v61.py tests_local/test_capital_v62.py -q',
'```','', 'The observer already runs. After stopping its current owner, restart with the absolute command:',
'```sh','"/Users/locoframe/Desktop/TRADING BOT/run-capital-demo.sh" app --mode signals_only','```','',
'Rollback scope: only Capital loss-accounting/read-only native-bar allowlist/provenance changes and V6.2 diagnostic tests; no broker switch or core-strategy/Risk Engine edits. Do not restore the known counter bug without validated replacement.']
(out/'RESULT.md').write_text('\n'.join(lines)+'\n')
creds=Credentials.load();secrets=[x.encode() for x in (creds.api_key,creds.identifier,creds.password)]
files=[p for p in out.rglob('*') if p.is_file()];assert not [str(p) for p in files if any(s in p.read_bytes() for s in secrets)]
(out/'delivery-sha256.json').write_text(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files+[root/'src/mnq_local/capital.py',root/'src/mnq_local/capital_app.py',root/'tests_local/test_capital_v62.py'] if p.name not in ('delivery-sha256.json','monitor.log')},indent=2))
print(json.dumps(summary,indent=2))
