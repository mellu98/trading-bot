"""Descriptive age-of-information check requested after freeze; no changed rules or PnL runs."""
import csv,json,socket
from pathlib import Path
import numpy as np
import runner as e
socket.socket.connect=e.deny;socket.socket.connect_ex=e.deny;socket.create_connection=e.deny
bars,quality=e.load();four=e.baseline.aggregate4(bars);close={b.end:b.close for b in four};cache={m:e.cached(m,quality,four) for m in e.PINS}
ledger=e.baseline.OUT/'run-1/reserved_test/base/strategy/trades.csv';trades=list(csv.DictReader(ledger.open()));end=bars[-1].end;result={}
for model in e.PINS:
 rows=[]
 for t in trades:
  decision=int(t['entry_ns']);r=cache[model].get(decision-4*e.H);target=decision+4*e.H
  if r is None or r.get('status')!='ok' or target>=end or target not in close:continue
  current=float(close[decision]);past=float(close[decision-4*e.H]);actual=float(close[target]);median=float(r['quantiles'][1][10]);allowed,reason=e.gate(r,decision,close[decision])
  rows.append({'decision_ns':decision,'forecast_origin_ns':decision-4*e.H,'target_ns':target,'current_close':current,'prior_origin_close':past,'actual_target_price':actual,'median_step2':median,'model_abs_error':abs(actual-median),'newer_decision_T_persistence_abs_error':abs(actual-current),'older_origin_O_persistence_abs_error':abs(actual-past),'filter_allowed':allowed,'reason':reason,'matched_A_trade_net':t['net'],'positive_A_roundtrip':e.dec(t['net'])>0})
 e.baseline.rows(e.OUT/(model+'-matched-A-candidate-diagnostic.csv'),rows)
 result[model]={'matched_mature_A_candidates':len(rows),'model_mae_price':float(np.mean([r['model_abs_error'] for r in rows])),'decision_T_persistence_mae_price':float(np.mean([r['newer_decision_T_persistence_abs_error'] for r in rows])),'origin_O_persistence_mae_price':float(np.mean([r['older_origin_O_persistence_abs_error'] for r in rows])),'filter_allowed':sum(r['filter_allowed'] for r in rows),'positive_A_roundtrips_vetoed':sum(r['positive_A_roundtrip'] and not r['filter_allowed'] for r in rows)}
e.save(e.OUT/'matched-A-candidate-diagnostic.json',{'scope':'Additive descriptive age-of-information analysis only; frozen primary originO horizon2 scores, rules/verdicts/economic configs unchanged. CurrentcloseT is newer information than cachedforecastoriginO=T-4h. MatchedAtrade outcomes are posthoc counterfactuals, not causal profitlost nor a selectedstrategy.','models':result,'source_A_ledger_sha256':e.sha(ledger),'dataset_sha256':quality['dataset_sha256'],'no_inference_rerun':True,'no_new_strategy':True})
print(json.dumps(result,indent=2))
