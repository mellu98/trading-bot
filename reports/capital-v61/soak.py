"""Bounded real read-only runtime soak with a pause and a flat crash restart."""
import json,time,urllib.request,os,signal,subprocess,sqlite3,argparse
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/capital-v61'

def current():
    return json.load(urllib.request.urlopen('http://127.0.0.1:8767/api/status',timeout=3))
def pid():
    lines=subprocess.check_output(['ps','-eo','pid=,command='],text=True).splitlines()
    found=[int(line.split()[0]) for line in lines if line.strip().split(maxsplit=1)[-1].startswith(str(ROOT/'.venv/bin/python')+' -m mnq_local.capital_app app --mode signals_only')]
    assert len(found)==1
    return found[0]
def sample(v,elapsed):
    c=v.get('capital',{})
    return {'elapsed_s':elapsed,'at':v.get('updated_at'),'authenticated':v['authenticated'],'mode':v['mode'],'connection':v['connection'],'error':v['error'],
        'received':c.get('received'),'signals':c.get('signals'),'fresh':c.get('data_fresh'),'freshness':c.get('quote_freshness'),
        'positions':len(c.get('positions',[])),'orders':len(c.get('working_orders',[])),'halt':c.get('halt'),
        'opening_intents':sum(i.get('operation')=='open' for i in c.get('intents',{}).values()),'metrics':c.get('feed_metrics'),
        'quotes':c.get('quotes'),'continuous_orders_enabled':c.get('continuous_strategy_orders_enabled')}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seconds',type=float,default=660);a=ap.parse_args()
    t0=time.monotonic();rows=[];events=[];paused=False;crashed=False;child=None
    started=datetime.now(timezone.utc).isoformat()
    while time.monotonic()-t0<a.seconds:
        elapsed=time.monotonic()-t0
        try:
            v=current();row=sample(v,elapsed);rows.append(row)
            assert row['positions']==0 and row['orders']==0 and row['opening_intents']==1
            assert row['mode']=='signals_only' and row['continuous_orders_enabled'] is False
            if elapsed>=180 and not paused:
                p=pid();os.kill(p,signal.SIGSTOP);time.sleep(7);os.kill(p,signal.SIGCONT)
                events.append({'kind':'application_pause_7s_NOT_network_outage','elapsed_s':elapsed});paused=True
            if elapsed>=360 and not crashed:
                # Never interrupt a process with known exposure. This scope cannot open.
                assert v['authenticated'] and not v['capital']['positions'] and not v['capital']['working_orders']
                old=pid();os.kill(old,signal.SIGKILL);time.sleep(2)
                path=ROOT/'data/capital-v6/signals_only-EUR/state.sqlite'
                db=sqlite3.connect(path);integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
                cap=json.loads(db.execute('select body from snapshot where id=1').fetchone()[0])['capital'];db.close()
                assert integrity=='ok' and cap['technical_attempted'] and cap['halt']=='kill'
                with (OUT/'monitor.log').open('a') as log:
                    child=subprocess.Popen([str(ROOT/'run-capital-demo.sh'),'app','--mode','signals_only'],cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
                events.append({'kind':'SIGKILL_flat_restart','elapsed_s':elapsed,'sqlite_integrity':integrity,'entry_budget_preserved':True});crashed=True
        except (OSError,TimeoutError,ValueError) as e:
            events.append({'kind':'sample_unavailable','elapsed_s':elapsed,'error_type':type(e).__name__})
        (OUT/'soak-progress.json').write_text(json.dumps({'started_at':started,'duration_s':time.monotonic()-t0,'samples':len(rows),'events':events},indent=2))
        time.sleep(5)
    final=current();result={'started_at':started,'duration_s':time.monotonic()-t0,'sample_count':len(rows),'events':events,
        'final':sample(final,time.monotonic()-t0),'actual_order_test':'NOT_RUN: independent WS freshness gate failed',
        'network_cable_outage':'NOT_TESTED','actual_token_expiry':'NOT_EXERCISED: requests keep session alive',
        'flat_during_all_samples':all(not r['positions'] and not r['orders'] for r in rows),
        'no_duplicate_openings':all(r['opening_intents']==1 for r in rows),
        'fresh_snapshot_count':sum(r['fresh'] is True for r in rows)}
    (OUT/'soak-samples.json').write_text(json.dumps(rows,indent=2));(OUT/'soak-result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ('duration_s','sample_count','events','flat_during_all_samples','no_duplicate_openings','fresh_snapshot_count')}))
if __name__=='__main__':main()
