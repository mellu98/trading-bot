"""Capital.com DEMO-only I/O and durable CFD coordinator; never CME sizing.

The V3 Journal and deterministic Risk remain shared. V3 Runtime/ContractSpec are
intentionally NOT passed CFD objects: they enforce DU accounts and CME constants.
No production origin, deposit, account switch, settings mutation or POST retry.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
import base64
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import urllib.error
import urllib.parse

from mnq_paper.core import Journal
from mnq_timestral.strategy import Risk, RiskState

BASE='https://demo-api-capital.backend-capital.com'
# Capital documents one shared quote server. ONLY DEMO-minted verified tokens
# are ever supplied here; no production REST authentication endpoint exists.
STREAM='wss://api-streaming-capital.backend-capital.com/connect'
UTC=timezone.utc
SERVICE='trading-bot.capital-demo'
KEYCHAIN_PREFIX='capital-b64-v1:'

class CapitalError(ConnectionError):
    def __init__(self,code,status=None,error_code=None):
        self.code,self.status,self.error_code=code,status,safe_error_code(error_code)
        super().__init__(code+(f' HTTP{status}' if status else ''))
    def diagnostic(self):
        return {'http_status':self.status,'errorCode':self.error_code}


def safe_error_code(value,secrets=()):
    # No server messages, response bodies, arbitrary strings or credential echoes.
    if not isinstance(value,str) or not re.fullmatch(r'error(?:\.[a-z][a-z0-9_-]{0,48}){1,8}',value):return None
    if any(secret and secret.casefold() in value.casefold() for secret in secrets):return None
    return value


def encode_keychain_value(value):
    # Parser-safe ASCII transport, NOT encryption. macOS Keychain encrypts it.
    return KEYCHAIN_PREFIX+base64.b64encode(value.encode('utf-8')).decode('ascii')


def decode_keychain_value(value):
    if not value.startswith(KEYCHAIN_PREFIX):return value  # Legacy plain records.
    try:return base64.b64decode(value[len(KEYCHAIN_PREFIX):],validate=True).decode('utf-8')
    except (ValueError,UnicodeError):raise CapitalError('malformed_demo_keychain_record') from None


def dec(value):
    if isinstance(value,bool):raise ValueError('Boolean is not a monetary value')
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Finite decimal required')
    return result


def validate_credential_field(name,value):
    if name not in ('api_key','identifier','password','account'):raise ValueError('Unknown credential field')
    if not isinstance(value,str):raise CapitalError('credential_'+name+'_wrong_type')
    if value=='':raise CapitalError('credential_'+name+'_empty')
    try:value.encode('utf-8')
    except UnicodeError:raise CapitalError('credential_'+name+'_invalid_unicode') from None
    if name=='api_key' and (not value.isascii() or any(ord(ch)<=32 or ord(ch)>=127 for ch in value)):
        raise CapitalError('credential_api_key_invalid_character')
    if name=='identifier':
        if value!=value.strip():raise CapitalError('credential_identifier_boundary_whitespace')
        if any(ord(ch)<32 or ord(ch)==127 for ch in value):raise CapitalError('credential_identifier_control_character')
    if name=='account' and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value):raise CapitalError('invalid_demo_account_id')
    # Password is opaque. Preserve all nonempty UTF-8 input without normalization.


@dataclass(frozen=True)
class Credentials:
    api_key:str=field(repr=False)
    identifier:str=field(repr=False)
    password:str=field(repr=False)
    account:str
    def __post_init__(self):
        for name in ('api_key','identifier','password','account'):
            validate_credential_field(name,getattr(self,name))
    @classmethod
    def load(cls):
        staged=subprocess.run(['security','find-generic-password','-a','trading-bot','-s',SERVICE+'.pending','-w'],capture_output=True,text=True)
        if staged.returncode==0:
            # A setup may have stopped after sending an unknown/failed POST.
            # Do not fall back to older credentials or start an app retry loop.
            raise CapitalError('authentication_retry_blocked')
        names=('CAPITAL_DEMO_API_KEY','CAPITAL_DEMO_IDENTIFIER','CAPITAL_DEMO_PASSWORD','CAPITAL_DEMO_ACCOUNT_ID')
        if any(os.environ.get(n) for n in names):return cls(*(os.environ.get(n,'') for n in names))
        p=subprocess.run(['security','find-generic-password','-a','trading-bot','-s',SERVICE,'-w'],capture_output=True,text=True)
        if p.returncode:
            pending=subprocess.run(['security','find-generic-password','-a','trading-bot','-s',SERVICE+'.api-key','-w'],capture_output=True,text=True)
            raise CapitalError('missing_identifier_and_custom_api_password' if pending.returncode==0 else 'missing_demo_credentials_in_keychain')
        try:return cls(**json.loads(decode_keychain_value(p.stdout.removesuffix('\n'))))
        except (ValueError,TypeError,KeyError):raise CapitalError('malformed_demo_keychain_record') from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):return None


def send(method,path,headers,body):
    # URL cannot be supplied by broker responses, environment, callers or config.
    if not path.startswith('/') or '://' in path or '..' in path:raise ValueError('Unsafe path')
    request=urllib.request.Request(BASE+'/api/v1'+path,
        None if body is None else json.dumps(body,allow_nan=False).encode(),headers,method=method)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    try:
        with opener.open(request,timeout=12) as response:
            return response.status,json.load(response),{k.lower():v for k,v in response.headers.items()}
    except urllib.error.HTTPError as error:
        try:
            raw=error.read(16385)
            payload=json.loads(raw) if len(raw)<=16384 else None
            code=safe_error_code(payload.get('errorCode')) if isinstance(payload,dict) else None
        except (OSError,ValueError):code=None
        finally:error.close()
        return error.code,({'errorCode':code} if code else {}),{}
    except (OSError,ValueError):raise CapitalError('transport_unknown') from None


class CapitalHTTP:
    def __init__(self,credentials,*,base=BASE,sender=send,sleep=time.sleep,clock=time.monotonic,orders_enabled=True):
        if base!=BASE:raise ValueError('Only exact HTTPS DEMO origin permitted')
        self.credentials,self.sender,self.sleep,self.clock=credentials,sender,sleep,clock
        self.tokens={};self.verified=False;self.last_request=-1e20;self.last_login=-1e20
        self.orders_enabled=orders_enabled;self.auth_rejected=False
        self.last_authenticated_use=None;self.renewals=0
        self.session_evidence=None
    def request(self,method,path,body=None):
        allowed={'GET':r'/(?:time|ping|session|accounts(?:/preferences)?|positions|workingorders|confirms/[A-Za-z0-9_-]+|prices/(?:US100|US500)\?resolution=(?:MINUTE|MINUTE_5)&max=(?:10|500)|markets(?:/[A-Za-z0-9_.-]+|\?searchTerm=[A-Za-z0-9%+_.-]+)?)',
                 'POST':r'/(?:session|positions|workingorders)',
                 'DELETE':r'/(?:positions|workingorders)/[A-Za-z0-9_-]+'}
        if method not in allowed or not re.fullmatch(allowed[method],path):raise ValueError('Forbidden API route')
        if method in ('POST','DELETE') and path!='/session' and not self.orders_enabled:raise CapitalError('orders_disabled')
        if method=='POST' and path=='/session' and self.auth_rejected:raise CapitalError('authentication_retry_blocked')
        # Renew only a previously verified, known-idle session, never rejected
        # credentials. No speculative retries on arbitrary 401/403 responses.
        if (path not in ('/session','/time') and self.verified and self.last_authenticated_use is not None
            and self.clock()-self.last_authenticated_use>=540):
            if method!='GET':raise CapitalError('idle_session_requires_readonly_refresh')
            self.login();self.renewals+=1
        if path!='/time' and not (method=='POST' and path=='/session') and not self.tokens:raise CapitalError('not_authenticated')
        if method in ('POST','DELETE') and path!='/session' and not self.verified:raise CapitalError('unverified_demo_account')
        delay=max(0,.13-(self.clock()-self.last_request))
        if path=='/session' and method=='POST':delay=max(delay,1.05-(self.clock()-self.last_login))
        self.sleep(max(0,delay));self.last_request=self.clock()
        if path=='/session' and method=='POST':self.last_login=self.last_request
        headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'trading-bot-demo/6'}
        headers.update(self.tokens)
        if method=='POST' and path=='/session':headers['X-CAP-API-KEY']=self.credentials.api_key
        status,result,received=self.sender(method,path,headers,body)
        if method=='POST' and path=='/session':
            lower={k.lower():v for k,v in received.items()}
            self.session_evidence={'http_status':status,'cst_present':bool(lower.get('cst')),
                'security_token_present':bool(lower.get('x-security-token'))}
        if not 200<=status<300:
            if status in (401,403):self.verified=False;self.tokens={};self.auth_rejected=True
            code=safe_error_code(result.get('errorCode'),(self.credentials.api_key,self.credentials.identifier,self.credentials.password)) if isinstance(result,dict) else None
            raise CapitalError('api_request_rejected',status,code)
        if not isinstance(result,dict):raise CapitalError('invalid_api_response')
        if path=='/session' and method=='POST':
            lower={k.lower():v for k,v in received.items()}
            if not lower.get('cst') or not lower.get('x-security-token'):raise CapitalError('missing_session_tokens')
            self.tokens={'CST':lower['cst'],'X-SECURITY-TOKEN':lower['x-security-token']}
        if path!='/time' and self.tokens:self.last_authenticated_use=self.clock()
        return result
    def login(self):
        self.verified=False;self.tokens={}
        value=self.request('POST','/session',{'identifier':self.credentials.identifier,'password':self.credentials.password,'encryptedPassword':False})
        return self.verify_session(value)
    def verify_session(self,value):
        self.verified=False
        if value.get('currentAccountId')!=self.credentials.account or value.get('hasActiveDemoAccounts') is not True:
            raise CapitalError('demo_account_identity_mismatch')
        if value.get('streamingHost','').rstrip('/')!=STREAM.rsplit('/connect',1)[0]:raise CapitalError('unexpected_stream_origin')
        current=self.request('GET','/session')
        accounts=self.request('GET','/accounts').get('accounts',[])
        matches=[a for a in accounts if a.get('accountId')==self.credentials.account]
        if current.get('accountId')!=self.credentials.account or len(matches)!=1 or matches[0].get('status')!='ENABLED' or matches[0].get('accountType')!='CFD':
            raise CapitalError('account_verification_failed')
        if current.get('currency')!=matches[0].get('currency'):raise CapitalError('account_currency_mismatch')
        self.verified=True
        return matches[0]
    def stream_message(self,destination,epics=None):
        if not self.verified:raise CapitalError('unverified_demo_stream')
        if destination not in ('marketData.subscribe','ping'):raise ValueError('Unsupported stream operation')
        msg={'destination':destination,'correlationId':str(time.time_ns()),'cst':self.tokens['CST'],'securityToken':self.tokens['X-SECURITY-TOKEN']}
        if epics is not None:
            if not 1<=len(epics)<=2 or any(not re.fullmatch(r'[A-Za-z0-9_.-]+',e) for e in epics):raise ValueError('Two discovered CFD markets maximum')
            msg['payload']={'epics':epics}
        return json.dumps(msg)


@dataclass(frozen=True)
class CapitalConfig:
    account:str
    mode:str='signals_only'
    daily_max_loss:float=20.
    max_drawdown:float=30.
    max_trades:int=3
    max_consecutive_losses:int=2
    max_size:float=1.
    stop_amount:float=2.
    profit_amount:float=4.
    currency:str='USD'
    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',self.account):raise ValueError('Explicit demo account required')
        if self.mode not in ('signals_only','technical_test','diagnostic_demo','strict_demo'):raise ValueError('No live mode exists')
        self.risk()
        for x in (self.max_size,self.stop_amount,self.profit_amount):
            if dec(x)<=0:raise ValueError('Positive CFD risk limit required')
        if self.max_size>1 or self.stop_amount>2 or self.daily_max_loss>20 or self.max_drawdown>30:raise ValueError('Initial DEMO risk ceiling exceeded')
        if self.currency not in ('USD','EUR','GBP'):raise ValueError('Explicit supported account currency required')
    def risk(self):return Risk(self.daily_max_loss,self.max_drawdown,self.max_trades,self.max_consecutive_losses)


@dataclass(frozen=True)
class CFDInstrument:
    epic:str
    name:str
    currency:str
    min_size:Decimal
    max_size:Decimal
    increment:Decimal
    margin_percent:Decimal
    opening_hours:dict
    raw:dict=field(repr=False)
    @classmethod
    def from_api(cls,data):
        i,r,s=data['instrument'],data['dealingRules'],data['snapshot']
        if i['type']!='INDICES' or s['delayTime']!=0 or not i['streamingPricesAvailable'] or s.get('streamingPricesAvailable',True) is not True:
            raise CapitalError('instrument_not_realtime_index_cfd')
        if i.get('marginFactorUnit')!='PERCENTAGE' or not i.get('openingHours',{}).get('zone'):raise CapitalError('missing_cfd_margin_or_hours')
        values=[dec(r[k]['value']) for k in ('minDealSize','maxDealSize','minSizeIncrement')]
        margin=dec(i['marginFactor'])
        if min(values)<=0 or values[0]>values[1] or not 0<margin<=100:raise CapitalError('invalid_cfd_rules')
        return cls(i['epic'],i['name'],i['currency'],*values,margin,i['openingHours'],data)
    def validate_size(self,size):
        if size<self.min_size or size>self.max_size or (size-self.min_size)%self.increment:raise CapitalError('invalid_cfd_size')


@dataclass(frozen=True)
class Quote:
    epic:str
    bid:Decimal
    ask:Decimal
    timestamp_ms:int
    received_at:datetime
    @property
    def spread(self):return self.ask-self.bid
    @property
    def at(self):return datetime(1970,1,1,tzinfo=UTC)+timedelta(milliseconds=self.timestamp_ms)
    @classmethod
    def parse(cls,payload,received):
        ms=payload['timestamp']
        if type(ms) is not int or ms<=0 or received.tzinfo is None:raise ValueError('Explicit UNIX millisecond quote timestamp required')
        q=cls(payload['epic'],dec(payload['bid']),dec(payload['ofr']),ms,received)
        if payload.get('product')!='CFD' or q.bid<=0 or q.ask<q.bid:raise ValueError('Invalid CFD bid/ask')
        if not timedelta(0)<=received-q.at<=timedelta(seconds=5):raise ValueError('Stale or future quote')
        return q


def rest_snapshot_payload(market):
    """Actual REST observation, never label it as a WebSocket tick."""
    if (market.get('instrumentType')!='INDICES' or market.get('delayTime')!=0
        or market.get('marketStatus')!='TRADEABLE' or not isinstance(market.get('updateTimeUTC'),str)):
        raise CapitalError('unverified_rest_quote_metadata')
    try:
        at=datetime.fromisoformat(market['updateTimeUTC'])
        if at.tzinfo is None:at=at.replace(tzinfo=UTC)  # Explicitly named UTC field.
        at=at.astimezone(UTC);delta=at-datetime(1970,1,1,tzinfo=UTC)
        if at.microsecond%1000:raise ValueError('Sub-millisecond timestamp not representable')
        ms=(delta.days*86400+delta.seconds)*1000+delta.microseconds//1000
        return {'epic':market['epic'],'product':'CFD','bid':market['bid'],'ofr':market['offer'],'timestamp':ms}
    except (ValueError,TypeError,KeyError):raise CapitalError('invalid_rest_quote_timestamp_or_fields') from None


class CapitalJournal(Journal):
    def __init__(self,path,config):
        from .replay import ROOT
        super().__init__(path,config,[],lock_root=ROOT/'data/capital-v6/account-locks')
        self.cap=self.state.setdefault('capital',{'intents':{},'fills':{},'positions':[],'working_orders':[],
            'halt':None,'quotes':{},'decisions':[],'received':0,'signals':0,'day':None,'day_baseline':None,
            'initial_balance':None,'peak':0.,'broker_net':None,'model_net':None,'technical_roundtrip_verified':False})
        self.save('capital_opened')


class CapitalBroker:
    kind='CAPITAL_COM_DEMO_CFD'
    def __init__(self,http,journal,config):
        self.http,self.journal,self.config=http,journal,config
        self.instruments={};self.ready=False
    @property
    def state(self):return self.journal.cap
    def discover(self):
        for query,aliases in [('US Tech 100',{'us tech 100','us tech100','nasdaq 100'}),('US 500',{'us 500','s&p 500'})]:
            markets=self.http.request('GET','/markets?searchTerm='+urllib.parse.quote(query,safe=''))['markets']
            matches=[m for m in markets if m.get('instrumentType')=='INDICES' and m.get('instrumentName','').lower() in aliases]
            if len(matches)!=1:raise CapitalError('instrument_discovery_ambiguous_or_missing')
            epic=matches[0]['epic']
            details=self.http.request('GET','/markets/'+urllib.parse.quote(epic,safe=''))
            details['discovery']=matches[0]
            spec=CFDInstrument.from_api(details)
            if spec.epic!=epic:raise CapitalError('instrument_currency_or_identity_mismatch')
            self.instruments[epic]=spec
        return self.instruments
    def snapshot(self):
        session=self.http.request('GET','/session')
        if session.get('accountId')!=self.config.account:
            self.http.verified=False;raise CapitalError('account_changed')
        accounts=self.http.request('GET','/accounts')['accounts']
        selected=[a for a in accounts if a.get('accountId')==self.config.account]
        if len(selected)!=1 or selected[0]['currency']!=self.config.currency or selected[0]['status']!='ENABLED':raise CapitalError('invalid_current_account')
        return {'account':self.config.account,'account_state':selected[0],
            'positions':self.http.request('GET','/positions')['positions'],
            'orders':self.http.request('GET','/workingorders')['workingOrders']}
    def _closed_outcome(self,parent,cash,*,closed_at=None,confirmation=None,legacy=False):
        """Persist one conservative outcome; independent of JSON key ordering."""
        if parent.get('risk_outcome'):return
        delta=parent.get('observed_broker_cash_delta') if legacy else cash-float(parent.get('cash_before',cash))
        native=(confirmation or {}).get('profit')
        loss=delta is None or delta<=0 or (native is not None and dec(native)<=0)
        at=datetime.fromisoformat(closed_at) if closed_at else datetime.now(UTC)
        if at.tzinfo is None:raise CapitalError('closed_outcome_time_ambiguous')
        parent['risk_outcome']={'day':at.astimezone(UTC).date().isoformat(),'sort_at':at.astimezone(UTC).isoformat(),
            'loss_or_unknown':loss,'cash_delta_account':delta,'source':'CONSERVATIVE_CASH_OR_CONFIRMED_NONPOSITIVE',
            'native_profit':str(native) if native is not None else None,'native_currency':(confirmation or {}).get('profitCurrency')}
        if not legacy:parent['observed_broker_cash_delta']=delta
    def reconcile(self):
        self.ready=False
        snap=self.snapshot();cap=self.state;cap['positions']=snap['positions'];cap['working_orders']=snap['orders']
        balance=snap['account_state']['balance'];cap['balance']=balance
        cash=float(dec(balance['balance']));upl=float(dec(balance['profitLoss']))
        if cap['initial_balance'] is None:cap['initial_balance']=cash
        day=datetime.now(UTC).date().isoformat()
        if cap['day']!=day:
            cap.update(day=day,day_baseline=cash,consecutive_losses=0)
        # Recover confirmed same-day exits missed by the old close-first bug.
        # A UTC-aware close request today, already confirmed today, bounds the
        # outcome to today without interpreting the broker's naive date field.
        for close in list(cap['intents'].values()):
            if close.get('operation')!='close' or close['state']!='CONFIRMED_CLOSED':continue
            requested=datetime.fromisoformat(close['created_at'])
            if requested.tzinfo is None or requested.astimezone(UTC).date().isoformat()!=day:continue
            for parent in cap['intents'].values():
                if parent.get('operation')=='open' and parent.get('deal_id')==close.get('target_id') and parent['state']=='BROKER_POSITION_CLOSED':
                    self._closed_outcome(parent,cash,closed_at=close['created_at'],confirmation=close.get('confirmation'),legacy=True)
        net=cash-cap['initial_balance']+upl;cap['broker_net']=net
        cap['peak']=max(cap['peak'],net);cap['broker_drawdown']=cap['peak']-net
        owned=set()
        for key,intent in cap['intents'].items():
            if intent['state'] in ('REJECTED','CANCELLED','BROKER_POSITION_CLOSED','CONFIRMED_CLOSED','CONFIRMED_CANCELLED'):continue
            if intent['state']=='UNKNOWN':cap['halt']='unknown_mutation_requires_reconciliation';continue
            reference=intent.get('reference')
            if not reference:continue
            try:confirmation=self.http.request('GET','/confirms/'+reference)
            except CapitalError as error:
                if error.status==404:continue
                raise
            if confirmation.get('dealReference')!=reference:cap['halt']='confirmation_identity_mismatch';continue
            if confirmation.get('dealStatus')=='REJECTED':intent['state']='REJECTED';continue
            if confirmation.get('dealStatus')!='ACCEPTED':continue
            # /confirms is not immutable: affectedDeals can disappear after
            # closure. Preserve the original accepted binding as evidence.
            intent.setdefault('confirmation',confirmation)
            intent['last_confirmation']=confirmation
            opened=[d.get('dealId') for d in confirmation.get('affectedDeals',[]) if d.get('status')=='OPENED']
            bound=intent.get('deal_id')
            if intent.get('operation')=='open' and intent.get('kind','market')=='market':
                if len(opened)>1 or (not opened and not bound):
                    cap['halt']='ambiguous_or_multiple_affected_deals';continue
                if opened and bound and opened[0]!=bound:
                    cap['halt']='confirmation_identity_mismatch';continue
            deal=opened[0] if opened else (bound or confirmation.get('dealId'))
            if intent.get('kind')=='limit':
                order_id=intent.setdefault('order_deal_id',confirmation.get('dealId'))
                matched=[p['position']['dealId'] for p in snap['positions'] if p['position'].get('workingOrderId')==order_id]
                if len(matched)>1:cap['halt']='multiple_position_fills';continue
                deal=matched[0] if matched else order_id
                owned.add(order_id)
            intent['deal_id']=deal
            if intent.get('operation') in ('close','cancel'):
                remaining=[p for p in snap['positions'] if p['position']['dealId']==intent['target_id']]
                orders=[o for o in snap['orders'] if o['workingOrderData']['dealId']==intent['target_id']]
                bound=(confirmation.get('dealId')==intent['target_id'] or any(
                    d.get('dealId')==intent['target_id'] for d in confirmation.get('affectedDeals',[])))
                if not remaining and not orders and bound:
                    intent['state']='CONFIRMED_CLOSED' if intent['operation']=='close' else 'CONFIRMED_CANCELLED'
                    for parent in cap['intents'].values():
                        if parent.get('operation')=='open' and parent.get('deal_id')==intent['target_id']:
                            if intent['operation']=='close':self._closed_outcome(parent,cash,closed_at=intent['created_at'],confirmation=confirmation)
                            parent['state']='BROKER_POSITION_CLOSED' if intent['operation']=='close' else 'CANCELLED'
                continue
            if deal:owned.add(deal)
            positions=[p for p in snap['positions'] if p['position']['dealId']==deal]
            if positions:
                p=positions[0]['position'];m=positions[0]['market']
                if m['epic']!=intent['epic'] or p['direction']!=intent['direction'] or dec(p['size'])!=dec(intent['size']):
                    cap['halt']='partial_or_mismatched_position';continue
                if p.get('stopLevel') is None or p.get('profitLevel') is None or not (
                    dec(p['stopLevel'])<dec(p['level'])<dec(p['profitLevel']) if p['direction']=='BUY' else
                    dec(p['profitLevel'])<dec(p['level'])<dec(p['stopLevel'])):
                    cap['halt']='protective_levels_missing';continue
                intent['state']='FILLED';cap['fills'].setdefault(deal,{'deal_id':deal,'epic':m['epic'],
                    'size':str(p['size']),'direction':p['direction'],'level':p['level'],'source':'CONFIRM_AND_BROKER_POSITION'})
            elif intent['state']=='FILLED':
                intent['state']='BROKER_POSITION_CLOSED'
                self._closed_outcome(intent,cash)
            else:
                orders=[o for o in snap['orders'] if o['workingOrderData']['dealId']==deal]
                if orders and intent.get('kind')=='limit':intent['state']='WORKING'
                else:intent['state']='ACCEPTED_AWAITING_POSITION'
        if any(p['position']['dealId'] not in owned for p in snap['positions']) or any(
            o['workingOrderData']['dealId'] not in owned for o in snap['orders']):cap['halt']='foreign_or_residual_position'
        # Narrow migration for the old false positive on this single completed
        # pilot only. Never clear a risk/kill/unknown/foreign-position halt.
        if (cap['halt']=='ambiguous_or_multiple_affected_deals' and cap.get('technical_roundtrip_verified')
            and not snap['positions'] and not snap['orders'] and len([v for v in cap['intents'].values() if v.get('operation')=='open'])==1
            and all(v['state'] in ('BROKER_POSITION_CLOSED','CONFIRMED_CLOSED') for v in cap['intents'].values())):
            cap['halt']=None;self.journal.save('capital_closed_pilot_binding_remediated')
        profits={}
        for intent in cap['intents'].values():
            confirmation=intent.get('confirmation',{})
            if intent.get('operation')=='close' and intent.get('state')=='CONFIRMED_CLOSED' and confirmation.get('profitCurrency'):
                currency=confirmation['profitCurrency'];profits[currency]=str(dec(profits.get(currency,0))+dec(confirmation.get('profit',0)))
        cap['confirmed_trade_profit_by_currency']=profits
        outcomes=sorted((v['risk_outcome'] for v in cap['intents'].values() if v.get('risk_outcome',{}).get('day')==day),key=lambda o:o['sort_at'])
        if outcomes:
            consecutive=0
            for outcome in outcomes:consecutive=consecutive+1 if outcome['loss_or_unknown'] else 0
            cap['consecutive_losses']=consecutive
        cap['daily_opening_attempts']=sum(v.get('operation')=='open' and v.get('created_at','')[:10]==day for v in cap['intents'].values())
        allowed,reason=self.config.risk().allow(RiskState(realized=cash-cap['day_baseline'],unrealized=upl,
            drawdown=cap['broker_drawdown'],trades=cap['daily_opening_attempts'],consecutive_losses=cap.get('consecutive_losses',0)))
        if not allowed:cap['halt']=reason
        pending=any(v['state'] in ('UNKNOWN','ACKNOWLEDGED','ACCEPTED_AWAITING_POSITION') for v in cap['intents'].values())
        self.ready=self.http.verified and cap['halt'] is None and not pending
        self.journal.save('capital_reconciliation',{'positions':len(snap['positions']),'orders':len(snap['orders'])})
        return snap
    def _mutation(self,key,method,path,body,details):
        cap=self.state
        if key in cap['intents']:raise CapitalError('duplicate_intent_blocked')
        if not self.http.verified:raise CapitalError('unverified_demo_account')
        cap['intents'][key]={'state':'UNKNOWN','created_at':datetime.now(UTC).isoformat(),**details}
        self.journal.save('capital_intent_before_network',{'key':key})
        try:response=self.http.request(method,path,body)
        except CapitalError as error:
            if error.status in (400,401,403,404,429):cap['intents'][key]['state']='REJECTED'
            else:cap['halt']='unknown_mutation_requires_reconciliation'
            self.ready=False;self.journal.save('capital_mutation_error',{'key':key,'status':error.status});raise
        reference=response.get('dealReference')
        if not isinstance(reference,str) or not re.fullmatch('[A-Za-z0-9_-]+',reference):
            cap['halt']='unknown_mutation_requires_reconciliation';self.journal.save('capital_missing_reference');raise CapitalError('missing_deal_reference')
        cap['intents'][key].update(state='ACKNOWLEDGED',reference=reference)
        self.ready=False
        self.journal.save('capital_acknowledged_not_filled',{'key':key})
        return reference
    def place(self,key,epic,direction,size,stop_amount,profit_amount,*,technical=False,limit_level=None):
        if key in self.state['intents']:raise CapitalError('duplicate_intent_blocked')
        if not self.ready or self.state['halt'] or self.config.mode in ('signals_only','strict_demo'):raise CapitalError('entries_blocked')
        if self.config.mode=='diagnostic_demo' and not self.state['technical_roundtrip_verified'] and not technical:raise CapitalError('technical_roundtrip_not_verified')
        spec=self.instruments[epic];size=dec(size);spec.validate_size(size)
        if technical and size!=spec.min_size:raise CapitalError('technical_test_requires_minimum_size')
        if any(v['state'] in ('UNKNOWN','ACKNOWLEDGED','ACCEPTED_AWAITING_POSITION') for v in self.state['intents'].values()):raise CapitalError('pending_broker_confirmation')
        if direction not in ('BUY','SELL') or size>dec(self.config.max_size) or spec.currency!=self.config.currency:raise CapitalError('cfd_size_or_currency_limit')
        if not 0<dec(stop_amount)<=dec(self.config.stop_amount) or not 0<dec(profit_amount)<=dec(self.config.profit_amount):raise CapitalError('native_amount_risk_limit')
        if self.state['positions'] or self.state['working_orders']:raise CapitalError('portfolio_not_flat')
        if spec.raw['snapshot'].get('marketStatus')!='TRADEABLE':raise CapitalError('market_not_tradeable')
        if dec(self.state.get('balance',{}).get('available',0))<=0:raise CapitalError('insufficient_demo_available_funds')
        now=datetime.now(UTC);today=now.date().isoformat()
        attempts=[v for v in self.state['intents'].values() if v.get('operation')=='open']
        if sum(v['created_at'][:10]==today for v in attempts)>=self.config.max_trades or sum((now-datetime.fromisoformat(v['created_at'])).total_seconds()<3600 for v in attempts)>=900:
            raise CapitalError('daily_or_hourly_order_cap')
        payload={'epic':epic,'direction':direction,'size':float(size),'stopAmount':float(stop_amount),
            'profitAmount':float(profit_amount),'guaranteedStop':False,'trailingStop':False}
        if limit_level is not None:
            if dec(limit_level)<=0:raise CapitalError('invalid_cfd_limit_level')
            payload.update(level=float(dec(limit_level)),type='LIMIT')
        return self._mutation(key,'POST','/workingorders' if limit_level is not None else '/positions',payload,
            {'operation':'open','kind':'limit' if limit_level is not None else 'market','epic':epic,'direction':direction,'size':str(size),'cash_before':self.state['balance']['balance']})
    def submit(self,orders):
        # Shared broker seam: translate one native bracket, NEVER three broker orders.
        if len(orders)!=3 or {o['role'] for o in orders}!={'entry','stop','target'}:raise CapitalError('complete_native_bracket_required')
        entry=next(o for o in orders if o['role']=='entry')
        if entry['side'] not in (-1,1) or any(o['symbol']!=entry['symbol'] or dec(o['quantity'])!=dec(entry['quantity']) or (o['role']!='entry' and (o.get('parent_id')!=entry['id'] or o['side']!=-entry['side'])) for o in orders):raise CapitalError('native_bracket_identity_mismatch')
        return self.place(str(entry['id']),entry['symbol'],'BUY' if entry['side']==1 else 'SELL',
            dec(entry['quantity']),dec(next(o['amount'] for o in orders if o['role']=='stop')),
            dec(next(o['amount'] for o in orders if o['role']=='target')))
    def technical_plan(self,epic):
        """One micro-sized infrastructure probe; no strategy or CME sizing."""
        if self.config.mode!='technical_test' or not self.http.verified or not self.ready or self.state['halt']:
            raise CapitalError('technical_preconditions_blocked')
        if epic not in ('US100','US500') or self.state['positions'] or self.state['working_orders']:
            raise CapitalError('technical_portfolio_or_instrument_blocked')
        spec=self.instruments[epic];raw=spec.raw;quote=self.state['quotes'].get(epic,{})
        now=datetime.now(UTC)
        age=now.timestamp()*1000-quote.get('timestamp_ms',0)
        if not 0<=age<=5000:raise CapitalError('stale_technical_quote')
        bid,ask=dec(quote['bid']),dec(quote['ask'])
        if ask<bid or bid<=0 or raw['snapshot']['marketStatus']!='TRADEABLE':raise CapitalError('technical_market_not_tradeable')
        lot=dec(raw['instrument']['lotSize'])
        if lot!=1 or spec.currency!='USD':raise CapitalError('unverified_cfd_point_value')
        fx=Decimal(1)
        if self.config.currency!='USD':
            if self.config.currency!='EUR':raise CapitalError('unverified_account_fx')
            values=self.http.request('GET','/markets?searchTerm=EURUSD').get('markets',[])
            matches=[v for v in values if v.get('epic')=='EURUSD']
            if len(matches)!=1:raise CapitalError('unverified_account_fx')
            value=matches[0]
            at=datetime.fromisoformat(value['updateTimeUTC'])
            if at.tzinfo is None:at=at.replace(tzinfo=UTC)  # Documented UTC field.
            if not 0<=(datetime.now(UTC)-at).total_seconds()<=5 or value.get('marketStatus')!='TRADEABLE':raise CapitalError('stale_account_fx')
            fx=dec(value['bid'])
            if fx<=0 or dec(value['offer'])<fx:raise CapitalError('invalid_account_fx')
        tick=dec(raw.get('discovery',{}).get('tickSize',0))
        if tick<=0:raise CapitalError('unverified_cfd_tick_size')
        rules=raw['dealingRules']
        def distance(name):
            rule=rules[name];v=dec(rule['value'])
            if rule['unit']=='PERCENTAGE':v=ask*v/100
            elif rule['unit']!='POINTS':raise CapitalError('unverified_stop_distance_unit')
            if v<=0:raise CapitalError('invalid_stop_distance')
            return v
        minimum=distance('minStopOrProfitDistance');maximum=distance('maxStopOrProfitDistance')
        # A wide, valid regular stop for the minimum size, not a trading signal.
        stop=(minimum*5/tick).to_integral_value(rounding=ROUND_CEILING)*tick
        target=stop*2
        if not minimum<=stop<target<=maximum:raise CapitalError('technical_stop_outside_broker_rules')
        size=spec.min_size;spec.validate_size(size)
        if size>dec(self.config.max_size):raise CapitalError('technical_size_limit')
        available=dec(self.state['balance']['available'])
        risk=stop*size*lot/fx
        buffered=(stop+ask-bid+minimum)*size*lot/fx
        margin=(ask+stop)*size*lot*spec.margin_percent/100/fx
        if available<=0 or buffered>min(dec(self.config.stop_amount),available/1000) or margin>available/10:
            raise CapitalError('technical_virtual_risk_or_margin_limit')
        return {'epic':epic,'size':str(size),'stop_distance':str(stop),'profit_distance':str(target),
            'account_currency':self.config.currency,'quote_currency':spec.currency,'fx_bid':str(fx),
            'nominal_risk_account':str(risk),'buffered_risk_account':str(buffered),'margin_account':str(margin),
            'stop_is_guaranteed':False,'gap_slippage_and_fees_not_certified':True}
    def technical_open(self,epic):
        if self.state.get('technical_attempted') or any(v.get('operation')=='open' for v in self.state['intents'].values()):
            raise CapitalError('technical_attempt_already_recorded')
        plan=self.technical_plan(epic)
        self.state.update(technical_attempted=True,technical_plan=plan)
        self.journal.save('capital_technical_before_network',plan)
        previous=self.http.orders_enabled;self.http.orders_enabled=True
        try:
            return self._mutation('technical-first-forward','POST','/positions',
                {'epic':epic,'direction':'BUY','size':float(dec(plan['size'])),
                 'stopDistance':float(dec(plan['stop_distance'])),'profitDistance':float(dec(plan['profit_distance'])),
                 'guaranteedStop':False,'trailingStop':False},
                {'operation':'open','kind':'market','epic':epic,'direction':'BUY','size':plan['size'],
                 'cash_before':self.state['balance']['balance']})
        finally:self.http.orders_enabled=previous
    def close_position(self,key,deal_id):
        if not any(v.get('deal_id')==deal_id and v.get('operation')=='open' for v in self.state['intents'].values()):raise CapitalError('foreign_position_close_forbidden')
        previous=self.http.orders_enabled;self.http.orders_enabled=True
        try:return self._mutation(key,'DELETE','/positions/'+deal_id,None,{'operation':'close','target_id':deal_id})
        finally:self.http.orders_enabled=previous
    def cancel(self,key,deal_id):
        if not any(v.get('deal_id')==deal_id and v.get('operation')=='open' for v in self.state['intents'].values()):raise CapitalError('foreign_order_cancel_forbidden')
        previous=self.http.orders_enabled;self.http.orders_enabled=True
        try:return self._mutation(key,'DELETE','/workingorders/'+deal_id,None,{'operation':'cancel','target_id':deal_id})
        finally:self.http.orders_enabled=previous
    def flatten(self):
        self.state['halt']='kill';self.ready=False;self.journal.save('capital_kill')
        # Only positively owned IDs; unknown/foreign positions are not guessed.
        for row in self.state['working_orders']:
            deal=row['workingOrderData']['dealId']
            if not any(v.get('operation')=='open' and v.get('deal_id')==deal for v in self.state['intents'].values()):continue
            if not any(v.get('operation')=='cancel' and v.get('target_id')==deal for v in self.state['intents'].values()):self.cancel('kill-cancel-'+deal,deal)
        for row in self.state['positions']:
            deal=row['position']['dealId']
            if not any(v.get('operation')=='open' and v.get('deal_id')==deal for v in self.state['intents'].values()):continue
            if not any(v.get('operation')=='close' and v.get('target_id')==deal for v in self.state['intents'].values()):self.close_position('kill-close-'+deal,deal)
