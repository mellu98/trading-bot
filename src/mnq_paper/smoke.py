"""One-intent paper infrastructure acceptance. NOT a financial strategy.

No login/config/Read-Only toggle is automated. An actual authenticated UI proof
and writable API configuration are mandatory. No retries of uncertain entries.
"""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json
import queue
import time
from dataclasses import replace
from .core import ContractSpec,Journal,Runtime
from .ib import IBPaper
from mnq_timestral.schema import NY
from .v4 import PRIVATE,OUT,settings,save


UTC=timezone.utc
KEY='v4-one-technical-entry'


def run(proof_path,state_path=None,seconds=180):
    if not proof_path:raise ValueError('Observed authenticated Paper UI proof required')
    local=datetime.now(UTC).astimezone(NY)
    if not (9,45)<=(local.hour,local.minute)<(15,30):raise ValueError('Technical entry window closed; no state or order created')
    cfg=replace(settings(),mode='technical_paper',max_contracts=1)
    specs=[ContractSpec(**value) for value in json.loads((PRIVATE/'contracts.json').read_text())]
    if {s.symbol for s in specs}!={'MNQ','MES'}:raise ValueError('Official read-only contract discovery required first')
    broker=IBPaper(cfg,specs,operation='paper_orders',session_proof=proof_path)
    journal=Journal(state_path or PRIVATE/'smoke/state.sqlite',cfg,specs)
    if journal.state['orders'] and journal.state.get('technical_scope')!='v4_single_entry':
        journal.close();raise ValueError('Never reuse an operational journal for isolated order testing')
    if sum(o['role']=='entry' for o in journal.state['orders'].values())>1:
        journal.close();raise ValueError('Single-entry acceptance journal invariant violated')
    journal.state['technical_scope']='v4_single_entry';journal.save('technical_scope')
    runtime=Runtime(cfg,specs,journal,broker,kill_path=PRIVATE/'KILL')
    report={'scope':'REAL_IB_PAPER_TECHNICAL_NOT_FINANCIAL','started_at':datetime.now(UTC).isoformat(),
      'paper_mode_confirmed':False,'entry_intents_max':1,'contracts_per_position_max':1,
      'accepted_roles':[],'accepted_order_ids':[],'actual_execution_ids':[],'flat_confirmed':False,
      'partial_fill_test':'NOT_OBSERVED_ONE_INTEGER_CONTRACT_CANNOT_FORCE_PARTIAL',
      'continuous_runtime_certified':False,'strategy_approved':False}
    observed=set();accepted_ids=set();last_beat=0
    try:
        broker.connect();report['paper_mode_confirmed']=True
        snapshot=broker.snapshot()
        if not runtime.state['orders'] and (any(snapshot['positions'].values()) or snapshot['orders']):
            raise ValueError('A new smoke test requires a flat account with no existing orders')
        runtime.reconcile(snapshot)
        if runtime.state['halt']:raise ValueError('Existing safety halt; never reset or replace journal to retry')
        broker.subscribe();deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if time.monotonic()-last_beat>5:broker.heartbeat();last_beat=time.monotonic()
            runtime.watchdog()
            try:event=broker.events.get(timeout=.2)
            except queue.Empty:event=None
            if event:
                if event['type']=='disconnect':runtime.disconnected();raise ConnectionError('Paper disconnected; no automatic entry resend')
                if event['type']=='error':runtime.stop('broker_error_'+str(event['code']))
                if event['type']=='commission':runtime.on_commission(event['value'])
                if event['type']=='status':runtime.on_status(event)
                if event['type']=='five_seconds':
                    at=datetime.fromtimestamp(event['start_ns']//10**9,UTC)+timedelta(seconds=5)
                    runtime.last_data=at;runtime.last_data_by_symbol[event['symbol']]=at
                    position=runtime.state['positions'].get(event['symbol'])
                    if position:position['mark']=event['close']
                    local=at.astimezone(NY)
                    if event['symbol']=='MES' and KEY not in runtime.state['seen_candidates'] and (9,45)<=(local.hour,local.minute)<(15,30):
                        runtime.submit_candidate('MES',1,event['close'],at,KEY,quantity=1)
            snapshot=broker.snapshot();runtime.reconcile(snapshot)
            for order in snapshot['orders']:
                if str(order['id']) in runtime.state['orders'] and order['status'] in ('Submitted','PreSubmitted'):
                    observed.add(order['role']);accepted_ids.add(order['id'])
            for execution in runtime.state['executions'].values():
                observed.add(runtime.state['orders'][str(execution['order_id'])]['role']);accepted_ids.add(execution['order_id'])
            if runtime.state['halt']:break
            if runtime.state['executions'] and not any(p['quantity'] for p in runtime.state['positions'].values()):break
        report['accepted_roles']=sorted(observed);report['accepted_order_ids']=sorted(accepted_ids)
    finally:
        runtime.stop('technical_test_complete')
        deadline=time.monotonic()+30
        while broker.verified and time.monotonic()<deadline:
            try:snapshot=broker.snapshot();runtime.reconcile(snapshot)
            except (ConnectionError,TimeoutError,OSError,ValueError):break
            if snapshot['accounts']==[cfg.account] and not any(snapshot['positions'].values()) and not snapshot['orders']:
                report['flat_confirmed']=True;break
            time.sleep(.2)
        report['actual_execution_ids']=list(runtime.state['executions'])
        report['accepted_roles']=sorted(observed);report['accepted_order_ids']=sorted(accepted_ids)
        report['halt']=runtime.state['halt'];report['finished_at']=datetime.now(UTC).isoformat()
        # This file can only be written after the real adapter path; mocks have
        # their own test artifacts and never write this acceptance receipt.
        save(OUT/'paper-smoke-attempt.json',report)
        broker.close();journal.close()
    return report
