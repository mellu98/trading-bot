"""Frozen conjunction of promotion gates. No new strategy selection or parameter search."""
import json
from pathlib import Path
from data import ROOT,save

def complete(x):return x.get('status')=='COMPLETE'
def finite(x):return x is not None and x==x and abs(x)!=float('inf')
def assess(devval,holdout):
 result={}
 for family in ('A','B','C'):
  v=devval['results']['validation'][family];h=holdout['results']['holdout'][family];g={}
  for period,arms in [('validation',v),('holdout',h)]:
   for cost in ('base','adverse','severe'):
    x=arms[cost]['primary_strategy'];g[f'{period}_{cost}_net']=complete(x) and (x['net_return']>=0 if cost=='severe' else x['net_return']>0)
  for cost in ('base','adverse'):
   x=h[cost]['neighbor_strategy'];g[f'neighbor_holdout_{cost}_positive']=complete(x) and x['net_return']>0
  main=h['base']['primary_strategy'];risk=h['base']['primary_riskcap'];valid=complete(main) and complete(risk)
  g['holdout_daily_drawdown_not_worse_than_exante_riskcap']=valid and main['max_drawdown']<=risk['max_drawdown']
  a=main.get('daily_sharpe_365');b=risk.get('daily_sharpe_365');g['holdout_risk_adjusted_comparator']=valid and finite(a) and finite(b) and (a>=b if family=='A' else a>b)
  if family=='A':
   comparator=h['base']['primary_matched'];g['positive_incremental_mean_excess_vs_exposure_matched_EW']=complete(main) and complete(comparator) and sum(main['daily_returns'])>sum(comparator['daily_returns'])
  inf=h['base'].get('inference',{});blocks=inf.get('blocks',{})
  for k in ('7','30'):
   z=blocks.get(k,{});g['holdout_family3_adjusted_inference_block'+k]=z.get('status')=='OK' and finite(z.get('lower_family3')) and z['lower_family3']>0
  result[family]={'eligible_for_signals_only_forward_research':all(g.values()),'gates':g,'not_financial_approval':True,'global_DSR':'NOT_ESTIMABLE_UNKNOWN_PRIOR_TRIAL_COUNT','concentration_and_regimes_are_required_descriptive_evidence_not_posthoc_pass_thresholds':True}
 return {'families':result,'any_promoted_to_forward_candidate':any(x['eligible_for_signals_only_forward_research'] for x in result.values()),'statistical_gate_period':'holdout only; validation has frozen economic conjunction, not fitted parameters','future_profit_guarantee':False}
if __name__=='__main__':
 a=json.loads((ROOT/'results-development-validation/results.json').read_text());b=json.loads((ROOT/'results-holdout/results.json').read_text());p=ROOT/'assessment.json'
 if p.exists():raise ValueError('never overwrite assessment')
 save(p,assess(a,b));print(p)
