"""Bounded, offline strategy research on already observed data. Never independent OOS."""
import argparse
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import numpy as np

from mnq_data.core import digest, file_hash
from mnq_timestral.schema import NY
from databento_planner.cache import atomic_json
from .engine import Config, summarize
from .quant import QuantReplay, read_bars, trade_stats, bucket
from .strategies import StrategyConfig, StrategyReplay
from .__main__ import write_rows

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/research-v2'
V1=ROOT/'reports/archive/vwap-v1-manifest.json'
DATA=ROOT/'reports/quant-validation/bars120.csv'
KINDS=('vwap_v1_fixed','orb','sweep_mss')
SOURCE_PATHS=('src/mnq_sim/strategies.py','src/mnq_sim/research_v2.py','run-research-v2.sh','tests_sim/test_strategies_v2.py','tests_sim/test_research_v2.py')


def verify_manifest(root,manifest):
    for name,expected in manifest['files'].items():
        if file_hash(root/name)!=expected:raise ValueError('Frozen V1 changed: '+name)
    return len(manifest['files'])


def prior_regimes(widths,lookback=20):
    result={};days=sorted(widths)
    for i,day in enumerate(days):
        threshold=float(np.median([widths[d] for d in days[i-lookback:i]])) if i>=lookback else None
        result[day]={'label':'unclassified' if threshold is None else 'high' if widths[day]>=threshold else 'low',
                     'threshold':threshold,'known_through':days[i-1] if i else None,
                     'opening_range_fraction':widths[day]}
    return result


def robust_intervals(values,replicates=5000,family=6):
    x=np.asarray(values,dtype=float);n=len(x)
    if n<30 or not np.isfinite(x).all():raise ValueError('At least30 finite sessions required')
    result={}
    for length in (1,5,10):
        rng=np.random.default_rng(1729)
        starts=rng.integers(0,n,(replicates,(n+length-1)//length))
        indices=((starts[:,:,None]+np.arange(length))%n).reshape(replicates,-1)[:,:n]
        means=x[indices].mean(axis=1)
        result[str(length)]={'mean_daily_net':float(x.mean()),'ci95':[float(np.quantile(means,.025)),float(np.quantile(means,.975))],
          'lower_family_adjusted':float(np.quantile(means,.05/family)),'family':family,'replicates':replicates,'seed':1729}
    return {'independent_evidence':False,'method':'Circular moving-block session bootstrap; conditional on observed sample and approximate dependence',
            'by_block_length':result}


def freeze():
    manifest=json.loads(V1.read_text());verify_manifest(ROOT,manifest)
    protocol={'version':2,'frozen_at':datetime.now(timezone.utc).isoformat(),
      'v1_manifest_sha256':file_hash(V1),'dataset_sha256':manifest['dataset_sha256'],
      'source_sha256':{p:file_hash(ROOT/p) for p in SOURCE_PATHS},
      'data_status':'ALL120_SESSIONS_PREVIOUSLY_OBSERVED_EXPLORATORY_ONLY',
      'parameter_search':False,'baseline':'VWAP/Z-score2.5 fixed TP/SL, frozen V1 engine; signal-time VWAP-target arm remains archived',
      'strategies':{k:asdict(StrategyConfig(k)) for k in ('orb','sweep_mss')},
      'common_config':asdict(Config(news_required=False)),
      'orb':'15bars09:30–09:45NY; first later close >= rangehigh+0.25 long or <= rangelow-0.25 short; one candidate per side/day, even if risk rejects it',
      'sweep_mss':'Strict2left2right pivot, usable only after rightbars close. Sweep previously confirmed low by>=0.25 and close back above (long), symmetric high(short). Freeze opposite confirmed pivot. A strictly later bar within10bars must close>=0.25 past opposite level. Cancel if extreme exceeded or timeout. Consume each pivot on its first breach, even without reclaim. Dual sweep or already-through-structure samebar rejected. No volume/book liquidity claim.',
      'execution':'Next available minute open only, same original fixed target/stop distances: MES4/2points MNQ15/8points; adverse stop-gap fill and stop-first collision. One contract/account, flatten15:30NY, entry09:45–15:30exclusive. No pyramiding.',
      'risk':'Original daily200USD, global500USD drawdown,10trades/day,3consecutive losses; same for every arm. Different stop-dollar risk MNQ16 vs MES10; also report netR.',
      'accounts':{'continuous':'Original persistent global risk; primary operational comparison',
                  'daily_reset_diagnostic':'Fresh10000USD virtual account each session; keeps intraday risk but removes cross-session global halt. NOT a deployable portfolio or unchanged baseline.'},
      'costs':'Broker0.25+exchange0.35 per side scenario; NFA0.02throughJune30 then0.01; entry and exit1tick each, zero spread assumption. Not account-specific fees.',
      'stress_ticks_each_side':[1.0,1.5,2.0],
      'robustness':'6instrument/strategy arms; bootstrap5000seed1729 blocks1/5/10, one-sided family6adjustment; 6consecutive20session blocks, calendar months, timebuckets, lagged20session opening-range-volatility median. Subgroups descriptive, no filter selection.',
      'news':'OFF_EXPLORATORY; strict mode must block because complete PITcalendar uncertified',
      'sources':[
       {'url':'https://onlinelibrary.wiley.com/doi/10.1002/9781119203933.ch11','support':'General opening-range breakout concept only; our exact15minute/fixed-risk rule is a research choice'},
       {'url':'https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/pivot-points-high-low','support':'Pivots require bars on both sides; right-side confirmation must be delayed'},
       {'url':'https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/learning-center/Idenitfying-Chart-Patterns.pdf','support':'False/failed breakout concepts only; our sweep/MSS state machine is a price-only operational hypothesis'}],
      'ict_archive':'No ICT2022archive found in project (excluding environments/rawdata); no ICT provenance claimed',
      'future_independent':{
       'candidates':['MNQ/orb','MES/orb','MNQ/sweep_mss','MES/sweep_mss'],
       'parameters':'Exactly frozen strategy/common_config above. No winner selection or refit from these120sessions.',
       'period':'First60 complete XNYS cash sessions strictly after2026-10-26; collect sequentially only after separate price/scope authorization, never inspect before freeze.',
       'regimes':'Separate replication on an earlier disjoint year/regime only after manifest/provenance confirms never observed; do not silently substitute an already viewed period.',
       'promotion':{'independent_sessions':60,'minimum_trades':60,'net_positive':True,'profit_factor_min':1.15,
                    'family4_one_sided95_lower_daily_mean_above':0,'cost_1_5ticks_each_side_net_positive':True,
                    'positive_20session_blocks_min':2,'global_risk_halt_allowed':False,
                    'strict_news_and_finer_execution_required_before_paper':True},
       'procedure':'Immutable raw/normalized checksums and PITcontract/news audit before one locked run. Four candidates including failures, Bonferroni4 block5CI; block1/10 sensitivity. Baseline descriptive. No early economic peeking or extension after failure. Any change resets experiment on new unseen data.',
       'purchase':'Not authorized. One official metadata.get_cost quote for exact missing point-in-time contracts/schema/cash scopes, exclude cache, then manual approval. One-minute screening first; matched1s/trades/MBP1 for execution only later with separate approval.'},
      'timestral':'Optional disabled; real checkpoints blocked pending modifiedMIT revenue-eligibility attestation; no financial predictive claim',
      'lean':'No live/broker adapter activation. Stable replay remains simulation; LEAN native execution/reconciliation certification pending'}
    path=OUT/'protocol.json'
    if path.exists():raise ValueError('Protocol already frozen; never overwrite it')
    atomic_json(path,protocol)
    print('Frozen V2 protocol',file_hash(path))


def execute(bars,config,kind,spec):
    replay=QuantReplay(bars,config) if kind=='vwap_v1_fixed' else StrategyReplay(bars,config,spec)
    result=replay.run()
    return result,replay.global_halt


def combined_daily(groups,days,symbol,config,kind,spec):
    result={k:[] for k in ('trades','decisions','orders','equity','risk_events')};realized=0.;peak=0.
    for day in days:
        part,_=execute(groups[day,symbol],config,kind,spec)
        for trade in part['trades']:trade['id']=day+'-'+trade['id']
        for order in part['orders']:
            for key in ('id','parent_id','oco_group'):
                if key in order:order[key]=day+'-'+order[key]
        for point in part['equity']:
            pnl=realized+point['net_pnl'];peak=max(peak,pnl)
            point.update(equity=config.virtual_capital+pnl,net_pnl=pnl,drawdown=peak-pnl)
        realized+=sum(t['net'] for t in part['trades'])
        for key in result:result[key].extend(part[key])
    return result,False


def describe(result,days,regimes,halt):
    trades=result['trades'];daily={d:sum(t['net'] for t in trades if t['entry_at'][:10]==d) for d in days}
    metrics={**summarize(result),**trade_stats(trades),'global_halt_latched':halt,'daily_net':daily}
    metrics['uncertainty']=robust_intervals(list(daily.values()))
    metrics['temporal_blocks']=[{'dates':[days[i],days[min(i+19,len(days)-1)]],
        **trade_stats([t for t in trades if t['entry_at'][:10] in days[i:i+20]])} for i in range(0,len(days),20)]
    metrics['by_month']={m:trade_stats([t for t in trades if t['entry_at'].startswith(m)]) for m in sorted({d[:7] for d in days})}
    metrics['by_regime']={r:trade_stats([t for t in trades if regimes[t['entry_at'][:10]]['label']==r]) for r in ('unclassified','low','high')}
    metrics['by_time']={b:trade_stats([t for t in trades if bucket(t['entry_at'])==b]) for b in ('morning','midday','afternoon')}
    metrics['by_side']={str(s):trade_stats([t for t in trades if t['side']==s]) for s in (-1,1)}
    metrics['ambiguity_bound_note']='Stop-first actual result; excluding ambiguous trades below is descriptive and selection-biased, not a tradable alternative'
    metrics['excluding_ambiguous_descriptive']=trade_stats([t for t in trades if not t['intrabar_ambiguous']])
    return metrics


def run():
    protocol=json.loads((OUT/'protocol.json').read_text())
    if file_hash(V1)!=protocol['v1_manifest_sha256']:raise ValueError('V1 manifest changed')
    count=verify_manifest(ROOT,json.loads(V1.read_text()))
    for p,h in protocol['source_sha256'].items():
        if file_hash(ROOT/p)!=h:raise ValueError('Frozen research source changed: '+p)
    if file_hash(DATA)!=protocol['dataset_sha256']:raise ValueError('Dataset changed')
    bars=read_bars(DATA);groups=defaultdict(list)
    for bar in bars:groups[bar.start.astimezone(NY).date().isoformat(),bar.symbol].append(bar)
    days=sorted({key[0] for key in groups})
    if len(days)!=120 or len(bars)!=93600:raise ValueError('Expected complete120session dataset')
    regimes={}
    for symbol in ('MNQ','MES'):
        widths={}
        for day in days:
            bb=groups[day,symbol]
            if len(bb)!=390:raise ValueError('Incomplete cash session')
            opening=bb[:15];widths[day]=(max(b.high for b in opening)-min(b.low for b in opening))/opening[-1].close
        regimes[symbol]=prior_regimes(widths)
    atomic_json(OUT/'causal-regimes.json',regimes)
    results={};strict={}
    for symbol in ('MNQ','MES'):
        for kind in KINDS:
            spec=StrategyConfig(**protocol['strategies'][kind]) if kind!='vwap_v1_fixed' else None
            subset=[b for day in days for b in groups[day,symbol]]
            for account in ('continuous','daily_reset_diagnostic'):
                for ticks in protocol['stress_ticks_each_side']:
                    config=replace(Config(**protocol['common_config']),entry_slippage_ticks=ticks,exit_slippage_ticks=ticks)
                    result,halt=execute(subset,config,kind,spec) if account=='continuous' else combined_daily(groups,days,symbol,config,kind,spec)
                    name=f'{symbol}/{kind}/{account}/ticks{ticks}'
                    results[name]=describe(result,days,regimes[symbol],halt)
                    folder=OUT/'results'/name;folder.mkdir(parents=True,exist_ok=True)
                    atomic_json(folder/'summary.json',results[name]);write_rows(folder/'trades.csv',result['trades'])
                    if ticks==1.:
                        for log in ('decisions','orders','equity','risk_events'):write_rows(folder/(log+'.csv'),result[log])
                    print(name,'trades',results[name]['trades'],'net',round(results[name]['net'],2),flush=True)
            if kind!='vwap_v1_fixed':
                blocked,_=execute(subset,replace(Config(**protocol['common_config']),news_required=True),kind,spec)
                if blocked['trades']:raise ValueError('Strict news gate bypass')
                strict[symbol+'/'+kind]={'trades':0,'decisions':len(blocked['decisions']),'status':'blocked_uncertified_news'}
    paired={}
    for symbol in ('MNQ','MES'):
        baseline=results[f'{symbol}/vwap_v1_fixed/daily_reset_diagnostic/ticks1.0']['daily_net']
        for kind in ('orb','sweep_mss'):
            candidate=results[f'{symbol}/{kind}/daily_reset_diagnostic/ticks1.0']['daily_net']
            paired[symbol+'/'+kind]=robust_intervals([candidate[d]-baseline[d] for d in days])
    output={'status':'EXPLORATORY_NO_INDEPENDENT_VALIDATION','protocol_sha256':file_hash(OUT/'protocol.json'),
        'dataset_sha256':file_hash(DATA),'sessions':len(days),'bars':len(bars),'results':results,'paired_daily_delta_vs_vwap':paired,
        'strict_news':strict,'protected_v1_files_verified':count,'new_paid_requests':0,'broker_connections':0,'timestral_enabled':False}
    atomic_json(OUT/'results.json',output)
    atomic_json(OUT/'future-independent-test.json',{'protocol_sha256':output['protocol_sha256'],**protocol['future_independent']})
    report(output)
    verify_manifest(ROOT,json.loads(V1.read_text()))


def report(output):
    lines=['# Strategy research V2 — observed-sample exploration','',
      'All120sessions were already observed. No result here is independent out-of-sample evidence. News filter OFF; strict mode blocked. Fixed exits intentionally isolate candidate generators, not all possible ORB/sweep implementations. No parameter optimization.','',
      '## Comparable net results','',
      '|Instrument|Strategy|Account|Trades|Gross USD|Fees USD|Slip USD|Net USD|PF|Expectancy USD|DD USD|Ambiguous|',
      '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name,m in output['results'].items():
        if not name.endswith('ticks1.0'):continue
        symbol,kind,account,_=name.split('/');pf=f"{m['profit_factor']:.3f}" if m['profit_factor'] is not None else 'n/a'
        ex=f"{m['expectancy']:.2f}" if m['expectancy'] is not None else 'n/a'
        lines.append(f"|{symbol}|{kind}|{account}|{m['trades']}|{m['gross']:.2f}|{m['fees']:.2f}|{m['slippage_spread']:.2f}|{m['net']:.2f}|{pf}|{ex}|{m['max_drawdown_mark_to_minute_close']:.2f}|{m['ambiguous_intrabar']}|")
    lines+=['','## Robustness (daily-reset diagnostic, not deployable portfolio)','',
      '|Arm|Positive20session blocks /6|1.5tick net|2tick net|Mean daily95%CI block5|Adjusted lower block1/5/10|',
      '|---|---:|---:|---:|---|---|']
    for symbol in ('MNQ','MES'):
        for kind in KINDS:
            prefix=f'{symbol}/{kind}/daily_reset_diagnostic/ticks';m=output['results'][prefix+'1.0']
            positive=sum(b['net']>0 for b in m['temporal_blocks']);ci=m['uncertainty']['by_block_length']['5']['ci95']
            lower=[round(m['uncertainty']['by_block_length'][str(k)]['lower_family_adjusted'],3) for k in (1,5,10)]
            lines.append(f"|{symbol}/{kind}|{positive}|{output['results'][prefix+'1.5']['net']:.2f}|{output['results'][prefix+'2.0']['net']:.2f}|{[round(v,3) for v in ci]}|{lower}|")
    lines+=['','## Interpretation and limitations','',
      'Daily reset removes cross-day global halt ONLY for descriptive signal coverage; continuous accounts retain original protection. One contract per arm means unequal dollar stops (MNQ$16 / MES$10); netR is also supplied. Minute-close drawdown understates possible tick-level excursions. Stop-first handles collisions conservatively; trade count/ambiguity are explicit. Costs are scenarios, not actual broker statements. Bootstrap cannot repair strategy-design selection bias on observed data; subgroup results are not independently tested filters.','',
      'Full session/month/regime/time/side breakdowns, paired differences and cost replays are in results.json; detailed orders, signals, brackets, trades and equity in results/. No evidence licenses live or autonomous paper trading.','',
      '## Frozen next test and data plan','',
      'future-independent-test.json freezes all four new instrument-strategy candidates and60prospective full cash sessions after2026-10-26. No purchases authorized. Require official exact-scope cost quote and cache exclusion before manual acquisition approval. A disjoint earlier-year replication needs proof it has never been inspected. If any definition changes, a new unseen test is required.','',
      '## Operational blockers','',
      'Complete point-in-time macro/news archive remains uncertified: strict mode blocks all four new arms. Timestral stays disabled; modifiedMIT revenue eligibility is not attested, so no weights/inference claim. LEAN runtime/native fills, broker paper adapter, reconnect/reconciliation and tick-level execution validation remain pending; no account or live connection was added.','',
      '## Definitions and sources','',
      'No ICT2022archive found locally. Sweep/MSS is our price-only hypothesis, not an attributed ICT implementation or proof of real liquidity. Our exact parameters/fixed exits are research choices, not claims made by these sources:',
      '- [Bulkowski opening-range breakout chapter](https://onlinelibrary.wiley.com/doi/10.1002/9781119203933.ch11): general range breakout concept.',
      '- [Fidelity pivot highs/lows](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/pivot-points-high-low): bars on both sides; implemented with delayed confirmation.',
      '- [Fidelity false/failed breakouts](https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/learning-center/Idenitfying-Chart-Patterns.pdf): conceptual failed breakout; our exact state machine is defined in protocol.json.','',
      '## Reproduce','',
      '```sh','cd "/Users/locoframe/Desktop/TRADING BOT"','./run-research-v2.sh','./run-research-v2.sh --tests','```','',
      'V1 recoverable snapshot: reports/archive/vwap-v1.tar.gz with per-file and archive SHA256 in vwap-v1-manifest.json. Sources, old reports, configs, raw cache and normalized dataset included. Runtime environment is pinned by archived locks, not bundled virtual environments.']
    (OUT/'RESEARCH-REPORT.md').write_text('\n'.join(lines)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');args=parser.parse_args()
    # Strong default boundary: even accidental connector calls cannot connect.
    def denied(*_args,**_kwargs):raise RuntimeError('Offline research: network disabled')
    socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
    if args.freeze:freeze()
    else:run()


if __name__=='__main__':main()
