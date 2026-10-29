"""V6 DEMO launcher and V5 dashboard extension. No production broker exists."""
import argparse
from collections import defaultdict,deque
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import getpass
import json
from pathlib import Path
import queue
import re
import shlex
import signal
import subprocess
import threading
import time
import warnings
from types import SimpleNamespace

from mnq_timestral.schema import NY
from .capital import (BASE,STREAM,SERVICE,CapitalError,Credentials,CapitalConfig,
                      CapitalHTTP,CapitalJournal,CapitalBroker,Quote,dec,safe_error_code,
                      encode_keychain_value,decode_keychain_value,validate_credential_field,rest_snapshot_payload)
from .dashboard import Dashboard,Handler,View
from .replay import ROOT,atomic_json
UTC=timezone.utc


class FeedMetrics:
    """Bounded rolling measurements; source age is NOT one-way transport."""
    def __init__(self):self.samples=defaultdict(lambda:deque(maxlen=2048));self.counts=defaultdict(int)
    def add(self,name,value):self.samples[name].append(value);self.counts[name]+=1
    def snapshot(self):
        result={'transport_latency':'NOT_IDENTIFIABLE','window_limit':2048}
        for name,values in self.samples.items():
            a=sorted(values)
            result[name]={'n':self.counts[name],'window_n':len(a),
                **{k:a[int((len(a)-1)*p)] for k,p in [('p50',.5),('p95',.95),('p99',.99),('max',1.)]}}
        return result


class StreamInbox:
    """Single recv owner. No disk, HTTP or signal work on the receive thread."""
    def __init__(self,ws,capacity=256):
        self.ws=ws;self.buffer=queue.Queue(capacity);self.stopped=threading.Event();self.error=None
    def __enter__(self):
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start();return self
    def _run(self):
        while not self.stopped.is_set():
            try:
                raw=self.ws.recv(timeout=.25)
                item=(raw,datetime.now(UTC),time.monotonic_ns())
                self.buffer.put_nowait(item)
            except TimeoutError:continue
            except queue.Full:self.error=CapitalError('stream_receive_queue_overflow');return
            except Exception:self.error=CapitalError('stream_receive_disconnected');return
    def recv(self,timeout=.25):
        if self.error:raise self.error
        try:return self.buffer.get(timeout=timeout)
        except queue.Empty:raise TimeoutError from None
    def __exit__(self,*_):self.stopped.set();self.thread.join(1)


class CFDSignals:
    """Price-only V2 hypotheses with broker-discovered price-unit scaling.

    VWAP is BLOCKED: quote counts are not verified traded volume. Partial cash
    opening sessions are blocked. Original evaluator receives event-time bars
    only after actual arrival; arrival is logged separately, never backdated as
    a receipt or an order timestamp.
    """
    def __init__(self,spec,connected_at):
        self.spec=spec;self.connected_at=connected_at
        tick=spec.raw.get('discovery',{}).get('tickSize')
        self.tick=dec(tick) if tick is not None else None
        self.current=None;self.last_ms=None;self.blocked=None;self.strategies={};self.day=None
    def on_quote(self,q):
        if q.epic!=self.spec.epic or (self.last_ms is not None and q.timestamp_ms<=self.last_ms):raise ValueError('Duplicate/reversed quote')
        self.last_ms=q.timestamp_ms
        start=q.at.replace(second=0,microsecond=0)
        local=start.astimezone(NY);day=local.date()
        if self.day!=day:
            self.day=day;self.strategies={};self.current=None;self.blocked=None
        if not (9,30)<=(local.hour,local.minute)<(16,0):return []
        anchor=local.replace(hour=9,minute=30,second=0,microsecond=0).astimezone(UTC)
        if not self.strategies and self.blocked is None:
            if start!=anchor or self.connected_at>anchor:self.blocked='partial_opening_session'
            elif self.tick is None or self.tick<=0:self.blocked='unverified_cfd_tick_size'
            else:
                from mnq_sim.strategies import PriceStrategy,StrategyConfig
                self.strategies={k:PriceStrategy(StrategyConfig(k)) for k in ('orb','sweep_mss')}
        if self.blocked:return []
        price=float((q.bid+q.ask)/2)
        result=[]
        if self.current and start!=self.current['start']:
            old=self.current
            if start!=old['start']+timedelta(minutes=1):
                self.blocked='quote_bar_gap';self.current=None;return []
            end=old['start']+timedelta(minutes=1)
            # Scale prices, not risk: one original algorithm buffer tick maps to
            # one API-discovered CFD tick. No CME tick value or multiplier used.
            scale=.25/float(self.tick)
            bar=SimpleNamespace(symbol=self.spec.epic,contract=self.spec.epic,start=old['start'],end=end,
                available_at=end,open=old['open']*scale,high=old['high']*scale,
                low=old['low']*scale,close=old['close']*scale)
            for kind,strategy in self.strategies.items():
                side=strategy.on_bar(bar)
                if side:
                    result.append({'strategy':kind,'epic':q.epic,'side':side,
                        'bar_end':end.isoformat(),'received_at':q.received_at.isoformat(),
                        'mid_close':old['close'],'source':'LIVE_DEMO_CFD_QUOTE_MIDPOINT',
                        'experimental':True,'approved':False})
        if self.current is None or start!=self.current['start']:
            self.current={'start':start,'open':price,'high':price,'low':price,'close':price}
        else:
            self.current['high']=max(self.current['high'],price)
            self.current['low']=min(self.current['low'],price);self.current['close']=price
        return result


class DemoRuntime:
    def __init__(self,broker,*,clock=lambda:datetime.now(UTC),strategy='orb'):
        if strategy not in ('orb','sweep_mss'):raise ValueError('Only existing price-only CFD research signals supported')
        self.broker,self.clock,self.strategy=broker,clock,strategy
        self.sources={e:CFDSignals(s,self.clock()) for e,s in broker.instruments.items()}
        self.connected=False;self.paused=False;self.last_quote=None;self.fresh_quotes=0
        self.seen=set(broker.state.get('seen_signals',[]));self.day=None
        self.metrics=FeedMetrics()
    def on_quote(self,payload,*,source='WEBSOCKET',received_at=None):
        now=self.clock();q=Quote.parse(payload,now)
        received_at=now if received_at is None else received_at
        if received_at.tzinfo is None or received_at>now:raise ValueError('Invalid quote receipt time')
        q=Quote.parse(payload,received_at)  # Preserve capture time; validate again at use.
        if q.epic not in self.sources:raise ValueError('Unsubscribed instrument quote')
        old=self.broker.state['quotes'].get(q.epic)
        if old and q.timestamp_ms<=old['timestamp_ms']:raise ValueError('Duplicate/reversed quote')
        events=[] if getattr(self,'native_provider',False) else self.sources[q.epic].on_quote(q)
        cap=self.broker.state;cap['received']+=1;self.fresh_quotes+=1;self.last_quote=now
        cap['quotes'][q.epic]={'epic':q.epic,'bid':str(q.bid),'ask':str(q.ask),'spread':str(q.spread),
            'timestamp_ms':q.timestamp_ms,'quote_at':q.at.isoformat(),'received_at':received_at.isoformat(),
            'processed_at':now.isoformat(),'source':source}
        for event in events:
            event.update(quote_source=source,bar_quality='SAMPLED_REST_NOT_COMPLETE_OHLC' if source=='REST_SNAPSHOT' else 'BROKER_QUOTE_MIDPOINT',
                execution_eligible=False,trigger_quote=deepcopy(cap['quotes'][q.epic]),
                strict_news_certified=False,strategy_economically_approved=False)
            key='|'.join(str(event[k]) for k in ('strategy','epic','side','bar_end'))
            if key in self.seen:continue
            self.seen.add(key);cap['seen_signals']=sorted(self.seen);cap['signals']+=1
            event['order_requested']=False;reason='signals_only'
            if self.broker.config.mode=='strict_demo':reason='uncertified_news_and_strategy'
            elif self.broker.config.mode=='diagnostic_demo' and event['strategy']==self.strategy:
                # Preparation is not certification. No flag or UI action can
                # turn uncertified strategy/news into automatic broker orders.
                reason='automated_demo_not_certified'
            event['reason']=reason;cap['decisions'].append(event);cap['decisions']=cap['decisions'][-200:]
            self.broker.journal.save('capital_signal',event)
        cap['indicator_status']={e:{'price_hypotheses':s.blocked or ('WARMING_UP' if not s.strategies else 'CAUSAL_QUOTE_BARS'),
            'vwap':'BLOCKED_NO_VERIFIED_TRADED_VOLUME','tick_size':str(s.tick) if s.tick else None,
            'quote_source':cap['quotes'].get(e,{}).get('source'),
            'bar_quality':'SAMPLED_REST_NOT_COMPLETE_OHLC' if cap['quotes'].get(e,{}).get('source')=='REST_SNAPSHOT' else 'BROKER_QUOTE_MIDPOINT'} for e,s in self.sources.items()}
        self.broker.journal.save('capital_quote',cap['quotes'][q.epic])
        return events
    def observe_rest(self):
        """No technical/strategy orders from this explicitly degraded path."""
        self.connected=False;self.broker.http.orders_enabled=False
        for epic in self.sources:
            started=time.monotonic_ns()
            matches=[m for m in self.broker.http.request('GET','/markets?searchTerm='+epic).get('markets',[]) if m.get('epic')==epic]
            received_at=self.clock()
            self.metrics.add('rest_request_ms',(time.monotonic_ns()-started)/1e6)
            if len(matches)!=1:raise CapitalError('rest_observation_identity_mismatch')
            payload=rest_snapshot_payload(matches[0])
            self.metrics.add('rest_source_age_ms',received_at.timestamp()*1000-payload['timestamp'])
            old=self.broker.state['quotes'].get(epic)
            if old and payload['timestamp']<=old['timestamp_ms']:continue
            try:
                self.on_quote(payload,source='REST_SNAPSHOT',received_at=received_at)
                self.broker.state.setdefault('observation_errors',{}).pop(epic,None)
            except ValueError:
                self.broker.state.setdefault('observation_errors',{})[epic]='invalid_or_stale_rest_quote'
                self.broker.journal.save('capital_observation_rejected',{'epic':epic,'source':'REST_SNAPSHOT',
                    'timestamp_ms':payload['timestamp'],'received_at':received_at.isoformat(),
                    'bid':str(payload['bid']),'ask':str(payload['ofr']),'reason':'invalid_or_stale_rest_quote'})
        now_ms=self.clock().timestamp()*1000
        self.broker.state['quote_freshness']={epic:0<=now_ms-self.broker.state['quotes'].get(epic,{}).get('timestamp_ms',0)<=5000 for epic in self.sources}
        self.broker.state['data_fresh']=all(self.broker.state['quote_freshness'].values())
        self.broker.state['continuous_strategy_orders_enabled']=False
        self.broker.state['ws_health']='BLOCKED_STALE_OR_UNAVAILABLE'
        self.broker.state['feed_metrics']=self.metrics.snapshot()
    def watchdog(self):
        cap=self.broker.state
        stale=not self.last_quote or (self.clock()-self.last_quote).total_seconds()>5
        if hasattr(self,'sources'):
            ms=self.clock().timestamp()*1000
            stale=stale or any(not 0<=ms-cap['quotes'].get(e,{}).get('timestamp_ms',0)<=5000 for e in self.sources)
        if stale:self.broker.ready=False;raise CapitalError('stale_quote_entries_blocked')
        if cap['halt']:raise CapitalError(cap['halt'])
        return True
    def require_fresh_stream(self,connected_for):
        # A live socket can contain an old backlog after a pause. Reconnect to
        # discard it; never relax timestamps or fabricate replacement prices.
        stale=not self.last_quote or (self.clock()-self.last_quote).total_seconds()>5
        if stale and connected_for>=10:raise CapitalError('stale_stream_reconnect')
    def disconnect(self):
        self.connected=False;self.fresh_quotes=0;self.broker.ready=False
        self.broker.journal.save('capital_disconnected')
    def technical_test(self,epic):
        self.watchdog()
        if self.fresh_quotes<20 or not self.connected:raise CapitalError('twenty_live_quotes_required')
        b=self.broker;b.reconcile()
        b.technical_open(epic)
        key='technical-first-forward';protected=False;deal=None
        try:
            for _ in range(12):
                time.sleep(.3);b.reconcile();intent=b.state['intents'][key]
                deal=intent.get('deal_id')
                if intent['state']=='FILLED':
                    protected=True
                    row=next(p['position'] for p in b.state['positions'] if p['position']['dealId']==deal)
                    b.state['technical_protection']={'verified':True,'stop_level':row['stopLevel'],
                        'profit_level':row['profitLevel'],'entry_level':row['level'],'size':row['size']}
                    b.journal.save('capital_actual_protection_verified',b.state['technical_protection'])
                    break
                if intent['state']=='REJECTED' or b.state['halt']:break
            if not protected:raise CapitalError('technical_protection_or_entry_not_verified')
        finally:
            # A positively bound observed position is closed even if protection
            # verification failed; unknown/foreign IDs are NEVER guessed.
            if deal and any(p['position']['dealId']==deal for p in b.state['positions']):
                previous=b.http.orders_enabled;b.http.orders_enabled=True
                try:b.close_position(key+'-close',deal)
                finally:b.http.orders_enabled=previous
        for _ in range(12):
            time.sleep(.3);b.reconcile()
            if b.state['intents'].get(key+'-close',{}).get('state')=='CONFIRMED_CLOSED':
                if b.state['positions'] or b.state['working_orders']:raise CapitalError('technical_exit_not_flat')
                b.state['technical_roundtrip_verified']=True
                b.journal.save('capital_actual_demo_roundtrip_verified')
                return
        raise CapitalError('technical_close_not_confirmed_no_resubmit')


def model_evidence():
    result=[]
    for model in ('28M','209M'):
        path=ROOT/'reports/timestral-real'/('benchmark-'+model+'.json')
        if path.is_file():
            doc=json.loads(path.read_text());p=doc['MES_prediction']
            result.append({'model':model,'market':'CME MES HISTORICAL — NOT CAPITAL CFD',
                'origin':p['origin'],'medians':p['medians'],'horizons':p['horizons'],
                'latency_seconds':p['latency_seconds'],'used_for_cfd_orders':False})
    return result


class DemoView(View):
    def publish(self,value):
        with self.lock:self.value=deepcopy(value)


JS=r"""
const el=id=>document.getElementById(id), token='__TOKEN__';
function table(id,rows){const root=el(id);root.replaceChildren();if(!rows.length){root.textContent='None reported';return}const keys=Object.keys(rows[0]);let t=document.createElement('table'),h=t.createTHead().insertRow();for(let k of keys){let c=document.createElement('th');c.textContent=k;h.append(c)}let b=t.createTBody();for(let r of rows){let row=b.insertRow();for(let k of keys)row.insertCell().textContent=typeof r[k]==='object'?JSON.stringify(r[k]):String(r[k]??'—')}root.append(t)}
async function refresh(){try{const res=await fetch('/api/status',{cache:'no-store'});if(!res.ok)throw Error();const d=await res.json(),c=d.capital||{};el('status').textContent=d.phase+' · '+d.connection+' · '+(d.error||'');for(let[k,v]of Object.entries({net:c.broker_net,gross:c.model_net,fees:null,trades:Object.keys(c.fills||{}).length,max_drawdown:c.broker_drawdown,ambiguities:c.received||0}))el(k).textContent=v==null?'—':Number(v).toFixed(2);el('details').textContent='Broker: Capital.com DEMO\nREST origin: DEMO hard-locked\nAuthenticated: '+d.authenticated+'\nAccount currency: '+(c.account_currency||'unverified')+'\nMode: '+d.mode+'\nNews: UNCERTIFIED / strict entries BLOCKED\nRisk halt: '+(c.halt||'none')+'\nBroker P&L: account balance delta + reported UPL; fees NOT independently certified\nModel P&L: unavailable until CFD point-value verification\nTechnical roundtrip: '+!!c.technical_roundtrip_verified;el('positions').textContent=JSON.stringify(c.positions||[],null,2);table('trade-table',Object.entries(c.intents||{}).slice(-20).map(([id,v])=>({id,state:v.state,operation:v.operation,epic:v.epic,size:v.size,reference:v.reference})));table('orders-table',(c.working_orders||[]));table('decision-table',(c.native_decisions||c.decisions||[]).slice(-10).reverse());table('quote-table',Object.values(c.quotes||{}));el('models').textContent=JSON.stringify(d.timestral_historical_readonly||[],null,2);el('indicator-status').textContent=JSON.stringify({native_bars:c.native_summary||{},strategies:c.native_strategy_status||c.indicator_status||{},metrics:c.feed_metrics||{},automatic_orders:false,websocket:'QUARANTINED'},null,2)}catch(e){el('status').textContent='LOCAL MONITOR UNAVAILABLE — no broker connection implied'}}
document.querySelectorAll('button[data-action]').forEach(b=>b.onclick=async()=>{await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json','X-Control-Token':token},body:JSON.stringify({action:b.dataset.action})});refresh()});setInterval(refresh,1000);refresh();
"""


class DemoHandler(Handler):
    def reply(self,status,value,content_type='application/json'):
        if isinstance(value,dict) and value.get('scope')=='LOCAL_REPLAY_ONLY':value={**value,'scope':'CAPITAL_DEMO_ONLY'}
        return super().reply(status,value,content_type)
    def do_GET(self):
        if self.path!='/':return super().do_GET()
        if not self._valid_host():return self.reply(403,{'error':'Host rejected'})
        page=Path(__file__).with_name('dashboard.html').read_text().split('<script nonce=')[0]
        page=page.replace('TRADING BOT · Local Replay','TRADING BOT · Capital DEMO').replace('OFFLINE · NO LIVE ROUTING','DEMO ONLY · PRODUCTION BLOCKED')
        page=page.replace('V3/V4 runtime · persistent journal · observed CME bars','V5 journal / risk / dashboard · separate CFD coordinator')
        page=re.sub(r'<div class="modes">.*?</div>\n','<div class="modes"><div class="mode">HISTORICAL REPLAY · separate / unchanged</div><div class="mode active">CAPITAL LIVE DATA / DEMO ONLY · authentication required</div><div class="mode">REAL-MONEY TRADING · NO ROUTE EXISTS</div></div>\n',page)
        page=re.sub(r'<div class="banner">.*?</div>','<div class="banner">EXPERIMENTAL CFD DEMO. NOT CME MNQ/MES. No profitability approval. Missing credentials means NO LIVE QUOTES and NO DEMO FILLS. Timestral CME history is read-only, OFF for CFD orders.</div>',page)
        page=page.replace('Realized net / USD','Broker equity delta / USD').replace('Gross / USD','Model P&amp;L / USD').replace('Fees / USD','Certified fees / USD').replace('Closed trades','Confirmed entries').replace('Intrabar flags','Received quotes')
        page=page.replace('<canvas id="equity" width="1000" height="200"></canvas>','<div id="quote-table"></div>').replace('Simulated equity / USD','Live DEMO CFD bid / ask / spread').replace('Marked on observed bar closes, not tick-level equity.','Original broker UNIX ms + actual UTC reception time; stale quotes rejected.')
        page=page.replace('<progress id="progress" value="0" max="780"></progress>','').replace('Simulated trades','DEMO requests / confirmations').replace('Positions / simulated only','Broker DEMO positions').replace('Working simulated orders / protective prices','Broker DEMO working orders').replace('An empty list means no local working orders, NOT a broker account check.','Only an authenticated snapshot verifies account state.')
        page=page.replace('· <a href="/download/trades.csv" download="trades.csv">Export CSV</a>','').replace('Data: owned GLBX.MDP3 / ohlcv-1m','Capital.com DEMO CFD data; CME results remain separate')
        page+='<section class="panel"><h2>Indicator readiness</h2><pre id="indicator-status"></pre><h2>Timestral actual inference / historical CME only</h2><pre id="models"></pre></section>'
        currency=self.server.view.read().get('capital',{}).get('account_currency')
        if currency in ('EUR','GBP','USD'):page=page.replace(' / USD',' / '+currency)
        page+='<script nonce="'+self.server.control_token+'">'+JS.replace('__TOKEN__',self.server.control_token)+'</script></html>'
        return self.reply(200,page,'text/html')


def _keychain_read(service):
    p=subprocess.run(['security','find-generic-password','-a','trading-bot','-s',service,'-w'],capture_output=True,text=True)
    if p.returncode not in (0,44):raise CapitalError('keychain_access_failed')
    return decode_keychain_value(p.stdout.removesuffix('\n')) if p.returncode==0 else None


def store_setup_credentials(credentials,*,verified=False,attempted=True,diagnostic=None):
    # Secrets travel through stdin, never argv, console, files or environment.
    service=SERVICE if verified else SERVICE+'.pending'
    value=asdict(credentials) if verified else {'credentials':asdict(credentials),'api_key_label':'claude','attempted':attempted,'diagnostic':diagnostic}
    command='add-generic-password -U -a trading-bot -s '+shlex.quote(service)+' -w '+encode_keychain_value(json.dumps(value))+'\n'
    p=subprocess.run(['security','-i'],input=command,text=True,capture_output=True)
    if p.returncode:raise CapitalError('keychain_storage_failed')
    try:readback=json.loads(_keychain_read(service) or 'null')
    except (ValueError,TypeError):raise CapitalError('keychain_readback_failed') from None
    if readback!=value:raise CapitalError('keychain_readback_failed')
    if verified:
        command='add-generic-password -U -a trading-bot -s '+shlex.quote(SERVICE+'.api-key')+' -w '+encode_keychain_value(credentials.api_key)+'\n'
        p=subprocess.run(['security','-i'],input=command,text=True,capture_output=True)
        if p.returncode:raise CapitalError('keychain_storage_failed')
        if _keychain_read(SERVICE+'.api-key')!=credentials.api_key:raise CapitalError('keychain_readback_failed')
        subprocess.run(['security','delete-generic-password','-a','trading-bot','-s',SERVICE+'.pending'],capture_output=True,text=True)


def hidden_input(field):
    """Never allow getpass to fall back to echoing stdin in a non-TTY shell."""
    prompts={'identifier':'Capital login identifier: ',
             'password':'API key CUSTOM password (not login password): '}
    if field not in prompts:raise ValueError('Unsupported hidden input field')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning)
            value=getpass.getpass(prompts[field])
    except getpass.GetPassWarning:raise CapitalError('hidden_input_unavailable_'+field) from None
    except EOFError:raise CapitalError('hidden_input_eof_'+field) from None
    except KeyboardInterrupt:raise CapitalError('hidden_input_cancelled_'+field) from None
    except UnicodeError:raise CapitalError('hidden_input_encoding_failed_'+field) from None
    except OSError:raise CapitalError('hidden_input_terminal_failed_'+field) from None
    validate_credential_field(field,value)
    return value


def load_setup_credentials(replace=False,*,allow_prompt=True):
    key=_keychain_read(SERVICE+'.api-key')
    if not replace:
        pending=_keychain_read(SERVICE+'.pending')
        if pending is not None:
            try:
                record=json.loads(pending);creds=Credentials(**record['credentials'])
                if key is not None and key!=creds.api_key:raise CapitalError('keychain_api_key_mismatch')
                return creds
            except (ValueError,TypeError,KeyError):raise CapitalError('malformed_demo_keychain_record') from None
        complete=_keychain_read(SERVICE)
        if complete is not None:
            try:creds=Credentials(**json.loads(complete))
            except (ValueError,TypeError,KeyError):raise CapitalError('malformed_demo_keychain_record') from None
            if key is not None and key!=creds.api_key:raise CapitalError('keychain_api_key_mismatch')
            return creds
    if key is None:raise CapitalError('missing_demo_api_key_in_keychain')
    validate_credential_field('api_key',key)
    if not allow_prompt:
        raise CapitalError('missing_identifier_and_custom_api_password' if key else 'missing_demo_credentials_in_keychain')
    identifier=hidden_input('identifier')
    password=hidden_input('password')
    return Credentials(key,identifier,password,'UNBOUND')


def configure_credentials(replace=False,*,allow_prompt=True):
    """Local-only configuration. Existing values never prompt or reset a latch."""
    credentials=load_setup_credentials(replace,**({'allow_prompt':False} if not allow_prompt else {}))
    if replace or (_keychain_read(SERVICE+'.pending') is None and _keychain_read(SERVICE) is None):
        store_setup_credentials(credentials,attempted=False)
    return credentials


def credential_failure_phase(code):
    if code.startswith('hidden_input_'):return 'credential_input'
    if code.startswith('credential_'):return 'credential_validation'
    if code.startswith('keychain_') or code=='malformed_demo_keychain_record':return 'keychain_configuration'
    return 'credentials'


def setup(replace=False,*,allow_prompt=True,report_path=None,diagnostic_only=False):
    phase='credentials';http=None;requests=0;saved_locally=False
    def result(error=None):
        value={'status':'BLOCKED' if error else 'AUTHENTICATED_DEMO',
            'reason':error.code if error else None,'phase':phase,
            'authentication_requests':requests,'session_response':http.session_evidence if http else None,
            'session_and_accounts_verified':bool(http and http.verified),
            'credentials_saved':saved_locally,'orders_enabled':False,
            'production_routing':False,**(error.diagnostic() if error else {'http_status':200,'errorCode':None})}
        if report_path:atomic_json(report_path,value)
        if diagnostic_only:
            value={**(error.diagnostic() if error else {'http_status':200,'errorCode':None}),
                'phase':phase+'.'+error.code if error else 'AUTHENTICATED_DEMO'}
        print(json.dumps(value))
    try:
        provisional=configure_credentials(replace,allow_prompt=allow_prompt)
        saved_locally=True
        cached=_keychain_read(SERVICE+'.pending')
        if cached:
            try:record=json.loads(cached)
            except ValueError:raise CapitalError('malformed_demo_keychain_record') from None
            if record.get('attempted'):
                phase='saved_attempt'
                diagnostic=record.get('diagnostic') or {}
                raise CapitalError('authentication_retry_blocked',diagnostic.get('http_status'),
                    safe_error_code(diagnostic.get('errorCode'),(provisional.api_key,provisional.identifier,provisional.password)))
        # Mark before I/O: even an interrupted/unknown POST is never auto-repeated.
        phase='keychain_staging'
        store_setup_credentials(provisional,attempted=True)
        http=CapitalHTTP(provisional,orders_enabled=False)
        try:
            phase='session_post';requests=1
            value=http.request('POST','/session',{'identifier':provisional.identifier,
                'password':provisional.password,'encryptedPassword':False})
            phase='demo_verification'
            if value.get('hasActiveDemoAccounts') is not True:raise CapitalError('no_active_demo_account')
            credentials=Credentials(provisional.api_key,provisional.identifier,provisional.password,value.get('currentAccountId',''))
            if provisional.account!='UNBOUND' and provisional.account!=credentials.account:raise CapitalError('demo_account_identity_mismatch')
            http.credentials=credentials
            http.verify_session(value)  # GET/session + GET/accounts, NOT a second POST
        except CapitalError as error:
            store_setup_credentials(provisional,attempted=True,diagnostic=error.diagnostic())
            raise
        phase='keychain_save'
        store_setup_credentials(credentials,verified=True)
        phase='complete';result()
        return http
    except CapitalError as error:
        # Local cause is independent of HTTP status: null never means success.
        if phase=='credentials':phase=credential_failure_phase(error.code)
        result(error)
        raise SystemExit(1) from None


def status(cap=None,*,error=None,authenticated=False,connection='DISCONNECTED',mode='signals_only'):
    return {'phase':'LIVE_DEMO' if authenticated else 'BLOCKED_NO_AUTHENTICATED_BROKER',
        'broker':'Capital.com DEMO','mode':mode,'authenticated':authenticated,'connection':connection,'error':error,
        'capital':deepcopy({k:v for k,v in (cap or {}).items() if k not in ('native_candles','native_processed')}),'timestral_historical_readonly':model_evidence(),
        'real_money_routing':False,'strategy_approved':False,'updated_at':datetime.now(UTC).isoformat()}


def stream_failure_status(broker,reason,mode):
    # Transport health and DEMO authentication are independent facts.
    return status(broker.state,error=reason,authenticated=broker.http.verified,connection='RECONNECTING',mode=mode)


def native_observer(runtime,view,commands,stopped,folder,mode):
    """Native bars own signals; REST snapshots only observe current bid/ask."""
    from .capital_candles import NativeObservationCycle
    b=runtime.broker;cycle=NativeObservationCycle(runtime);last_reconcile=last_metadata=0
    b.state['native_runtime_started_ns']=time.time_ns()
    b.state['native_runtime_starts']=b.state.get('native_runtime_starts',0)+1
    b.journal.save('capital_native_started',{'orders_enabled':False,'websocket_enabled':False})
    while not stopped.is_set():
        began=time.monotonic()
        try:
            b.http.orders_enabled=False
            if began-last_reconcile>=10:b.reconcile();last_reconcile=time.monotonic()
            if began-last_metadata>=60:
                b.discover();last_metadata=time.monotonic()
                runtime.sources={epic:runtime.sources.get(epic) or CFDSignals(spec,runtime.clock()) for epic,spec in b.instruments.items()}
            while not commands.empty():
                action=commands.get_nowait()
                if action=='kill':b.flatten();runtime.paused=True
                elif action=='pause':runtime.paused=True
                elif action=='resume':runtime.paused=False
            runtime.observe_rest()
            cycle.poll()
            connection='NATIVE_CANDLES_SIGNALS_ONLY'
            if b.state.get('native_errors') or any(g.get('blocked') for g in b.state['native_strategy_status'].values()):
                connection='NATIVE_CANDLES_OBSERVATION_BLOCKED_SIGNALS'
            b.state['native_observation_paused']=runtime.paused
            value=status(b.state,authenticated=b.http.verified,connection=connection,mode=mode)
            view.publish(value);atomic_json(folder/'health.json',value)
        except (CapitalError,ValueError,KeyError,TypeError) as error:
            reason=error.code if isinstance(error,CapitalError) else 'native_observation_validation_failed'
            b.ready=False;b.state['data_fresh']=False
            b.journal.save('capital_native_error',{'reason':reason})
            value=status(b.state,error=reason,authenticated=b.http.verified,connection='NATIVE_CANDLES_DEGRADED',mode=mode)
            view.publish(value);atomic_json(folder/'health.json',value)
            if isinstance(error,CapitalError) and (error.status in (401,403) or error.code=='authentication_retry_blocked'):
                while not stopped.wait(.5):pass
        stopped.wait(max(.1,2-(time.monotonic()-began)))


def app(args,*,session=None):
    folder=ROOT/'data/capital-v6'/args.mode;folder.mkdir(parents=True,exist_ok=True)
    view=DemoView();commands=queue.Queue();view.publish(status(mode=args.mode))
    server=Dashboard(('127.0.0.1',args.port),view,commands,folder);server.RequestHandlerClass=DemoHandler
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    stopped=threading.Event()
    for s in (signal.SIGINT,signal.SIGTERM):signal.signal(s,lambda *_:stopped.set())
    print(f'CAPITAL DEMO monitor http://127.0.0.1:{server.server_port}; no production route',flush=True)
    journal=None;b=None;runtime=None;failure=None
    try:
        announced=False
        while not stopped.is_set():
            try:
                creds=Credentials.load()
                http=session if session is not None else CapitalHTTP(creds,orders_enabled=False)
                if http.credentials!=creds or http.orders_enabled:raise CapitalError('unsafe_monitor_session')
                if not http.verified:account=http.login()
                else:
                    current=http.request('GET','/session')
                    matches=[a for a in http.request('GET','/accounts').get('accounts',[]) if a.get('accountId')==creds.account]
                    if current.get('accountId')!=creds.account or len(matches)!=1:raise CapitalError('account_verification_failed')
                    account=matches[0]
                cfg=CapitalConfig(creds.account,mode=args.mode,currency=account['currency'])
                folder=ROOT/'data/capital-v6'/(args.mode+('-'+cfg.currency if cfg.currency!='USD' else ''))
                folder.mkdir(parents=True,exist_ok=True);server.folder=folder
                journal=CapitalJournal(folder/'state.sqlite',cfg)
                b=CapitalBroker(http,journal,cfg)
                b.state['account_currency']=cfg.currency
                b.state['risk_limits']={'daily_loss':cfg.daily_max_loss,'drawdown':cfg.max_drawdown,'currency':cfg.currency,'native_stop_budget':cfg.stop_amount}
                b.state['strict_news_certified']=False
                break
            except CapitalError as error:
                failure=error.code
                view.publish(status(error=failure,mode=args.mode));atomic_json(folder/'health.json',view.read())
                if not announced:
                    print('BLOCKED: '+failure+'; configure with ./run-capital-demo.sh setup',flush=True)
                    announced=True
                if error.status in (401,403) or error.code=='authentication_retry_blocked':
                    while not stopped.wait(.5):pass
                stopped.wait(2)
        if stopped.is_set():return
        # V6.3 deliberately never opens a WebSocket or a technical entry. Keep
        # the previous receiver implementation dormant for evidence continuity.
        runtime=DemoRuntime(b,strategy=args.strategy)
        native_observer(runtime,view,commands,stopped,folder,args.mode)
        return
        reconnects=0
        while not stopped.is_set():
            try:
                if not http.verified:http.login()
                b.reconcile();b.discover()
                # Retain streamed bar state on reconnect but require20fresh quotes.
                if runtime is None:runtime=DemoRuntime(b,strategy=args.strategy)
                from websockets.sync.client import connect
                # Sync client rejects HTTP redirects (no alternate-origin token path).
                with connect(STREAM,proxy=None,open_timeout=12,close_timeout=5,max_size=65536,max_queue=16,ping_interval=20) as ws, StreamInbox(ws) as inbox:
                    metrics=runtime.metrics;last_publish=0;session_generation=http.renewals
                    b.state['stream_connections']=b.state.get('stream_connections',0)+1
                    journal.save('capital_stream_connected',{'connections':b.state['stream_connections']})
                    ws.send(http.stream_message('marketData.subscribe',list(b.instruments)))
                    subscribed=False;last_ping=time.monotonic();stream_opened=last_ping;last_ack=last_ping;last_rest=last_ping;last_snapshot=last_ping;last_metadata=last_ping
                    while not stopped.is_set():
                        now=time.monotonic()
                        if now-last_ping>=30:ws.send(http.stream_message('ping'));last_ping=now
                        if now-last_ack>90:raise CapitalError('websocket_heartbeat_timeout')
                        if now-last_rest>=60:http.request('GET','/ping');last_rest=now
                        if now-last_metadata>=60:
                            epics=set(b.instruments);b.discover();last_metadata=now
                            if set(b.instruments)!=epics:raise CapitalError('instrument_set_changed')
                        if now-last_snapshot>=10:
                            operation_started=time.monotonic_ns()
                            b.reconcile();last_snapshot=now
                            metrics.add('reconciliation_ms',(time.monotonic_ns()-operation_started)/1e6)
                            if b.state['halt'] in ('daily_max_loss','max_drawdown'):b.flatten()
                        if http.renewals!=session_generation:raise CapitalError('session_renewed_reconnect')
                        try:raw,received_at,received_mono=inbox.recv(timeout=.25)
                        except TimeoutError:raw=None
                        if raw:
                            processing_started=time.monotonic_ns()
                            metrics.add('local_queue_ms',(processing_started-received_mono)/1e6)
                            msg=json.loads(raw)
                            if msg.get('status')!='OK':raise CapitalError('websocket_message_rejected')
                            if msg.get('destination')=='marketData.subscribe':
                                sub=msg.get('payload',{}).get('subscriptions',{})
                                if any(sub.get(e)!='PROCESSED' for e in b.instruments):raise CapitalError('subscription_not_confirmed')
                                subscribed=True;runtime.connected=True
                            elif msg.get('destination')=='ping':
                                last_ack=now;b.state['heartbeat_acknowledgements']=b.state.get('heartbeat_acknowledgements',0)+1
                                journal.save('capital_stream_heartbeat')
                            elif msg.get('destination')=='quote' and subscribed:
                                stamp=msg.get('payload',{}).get('timestamp')
                                if type(stamp) is int:metrics.add('source_age_ms',received_at.timestamp()*1000-stamp)
                                try:
                                    runtime.on_quote(msg['payload'],received_at=received_at)
                                    if runtime.fresh_quotes>=20:reconnects=0
                                except ValueError:
                                    b.ready=False;journal.save('capital_bad_quote');runtime.fresh_quotes=0
                            metrics.add('message_processing_ms',(time.monotonic_ns()-processing_started)/1e6)
                        while not commands.empty():
                            action=commands.get_nowait()
                            if action=='pause':runtime.paused=True
                            elif action=='resume':runtime.paused=False
                            elif action=='kill':b.flatten();runtime.paused=True
                        # Re-evaluate freshness even when no messages arrive.
                        try:runtime.watchdog()
                        except CapitalError:pass
                        runtime.require_fresh_stream(time.monotonic()-stream_opened)
                        if args.technical_test and runtime.fresh_quotes>=20 and not b.state['technical_roundtrip_verified']:
                            args.technical_test=False  # One invocation even when preflight/order fails.
                            runtime.technical_test(next(iter(b.instruments)))
                        now_ms=datetime.now(UTC).timestamp()*1000
                        b.state['quote_freshness']={epic:0<=now_ms-b.state['quotes'].get(epic,{}).get('timestamp_ms',0)<=5000 for epic in runtime.sources}
                        b.state['data_fresh']=all(b.state['quote_freshness'].values())
                        b.state['continuous_strategy_orders_enabled']=False
                        b.state['feed_metrics']=metrics.snapshot()
                        connection=('SUBSCRIBED' if b.state['data_fresh'] else 'SUBSCRIBED_STALE') if subscribed else 'SUBSCRIBING'
                        if now-last_publish>=1:
                            value=status(b.state,authenticated=http.verified,connection=connection,mode=args.mode)
                            view.publish(value);atomic_json(folder/'health.json',value);last_publish=now
            except Exception as error:
                # Never log exception text from transport libraries (URLs/tokens).
                if runtime:runtime.disconnect()
                if isinstance(error,CapitalError) and (error.status in (401,403) or error.code=='authentication_retry_blocked'):
                    view.publish(status(b.state,error='authentication_rejected_manual_action_required',mode=args.mode))
                    atomic_json(folder/'health.json',view.read())
                    journal.save('capital_authentication_stopped',error.diagnostic())
                    print(json.dumps(error.diagnostic()),flush=True)
                    while not stopped.wait(.5):pass
                    break
                reconnects+=1;code=error.code if isinstance(error,CapitalError) else type(error).__name__
                if code=='stale_stream_reconnect':reconnects=5  # Quarantine delayed data; REST observations only.
                view.publish(stream_failure_status(b,code,args.mode))
                atomic_json(folder/'health.json',view.read());journal.save('capital_connection_error',{'type':code})
                if reconnects>=5:
                    print('WEBSOCKET_BLOCKED: '+code,flush=True)
                    # Quotes only: a bounded WS failure must never silently
                    # enable stale trading or discard the usable REST feed.
                    if runtime is not None and http.verified:
                        last_reconcile=0
                        while not stopped.is_set():
                            try:
                                runtime.observe_rest()
                                if time.monotonic()-last_reconcile>=10:
                                    b.reconcile();last_reconcile=time.monotonic()
                                while not commands.empty():
                                    action=commands.get_nowait()
                                    if action=='kill':b.flatten();runtime.paused=True
                                    elif action=='pause':runtime.paused=True
                                    elif action=='resume':runtime.paused=False
                                value=status(b.state,authenticated=http.verified,
                                    connection='REST_OBSERVATION_WS_BLOCKED' if b.state['data_fresh'] else 'REST_STALE_WS_BLOCKED',mode=args.mode)
                                view.publish(value);atomic_json(folder/'health.json',value)
                            except (CapitalError,ValueError) as failure:
                                reason=failure.code if isinstance(failure,CapitalError) else 'invalid_rest_quote'
                                b.ready=False;b.state['data_fresh']=False
                                view.publish(status(b.state,error=reason,authenticated=http.verified,connection='DEGRADED_BLOCKED',mode=args.mode))
                                atomic_json(folder/'health.json',view.read())
                                if isinstance(failure,CapitalError) and failure.status in (401,403):break
                            stopped.wait(2)
                    while not stopped.wait(.5):pass
                stopped.wait(min(2**reconnects,30))
    finally:
        if journal:journal.save('capital_process_stopped');journal.close()
        server.shutdown();server.server_close()


def preflight():
    report={'rest_origin':BASE,'authenticated':False,'orders_sent':0,'real_quotes_received':0,'real_demo_fills':0,'production_routing':False}
    try:
        creds=Credentials.load();http=CapitalHTTP(creds,orders_enabled=False)
        cfg=CapitalConfig(creds.account);folder=ROOT/'data/capital-v6/signals_only'
        j=CapitalJournal(folder/'state.sqlite',cfg)
        try:
            account=http.login();b=CapitalBroker(http,j,cfg);snapshot=b.reconcile();specs=b.discover()
            report.update(authenticated=True,account_id=creds.account,currency=account['currency'],
                positions=len(snapshot['positions']),working_orders=len(snapshot['orders']),
                instruments={e:asdict(s) for e,s in specs.items()},status='AUTHENTICATED_DEMO_READ_ONLY')
        finally:j.close()
    except CapitalError as error:report.update(status='BLOCKED',reason=error.code,**error.diagnostic())
    path=ROOT/'reports/capital-v6/preflight.json'
    atomic_json(path,json.loads(json.dumps(report,default=str)))
    print(json.dumps(report,indent=2,default=str))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('configure','diagnose','setup','preflight','app'))
    parser.add_argument('--mode',choices=('signals_only','technical_test','diagnostic_demo','strict_demo'),default='signals_only')
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--strategy',choices=('orb','sweep_mss'),default='orb')
    parser.add_argument('--technical-test',action='store_true')
    parser.add_argument('--replace-credentials',action='store_true',help='One attempt with explicitly replaced credentials; no automatic retries')
    parser.add_argument('--saved-only',action='store_true',help='Setup using Keychain only; never prompt for missing credentials')
    args=parser.parse_args()
    if args.technical_test and args.mode not in ('diagnostic_demo','technical_test'):parser.error('Technical test requires isolated technical_test mode')
    if args.replace_credentials and args.command not in ('configure','setup'):parser.error('Credential replacement requires configure or setup')
    if args.saved_only and (args.command not in ('configure','setup') or args.replace_credentials):parser.error('Saved-only requires configure/setup without replacement')
    if args.command=='configure':
        try:
            configure_credentials(args.replace_credentials,allow_prompt=not args.saved_only)
            print(json.dumps({'http_status':None,'errorCode':None,'phase':'CREDENTIALS_SAVED_AND_READ_BACK'}))
        except CapitalError as error:
            print(json.dumps({**error.diagnostic(),'phase':credential_failure_phase(error.code)+'.'+error.code}))
            raise SystemExit(1) from None
    elif args.command in ('setup','diagnose'):
        http=setup(args.replace_credentials,allow_prompt=args.command=='setup' and not args.saved_only,
            diagnostic_only=args.command=='diagnose',report_path=ROOT/'reports/capital-credentials/setup-status.json')
        if args.command=='setup':
            args.mode='signals_only';args.technical_test=False
            app(args,session=http)
    elif args.command=='preflight':preflight()
    else:
        if args.technical_test:args.mode='technical_test'
        app(args)


if __name__=='__main__':main()
