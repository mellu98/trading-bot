"""Official IB1051.01 socket adapter. Paper-only, no credentials or live branch."""
from decimal import Decimal
from datetime import datetime, timezone
import queue
import hashlib
import importlib.metadata
from pathlib import Path
import json
import threading
import time
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.order_cancel import OrderCancel
from ibapi.execution import ExecutionFilter
from .core import integer, finite
from .session import SessionProof
from ibapi.protobuf.ConfigRequest_pb2 import ConfigRequest

UTC=timezone.utc
time_module=time.monotonic


class _Client(EWrapper,EClient):
    def __init__(self,owner):
        EClient.__init__(self,self);self.owner=owner

    def nextValidId(self,orderId):self.owner.next_id=orderId
    def managedAccounts(self,accountsList):self.owner.accounts=sorted(x for x in accountsList.split(',') if x)
    def connectionClosed(self):self.owner.events.put({'type':'disconnect'})
    def currentTime(self,time):
        self.owner.server_time=time;self.owner.last_heartbeat=time_module()
    def error(self,reqId,errorTime,errorCode,errorString,advancedOrderRejectJson=''):
        # Never log raw SDK diagnostics (may include account/session information).
        if errorCode in (2104,2106,2107,2108,2158):return
        self.owner.events.put({'type':'error','code':errorCode,'request_id':reqId})
    def configResponseProtoBuf(self,response):
        if response.reqId!=8999 or not response.HasField('api') or not response.api.HasField('settings'):return
        settings=response.api.settings
        if not settings.HasField('readOnlyApi') or not settings.HasField('socketPort'):return
        self.owner.api_config={'read_only':settings.readOnlyApi,'port':settings.socketPort,'received_at':time.monotonic()}
    def accountSummary(self,reqId,account,tag,value,currency):
        if account==self.owner.config.account:self.owner.account_values[tag]={'value':value,'currency':currency}
    def accountSummaryEnd(self,reqId):self.owner.account_end=True
    def contractDetails(self,reqId,details):self.owner.details.setdefault(reqId,[]).append(details)
    def contractDetailsEnd(self,reqId):self.owner.details_done.add(reqId)
    def position(self,account,contract,position,avgCost):
        if account!=self.owner.config.account:return
        self.owner.positions[self.owner.symbol(contract)]=float(position)
    def positionEnd(self):self.owner.ends.add('positions')
    def openOrder(self,orderId,contract,order,orderState):
        self.owner.open_orders[orderId]=self.owner.from_order(orderId,contract,order,orderState)
    def openOrderEnd(self):self.owner.ends.add('orders')
    def orderStatus(self,orderId,status,filled,remaining,avgFillPrice,permId,parentId,lastFillPrice,clientId,whyHeld,mktCapPrice):
        self.owner.events.put({'type':'status','id':orderId,'status':status,'filled':float(filled),'remaining':float(remaining)})
    def execDetails(self,reqId,contract,execution):
        try:at=self.owner.execution_time(execution.time,self.owner.config.execution_timezone)
        except ValueError:
            self.owner.events.put({'type':'error','code':1000001,'request_id':reqId});return
        event={'exec_id':execution.execId,'order_id':execution.orderId,'symbol':self.owner.symbol(contract),
          'account':execution.acctNumber,'client_id':execution.clientId,'quantity':float(execution.shares),
          'side':1 if execution.side=='BOT' else -1,'price':float(execution.price),
          # Attribution day must come from the broker execution, not receipt time.
          'at':at}
        self.owner.executions[event['exec_id']]=event
        self.owner.events.put({'type':'execution','value':event})
    def execDetailsEnd(self,reqId):
        if reqId==self.owner.exec_request:self.owner.ends.add('executions')
    def commissionAndFeesReport(self,report):
        event={'exec_id':report.execId,'commission':float(report.commissionAndFees),'currency':report.currency}
        self.owner.commissions[report.execId]=event;self.owner.events.put({'type':'commission','value':event})
    def realtimeBar(self,reqId,time,open_,high,low,close,volume,wap,count):
        self.owner.events.put({'type':'five_seconds','symbol':self.owner.streams[reqId],'start_ns':int(time)*10**9,
          'open':float(open_),'high':float(high),'low':float(low),'close':float(close),'volume':float(volume)})


class IBPaper:
    kind='OFFICIAL_IB_SDK_NOT_YET_REAL_PAPER_CERTIFIED'
    def __init__(self,config,specs,operation='read_only',session_proof=None):
        self.config=config;self.specs={s.symbol:s for s in specs};self.events=queue.Queue();self.streams={}
        self.app=None;self.thread=None;self.verified=False;self.generation=7000
        if operation not in ('read_only','paper_orders'):raise ValueError('Unknown paper adapter operation')
        self.operation=operation;self.paper_proof=SessionProof(session_proof) if session_proof else None
        self.api_config=None;self.last_heartbeat=0.;self.account_values={};self.account_end=False
        self.positions={};self.open_orders={};self.executions={};self.commissions={};self.ends=set()
        self.accounts=[];self.next_id=None;self.server_time=None

    @staticmethod
    def execution_time(value,configured_timezone=None):
        # API configured to UTC login/operator timezone. Reject ambiguous stamps.
        # IB may use double-space between date/time or a named UTC suffix.
        fields=value.split()
        if len(fields)==2 and configured_timezone=='UTC':fields.append('UTC')
        if len(fields)!=3 or fields[2] not in ('UTC','Etc/UTC','GMT'):
            raise ValueError('IB execution timestamps require explicit UTC; set TWS API operator timezone UTC')
        return datetime.strptime(fields[0]+' '+fields[1],'%Y%m%d %H:%M:%S').replace(tzinfo=UTC).isoformat()

    def symbol(self,contract):
        return next((s.symbol for s in self.specs.values() if s.con_id==contract.conId),f'foreign:{contract.conId}')

    def contract(self,symbol):
        s=self.specs[symbol];c=Contract();c.conId=s.con_id;c.secType='FUT';c.exchange='CME';c.currency='USD'
        c.symbol=s.symbol;c.localSymbol=s.local_symbol;c.lastTradeDateOrContractMonth=s.expiry
        c.multiplier='2' if s.symbol=='MNQ' else '5';return c

    def _wait(self,predicate,timeout=10):
        deadline=time.monotonic()+timeout
        while not predicate():
            if time.monotonic()>deadline:raise TimeoutError('IB protocol barrier timed out')
            time.sleep(.02)

    @staticmethod
    def verify_sdk():
        import ibapi
        base=Path(__file__).resolve().parents[2]/'adapters/ib_paper/vendor'
        provenance=json.loads((base/'provenance.json').read_text())
        if importlib.metadata.version('ibapi')!='1051.1':raise ValueError('Pinned official SDK version required')
        if hashlib.sha256((base/'twsapi_macunix.1051.01.zip').read_bytes()).hexdigest()!=provenance['archive_sha256']:raise ValueError('Official SDK archive changed')
        installed=Path(ibapi.__file__).parent.parent
        for name,expected in provenance['files'].items():
            if hashlib.sha256((installed/name).read_bytes()).hexdigest()!=expected:raise ValueError('Installed IB SDK differs from verified source')
        return len(provenance['files'])

    def connect(self):
        self.verify_sdk()
        if self.thread and self.thread.is_alive():raise ConnectionError('Previous reader has not stopped; reconnect forbidden')
        if self.operation=='paper_orders':
            if self.paper_proof is None:raise ValueError('Independent Paper UI evidence required before operational connection')
            self.paper_proof.validate(self.config,[self.config.account])
        self.events=queue.Queue();self.api_config=None;self.last_heartbeat=0.
        self.verified=False;self.accounts=[];self.next_id=None;self.server_time=None
        self.details={};self.details_done=set();self.app=_Client(self)
        self.app.connect(self.config.host,self.config.port,self.config.client_id)
        self.thread=threading.Thread(target=self.app.run,daemon=True);self.thread.start()
        try:
            self._wait(lambda:self.next_id is not None and bool(self.accounts))
            if self.accounts!=[self.config.account]:raise ValueError('Paper account whitelist mismatch')
            self.app.reqCurrentTime();self._wait(lambda:self.server_time is not None)
            self.refresh_config()
            if self.operation=='read_only' and self.api_config['read_only'] is not True:raise ValueError('Enable Read-Only API in the actual Gateway/TWS before initial verification')
            if self.operation=='paper_orders':
                if self.paper_proof is None:raise ValueError('Independent authenticated Paper session evidence required')
                self.paper_proof.validate(self.config,self.accounts)
                if self.api_config['read_only']:raise ValueError('Paper order API remains read-only')
            if abs(time.time()-self.server_time)>5:raise ValueError('Broker/host clock skew exceeds5seconds')
            for i,s in enumerate(self.specs.values(),900):self.app.reqContractDetails(i,self.contract(s.symbol))
            self._wait(lambda:len(self.details_done)==len(self.specs))
            for i,s in enumerate(self.specs.values(),900):
                results=self.details.get(i,[])
                if len(results)!=1:raise ValueError('Ambiguous contract identity')
                d=results[0];c=d.contract
                if (c.conId,c.symbol,c.localSymbol,c.secType,c.currency,c.multiplier,c.lastTradeDateOrContractMonth[:8],d.minTick)!=(s.con_id,s.symbol,s.local_symbol,'FUT','USD','2' if s.symbol=='MNQ' else '5',s.expiry,.25):
                    raise ValueError('IB actual contract metadata mismatch')
            self.verified=True
        except Exception:
            self.close();raise

    def close(self):
        self.verified=False
        if self.app:self.app.disconnect()
        if self.thread and threading.current_thread()!=self.thread:self.thread.join(timeout=2)

    def refresh_config(self):
        self.api_config=None;request=ConfigRequest();request.reqId=8999
        self.app.reqConfigProtoBuf(request)
        self._wait(lambda:self.api_config is not None,timeout=5)
        if self.api_config['port']!=self.config.port:raise ValueError('Actual API socket configuration mismatch')

    def heartbeat(self):
        self.server_time=None;self.app.reqCurrentTime();self._wait(lambda:self.server_time is not None,timeout=3)
        if abs(time.time()-self.server_time)>5:raise ConnectionError('Broker clock/heartbeat mismatch')
        self.refresh_config()
        if self.operation=='read_only' and not self.api_config['read_only']:raise ConnectionError('Read-Only API was disabled; observer is blocked')

    def guard(self,mutating=False):
        if not self.verified or self.accounts!=[self.config.account] or not self.app.isConnected():
            raise ConnectionError('Authenticated configured account protocol session required')
        if mutating:
            if self.operation!='paper_orders' or self.paper_proof is None:raise ConnectionError('Adapter is hard read-only; DU/port are not Paper certification')
            if not self.api_config or self.api_config['read_only'] or time.monotonic()-self.api_config['received_at']>15:raise ConnectionError('Fresh official API writable configuration required')
            if time.monotonic()-self.last_heartbeat>15:raise ConnectionError('Broker heartbeat expired')
            self.paper_proof.validate(self.config,self.accounts)

    def snapshot(self):
        self.guard();self.ends=set();self.positions={};self.open_orders={};self.executions={};self.commissions={}
        self.generation+=1;self.exec_request=self.generation
        self.app.reqPositions();self.app.reqAllOpenOrders()
        query=ExecutionFilter();query.acctCode=self.config.account;query.time=''
        self.app.reqExecutions(self.exec_request,query)
        self._wait(lambda:self.ends=={'positions','orders','executions'})
        return {'accounts':self.accounts[:],'next_id':self.next_id,'positions':dict(self.positions),
                'orders':list(self.open_orders.values()),'executions':list(self.executions.values()),'commissions':list(self.commissions.values())}

    def from_order(self,oid,contract,order,state):
        role='entry' if not order.parentId else 'stop' if order.orderType=='STP' else 'target'
        if order.orderRef.startswith('paper-flat-'):role='flatten'
        return {'id':oid,'symbol':self.symbol(contract),'side':1 if order.action=='BUY' else -1,
          'quantity':integer(order.totalQuantity),'parent_id':order.parentId,'limit':order.lmtPrice if order.orderType=='LMT' else None,
          'stop':order.auxPrice if order.orderType=='STP' else None,'role':role,'ref':order.orderRef,
          'client_id':order.clientId,'status':state.status,'account':order.account,'good_till':order.goodTillDate if role=='entry' else None}

    def submit(self,orders):
        self.guard(mutating=True)
        if len(orders)==3:
            parent,target,stop=orders
            if [o['role'] for o in orders]!=['entry','target','stop'] or [o['transmit'] for o in orders]!=[False,False,True]:raise ValueError('Invalid native bracket transmission')
            if parent['parent_id']!=0 or any(o['parent_id']!=parent['id'] for o in orders[1:]):raise ValueError('Invalid attached parent')
            if any(o['symbol']!=parent['symbol'] or o['quantity']!=parent['quantity'] or o['ref']!=parent['ref'] or o['side']!=-parent['side'] for o in orders[1:]):raise ValueError('Invalid bracket identity')
        elif len(orders)!=1 or orders[0]['role']!='flatten' or orders[0]['parent_id']!=0 or orders[0]['transmit'] is not True:
            raise ValueError('Only complete native brackets or risk-reducing flatten intents supported')
        for item in orders:
            if item['account']!=self.config.account or item['side'] not in (-1,1) or integer(item['quantity'])!=1:raise ValueError('Invalid scoped paper order')
            for field in ('limit','stop'):
                value=item[field]
                if value is not None and (finite(value)<=0 or value/.25!=round(value/.25)):raise ValueError('Invalid quartertick order price')
        for item in orders:
            if item['symbol'] not in self.specs or item['quantity']>self.config.max_contracts:raise ValueError('Order outside approved scope')
            order=Order();order.orderId=item['id'];order.account=self.config.account
            order.action='BUY' if item['side']==1 else 'SELL';order.totalQuantity=Decimal(integer(item['quantity']))
            order.parentId=item['parent_id'];order.transmit=item['transmit'];order.orderRef=item['ref']
            order.tif='GTD' if item['role']=='entry' else 'GTC';order.outsideRth=True
            if item['role']=='entry':order.goodTillDate=item['good_till']
            order.orderType='STP' if item['role']=='stop' else 'MKT' if item['role']=='flatten' else 'LMT'
            if item['limit'] is not None:order.lmtPrice=finite(item['limit'])
            if item['stop'] is not None:order.auxPrice=finite(item['stop'])
            # Native attached siblings share OCA cancellation, reduce overfill risk.
            if item['parent_id']:order.ocaGroup=item['ref'];order.ocaType=1
            self.app.placeOrder(item['id'],self.contract(item['symbol']),order)

    def cancel(self,oid):self.guard(mutating=True);self.app.cancelOrder(oid,OrderCancel())

    def subscribe(self):
        self.guard()
        for i,symbol in enumerate(self.specs,100):
            self.streams[i]=symbol;self.app.reqRealTimeBars(i,self.contract(symbol),5,'TRADES',False,[])

    def read_only_inventory(self,timeout=5):
        self.guard()
        if self.operation!='read_only' or not self.api_config['read_only']:
            raise ValueError('Read-only account inspection requires real API Read-Only response')
        self.account_values={};self.account_end=False;self.positions={};self.open_orders={};self.ends=set()
        self.app.reqAccountSummary(8000,'All','AccountType,NetLiquidation,AvailableFunds,ExcessLiquidity')
        self.app.reqPositions();self.app.reqAllOpenOrders()
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline and not (self.account_end and {'positions','orders'}<=self.ends):time.sleep(.02)
        self.app.cancelAccountSummary(8000);self.app.cancelPositions()
        errors=[]
        while True:
            try:event=self.events.get_nowait()
            except queue.Empty:break
            if event['type']=='error':errors.append(event['code'])
        # A refused/omitted order inventory is NOT evidence of zero open orders.
        return {'account_summary_received':self.account_end,'account_tags':sorted(self.account_values),
          'positions_status':'received' if 'positions' in self.ends else 'unverified',
          'orders_status':'received' if 'orders' in self.ends and not errors else 'unverified_read_only_or_permission',
          'positions':dict(self.positions) if 'positions' in self.ends else None,
          'orders':list(self.open_orders.values()) if 'orders' in self.ends and not errors else None,'error_codes':errors}

    def discover_contracts(self,month):
        import re
        from .core import ContractSpec
        if not re.fullmatch(r'\d{4}(03|06|09|12)',month):raise ValueError('Explicit quarterly contract month required')
        self.guard()
        for i,symbol in enumerate(('MNQ','MES'),3000):
            self.details[i]=[];self.details_done.discard(i)
            c=Contract();c.symbol=symbol;c.secType='FUT';c.exchange='CME';c.currency='USD';c.lastTradeDateOrContractMonth=month
            self.app.reqContractDetails(i,c)
        self._wait(lambda:all(i in self.details_done for i in (3000,3001)))
        specs=[]
        for i,symbol in enumerate(('MNQ','MES'),3000):
            details=self.details.get(i,[])
            if len(details)!=1:raise ValueError('Ambiguous actual IB contract identity')
            d=details[0];c=d.contract
            if (c.symbol,c.secType,c.currency,c.multiplier,d.minTick)!=(symbol,'FUT','USD','2' if symbol=='MNQ' else '5',.25):raise ValueError('Unexpected micro futures metadata')
            specs.append(ContractSpec(symbol,c.localSymbol,c.conId,c.lastTradeDateOrContractMonth[:8]))
        return specs

    def probe_market_data(self,seconds=15):
        self.subscribe();received={s:[] for s in self.specs};errors=[];deadline=time.monotonic()+seconds
        try:
            while time.monotonic()<deadline and any(len(v)<2 for v in received.values()):
                try:event=self.events.get(timeout=.2)
                except queue.Empty:continue
                if event['type']=='five_seconds':received[event['symbol']].append(event)
                elif event['type']=='error':errors.append(event['code'])
                elif event['type']=='disconnect':raise ConnectionError('Disconnected during data probe')
        finally:
            for reqid in self.streams:self.app.cancelRealTimeBars(reqid)
        return {'symbols':{s:{'observed_5second_bars':len(values),'last_start_ns':values[-1]['start_ns'] if values else None,
              'availability':'observed' if values else 'unverified_no_samples'} for s,values in received.items()},
              'error_codes':errors,'new_subscriptions_purchased':False,
              'note':'No samples may mean closed market or missing permissions; never infer entitlement from silence'}
