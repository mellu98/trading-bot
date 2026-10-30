def fvg(bars,direction,atr,cfg):
    if len(bars)<3:return None
    a,_,c=bars[-3:]
    lo,hi=(a.h,c.l) if direction==1 else (c.h,a.l)
    if cfg['fvg_min_atr']*atr<=hi-lo<=cfg['fvg_max_atr']*atr:return (lo,hi)
    return None
