"""Pure unlevered research accounting. No exchange client or operational imports."""
from dataclasses import dataclass
import math
import numpy as np
DAY=86400
@dataclass(frozen=True)
class Bar:
 start:int;end:int;open:float;high:float;low:float;close:float;volume:float;quote_volume:float;full:bool=True
@dataclass(frozen=True)
class Costs:
 fee:float=.001;slip:float=.0001;spread:float=.0002
 @property
 def buy(self):return (1+self.spread/2)*(1+self.slip)
 @property
 def sell(self):return (1-self.spread/2)*(1-self.slip)
class Portfolio:
 def __init__(self,n,costs,capital=1000.):
  self.cash=capital;self.qty=np.zeros(n);self.costs=costs;self.orders=[];self.turnover=0.;self.fees=0.;self.spread=0.;self.slippage=0.
 def mark(self,prices,liquidation=False):
  prices=np.asarray(prices);held=self.qty>1e-15
  if np.any(held&(~np.isfinite(prices)|(prices<=0))):raise ValueError('untradable held asset: no executable price')
  v=float(np.dot(self.qty[held],prices[held]));return self.cash+v*(self.costs.sell*(1-self.costs.fee) if liquidation else 1)
 def rebalance(self,prices,weights,at,meta=None):
  prices=np.asarray(prices);weights=np.asarray(weights);assert np.all(weights>=0) and sum(weights)<=1+1e-12
  nav=self.mark(prices);valid=np.isfinite(prices)&(prices>0);target=np.zeros(len(weights));target[valid]=weights[valid]*nav/prices[valid]
  # No physical quote means no buy. A missing HELD price has already raised.
  for j in np.flatnonzero(self.qty>target+1e-14):self._trade(j,self.qty[j]-target[j],prices[j],False,at,nav,meta)
  need=np.maximum(0,target-self.qty);cost=np.where(valid,need*np.nan_to_num(prices)*self.costs.buy*(1+self.costs.fee),0)
  factor=min(1,self.cash/sum(cost)) if sum(cost)>0 else 0
  for j in np.flatnonzero((need*factor>1e-14)&valid):self._trade(j,need[j]*factor,prices[j],True,at,nav,meta)
  assert self.cash>=-1e-8 and np.all(self.qty>=-1e-12)
  if abs(self.cash)<1e-10:self.cash=0.
 def _trade(self,j,q,raw,buy,at,nav,meta):
  fill=raw*(self.costs.buy if buy else self.costs.sell);notional=q*fill;fee=notional*self.costs.fee
  self.cash+=-notional-fee if buy else notional-fee;self.qty[j]+=q if buy else -q
  if abs(self.qty[j])<1e-12:self.qty[j]=0.
  spread=q*raw*self.costs.spread/2;slip=q*raw*(1+self.costs.spread/2 if buy else 1-self.costs.spread/2)*self.costs.slip
  self.fees+=fee;self.spread+=spread;self.slippage+=slip;self.turnover+=q*raw/nav
  self.orders.append({'at':int(at),'asset_index':int(j),'side':'BUY' if buy else 'SELL','quantity':float(q),'raw':float(raw),'fill':float(fill),'fee':float(fee),'spread':float(spread),'slippage':float(slip),'cash':float(self.cash),'metadata':meta or {}})

def daily_features(close,volume,full,i,lookback):
 # At UTC execution-day i, latest usable close is end of day i-2.
 j=i-2;n=close.shape[1];result={'latest_index':j,'eligible':np.zeros(n,dtype=bool),'momentum':np.full(n,np.nan),'returns':np.full((30,n),np.nan),'vol':np.full(n,np.nan)}
 if j<30:return result
 for k in range(n):
  v=close[j-30:j+1,k];ok=np.all(full[j-29:j+1,k]) and np.all(np.isfinite(v)) and np.all(v>0)
  if not ok:continue
  result['returns'][:,k]=np.diff(np.log(v));result['vol'][k]=np.std(result['returns'][:,k],ddof=1)*math.sqrt(365)
  result['eligible'][k]=np.all(np.isfinite(volume[j-29:j+1,k])) and np.median(volume[j-29:j+1,k])>=1e7
  if j>=lookback and np.isfinite(close[j-lookback,k]) and close[j-lookback,k]>0:result['momentum'][k]=close[j,k]/close[j-lookback,k]-1
 return result

def cap(weights,returns):
 active=weights>0
 if not np.any(active):return weights
 if not np.all(np.isfinite(returns[:,active])):return np.zeros_like(weights)
 vol=float(np.std(returns[:,active]@weights[active],ddof=1)*math.sqrt(365))
 return weights*min(1,.2/vol) if vol>0 and np.isfinite(vol) else np.zeros_like(weights)

def target_a(x,symbols,mode='strategy',exposure=None):
 w=np.zeros(len(symbols));eligible=np.flatnonzero(x['eligible'])
 if mode=='strategy':
  ranked=sorted([k for k in eligible if x['momentum'][k]>0],key=lambda k:(-x['momentum'][k],symbols[k]))
  for k in ranked[:2]:w[k]=.5
  return cap(w,x['returns'])
 if len(eligible):w[eligible]=1/len(eligible)
 if mode=='riskcap':return cap(w,x['returns'])
 if mode=='matched':return w*(exposure or 0)
 return w

def target_b(x,trend=True,exposure=None):
 vol=x['vol'];ok=np.isfinite(vol)&(vol>0)&x['eligible'];w=np.zeros(len(vol));w[ok]=.5*np.minimum(1,.2/vol[ok])
 if trend:w[~(x['momentum']>0)]=0
 if exposure is not None:w[:]=exposure/len(w)
 return w

def impulse(returns,j):
 if j<168:return None
 past=returns[j-168:j]
 if not np.all(np.isfinite(past)) or not np.isfinite(returns[j]):return None
 sd=np.std(past,ddof=1)
 return float((returns[j]-np.mean(past))/sd) if sd>0 else None

def schedule_impulses(returns,delay,end):
 result={}
 for j in range(168,len(returns)):
  z=impulse(returns,j);entry=j+1+delay
  if z is not None and z>1 and entry+1<end:result[entry]={'signal_index':j,'z':z,'exit_index':entry+1}
 return result

def sharpe(r):
 r=np.asarray(r);sd=np.std(r,ddof=1) if len(r)>1 else 0
 return float(np.mean(r)/sd*math.sqrt(365)) if sd>0 and np.all(np.isfinite(r)) else None

def summarize(equity,times,orders,exposure):
 eq=np.asarray(equity);ret=eq[1:]/eq[:-1]-1;pnl=np.diff(eq);gain=sum(pnl[pnl>0]);loss=-sum(pnl[pnl<0]);peak=np.maximum.accumulate(eq);down=np.minimum(ret,0);rms=math.sqrt(float(np.mean(down**2))) if len(ret) else 0;days=(times[-1]-times[0])/DAY
 s=sharpe(ret)
 return {'net_return':float(eq[-1]/eq[0]-1),'net_pnl':float(eq[-1]-eq[0]),'cagr':float((eq[-1]/eq[0])**(365/days)-1) if days>0 and eq[-1]>0 else None,'daily_sharpe_365':s,'daily_sortino_365_rf0_all_day_downside_rms':float(np.mean(ret)/rms*math.sqrt(365)) if rms>0 else None,'max_drawdown':float(np.max(1-eq/peak)),'daily_pnl_profit_factor':float(gain/loss) if loss>0 else None,'days':int(len(ret)),'order_count':len(orders),'average_exposure':float(np.mean(exposure)) if len(exposure) else 0.,'maximum_exposure':float(max(exposure,default=0)),'daily_returns':ret.tolist(),'daily_pnl':pnl.tolist(),'capital_initial':float(eq[0]),'capital_final':float(eq[-1])}

def paired_bootstrap(a,b,metric,replicates=10000):
 a=np.asarray(a);b=np.asarray(b);assert len(a)==len(b);n=len(a);out={}
 if n<30:return {'status':'UNDEFINED_INSUFFICIENT_DAYS','blocks':{}}
 for k in (7,30):
  rng=np.random.default_rng(20261028);values=[]
  # bounded batches avoid giant 10000 x long-series matrices
  for start in range(0,replicates,250):
   size=min(250,replicates-start);beg=rng.integers(0,n,(size,math.ceil(n/k)));ix=((beg[:,:,None]+np.arange(k))%n).reshape(size,-1)[:,:n];aa=a[ix];bb=b[ix]
   if metric=='mean_excess':v=np.mean(aa-bb,axis=1)
   else:
    sa=np.std(aa,axis=1,ddof=1);sb=np.std(bb,axis=1,ddof=1)
    with np.errstate(divide='ignore',invalid='ignore'):v=(np.mean(aa,axis=1)/sa-np.mean(bb,axis=1)/sb)*math.sqrt(365)
   values.extend(v.tolist())
  finite=all(np.isfinite(values));out[str(k)]={'status':'OK' if finite else 'UNDEFINED_VARIANCE','lower_family3':float(np.quantile(values,.05/3)) if finite else None,'ci95':np.quantile(values,[.025,.975]).tolist() if finite else None}
 return {'metric':metric,'replicates':replicates,'seed':20261028,'one_sided_alpha':.05/3,'paired_same_indices':True,'blocks':out,'limitation':'Conditional current-family block resampling, not correction for unknown prior project trials or future success probability'}
