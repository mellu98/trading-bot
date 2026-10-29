from datetime import datetime,timezone
import numpy as np
import pytest
from analyze import period_table, attribute, drawdown_detail, cost_totals
D=86400

def test_period_return_compounds_and_pnl_reconciles():
 x=period_table([1000,1100,990],[0,D,2*D],'month')
 assert x[0]['net_pnl']==pytest.approx(-10);assert x[0]['return']==pytest.approx(-.01)

def test_fifo_not_needed_attribution_reconciles_liquidation_marks():
 bars={0:{'open':100.,'close':110.},D:{'open':110.,'close':120.}}
 orders=[{'at':0,'asset_index':0,'side':'BUY','quantity':1.,'raw':100.,'fill':100.,'fee':1.,'spread':0.,'slippage':0.,'metadata':{}}, {'at':2*D,'asset_index':0,'side':'SELL','quantity':1.,'raw':120.,'fill':120.,'fee':1.,'spread':0.,'slippage':0.,'metadata':{'reason':'EXPLICIT_FINITE_SEGMENT_TERMINAL_CLOSE_NOT_PRODUCTION_FILL'}}]
 x=attribute([1000,1009,1018],[0,D,2*D],orders,[bars],1.)
 assert x['asset_net_pnl'][0]==pytest.approx(18);assert x['daily'][0]['asset_net_pnl'][0]==pytest.approx(9);assert x['daily'][1]['asset_net_pnl'][0]==pytest.approx(9)
 assert x['exposure_average']>0 and x['cash_fraction_average']<1

def test_unrealized_exit_reserve_not_double_charged():
 bars={0:{'open':100.,'close':100.},D:{'open':100.,'close':100.}}
 orders=[{'at':0,'asset_index':0,'side':'BUY','quantity':1.,'raw':100.,'fill':100.,'fee':0.,'spread':0.,'slippage':0.,'metadata':{}}]
 x=attribute([1000,998,998],[0,D,2*D],orders,[bars],.98)
 assert x['daily'][0]['asset_net_pnl'][0]==pytest.approx(-2);assert x['daily'][1]['asset_net_pnl'][0]==pytest.approx(0)

def test_cost_decomposition_is_actual_fixed_path_accounting():
 orders=[{'fee':2.,'spread':.2,'slippage':.3,'asset_index':0}]
 x=cost_totals(orders,2);assert x['all']['total']==pytest.approx(2.5);assert x['assets'][1]['total']==0

def test_drawdown_dates_include_initial_capital():
 x=drawdown_detail([1000,900,950,1000],[0,D,2*D,3*D]);assert x['drawdown']==pytest.approx(.1);assert x['peak_at']==0;assert x['trough_at']==D;assert x['recovery_at']==3*D

def test_terminal_order_must_not_be_assigned_to_next_segment():
 bars={0:{'open':100.,'close':105.}}
 orders=[{'at':0,'asset_index':0,'side':'BUY','quantity':1.,'raw':100.,'fill':100.,'fee':0.,'spread':0.,'slippage':0.,'metadata':{}},{'at':D,'asset_index':0,'side':'SELL','quantity':1.,'raw':105.,'fill':105.,'fee':0.,'spread':0.,'slippage':0.,'metadata':{'reason':'EXPLICIT_FINITE_SEGMENT_TERMINAL_CLOSE_NOT_PRODUCTION_FILL'}}]
 x=attribute([1000,1005],[0,D],orders,[bars],1.);assert x['daily'][0]['orders']==2;assert x['asset_net_pnl'][0]==5
