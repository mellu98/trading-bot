from decimal import Decimal,ROUND_FLOOR
D=lambda x:Decimal(str(x))
def size(equity,entry,stop,target,direction,cfg):
    if direction not in (-1,1) or min(equity,entry,stop,target)<=0:raise ValueError('inputs')
    if direction==-1 and not cfg['short_allowed']:return {'qty':0,'reason':'SKIP_SHORT_UNSUPPORTED'}
    if direction*(entry-stop)<=0 or direction*(target-entry)<=0:return {'qty':0,'reason':'SKIP_INVALID_GEOMETRY'}
    # Entry, stop, target are executable-side prices. No extra spread charge.
    x,m,sl,f=map(D,(cfg['quote_to_eur'],cfg['multiplier'],cfg['slippage_price'],cfg['fee_rate']))
    if x<=0 or m<=0 or sl<0 or f<0:raise ValueError('metadata')
    en,st,tp=map(D,(entry,stop,target));fixed=D(cfg['fixed_fee_eur'])
    unit=(abs(en-st)+sl)*m*x+f*(en+st+sl)*m*x+D(cfg['unit_fee_eur'])
    reward=(abs(tp-en)-sl)*m*x-f*(en+tp+sl)*m*x-D(cfg['unit_fee_eur'])
    budget=D(equity)*min(D(cfg['risk_fraction']),D(cfg['risk_cap_fraction']))
    step=D(cfg['lot_step'])
    if step<=0 or unit<=0 or fixed<0 or budget<=fixed:return {'qty':0,'reason':'SKIP_METADATA_OR_BUDGET'}
    raw=min((budget-fixed)/unit,max(D(0),D(cfg['available_cash_eur'])-fixed)/(en*m*x*(1+f)+D(cfg['unit_fee_eur'])))
    q=(raw/step).to_integral_value(rounding=ROUND_FLOOR)*step
    loss=q*unit+fixed;gain=q*reward-fixed
    if q<D(cfg['min_qty']) or q*en*m<D(cfg['min_notional']):return {'qty':0,'reason':'SKIP_MINIMUM_SIZE'}
    if gain/loss<D(cfg['min_net_rr']):return {'qty':0,'reason':'SKIP_NET_RR'}
    return {'qty':float(q),'risk_eur':float(loss),'reward_eur':float(gain),'net_rr':float(gain/loss),'reason':'SIZE_OK'}
