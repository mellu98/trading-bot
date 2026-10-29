"""One bounded exploratory cost stress on owned data. No parameter selection."""
from collections import defaultdict
from dataclasses import replace
from datetime import datetime,timezone
import csv,hashlib,json,socket
from pathlib import Path
from mnq_sim.engine import Config
from mnq_sim.quant import read_bars,trade_stats,fee_for_date
from mnq_sim.strategies import StrategyConfig
from mnq_sim.research_v2 import combined_daily,verify_manifest
from mnq_timestral.evaluation import POINT_VALUE

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):Path(p).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def deny(*a,**k):raise AssertionError('Network access forbidden in offline research')


def run():
    socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny
    protocol_path=OUT/'stress-protocol.json';protocol_hash=sha(protocol_path)
    protocol=json.loads(protocol_path.read_text());frozen_path=ROOT/'reports/research-v2/protocol.json'
    frozen=json.loads(frozen_path.read_text());baseline=json.loads((ROOT/'reports/research-v2/results.json').read_text())
    for name,expected in frozen['source_sha256'].items():assert sha(ROOT/name)==expected
    v1=json.loads((ROOT/'reports/archive/vwap-v1-manifest.json').read_text());protected=verify_manifest(ROOT,v1)
    data=ROOT/'reports/quant-validation/bars120.csv';assert sha(data)==protocol['dataset_sha256']==frozen['dataset_sha256']
    bars=read_bars(data);groups=defaultdict(list)
    for b in bars:groups[b.start.date().isoformat(),b.symbol].append(b)
    days=sorted({d for d,_ in groups});assert len(days)==120 and len(bars)==93600
    assert all(len(v)==390 for v in groups.values())
    cfg=protocol['single_stress_scenario'];results={};ledger={}
    folder=OUT/'stress-results';folder.mkdir(exist_ok=True)
    for symbol in ('MNQ','MES'):
        for kind in ('vwap_v1_fixed','orb','sweep_mss'):
            spec=None if kind=='vwap_v1_fixed' else StrategyConfig(**frozen['strategies'][kind])
            config=replace(Config(**frozen['common_config']),**{k:v for k,v in cfg.items() if k!='regulatory_per_side'})
            result,_=combined_daily(groups,days,symbol,config,kind,spec)
            trades=result['trades'];stats=trade_stats(trades);key=symbol+'/'+kind
            for t in trades:
                assert abs(t['gross']-t['fees']-t['execution_cost']-t['net'])<1e-8
                assert datetime.fromisoformat(t['signal_at'])<=datetime.fromisoformat(t['entry_at'])<=datetime.fromisoformat(t['exit_at'])
            stats.update(spread_cost_usd=len(trades)*.25*POINT_VALUE[symbol]*config.spread_ticks,
                slippage_cost_usd=len(trades)*.25*POINT_VALUE[symbol]*(config.entry_slippage_ticks+config.exit_slippage_ticks),
                daily_net={d:sum(t['net'] for t in trades if t['entry_at'][:10]==d) for d in days},
                policy='Daily-reset descriptive coverage only; not deployable portfolio or independent holdout')
            results[key]=stats
            with (folder/(symbol+'-'+kind+'-trades.csv')).open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(trades[0]) if trades else ['empty']);writer.writeheader();writer.writerows(trades)
            old=baseline['results'][key+'/daily_reset_diagnostic/ticks1.0']
            old_path=ROOT/'reports/research-v2/results'/symbol/kind/'daily_reset_diagnostic/ticks1.0/trades.csv'
            with old_path.open(newline='') as f:rows=list(csv.DictReader(f))
            assert len(rows)==old['trades']
            for t in rows:assert abs(float(t['gross'])-float(t['fees'])-float(t['execution_cost'])-float(t['net']))<1e-8
            n=len(rows);gross=sum(float(t['gross']) for t in rows);fees=sum(float(t['fees']) for t in rows)
            daily=[old['daily_net'][d] for d in days]
            ledger[key]={'trades':n,'gross':gross,'fees':fees,'net':old['net'],
                'net_without_any_slippage_or_spread_fixed_ledger':gross-fees,
                'gross_per_trade':gross/n if n else None,'break_even_all_in_cost_per_trade':gross/n if n else None,
                'positive_20session_blocks':sum(v['net']>0 for v in old['temporal_blocks']),
                'block5_daily_mean_ci95':old['uncertainty']['by_block_length']['5']['ci95'],
                'block5_family_adjusted_lower':old['uncertainty']['by_block_length']['5']['lower_family_adjusted'],
                'worst_5_daily_net':sum(sorted(daily)[:5]),'total_if_remove_best_5_days_descriptive_only':sum(daily)-sum(sorted(daily)[-5:]),
                'warning':'Removing costs or days is fixed-ledger descriptive arithmetic, NOT an executable rerun or tradable filter'}
            print(key,'stress trades',len(trades),'net',round(stats['net'],2),flush=True)
    assert sha(protocol_path)==protocol_hash
    assert sha(frozen_path)==json.loads((OUT/'before-sha256.json').read_text())['reports/research-v2/protocol.json']
    verify_manifest(ROOT,v1)
    output={'status':'EXPLORATORY_ALL_120_ALREADY_OBSERVED_NO_STRATEGY_PROMOTED','completed_at':datetime.now(timezone.utc).isoformat(),
        'stress_protocol_sha256':protocol_hash,'frozen_v2_protocol_sha256':sha(frozen_path),'dataset_sha256':sha(data),
        'sessions':len(days),'bars':len(bars),'v1_archive_files_verified':protected,'live_connections':0,'api_keys_loaded':0,
        'old_results_ledger_reconciliation':ledger,'one_predeclared_cost_stress':results,
        'empirical_spread_or_slippage_measured':False,'independent_holdout':False,'strict_news_certified':False}
    write(OUT/'research-verification.json',output)

if __name__=='__main__':run()
