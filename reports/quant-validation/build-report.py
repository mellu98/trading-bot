"""Render actual offline evaluation evidence; never produces hypothetical metrics."""
import json
from pathlib import Path
from decimal import Decimal
P=Path(__file__).resolve().parent
r=json.loads((P/'quant-results.json').read_text());q=json.loads((P/'quote115.json').read_text())
d=json.loads((P/'data-quality120.json').read_text());g=json.loads((P/'granular-quote.json').read_text())
proto=json.loads((P/'preregistered-protocol.json').read_text())
# Post-evaluation uncertainty is explicitly exploratory, not a newly registered filter.
import csv
from mnq_sim.quant import block_interval
subgroups={}
for symbol in ('MNQ','MES'):
 for arm in ('fixed','vwap'):
  for stage in ('walkforward','holdout'):
   rows=list(csv.DictReader((P/'results'/f'{symbol}-{arm}-{stage}-trades.csv').open()))
   days=list(r['walk_forward' if stage=='walkforward' else 'holdout'][symbol+'/'+arm]['daily_net'])
   key=f'{symbol}/{arm}/{stage}';subgroups[key]={}
   for field in ('regime','time_bucket','side'):
    subgroups[key][field]={}
    for cat in sorted({row[field] for row in rows}):
     values=[sum(float(row['net']) for row in rows if row[field]==cat and row['entry_at'].startswith(day)) for day in days]
     selected=[row for row in rows if row[field]==cat]
     subgroups[key][field][cat]={'trades':len(selected),'net':sum(values),
        'uncertainty_exploratory_family72':block_interval(values,family=72)}
(P/'oos-predeclared-subgroups.json').write_text(json.dumps({
 'status':'descriptive_only_no_filter_selected','no_additional_significance_claim':True,
 'interpretation':'Post-evaluation uncertainty for predeclared categories; conservative family72; not a confirmatory new filter',
 'results':subgroups},sort_keys=True,indent=2)+'\n')

def fmt(value):
    return 'n/a' if value is None else f'{value:.2f}' if isinstance(value,(int,float)) else str(value)

def table(title,rows):
    out=['',title,'','| Arm | Trades | Gross USD | Fees USD | Slippage/spread USD | Net USD | Win % | PF | Expectancy USD | Minute-close DD USD |',
         '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name,m in rows:
        win=None if m.get('win_rate') is None else 100*m['win_rate']
        out.append('| '+' | '.join([name,str(m['trades']),fmt(m.get('gross')),fmt(m.get('fees')),
           fmt(m.get('slippage_spread',m.get('execution_cost'))),fmt(m['net']),fmt(win),fmt(m.get('profit_factor')),
           fmt(m.get('expectancy')),fmt(m.get('max_drawdown_mark_to_minute_close',0))])+' |')
    return out

lines=['# MNQ/MES quantitative validation — actual data, exploratory only','',
 'The new115sessions were acquired once within the approved$0.50. All120sessions are locally available. No result below approves paper/live trading: the complete point-in-time news calendar and tick-level execution remain unverified.','',
 '## Reproduce offline','',
 '```sh',"'/Users/locoframe/Desktop/TRADING BOT/run-validation.sh'",'```','',
 'The command reads validated local CSV/cache only; no credentials, downloads or broker orders. It preserves the frozen selection and fails if protocol/data/selection identity changes. The previously verified five-day simulation remains `run-simulation.sh`.','',
 '## Dataset and scope','',
 f"- {d['rows']} actual1minute bars,120cash sessions May5–October23,2026. The115new daily queries each contained both actual MNQ/MES contracts; original five sessions were cache hits, not downloaded again.",
 f"- Fresh official preflight ${q['total_cost_usd']}; actual completed-query reserved estimate ${d['estimated_reserved_usd']}, cap$0.50. Client-side estimate, not an independently checked invoice/vendor hard spending limit.",
 '- Original multi-contract DBN bytes are retained in `data/databento/bulk120`, with durable per-query attempted/completed ledger, checksums and contract/publisher/time-grid/volume/OHLC validation before normalization. `data-quality120.json` records each cash day. No missing bars are fabricated.',
 '- Selection uses the provider previous-day-volume rule, resolved into explicit contract IDs/raw symbols. No contemporaneous full-day volume was used. Vendor publication latency and historical correction lineage are not independently attested.',
 '- Raw data is not redistributed. `bars120.csv` retains original integer UNIXns. `quote115.json` contains actual rollover intervals and daily availability conditions.','',
 '## Frozen method and limits','',
 '- Threshold±2.5, rolling residual standard deviation20(ddof0), cash typical-price VWAP anchor09:30, original MES4/2point and MNQ15/8point target/stop. Signals at completed bars; following-open fills with assumed zero extra feed latency. Stops first if target and stop touch the same bar; adverse gap stop fills, no favorable gap target improvement.',
 '- Primary four arms use independent per-instrument virtual accounts and the original persistent global drawdown kill. The original combined portfolio (one position total, MNQ-first tie priority) is shown separately. It is not valid to add independent-arm drawdowns or claim they are the same shared-risk portfolio.',
 '- VWAP variant preserves the earlier registered rule: freeze signal-time VWAP rounded to a quarter tick, not a moving VWAP target. It is evaluated separately, never substituted retrospectively for a better result.',
 '- Fee scenario: broker$0.25+exchange$0.35per side; NFA$0.02per side throughJune30 and$0.01fromJuly1,2026. Slippage1tick entry+1tick exit, spread0assumption; stresses1.5x/2x rerun risk gates, not just subtract costs afterwards. These are public schedule assumptions, not verified account statements.',
 '- News OFF is explicitly exploratory. No revised economic value was used as ex-ante data. Strict mode actually processed the full dataset and opened zero trades because complete certifiedPITnews is absent.',
 '- Training threshold for low/high volatility uses only the first20calibration sessions; earlier trades are calibration_unclassified. Regime labels use causal20bar volatility at signal, never whole-day future realized volatility. Predeclared time buckets are09:45–11:30,11:30–13:30,13:30–15:30NY.',
 '- No threshold/time/regime filter was selected from the test outcomes. `preregistered-protocol.json` was frozen before new acquisition/return inspection; statisticalamendment01(before returns) uses conservative family16 one-sided bounds, seed1729,5000circular5session block bootstrap replicates. Subgroups are descriptive, not new significant strategies.','']
lines+=table('## Original continuous protected accounts — all120sessions',list(r['primary_continuous_account'].items()))
portfolio=r['original_portfolio_fixed_reference']
lines+=table('### Original shared-risk portfolio reference',[('Combined fixed-target portfolio',portfolio)])
lines+=['','Global drawdown kills are not reset inside these continuous runs. Zero-trade sessions after a kill remain in daily results.']
for name,m in r['primary_continuous_account'].items():
 lines.append(f"- {name}: global halt={m['global_halt_latched']}, last trade={m['last_trade_date']}, sessions with nonzero realized PnL={m['sessions_with_trades']}.")
lines+=table('## Independent-session diagnostic — explicit account-reset rule change',list(r['daily_independent_diagnostic_rule_change'].items()))
lines+=['','This diagnostic resets the virtual account at each session to inspect signal/cost economics across all market dates. It is NOT the original persistent account and cannot replace its baseline or be selected using test results. Its aggregate drawdown can exceed the original global cap.']
lines+=table('## Walk-forward — disjoint50test sessions',[(k,v['metrics']) for k,v in r['walk_forward'].items()])
lines+=['','Each fold:20calibration/10validation/10test; five folds. Fixed/VWAP selection uses validation-only net and chooses NO_TRADE if both lose. A fresh virtual account starts at each evaluation fold; this is explicitly separate from the120session persistent run.','',
 '### Validation-only final choices']
for sym,choice in r['selection']['final_selected'].items():lines.append(f"- {sym}: {choice}; aggregate validation scores {r['selection']['final_validation_aggregate'][sym]}.")
lines+=table('## Temporal holdout —30sessions',[(k,v['metrics']) for k,v in r['holdout'].items()])
lines+=['',f"Holdout {proto['holdout'][0]} through {proto['holdout'][-1]}; selected policy frozen before holdout was unlocked. The five inspected October19–23dates are excluded. The project has not supplied an external human attestation that this holdout was never seen elsewhere. Reproduction reruns do not authorize parameter retuning.",'',
 '### Conditional out-of-sample uncertainty','',
 '| Stage / arm | Mean daily net | Mean95%CI | Simultaneous one-sided lower mean | Positive conditional bound |',
 '|---|---:|---|---:|---|']
for stage,arms in [('WF',r['walk_forward']),('Holdout',r['holdout'])]:
 for name,item in arms.items():
  u=item['uncertainty'];lines.append(f"| {stage}/{name} | {fmt(u.get('mean_daily_net'))} | {u.get('mean_ci95')} | {fmt(u.get('simultaneous_lower_mean'))} | {u['positive_edge_supported']} |")
lines+=['','These approximate moving-block intervals are conditional on this sample, risk rule, costs and exploratory news-OFF mode. They are not proof against nonstationarity, calendar errors, selection reuse, or unknown intrabar fills.','',
 '## Cost sensitivity','',
 '| Arm / slippage multiplier | Trades | Gross | Fees | Execution | Net |','|---|---:|---:|---:|---:|---:|']
for name,m in r['cost_stress'].items():lines.append(f"| {name} | {m['trades']} | {fmt(m['gross'])} | {fmt(m['fees'])} | {fmt(m['execution_cost'])} | {fmt(m['net'])} |")
lines+=['','### Cost break-even arithmetic (not an estimated win probability)','',
 '| Fee period | Instrument | Gross target/stop USD | Roundtrip fees+slippage USD | Required TP win rate | Minimum quarter-tick profitable target distance |',
 '|---|---|---|---:|---:|---:|']
for period,reg in [('May-June',.02),('July-October',.01)]:
 for symbol,point,tp,sl in [('MES',5.,4.,2.),('MNQ',2.,15.,8.)]:
  import math
  friction=2*(.25+.35+reg)+2*.25*point
  probability=(sl*point+friction)/((tp+sl)*point)
  minimum=(math.floor((friction/point)/.25)+1)*.25
  lines.append(f'| {period} | {symbol} | {tp*point}/{sl*point} | {friction:.2f} | {100*probability:.4f}% | {minimum}points |')
lines+=['','This algebra assumes only exact fixed-target/stop outcomes, no gap/time/risk exits, baseline1tick slippage each side and spread0. It is NOT a forecast. The VWAP variant can hit a small gross-profit target yet lose net if its target distance does not cover friction. No cost-aware entry filter was fitted or added after seeing test results.']
lines+=['','### Attribution and loss categories','',
 'Categories below use the independent-session diagnostic to avoid hiding later regimes behind an early global kill. Never sum overlapping time/regime/side categories together. No category becomes a trading filter merely because it looks better.',
 'Ambiguous bracket counts: MESfixed23/633, MESVWAP3/500, MNQfixed75/627, MNQVWAP2/452 in the daily-independent diagnostic. Stop-first remains the only realized simulation assumption; these are not resolved tick outcomes.']
for name,m in r['daily_independent_diagnostic_rule_change'].items():
 lines+=['',f'#### {name}',f"Gross {fmt(m['gross'])}; broker commissions {fmt(m['commissions_broker'])}; exchange {fmt(m['exchange_fees'])}; regulatory {fmt(m['regulatory_fees'])}; slippage/spread {fmt(m['execution_cost'])}; net {fmt(m['net'])}. Gross-positive/net-negative trades: {m['gross_positive_net_negative']}."]
 for label,values in [('Time',m['time_buckets']),('Volatility',m['volatility_regimes']),('Side',m['sides']),('Exit',m['exits'])]:
  for k,v in sorted(values.items(),key=lambda x:x[1]['net']):
   lines.append(f"- {label}/{k}: {v['trades']}trades, gross{fmt(v['gross'])}, fees{fmt(v['fees'])}, execution{fmt(v['slippage_spread'])}, net{fmt(v['net'])}, expectancy{fmt(v['expectancy'])},PF{fmt(v['profit_factor'])}.")
lines+=['','### Paired MNQ versus MES','']
for name,v in r['paired_instruments'].items():
 u=v['MES_minus_MNQ_daily_usd'];lines.append(f"- {name}, MES-minus-MNQ daily USD mean {fmt(u['mean_daily_net'])},95%CI{u['mean_ci95']}, simultaneous lower{fmt(u['simultaneous_lower_mean'])}. Relative differences are NOT evidence either instrument has positive absolute net edge; one-contract risk differs (MES stop$10,MNQstop$16). NetR is reported in JSON.")
supported=[]
for name in r['primary_continuous_account']:
 if r['walk_forward'][name]['uncertainty']['positive_edge_supported'] and r['holdout'][name]['uncertainty']['positive_edge_supported']:supported.append(name)
for name,v in r['paired_instruments'].items():
 for stage in ('walk_forward_paired','holdout_paired'):
  u=v[stage];lines.append(f"- OOS {stage}/{name}: MES-minus-MNQ mean{fmt(u['mean_daily_net'])},95%CI{u['mean_ci95']}, multiplicity-adjusted lower{fmt(u['simultaneous_lower_mean'])}; positive relative difference supported={u['positive_relative_difference_supported']}.")
lines+=['','### A positive subgroup is not a validated filter','']
for stage in ('walkforward','holdout'):
 item=subgroups['MNQ/fixed/'+stage]['regime']['low'];u=item['uncertainty_exploratory_family72']
 lines.append(f"- MNQ fixed/low-volatility {stage}: {item['trades']}trades, net{fmt(item['net'])}, mean daily95%CI{u['mean_ci95']}, exploratory multiplicity-adjusted lower{fmt(u['simultaneous_lower_mean'])}.")
lines+=['The positive point estimates do not establish a robust condition-specific edge. No low-volatility filter was fitted after seeing these results; any such proposal needs new preregistration and untouched evaluation. All120sessions, including this holdout, have now been economically inspected: the same holdout cannot be relabeled untouched for a new rule. Any further data acquisition needs a new explicit scope/budget authorization.','']
lines+=['','## Strategy assessment','',
 f"Arms with positive multiplicity-adjusted lower daily mean in BOTH frozen WF and temporal holdout: {supported or 'none'}.",
 'No certified tradable edge is established. Even a positive exploratory subgroup/result is insufficient to approve autonomous paper/live trading while the calendar/execution/account-cost evidence is incomplete. Negative net after fees/slippage must not be replaced with gross profitability. No live order route was implemented or enabled.','',
 '## More-granular data — quotes only','',
 '| Scope | Schema | Official USD | Records | Billable uncompressed bytes |','|---|---|---:|---:|---:|']
for v in g['quotes']:
 m=v['official_metrics'];lines.append(f"| {v['purpose']} | {v['request']['schema']} | {m['get_cost']} | {m['get_record_count']} | {m['get_billable_size']} |")
if (P/'granular-mnq-quote.json').exists():
 mnq_quote=json.loads((P/'granular-mnq-quote.json').read_text())
 for item in mnq_quote['quotes']:
  met=item['official_metrics'];lines.append(f"| MNQ calibration ambiguous-bracket10minute slice | {item['request']['schema']} | {met['get_cost']} | {met['get_record_count']} | {met['get_billable_size']} |")
lines+=['',f"Quotes checked {g['checked_at']}; refresh and obtain separate explicit approval before any acquisition. None was downloaded. One-second bars still cannot resolve subsecond ordering. Trades+BBO for the known10minuteMEScollision slice are a focused next execution test, not a representative financial validation of120days.",'',
 '## Remaining blockers before autonomous paper trading','',
 '- Complete versioned CPI/NFP/FOMC/other configured event evidence with pre-session known_at/revision lineage. FOMC tentative schedule is verifiable from a dated2024FederalReserve release; current BLS pages alone do not complete the PIT audit. Strict mode remains blocked.',
 '- Account-specific dated transaction fees, spread/latency/slippage estimates from suitably granular data, conservative fill validation, and enough untouched evidence after any new rule selection.',
 '- Authenticated broker paper session/permissions, native bracket/OCO/partial/reject/reconnect/restart reconciliation and continuously authorized data/news watchdog. No real orders or withdrawals.',
 '- Timestral remains optional/off. ModifiedMIT model eligibility under company/employer revenue conditions is unknown; no false legal attestation or synthetic AI economic results. Existing Timestral code is unchanged.','',
 '## Evidence','',
 '`quote115.json`, `preflight-responses.json`, `data-quality120.json`, `preregistered-protocol.json`, `protocol-amendment-01.json`, `validation-only-selection.json`, `holdout-access.json`, `quant-results.json`, `results/`, `news-pit-assessment.json`, `granular-quote.json`, `tests-local.txt`.','']
(P/'QUANTITATIVE-REPORT.md').write_text('\n'.join(lines))
print(json.dumps({'report':str(P/'QUANTITATIVE-REPORT.md'),'jointly_positive_conditional_arms':supported}))
