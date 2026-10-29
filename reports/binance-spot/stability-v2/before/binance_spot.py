"""Opt-in public Spot seam for the existing V3 runtime, journal and Risk.

No account, credential, private path, remote order, leverage or short operation.
The only execution is local arithmetic against received public bid/ask quotes.
"""
from collections import Counter,deque
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal,ROUND_DOWN
from types import SimpleNamespace
import asyncio,json,math,time
from urllib.parse import urlencode
import aiohttp
from mnq_paper.core import Runtime
from mnq_timestral.strategy import Risk,RiskState

UTC=timezone.utc
REST='https://data-api.binance.vision'
WS='wss://data-stream.binance.vision/stream?streams=btcusdt@trade/btcusdt@bookTicker/btcusdt@kline_1m'
SYMBOL='BTCUSDT'

def dec(value):
    if isinstance(value,bool):raise ValueError('Boolean monetary value')
    x=Decimal(str(value))
    if not x.is_finite():raise ValueError('Nonfinite monetary value')
    return x

def utc(ns=None):return datetime.fromtimestamp((time.time_ns() if ns is None else ns)/1e9,UTC).isoformat()
def ms_ns(value):
    if type(value) is not int or not 1_500_000_000_000<=value<10_000_000_000_000:raise ValueError('Explicit UNIX milliseconds required')
    return value*1_000_000

@dataclass(frozen=True)
class SpotConfig:
    account:str='LOCAL_BINANCE_SPOT'
    mode:str='technical_paper'
    strategy_id:str='btcusdt_technical_once'
    client_id:int=0
    max_contracts:int=1
    stale_seconds:float=2.
    daily_max_loss:float=10.
    max_drawdown:float=20.
    max_trades:int=1
    max_consecutive_losses:int=1
    virtual_cash:str='1000'
    entry_cash_cap:str='100'
    fee_rate:str='0.001'
    slippage_rate:str='0.0001'
    stop_fraction:str='0.005'
    deadline_seconds:int=60
    def __post_init__(self):
        if self.account!='LOCAL_BINANCE_SPOT' or self.mode!='technical_paper':raise ValueError('Local technical Spot only')
        if any(dec(v)<=0 for v in (self.virtual_cash,self.entry_cash_cap,self.fee_rate,self.stop_fraction)):raise ValueError('Positive settings required')
        if dec(self.entry_cash_cap)>100 or self.daily_max_loss>10 or self.max_drawdown>20 or self.deadline_seconds!=60:raise ValueError('Technical ceilings fixed')
        self.risk()
    def risk(self):return Risk(self.daily_max_loss,self.max_drawdown,self.max_trades,self.max_consecutive_losses)

@dataclass(frozen=True)
class SpotSpec:
    symbol:str
    tick_text:str
    step_text:str
    min_qty_text:str
    max_qty_text:str
    min_notional_text:str
    @property
    def tick(self):return dec(self.tick_text)
    @property
    def step(self):return dec(self.step_text)
    @property
    def min_qty(self):return dec(self.min_qty_text)
    @property
    def max_qty(self):return dec(self.max_qty_text)
    @property
    def min_notional(self):return dec(self.min_notional_text)
    @classmethod
    def from_exchange(cls,payload):
        matches=[s for s in payload['symbols'] if s['symbol']==SYMBOL]
        if len(matches)!=1:raise ValueError('BTCUSDT metadata required')
        s=matches[0];f={v['filterType']:v for v in s['filters']}
        if s['status']!='TRADING' or s['baseAsset']!='BTC' or s['quoteAsset']!='USDT' or not s.get('isSpotTradingAllowed'):raise ValueError('Trading Spot BTC/USDT required')
        # MARKET_LOT_SIZE can legitimately have stepSize=0. LOT_SIZE is the
        # actual nonzero Spot quantity grid, never a CME contract multiplier.
        lot=f['LOT_SIZE'];notional=f.get('NOTIONAL',f.get('MIN_NOTIONAL',{}))
        result=cls(SYMBOL,f['PRICE_FILTER']['tickSize'],lot['stepSize'],lot['minQty'],lot['maxQty'],notional['minNotional'])
        if min(result.tick,result.step,result.min_qty,result.min_notional)<=0:raise ValueError('Positive exchange grids required')
        return result

class PublicREST:
    PATHS={'/api/v3/ping':set(),'/api/v3/time':set(),'/api/v3/exchangeInfo':{'symbol'},
      '/api/v3/ticker/bookTicker':{'symbol'},'/api/v3/trades':{'symbol','limit'},'/api/v3/klines':{'symbol','interval','startTime','endTime','limit'}}
    def __init__(self,session,evidence):self.session=session;self.evidence=evidence
    @classmethod
    def validate(cls,method,path,params):
        if method!='GET' or path not in cls.PATHS or set(params)-cls.PATHS[path]:raise ValueError('Public GET allowlist only')
        if 'symbol' in params and params['symbol']!=SYMBOL:raise ValueError('BTCUSDT only')
        if 'symbol' in cls.PATHS[path] and params.get('symbol')!=SYMBOL:raise ValueError('Explicit symbol required')
        if 'interval' in params and params['interval']!='1m':raise ValueError('Native 1m only')
        if 'limit' in params and (type(params['limit']) is not int or not 1<=params['limit']<=1000):raise ValueError('Bounded public request')
        for k in ('startTime','endTime'):
            if k in params:ms_ns(params[k])
        return True
    async def get(self,path,**params):
        self.validate('GET',path,params);start=time.time_ns();mono=time.monotonic_ns()
        async with self.session.get(REST+path,params=params,allow_redirects=False,timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status!=200:raise ConnectionError('Public REST HTTP '+str(response.status))
            data=await response.json()
        item={'method':'GET','origin':REST,'path':path,'params':params,'request_start_ns':start,'response_received_ns':time.time_ns(),
          'request_start_mono_ns':mono,'response_received_mono_ns':time.monotonic_ns(),'status':200,'data':data}
        self.evidence(item);return item


def local_quote(data,receipt_ns,receipt_mono):
    if data.get('s')!=SYMBOL or type(data.get('u')) is not int or data['u']<0:raise ValueError('Invalid book identity')
    bid,ask=dec(data['b']),dec(data['a'])
    if bid<=0 or ask<bid or min(dec(data['B']),dec(data['A']))<=0:raise ValueError('Positive uncrossed book required')
    return {'symbol':SYMBOL,'update_id':data['u'],'bid':str(bid),'ask':str(ask),'bid_qty':data['B'],'ask_qty':data['A'],
      'received_ns':receipt_ns,'received_mono_ns':receipt_mono,'received_at':utc(receipt_ns),'source_ns':None,
      'timestamp_note':'bookTicker has no exchange E/T timestamp; receipt freshness only, not transport latency',
      'origin':'BINANCE_PUBLIC_WEBSOCKET_BOOKTICKER','spread_bps':str((ask-bid)/((ask+bid)/2)*10000)}

class LocalExecution:
    """Existing Runtime cancellation seam; never performs any I/O."""
    def __init__(self,runtime):self.runtime=runtime
    def cancel(self,oid):
        o=self.runtime.state['orders'].get(str(oid))
        if o and o['status']!='Filled':o['status']='Cancelled'

class SpotRuntime(Runtime):
    def __init__(self,config,spec,journal):
        super().__init__(config,[spec],journal,None,signal_source=SimpleNamespace(identity=config.strategy_id))
        self.spec=spec;self.broker=LocalExecution(self);self.quote=None;self.trade_fresh=False;self.certificate={'passed':False}
        self.state.setdefault('binance_spot',{'cash':config.virtual_cash,'position':None,'budget_spent':False,'buy_count':0,'sell_count':0,
          'net':'0','fees':'0','gross':'0','pending_exit':None,'peak_net':'0','max_drawdown':'0','equity':[],'events':[],
          'last_trade_id':None,'last_book_id':None,'closed_bar':None,'roundtrip':None,'restart_count':0})
        self.spot['restart_count']+=1
        self.journal.save('spot_recovered',{'open_position':self.spot['position'] is not None,'budget_spent':self.spot['budget_spent'],
          'protection':self.spot['position'],'restart_count':self.spot['restart_count']})
    @property
    def spot(self):return self.state['binance_spot']
    def net(self,day=False):
        return float(sum((dec(e['gross_exact'])-dec(e['fee_exact']) for e in self.state['executions'].values() if not day or e['date']==datetime.now(UTC).date().isoformat()),Decimal(0)))
    def _roll_day(self,now):
        date=now.astimezone(UTC).date().isoformat()
        if date!=self.state['date']:self.state.update(date=date,day_gross=0.,day_trades=0,consecutive=0)
    def quote_fresh(self,for_exit=False):
        return self.connected and self.quote is not None and 0<=time.monotonic_ns()-self.quote['received_mono_ns']<=2_000_000_000 and (for_exit or dec(self.quote['spread_bps'])<=10)
    def _mark_risk(self):
        p=self.spot['position'];unreal=Decimal(0)
        if p and self.quote:
            qty=dec(p['quantity']);fill=dec(self.quote['bid'])*(1-dec(self.config.slippage_rate))
            unreal=qty*(fill-dec(p['entry_fill']))-qty*fill*dec(self.config.fee_rate)
        net=dec(str(self.net()))+unreal;peak=max(dec(self.spot['peak_net']),net);dd=peak-net
        self.spot['peak_net']=str(peak);self.spot['max_drawdown']=str(max(dec(self.spot['max_drawdown']),dd));self.state['peak']=float(peak)
        return RiskState(realized=self.net(day=True),unrealized=float(unreal),drawdown=float(max(Decimal(0),dd)),trades=self.state['day_trades'],
          consecutive_losses=self.state['consecutive'],positions=int(p is not None),kill=bool(self.state['halt']),data_fresh=self.quote_fresh() and self.trade_fresh)
    def _fill(self,order,qty,price,fee,gross,quote):
        oid=order['id'];eid='local-spot-'+str(oid);now=utc();date=now[:10]
        if eid in self.state['executions']:raise ValueError('Duplicate local fill')
        self.state['executions'][eid]={'exec_id':eid,'order_id':oid,'symbol':SYMBOL,'quantity':str(qty),'price':str(price),'side':order['side'],
          'at':now,'date':date,'account':self.config.account,'client_id':0,'gross':float(gross),'fee':float(fee),
          'gross_exact':str(gross),'fee_exact':str(fee),'notional':str(qty*price),'quote':dict(quote),'execution':'LOCAL_SIMULATED_NOT_BINANCE_ORDER'}
        order.update(status='Filled',filled=str(qty));self.journal.save('spot_execution',self.state['executions'][eid]);return eid
    def submit_technical(self):
        self._roll_day(datetime.now(UTC));risk=self._mark_risk();allowed,reason=self.config.risk().allow(risk)
        if self.spot['budget_spent']:return False
        if not(self.ready and self.connected and self.certificate.get('passed') and self.quote_fresh() and self.trade_fresh):return False
        if not allowed:
            self.journal.save('spot_risk_rejected',{'reason':reason});return False
        q=self.quote;price=dec(q['ask'])*(1+dec(self.config.slippage_rate));budget=min(dec(self.config.entry_cash_cap),dec(self.spot['cash']))
        qty=(budget/(price*(1+dec(self.config.fee_rate)))/self.spec.step).to_integral_value(rounding=ROUND_DOWN)*self.spec.step
        if qty<self.spec.min_qty or qty>self.spec.max_qty or qty*price<self.spec.min_notional or qty>dec(q['ask_qty']):return False
        fee=qty*price*dec(self.config.fee_rate);cash=qty*price+fee;stop=(price*(1-dec(self.config.stop_fraction))/self.spec.tick).to_integral_value(rounding=ROUND_DOWN)*self.spec.tick
        stop_exit=stop*(1-dec(self.config.slippage_rate));initial_risk=qty*(price-stop_exit)+fee+qty*stop_exit*dec(self.config.fee_rate)
        if cash>budget or initial_risk>min(dec(str(self.config.daily_max_loss))+dec(str(self.net(day=True))),dec(str(self.config.max_drawdown))-dec(str(risk.drawdown))):return False
        with self.journal.bar_transaction():
            self.spot['entry_certificate']=dict(self.certificate);self.spot['budget_spent']=True;self.state['seen_candidates'].append('ONE_LIFETIME_TECHNICAL_BUY')
            oid=self.state['next_id'];self.state['next_id']+=3;order=self._order(oid,SYMBOL,1,str(qty),'entry',0,str(price),None,True,'spot-technical-once')
            self.state['orders'][str(oid)]=order;self.journal.save('spot_entry_intent',{'order':order,'quote':q,'certificate':self.certificate})
            eid=self._fill(order,qty,price,fee,Decimal(0),q)
            for n,role in ((1,'stop'),(2,'time_exit')):
                child=self._order(oid+n,SYMBOL,-1,str(qty),role,oid,None,str(stop) if role=='stop' else None,True,'spot-protection')
                child['status']='Submitted';self.state['orders'][str(oid+n)]=child
            self.spot['cash']=str(dec(self.spot['cash'])-cash);self.spot['fees']=str(dec(self.spot['fees'])+fee);self.spot['buy_count']+=1
            self.spot['position']={'quantity':str(qty),'entry_fill':str(price),'entry_fee':str(fee),'entry_cash':str(cash),'entry_quote':dict(q),
              'entry_at':utc(),'entry_ns':time.time_ns(),'deadline_ns':time.time_ns()+60_000_000_000,'stop':str(stop),'entry_exec':eid,
              'initial_modeled_risk_usdt':str(initial_risk),'risk_not_guaranteed':'Price gaps and quote execution can exceed initial modeled loss'}
            self.state['positions'][SYMBOL]={'quantity':str(qty),'average':str(price),'mark':q['bid'],'cycle_execs':[eid]}
            self.state['day_trades']+=1;self.spot['events'].append({'at':utc(),'event':'LOCAL_BUY','quantity':str(qty),'price':str(price),'fee':str(fee)})
            self.state['decisions'].append({'at':utc(),'symbol':SYMBOL,'side':'BUY','accepted':True,'reason':'ONE_TECHNICAL_FEED_CERTIFIED_TEST','strategy_approved':False})
            self.journal.save('spot_open_protected',{'position':self.spot['position'],'cash':self.spot['cash']})
        return True
    def request_exit(self,reason):
        if self.spot['position'] and not self.spot['pending_exit']:
            self.spot['pending_exit']=reason;self.journal.save('spot_pending_protective_exit',{'reason':reason})
    def protect(self):
        p=self.spot['position']
        if not p:return False
        if self.state['halt']:self.request_exit(self.state['halt'])
        if self.quote_fresh(for_exit=True) and dec(self.quote['bid'])<=dec(p['stop']):self.request_exit('protective_stop')
        if time.time_ns()>=p['deadline_ns']:self.request_exit('time_exit')
        risk=self._mark_risk()
        if risk.drawdown>=self.config.max_drawdown:self.stop('max_drawdown');self.request_exit('max_drawdown')
        if risk.realized+risk.unrealized<=-self.config.daily_max_loss:self.stop('daily_max_loss');self.request_exit('daily_max_loss')
        if not self.spot['pending_exit'] or not self.quote_fresh(for_exit=True):return False
        # Exits never require entry certificate, news, strategy or unspent budget.
        q=self.quote;qty=dec(p['quantity'])
        if qty>dec(q['bid_qty']):return False
        price=dec(q['bid'])*(1-dec(self.config.slippage_rate));fee=qty*price*dec(self.config.fee_rate);gross=qty*(price-dec(p['entry_fill']));reason=self.spot['pending_exit']
        with self.journal.bar_transaction():
            oid=self.state['next_id'];self.state['next_id']+=1;order=self._order(oid,SYMBOL,-1,str(qty),'flatten',0,None,None,True,'spot-'+reason)
            self.state['orders'][str(oid)]=order;eid=self._fill(order,qty,price,fee,gross,q)
            self.spot['cash']=str(dec(self.spot['cash'])+qty*price-fee);self.spot['fees']=str(dec(self.spot['fees'])+fee);self.spot['gross']=str(dec(self.spot['gross'])+gross)
            self.spot['net']=str(dec(self.spot['cash'])-dec(self.config.virtual_cash));self.spot['sell_count']+=1
            self.spot['roundtrip']={**p,'symbol':SYMBOL,'side':'LONG','exit_at':utc(),'exit_reason':reason,'exit_fill':str(price),'exit_fee':str(fee),
              'exit_quote':dict(q),'gross':str(gross),'fees':str(dec(p['entry_fee'])+fee),'net':str(gross-dec(p['entry_fee'])-fee),'execution':'LOCAL_SIMULATED_PUBLIC_BOOK'}
            if dec(self.spot['roundtrip']['net'])!=dec(self.spot['net']):raise ValueError('Cash/PnL reconciliation failed')
            self.state['positions'][SYMBOL].update(quantity='0',mark=q['bid'],cycle_execs=[])
            self.state['gross']=float(dec(self.spot['gross']));self.state['day_gross']+=float(gross)
            self.state['closed_cycles'].append({'date':self.state['date'],'exec_ids':[p['entry_exec'],eid]});self._consecutive()
            for o in self.state['orders'].values():
                if o['status']=='Submitted':o['status']='Cancelled'
            self.spot['position']=None;self.spot['pending_exit']=None;self.spot['events'].append({'at':utc(),'event':'LOCAL_SELL','reason':reason,'net':self.spot['net']})
            self.journal.save('spot_flat_reconciled',{'roundtrip':self.spot['roundtrip'],'cash':self.spot['cash']})
        return True

class Feed:
    def __init__(self,runtime):
        self.r=runtime;self.started=time.monotonic_ns();self.stats=Counter();self.books=deque(maxlen=4096);self.trades=deque(maxlen=4096)
        self.closed=None;self.rest_checks={};self.offset_ns=0;self.uncertainty_ns=None;self.last_trade_receipt=None;self.missing=set();self.delays=deque(maxlen=2048)
        self.ages=deque(maxlen=2048);self.processing_ns=0;self.last_kline=None;self.current_stream_ok=False
    def connected(self):
        self.started=time.monotonic_ns();self.closed=None;self.rest_checks={};self.r.quote=None;self.r.trade_fresh=False;self.last_trade_receipt=None;self.r.connected=True;self.r.ready=False;self.current_stream_ok=True
        self.r.certificate={'passed':False,'reason':'60s_and_native_closed_candle_required'}
    def disconnected(self,reason):
        self.current_stream_ok=False;self.r.connected=False;self.r.ready=False;self.r.trade_fresh=False;self.r.quote=None;self.r.certificate={'passed':False,'reason':reason}
        self.r.request_exit('feed_disconnect');self.r.journal.save('public_stream_disconnected',{'reason':reason})
    def trade_is_fresh(self):
        if not self.trades or self.uncertainty_ns is None or self.last_trade_receipt is None:return False
        t=self.trades[-1];age=time.time_ns()+self.offset_ns-t['source_ns']
        return 0<=time.monotonic_ns()-self.last_trade_receipt<=2_000_000_000 and age+self.uncertainty_ns<=2_000_000_000 and age+self.uncertainty_ns>=0
    def process(self,item,receipt_ns,receipt_mono):
        delay=time.monotonic_ns()-receipt_mono;self.delays.append(delay/1e6);self.processing_ns=delay
        if delay<0 or delay>250_000_000:
            self.stats['processing_delay_rejections']+=1;self.r.ready=False;self.started=time.monotonic_ns();self.rest_checks={};self.r.request_exit('processing_delay');return False
        if self.current_stream_ok and receipt_mono<self.started:
            self.stats['previous_connection_events_discarded']+=1;return False
        stream=item.get('stream');d=item.get('data',{});r=self.r
        if d.get('s')!=SYMBOL:raise ValueError('Unexpected symbol')
        if stream=='btcusdt@bookTicker':
            q=local_quote(d,receipt_ns,receipt_mono);last=r.spot['last_book_id']
            if last is not None and q['update_id']<=last:self.stats['book_duplicates']+=1;return False
            r.spot['last_book_id']=q['update_id'];r.quote=q;self.books.append(q);self.stats['book']+=1
        elif stream=='btcusdt@trade':
            if d.get('e')!='trade' or type(d.get('t')) is not int:raise ValueError('Native trade required')
            source=ms_ns(d['T']);event=ms_ns(d['E']);tid=d['t'];last=r.spot['last_trade_id']
            if dec(d['p'])<=0 or dec(d['q'])<=0:raise ValueError('Positive trade')
            if last is not None and tid<=last:self.stats['trade_duplicates']+=1;return False
            if last is not None and tid!=last+1:
                self.stats['trade_gaps']+=1
                if tid-last>1000:self.stats['unrepairable_gap']+=1
                else:self.missing.update(range(last+1,tid))
                r.ready=False
            r.spot['last_trade_id']=tid;self.last_trade_receipt=receipt_mono
            self.trades.append({'id':tid,'price':d['p'],'qty':d['q'],'source_ns':source,'event_ns':event,'receipt_ns':receipt_ns,'receipt_mono_ns':receipt_mono})
            self.ages.append((receipt_ns+self.offset_ns-source)/1e6);self.stats['trade']+=1
        elif stream=='btcusdt@kline_1m':
            if d.get('e')!='kline':raise ValueError('Native kline required')
            ms_ns(d['E']);k=d['k'];ms_ns(k['t']);ms_ns(k['T'])
            if k['s']!=SYMBOL or k['i']!='1m' or k['T']!=k['t']+59999 or type(k['x']) is not bool:raise ValueError('Native 1m bounds/finality')
            if min(dec(k[n]) for n in ('o','h','l','c'))<=0 or dec(k['v'])<0 or not dec(k['l'])<=min(dec(k['o']),dec(k['c']))<=max(dec(k['o']),dec(k['c']))<=dec(k['h']):raise ValueError('Invalid native OHLCV')
            if k['x']:
                if self.closed and k['t']<=self.closed['t']:self.stats['bar_duplicates']+=1;return False
                if self.closed and k['t']!=self.closed['t']+60000:self.stats['bar_gaps']+=1
                self.closed=dict(k);r.spot['closed_bar']={**k,'receipt_ns':receipt_ns,'receipt_mono_ns':receipt_mono,'event_ns':ms_ns(d['E']),'signal_ready':True}
                self.stats['closed_bars']+=1
            else:self.stats['forming_bars']+=1
        else:raise ValueError('Unsubscribed stream')
        r.trade_fresh=self.trade_is_fresh();return True
    def certified(self):
        self.r.trade_fresh=self.trade_is_fresh()
        return bool(self.current_stream_ok and time.monotonic_ns()-self.started>=60_000_000_000 and self.closed and self.r.quote_fresh() and self.r.trade_fresh
          and not self.missing and not self.stats['unrepairable_gap'] and not self.stats['bar_gaps'] and self.processing_ns<=250_000_000
          and self.rest_checks.get('passed') and time.monotonic_ns()-self.rest_checks.get('checked_mono_ns',0)<=10_000_000_000)
    def certificate(self):
        passed=self.certified();age=(time.monotonic_ns()-self.started)/1e9
        return {'passed':passed,'actual_connected_seconds':age,'native_closed_candles':self.stats['closed_bars'],'stats':dict(self.stats),
          'book_receipt_fresh':self.r.quote_fresh(),'trade_fresh':self.r.trade_fresh,'max_spread_bps':10,'max_fresh_seconds':2,
          'clock_offset_ms':self.offset_ns/1e6,'clock_uncertainty_ms':None if self.uncertainty_ns is None else self.uncertainty_ns/1e6,
          'source_age_not_network_latency':True,'book_source_timestamp':'NOT_PROVIDED_BY_BINANCE','rest_comparison':self.rest_checks,
          'processing_delay_ms':{'last':self.processing_ns/1e6,'max_observed':max(self.delays,default=0)},
          'source_age_ms':{'last':self.ages[-1] if self.ages else None,'min':min(self.ages,default=0),'max':max(self.ages,default=0)},
          'strict_news':'BLOCKED_UNCERTIFIED','economic_strategy':'NONE_TECHNICAL_ONLY','timestral':'DISABLED'}
    async def compare_rest(self,http):
        stamp=await http.get('/api/v3/time');server=ms_ns(stamp['data']['serverTime']);mid=(stamp['request_start_ns']+stamp['response_received_ns'])//2
        self.offset_ns=server-mid;self.uncertainty_ns=(stamp['response_received_ns']-stamp['request_start_ns'])//2
        trades=await http.get('/api/v3/trades',symbol=SYMBOL,limit=1000)
        known={t['id']:t for t in trades['data']};shared=[t for t in self.trades if t['id'] in known]
        coherent=bool(shared) and all(dec(t['price'])==dec(known[t['id']]['price']) and dec(t['qty'])==dec(known[t['id']]['qty']) and t['source_ns']==ms_ns(known[t['id']]['time']) for t in shared)
        repaired=self.missing.intersection(known)
        if coherent:self.missing.difference_update(repaired)
        book=await http.get('/api/v3/ticker/bookTicker',symbol=SYMBOL)
        # No invented exchange timestamp: compare snapshots observed within the
        # actual request interval plus a fixed2s receipt uncertainty envelope.
        bd=book['data'];book_match=any(q['received_mono_ns']>=book['request_start_mono_ns']-2_000_000_000 and q['received_mono_ns']<=book['response_received_mono_ns']+2_000_000_000
          and dec(q['bid'])==dec(bd['bidPrice']) and dec(q['ask'])==dec(bd['askPrice']) for q in self.books)
        candle_ok=False;kline_evidence=None
        closed=dict(self.closed) if self.closed else None
        if closed:
            kr=await http.get('/api/v3/klines',symbol=SYMBOL,interval='1m',startTime=closed['t'],limit=1);rows=kr['data']
            candle_ok=len(rows)==1 and rows[0][0]==closed['t'] and rows[0][6]==closed['T'] and all(dec(rows[0][i])==dec(closed[k]) for i,k in [(1,'o'),(2,'h'),(3,'l'),(4,'c'),(5,'v')])
            kline_evidence={'native_close_start_ms':closed['t'],'rest_row':rows[0] if rows else None,'matches':candle_ok}
        self.rest_checks={'passed':coherent and book_match and candle_ok,'trades_shared':len(shared),'trade_values_match':coherent,'missing_trade_ids_remaining':len(self.missing),
          'trade_gaps_repaired':len(repaired),'book_bid_ask_match':book_match,'closed_candle_match':candle_ok,'candle':kline_evidence,
          'request_intervals':[{'path':v['path'],'start_ns':v['request_start_ns'],'received_ns':v['response_received_ns']} for v in (stamp,trades,book)],
          'checked_mono_ns':time.monotonic_ns(),'checked_at':utc()}
        return self.rest_checks
