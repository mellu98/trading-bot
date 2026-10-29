"""Snapshot actual local forward evidence; no API requests or credentials."""
from pathlib import Path
from datetime import datetime,timezone
import sqlite3,json,hashlib,urllib.request,time,re
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent

def read_cap(path):
 c=sqlite3.connect(path);c.execute('BEGIN');s=json.loads(c.execute('SELECT body FROM snapshot WHERE id=1').fetchone()[0])['capital'];return c,s

def verify():
 db,cap=read_cap(ROOT/'data/capital-v6/signals_only-EUR/state.sqlite')
 before_db,before=read_cap(OUT/'before-native.sqlite');before_db.close()
 current=json.load(urllib.request.urlopen('http://127.0.0.1:8767/api/status'))
 before_restart=json.loads((OUT/'before-restart-status.json').read_text())['capital'];recovery=json.loads((OUT/'recovery.json').read_text())
 analysis=json.loads((OUT/'native-analysis.json').read_text());capture=json.loads((OUT/'raw-completion.json').read_text())
 decisions=[]
 for row, in db.execute("SELECT body FROM journal WHERE kind='capital_native_decisions'"):decisions.extend(json.loads(row)['decisions'])
 kinds=dict(db.execute("SELECT kind,count(*) FROM journal WHERE kind LIKE 'capital_native%' GROUP BY kind"))
 integrity=db.execute('PRAGMA integrity_check').fetchone()[0];db.close()
 protected=json.loads((ROOT/'reports/capital-forward/before-sha256.json').read_text())
 changes=[p for p,sha in protected.items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha]
 allowed={'src/mnq_local/capital_app.py','src/mnq_local/capital.py','tests_local/test_capital_identifier.py','tests_local/test_capital_auth.py'}
 assert set(changes)<=allowed
 previous=json.loads((ROOT/'reports/capital-v62/delivery-sha256.json').read_text())
 prior_changed=[p for p,sha in previous.items() if not (ROOT/p).is_file() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha]
 assert set(prior_changed)<={'src/mnq_local/capital.py','src/mnq_local/capital_app.py'}
 assert current['authenticated'] and not cap['positions'] and not cap['working_orders']
 assert cap['daily_opening_attempts']==before['daily_opening_attempts']==1 and len(cap['intents'])==len(before['intents'])==2
 assert cap['halt']=='kill' and cap['technical_attempted'] and integrity=='ok'
 assert all(not d['order_requested'] and not d['execution_eligible'] and d['decided_at_ns']>=d['available_at_ns']>=d['bar_end_ms']*10**6 for d in decisions)
 ids=[d['decision_id'] for d in decisions];assert len(ids)==len(set(ids))
 result={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'native_verdict':'NOT_RELIABLE_FOR_AUTOMATIC_ENTRIES',
  'reason':'Observed late source rollover, historical ask revisions and crossed native bid/ask; no provider finality guarantee',
  'broker_demo_authenticated':current['authenticated'],'production_routing':current['real_money_routing'],'automatic_orders':False,
  'native_forward_running':current['connection'],'current_pid':json.loads((OUT/'runtime-pid.json').read_text())['pid'],
  'first_runtime_observed_seconds':(recovery['native_observation_at_ns']-recovery['native_runtime_started_ns'])/1e9,
  'second_runtime_observed_seconds':(lambda c:(c['native_observation_at_ns']-c['native_runtime_started_ns'])/1e9)(json.loads((OUT/'second-runtime-status.json').read_text())['capital']),
  'restarted_runtime_observed_seconds':(cap['native_observation_at_ns']-cap['native_runtime_started_ns'])/1e9,
  'raw_capture_seconds':capture['elapsed_s'],'raw_successful_reads':capture['responses'],'raw_transport_errors':capture['errors'],
  'native_runtime_journal_events':kinds,'native_summary':cap['native_summary'],'native_strategy_status':cap['native_strategy_status'],
  'actual_forward_decisions':len(decisions),'actual_nonzero_candidates':sum(bool(d['side']) for d in decisions),
  'rejected_candidates':cap.get('native_rejected_signals',0),'duplicate_decisions':len(ids)-len(set(ids)),
  'new_quote_events':cap['received']-before['received'],'new_orders':0,'positions_flat':True,'working_orders_flat':True,
  'daily_opening_attempts_preserved':cap['daily_opening_attempts'],'loss_counter_preserved':cap['consecutive_losses'],
  'kill_active':cap['halt'],'old_entry_budget_consumed':cap['technical_attempted'],'strict_news_certified':False,
  'clock_bounds_current':cap['native_candles']['clock'],'first_runtime_metrics':before_restart.get('feed_metrics'),
  'current_runtime_metrics':cap.get('feed_metrics'),'sqlite_integrity':integrity,'actual_flat_crash_recovery':recovery,
  'actual_open_position_kill':'NOT_TESTED: no new opening permitted with uncertified feed',
  'risk_verification':'LOCAL_CONTRACT_TESTS; actual prior DEMO roundtrip preserved; flat reconciliation and crash recovery verified this run',
  'capital_tests_passed':int(re.search(r'(\d+) passed', (OUT/'regression-tests.txt').read_text()).group(1)),'test_warnings':5,'protected_unchanged':len(protected)-len(changes),'previous_evidence_unchanged':not any(p.startswith('reports/') for p in prior_changed),
  'blocking_requirements':['Stable valid native bid/ask OHLC and bounded availability','Longer multi-session forward validation',
    'Certified strict news calendar','Independent financial strategy validation','Calibrated CFD costs and execution validation',
    'Actual protected open-position kill/recovery only after safe feed eligibility'],
  'instrument_contracts':{},'official_documentation':'https://open-api.capital.com/'}
 specs=json.loads((ROOT/'reports/capital-forward/instruments.json').read_text())
 for epic in ('US100','US500'):
  d=specs[epic];result['instrument_contracts'][epic]={'lotSize':d['instrument']['lotSize'],'marginFactor':d['instrument']['marginFactor'],
   'marginFactorUnit':d['instrument']['marginFactorUnit'],'minDealSize':d['dealingRules']['minDealSize'],'minSizeIncrement':d['dealingRules']['minSizeIncrement'],
   'native_tick_size_current':cap['native_strategy_status'][epic+'|MINUTE']['tick_size'],
   'currency':'USD','account_currency':cap['account_currency'],'cost_model':'CFD_NOT_CALIBRATED_NO_CME_COSTS',
   'spec_provenance':'Prior official DEMO instrument payload; runtime rediscovers and validates tick/lot/currency/margin every60s'}
 (OUT/'verification.json').write_text(json.dumps(result,indent=2));(OUT/'actual-decisions.json').write_text(json.dumps(decisions,indent=2))
 return result
if __name__=='__main__':
 r=verify();print(json.dumps({k:r[k] for k in ['checked_at_utc','native_verdict','native_forward_running','first_runtime_observed_seconds','restarted_runtime_observed_seconds','actual_forward_decisions','actual_nonzero_candidates','new_quote_events','new_orders','capital_tests_passed','protected_unchanged']}))
