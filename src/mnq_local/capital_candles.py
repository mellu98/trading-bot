"""Broker-native bid/ask bars. Observation-only; no order execution capability."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import hashlib,json,re,time
from types import SimpleNamespace
from mnq_timestral.schema import NY
from .capital import dec
UTC=timezone.utc
STEPS={'MINUTE':60,'MINUTE_5':300}
EPOCH=datetime(1970,1,1,tzinfo=UTC)


def parse_candle(epic,resolution,raw):
    if epic not in ('US100','US500') or resolution not in STEPS:raise ValueError('Unsupported native candle identity')
    text=raw.get('snapshotTimeUTC')
    if not isinstance(text,str):raise ValueError('Explicit broker UTC timestamp required')
    match=re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,9}))?(?:Z|\+00:00)?',text)
    if not match or (match.group(1) and any(c!='0' for c in match.group(1))):raise ValueError('Non-minute or ambiguous native timestamp')
    at=datetime.fromisoformat(text.replace('Z','+00:00'))
    if at.tzinfo is None:at=at.replace(tzinfo=UTC)  # The documented field is explicitly UTC.
    ms=(at-EPOCH)//timedelta(milliseconds=1)
    if ms%(STEPS[resolution]*1000):raise ValueError('Native timestamp not aligned to resolution')
    prices={name:{side:str(dec(raw[name+'Price'][side])) for side in ('bid','ask')} for name in ('open','high','low','close')}
    for side in ('bid','ask'):
        o,h,l,c=(dec(prices[n][side]) for n in ('open','high','low','close'))
        if not 0<l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid native OHLC')
    if any(dec(p['ask'])<dec(p['bid']) for p in prices.values()):raise ValueError('Crossed native bid/ask')
    volume=raw.get('lastTradedVolume')
    if volume is not None and dec(volume)<0:raise ValueError('Negative broker-reported volume')
    record={'epic':epic,'resolution':resolution,'source_timestamp_utc':text,'start_ms':ms,'end_ms':ms+STEPS[resolution]*1000,
        'prices':prices,'volume':str(dec(volume)) if volume is not None else None,'volume_kind':'BROKER_REPORTED_NOT_CME_VERIFIED'}
    record['hash']=hashlib.sha256(json.dumps({k:v for k,v in record.items() if k!='source_timestamp_utc'},sort_keys=True).encode()).hexdigest()
    return record


class NativeCandleProvider:
    """Two post-close identical observations; later revisions remain possible."""
    def __init__(self,state,save):
        self.state=state.setdefault('native_candles',{'groups':{},'clock':{}});self.save=save
    def group(self,epic,resolution):
        return self.state['groups'].setdefault(epic+'|'+resolution,{'bars':{},'quarantined_days':{},'polls':0,
            'revisions_after_close':0,'revisions_after_verification':0,'gaps':[],'last_poll_ns':0,'bootstrapped':False})
    def observe(self,epic,resolution,payload,received_ns,*,bootstrap=False,safe_received_ms=None):
        # Validate the WHOLE response before changing durable context.
        rows=[parse_candle(epic,resolution,r) for r in payload['prices']]
        if not rows:raise ValueError('Empty native response')
        starts=[r['start_ms'] for r in rows]
        if len(set(starts))!=len(starts):raise ValueError('Duplicate native source timestamp')
        if starts!=sorted(starts):raise ValueError('Native response order reversed')
        group=self.group(epic,resolution)
        if received_ns<=group['last_poll_ns']:raise ValueError('Native receipt time reversed')
        cutoff=min(received_ns/1e6,safe_received_ms if safe_received_ms is not None else received_ns/1e6)
        group['polls']+=1;group['last_poll_ns']=received_ns;changed=[];ready=[]
        for row in rows:
            key=str(row['start_ms']);old=group['bars'].get(key)
            # The API can retain the still-changing latest bar past its nominal
            # end. A successor is source evidence of rollover, not a time grace.
            closed=row['end_ms']<=cutoff and max(starts)>=row['end_ms']
            day=datetime.fromtimestamp(row['start_ms']/1000,UTC).astimezone(NY).date().isoformat()
            if old and old['hash']!=row['hash']:
                if old.get('first_closed_seen_ns'):
                    group['revisions_after_close']+=1
                    group['revisions_after_verification']+=bool(old.get('verified_at_ns'))
                    group['quarantined_days'][day]='closed_native_bar_revision'
                row.update(first_seen_ns=old['first_seen_ns'],tracked_before_close=old['tracked_before_close'],
                    revised_after_close=bool(old.get('first_closed_seen_ns')) or old.get('revised_after_close',False),
                    previous_hash=old['hash'],revisions=old.get('revisions',0)+1,first_closed_seen_ns=None,
                    confirmations=0,last_closed_observation_ns=None,verified_at_ns=None)
                old=None
            if old is None:
                row.setdefault('first_seen_ns',received_ns);row.setdefault('tracked_before_close',not closed and not bootstrap)
                row.setdefault('revised_after_close',False);row.setdefault('revisions',0)
                row.setdefault('first_closed_seen_ns',None);row.setdefault('confirmations',0)
                row.setdefault('last_closed_observation_ns',None);row.setdefault('verified_at_ns',None)
                group['bars'][key]=row;changed.append(deepcopy(row));old=row
            if closed:
                if old['first_closed_seen_ns'] is None:old['first_closed_seen_ns']=received_ns
                if old['last_closed_observation_ns'] is None or received_ns-old['last_closed_observation_ns']>=10**9:
                    old['confirmations']+=1;old['last_closed_observation_ns']=received_ns
                if old['confirmations']>=2 and old['verified_at_ns'] is None and not old['revised_after_close'] and day not in group['quarantined_days']:
                    old['verified_at_ns']=received_ns
                    old['publication_delay_upper_s']=(old['first_closed_seen_ns']-old['end_ms']*10**6)/1e9 if old['tracked_before_close'] else None
                    old['verification_delay_s']=(received_ns-old['end_ms']*10**6)/1e9
                    ready.append(deepcopy(old))
            else:old['tracked_before_close']=old['tracked_before_close'] or not bootstrap
        group['bootstrap_polls']=group.get('bootstrap_polls',0)+bool(bootstrap)
        group['bootstrapped']=group['bootstrapped'] or group['bootstrap_polls']>=2
        cached=sorted(group['bars'].values(),key=lambda r:r['start_ms']);gaps=[]
        for a,b in zip(cached,cached[1:]):
            if a['end_ms']!=b['start_ms']:gaps.append({'after_ms':a['end_ms'],'before_ms':b['start_ms']})
        group['gaps']=gaps[-50:]
        # Bound the cache, retaining enough source bars to reconstruct the RTH day.
        if len(cached)>600:group['bars']={str(r['start_ms']):r for r in cached[-600:]}
        self.save('capital_native_poll',{'epic':epic,'resolution':resolution,'received_ns':received_ns,
            'observed':len(rows),'changed_versions':changed,'verified':[r['start_ms'] for r in ready],
            'revisions_after_close':group['revisions_after_close'],'gaps':group['gaps']})
        return ready
    def summary(self):
        return {key:{k:v for k,v in g.items() if k!='bars'}|{'cached':len(g['bars']),
            'verified':sum(bool(r.get('verified_at_ns')) for r in g['bars'].values()),
            'live_verified':sum(bool(r.get('verified_at_ns')) and r['tracked_before_close'] for r in g['bars'].values())}
            for key,g in self.state['groups'].items()}


class NativeStrategyEngine:
    """Reuse frozen price hypotheses behind a real-availability gate.

    The replay kernel consumes an explicitly event-time view. Its clock is NOT
    the decision clock: actual verified availability and processing timestamps
    are mandatory in every emitted decision. No order method exists here.
    """
    def __init__(self,provider,state,save):self.provider,self.state,self.save=provider,state,save
    def process(self,broker,now_ns):
        from mnq_sim.strategies import PriceStrategy,StrategyConfig
        from mnq_timestral.strategy import RiskState
        decided=self.state.setdefault('native_processed',{});output=[];statuses={};day=datetime.fromtimestamp(now_ns/1e9,UTC).astimezone(NY).date()
        for key,g in self.provider.state['groups'].items():
            epic,resolution=key.split('|');step=STEPS[resolution]
            rows=sorted((r for r in g['bars'].values() if r.get('verified_at_ns') and r['verified_at_ns']<=now_ns and
                datetime.fromtimestamp(r['start_ms']/1000,UTC).astimezone(NY).date()==day and
                (9,30)<=(datetime.fromtimestamp(r['start_ms']/1000,UTC).astimezone(NY).hour,datetime.fromtimestamp(r['start_ms']/1000,UTC).astimezone(NY).minute)<(16,0)),key=lambda r:r['start_ms'])
            blocked=None
            if str(day) in g['quarantined_days']:blocked=g['quarantined_days'][str(day)]
            elif not g['bootstrapped']:blocked='native_context_bootstrap_pending'
            elif not rows or datetime.fromtimestamp(rows[0]['start_ms']/1000,UTC).astimezone(NY).strftime('%H:%M')!='09:30':blocked='missing_cash_opening_context'
            elif any(a['end_ms']!=b['start_ms'] for a,b in zip(rows,rows[1:])):blocked='native_cash_context_gap'
            spec=broker.instruments.get(epic)
            tick=dec(spec.raw.get('discovery',{}).get('tickSize',0)) if spec else Decimal(0)
            if not spec or tick<=0 or spec.currency!='USD' or dec(spec.raw['instrument'].get('lotSize',0))!=1:blocked='unverified_cfd_contract_units'
            elif any(dec(value)%tick for r in rows for price in r['prices'].values() for value in price.values()):blocked='native_price_off_tick_grid'
            statuses[key]={'blocked':blocked,'verified_session_bars':len(rows),'source':'CAPITAL_NATIVE_BID_ASK','price_basis':'NATIVE_BID',
                'opening_range_minutes':15,'opening_range_bars':900//step,'pivot_left_bars':2,'pivot_right_bars':2,
                'breakout_buffer_cfd_ticks':1,'mss_timeout_bars':max(1,600//step),'volume_use':'DISABLED_UNVERIFIED_BROKER_VOLUME',
                'tick_size':str(tick),'point_value_quote_currency_per_unit':str(spec.raw['instrument'].get('lotSize')) if spec else None,
                'margin_percent':str(spec.margin_percent) if spec else None,'cost_model':'NOT_CALIBRATED_FOR_CFD','parameter_profile':'CFD_NATIVE_EXPERIMENT_V1'}
            if blocked:continue
            kernels={kind:PriceStrategy(StrategyConfig(kind,opening_minutes=900//step,buffer_ticks=1,
                pivot_left=2,pivot_right=2,mss_timeout=max(1,600//step))) for kind in ('orb','sweep_mss')}
            for r in rows:
                start=EPOCH+timedelta(milliseconds=r['start_ms']);end=EPOCH+timedelta(milliseconds=r['end_ms']);scale=Decimal('.25')/tick
                view=SimpleNamespace(symbol=epic,contract=epic,start=start,end=end,available_at=end,
                    **{n:float(dec(r['prices'][n]['bid'])*scale) for n in ('open','high','low','close')})
                for kind,kernel in kernels.items():
                    side=kernel.on_bar(view)
                    decision_id='|'.join((key,kind,str(r['start_ms'])))
                    if decision_id in decided:continue
                    # Historical bootstrap reconstructs state, not forward opportunities.
                    decided[decision_id]=r['hash']
                    if not r['tracked_before_close']:continue
                    q=broker.state['quotes'].get(epic,{});fresh=0<=now_ns/1e6-q.get('timestamp_ms',0)<=5000
                    cap=broker.state;balance=cap.get('balance',{})
                    risk_ok,risk_reason=broker.config.risk().allow(RiskState(realized=float(balance.get('balance',0))-float(cap.get('day_baseline') or 0),
                        unrealized=float(balance.get('profitLoss',0)),drawdown=float(cap.get('broker_drawdown',0)),trades=cap.get('daily_opening_attempts',0),
                        consecutive_losses=cap.get('consecutive_losses',0),positions=len(cap['positions']),kill=bool(cap['halt']),data_fresh=fresh))
                    reason='strategy_no_candidate' if not side else ('stale_rest_price' if not fresh else
                        'late_native_bar_availability' if now_ns-r['end_ms']*10**6>5*10**9 else 'uncertified_news_and_strategy')
                    output.append({'decision_id':decision_id,'strategy':kind,'epic':epic,'resolution':resolution,'side':side,
                        'bar_start_ms':r['start_ms'],'bar_end_ms':r['end_ms'],'bar_hash':r['hash'],
                        'available_at_ns':r['verified_at_ns'],'decided_at_ns':now_ns,'publication_delay_upper_s':r['publication_delay_upper_s'],
                        'price_basis':'NATIVE_BID','opening_range_bars':900//step,'parameter_profile':'CFD_NATIVE_EXPERIMENT_V1',
                        'risk_allowed':risk_ok,'risk_reason':risk_reason,'reason':reason,'order_requested':False,'execution_eligible':False,
                        'quote':deepcopy(q),'strict_news_certified':False,'strategy_approved':False,
                        'kernel_event_time_audit':deepcopy(kernel.audit),'audit_timestamps_are_event_time_not_availability':True})
        self.state['native_strategy_status']=statuses
        self.state['native_decisions']=(self.state.get('native_decisions',[])+output)[-200:]
        self.state['native_signal_count']=self.state.get('native_signal_count',0)+sum(bool(e['side']) for e in output)
        self.state['native_rejected_signals']=self.state.get('native_rejected_signals',0)+sum(bool(e['side']) for e in output)
        if output:self.save('capital_native_decisions',{'decisions':output})
        return output


class NativeObservationCycle:
    """One read-only cycle in the existing runtime and journal owner."""
    def __init__(self,runtime,*,clock_ns=time.time_ns):
        self.runtime=runtime;runtime.native_provider=True;self.broker=runtime.broker;self.clock_ns=clock_ns
        self.provider=NativeCandleProvider(self.broker.state,self.broker.journal.save)
        self.engine=NativeStrategyEngine(self.provider,self.broker.state,self.broker.journal.save)
        self.full_reads={};self.last_full={}
    def poll(self):
        b=self.broker;h=b.http;h.orders_enabled=False;now=self.clock_ns();clock=self.provider.state['clock']
        if not clock or now-clock['checked_at_ns']>=60*10**9:
            before=self.clock_ns();mono=time.monotonic_ns();server=h.request('GET','/time')['serverTime'];after=self.clock_ns()
            if type(server) is not int or after<before or abs((after-before)-(time.monotonic_ns()-mono))>100*10**6:
                raise ValueError('Native clock sample invalid')
            clock.update(checked_at_ns=after,offset_lower_ms=server-after/1e6,offset_upper_ms=server-before/1e6,
                request_ms=(after-before)/1e6,source='OFFICIAL_GET_TIME_RTT_BOUNDS')
        errors={}
        for epic in ('US100','US500'):
            if epic not in b.instruments:continue
            for resolution in STEPS:
                g=self.provider.group(epic,resolution);key=epic+'|'+resolution;now=self.clock_ns()
                bootstrap=self.full_reads.get(key,0)<2 or (not g['bootstrapped'] and now-self.last_full.get(key,0)>60*10**9)
                if bootstrap:self.full_reads[key]=self.full_reads.get(key,0)+1;self.last_full[key]=now
                started=time.monotonic_ns()
                try:
                    payload=h.request('GET',f'/prices/{epic}?resolution={resolution}&max={500 if bootstrap else 10}')
                    received=self.clock_ns()
                    self.runtime.metrics.add(key+'.native_request_ms',(time.monotonic_ns()-started)/1e6)
                    if received-clock['checked_at_ns']>120*10**9:raise ValueError('Native clock evidence expired')
                    # A possibly-ahead client must not mark a source bar complete early.
                    safe=received/1e6+min(0,clock['offset_lower_ms'])
                    processing=time.monotonic_ns()
                    ready=self.provider.observe(epic,resolution,payload,received,bootstrap=bootstrap,safe_received_ms=safe)
                    self.runtime.metrics.add(key+'.native_validation_persist_ms',(time.monotonic_ns()-processing)/1e6)
                    for r in ready:
                        if r['tracked_before_close']:
                            self.runtime.metrics.add(key+'.observed_publication_upper_s',r['publication_delay_upper_s'])
                            self.runtime.metrics.add(key+'.verification_delay_s',r['verification_delay_s'])
                    g.pop('last_error',None)
                except (ValueError,KeyError,TypeError) as error:
                    # Invalid payloads remain evidence, never repaired or fed to signals.
                    code={'Crossed native bid/ask':'native_crossed_bid_ask','Invalid native OHLC':'native_invalid_ohlc'}.get(str(error),'native_response_validation_failed')
                    errors[key]=code;g['last_error']=code;g['invalid_responses']=g.get('invalid_responses',0)+1
                    day=datetime.fromtimestamp(self.clock_ns()/1e9,UTC).astimezone(NY).date().isoformat()
                    g['quarantined_days'][day]='invalid_native_response'
                    b.journal.save('capital_native_rejected',{'epic':epic,'resolution':resolution,'received_ns':self.clock_ns(),
                        'reason':code,'prices':payload.get('prices',[]) if isinstance(payload,dict) else []})
        now=self.clock_ns();begin=time.monotonic_ns();events=self.engine.process(b,now)
        self.runtime.metrics.add('native_processing_ms',(time.monotonic_ns()-begin)/1e6)
        b.state.update(native_summary=self.provider.summary(),native_errors=errors,native_feed_certified=False,
            native_feed_policy='SUCCESSOR_AND_TWO_STABLE_POST_CLOSE_READS_REVISION_QUARANTINE',
            native_observation_at_ns=now,continuous_strategy_orders_enabled=False,
            indicator_status=b.state.get('native_strategy_status',{}),feed_metrics=self.runtime.metrics.snapshot())
        b.ready=False  # Observation is never an order eligibility certificate.
        b.journal.save('capital_native_cycle',{'decisions':len(events),'errors':errors,'orders_enabled':False})
        return events
