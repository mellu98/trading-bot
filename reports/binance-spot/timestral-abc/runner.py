"""One frozen retrospective A/B/C diagnostic; no live engine/model/schema changes."""
from pathlib import Path
from dataclasses import replace
from decimal import Decimal
from collections import Counter,defaultdict
import argparse,hashlib,importlib.util,json,math,os,resource,socket,subprocess,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;H=3600000000000
PH='e4852ae6a1e3c9ff37c08b724e54f3bef23c1d3c12179baa0a09123ae5d2b3ab';HURDLE=Decimal('0.002402882974988590390614641')
path=ROOT/'reports/binance-spot/breakout-4h/runner.py';spec=importlib.util.spec_from_file_location('frozen_channel_reuse',path);baseline=importlib.util.module_from_spec(spec);sys.modules[spec.name]=baseline;spec.loader.exec_module(baseline)
from mnq_local.binance_spot import dec,SpotSpec
from mnq_local.replay import AtomicJournal
from mnq_timestral.schema import LEVELS
from mnq_timestral.model import PINS,SOURCE_REVISION
sha,save,iso,day=baseline.sha,baseline.save,baseline.iso,baseline.day


def deny(*a,**kw):raise RuntimeError('Cached offline experiment: network forbidden')
def valid_quantiles(q):
    try:
        q=np.asarray(q,dtype=float)
        return q.shape==(15,21) and np.isfinite(q).all() and (q>0).all() and (np.diff(q,axis=-1)>=0).all()
    except (TypeError,ValueError):return False

def gate(record,decision,current):
    if record is None:return False,'missing'
    if record.get('status')=='missing_warmup':return False,'missing_warmup'
    if record['origin_ns']!=decision-4*H or record.get('input_end_ns')!=record['origin_ns']:return False,'origin_mismatch'
    if record.get('status')!='ok' or not valid_quantiles(record.get('quantiles')):return False,'invalid'
    if record['latency_seconds']>300 or record['historical_available_ns']>=decision:return False,'late'
    return (True,'allow') if dec(record['quantiles'][1][10])>current*(1+HURDLE) else (False,'nonpositive_forecast_edge_after_cost_hurdle')

def context_at(closes,index):return closes[index-255:index+1] if index>=255 else None

def mature(origin,h,end):return origin+h*4*H<end

def naive_quantiles(past,h):
    returns=past[h:]/past[:-h]-1
    return past[-1]*(1+np.quantile(returns,LEVELS,method='linear'))

def rank(x):
    x=np.asarray(x);_,ix,count=np.unique(x,return_inverse=True,return_counts=True);r=np.cumsum(count)-count/2+.5
    return r[ix]


def load():
    validate();original=baseline.save
    def isolated(path,value):
        if path!=baseline.OUT/'data-quality.json':raise ValueError('Unexpected frozen baseline write')
        save(OUT/'data-quality.json',value)
    baseline.save=isolated
    try:return baseline.load()
    finally:baseline.save=original


class FilteredSpot(baseline.ChannelSpot):
    def __init__(self,*a,model,records,closes,**kw):
        self.filter_model=model;self.forecasts=records;self.close_map=closes;self.filter_audit=[]
        super().__init__(*a,**kw)
    def enter(self,atr):
        rec=self.forecasts.get(self.now-4*H);current=self.close_map.get(self.now)
        allowed,reason=gate(rec,self.now,current) if current is not None else (False,'missing_current_closed_bar')
        self.filter_audit.append({'decision_ns':self.now,'forecast_origin_ns':rec['origin_ns'] if rec else None,'target_ns':self.now+4*H,'allowed':allowed,'reason':reason,'model':self.filter_model,'current_close':str(current),'median_step2':rec['quantiles'][1][10] if rec and rec.get('status')=='ok' else None})
        return super().enter(atr) if allowed else False


def make_engine(path,scenario,model,records,closes):
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    if (path/'state.sqlite').exists():raise ValueError('Fresh independent diagnostic account required')
    fee,slip,_=baseline.COSTS[scenario];cfg=replace(baseline.old.ResearchConfig(),account='OFFLINE_BTC_CHANNEL_RESEARCH',fee_rate=fee,slippage_rate=slip)
    s=SpotSpec('BTCUSDT','.01','.00001','.00001','9000','5');j=AtomicJournal(path/'state.sqlite',cfg,[s],lock_root=path/'locks')
    return FilteredSpot(cfg,s,j,scenario,model=model,records=records,closes=closes),j


def sources():
    paths=[str((OUT/'runner.py').relative_to(ROOT)),str((OUT/'test_abc.py').relative_to(ROOT)),'src/mnq_timestral/model.py','src/mnq_timestral/schema.py','src/mnq_timestral/data.py',str(path.relative_to(ROOT))]+list(baseline.frozen_sources())
    return {p:sha(ROOT/p) for p in set(paths)}


def freeze():
    if sha(OUT/'protocol.json')!=PH or (OUT/'execution-freeze.json').exists():raise ValueError('Protocol changed or already frozen')
    save(OUT/'execution-freeze.json',{'at_ns':time.time_ns(),'protocol_sha256':PH,'sources':sources(),'model_pins':{k:vars(v) for k,v in PINS.items()},'source_revision':SOURCE_REVISION,'hurdle':str(HURDLE),
    'fixed_technical_interpretations':{'data':'Existing verified loader reused with dataquality write redirected only to this isolated report; no new downloads.',
    'input_hash':'Canonical littleendian256float32 tensor bytes and normalizeddataset SHA bind each origin. Decimalrawprices converted once to explicitfloat32 model input. Naive uses same256observedcloses in float64 for scoring.',
    'time':'OriginO one4hbeforebaselinecandidateT. Step2targetO+8h=T+4h. Historicalavailability=O+ceilmeasuredwallns is counterfactual only, separately actualwallissuance. NooriginTsubstitution.',
    'boundary':'Forecast evaluation excludes targets>=segmentend; no futureperiodprice used. Missing first2025warmup recorded; inference attempted only after256completecloses.',
    'uncertainty':'Circular1/5/10UTCdayblock10000seed1729; dailymeanorigin error improvement for forecasts, dailyMTMnetdiff for economics. One-sided97.5lower=2.5percentile for2models; diagnostic not independent proof.',
    'direction':'Allorigins tie-inclusive directionaccuracy plus nonzero forecast/actual conditionalcalls; ties counted explicitly. Spearmanaverage-tie rank correlation, None if degenerate.',
    'invalid':'Nonpositive/nonfinite/crossedoutput never sorted/clipped/repaired; error row thenveto. No settings retries. Supervisor kills worker ifoneforecast/coldloadprogress exceeds300s.',
    'naive':'ONEpointpersistence=zero-cumulative-return baseline. Past empiricalhreturnquantiles linear interpolation fromsame256closes, notfittedoutcomes; naivequantilemedian isnotpointpersistence.'},'full_forecasts_not_run':True,'parameter_search':False})
    print('FROZEN',sha(OUT/'execution-freeze.json'),flush=True)


def validate():
    f=json.loads((OUT/'execution-freeze.json').read_text())
    if sha(OUT/'protocol.json')!=PH or f['sources']!=sources():raise ValueError('Frozen experiment changed')
    baseline.validate()


def worker(model):
    socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny
    validate();bars,quality=load();four=baseline.aggregate4(bars);closes=[float(b.close) for b in four]
    import torch
    from mnq_timestral.model import OfficialAdapter
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(1729)
    progress=OUT/(model+'-progress.json');destination=OUT/(model+'-forecasts.jsonl')
    if destination.exists():raise ValueError('Never overwrite a forecast run')
    save(progress,{'stage':'loading','started_mono_ns':time.monotonic_ns()});started=time.perf_counter();adapter=OfficialAdapter(model,ROOT/'data/models'/('Timestral-'+model),max_context=256);load_seconds=time.perf_counter()-started
    config={'prediction_length':15,'symmetric_averaging':True,'clip_nonnegative':False,'past_covariates':None,'known_covariates':None}
    warm=np.array(closes[:256],dtype=np.float32)[None,None,:];save(progress,{'stage':'warmup','started_mono_ns':time.monotonic_ns()});started=time.perf_counter();adapter.forecaster.forecast(warm,**config);warmup=time.perf_counter()-started
    wall0=time.time_ns();mono0=time.monotonic_ns();cpu0=time.process_time();times=[];errors=Counter();rows=0
    with destination.open('x',buffering=1) as f:
        for i,b in enumerate(four):
            if not ('2025-01'<=iso(b.end)[:7]<'2026-10'):continue
            segment='primary' if iso(b.end)[:4]=='2026' else 'secondary'
            past=context_at(closes,i)
            if past is None:
                f.write(json.dumps({'status':'missing_warmup','model':model,'origin_ns':b.end,'segment':segment})+'\n');continue
            tensor=np.array(past,dtype='<f4')[None,None,:];origin=b.end;started_ns=time.time_ns();start_mono=time.monotonic_ns();cpu=time.process_time()
            save(progress,{'stage':'forecast','origin_ns':origin,'started_mono_ns':start_mono})
            row={'model':model,'model_revision':PINS[model].revision,'source_revision':SOURCE_REVISION,'weights_sha256':PINS[model].weights_sha256,'dataset_sha256':quality['dataset_sha256'],'origin_ns':origin,'input_end_ns':origin,'input_start_ns':four[i-255].start,'last_raw_hour_start_ns':origin-H,'input_sha256':hashlib.sha256(tensor.tobytes()).hexdigest(),'context_length':256,'targets_ns':[origin+h*4*H for h in range(1,16)],'segment':segment,'wall_infer_start_ns':started_ns}
            try:
                prediction=adapter.forecaster.forecast(tensor,**config);q=prediction.quantiles.detach().cpu().numpy()[0,0];elapsed=time.monotonic_ns()-start_mono
                if tuple(prediction.quantile_levels)!=LEVELS or not valid_quantiles(q):raise ValueError('invalid_quantile_output')
                row.update(status='ok',quantiles=q.tolist())
            except Exception as exc:
                elapsed=time.monotonic_ns()-start_mono;row.update(status='error',error=type(exc).__name__+':'+str(exc));errors[type(exc).__name__]+=1
            row.update(latency_seconds=elapsed/1e9,process_cpu_seconds=time.process_time()-cpu,wall_infer_end_ns=time.time_ns(),historical_available_ns=origin+elapsed,wall_available_ns=time.time_ns(),availability_note='Counterfactual O+measured latency is NOT historical issuance; wall times are actual run.')
            if elapsed>300000000000:row['status']='late';errors['late']+=1
            f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n');times.append(elapsed/1e9);rows+=1
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    save(OUT/(model+'-runtime.json'),{'model':model,'load_seconds':load_seconds,'warmup_seconds':warmup,'cpu_threads':torch.get_num_threads(),'interop_threads':torch.get_num_interop_threads(),'wall_start_ns':wall0,'wall_end_ns':time.time_ns(),'full_run_wall_seconds':(time.monotonic_ns()-mono0)/1e9,'full_run_process_cpu_seconds':time.process_time()-cpu0,'rows':rows,'errors':dict(errors),'latency_seconds':{k:float(np.quantile(times,v)) for k,v in [('p50',.5),('p95',.95),('p99',.99),('max',1)]},'peak_rss_raw':rss,'peak_rss_unit':'bytes' if sys.platform=='darwin' else 'KiB','forecast_sha256':sha(destination),'configuration':config,'checkpoint_revision':PINS[model].revision})
    save(progress,{'stage':'done','started_mono_ns':time.monotonic_ns()});print(model,'DONE',rows,'errors',dict(errors),flush=True)


def infer(model):
    validate();env=dict(os.environ);env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    process=subprocess.Popen([sys.executable,str(OUT/'runner.py'),'worker','--model',model],env=env)
    progress=OUT/(model+'-progress.json');initial=time.monotonic_ns()
    while process.poll() is None:
        time.sleep(.5);p=json.loads(progress.read_text()) if progress.exists() else {'stage':'startup','started_mono_ns':initial}
        if time.monotonic_ns()-p['started_mono_ns']>300000000000:
            process.terminate()
            try:process.wait(5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            save(OUT/(model+'-timeout.json'),{'status':'blocked_timeout','progress':p,'at_ns':time.time_ns(),'no_retry':True});raise RuntimeError('300s worker progress budget exceeded')
    if process.returncode:raise RuntimeError('Inference worker failed '+str(process.returncode))


def cached(model,quality=None,four=None):
    runtime=OUT/(model+'-runtime.json');file=OUT/(model+'-forecasts.jsonl')
    if runtime.exists() and json.loads(runtime.read_text())['forecast_sha256']!=sha(file):raise ValueError('Forecast cache hash changed')
    if not runtime.exists() and not (OUT/(model+'-timeout.json')).exists():raise ValueError('No completed runtime or timeout provenance')
    lookup={b.end:i for i,b in enumerate(four)} if four is not None else None
    result={}
    for line in (OUT/(model+'-forecasts.jsonl')).open():
        r=json.loads(line);origin=r['origin_ns']
        if origin in result:raise ValueError('Duplicate forecast origin')
        if lookup is not None and r['status']!='missing_warmup':
            i=lookup[origin];past=context_at([float(b.close) for b in four[max(0,i-255):i+1]],255)
            if past is None:raise ValueError('Insufficient cached input context')
            digest=hashlib.sha256(np.array(past,dtype='<f4').tobytes()).hexdigest()
            if r['model']!=model or r['model_revision']!=PINS[model].revision or r['source_revision']!=SOURCE_REVISION or r['weights_sha256']!=PINS[model].weights_sha256 or r['dataset_sha256']!=quality['dataset_sha256'] or r['input_sha256']!=digest or r['input_end_ns']!=origin or r['input_start_ns']!=four[i-255].start or r['last_raw_hour_start_ns']!=origin-H or r['context_length']!=256:raise ValueError('Forecast source/input provenance mismatch')
            if abs(r['historical_available_ns']-origin-round(r['latency_seconds']*1e9))>1:raise ValueError('Historical availability mismatch')
            if r['targets_ns']!=[origin+h*4*H for h in range(1,16)]:raise ValueError('Forecast target mismatch')
        result[origin]=r
    return result


def uncertainty(daily):
    b=baseline.bootstrap(list(daily))
    for v in b['blocks'].values():v['one_sided97_5_lower_two_model_bonferroni']=v['ci95'][0]
    return b


def score(model,records,four,lo,hi,common):
    selected=[i for i,b in enumerate(four) if lo<=b.end<hi and i>=255];report={'eligible_origins':len(selected),'valid_forecasts':sum(records.get(four[i].end,{}).get('status')=='ok' for i in selected),'horizons':{}}
    report['coverage']=report['valid_forecasts']/len(selected) if selected else 0
    for h in (1,2,3,6):
        paired=[];daily=defaultdict(list);naive_pin=[];naive_cov=[];naive_width=[]
        for i in selected:
            b=four[i];r=records.get(b.end)
            if b.end not in common or not mature(b.end,h,hi) or i+h>=len(four):continue
            actual=float(four[i+h].close);current=float(b.close);q=np.asarray(r['quantiles'][h-1],dtype=float);past=np.array([float(x.close) for x in four[i-255:i+1]])
            median=q[10];errors=actual-q;pin=np.maximum(np.asarray(LEVELS)*errors,(np.asarray(LEVELS)-1)*errors);nq=naive_quantiles(past,h);ne=actual-nq
            paired.append((actual,current,median,pin,q[2]<=actual<=q[18],q[18]-q[2]));daily[day(b.end)].append(abs(actual-current)-abs(actual-median))
            naive_pin.append(np.maximum(np.asarray(LEVELS)*ne,(np.asarray(LEVELS)-1)*ne));naive_cov.append(nq[2]<=actual<=nq[18]);naive_width.append(nq[18]-nq[2])
        if not paired:report['horizons'][str(h)]={'count':0};continue
        actual,current,pred=np.array([x[:3] for x in paired]).T;returns=(actual/current)-1;predreturns=(pred/current)-1;directions=np.sign(predreturns);truth=np.sign(returns);calls=(directions!=0)&(truth!=0)
        ic=float(np.corrcoef(rank(predreturns),rank(returns))[0,1]) if np.std(predreturns)>0 and np.std(returns)>0 else None
        report['horizons'][str(h)]={'count':len(paired),'mae_price':float(np.mean(abs(actual-pred))),'rmse_price':float(np.sqrt(np.mean((actual-pred)**2))),'mae_cumulative_return':float(np.mean(abs(returns-predreturns))),
        'point_persistence_zero_return_ONE_baseline':{'mae_price':float(np.mean(abs(actual-current))),'rmse_price':float(np.sqrt(np.mean((actual-current)**2))),'mae_return':float(np.mean(abs(returns)))},
        'direction_accuracy_including_zero_ties':float(np.mean(directions==truth)),'nonzero_calls':int(calls.sum()),'direction_accuracy_nonzero_calls':float(np.mean(directions[calls]==truth[calls])) if calls.any() else None,'zero_forecast':int((directions==0).sum()),'zero_actual':int((truth==0).sum()),'spearman_return_IC':ic,
        'pinball_by_level':{str(q):float(v) for q,v in zip(LEVELS,np.mean([x[3] for x in paired],axis=0))},'q10q90_coverage':float(np.mean([x[4] for x in paired])),'q10q90_mean_width':float(np.mean([x[5] for x in paired])),
        'past_empirical_naive_distribution':{'pinball_by_level':{str(q):float(v) for q,v in zip(LEVELS,np.mean(naive_pin,axis=0))},'q10q90_coverage':float(np.mean(naive_cov)),'q10q90_mean_width':float(np.mean(naive_width)),'point_median_not_persistence':True},
        'paired_absolute_error_improvement_vs_persistence':uncertainty([float(np.mean(v)) for v in daily.values()]),'origins_same_for_models_and_naive':True}
    return report


def run(tag):
    socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny
    bars,quality=load();four=baseline.aggregate4(bars);close_map={b.end:b.close for b in four};forecasts={m:cached(m,quality,four) for m in PINS}
    common=set.intersection(*[{o for o,r in c.items() if r.get('status')=='ok' and valid_quantiles(r.get('quantiles'))} for c in forecasts.values()])
    folder=OUT/tag;folder.mkdir(exist_ok=True);results={};accuracy={}
    for segment,lo,hi,original in [('secondary','2025-01','2026-01','observed_development'),('primary','2026-01','2026-10','reserved_test')]:
        start=next(i for i,b in enumerate(bars) if iso(b.start)[:7]>=lo);end=next((i for i,b in enumerate(bars) if iso(b.start)[:7]>=hi),len(bars));results[segment]={};accuracy[segment]={}
        for model in PINS:accuracy[segment][model]=score(model,forecasts[model],four,bars[start].start,bars[end-1].end,common)
        for scenario in baseline.COSTS:
            arms={};ledgers={};audits={}
            for arm,model in [('A',None),('B','28M'),('C','209M')]:
                dest=folder/segment/scenario/arm;dest.mkdir(parents=True,exist_ok=True);db=ROOT/'data/binance-spot/timestral-abc'/tag/segment/scenario/arm
                r,j=baseline.engine(db,scenario) if model is None else make_engine(db,scenario,model,forecasts[model],close_map)
                try:
                    result=baseline.simulate(r,bars,start,end);metrics=baseline.additional_metrics(result,baseline.summarize(result));audit=getattr(r,'filter_audit',[]);ledgers[arm]=result['trades'];audits[arm]=audit
                    baseline.rows(dest/'trades.csv',result['trades']);baseline.rows(dest/'daily.csv',[{'date':d,'net':n} for d,n in metrics['daily_marked_net'].items()]);baseline.rows(dest/'filter-decisions.csv',audit)
                    if arm=='A':
                        expected=json.loads((baseline.OUT/'run-1'/original/scenario/'strategy/metrics.json').read_text())
                        if metrics!=expected:raise ValueError('BaselineA must exactly reproduce frozen original metrics')
                        metrics={**metrics,'exact_original_metrics_reproduced':True,'original_metrics_sha256':sha(baseline.OUT/'run-1'/original/scenario/'strategy/metrics.json')}
                    else:metrics.update(filter_candidates=len(audit),filter_allowed=sum(x['allowed'] for x in audit),filter_reasons=dict(Counter(x['reason'] for x in audit)))
                    save(dest/'metrics.json',metrics);arms[arm]=metrics
                finally:j.close()
            for arm,model in [('B','28M'),('C','209M')]:
                paired=[n-arms['A']['daily_marked_net'][d] for d,n in arms[arm]['daily_marked_net'].items()]
                arms[arm]['paired_daily_minus_A']=uncertainty(paired)
                vetoed=[t for t in ledgers['A'] if not gate(forecasts[model].get(t['entry_ns']-4*H),t['entry_ns'],close_map[t['entry_ns']])[0]]
                arms[arm]['matched_A_opportunities_vetoed']={'count':len(vetoed),'positive_A_trades':sum(dec(t['net'])>0 for t in vetoed),'sum_A_net':str(sum((dec(t['net']) for t in vetoed),Decimal(0))),'interpretation':'Matched original baseline-trade counterfactual only, not causal profit lost; filtered positions change future candidate sets.'}
            results[segment][scenario]=arms
            print(segment,scenario,[(arm,m['trades'],m['net']) for arm,m in arms.items()],flush=True)
    verdicts={};a=results['primary']['base']['A']
    for arm,model in [('B','28M'),('C','209M')]:
        f=accuracy['primary'][model];h=f['horizons']['2'];m=results['primary']['base'][arm];lower=m['paired_daily_minus_A']['blocks']['5']['one_sided97_5_lower_two_model_bonferroni']
        failed=f['coverage']>=.99 and h['count']>=1000 and h['mae_price']>=h['point_persistence_zero_return_ONE_baseline']['mae_price'] and dec(m['net'])<=dec(a['net']) and lower<=0
        verdicts[model]='NON_UTILE_NELLA_CONFIGURAZIONE_TESTATA' if failed else 'INCONCLUDENTE'
    save(folder/'results.json',{'verdicts':verdicts,'protocol_sha256':PH,'execution_freeze_sha256':sha(OUT/'execution-freeze.json'),'dataset_sha256':quality['dataset_sha256'],'forecast_hashes':{m:sha(OUT/(m+'-forecasts.jsonl')) for m in PINS},'accuracy':accuracy,'economic_results':results,'historical_only_already_observed':True,'pretraining_overlap':'UNKNOWN_NOT_RULED_OUT','UTILE_possible_from_this_history':False,'live_models_or_orders_enabled':False})
    print('RESULT_SHA',sha(folder/'results.json'),'VERDICTS',verdicts,flush=True);validate()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','infer','worker','run']);p.add_argument('--model',choices=list(PINS));p.add_argument('--tag',default='run-1');a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='infer':infer(a.model)
    elif a.action=='worker':worker(a.model)
    else:run(a.tag)
if __name__=='__main__':main()
