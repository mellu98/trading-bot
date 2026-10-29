"""Official DBN ingestion only. No credentials, network or order API here."""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
import hashlib,json
from mnq_timestral.schema import Bar,NY
UTC=timezone.utc;EPOCH=datetime(1970,1,1,tzinfo=UTC);MINUTE=60*10**9;SCALE=10**9;TICK=SCALE//4

def ns(value):
    if type(value) is not int or not 0<value<2**63:raise ValueError('explicit_unix_ns_required')
    return value

def exact_utc(value):
    ns(value)
    if value%1000:raise ValueError('non_exact_legacy_datetime_conversion')
    return EPOCH+timedelta(microseconds=value//1000)

def legacy_bar(row):
    # The immutable source envelope retains ALL ns. Only this legacy boundary
    # explicitly rounds availability UP, never making data available earlier.
    available=ns(row['available_ns']);ceil_us=(available+999)//1000
    return Bar(row['symbol'],row['contract'],exact_utc(row['start_ns']),exact_utc(row['end_ns']),
        EPOCH+timedelta(microseconds=ceil_us),*(row[n] for n in ('open','high','low','close','volume')))

def normalize(record,received_ns):
    import databento_dbn as dbn
    ns(received_ns)
    if isinstance(record,dbn.ErrorMsg):raise ValueError('sdk_error_record')
    if isinstance(record,dbn.SystemMsg):return {'kind':'control','received_ns':received_ns}
    if isinstance(record,dbn.SymbolMappingMsg):
        return {'kind':'mapping','publisher_id':int(record.publisher_id),'instrument_id':int(record.instrument_id),
            'contract':record.stype_in_symbol,'stype_in':str(record.stype_in),'stype_out':str(record.stype_out),
            'mapped_contract':record.stype_out_symbol,'start_ns':int(record.start_ts),'end_ns':int(record.end_ts),'received_ns':received_ns}
    if not isinstance(record,(dbn.TradeMsg,dbn.MBP1Msg)):raise ValueError('unsupported_dbn_record')
    row={'kind':'trade' if isinstance(record,dbn.TradeMsg) else 'quote','publisher_id':int(record.publisher_id),
        'instrument_id':int(record.instrument_id),'ts_event_ns':ns(int(record.ts_event)),'ts_recv_ns':ns(int(record.ts_recv)),
        'received_ns':received_ns,'sequence':int(record.sequence),'flags':int(record.flags),'price_nano':int(record.price),
        'size':int(record.size),'action':str(record.action),'side':str(record.side),'depth':int(record.depth)}
    if row['kind']=='quote':
        level=record.levels[0]
        row.update(bid_nano=int(level.bid_px),ask_nano=int(level.ask_px),bid_size=int(level.bid_sz),ask_size=int(level.ask_sz))
    return row


class DatabentoLiveProvider:
    dataset='GLBX.MDP3';schemas=('trades','mbp-1')
    def __init__(self,specs,state,save,*,context_start_ns,stale_ns=5*SCALE):
        if {s.symbol for s in specs}!={'MNQ','MES'}:raise ValueError('both_micro_futures_required')
        ns(context_start_ns)
        if context_start_ns%MINUTE:raise ValueError('minute_context_start_required')
        if type(stale_ns) is not int or not 0<stale_ns<=5*SCALE:raise ValueError('stale_limit_not_relaxable')
        self.specs={s.con_id:s for s in specs};self.save=save;self.stale_ns=stale_ns
        identity={'dataset':self.dataset,'specs':[asdict(s) for s in specs],'context_start_ns':context_start_ns,'stale_ns':stale_ns}
        self.state=state.setdefault('databento_live',{'identity':identity,'mapped':{},'seen':{},'watermarks':{},'quotes':{},
            'open_bars':{},'closed_bars':[],'last_closed':{},'fault':None,'counts':{},'context_start_ns':context_start_ns})
        if self.state['identity']!=identity:raise ValueError('feed_identity_mismatch')
        self.state.setdefault('seen_order',sorted(self.state['seen'],key=self.state['seen'].get))
    def count(self,key):self.state['counts'][key]=self.state['counts'].get(key,0)+1
    def fault(self,code):
        self.state['fault']=self.state['fault'] or code;self.count('rejected');self.save('db_live_fault',{'code':code})
    def fresh(self,symbol,now_ns):
        q=self.state['quotes'].get(symbol)
        return bool(q and not self.state['fault'] and 0<=now_ns-q['ts_event_ns']<=self.stale_ns and
            0<=now_ns-q['received_ns']<=self.stale_ns)
    def ingest(self,record,*,received_ns,now_ns):
        ns(now_ns);result={'status':'accepted','event':None,'bars':[],'quote_fresh':False}
        try:
            row=normalize(record,received_ns);result['event']=row;kind=row['kind'];self.count('received')
            if kind=='control':self.save('db_live_control',{'received_ns':received_ns});return result
            spec=self.specs.get(row['instrument_id'])
            if spec is None:raise ValueError('unsubscribed_instrument')
            if kind=='mapping':
                # Live service mappings are publisher 0. The output is a raw
                # symbol; instrument identity is in the record HEADER, not output.
                if (row['publisher_id']!=0 or row['contract']!=spec.local_symbol or
                    row['mapped_contract']!=spec.local_symbol or row['stype_in']!='raw_symbol' or row['stype_out']!='raw_symbol'):
                    raise ValueError('symbol_mapping_mismatch')
                undefined=2**64-1
                row['source_start_ns']=row['start_ns'];row['source_end_ns']=row['end_ns']
                expiry=int(datetime.strptime(spec.expiry,'%Y%m%d').replace(tzinfo=UTC).timestamp())*SCALE
                start=row['start_ns'];end=row['end_ns']
                if start!=undefined and not 0<=start<2**63:raise ValueError('symbol_mapping_mismatch')
                if end!=undefined and not 0<end<2**63:raise ValueError('symbol_mapping_mismatch')
                if start!=undefined and end!=undefined and start>=end:raise ValueError('symbol_mapping_mismatch')
                row['start_ns']=max(self.state['context_start_ns'],0 if start==undefined else start)
                row['end_ns']=min(expiry,expiry if end==undefined else end)
                if row['start_ns']>=row['end_ns']:raise ValueError('symbol_mapping_mismatch')
                row['bounds_policy']=('UNDEFINED_SOURCE_BOUNDS_SCOPED_TO_CONTEXT_AND_EXPIRY' if undefined in (start,end)
                    else 'SOURCE_BOUNDS_INTERSECT_CONTEXT_AND_EXPIRY')
                self.state['mapped'][spec.symbol]=row;self.save('db_live_mapping',row);return result
            if row['publisher_id']!=1:raise ValueError('foreign_publisher')
            at=row['ts_event_ns'];mapping=self.state['mapped'].get(spec.symbol)
            if not mapping or not mapping['start_ns']<=at<mapping['end_ns']:raise ValueError('unverified_point_in_time_mapping')
            if row['flags']&12:raise ValueError('bad_source_timestamp_or_book_flag')
            if at>now_ns or row['ts_recv_ns']>received_ns+SCALE:raise ValueError('future_source_timestamp')
            if received_ns>now_ns:raise ValueError('future_receipt_timestamp')
            day=exact_utc(at//MINUTE*MINUTE).astimezone(NY).date()
            if spec.expiry<=day.strftime('%Y%m%d'):raise ValueError('expired_contract')
            key=hashlib.sha256(json.dumps({k:v for k,v in row.items() if k!='received_ns'},sort_keys=True).encode()).hexdigest()
            if key in self.state['seen']:
                self.count('duplicates');result['status']='duplicate';return result
            stream=kind+'|'+spec.symbol;previous=self.state['watermarks'].get(stream,0)
            if at<previous:raise ValueError('out_of_order_source_event')
            if kind=='quote':
                if not 0<row['bid_nano']<=row['ask_nano']<2**63-1:raise ValueError('invalid_bid_ask')
                if any(row[n]%TICK for n in ('bid_nano','ask_nano')):raise ValueError('off_tick_quote')
                if row['bid_size']<=0 or row['ask_size']<=0:raise ValueError('empty_top_of_book')
            else:
                if row['action']!='T' or row['size']<=0:raise ValueError('unsupported_trade_correction_or_size')
                if not 0<row['price_nano']<2**63-1 or row['price_nano']%TICK:raise ValueError('invalid_trade_price')
            self.state['seen'][key]=at
            self.state['seen_order'].append(key)
            while len(self.state['seen_order'])>8192:self.state['seen'].pop(self.state['seen_order'].pop(0),None)
            self.state['watermarks'][stream]=at;row.update(symbol=spec.symbol,contract=spec.local_symbol,event_id=key)
            if kind=='quote':
                self.state['quotes'][spec.symbol]=row;result['quote_fresh']=self.fresh(spec.symbol,now_ns)
                if not result['quote_fresh']:self.count('stale_quotes')
            else:result['bars']=self._trade(row)
            self.count(kind);self.save('db_live_event',row)
        except (ValueError,TypeError,KeyError) as error:
            code=str(error) if str(error) in {'explicit_unix_ns_required','sdk_error_record','unsupported_dbn_record','foreign_publisher',
                'unsubscribed_instrument','symbol_mapping_mismatch','unverified_point_in_time_mapping','bad_source_timestamp_or_book_flag',
                'future_source_timestamp','future_receipt_timestamp','expired_contract','out_of_order_source_event','invalid_bid_ask',
                'off_tick_quote','empty_top_of_book','unsupported_trade_correction_or_size','invalid_trade_price','source_bar_gap'} else 'malformed_dbn_record'
            self.fault(code);result['status']='rejected';result['quote_fresh']=False
            # Only normalized market records, never SDK error text or credentials.
            self.save('db_live_rejected',{'code':code,'received_ns':received_ns,'event':result['event']})
        return result
    def _trade(self,row):
        start=row['ts_event_ns']//MINUTE*MINUTE;at=exact_utc(start).astimezone(NY)
        symbol=row['symbol'];old=self.state['open_bars'].get(symbol);ready=[]
        if old and old['start_ns']!=start:
            old_local=exact_utc(old['start_ns']).astimezone(NY)
            if start!=old['end_ns'] and (old_local.hour,old_local.minute)!=(15,59):self.fault('source_bar_gap')
            old['available_ns']=max(row['received_ns'],old['end_ns']);ready=[dict(old)]
            self.state['closed_bars'].append(dict(old));self.state['closed_bars']=self.state['closed_bars'][-800:]
            self.state['last_closed'][symbol]=old['end_ns'];self.save('db_live_closed_bar',old);old=None
            self.state['open_bars'].pop(symbol,None)
        if not (9,30)<=(at.hour,at.minute)<(16,0):return ready
        price=row['price_nano']/SCALE
        if old is None:
            old={'symbol':symbol,'contract':row['contract'],'start_ns':start,'end_ns':start+MINUTE,'available_ns':None,
                'open':price,'high':price,'low':price,'close':price,'volume':0,'source':'CME_DEDICATED_TRADES','first_event_ns':row['ts_event_ns']}
            self.state['open_bars'][symbol]=old
        old['high']=max(old['high'],price);old['low']=min(old['low'],price);old['close']=price;old['volume']+=row['size']
        return ready
    def historical_bar(self,bar):
        # Explicit offline seam for genuine owned OHLCV; NEVER fabricate ticks.
        start=(bar.start-EPOCH)//timedelta(microseconds=1)*1000;end=start+MINUTE
        if bar.available_at!=bar.end:raise ValueError('historical_latency_not_measured')
        spec=next((s for s in self.specs.values() if s.symbol==bar.symbol),None)
        if not spec or spec.local_symbol!=bar.contract:raise ValueError('historical_contract_mismatch')
        return {'symbol':bar.symbol,'contract':bar.contract,'start_ns':start,'end_ns':end,'available_ns':end,
            **{n:getattr(bar,n) for n in ('open','high','low','close','volume')},'source':'HISTORICAL_OHLCV_NO_LIVE_LATENCY_MEASUREMENT'}


def validate_authorization(doc,specs,seconds,now_ns):
    from decimal import Decimal,InvalidOperation
    ns(now_ns)
    for field in ('license_confirmed','live_entitlement_confirmed','spending_authorized','credential_owner_verified'):
        if doc.get(field) is not True:raise PermissionError(field+'_required')
    key_digest=doc.get('authorized_key_sha256')
    if not isinstance(key_digest,str) or len(key_digest)!=64 or any(c not in '0123456789abcdef' for c in key_digest):
        raise PermissionError('owner_verified_key_binding_required')
    if (doc.get('dataset')!='GLBX.MDP3' or doc.get('schemas')!=['trades','mbp-1'] or
        doc.get('contracts')!=[s.local_symbol for s in specs] or doc.get('purpose')!='READ_ONLY_MARKET_DATA_LOCAL_SIMULATION'):
        raise PermissionError('live_authorization_scope_mismatch')
    if not isinstance(doc.get('license_reference'),str) or not doc['license_reference'] or not isinstance(doc.get('authorization_id'),str) or not doc['authorization_id']:
        raise PermissionError('documented_authorization_reference_required')
    if type(seconds) is not int or type(doc.get('max_seconds')) is not int or not 1<=seconds<=doc['max_seconds']<=600:
        raise PermissionError('bounded_readonly_trial_required')
    if not ns(doc['not_before_ns'])<=now_ns or ns(doc['expires_ns'])<now_ns+seconds*SCALE:
        raise PermissionError('authorization_not_current_for_trial')
    try:
        actual=Decimal(str(doc['confirmed_total_monthly_usd']));cap=Decimal(str(doc['authorized_total_monthly_usd_max']))
    except (InvalidOperation,KeyError):raise PermissionError('confirmed_cost_invalid') from None
    if not actual.is_finite() or not cap.is_finite() or not 0<actual<=cap:raise PermissionError('confirmed_cost_exceeds_authorization')
    if any(s.expiry<=exact_utc(now_ns//1000*1000).strftime('%Y%m%d') for s in specs):raise PermissionError('dated_contract_expired')
    return hashlib.sha256(json.dumps(doc,sort_keys=True,allow_nan=False).encode()).hexdigest()


def connect_sdk(provider,authorization,seconds,now_ns,*,key_loader,factory=None):
    """The first subscribe opens TCP. It is unreachable without an exact grant.

    SDK callbacks only enqueue. Durable event/risk processing stays in the one
    application owner. Reconnect resumes observation, never authorizes orders.
    """
    import queue,threading,time,logging
    specs=tuple(provider.specs.values())
    digest=validate_authorization(authorization,specs,seconds,now_ns)
    used=provider.state.setdefault('used_authorizations',{})
    if authorization['authorization_id'] in used:raise PermissionError('single_trial_authorization_already_consumed')
    key=key_loader()
    if not isinstance(key,str) or not key:raise PermissionError('saved_api_key_unavailable')
    # The grant binds the key verified against the user's own portal account.
    # Never infer ownership from successful Historical API authentication.
    if hashlib.sha256(key.encode()).hexdigest()!=authorization['authorized_key_sha256']:
        raise PermissionError('saved_key_not_bound_to_verified_owner')
    used[authorization['authorization_id']]={'sha256':digest,'at_ns':now_ns}
    provider.save('db_live_authorization_consumed',{'sha256':digest,'at_ns':now_ns,'max_seconds':seconds})
    if factory is None:
        import databento as db
        factory=db.Live
    # Never forward SDK exception strings or raw error records to logs.
    logging.getLogger('databento').setLevel(logging.CRITICAL+1)
    client=factory(key=key,reconnect_policy='reconnect',heartbeat_interval_s=10)
    inbox=queue.Queue(maxsize=4096);failed=threading.Event()
    def put(kind,value):
        try:inbox.put_nowait((kind,value,time.time_ns()))
        except queue.Full:failed.set()
    client.add_callback(lambda record:put('record',record),exception_callback=lambda _:failed.set())
    client.add_reconnect_callback(lambda last,start:put('reconnect',None),exception_callback=lambda _:failed.set())
    try:
        import pandas as pd
        for schema in provider.schemas:
            client.subscribe(dataset=provider.dataset,schema=schema,symbols=[s.local_symbol for s in specs],
                stype_in='raw_symbol',start=pd.Timestamp(provider.state['context_start_ns'],unit='ns',tz='UTC'))
        client.start()
    except BaseException:
        client.terminate();raise RuntimeError('official_sdk_connection_failed_no_auto_retry') from None
    return client,inbox,failed
