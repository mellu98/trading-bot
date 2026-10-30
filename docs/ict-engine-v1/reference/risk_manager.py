from dataclasses import dataclass
@dataclass(frozen=True)
class RiskState:
    day_return:float=0
    week_return:float=0
    drawdown:float=0
    consecutive_losses:int=0
    daily_trades:int=0
    concurrent:int=0
    reserved_fraction:float=0
    api_errors:int=0
    halted:bool=False
def gate(state,cfg):
    checks=[(state.halted,'DISABLE_KILL_SWITCH'),(state.drawdown>=cfg['drawdown_fraction'],'DISABLE_DRAWDOWN'),
    (state.day_return<=-cfg['daily_loss_fraction'],'SKIP_DAILY_LOSS'),(state.week_return<=-cfg['weekly_loss_fraction'],'SKIP_WEEKLY_LOSS'),
    (state.consecutive_losses>=cfg['max_consecutive_losses'],'SKIP_LOSS_STREAK'),(state.daily_trades>=cfg['max_daily_trades'],'SKIP_TRADE_LIMIT'),
    (state.concurrent>=cfg['max_concurrent'],'SKIP_CONCURRENT'),
    (state.reserved_fraction+cfg['risk_fraction']>cfg['max_aggregate_risk_fraction'],'SKIP_AGGREGATE_RISK'),
    (state.api_errors>=cfg['api_error_limit'],'DISABLE_API_ERRORS')]
    return next((code for test,code in checks if test),None)
