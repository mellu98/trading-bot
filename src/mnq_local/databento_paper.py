"""Databento market-input seam into the existing V3 owner and local simulator."""
from copy import deepcopy
from dataclasses import asdict,replace
from datetime import datetime,timedelta
from pathlib import Path
import json
from mnq_timestral.schema import Bar,Request,NY,UTC,dumps
from mnq_timestral.evaluation import POINT_VALUE
from mnq_paper.core import Runtime,TERMINAL
from mnq_paper.signals import VwapV1Source
from .replay import ReplaySession,ReplayBroker,AtomicJournal,FrozenSource,atomic_json
from .databento_live import DatabentoLiveProvider,legacy_bar,exact_utc,MINUTE,SCALE


class AvailableSource:
    def __init__(self,session):
        self.session=session;self.identity=session.options.strategy
        self.source=VwapV1Source() if self.identity=='vwap_v1' else FrozenSource(self.identity)
    def evaluate(self,bars,now,state):
        if any(b.available_at>now for b in bars):raise ValueError('future_signal_context')
        # The frozen V2 replay kernel has an event-time-only API. All real
        # availability checks happen BEFORE this temporary, explicitly audited view.
        view=bars if self.identity=='vwap_v1' else tuple(replace(b,available_at=b.end) for b in bars)
        side,result=self.source.evaluate(view,now,state)
        result['actual_available_at']=bars[-1].available_at.isoformat()
        result['kernel_clock']='EVENT_TIME_VIEW_AFTER_ACTUAL_AVAILABILITY_GATE'
        s=self.session
        if not s.offline and not all(s.provider.fresh(symbol,s.now_ns) for symbol in ('MNQ','MES')):
            result.update(blocked='stale_or_missing_micro_quote',observed_side=side);side=0
        # Optional Timestral uses only its existing nonblocking submit/cache seam.
        p=s.predictions.get(bars[-1].symbol)
        if p is not None:
            request=Request(tuple(bars),now);p.submit(request);cached=p.latest(request,now)
            result['timestral_observation_only']=cached is not None
        return side,result


class LivePaperBroker(ReplayBroker):
    """Same simulated orders/fills/fees/OCO state; only event matching is added."""
    def __init__(self,*args,entries_enabled=False,clock_ns=None,**kwargs):
        super().__init__(*args,**kwargs);self.entries_enabled=entries_enabled;self.clock_ns=clock_ns
    def submit(self,orders):
        if any(o['role']=='entry' for o in orders) and not self.entries_enabled:raise ValueError('simulated_entries_disabled')
        super().submit(orders)
        for order in orders:
            at=self.clock_ns()
            self.orders[order['id']]['submitted_at_ns']=at
            self.owner.state['orders'][str(order['id'])]['submitted_at_ns']=at
        self.save()
    def on_quote(self,row,now):
        bid,ask=row['bid_nano']/SCALE,row['ask_nano']/SCALE;symbol=row['symbol'];slip=.25*self.options.slippage_ticks
        # New orders cannot fill against quotes observed before submission.
        for o in list(self.orders.values()):
            if o['symbol']!=symbol or o['status'] in TERMINAL:continue
            if row['ts_event_ns']<o['submitted_at_ns']:continue
            side=o['side'];price=ask if side==1 else bid
            if o['role']=='entry':
                expires=datetime.strptime(o['good_till'],'%Y%m%d %H:%M:%S UTC').replace(tzinfo=UTC)
                if now>=expires:
                    self.cancel(o['id'])
                    for child in self.orders.values():
                        if child['parent_id']==o['id']:self.cancel(child['id'])
                    continue
                if side*(price-o['limit'])>0:continue
                price=min(o['limit'],price+slip) if side==1 else max(o['limit'],price-slip)
            elif o['role'] in ('stop','target'):
                parent=self.orders.get(o['parent_id'])
                if not parent or parent['status']!='Filled':continue
                if o['role']=='stop':
                    if side*(price-o['stop'])<0:continue
                    price+=side*slip
                else:
                    if side*(price-o['limit'])> -slip:continue
                    price=o['limit']
            elif o['role']=='flatten':price+=side*slip
            else:continue
            self.fill(o['id'],o['quantity']-o['filled'],price,f'local-dbn-{o["id"]}',now)
            self.owner.save('db_live_simulated_fill',{'order_id':o['id'],'source_event_ns':row['ts_event_ns'],
                'received_ns':row['received_ns'],'execution':'SYNTHETIC_BBO_NOT_EXCHANGE_FILL'})
        self.save()


class DatabentoPaperSession(ReplaySession):
    def __init__(self,folder,options,specs,*,context_start_ns,offline=False,technical_simulation=False,predictions=None):
        if technical_simulation and not offline:raise ValueError('technical_simulation_is_offline_only')
        self.folder=Path(folder);self.options=options;self.specs=tuple(specs);self.offline=offline;self.predictions=predictions or {}
        self.context_start_ns=context_start_ns;self.now_ns=context_start_ns if offline else __import__('time').time_ns()
        self.now=exact_utc((self.now_ns+999)//1000*1000)
        self.config=replace(options.paper_config(),account='DU00000042',mode='technical_paper' if technical_simulation else 'strict_paper')
        self.journal=AtomicJournal(self.folder/'state.sqlite',self.config,self.specs,lock_root=self.folder.parent/'databento-owner-locks')
        try:
            identity={'options':asdict(options),'specs':[asdict(s) for s in specs],'offline':offline,'technical_simulation':technical_simulation,'context_start_ns':context_start_ns}
            previous=self.journal.state.get('live_session')
            if previous and previous['identity']!=identity:raise ValueError('live_session_identity_mismatch')
            self.journal.state.setdefault('live_session',{'identity':identity,'cursor':0,'equity':[],'complete':False,'consumed_bars':{},'quotes_processed':0})
            self.progress=self.journal.state['live_session'];self.progress.setdefault('input_kind','NONE');self.journal.state.setdefault('local_replay',{'broker':{}})
            self.provider=DatabentoLiveProvider(self.specs,self.journal.state,self.journal.save,context_start_ns=context_start_ns)
            self.broker=LivePaperBroker(self.config,self.specs,self.journal,lambda:self.now,options,entries_enabled=technical_simulation,clock_ns=lambda:self.now_ns)
            self.runtime=Runtime(self.config,self.specs,self.journal,self.broker,clock=lambda:self.now,signal_source=AvailableSource(self))
            self._restore_data()
            with self.journal.bar_transaction():self.reconcile()
        except BaseException:self.journal.close();raise
    def _restore_data(self):
        self.runtime.last_data_by_symbol={s:datetime.fromisoformat(t) for s,t in self.runtime.state['last_bar'].items()}
        self.runtime.last_data=max(self.runtime.last_data_by_symbol.values(),default=None)
    def reconcile(self):self.runtime.reconcile(self.broker.snapshot())
    def _clock(self,value):
        from .databento_live import ns
        self.now_ns=ns(value);self.now=exact_utc((value+999)//1000*1000)
    def _restore_after_error(self,old):
        self.now_ns,self.now=old;self.progress=self.journal.state['live_session'];self.broker.restore();self.runtime.ready=False
        self.provider=DatabentoLiveProvider(self.specs,self.journal.state,self.journal.save,context_start_ns=self.context_start_ns);self._restore_data()
    def _bar(self,row,*,historical=False):
        key=row['symbol']+'|'+str(row['start_ns'])
        digest=__import__('hashlib').sha256(json.dumps(row,sort_keys=True).encode()).hexdigest()
        consumed=self.progress['consumed_bars']
        if key in consumed:
            if consumed[key]!=digest:self.runtime.stop('conflicting_duplicate_bar')
            return
        bar=legacy_bar(row)
        if bar.available_at>self.now:raise ValueError('bar_not_yet_available')
        bootstrap=not historical and self.now-bar.end>timedelta(seconds=self.config.stale_seconds)
        if bootstrap:
            history=self.runtime.state['history'].setdefault(bar.symbol,[])
            if history and history[-1]['end']!=bar.start.isoformat():self.runtime.state['blocked_session']=bar.start.astimezone(NY).date().isoformat()
            if not history and bar.start.astimezone(NY).strftime('%H:%M')!='09:30':self.runtime.state['blocked_session']=bar.start.astimezone(NY).date().isoformat()
            history.append(json.loads(dumps(bar)));self.runtime.state['last_bar'][bar.symbol]=bar.end.isoformat()
            if len(history)>=20 and self.runtime.state['blocked_session']!=bar.start.astimezone(NY).date().isoformat():
                _,state=self.runtime.signal_source.evaluate(tuple(Bar.from_dict(b) for b in history),self.now,self.runtime.state['signal_states'].get(bar.symbol,{}))
                self.runtime.state['signal_states'][bar.symbol]=state
        else:
            if historical:self.broker.match(bar)
            self.reconcile();self.runtime.on_bar(bar);self.reconcile()
        consumed[key]=digest;self.progress['cursor']+=1
        unrealized=sum(p['quantity']*(p['mark']-p['average'])*POINT_VALUE[s] for s,p in self.runtime.state['positions'].items())
        self.progress['equity'].append({'at':self.now.isoformat(),'realized_net':self.runtime.net(),'equity':self.runtime.net()+unrealized})
        self.journal.save('db_live_bar_consumed',{'bar':row,'bootstrap_no_order':bootstrap,'legacy_availability_conversion':'EXPLICIT_CEIL_TO_US_ORIGINAL_NS_RETAINED'})
        if historical and bar.start.astimezone(NY).strftime('%H:%M')=='15:59' and bar.symbol=='MNQ':
            self._stop_flat('session_flatten');self.progress['complete']=True
    def _ingest_one(self,record,received_ns,now_ns):
        self.progress['input_kind']='OFFLINE_DBN_FIXTURES' if self.offline else 'OFFICIAL_LIVE_DBN'
        now_ns=now_ns() if callable(now_ns) else now_ns
        self._clock(now_ns);result=self.provider.ingest(record,received_ns=received_ns,now_ns=now_ns)
        if self.provider.state['fault']:
            self._stop_flat('feed_integrity_fault')
        else:
            for bar in result['bars']:self._bar(bar)
            event=result['event']
            if event and event['kind']=='quote' and result['status']=='accepted' and result['quote_fresh']:
                p=self.runtime.state['positions'].get(event['symbol'])
                if p:p['mark']=(event['bid_nano'] if p['quantity']>=0 else event['ask_nano'])/SCALE
                self.broker.on_quote(event,self.now);self.reconcile();self.progress['quotes_processed']+=1
        self.broker.save();self.journal.save('db_live_processed',{'status':result['status'],'at_ns':now_ns})
        return result
    def ingest_batch(self,events):
        if not 1<=len(events)<=256:raise ValueError('bounded_market_batch_required')
        old=(self.now_ns,self.now)
        try:
            with self.journal.bar_transaction():return [self._ingest_one(*event) for event in events]
        except BaseException:self._restore_after_error(old);raise
    def ingest(self,record,received_ns,now_ns):
        return self.ingest_batch([(record,received_ns,now_ns)])[0]
    def ingest_historical(self,bar):
        if not self.offline:raise ValueError('offline_ohlcv_cannot_enter_live_session')
        old=(self.now_ns,self.now)
        try:
            with self.journal.bar_transaction():
                self.progress['input_kind']='OWNED_HISTORICAL_OHLCV_1M'
                row=self.provider.historical_bar(bar);self._clock(row['available_ns']);self._bar(row,historical=True)
                self.broker.save();self.journal.save('db_offline_bar',{'source':'OWNED_CME_OHLCV_NOT_LIVE'})
        except BaseException:self._restore_after_error(old);raise
    def disconnected(self,reason='sdk_disconnected'):
        with self.journal.bar_transaction():
            self.provider.fault(reason);self.runtime.disconnected();self._stop_flat('data_gap');self.broker.save()
    def tick(self,now_ns):
        with self.journal.bar_transaction():
            self._clock(now_ns)
            if self.runtime.last_data is not None and not all(self.provider.fresh(s,now_ns) for s in ('MNQ','MES')):
                self._stop_flat('stale_data')
            self.runtime.watchdog();self.reconcile();self.broker.save();self.journal.save('db_live_heartbeat',{'at_ns':now_ns})
    def report(self):
        fees=sum(e['fee'] for e in self.runtime.state['executions'].values());peak=dd=0.
        for e in self.progress['equity']:peak=max(peak,e['equity']);dd=max(dd,peak-e['equity'])
        return {'mode':'OFFLINE_CME_REPLAY_NOT_LIVE' if self.offline else 'CME_LIVE_DATA_LOCAL_SIMULATION',
            'execution':self.broker.kind,'strategy':self.options.strategy,'session':self.options.session,'strict_news':self.config.mode=='strict_paper',
            'strategy_approved':False,'broker_connected':False,'real_money_routing':False,'timestral':'OBSERVATION_ONLY' if self.predictions else 'DISABLED',
            'bars_processed':self.progress['cursor'],'bars_total':None,'complete':self.progress['complete'],'replay_time':self.now.isoformat(),
            'trades':len(self.trades()),'orders':len(self.runtime.state['orders']),'gross':self.runtime.state['gross'],'fees':fees,'net':self.runtime.net(),
            'max_drawdown':dd,'positions':deepcopy(self.runtime.state['positions']),'working_orders':[o for o in self.runtime.state['orders'].values() if o['status'] not in TERMINAL],
            'halt':self.runtime.state['halt'],'accepted':sum(d['accepted'] for d in self.runtime.state['decisions']),
            'rejected':sum(not d['accepted'] for d in self.runtime.state['decisions']),'ambiguities':len(self.broker.ambiguities),
            'source':{'dataset':'GLBX.MDP3','configured_live_schemas':list(self.provider.schemas),'actual_input_kind':self.progress['input_kind'],'source_event_ns_preserved':True,'provider_counts':deepcopy(self.provider.state['counts']),
                'fault':self.provider.state['fault'],'quote_fresh':{s:self.provider.fresh(s,self.now_ns) for s in ('MNQ','MES')},
                'transport_latency_measured':False,'top_of_book':{s:{'contract':q['contract'],'bid':q['bid_nano']/SCALE,
                    'ask':q['ask_nano']/SCALE,'bid_size':q['bid_size'],'ask_size':q['ask_size'],
                    'source_event_ns':q['ts_event_ns'],'capture_recv_ns':q['ts_recv_ns'],'received_ns':q['received_ns'],
                    'source_age_ns':self.now_ns-q['ts_event_ns'],'local_receipt_age_ns':self.now_ns-q['received_ns']}
                    for s,q in self.provider.state['quotes'].items()}},
            'simulated_entries_enabled':self.broker.entries_enabled,'news_certified':False,'financial_validation':False,
            'costs':asdict(self.options),'runtime_policy':'UNCHANGED_V3_ORDER_OWNER_AND_RISK; '+('OFFLINE_TECHNICAL_UNCERTIFIED_NEWS' if self.broker.entries_enabled else 'STRICT_NEWS_BLOCKED'),
            'intrabar_policy':'Observed post-submission BBO for live simulation; conservative original OHLC matcher for explicitly offline bars only'}
