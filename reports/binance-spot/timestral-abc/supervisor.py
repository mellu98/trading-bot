"""Additive progress-transport remedy. Never changes/retries scientific inference."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
OUT=Path(__file__).resolve().parent

class ProgressDeadline:
    def __init__(self,path,started):self.path=Path(path);self.last=started;self.progress={'stage':'startup','started_mono_ns':started}
    def expired(self,now):
        try:
            p=json.loads(self.path.read_text());stamp=p['started_mono_ns']
            if type(stamp) is int and self.last<=stamp<=now and p.get('stage') in ('loading','warmup','forecast','done'):
                self.last=stamp;self.progress=p
        except (OSError,ValueError,KeyError,TypeError):pass
        return now-self.last>300000000000


def watch(process,deadline,now=time.monotonic_ns,sleep=time.sleep):
    while True:
        status=process.poll()
        if status is not None:return status
        if deadline.expired(now()):
            process.terminate()
            try:process.wait(5)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            return 124
        sleep(.5)


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',choices=['209M'],required=True);a=p.parse_args()
    import runner
    runner.validate();receipt=json.loads((OUT/'supervisor-addendum.json').read_text())
    for path,digest in receipt['immutable_sha256'].items():
        if runner.sha(runner.ROOT/path)!=digest:raise ValueError('Immutable incident target changed')
    for path,digest in receipt['helper_sha256'].items():
        if runner.sha(runner.ROOT/path)!=digest:raise ValueError('Additive helper changed')
    if (OUT/(a.model+'-forecasts.jsonl')).exists():raise ValueError('No same-model retry or overwrite')
    env=dict(os.environ);env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    started=time.monotonic_ns();process=subprocess.Popen([sys.executable,str(OUT/'runner.py'),'worker','--model',a.model],env=env)
    deadline=ProgressDeadline(OUT/(a.model+'-progress.json'),started);status=watch(process,deadline)
    proof={'model':a.model,'worker_exit':status,'last_valid_progress':deadline.progress,'ended_ns':time.time_ns(),'no_retry':True,'scientific_code_unchanged':True}
    if status==124:runner.save(OUT/(a.model+'-timeout.json'),proof)
    runner.save(OUT/'supervisor-result.json',proof)
    if status:raise SystemExit(status)
    runtime=json.loads((OUT/(a.model+'-runtime.json')).read_text())
    if runtime['forecast_sha256']!=runner.sha(OUT/(a.model+'-forecasts.jsonl')):raise ValueError('Worker output hash mismatch')
    print('SUPERVISOR_DONE',a.model,runtime['rows'],'errors',runtime['errors'],flush=True)
if __name__=='__main__':main()
