from datetime import datetime
class SimulationAdapter:
    """OHLC conservative harness. No network, keys or live path. One order at a time.
    spread is constant within a bar in this harness, not a market-data claim.
    No partial fills: production requires quote/trade replay adapter.
    """
    def __init__(self,cfg):
        if cfg['mode']!='simulation':raise ValueError('simulation only')
        self.cfg=cfg;self.orders={};self.fills=[]
    def create(self,signal):
        sid=signal['signal_id']
        if sid in self.orders:
            if self.orders[sid]['signal']!=signal:raise ValueError('ID conflict')
            return self.orders[sid]
        if any(x['status'] in ('PENDING','OPEN') for x in self.orders.values()):raise ValueError('one exposure only')
        if signal['qty']<=0:raise ValueError('qty')
        row={'signal':dict(signal),'status':'PENDING','held':0};self.orders[sid]=row;return row
    def cancel(self,sid):
        x=self.orders[sid]
        if x['status']=='PENDING':x['status']='CANCELLED'
        return x
    def reconcile(self):return list(self.orders.values())
    def on_bar(self,b,spread):
        out=[];c=self.cfg
        for x in self.orders.values():
            s=x['signal'];d=s['direction'];new=False
            if b.ts<=datetime.fromisoformat(s['known_at']):continue
            if x['status']=='PENDING':
                if b.ts>=datetime.fromisoformat(s['expires_at']):x['status']='EXPIRED';continue
                # Entry ask for long, bid for short; require penetration by one tick.
                touched=b.l+spread/2<=s['entry']-c['tick_size'] if d==1 else b.h-spread/2>=s['entry']+c['tick_size']
                if not touched:continue
                x['status']='OPEN';x['entry_fill']=s['entry'];new=True
            if x['status']!='OPEN':continue
            x['held']+=1;side=-spread/2 if d==1 else spread/2
            lo,hi,op=b.l+side,b.h+side,b.o+side
            hitstop=lo<=s['stop'] if d==1 else hi>=s['stop']
            hittarget=hi>=s['target']+c['tick_size'] if d==1 else lo<=s['target']-c['tick_size']
            exit_price=None;why=None
            if hitstop:
                exit_price=(min(op,s['stop']) if d==1 else max(op,s['stop']))-d*c['slippage_price'];why='STOP'
            elif hittarget and not new:exit_price=s['target'];why='TARGET'
            elif x['held']>=c['max_hold_bars']:exit_price=b.c+side-d*c['slippage_price'];why='TIME'
            if exit_price is not None:
                q=s['qty'];m=c['multiplier'];fx=c['quote_to_eur']
                gross=d*(exit_price-x['entry_fill'])*q*m*fx
                fees=c['fee_rate']*(exit_price+x['entry_fill'])*q*m*fx+c['fixed_fee_eur']+q*c['unit_fee_eur']
                result={'signal_id':s['signal_id'],'exit_at':b.ts.isoformat(),'exit_price':exit_price,'reason':why,'gross_eur':gross,'fees_eur':fees,'net_eur':gross-fees}
                x['status']='CLOSED';self.fills.append(result);out.append(result)
        return out
