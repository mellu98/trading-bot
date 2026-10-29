"""One preregistered H1 research experiment; isolated from production sources."""
from collections import Counter,defaultdict
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import argparse,csv,hashlib,json,math,socket
import numpy as np
from mnq_sim.engine import Config,summarize
from mnq_sim.quant import read_bars,fee_for_date
from mnq_sim.strategies import StrategyReplay,StrategyConfig
from mnq_sim.research_v2 import execute,combined_daily,verify_manifest
from mnq_timestral.schema import NY
from mnq_timestral.evaluation import simulate_trade

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
DATA=ROOT/'reports/quant-validation/bars120.csv'

def hashed(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n')
def csvwrite(path,rows):
    rows=list(rows)
    with Path(path).open('w',newline='') as f:
        if rows:
            w=csv.DictWriter(f,fieldnames=sorted(set().union(*(r.keys() for r in rows))))
            w.writeheader();w.writerows(rows)

def atr20(history):
    if len(history)<21:return None
    bb=history[-21:]
    if len({b.start.astimezone(NY).date() for b in bb})!=1:return None
    if any(a.end!=b.start or a.contract!=b.contract for a,b in zip(bb,bb[1:])):return None
    return sum(max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)) for a,b in zip(bb,bb[1:]))/20

def stop_distance(atr):return math.ceil(1.5*atr/.25)*.25

def admit(distance,friction,day_pnl,peak,realized,quantity=1):
    risk=distance*2+friction
    if quantity!=1:return False,'quantity_not_one_micro'
    if not math.isfinite(risk) or distance<=0:return False,'invalid_stop'
    if risk>100+1e-9:return False,'initial_risk_cap_100'
    if risk>200+day_pnl+1e-9:return False,'remaining_daily_budget'
    if risk>500-max(0,peak-realized)+1e-9:return False,'remaining_drawdown_budget'
    return True,'admitted'

def first_candidate(at,side,atr_ready,used):
    local=at.astimezone(NY);day=local.date().isoformat()
    if side and atr_ready and (10,0)<=(local.hour,local.minute)<(15,0) and day not in used:
        used.add(day);return True
    return False

def exit_event(bar,p,deadline):
    side=p['side'];stop=p['stop'];target=p['target']
    gap=bar.open<=stop if side==1 else bar.open>=stop
    if gap:return 'stop',bar.open,False,True
    if deadline is not None and bar.start>=deadline:return 'time_exit',bar.open,False,True
    local=bar.start.astimezone(NY)
    if (local.hour,local.minute)>=(15,30):return 'session_close',bar.open,False,True
    hs=bar.low<=stop if side==1 else bar.high>=stop
    ht=bar.high>=target if side==1 else bar.low<=target
    if hs:return 'stop',stop,hs and ht,False
    if ht:return 'target',target,False,False
    return None

def excursion_bounds(t,bars):
    entry=datetime.fromisoformat(t['entry_at']);end=datetime.fromisoformat(t['exit_at'])
    bound=t['exit_timestamp_is_bar_bound'];side=t['side'];raw=t['raw_entry']
    complete=[b for b in bars if b.start>=entry and (b.end<end if bound else b.end<=end)]
    # End-bound stop/target: only open and execution are guaranteed before exit.
    exitbar=next((b for b in bars if b.end==end),None) if bound else None
    close_exit=bound and t['reason'] in ('risk_loss','end_of_data','session_close')
    prices=[raw,t['raw_exit']]+[v for b in complete for v in (b.high,b.low)]
    if exitbar is not None:prices.append(exitbar.open)
    possible=prices+([exitbar.high,exitbar.low] if exitbar is not None else [])
    if close_exit:prices=possible
    moves=[side*(x-raw)*2 for x in prices];poss=[side*(x-raw)*2 for x in possible]
    return {'mfe_guaranteed_usd':max(0,max(moves)),'mfe_possible_usd':max(0,max(poss)),
      'mae_guaranteed_usd':max(0,-min(moves)),'mae_possible_usd':max(0,-min(poss)),
      'excursion_censored':bool(exitbar is not None and not close_exit),
      'duration_min_minutes':max(0,(end-entry).total_seconds()/60-(1 if bound else 0)),
      'duration_max_minutes':(end-entry).total_seconds()/60}

class H1Replay(StrategyReplay):
    """Reuse frozen signals, admission authority, close ledger and risk latches.

    Override only research event loop because original engine has no bracket hook.
    A_matched and B are the same schedule, cap and risk; only exits differ.
    """
    def __init__(self,bars,config,spec,arm):
        super().__init__(bars,config,spec);self.arm=arm;self.used=set();self.candidates=[]

    def step(self,start,group):
        self.config=replace(self.config,regulatory_per_side=fee_for_date(start.date().isoformat()))
        date=start.astimezone(NY).date().isoformat()
        if date!=self.date:
            if self.position or self.pending:raise ValueError('Unsafe overnight')
            self.date=date;self.realized_day=0.;self.day_trades=0;self.consecutive=0;self.day_halt=False
        b=group['MNQ'];strategy=self.generators['MNQ'].strategy
        # Pending state was constructed only after previous bar closed.
        if self.pending:
            p=self.pending;self.pending=None
            if start<datetime.fromisoformat(p['signal_at']):raise ValueError('Lookahead entry')
            allowed,reason=self.entry_permission()
            friction=self.config.costs().fees+self.config.costs().execution_cost('MNQ')
            if allowed:allowed,reason=admit(p['distance'],friction,self.realized_day,self.peak,self.realized)
            self.candidates[p['candidate_index']].update(entry_accepted=allowed,entry_reason=reason)
            if allowed:
                side=p['side'];sl=p['distance'];tp=2*sl if self.arm=='B' else 15.
                order={'id':date+'-H1','type':'market','symbol':'MNQ','side':side,'quantity':1,'status':'filled','filled_at':start.isoformat()}
                self.orders.append(order)
                self.position={'id':order['id'],'symbol':'MNQ','contract':b.contract,'side':side,'quantity':1,
                  'entry_at':start.isoformat(),'raw_entry':b.open,'entry_fill':b.open+side*.25*self.config.entry_slippage_ticks,
                  'stop':b.open-side*sl,'target':b.open+side*tp,'signal_at':p['signal_at'],'signal_bar_start':p['signal_bar_start'],
                  'atr20_signal':p['atr'],'initial_stop_risk_usd':2*sl,'modeled_initial_all_in_risk_usd':2*sl+friction}
                self.day_trades+=1
        mark=0.
        if self.position:
            p=self.position;deadline=datetime.fromisoformat(p['entry_at'])+timedelta(minutes=5) if self.arm=='B' else None
            event=exit_event(b,p,deadline)
            if event:
                reason,price,ambiguous,at_open=event;self.close(b,price,reason,ambiguous,at_open)
            else:
                mark=p['side']*(b.close-p['raw_entry'])*2-self.config.costs().fees-self.config.costs().execution_cost('MNQ')
                if self.realized_day+mark<=-self.config.daily_max_loss or self.peak-self.realized-mark>=self.config.max_drawdown:
                    self.risk_events.append({'at':b.end.isoformat(),'reason':'unrealized_loss_limit','mark':mark})
                    self.day_halt=True
                    if self.peak-self.realized-mark>=self.config.max_drawdown:self.global_halt=True
                    self.close(b,b.close,'risk_loss');mark=0.
        equity=self.realized+mark;self.peak=max(self.peak,equity)
        self.equity.append({'at':b.end.isoformat(),'net_pnl':equity,'equity':self.config.virtual_capital+equity,'drawdown':self.peak-equity})
        side=strategy.on_bar(b);atr=atr20(strategy.history)
        if first_candidate(b.end,side,atr is not None,self.used):
            distance=stop_distance(atr) if self.arm=='B' else 8.
            allowed,reason=self.entry_permission()
            if allowed:allowed,reason=admit(distance,self.config.costs().fees+self.config.costs().execution_cost('MNQ'),self.realized_day,self.peak,self.realized)
            candidate={'date':date,'signal_at':b.end.isoformat(),'signal_bar_start':b.start.isoformat(),'side':side,'atr':atr,'distance':distance,
              'accepted':allowed,'reason':reason,**strategy.audit}
            self.candidates.append(candidate);self.decisions.append({'at':b.end.isoformat(),'symbol':'MNQ',**candidate})
            if allowed:self.pending={**candidate,'candidate_index':len(self.candidates)-1}

def distribution(values):
    x=np.array(values,dtype=float)
    return {} if not len(x) else {'min':float(x.min()),'mean':float(x.mean()),'max':float(x.max()),
      'quantiles':{str(q):float(np.quantile(x,q)) for q in (.01,.05,.25,.5,.75,.95,.99)}}

def uncertainty(values):
    x=np.asarray(values,dtype=float);n=len(x);out={}
    for length in (1,5,10):
        rng=np.random.default_rng(1729);starts=rng.integers(0,n,(10000,math.ceil(n/length)))
        ix=((starts[:,:,None]+np.arange(length))%n).reshape(10000,-1)[:,:n]
        means=x[ix].mean(axis=1)
        out[str(length)]={'mean_daily_usd':float(x.mean()),'ci95':np.quantile(means,[.025,.975]).tolist(),
          'lower_one_sided_family8_95':float(np.quantile(means,.05/8))}
    return {'independent_evidence':False,'family':8,'replicates':10000,'seed':1729,'blocks':out,
      'limitation':'Conditional observed-sample circular session blocks; halted-path zeros retained, not re-simulated portfolio risk under resampling'}

def analyze(result,bars,days,halt,candidates):
    trades=result['trades'];byday=defaultdict(list)
    for b in bars:byday[b.start.astimezone(NY).date().isoformat()].append(b)
    for t in trades:
        t.update(excursion_bounds(t,byday[datetime.fromisoformat(t['entry_at']).astimezone(NY).date().isoformat()]))
    sessions=[{'date':d,'trades':sum(datetime.fromisoformat(t['entry_at']).astimezone(NY).date().isoformat()==d for t in trades),
       'net':sum(t['net'] for t in trades if datetime.fromisoformat(t['entry_at']).astimezone(NY).date().isoformat()==d)} for d in days]
    streak=longest=0
    for t in trades:
        streak=streak+1 if t['net']<0 else 0;longest=max(longest,streak)
    m=summarize(result)
    m.update(global_halt_latched=halt,last_trade_at=trades[-1]['exit_at'] if trades else None,sessions=sessions,
      daily_net={x['date']:x['net'] for x in sessions},net_distribution_usd=distribution([t['net'] for t in trades]),
      losing_trade_net_distribution_usd=distribution([t['net'] for t in trades if t['net']<0]),
      maximum_loss_streak_across_sessions_descriptive=longest,
      duration_lower_minutes=distribution([t['duration_min_minutes'] for t in trades]),
      duration_upper_minutes=distribution([t['duration_max_minutes'] for t in trades]),
      excursion_distributions={key:distribution([t[key] for t in trades]) for key in ('mfe_guaranteed_usd','mfe_possible_usd','mae_guaranteed_usd','mae_possible_usd')},
      excursion_censored_trades=sum(t['excursion_censored'] for t in trades),
      initial_stop_dollars=distribution([abs(t['stop']-t['raw_entry'])*2 for t in trades]),
      risk_rejections=dict(Counter(c['reason'] for c in candidates if not c['accepted'])),
      fill_rejections=dict(Counter(c['entry_reason'] for c in candidates if c.get('entry_accepted') is False)),
      candidate_count=len(candidates),risk_events=result['risk_events'],
      positive_30session_blocks=sum(sum(s['net'] for s in sessions[i:i+30])>0 for i in range(0,len(days),30)),
      temporal_30session_blocks=[{'from':days[i],'through':days[min(i+29,len(days)-1)],'net':sum(s['net'] for s in sessions[i:i+30])} for i in range(0,len(days),30)],
      uncertainty=uncertainty([s['net'] for s in sessions]))
    return m,sessions

def preservation():
    paths=set()
    for folder in ('src','tests','tests_sim','config','configs','reports','dashboard','adapters'):
        base=ROOT/folder
        if not base.exists():continue
        for p in base.rglob('*'):
            if not p.is_file() or OUT in p.parents:continue
            if any(s in ('.venv','__pycache__','.pytest_cache','node_modules','.git') for s in p.parts):continue
            paths.add(p)
    paths.update(p for p in ROOT.iterdir() if p.is_file())
    return {str(p.relative_to(ROOT)):hashed(p) for p in sorted(paths)}

def protocol():
    return {'experiment':'MNQ Sweep/MSS H1 ATR20 1.5 stop / 2R target / 5 complete minutes, ONE configuration',
      'frozen_at_utc':datetime.now(timezone.utc).isoformat(),'data_status':'ALL120_PREVIOUSLY_OBSERVED_EXPLORATORY_FOREVER',
      'dataset_sha256':'b5d3e676d1de881a8bd1a07eedccc14f286a615db0d7b4169f9950fead600ff5',
      'signal':'Unchanged PriceStrategy(StrategyConfig(sweep_mss)); closed causal pivot/sweep/MSS, no signal replacement',
      'ATR':'Arithmetic mean last20 same-session TR using21completed bars, previous close within session, no Wilder smoothing',
      'B':{'stop':'ceil(1.5*signal_ATR20/0.25)*0.25, frozen at signal','target_R':2,'time_minutes':5,'quantity':1,'trailing':False},
      'schedule':'First ATR-ready causal closed signal with10:00<=signal availability<15:00NY. At most1candidate perday; all signal-time/fill-time risk rejections consume day. Next available open; gap/roll causes safe error (owned cache is complete).',
      'A_full':'Unmodified original StrategyReplay, original all signals/fixed15target8stop original09:45–15:30window; exact original ledger required both accounts',
      'A_matched':'Only matched control, not selectable: same first-signal schedule and admission caps asB, original fixed15point target/8point stop, no5minute exit. Shared15:30open safety. Conditional stop/target prices same frozen engine.',
      'risk':'Config/Risk/entry_permission/close authority unchanged: daily200USD/global500USD/3losses; max10 original but research max1candidate/day. Continuous primary, daily-reset separate coverage diagnostic NEVER deployable.',
      'cap':{'all_in_initial_stop_usd':100,'justification':'1% original10000USD capital and half200daily budget, frozen without B economics','quantity':'Exactly1MNQmicro or reject; no fractional sizing or scale-up','includes':'stop distance*$2 + dated roundtrip broker/exchange/regulatory + assumed roundtrip slip/spread','budgets':'Reject if modeled stop loss exceeds remaining daily200+realized_day or global500-max(0,peak-realized)','limitation':'Initial modeled risk only, not guaranteed realized loss: gaps and unmeasured fills can exceed cap'},
      'costs':{'broker_per_side':.25,'exchange_per_side':.35,'regulatory_per_side':'0.02 before2026-07-01 otherwise0.01','slippage_ticks_each_side':1,'spread_ticks':0,'empirically_measured':False},
      'exit_priority':'Adverse stop gap at open first. Then deadline5complete minutes or safety15:30at open (before that minute OHLC). Then stop-first bracket collision; target fills atlevel,no favorable gap improvement. Then risk atclose. Lastbar close only emergency end_of_data; missing/incomplete sessions error.',
      'marking':'Original minute-close net equity reserves FULL roundtrip fee and executioncost whileopen; DD from initialzero peak incl no-trade sessions. Not ticklevel DD.',
      'excursions':'GrossUSD rawprice excursions: guaranteed completed pre-exitbars + execution/open endpoints; intrabar stop/target exitbar full extrema only POSSIBLE upper envelopes, may be postexit so never realized. Open exits exclude whole subsequent high/low. Intrabar durations1minute interval; open exact.',
      'uncertainty':'Circular paired daily bootstrap10000 seed1729 primaryblock5 sensitivity1/10; family8 retained conservatively from existing decision. Pathconditional not independent and halted risk not reconstructed.',
      'decision':{'negative_fullcoverage_B_net':'REJECT_THIS_CONFIGURATION_ON_OBSERVED_SAMPLE, not universal proof; no stress rerun needed',
        'promotion_minimum':'Continuous and diagnostic B net>0, PF>=1.15, >=60trades, no continuous globalhalt; family8 one-sided lower>0 on Babsolute and pairedBminusA_matched at blocks1/5/10, >=3of4 positive30session diagnostic blocks; adversecostnet>0. Otherwise INCONCLUSIVE_NOT_PROMOTED; an interrupted lowN primary alone never establishes profitable edge.',
        'relative_only':'Improvement over losing A does not qualify; no parameter adjustment after results','independent_evidence':False},
      'adverse_cost':'If base B diagnostic net<=0, skip as already economically rejected; otherwise exactly existing adverse broker0.50/exchange0.35/datedreg per side, spread1tick,slip2ticks each side, same frozen B and caps, both accounts; no parametersearch',
      'future_independent':{'scope':'Only MNQ H1 and matchedparent; retain family8 conservative bounds, no H2 run orMES variant',
       'period':'First90complete XNYS cash sessions strictly after code/protocolfreeze; earliest2026-10-27, never inspected; no economics interim peeking/no extension',
       'minimum_trades_each_arm':60,'criteria':'Bnet>0;PF>=1.15; family8 one-sided95% lower Bnet and pairedparentdelta>0 with10000seed1729 circularblock5 and1/10sensitivity; >=2of3 positive30sessionblocks; no continuousriskhalt; existingadversecostnet>0',
       'exclusions':'Predetermined XNYS fullcashcalendar; halfdays excluded bycalendar, missing/invalid/roll/gap/availability sessions reported unpriceable not silently dropped or PnLselected; failure to obtain90valid locked sessions=>INCONCLUSIVE, no date extension. Any inspected session ineligible.',
       'controls':'Freeze raw/normalized hashes, source/config, PIT rollovercalendar mapping, costs before one run; substantive change requires newfreeze+freshdata. No paiddata or connection authorized; quote/prints and certifiednews needed before promotion.'},
      'network':'Denied socket.connect/connect_ex/create_connection/sendto in CLI; no credentials read; newsOFF exploratory, strictnews remains blocked',
      'rollback':'Delete only reports/sweep-atr-experiment; no production imports/dependencies changed','skill_resolution':'paths-injected'}

def freeze():
    if (OUT/'protocol.json').exists():raise ValueError('Already frozen, never overwrite')
    protected=preservation();save(OUT/'preservation-before.json',protected)
    p=protocol();save(OUT/'protocol.json',p)
    files=['experiment.py','test_experiment.py','protocol.json','preservation-before.json','tdd-red.txt','tdd-green.txt']
    save(OUT/'freeze-manifest.json',{'files':{f:hashed(OUT/f) for f in files},'source_files':{p:h for p,h in protected.items() if p.startswith('src/')},'dataset_sha256':hashed(DATA)})
    print('FROZEN protocol',hashed(OUT/'protocol.json'),'manifest',hashed(OUT/'freeze-manifest.json'),flush=True)

def validate():
    frozen=json.loads((OUT/'freeze-manifest.json').read_text())
    for f,h in frozen['files'].items():
        if hashed(OUT/f)!=h:raise ValueError('Frozen experiment changed:'+f)
    before=json.loads((OUT/'preservation-before.json').read_text())
    for p,h in before.items():
        if hashed(ROOT/p)!=h:raise ValueError('Protected input changed:'+p)
    if hashed(DATA)!=frozen['dataset_sha256']:raise ValueError('Data changed')
    return before

def research_run(bars,days,arm,account,config,spec):
    if arm=='A_full':
        groups={(d,'MNQ'):[b for b in bars if b.start.astimezone(NY).date().isoformat()==d] for d in days}
        result,halt=execute(bars,config,'sweep_mss',spec) if account=='continuous' else combined_daily(groups,days,'MNQ',config,'sweep_mss',spec)
        return result,halt,[]
    if account=='continuous':
        r=H1Replay(bars,config,spec,arm);return r.run(),r.global_halt,r.candidates
    result={k:[] for k in ('trades','decisions','orders','equity','risk_events')};candidates=[];realized=peak=0.
    for d in days:
        r=H1Replay([b for b in bars if b.start.astimezone(NY).date().isoformat()==d],config,spec,arm);part=r.run();candidates.extend(r.candidates)
        for point in part['equity']:
            pnl=realized+point['net_pnl'];peak=max(peak,pnl);point.update(net_pnl=pnl,equity=config.virtual_capital+pnl,drawdown=peak-pnl)
        realized+=sum(t['net'] for t in part['trades'])
        for key in result:result[key].extend(part[key])
    return result,False,candidates

def run():
    before=validate();v1=json.loads((ROOT/'reports/archive/vwap-v1-manifest.json').read_text());count=verify_manifest(ROOT,v1)
    pp=json.loads((OUT/'protocol.json').read_text());bb=read_bars(DATA);bars=[b for b in bb if b.symbol=='MNQ'];days=sorted({b.start.astimezone(NY).date().isoformat() for b in bars})
    if len(bb)!=93600 or len(days)!=120 or any(sum(b.start.astimezone(NY).date().isoformat()==d for b in bars)!=390 for d in days):raise ValueError('Expected120complete sessions and93600MNQ+MESbars')
    results={};config=Config(news_required=False);spec=StrategyConfig('sweep_mss');reference=json.loads((ROOT/'reports/research-v2/results.json').read_text())
    for arm in ('A_full','A_matched','B'):
        for account in ('continuous','daily_reset_diagnostic'):
            result,halt,candidates=research_run(bars,days,arm,account,config,spec)
            if arm=='A_full':
                original=reference['results'][f'MNQ/sweep_mss/{account}/ticks1.0']
                for k in ('trades','gross','fees','execution_cost','net','max_drawdown_mark_to_minute_close'):
                    if abs(summarize(result)[k]-original[k])>1e-7:raise ValueError('A_full mismatch:'+k)
                with (ROOT/f'reports/research-v2/results/MNQ/sweep_mss/{account}/ticks1.0/trades.csv').open() as f:old=list(csv.DictReader(f))
                if len(old)!=len(result['trades']):raise ValueError('A_full ledger count mismatch')
                for a,b in zip(result['trades'],old):
                    for k in ('entry_at','exit_at','side','raw_entry','raw_exit','gross','fees','execution_cost','net','reason'):
                        if str(a[k])!=b[k] and not (k not in ('entry_at','exit_at','reason') and abs(float(a[k])-float(b[k]))<1e-8):raise ValueError('A_full ledger mismatch:'+k)
            m,sessions=analyze(result,bars,days,halt,candidates);results[arm+'/'+account]=m
            folder=OUT/arm/account;folder.mkdir(parents=True,exist_ok=True)
            csvwrite(folder/'trades.csv',result['trades']);csvwrite(folder/'sessions.csv',sessions);csvwrite(folder/'candidates.csv',candidates);csvwrite(folder/'equity.csv',result['equity'])
            save(folder/'metrics.json',m)
            print(arm,account,'N',m['trades'],'gross',m['gross'],'net',m['net'],'halt',halt,flush=True)
    paired={}
    for account in ('continuous','daily_reset_diagnostic'):
        a=results['A_matched/'+account]['daily_net'];b=results['B/'+account]['daily_net']
        paired[account]=uncertainty([b[d]-a[d] for d in days]);csvwrite(OUT/('paired-'+account+'.csv'),[{'date':d,'A_matched_net':a[d],'B_net':b[d],'delta':b[d]-a[d]} for d in days])
    adverse={};diagnostic=results['B/daily_reset_diagnostic'];primary=results['B/continuous']
    if diagnostic['net']<=0:decision='REJECT_THIS_CONFIGURATION_ON_OBSERVED_SAMPLE';adverse={'status':'SKIPPED_PREDECLARED_ALREADY_NEGATIVE_BASE_NET'}
    else:
        stress=replace(config,commission_per_side=.5,spread_ticks=1.,entry_slippage_ticks=2.,exit_slippage_ticks=2.)
        for account in ('continuous','daily_reset_diagnostic'):
            result,halt,c=research_run(bars,days,'B',account,stress,spec);m,s=analyze(result,bars,days,halt,c);adverse[account]=m
            folder=OUT/'adverse'/account;folder.mkdir(parents=True,exist_ok=True);csvwrite(folder/'trades.csv',result['trades']);csvwrite(folder/'sessions.csv',s)
        eligible=all(m['net']>0 and m['profit_factor']>=1.15 and m['trades']>=60 for m in (primary,diagnostic)) and not primary['global_halt_latched'] and diagnostic['positive_30session_blocks']>=3
        eligible=eligible and all(diagnostic['uncertainty']['blocks'][str(k)]['lower_one_sided_family8_95']>0 and paired['daily_reset_diagnostic']['blocks'][str(k)]['lower_one_sided_family8_95']>0 for k in (1,5,10))
        eligible=eligible and all(v['net']>0 for v in adverse.values())
        decision='EXPLORATORY_CANDIDATE_REQUIRES_90_NEW_SESSIONS' if eligible else 'INCONCLUSIVE_NOT_PROMOTED'
    validate();save(OUT/'preservation-after.json',{p:hashed(ROOT/p) for p in before})
    output={'decision':decision,'protocol_sha256':hashed(OUT/'protocol.json'),'freeze_manifest_sha256':hashed(OUT/'freeze-manifest.json'),
      'dataset_sha256':hashed(DATA),'sessions':120,'bars_all':len(bb),'bars_MNQ':len(bars),'results':results,'paired_B_minus_A_matched':paired,'adverse_cost':adverse,
      'independent_evidence':False,'protected_files_verified':len(before),'archive_files_verified':count,'network_connections':0,'credentials_read':False,'risk_engine_modified':False,
      'A_full_reconciled':'Full pertrade ledger and economics match saved V2 in bothaccounts','news':'OFF exploratory, strict remains blocked'}
    save(OUT/'results.json',output);save(OUT/'future-independent-protocol.json',{'frozen_protocol_sha256':output['protocol_sha256'],**pp['future_independent']})
    print('DECISION',decision,'resultsSHA',hashed(OUT/'results.json'),flush=True)


def main():
    def denied(*a,**kw):raise RuntimeError('Offline experiment: network disabled')
    socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied;socket.socket.sendto=denied
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');args=parser.parse_args()
    freeze() if args.freeze else run()

if __name__=='__main__':main()
