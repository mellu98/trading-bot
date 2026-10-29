"""Single-writer, durable paper order/portfolio owner; broker callbacks are inputs."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from mnq_timestral.schema import Bar, NY, dumps
from mnq_timestral.strategy import Risk, RiskState
from mnq_timestral.evaluation import DISTANCES, POINT_VALUE
from .signals import VwapV1Source

UTC=timezone.utc
TERMINAL={'Filled','Cancelled','ApiCancelled','Inactive','Absent'}


def finite(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('Finite numeric value required')
    return value


def integer(value):
    value=finite(float(value))
    if value!=int(value) or value<0:raise ValueError('Nonnegative whole futures quantity required')
    return int(value)


def identity(config,specs):
    return hashlib.sha256(json.dumps([asdict(config),[asdict(s) for s in specs]],sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    local_symbol: str
    con_id: int
    expiry: str

    def __post_init__(self):
        if self.symbol not in ('MNQ','MES') or not re.fullmatch(self.symbol+r'[HMUZ]\d{1,2}',self.local_symbol):
            raise ValueError('Explicit quarterly micro futures contract required')
        if type(self.con_id) is not int or self.con_id<=0:raise ValueError('Verified positive conId required')
        datetime.strptime(self.expiry,'%Y%m%d')


@dataclass(frozen=True)
class PaperConfig:
    account: str
    host: str = '127.0.0.1'
    port: int = 7497
    client_id: int = 71
    mode: str = 'strict_paper'
    strategy_id: str = 'vwap_v1'
    execution_timezone: str | None = None
    max_contracts: int = 1
    stale_seconds: float = 90.
    daily_max_loss: float = 200.
    max_drawdown: float = 500.
    max_trades: int = 10
    max_consecutive_losses: int = 3

    def __post_init__(self):
        if not re.fullmatch(r'DU\d+',self.account):raise ValueError('Explicit DU paper account allowlist required')
        if self.host!='127.0.0.1' or self.port not in (7497,4002):raise ValueError('Only local paper endpoints permitted')
        if type(self.client_id) is not int or self.client_id<1:raise ValueError('Nonzero dedicated client ID required')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,63}',self.strategy_id):raise ValueError('Explicit signal source identity required')
        if self.mode not in ('strict_paper','technical_paper'):raise ValueError('No live mode exists')
        if type(self.max_contracts) is not int or not 1<=self.max_contracts<=2:raise ValueError('Maximum1–2 contracts, default1')
        if not 0<finite(self.stale_seconds)<=90:raise ValueError('Stale limit must not exceed90seconds')
        if self.execution_timezone not in (None,'UTC'):raise ValueError('Only explicitly configured UTC execution timezone supported')
        self.risk()

    def risk(self):return Risk(self.daily_max_loss,self.max_drawdown,self.max_trades,self.max_consecutive_losses)


class Journal:
    def __init__(self,path,config,specs,lock_root=None):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        locks=Path(lock_root or Path(__file__).resolve().parents[2]/'data/paper-v3/locks');locks.mkdir(parents=True,exist_ok=True)
        self.lock=(locks/(hashlib.sha256(config.account.encode()).hexdigest()+'.lock')).open('a+')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close();raise RuntimeError('Another runtime owns this account') from None
        self.db=sqlite3.connect(path);path.chmod(0o600)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS snapshot (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS journal (seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL)')
        self.identity=identity(config,specs)
        row=self.db.execute('SELECT body FROM snapshot WHERE id=1').fetchone()
        self.state=json.loads(row[0]) if row else {'identity':self.identity,'orders':{},'executions':{},'positions':{},'decisions':[],
          'gross':0.,'day_gross':0.,'date':None,'peak':0.,'halt':None,'blocked_session':None,'stopping':False,
          'day_trades':0,'consecutive':0,'next_id':1,'history':{},'signal_states':{},'seen_candidates':[], 'last_bar':{},'closed_cycles':[],'pending_commissions':{}}
        if self.state['identity']!=self.identity:
            self.close();raise ValueError('Persistent account/config/contract identity mismatch')
        self.save('opened',{'mode':config.mode})

    def save(self,kind,body=None):
        encoded=json.dumps(self.state,sort_keys=True,allow_nan=False)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO snapshot VALUES(1,?)',(encoded,))
            self.db.execute('INSERT INTO journal(kind,body) VALUES(?,?)',(kind,json.dumps(body or {},sort_keys=True,allow_nan=False)))

    def close(self):
        self.db.close();fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close()


class Runtime:
    def __init__(self,config,specs,journal,broker,clock=lambda:datetime.now(UTC),kill_path=None,signal_source=None):
        self.config=config;self.specs={s.symbol:s for s in specs};self.journal=journal;self.state=journal.state
        self.broker=broker;self.clock=clock;self.kill_path=Path(kill_path) if kill_path else None
        self.signal_source=signal_source or VwapV1Source()
        if self.signal_source.identity!=config.strategy_id:raise ValueError('Signal source/config identity mismatch')
        self.ready=False;self.connected=False;self.last_data=None;self.last_data_by_symbol={}

    def net(self,day=False):
        fees=sum(e['fee'] for e in self.state['executions'].values() if not day or e['date']==self.state['date'])
        return self.state['day_gross' if day else 'gross']-fees

    def _roll_day(self,now):
        date=now.astimezone(NY).date().isoformat()
        if date!=self.state['date']:
            self.state.update(date=date,day_gross=0.,day_trades=0,consecutive=0)
            transient={'daily_max_loss','consecutive_losses','session_flatten','stale_data','data_gap'}
            if self.state['halt'] in transient and not self.state['stopping'] and not any(p['quantity'] for p in self.state['positions'].values()) and not any(o['status'] not in TERMINAL for o in self.state['orders'].values()):
                self.state['halt']=None


    def on_execution(self,event):
        eid=event['exec_id']
        if eid in self.state['executions']:
            old=self.state['executions'][eid]
            if any(old[k]!=event[k] for k in ('order_id','symbol','quantity','price','side')):
                self.stop('execution_correction_requires_review')
            return
        order=self.state['orders'].get(str(event['order_id']))
        if not order or event['account']!=self.config.account or event.get('client_id')!=self.config.client_id or event['symbol']!=order['symbol'] or event['side']!=order['side']:
            self.ready=False;self.state['halt']='foreign_execution';self.journal.save('foreign_execution');return
        quantity=integer(event['quantity']);price=finite(event['price'])
        if quantity==0 or price<=0:raise ValueError('Positive fill required')
        self._roll_day(self.clock());date=datetime.fromisoformat(event['at']).astimezone(NY).date().isoformat()
        if date>self.state['date']:raise ValueError('Future execution')
        position=self.state['positions'].setdefault(event['symbol'],{'quantity':0,'average':0.,'mark':price,'cycle_execs':[]})
        old=position['quantity'];change=event['side']*quantity;realized=0.
        if old*change<0:
            closed=min(abs(old),quantity);realized=closed*(price-position['average'])*(1 if old>0 else -1)*POINT_VALUE[event['symbol']]
        if old*change>=0:position['average']=(position['average']*abs(old)+price*quantity)/(abs(old)+quantity)
        elif abs(change)>abs(old):position['average']=price
        position['quantity']=old+change;position['mark']=price
        self.state['gross']+=realized
        if date==self.state['date']:self.state['day_gross']+=realized
        estimate=.25+.35+(.02 if date<'2026-07-01' else .01)
        self.state['executions'][eid]={**event,'date':date,'gross':realized,'fee':estimate*quantity,'fee_source':'estimated_conservative_until_report'}
        position['cycle_execs'].append(eid)
        order['filled']+=quantity
        if order['filled']>order['quantity']:self.state['halt']='overfill';self.state['stopping']=True
        order['status']='Filled' if order['filled']==order['quantity'] else 'Partial'
        if order['role']=='entry' and order['filled']==quantity:self.state['day_trades']+=1
        if old and position['quantity']==0:
            self.state['closed_cycles'].append({'date':date,'exec_ids':position['cycle_execs'][:]})
            position['cycle_execs']=[]
            self._consecutive()
        if 0<order['filled']<order['quantity']:
            self.state['halt']='partial_fill';self.state['stopping']=True
        self.journal.save('execution',{'exec_id':eid})
        pending=self.state['pending_commissions'].pop(eid,None)
        if pending:self.on_commission(pending)
        self.ready=False  # A complete broker snapshot must confirm portfolio/protection.

    def on_commission(self,event):
        amount=finite(event['commission'])
        if event['currency']!='USD' or amount<0:self.stop('invalid_fee_report');return False
        execution=self.state['executions'].get(event['exec_id'])
        if execution is None:
            self.state['pending_commissions'][event['exec_id']]=dict(event)
            self.journal.save('pending_commission',{'exec_id':event['exec_id']});return False
        # Conservative floor prevents delayed/understated commissions loosening risk.
        execution.update(actual_commission=amount,fee=max(execution['fee'],amount),fee_source='actual_with_scenario_floor')
        self._consecutive()
        self.journal.save('commission',{'exec_id':event['exec_id']});return True

    def _consecutive(self):
        count=0
        for cycle in reversed(self.state['closed_cycles']):
            if cycle['date']!=self.state['date']:break
            net=sum(self.state['executions'][e]['gross']-self.state['executions'][e]['fee'] for e in cycle['exec_ids'])
            if net>=0:break
            count+=1
        self.state['consecutive']=count

    def on_status(self,event):
        order=self.state['orders'].get(str(event['id']))
        if order is None:self.ready=False;return
        filled=integer(event.get('filled',0))
        if order['status'] not in TERMINAL:order['status']=event['status']
        order['reported_filled']=max(order.get('reported_filled',0),filled)
        if event['status'] in ('Inactive','Rejected'):
            self.stop('order_rejected')
        self.journal.save('order_status',{'id':event['id'],'status':event['status']})
        self.ready=False

    def reconcile(self,snapshot):
        self.ready=False;self.connected=False
        if snapshot['accounts']!=[self.config.account]:
            self.state['halt']='paper_account_mismatch';self.journal.save('blocked');return
        self.connected=True;self._roll_day(self.clock())
        self.state['next_id']=max(self.state['next_id'],snapshot['next_id'])
        for event in sorted(snapshot['executions'],key=lambda e:(e['at'],e['order_id'],e['exec_id'])):self.on_execution(event)
        for event in snapshot.get('commissions',[]):self.on_commission(event)
        if self.state['halt'] in ('foreign_execution','execution_correction_requires_review'):return
        actual={k:integer(abs(v))*(1 if v>=0 else -1) for k,v in snapshot['positions'].items() if v}
        expected={k:p['quantity'] for k,p in self.state['positions'].items() if p['quantity']}
        if actual!=expected:
            self.state['halt']='portfolio_mismatch';self.journal.save('blocked',{'reason':'portfolio_mismatch'});return
        active={str(o['id']):o for o in snapshot['orders']}
        if any(k not in self.state['orders'] or o.get('client_id')!=self.config.client_id for k,o in active.items()):
            self.state['halt']='foreign_order';self.journal.save('blocked');return
        uncertain_flatten=False
        for key,local in self.state['orders'].items():
            remote=active.get(key)
            if remote:
                keys=('symbol','side','quantity','role','parent_id','limit','stop','ref','account','good_till')
                if any(remote.get(k)!=local.get(k) for k in keys):
                    self.state['halt']='order_identity_mismatch';self.journal.save('blocked');return
                if local['status'] not in TERMINAL:local['status']=remote['status']
            elif local['status'] not in TERMINAL:
                if local['role']=='entry' and local['filled']==0 and local['status']=='Reserved':
                    self.state['halt']=self.state['halt'] or 'uncertain_submission';self.state['stopping']=True
                if local['role']=='flatten' and local['status']=='Reserved' and local['filled']==0:
                    uncertain_flatten=True
                    self.state['halt']='uncertain_flatten_requires_review'
                local['status']='Absent'
        if sum(abs(v) for v in actual.values())>self.config.max_contracts:
            self.state['halt']='position_limit';self.state['stopping']=True
        for symbol,quantity in actual.items():
            children=[o for o in active.values() if o['symbol']==symbol and o['role'] in ('stop','target')]
            good=(len(children)==2 and {o['role'] for o in children}=={'stop','target'}
                  and len({o['parent_id'] for o in children})==1
                  and all(o['status'] in ('Submitted','PreSubmitted') and o['quantity']==abs(quantity) and o['side']==(-1 if quantity>0 else 1) for o in children))
            if not good:self.state['halt']=self.state['halt'] or 'missing_bracket';self.state['stopping']=True
        self.journal.save('reconciled',{'open_orders':len(active),'positions':actual})
        if uncertain_flatten or self.state['halt']=='uncertain_flatten_requires_review':return
        if self.state['stopping']:
            # Never race a still-working flatten. Never submit a second one.
            flatten=[o for o in active.values() if o['role']=='flatten']
            other=[o for o in active.values() if o['role']!='flatten']
            if other:
                for order in other:self.broker.cancel(order['id'])
                return
            if flatten:return
            for symbol,quantity in actual.items():self._flatten(symbol,quantity)
            if not actual:self.state['stopping']=False;self.journal.save('stopped_flat')
            return
        self.ready=self.state['halt'] is None

    def stop(self,reason):
        self.state['halt']=self.state['halt'] or reason;self.state['stopping']=True;self.ready=False
        self.journal.save('stop',{'reason':reason})
        if self.connected:
            for order in self.state['orders'].values():
                if order['status'] not in TERMINAL and order['role']!='flatten':
                    try:self.broker.cancel(order['id'])
                    except (ConnectionError,OSError):self.connected=False;self.ready=False

    def rearm(self,snapshot):
        # Explicit operator action only. Never resets risk counters/peak/P&L or
        # clears uncertain/foreign exposure and global drawdown incidents.
        allowed={'kill','operator_shutdown','stale_data','data_gap','session_flatten'}
        if self.state['halt'] not in allowed:raise ValueError('This halt requires separate risk/incident review')
        if self.kill_path and self.kill_path.exists():raise ValueError('Remove the kill request before explicit re-arm')
        if snapshot['accounts']!=[self.config.account] or any(snapshot['positions'].values()) or snapshot['orders']:
            raise ValueError('Fresh broker-confirmed flat account with no working orders required')
        if any(p['quantity'] for p in self.state['positions'].values()):raise ValueError('Local portfolio mismatch cannot be reset')
        self.reconcile(snapshot)
        if self.state['halt'] not in allowed or self.state['stopping']:raise ValueError('Unresolved reconciliation incident')
        self.state['halt']=None;self.ready=False
        self.journal.save('operator_rearm',{'risk_counters_preserved':True})

    def disconnected(self):
        self.ready=False;self.connected=False
        self.state['blocked_session']=self.clock().astimezone(NY).date().isoformat();self.state['stopping']=True
        self.journal.save('disconnected')

    def _flatten(self,symbol,quantity):
        oid=self.state['next_id'];self.state['next_id']+=1
        order=self._order(oid,symbol,-1 if quantity>0 else 1,min(abs(quantity),self.config.max_contracts),'flatten',0,None,None,True,f'paper-flat-{oid}')
        self.state['orders'][str(oid)]=order;self.journal.save('flatten_intent',order)
        try:self.broker.submit([order])
        except Exception:self.connected=False;self.ready=False  # Intent stays uncertain; no resend.

    def _order(self,oid,symbol,side,quantity,role,parent,limit,stop,transmit,ref):
        return {'id':oid,'symbol':symbol,'side':side,'quantity':quantity,'role':role,'parent_id':parent,
          'limit':limit,'stop':stop,'transmit':transmit,'ref':ref,'status':'Reserved','filled':0,'client_id':self.config.client_id,'account':self.config.account,'good_till':None}

    def _exit_reserve(self,symbol):
        # A simulator may configure higher fees/slippage. Never reserve less
        # than the existing safety floor; broker adapters retain that default.
        floor=.61+.25*POINT_VALUE[symbol]
        estimate=getattr(self.broker,'liquidation_cost_per_contract',None)
        if estimate is None:return floor
        value=finite(estimate(symbol))
        if value<0:raise ValueError('Nonnegative liquidation reserve required')
        return max(floor,value)

    def _mark_risk(self):
        unrealized=sum(p['quantity']*(p['mark']-p['average'])*POINT_VALUE[s]-abs(p['quantity'])*self._exit_reserve(s) for s,p in self.state['positions'].items() if p['quantity'])
        value=self.net()+unrealized;self.state['peak']=max(self.state['peak'],value)
        return RiskState(realized=self.net(day=True),unrealized=unrealized,drawdown=max(0.,self.state['peak']-value),
          trades=self.state['day_trades'],consecutive_losses=self.state['consecutive'],
          positions=int(any(p['quantity'] for p in self.state['positions'].values()) or any(o['status'] not in TERMINAL for o in self.state['orders'].values())),
          kill=bool(self.state['halt']),data_fresh=self.last_data is not None and 0<=(self.clock()-self.last_data).total_seconds()<=self.config.stale_seconds)

    def submit_candidate(self,symbol,side,price,at,key,quantity=1):
        if self.kill_path and self.kill_path.exists():self.stop('kill')
        self._roll_day(self.clock());finite(price)
        if symbol not in self.specs or side not in (-1,1) or price<=0 or price/.25!=round(price/.25):raise ValueError('Invalid candidate')
        quantity=integer(quantity)
        if not quantity:raise ValueError('Positive order size required')
        risk=self._mark_risk();allowed,reason=self.config.risk().allow(risk)
        local=at.astimezone(NY)
        if not self.ready or not self.connected:allowed,reason=False,'not_reconciled'
        if self.config.mode!='technical_paper':allowed,reason=False,'strict_news_and_strategy_not_certified'
        if self.state['blocked_session']==self.state['date']:allowed,reason=False,'session_data_or_disconnect_block'
        if not (9,45)<=(local.hour,local.minute)<(15,30):allowed,reason=False,'outside_entry_window'
        if at.tzinfo is None or not 0<=(self.clock()-at).total_seconds()<=self.config.stale_seconds:allowed,reason=False,'stale_candidate'
        if self.specs[symbol].expiry<=self.clock().strftime('%Y%m%d'):allowed,reason=False,'contract_expired'
        if quantity>self.config.max_contracts:allowed,reason=False,'max_contracts'
        if key in self.state['seen_candidates']:allowed,reason=False,'duplicate_candidate'
        self.state['seen_candidates'].append(key)
        self.state['decisions'].append({'at':at.isoformat(),'symbol':symbol,'side':side,'accepted':allowed,'reason':reason,'mode':self.config.mode,'strategy_approved':False})
        if not allowed:self.journal.save('decision');return False
        oid=self.state['next_id'];self.state['next_id']+=3
        # Marketable bounded limit; stop/target anchored to known limit, NOT an
        # invented future fill. This is an infrastructure execution policy.
        limit=price+side*.25;tp,sl=DISTANCES[symbol];ref=f'paper-{oid}-{key[:20]}'
        orders=[self._order(oid,symbol,side,quantity,'entry',0,limit,None,False,ref),
          self._order(oid+1,symbol,-side,quantity,'target',oid,limit+side*tp,None,False,ref),
          self._order(oid+2,symbol,-side,quantity,'stop',oid,None,limit-side*sl,True,ref)]
        orders[0]['good_till']=(at+timedelta(seconds=60)).strftime('%Y%m%d %H:%M:%S UTC')
        for order in orders:self.state['orders'][str(order['id'])]=order
        self.journal.save('bracket_intent',{'ids':[o['id'] for o in orders]})
        self.ready=False
        try:self.broker.submit(orders)
        except Exception:self.stop('uncertain_submission');self.connected=False
        return True

    def on_bar(self,bar):
        now=self.clock();self._roll_day(now)
        if bar.symbol not in self.specs or bar.contract!=self.specs[bar.symbol].local_symbol:raise ValueError('Contract mismatch')
        if bar.end>now or bar.available_at>now or now-bar.end>timedelta(seconds=self.config.stale_seconds):
            self.stop('stale_or_future_bar');return
        self.last_data=bar.end;self.last_data_by_symbol[bar.symbol]=bar.end
        position=self.state['positions'].get(bar.symbol)
        if position:position['mark']=bar.close
        day=bar.start.astimezone(NY).date().isoformat();history=self.state['history'].setdefault(bar.symbol,[])
        if history and history[-1]['start']==bar.start.isoformat():
            if history[-1]!=json.loads(dumps(bar)):self.stop('conflicting_duplicate_bar')
            return
        if history and datetime.fromisoformat(history[-1]['start'])>=bar.start:self.stop('reordered_bar');return
        if history and datetime.fromisoformat(history[-1]['start']).astimezone(NY).date().isoformat()!=day:
            history.clear();self.state['signal_states'][bar.symbol]={}
        if not history and (bar.start.astimezone(NY).hour,bar.start.astimezone(NY).minute)!=(9,30):
            self.state['blocked_session']=day
        if history and (history[-1]['end']!=bar.start.isoformat() or history[-1]['contract']!=bar.contract):
            self.state['blocked_session']=day;self.stop('data_gap');return
        history.append(json.loads(dumps(bar)));self.state['last_bar'][bar.symbol]=bar.end.isoformat()
        local=self.clock().astimezone(NY)
        if not (9,30)<=(local.hour,local.minute)<(15,30) and (any(p['quantity'] for p in self.state['positions'].values()) or any(o['status'] not in TERMINAL for o in self.state['orders'].values())):self.stop('session_flatten')
        risk=self._mark_risk()
        if risk.consecutive_losses>=self.config.max_consecutive_losses:self.stop('consecutive_losses')
        if any(p['quantity'] and (s not in self.last_data_by_symbol or (self.clock()-self.last_data_by_symbol[s]).total_seconds()>self.config.stale_seconds) for s,p in self.state['positions'].items()) and self.last_data_by_symbol:self.stop('stale_data')
        if risk.drawdown>=self.config.max_drawdown:self.stop('max_drawdown')
        if risk.realized+risk.unrealized<=-self.config.daily_max_loss:self.stop('daily_max_loss')
        if not (9,30)<=(bar.end.astimezone(NY).hour,bar.end.astimezone(NY).minute)<(15,30):
            if any(p['quantity'] for p in self.state['positions'].values()) or any(o['status'] not in TERMINAL for o in self.state['orders'].values()):self.stop('session_flatten')
        if len(history)>=20 and self.state['blocked_session']!=day:
            bb=tuple(Bar.from_dict(b) for b in history)
            side,source_state=self.signal_source.evaluate(bb,now,self.state['signal_states'].get(bar.symbol,{}))
            if side not in (-1,0,1) or not isinstance(source_state,dict):raise ValueError('Invalid signal provider result')
            self.state['signal_states'][bar.symbol]=source_state
            self.journal.save('signal',{'at':bar.end.isoformat(),'side':side})
            if side:self.submit_candidate(bar.symbol,side,bar.close,bar.end,bar.symbol+'-'+bar.end.isoformat())
        self.journal.save('bar',{'symbol':bar.symbol,'at':bar.end.isoformat()})

    def watchdog(self):
        self._roll_day(self.clock())
        if self.kill_path and self.kill_path.exists():self.stop('kill')
        if self.last_data is not None and (self.clock()-self.last_data).total_seconds()>self.config.stale_seconds:
            self.stop('stale_data')
        local=self.clock().astimezone(NY)
        if not (9,30)<=(local.hour,local.minute)<(15,30) and (any(p['quantity'] for p in self.state['positions'].values()) or any(o['status'] not in TERMINAL for o in self.state['orders'].values())):self.stop('session_flatten')
        risk=self._mark_risk()
        if risk.consecutive_losses>=self.config.max_consecutive_losses:self.stop('consecutive_losses')
        if any(p['quantity'] and (s not in self.last_data_by_symbol or (self.clock()-self.last_data_by_symbol[s]).total_seconds()>self.config.stale_seconds) for s,p in self.state['positions'].items()) and self.last_data_by_symbol:self.stop('stale_data')
        if risk.drawdown>=self.config.max_drawdown:self.stop('max_drawdown')
        if risk.realized+risk.unrealized<=-self.config.daily_max_loss:self.stop('daily_max_loss')
