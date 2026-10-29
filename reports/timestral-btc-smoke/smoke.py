"""Technical real-checkpoint smoke only; no economic comparison or live integration."""
from pathlib import Path
import argparse,hashlib,importlib.util,io,csv,json,os,resource,socket,statistics,subprocess,sys,time,zipfile
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
def denied(*a,**kw):raise RuntimeError('Technical cached smoke: network forbidden')
def rss():
 return {'resident_kib':int(subprocess.check_output(['ps','-p',str(os.getpid()),'-o','rss='],text=True).strip()),'peak_rss_raw':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'peak_rss_raw_unit':'bytes' if sys.platform=='darwin' else 'KiB'}

def context():
 spec=importlib.util.spec_from_file_location('frozen_breakout_context_reuse',ROOT/'reports/binance-spot/breakout-4h/runner.py')
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 bars=[];sources=[]
 for month in ['2024-12','2025-01']:
  p=ROOT/'data/binance-spot/research'/f'BTCUSDT-1h-{month}.zip';checksum=p.with_name(p.name+'.CHECKSUM');fields=checksum.read_text().split();digest=sha(p)
  if fields!=[digest,p.name]:raise ValueError('Original checksum mismatch')
  with zipfile.ZipFile(p) as z:
   entries=z.infolist()
   if len(entries)!=1 or entries[0].filename!=p.stem+'.csv' or entries[0].file_size>10000000:raise ValueError('Unsafe archive')
   content=z.read(entries[0])
  rows=[module.parse_row(row,month) for row in csv.reader(io.StringIO(content.decode()))];bars.extend(rows)
  sources.append({'path':str(p.relative_to(ROOT)),'sha256':digest,'checksum_sha256':sha(checksum),'unit':'ms' if month.startswith('2024') else 'us'})
 four=module.aggregate4(bars[:1024]);assert len(four)==256
 records=[{'start_ns':b.start,'end_ns':b.end,'close':str(b.close)} for b in four]
 save(OUT/'context.json',{'symbol':'BTCUSDT','interval_seconds':14400,'context_length':256,'start':module.iso(four[0].start),'origin':module.iso(four[-1].end),'bars':records,'sources':sources,'purpose':'technical inference smoke only; no future labels or economic outcome evaluated'})
 return records

def run(model):
 socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
 import numpy as np,torch
 from mnq_timestral.model import OfficialAdapter,PINS,SOURCE_REVISION,verify_source
 from mnq_timestral.schema import LEVELS
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(1729)
 records=json.loads((OUT/'context.json').read_text());x=np.array([float(b['close']) for b in records['bars']],dtype=np.float64)[None,None,:]
 verify_source();checkpoint=ROOT/'data/models'/('Timestral-'+model);pin=PINS[model]
 start=time.perf_counter();adapter=OfficialAdapter(model,checkpoint,max_context=256);load=time.perf_counter()-start
 configuration={'prediction_length':15,'symmetric_averaging':True,'clip_nonnegative':False,'past_covariates':None,'known_covariates':None}
 calls=[];values=[]
 for n in range(4):
  start=time.perf_counter();cpu=time.process_time();prediction=adapter.forecaster.forecast(x,**configuration);latency=time.perf_counter()-start;cpu=time.process_time()-cpu
  q=prediction.quantiles.detach().cpu().numpy();assert q.shape==(1,1,15,21) and tuple(prediction.quantile_levels)==LEVELS
  assert np.isfinite(q).all() and (np.diff(q,axis=-1)>=0).all()
  calls.append({'warmup':n==0,'wall_seconds':latency,'process_cpu_seconds':cpu,**rss()});values.append(q)
 latencies=[c['wall_seconds'] for c in calls[1:]]
 model_config=adapter.forecaster.model.config
 result={'status':'PASS','real_inference_performed':True,'mock_used':False,'model':model,'checkpoint_revision':pin.revision,'source_revision':SOURCE_REVISION,'weights_sha256':pin.weights_sha256,'weights_bytes':pin.weights_bytes,'config_sha256':pin.config_sha256,'license_sha256':sha(checkpoint/'LICENSE'),
 'torch':torch.__version__,'cpu_threads':torch.get_num_threads(),'interop_threads':torch.get_num_interop_threads(),'device':str(adapter.forecaster.device),'dtype':str(next(adapter.forecaster.model.parameters()).dtype),'training':adapter.forecaster.model.training,'load_seconds':load,'calls':calls,
 'timed_calls':3,'median_seconds':statistics.median(latencies),'max_seconds':max(latencies),'context_sha256':sha(OUT/'context.json'),'context_shape':list(x.shape),'configuration':configuration,'quantile_levels':list(prediction.quantile_levels),'shape':list(q.shape),'quantiles':q[0,0].tolist(),'all_repeated_outputs_identical':all(np.array_equal(values[0],v) for v in values[1:]),
 'forecaster_defaults':{'max_context':adapter.forecaster.max_context,'per_shot_horizon_patches':adapter.forecaster.per_shot_horizon_patches,'quantile_real_cap_k':adapter.forecaster.quantile_real_cap_k},
 'interpretation':'Technical output only; each step is one4hbar, not minute. No forecast quality/PnL/edge measured. Quantiles are marginal level predictions, not TP-before-SL probabilities. CME Request/Prediction wrapper intentionally bypassed, not relabeled.'}
 save(OUT/(model+'.json'),result);print(model,'PASS','median_ms',statistics.median(latencies)*1000,'load_s',load,'rss',rss(),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['context','28M','209M']);a=p.parse_args()
 if a.action=='context':context()
 else:run(a.action)
