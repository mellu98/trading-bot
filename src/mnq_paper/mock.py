"""Fault-injectable external broker simulator, NEVER evidence of real IB fills."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from .core import TERMINAL


class MockBroker:
    kind='MOCK_NOT_IB'
    def __init__(self,config,specs,path=None):
        self.config=config;self.specs={s.symbol:s for s in specs};self.path=Path(path) if path else None
        state=json.loads(self.path.read_text()) if self.path and self.path.exists() else {}
        self.orders={int(k):v for k,v in state.get('orders',{}).items()};self.executions=state.get('executions',[])
        self.positions=state.get('positions',{});self.fail_after=None;self.submissions=0;self.connected=True

    def save(self):
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps({'orders':self.orders,'executions':self.executions,'positions':self.positions},sort_keys=True))
            temp.replace(self.path)

    def submit(self,orders):
        if not self.connected:raise ConnectionError('Mock disconnected')
        for order in orders:
            self.submissions+=1
            if self.fail_after==self.submissions:raise ConnectionError('Injected ambiguous send failure')
            if order['id'] in self.orders:raise ValueError('Duplicate broker order ID')
            self.orders[order['id']]={**deepcopy(order),'status':'Submitted'};self.save()

    def cancel(self,oid):
        if not self.connected:raise ConnectionError('Mock disconnected')
        if oid in self.orders and self.orders[oid]['status'] not in TERMINAL:
            self.orders[oid]['status']='Cancelled';self.save()

    def fill(self,oid,quantity,price,exec_id,at):
        order=self.orders[oid]
        if order['status'] in TERMINAL:raise ValueError('Cannot fill terminal order')
        if quantity<=0 or quantity+order['filled']>order['quantity']:raise ValueError('Mock fill exceeds order')
        event={'exec_id':exec_id,'order_id':oid,'symbol':order['symbol'],'account':self.config.account,
               'client_id':self.config.client_id,'side':order['side'],'quantity':quantity,'price':price,'at':at.isoformat()}
        self.executions.append(event);order['filled']+=quantity
        order['status']='Filled' if order['filled']==order['quantity'] else 'Partial'
        self.positions[order['symbol']]=self.positions.get(order['symbol'],0)+order['side']*quantity
        if order['role'] in ('stop','target'):
            for sibling in self.orders.values():
                if sibling['parent_id']==order['parent_id'] and sibling['id']!=oid and sibling['role'] in ('stop','target'):
                    self.cancel(sibling['id'])
        self.save();return event

    def snapshot(self):
        if not self.connected:raise ConnectionError('Mock disconnected')
        return deepcopy({'accounts':[self.config.account],'next_id':max(self.orders,default=0)+1,
          'orders':[o for o in self.orders.values() if o['status'] not in TERMINAL],
          'positions':self.positions,'executions':self.executions})

    def match(self,bar):
        for order in list(self.orders.values()):
            if order['symbol']!=bar.symbol or order['status'] in TERMINAL:continue
            if order['role']=='flatten':
                self.fill(order['id'],order['quantity']-order['filled'],bar.open,f'mock-{order["id"]}-flat',bar.start)
            elif order['role']=='entry':
                expiry=datetime.strptime(order['good_till'],'%Y%m%d %H:%M:%S UTC').replace(tzinfo=timezone.utc)
                if bar.start>=expiry:
                    self.cancel(order['id'])
                    for child in self.orders.values():
                        if child['parent_id']==order['id']:self.cancel(child['id'])
                    continue
                crossed=bar.low<=order['limit'] if order['side']==1 else bar.high>=order['limit']
                if crossed:
                    price=min(bar.open,order['limit']) if order['side']==1 else max(bar.open,order['limit'])
                    self.fill(order['id'],order['quantity']-order['filled'],price,f'mock-{order["id"]}-entry',bar.start)
        for parent in list(self.orders.values()):
            if parent['symbol']!=bar.symbol or parent['role']!='entry' or parent['status']!='Filled':continue
            children=[o for o in self.orders.values() if o['parent_id']==parent['id'] and o['status'] not in TERMINAL]
            stop=next((o for o in children if o['role']=='stop'),None);target=next((o for o in children if o['role']=='target'),None)
            if not stop or not target:continue
            side=parent['side'];hitstop=bar.low<=stop['stop'] if side==1 else bar.high>=stop['stop']
            hittarget=bar.high>=target['limit'] if side==1 else bar.low<=target['limit']
            if hitstop or hittarget:
                chosen=stop if hitstop else target
                price=(min(bar.open,stop['stop']) if side==1 else max(bar.open,stop['stop'])) if hitstop else target['limit']
                self.fill(chosen['id'],chosen['quantity'],price,f'mock-{chosen["id"]}-exit',bar.end)
