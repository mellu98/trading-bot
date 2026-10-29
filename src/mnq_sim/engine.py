"""Deterministic one-minute simulated execution using the existing signal/risk code."""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import json
import math
from pathlib import Path

from mnq_timestral.schema import Bar, Request, NY, dumps
from mnq_timestral.data import features
from mnq_timestral.strategy import SignalGenerator, Risk, RiskState
from mnq_timestral.evaluation import Costs, DISTANCES, POINT_VALUE, simulate_trade
from mnq_data.core import digest


@dataclass(frozen=True)
class Config:
    commission_per_side: float = 0.25
    exchange_per_side: float = 0.35
    regulatory_per_side: float = 0.01
    spread_ticks: float = 0.0
    entry_slippage_ticks: float = 1.0
    exit_slippage_ticks: float = 1.0
    virtual_capital: float = 10000.0
    threshold: float = 2.5
    daily_max_loss: float = 200.0
    max_drawdown: float = 500.0
    max_trades: int = 10
    max_consecutive_losses: int = 3
    exit_variant: str = 'fixed'
    news_required: bool = True

    def __post_init__(self):
        self.costs()
        self.risk()
        if self.exit_variant not in ('fixed','vwap') or not math.isfinite(self.virtual_capital) or self.virtual_capital<=0 or not math.isfinite(self.threshold) or self.threshold<=0:
            raise ValueError('Invalid simulation configuration')
        if not isinstance(self.news_required,bool): raise ValueError('Boolean news gate required')

    def costs(self):
        fields=Costs.__dataclass_fields__
        return Costs(**{k:getattr(self,k) for k in fields if k!='evidence'},
                     evidence='Explicit technical cost scenario, NOT verified account-specific broker fees')

    def risk(self):
        return Risk(self.daily_max_loss,self.max_drawdown,self.max_trades,self.max_consecutive_losses)


def exit_bar(bar,side,entry,config,target=None):
    tp,sl=DISTANCES[bar.symbol]
    if target is not None:
        tp=side*(target-entry)
        if tp<=0: raise ValueError('Target must be in profitable direction at entry')
    stop=entry-side*sl;target=entry+side*tp
    hit_stop=bar.low<=stop if side==1 else bar.high>=stop
    hit_target=bar.high>=target if side==1 else bar.low<=target
    trade=simulate_trade(bar.symbol,side,[bar],entry,config.costs(),tp=tp,sl=sl)
    return {'reason':trade.reason,'raw_exit':trade.raw_exit,'ambiguous':bool(hit_stop and hit_target),
            'stop':stop,'target':target,'net_mark':trade.net}


def load_state(path):
    return json.loads(Path(path).read_text())


class Replay:
    """One contract per trade; portfolio exposure cap one open position total.

    Decisions occur after bar close. Pending markets fill only at a following
    bar's open. Event timestamps on intrabar exits are interval-end bounds, not ticks.
    News unavailable -> no entries. There is no network/broker integration here.
    """
    def __init__(self,bars,config,news=None,state=None,kill_path=None):
        self.bars=list(bars);self.config=config;self.news=news;self.kill_path=kill_path
        self.dataset_sha256=digest(json.loads(dumps(tuple(self.bars))))
        self.config_sha256=digest(asdict(config))
        self.news_sha256=digest(news)
        groups=defaultdict(list)
        for b in self.bars: groups[(b.start.astimezone(NY).date().isoformat(),b.symbol)].append(b)
        self.indicators={}
        for session in groups.values():
            if len(session)<20: continue
            for a,b in zip(session,session[1:]):
                if a.end!=b.start or a.contract!=b.contract:
                    raise ValueError('Data gap/reorder/roll requires safe halt before execution')
            f=features(Request(tuple(session),session[-1].end))
            for i,b in enumerate(session):
                self.indicators[(b.start.isoformat(),b.symbol)]={'z':float(f.z[i]) if math.isfinite(f.z[i]) else None,
                    'vwap':float(f.vwap[i]),'volatility':float(f.volatility[i])}
        bytime=defaultdict(dict)
        for b in bars:
            if b.symbol in bytime[b.start]: raise ValueError('Duplicate input bar')
            bytime[b.start][b.symbol]=b
        self.events=sorted(bytime.items())
        self.index=0;self.date=None;self.pending=None;self.position=None
        self.realized=0.;self.realized_day=0.;self.peak=0.;self.day_trades=0;self.consecutive=0
        self.kill=False;self.day_halt=False;self.global_halt=False
        self.generators={r:SignalGenerator(config.threshold) for r in ('MNQ','MES')}
        self.decisions=[];self.orders=[];self.trades=[];self.equity=[];self.risk_events=[]
        self.force_candidates={}
        if state is not None:
            if (state.get('dataset_sha256'),state.get('config_sha256'),state.get('news_sha256')) != (self.dataset_sha256,self.config_sha256,self.news_sha256):
                raise ValueError('Restart input/config/news identity mismatch')
            for k in self.persisted_fields(): setattr(self,k,state[k])
            for root,previous in state['generator_previous'].items(): self.generators[root].previous=previous
            if self.position:
                children=[o for o in self.orders if o.get('parent_id')==self.position['id'] and o['status']=='working']
                if {o['type'] for o in children}!={'stop','target'}: raise ValueError('Open position bracket reconciliation failed')

    @staticmethod
    def persisted_fields():
        return ('index','date','pending','position','realized','realized_day','peak','day_trades',
                'consecutive','kill','day_halt','global_halt','decisions','orders','trades','equity','risk_events')

    def state(self):
        return {**{k:getattr(self,k) for k in self.persisted_fields()},
            'dataset_sha256':self.dataset_sha256,'config_sha256':self.config_sha256,'news_sha256':self.news_sha256,
            'generator_previous':{k:g.previous for k,g in self.generators.items()}}

    def entry_permission(self,mark=0):
        if self.day_halt: return False,'daily_halt_latched'
        if self.global_halt: return False,'global_halt_latched'
        return self.config.risk().allow(RiskState(realized=self.realized_day,unrealized=mark,
            drawdown=max(0,self.peak-self.realized-mark),trades=self.day_trades,
            consecutive_losses=self.consecutive,positions=int(self.position is not None),kill=self.kill))

    def news_allowed(self,now):
        if not self.config.news_required: return True
        if not self.news or self.news.get('status')!='verified_scoped_official_schedule' or self.date not in self.news.get('dates',[]):
            return False
        return not any(datetime.fromisoformat(b['start'])<=now<=datetime.fromisoformat(b['end']) for b in self.news['blocks'])

    @staticmethod
    def in_window(now):
        local=now.astimezone(NY)
        return (9,45)<=(local.hour,local.minute)<(15,30)

    def close(self,bar,raw_exit,reason,ambiguous=False,at_open=False):
        p=self.position;side=p['side'];costs=self.config.costs()
        gross=side*(raw_exit-p['raw_entry'])*POINT_VALUE[bar.symbol]
        execution=costs.execution_cost(bar.symbol);net=gross-costs.fees-execution
        self.trades.append({**p,'exit_at':(bar.start if at_open else bar.end).isoformat(),
            'raw_exit':raw_exit,'exit_fill':raw_exit-side*.25*(costs.exit_slippage_ticks+costs.spread_ticks/2),
            'gross':gross,'fees':costs.fees,'execution_cost':execution,'net':net,'reason':reason,
            'intrabar_ambiguous':ambiguous,'exit_timestamp_is_bar_bound':not at_open})
        for order in self.orders:
            if order.get('parent_id')==p['id'] and order['status']=='working':
                order['status']='filled' if order['type']==reason else 'cancelled_oco'
                order['completed_at']=(bar.start if at_open else bar.end).isoformat()
        self.orders.append({'id':p['id']+'-exit','parent_id':p['id'],'type':'simulated_exit','status':'filled','reason':reason})
        self.realized+=net;self.realized_day+=net
        self.consecutive=self.consecutive+1 if net<0 else 0
        self.position=None
        if self.realized_day<=-self.config.daily_max_loss or self.consecutive>=self.config.max_consecutive_losses:
            self.day_halt=True
        if self.peak-self.realized>=self.config.max_drawdown: self.global_halt=True

    def step(self,start,group):
        date=start.astimezone(NY).date().isoformat()
        if date!=self.date:
            if self.position or self.pending: raise ValueError('Unsafe overnight position/order')
            self.date=date;self.realized_day=0.;self.day_trades=0;self.consecutive=0;self.day_halt=False
            for generator in self.generators.values(): generator.previous=0
        if self.kill_path and Path(self.kill_path).exists(): self.kill=True
        if self.kill and self.pending:
            self.orders[self.pending['order_index']]['status']='cancelled_kill';self.pending=None
        if self.kill and self.position:
            b=group[self.position['symbol']];self.close(b,b.open,'kill',at_open=True)
        if self.pending:
            p=self.pending;self.pending=None;b=group.get(p['symbol'])
            allowed,reason=self.entry_permission()
            if not b or b.start.isoformat()!=p['expected_start'] or not self.in_window(b.start) or not self.news_allowed(b.start):
                allowed,reason=False,'stale_or_calendar'
            order=self.orders[p['order_index']]
            if allowed:
                tp,sl=DISTANCES[b.symbol];target=round(p['signal_vwap']/.25)*.25 if self.config.exit_variant=='vwap' else b.open+p['side']*tp
                if p['side']*(target-b.open)<=0: allowed,reason=False,'vwap_target_not_profitable'
            if allowed:
                side=p['side'];costs=self.config.costs()
                self.position={'id':order['id'],'symbol':b.symbol,'contract':b.contract,'side':side,'quantity':1,
                    'entry_at':b.start.isoformat(),'raw_entry':b.open,
                    'entry_fill':b.open+side*.25*(costs.entry_slippage_ticks+costs.spread_ticks/2),
                    'stop':b.open-side*sl,'target':target,'signal_bar_start':p['signal_bar_start'],'signal_at':p['signal_at']}
                order.update(status='filled',filled_at=b.start.isoformat());self.day_trades+=1
                for typ in ('stop','target'):
                    self.orders.append({'id':order['id']+'-'+typ,'parent_id':order['id'],'type':typ,'status':'working',
                                        'level':self.position[typ],'oco_group':order['id']})
            else: order.update(status='rejected',reason=reason)
        mark=0.
        if self.position:
            p=self.position;b=group.get(p['symbol'])
            if b is None: raise ValueError('Open position lacks market data; safe halt')
            result=exit_bar(b,p['side'],p['raw_entry'],self.config,p['target'])
            if result['reason'] in ('stop','target'):
                self.close(b,result['raw_exit'],result['reason'],result['ambiguous'])
            elif not self.in_window(b.end): self.close(b,b.close,'session_close')
            else:
                mark=result['net_mark']
                if self.realized_day+mark<=-self.config.daily_max_loss or self.peak-self.realized-mark>=self.config.max_drawdown:
                    self.risk_events.append({'at':b.end.isoformat(),'reason':'unrealized_loss_limit','mark':mark})
                    self.day_halt=True
                    if self.peak-self.realized-mark>=self.config.max_drawdown:self.global_halt=True
                    self.close(b,b.close,'risk_loss');mark=0.
        equity=self.realized+mark;self.peak=max(self.peak,equity)
        self.equity.append({'at':(start+timedelta(minutes=1)).isoformat(),'equity':self.config.virtual_capital+equity,
                            'net_pnl':equity,'drawdown':self.peak-equity})
        for root in ('MNQ','MES'):
            b=group.get(root)
            if b is None: continue
            ind=self.indicators.get((b.start.isoformat(),root),{'z':None,'vwap':b.close,'volatility':0})
            z=ind['z'];side=self.generators[root].direction(z if z is not None else math.nan)
            forced=self.force_candidates.get(b.end.isoformat())
            if forced and forced[0]==root: side=forced[1]
            allowed,reason=self.entry_permission()
            if not self.in_window(b.end): allowed,reason=False,'outside_entry_window'
            if not self.news_allowed(b.end): allowed,reason=False,'news_unavailable_or_blocked'
            if self.pending: allowed,reason=False,'pending_order'
            if not side: allowed,reason=False,'hold_or_no_new_crossing'
            decision={'at':b.end.isoformat(),'bar_start':b.start.isoformat(),'symbol':root,**ind,
                      'side':side,'accepted':allowed,'reason':reason}
            self.decisions.append(decision)
            if allowed:
                order={'id':f'order-{len([o for o in self.orders if o["type"]=="market"])+1:05d}',
                       'type':'market','symbol':root,'side':side,'quantity':1,'status':'pending','submitted_at':b.end.isoformat()}
                self.orders.append(order)
                self.pending={'symbol':root,'side':side,'signal_bar_start':b.start.isoformat(),
                    'signal_at':b.end.isoformat(),'expected_start':b.end.isoformat(),'signal_vwap':ind['vwap'],'order_index':len(self.orders)-1}

    def run(self,stop_after=None,checkpoint=None):
        while self.index<len(self.events):
            self.step(*self.events[self.index]);self.index+=1
            if checkpoint: checkpoint(self.state())
            if stop_after is not None and self.index>=stop_after: break
        if self.index==len(self.events) and (self.pending or self.position):
            if self.pending:
                self.orders[self.pending['order_index']]['status']='cancelled_end_of_data';self.pending=None
            if self.position:
                last=next(b for b in reversed(self.bars) if b.symbol==self.position['symbol'])
                self.close(last,last.close,'end_of_data')
            if checkpoint: checkpoint(self.state())
        return {'trades':self.trades,'decisions':self.decisions,'orders':self.orders,'equity':self.equity,'risk_events':self.risk_events}


def summarize(result):
    trades=result['trades'];net=[t['net'] for t in trades]
    gains=sum(x for x in net if x>0);losses=-sum(x for x in net if x<0)
    bysymbol={s:{'trades':sum(t['symbol']==s for t in trades),'net':sum(t['net'] for t in trades if t['symbol']==s)} for s in ('MNQ','MES')}
    return {'trades':len(trades),'gross':sum(t['gross'] for t in trades),'fees':sum(t['fees'] for t in trades),
        'execution_cost':sum(t['execution_cost'] for t in trades),'net':sum(net),
        'win_rate':sum(x>0 for x in net)/len(net) if net else None,'profit_factor':gains/losses if losses else None,
        'max_drawdown_mark_to_minute_close':max([e['drawdown'] for e in result['equity']]+[0]),
        'expectancy':sum(net)/len(net) if net else None,'ambiguous_intrabar_trades':sum(t['intrabar_ambiguous'] for t in trades),
        'by_symbol':bysymbol,'by_day':{d:sum(t['net'] for t in trades if t['entry_at'].startswith(d)) for d in sorted({t['entry_at'][:10] for t in trades})},
        'exit_reasons':dict(Counter(t['reason'] for t in trades)),
        'decision_reasons':dict(Counter(d['reason'] for d in result['decisions']))}
