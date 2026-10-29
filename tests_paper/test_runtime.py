from datetime import datetime, timedelta, timezone
from dataclasses import replace
import pytest
from mnq_timestral.schema import Bar
from mnq_paper.core import PaperConfig, ContractSpec, Journal, Runtime
from mnq_paper.mock import MockBroker

NOW=datetime(2026,10,19,14,tzinfo=timezone.utc)
SPEC=ContractSpec('MES','MESZ6',42001581,'20261218')


def make(tmp_path,mode='technical_paper',max_contracts=1):
    config=PaperConfig(account='DU12345',mode=mode,max_contracts=max_contracts)
    broker=MockBroker(config,[SPEC])
    journal=Journal(tmp_path/'state.sqlite',config,[SPEC],lock_root=tmp_path/'locks')
    engine=Runtime(config,[SPEC],journal,broker,clock=lambda:NOW)
    engine.reconcile(broker.snapshot())
    return engine,broker,journal


def candidate(engine):
    engine.last_data=NOW
    return engine.submit_candidate('MES',1,100,NOW,'test-candidate')


@pytest.mark.parametrize('kwargs',[{'account':'U123'},{'account':'DU12345','host':'example.com'},
 {'account':'DU12345','port':7496},{'account':'DU12345','mode':'live'},
 {'account':'DU12345','client_id':0},{'account':'DU12345','max_contracts':0}])
def test_no_live_configuration(kwargs):
    with pytest.raises(ValueError):PaperConfig(**kwargs)


def test_news_blocks_strict_and_technical_is_explicit(tmp_path):
    engine,broker,journal=make(tmp_path,mode='strict_paper')
    assert candidate(engine) is False and not broker.orders
    journal.close()


def test_intent_is_durable_before_network_and_not_duplicated(tmp_path):
    engine,broker,journal=make(tmp_path)
    assert candidate(engine)
    assert len(broker.orders)==3
    assert not candidate(engine)
    assert len(broker.orders)==3
    assert [o['transmit'] for o in broker.orders.values()]==[False,False,True]
    assert engine.state['decisions'][-1]['accepted'] is False
    journal.close()


def test_restart_reconciles_open_native_bracket(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    parent=min(broker.orders);broker.fill(parent,1,100,'fill-entry',NOW)
    engine.reconcile(broker.snapshot());assert engine.state['positions']['MES']['quantity']==1
    journal.close()
    journal=Journal(tmp_path/'state.sqlite',engine.config,[SPEC],lock_root=tmp_path/'locks')
    restarted=Runtime(engine.config,[SPEC],journal,broker,clock=lambda:NOW)
    assert not restarted.ready
    restarted.reconcile(broker.snapshot());assert restarted.ready
    assert not candidate(restarted) and len(broker.orders)==3
    journal.close()


def test_duplicate_executions_do_not_double_position(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    parent=min(broker.orders);event=broker.fill(parent,1,100,'entry-1',NOW)
    engine.on_execution(event);engine.on_execution(event)
    assert engine.state['positions']['MES']['quantity']==1
    assert len(engine.state['executions'])==1
    journal.close()


def test_kill_cancels_then_flattens_once(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    broker.fill(min(broker.orders),1,100,'entry',NOW);engine.reconcile(broker.snapshot())
    engine.stop('kill');engine.reconcile(broker.snapshot());engine.reconcile(broker.snapshot())
    flatten=[o for o in broker.orders.values() if o['role']=='flatten']
    assert len(flatten)==1
    broker.fill(flatten[0]['id'],1,99,'flat',NOW);engine.reconcile(broker.snapshot())
    assert engine.state['positions']['MES']['quantity']==0
    assert not candidate(engine)
    journal.close()


def test_disconnect_and_stale_data_block_entries(tmp_path):
    engine,broker,journal=make(tmp_path)
    engine.last_data=NOW-timedelta(seconds=180)
    assert not engine.submit_candidate('MES',1,100,NOW,'stale')
    engine.disconnected();assert not candidate(engine)
    journal.close()


def test_foreign_position_never_silently_adopted(tmp_path):
    engine,broker,journal=make(tmp_path)
    snap=broker.snapshot();snap['positions']={'MES':1}
    engine.reconcile(snap)
    assert not engine.ready and engine.state['halt']=='portfolio_mismatch'
    assert not broker.orders
    journal.close()


def test_partial_parent_causes_cancel_and_flatten(tmp_path):
    engine,broker,journal=make(tmp_path,max_contracts=2)
    engine.last_data=NOW;assert engine.submit_candidate('MES',1,100,NOW,'partial',quantity=2)
    broker.fill(min(broker.orders),1,100,'partial-1',NOW)
    engine.reconcile(broker.snapshot());engine.reconcile(broker.snapshot())
    assert engine.state['halt']=='partial_fill'
    assert len([o for o in broker.orders.values() if o['role']=='flatten'])==1
    journal.close()


def test_single_writer_and_config_identity(tmp_path):
    engine,broker,journal=make(tmp_path)
    with pytest.raises(RuntimeError):Journal(tmp_path/'other.sqlite',engine.config,[SPEC],lock_root=tmp_path/'locks')
    journal.close()
    with pytest.raises(ValueError):Journal(tmp_path/'state.sqlite',replace(engine.config,mode='strict_paper'),[SPEC],lock_root=tmp_path/'locks')


def test_ambiguous_flatten_send_is_never_retried(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    broker.fill(min(broker.orders),1,100,'entry',NOW);engine.reconcile(broker.snapshot())
    engine.stop('kill');broker.fail_after=broker.submissions+1
    engine.reconcile(broker.snapshot());engine.reconcile(broker.snapshot())
    assert broker.submissions==4  # One uncertain flatten attempt, never another.
    journal.close()


def test_flat_gross_trade_is_net_loss_for_consecutive_limit(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    parent=min(broker.orders);broker.fill(parent,1,100,'entry',NOW)
    child=next(o for o in broker.orders.values() if o['role']=='target')
    broker.fill(child['id'],1,100,'exit',NOW);engine.reconcile(broker.snapshot())
    assert engine.state['consecutive']==1
    journal.close()


def test_execution_wrong_client_is_not_adopted(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    event=broker.fill(min(broker.orders),1,100,'entry',NOW);event['client_id']=999
    engine.on_execution(event)
    assert engine.state['halt']=='foreign_execution'
    journal.close()


def test_crash_after_one_leg_never_resends_parent(tmp_path):
    engine,broker,journal=make(tmp_path);broker.fail_after=2
    assert candidate(engine)
    assert len(broker.orders)==1
    before=broker.submissions;journal.close()
    journal=Journal(tmp_path/'state.sqlite',engine.config,[SPEC],lock_root=tmp_path/'locks')
    recovered=Runtime(engine.config,[SPEC],journal,broker,clock=lambda:NOW)
    recovered.reconcile(broker.snapshot());recovered.reconcile(broker.snapshot())
    assert broker.submissions==before and recovered.state['halt']=='uncertain_submission'
    assert not candidate(recovered)
    journal.close()


def test_child_rejection_cancels_parent_and_freezes(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    stop=next(o for o in broker.orders.values() if o['role']=='stop')
    engine.on_status({'id':stop['id'],'status':'Inactive','filled':0})
    engine.reconcile(broker.snapshot())
    assert engine.state['halt']=='order_rejected'
    assert all(o['status'] in ('Cancelled','Inactive') for o in broker.orders.values())
    journal.close()


def test_missing_bracket_is_not_treated_as_protected(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    broker.fill(min(broker.orders),1,100,'entry',NOW)
    broker.cancel(next(o['id'] for o in broker.orders.values() if o['role']=='stop'))
    engine.reconcile(broker.snapshot());engine.reconcile(broker.snapshot())
    assert engine.state['halt']=='missing_bracket'
    assert len([o for o in broker.orders.values() if o['role']=='flatten'])==1
    journal.close()


def test_daily_and_drawdown_limits_kill_new_openings(tmp_path):
    engine,broker,journal=make(tmp_path);engine.state['date']=NOW.date().isoformat();engine.state['day_gross']=-201
    assert not candidate(engine);engine.watchdog()
    assert engine.state['halt']=='daily_max_loss'
    journal.close()


def test_duplicate_status_cannot_unfill_order(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    parent=min(broker.orders);event=broker.fill(parent,1,100,'entry',NOW)
    engine.on_execution(event);engine.on_status({'id':parent,'status':'Submitted','filled':0})
    assert engine.state['orders'][str(parent)]['status']=='Filled'
    journal.close()


def test_offline_single_symbol_staleness_cannot_hide_behind_other_stream(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    broker.fill(min(broker.orders),1,100,'entry',NOW);engine.reconcile(broker.snapshot())
    engine.last_data=NOW;engine.last_data_by_symbol={'MES':NOW-timedelta(seconds=91),'MNQ':NOW}
    engine.watchdog();assert engine.state['halt']=='stale_data'
    journal.close()


def test_commission_before_execution_is_not_lost(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    engine.on_commission({'exec_id':'entry','commission':2.0,'currency':'USD'})
    event=broker.fill(min(broker.orders),1,100,'entry',NOW);engine.on_execution(event)
    assert engine.state['executions']['entry']['actual_commission']==2.0
    journal.close()


def test_only_transient_flat_halts_reset_on_new_day(tmp_path):
    engine,broker,journal=make(tmp_path);engine.state['halt']='daily_max_loss';engine.state['date']='2026-10-19'
    engine._roll_day(NOW+timedelta(days=1));assert engine.state['halt'] is None
    engine.state['halt']='max_drawdown';engine._roll_day(NOW+timedelta(days=2));assert engine.state['halt']=='max_drawdown'
    journal.close()


def test_future_signal_source_cannot_change_risk_or_strict_gates(tmp_path):
    engine,broker,journal=make(tmp_path,mode='strict_paper')
    source=type('FixtureSource',(),{'identity':'vwap_v1','evaluate':lambda self,*args:(1,{})})()
    replacement=Runtime(engine.config,[SPEC],journal,broker,clock=lambda:NOW,signal_source=source)
    replacement.reconcile(broker.snapshot());assert not candidate(replacement)
    assert not broker.orders
    journal.close()


def test_snapshot_fill_delivery_can_arrive_reversed(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine)
    parent=min(broker.orders);broker.fill(parent,1,100,'entry',NOW)
    child=next(o for o in broker.orders.values() if o['role']=='target')
    broker.fill(child['id'],1,104,'exit',NOW+timedelta(seconds=1))
    snapshot=broker.snapshot();snapshot['executions'].reverse()
    engine.reconcile(snapshot)
    assert engine.state['positions']['MES']['quantity']==0 and engine.state['gross']==20
    journal.close()


def test_explicit_rearm_requires_fresh_flat_paper_truth(tmp_path):
    engine,broker,journal=make(tmp_path);engine.stop('kill');engine.reconcile(broker.snapshot())
    engine.rearm(broker.snapshot());assert engine.state['halt'] is None
    engine.state['halt']='max_drawdown'
    with pytest.raises(ValueError):engine.rearm(broker.snapshot())
    journal.close()


def test_rearm_does_not_accept_unknown_position_or_working_order(tmp_path):
    engine,broker,journal=make(tmp_path);candidate(engine);engine.state['halt']='operator_shutdown'
    with pytest.raises(ValueError):engine.rearm(broker.snapshot())
    journal.close()
