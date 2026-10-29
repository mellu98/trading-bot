"""Independent arithmetic/provenance checks; no strategy selection or purchases."""
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import math

from mnq_data.core import file_hash
from mnq_sim.research_v2 import ROOT, OUT, DATA, V1, verify_manifest
from mnq_sim.quant import read_bars
from databento_planner.cli import baseline_check


def near(a,b):
    if not math.isclose(a,b,abs_tol=1e-7,rel_tol=1e-10):raise AssertionError((a,b))


def verify():
    output=json.loads((OUT/'results.json').read_text());protocol=json.loads((OUT/'protocol.json').read_text())
    near(output['sessions'],120);near(output['bars'],93600)
    assert file_hash(OUT/'protocol.json')==output['protocol_sha256']
    manifest=json.loads(V1.read_text());count=verify_manifest(ROOT,manifest)
    assert file_hash(ROOT/manifest['archive'])==manifest['archive_sha256']
    bars=read_bars(DATA);by_start={(b.symbol,b.start.isoformat()):b for b in bars}
    by_end={(b.symbol,b.end.isoformat()):b for b in bars}
    checked=0;signals=0;collisions=0
    for name,metrics in output['results'].items():
        symbol,kind,account,stress=name.split('/');ticks=float(stress.removeprefix('ticks'))
        folder=OUT/'results'/name
        rows=list(csv.DictReader((folder/'trades.csv').open())) if (folder/'trades.csv').stat().st_size else []
        assert len(rows)==metrics['trades']
        sums={k:0. for k in ('gross','fees','net','execution_cost')}
        for t in rows:
            side=int(t['side']);pv=2 if symbol=='MNQ' else 5
            entry=float(t['raw_entry']);exit=float(t['raw_exit']);signal=datetime.fromisoformat(t['signal_at'])
            b=by_start[symbol,t['entry_at']]
            assert signal==b.start and datetime.fromisoformat(t['signal_bar_start'])+timedelta(minutes=1)==signal
            assert t['contract']==b.contract;near(entry,b.open)
            gross=side*(exit-entry)*pv
            fee=2*(.25+.35+(.02 if t['entry_at'][:10]<'2026-07-01' else .01))
            execution=.25*2*ticks*pv
            for key,value in [('gross',gross),('fees',fee),('execution_cost',execution),('net',gross-fee-execution)]:
                near(float(t[key]),value);sums[key]+=value
            target,stop=(15,8) if symbol=='MNQ' else (4,2)
            near(float(t['stop']),entry-side*stop);near(float(t['target']),entry+side*target)
            if t['exit_timestamp_is_bar_bound']=='True':
                exitbar=by_end[symbol,t['exit_at']]
                hitstop=exitbar.low<=float(t['stop']) if side==1 else exitbar.high>=float(t['stop'])
                hittarget=exitbar.high>=float(t['target']) if side==1 else exitbar.low<=float(t['target'])
                if hitstop and hittarget:
                    assert t['intrabar_ambiguous']=='True' and t['reason']=='stop';collisions+=1
                assert (t['intrabar_ambiguous']=='True')==(hitstop and hittarget)
            checked+=1
        for key in ('gross','fees','net'):near(sums[key],metrics[key])
        near(sums['execution_cost'],metrics['slippage_spread'])
        if ticks==1. and kind!='vwap_v1_fixed':
            seen=set()
            for decision in csv.DictReader((folder/'decisions.csv').open()):
                side=int(decision['side'])
                if not side:continue
                evidence=__import__('ast').literal_eval(decision['strategy_evidence'])
                assert evidence['known_at']==decision['at']
                if kind=='orb':
                    assert evidence['range_known_at']<decision['at']
                    key=(decision['at'][:10],side);assert key not in seen;seen.add(key)
                else:
                    assert evidence['pivot_confirmed_at']<evidence['sweep_at']<decision['at']
                signals+=1
    # Original fixed baseline must reproduce V1 exactly under both account rules.
    old=json.loads((ROOT/'reports/quant-validation/quant-results.json').read_text())
    # Check actual archived summaries rather than inferring an old JSON key layout.
    oldchecks=0
    for symbol in ('MNQ','MES'):
        for account,oldname in [('continuous',symbol+'-fixed-cost1.0'),('daily_reset_diagnostic',symbol+'-fixed-daily-independent')]:
            oldpath=ROOT/'reports/quant-validation/results'/oldname/'summary.json'
            previous=json.loads(oldpath.read_text());current=output['results'][f'{symbol}/vwap_v1_fixed/{account}/ticks1.0']
            for key in ('trades','net','gross','fees'):near(previous[key],current[key])
            oldchecks+=1
    evidence={'status':'pass','trade_rows_independently_recomputed':checked,'signal_time_checks':signals,
       'stop_first_collisions_checked_across_replays':collisions,'archived_v1_files_unchanged':count,
       'old_baseline_economic_comparisons':oldchecks,'original_protection':baseline_check(),
       'new_paid_requests':0,'real_orders':0,'independent_validation':False}
    (OUT/'verification.json').write_text(json.dumps(evidence,indent=2,sort_keys=True)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':verify()
