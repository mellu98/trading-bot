"""Four preregistered lag variants, no parameter fitting or economic selection."""
import math
import numpy as np
from reuse import cap
DAY=86400

def features(close,quote,full,j):
 n=close.shape[1];x={'feature_index':j,'eligible':np.zeros(n,bool),'L':np.full(n,np.nan),'risk_returns':np.full((30,n),np.nan)}
 if j<30:return x
 for k in range(n):
  c=close[j-30:j+1,k];q=quote[j-29:j+1,k];priorQ=quote[j-30:j,k]
  if not(np.all(full[j-29:j+1,k]) and np.all(np.isfinite(c)) and np.all(c>0)):continue
  x['risk_returns'][:,k]=np.diff(np.log(c))
  x['eligible'][k]=np.all(np.isfinite(q)) and np.median(q)>=1e7
  if quote[j,k]>0 and np.all(np.isfinite(priorQ)) and np.all(priorQ>0):x['L'][k]=np.log(quote[j,k]/np.mean(priorQ))
 return x

def h1_features(close,quote,full,j):
 x=features(close,quote,full,j);n=close.shape[1];x.update(z=np.full(n,np.nan),current_return=np.full(n,np.nan),trigger=np.zeros(n,bool))
 if j<31:return x
 for k in range(n):
  c=close[j-31:j+1,k]
  if not(np.all(np.isfinite(c)) and np.all(c>0)):continue
  r=np.diff(np.log(c));prior=r[:-1];sd=np.std(prior,ddof=1);current=r[-1];x['current_return'][k]=current
  if sd>0 and np.isfinite(sd):x['z'][k]=(current-np.mean(prior))/sd
  x['trigger'][k]=x['eligible'][k] and current<0 and x['z'][k]<-1 and x['L'][k]<0
 return x

def h2_features(close,quote,full,j):return features(close,quote,full,j)

def target(x,symbols,family,mode='strategy',requested_exposure=None):
 w=np.zeros(len(symbols));eligible=np.flatnonzero(x['eligible'])
 if mode=='strategy':
  if family=='H1':w[x['trigger']]=.5
  else:
   ranked=sorted([k for k in eligible if np.isfinite(x['L'][k]) and x['L'][k]<0],key=lambda k:(x['L'][k],symbols[k]))
   for k in ranked[:2]:w[k]=.5
  return cap(w,x['risk_returns'])
 if len(eligible):w[eligible]=1/len(eligible)
 if mode=='riskcap':return cap(w,x['risk_returns'])
 if mode=='matched':return w*(requested_exposure or 0.)
 return w

def h1_schedule(at,lag_hours):return at%DAY==lag_hours*3600

def h2_feature_index(execution_day_index,lag_days):return execution_day_index-lag_days-1

def paired_bootstrap(a,b,metric,replicates=10000):
 a=np.asarray(a);b=np.asarray(b);assert len(a)==len(b);n=len(a)
 if n<30:return {'status':'UNDEFINED_INSUFFICIENT_DAYS','blocks':{}}
 blocks={}
 for k in (7,30):
  rng=np.random.default_rng(20261028);values=[]
  for t in range(0,replicates,250):
   size=min(250,replicates-t);beg=rng.integers(0,n,(size,math.ceil(n/k)));ix=((beg[:,:,None]+np.arange(k))%n).reshape(size,-1)[:,:n];aa=a[ix];bb=b[ix]
   if metric=='mean_excess':v=np.mean(aa-bb,axis=1)
   else:
    with np.errstate(divide='ignore',invalid='ignore'):v=(np.mean(aa,axis=1)/np.std(aa,axis=1,ddof=1)-np.mean(bb,axis=1)/np.std(bb,axis=1,ddof=1))*math.sqrt(365)
   values.extend(v.tolist())
  good=bool(np.all(np.isfinite(values)));blocks[str(k)]={'status':'OK' if good else 'UNDEFINED_VARIANCE','lower_family2':float(np.quantile(values,.025)) if good else None,'ci95':np.quantile(values,[.025,.975]).tolist() if good else None}
 return {'metric':metric,'alpha':.025,'current_primary_families':2,'seed':20261028,'replicates':replicates,'blocks':blocks,'interpretation':'CONDITIONAL EXPLORATORY ONLY, observed history; not global p-value, OOS proof, future-profit probability or unknown-trial-history DSR'}
