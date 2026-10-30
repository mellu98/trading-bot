from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo
from math import floor,ceil,isfinite
from market_data import validate_append,atr
from market_structure import confirmed_pivots
from liquidity_detector import sweep
from mss_detector import mss
from fvg_detector import fvg
from position_sizing import size
from news_filter import blocked
from risk_manager import gate,RiskState
@dataclass(frozen=True)
class Context:
    equity:float
    spread:float
    quote_time:object
    calendar_updated:object
    events:tuple=()
    currencies:tuple=('USD',)
    risk:RiskState=RiskState()
class Engine:
    """Streaming detector; emits a simulation intent. Caller owns order lifecycle.
    After an intent caller MUST set RiskState.concurrent/reserved_fraction until terminal.
    Only confirmed swing pools; advanced context is specified, not enabled here.
    """
    def __init__(self,cfg):
        if cfg['mode']!='simulation':raise ValueError('simulation only')
        if any(cfg[k] for k in ('htf_filter','premium_discount_filter','daily_bias_filter')):raise ValueError('optional filters not implemented')
        if cfg['fvg_ttl_bars']!=1:raise ValueError('A1 requires immediate FVG')
        self.cfg=cfg;self.bars=[];self.setup=None;self.used=set();self.log=[]
    def record(self,b,code):self.log.append({'ts':b.ts.isoformat(),'reason':code})
    def on_bar(self,b,ctx):
        if not all(isfinite(x) for x in (ctx.equity,ctx.spread)) or ctx.equity<=0 or ctx.spread<0:raise ValueError('invalid account/quote')
        c=self.cfg;validate_append(self.bars,b,c['timeframe_seconds']);prior_atr=atr(self.bars,c['atr_period'])
        pivots=confirmed_pivots(self.bars,c['pivot_left'],c['pivot_right'])
        self.bars.append(b);i=len(self.bars)-1
        if prior_atr is None or prior_atr<=0:self.record(b,'WAIT_WARMUP');return None
        local=b.ts.astimezone(ZoneInfo(c['session_timezone']));clock=local.strftime('%H:%M')
        reason=gate(ctx.risk,c) or blocked(b.ts,ctx.events,ctx.calendar_updated,ctx.currencies,c)
        if not (c['session_start']<=clock<c['session_end'] and local.weekday() in c['weekdays']):reason=reason or 'SKIP_SESSION'
        age=(b.ts-ctx.quote_time).total_seconds()
        if not 0<=age<=c['quote_max_age_seconds']:reason=reason or 'SKIP_STALE_QUOTE'
        if ctx.spread<0 or ctx.spread>c['max_spread_atr']*prior_atr:reason=reason or 'SKIP_SPREAD_TOO_HIGH'
        if c['slippage_price']>c['max_slippage_atr']*prior_atr:reason=reason or 'SKIP_SLIPPAGE'
        if reason:self.setup=None;self.record(b,reason);return None
        s=self.setup
        if s:
            d=s['direction']
            if (b.l<s['extreme'] if d==1 else b.h>s['extreme']):
                self.setup=None;self.record(b,'SKIP_SWEEP_INVALIDATED');return None
            if s['mss_index'] is None:
                if i-s['sweep_index']>c['mss_ttl_bars']:
                    self.setup=None;self.record(b,'SKIP_MSS_EXPIRED');return None
                if mss(b,s['break_level'],d,prior_atr,c):s['mss_index']=i
            else:
                if i-s['mss_index']>c['fvg_ttl_bars']:
                    self.setup=None;self.record(b,'SKIP_FVG_EXPIRED');return None
                gap=fvg(self.bars,d,prior_atr,c)
                # Exactly the displacement/MSS candle is the middle candle.
                if gap and i==s['mss_index']+1:
                    lo,hi=gap;entry=hi-c['entry_fraction']*(hi-lo) if d==1 else lo+c['entry_fraction']*(hi-lo)
                    tick=c['tick_size'];entry=(floor(entry/tick) if d==1 else ceil(entry/tick))*tick
                    buff=max(c['stop_buffer_atr']*prior_atr,c['stop_buffer_spreads']*ctx.spread,tick)
                    stop=s['extreme']-d*buff;stop=(floor(stop/tick) if d==1 else ceil(stop/tick))*tick
                    targets=[p.price-d*tick for p in pivots if p.kind==('HIGH' if d==1 else 'LOW') and d*(p.price-entry)>0 and self.intact(p,i)]
                    targets=[x for x in targets if d*(x-entry)>0]
                    if not targets:self.setup=None;self.record(b,'SKIP_NO_TARGET');return None
                    target=min(targets) if d==1 else max(targets)
                    target=(floor(target/tick) if d==1 else ceil(target/tick))*tick
                    dist=abs(entry-stop)/prior_atr
                    if not c['stop_min_atr']<=dist<=c['stop_max_atr'] or (b.c+ctx.spread/2<=entry if d==1 else b.c-ctx.spread/2>=entry):
                        self.setup=None;self.record(b,'SKIP_ENTRY_OR_STOP');return None
                    sized=size(ctx.equity,entry,stop,target,d,c);self.setup=None
                    if not sized['qty']:self.record(b,sized['reason']);return None
                    sid=sha256(f"{c['version']}|{c['symbol']}|{b.ts.isoformat()}|{d}|{s['sweep_index']}".encode()).hexdigest()
                    signal={'signal_id':sid,'version':c['version'],'symbol':c['symbol'],'direction':d,'known_at':b.ts.isoformat(),'entry':entry,'stop':stop,'target':target,'expires_at':(b.ts+timedelta(seconds=c['order_ttl_bars']*c['timeframe_seconds'])).isoformat(),**sized}
                    self.record(b,'ENTER_LONG' if d==1 else 'ENTER_SHORT');return signal
            if s['mss_index'] is not None and i==s['mss_index']+1:
                self.setup=None;self.record(b,'SKIP_FVG_EXPIRED');return None
            self.record(b,'WAIT_FVG' if s['mss_index'] is not None else 'WAIT_MSS');return None
        candidates=[]
        for p in pivots:
            d=1 if p.kind=='LOW' else -1
            if (p.index,p.kind) in self.used or i-p.index>c['structure_lookback'] or not self.intact(p,i-1):continue
            if sweep(b,p,d,prior_atr,c):
                opposite=[x for x in pivots if x.kind!=p.kind and i-x.index<=c['structure_lookback']]
                if opposite:candidates.append((p,d,max(opposite,key=lambda x:x.index)))
        if len({d for _,d,_ in candidates})>1:self.record(b,'SKIP_DUAL_SWEEP');return None
        if candidates:
            p,d,op=max(candidates,key=lambda x:x[0].index);self.used.add((p.index,p.kind))
            self.setup={'direction':d,'sweep_index':i,'extreme':b.l if d==1 else b.h,'break_level':op.price,'mss_index':None}
            self.record(b,'SWEEP_CONFIRMED')
        else:self.record(b,'WAIT_SWEEP')
        return None
    def intact(self,p,end):
        segment=self.bars[p.known_at+1:end+1]
        return all(x.h<p.price if p.kind=='HIGH' else x.l>p.price for x in segment)
