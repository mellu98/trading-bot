def sweep(bar,pool,direction,atr,cfg):
    penetration=pool.price-bar.l if direction==1 else bar.h-pool.price
    recovered=direction*(bar.c-pool.price)>=cfg['sweep_recovery_ticks']*cfg['tick_size']
    return cfg['sweep_min_atr']*atr<=penetration<=cfg['sweep_max_atr']*atr and recovered
