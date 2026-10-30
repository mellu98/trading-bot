def displaced(bar,direction,atr,cfg):
    r=bar.h-bar.l
    if r<=0 or atr<=0:return False
    body=direction*(bar.c-bar.o)
    end=(bar.h-bar.c if direction==1 else bar.c-bar.l)/r
    return body>=cfg['body_atr_min']*atr and body/r>=cfg['body_ratio_min'] and end<=cfg['close_extreme_max']
def mss(bar,level,direction,atr,cfg):
    return direction*(bar.c-level)>cfg['mss_buffer_ticks']*cfg['tick_size'] and displaced(bar,direction,atr,cfg)
