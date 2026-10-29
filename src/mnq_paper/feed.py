"""Exact Unix-nanosecond5s aggregation; no invented missing bars/volume."""
from datetime import datetime, timedelta, timezone
from mnq_timestral.schema import Bar, NY
from .core import finite, integer


class MinuteFeed:
    def __init__(self,specs):self.specs={s.symbol:s for s in specs};self.buckets={};self.last={}

    def push(self,event,now):
        symbol=event['symbol'];ns=event['start_ns']
        if type(ns) is not int or ns%(5*10**9):raise ValueError('Aligned integerUNIXns5second timestamp required')
        start=datetime.fromtimestamp(ns//10**9,timezone.utc)
        if start+timedelta(seconds=5)>now:raise ValueError('Future/unclosed5second bar')
        local=start.astimezone(NY)
        if not (9,30)<=(local.hour,local.minute)<(16,0):return None
        prior=self.last.get(symbol)
        if prior:
            if ns==prior['start_ns']:
                if prior!=event:raise ValueError('Conflicting duplicate5second event')
                return None
            if ns<prior['start_ns']:raise ValueError('Reordered5second event')
        self.last[symbol]=dict(event)
        minute=ns//(60*10**9)
        bucket=self.buckets.get(symbol)
        if bucket and bucket[0]!=minute:
            self.buckets[symbol]=(minute,[event]);raise ValueError('Incomplete previous minute')
        if not bucket:self.buckets[symbol]=(minute,[])
        values=self.buckets[symbol][1];values.append(event)
        if ns%(60*10**9)!=55*10**9:return None
        self.buckets.pop(symbol)
        if [e['start_ns']%(60*10**9) for e in values]!=[i*5*10**9 for i in range(12)]:raise ValueError('Incomplete minute: no gap filling permitted')
        for e in values:
            for k in ('open','high','low','close','volume'):finite(e[k])
            integer(e['volume'])
            if not 0<e['low']<=min(e['open'],e['close'])<=max(e['open'],e['close'])<=e['high']:raise ValueError('Invalid5second OHLC')
        opened=datetime.fromtimestamp(minute*60,timezone.utc);end=opened+timedelta(minutes=1)
        return Bar(symbol,self.specs[symbol].local_symbol,opened,end,now,values[0]['open'],max(e['high'] for e in values),
          min(e['low'] for e in values),values[-1]['close'],sum(e['volume'] for e in values))
