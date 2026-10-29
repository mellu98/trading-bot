"""End-to-end fixtures are SYNTHETIC and stub forecasts are NOT Timestral evidence."""
import csv
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path
import json
import pytest
from conftest import bars, prediction
from mnq_timestral.schema import Request, dumps, loads, UTC
from mnq_timestral.data import validate_dataset, file_hash
from mnq_timestral.evaluation import (DEFAULT_PLAN, register_experiment, compare, group_sessions,
    build_records, run_arm, choose_on_validation, forecast_dataset, load_forecasts, screen_sessions)
from mnq_timestral.model import SOURCE_REVISION


def make_synthetic_research(tmp_path, *, dates=None, holdout=1, only_one_forecast=False, stale=False, flat_after_dip=False):
    data=tmp_path/'synthetic.csv';manifest_file=tmp_path/'synthetic-manifest.json';plan_file=tmp_path/'plan.json'
    all_bars=[];sessions={};active={}
    dates=dates or ['2026-10-19','2026-10-20','2026-10-21','2026-10-22']
    for date in dates:
        sessions[date]={'open':date+'T13:30:00+00:00','close':date+'T14:05:00+00:00',
                        'known_at':date+'T00:00:00+00:00','news_complete':True,'news_blocks':[]}
        active[date]={'MES':'MESZ6','MNQ':'MNQZ6'}
        for symbol in ('MES','MNQ'):
            prices=[6000.]*20+[5990.,5990.,5990.,6000.,6000.,6000.,6000.,6000.,6000.,6000.]
            if flat_after_dip: prices=[6000.]*20+[5990.,5990.]+[6000.]*8
            all_bars.extend(bars(30,symbol=symbol,date=date,prices=prices))
    with open(data,'w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=asdict(all_bars[0]).keys());writer.writeheader()
        for b in all_bars:
            writer.writerow({k:v.isoformat() if isinstance(v,datetime) else v for k,v in asdict(b).items()})
    cost={'commission_per_side':.2,'exchange_per_side':.1,'regulatory_per_side':.05,'spread_ticks':1.,
          'entry_slippage_ticks':1.,'exit_slippage_ticks':1.,'evidence':'SYNTHETIC software test only','attested_verified':True}
    manifest={'source':'SYNTHETIC software test only','license':'test fixture','retrieved_at':'2026-10-25T00:00:00+00:00',
              'audit_reference':'SYNTHETIC software test, no market authenticity','calendar_source':'synthetic early closes',
              'news_source':'synthetic empty events','roll_policy':'synthetic fixed actual symbol','attested_verified':True,
              'sha256':file_hash(data),'timestamp_convention':'bar_start_utc','price_adjustment':'none','interval_seconds':60,
              'sessions':sessions,'active_contracts':active,'costs':{'MES':cost,'MNQ':cost}}
    manifest_file.write_text(dumps(manifest))
    plan=dict(DEFAULT_PLAN,calibration_sessions=1,validation_sessions=1,test_sessions=1,holdout_sessions=holdout,
              thresholds=[0.],holdout_previously_unseen_attestation=True,bootstrap_replicates=1000,cost_stress=[1.,2.])
    plan_file.write_text(dumps(plan))
    registration=tmp_path/'registration.json'
    register_experiment(data,manifest_file,plan_file,registration)
    loaded,manifest=validate_dataset(data,manifest_file)
    groups=group_sessions(loaded);predictions={}
    for session in groups.values():
        for i in range(19,len(session)):
            for model in ('28M','209M'):
                for variant in ('target_only','past_covariates'):
                    req=Request(session[:i+1],session[i].available_at,model,variant)
                    if only_one_forecast and (predictions or model != "28M" or variant != "target_only"): continue
                    p=prediction(req,delta=3,delay=120 if stale else .01)
                    predictions[req.key]=p
    logfile=tmp_path/'synthetic-stub-forecasts.jsonl'
    header={'kind':'official_local_cpu_forecasts','dataset_sha256':file_hash(data),'manifest_sha256':file_hash(manifest_file),
            'source_revision':SOURCE_REVISION,'runtime':{'test_only':True},'generated_at':datetime.now(UTC).isoformat()}
    # Deliberately stubbing the producer boundary in a temporary test directory.
    with open(logfile,'w') as stream:
        stream.write(dumps(header)+'\n')
        for p in predictions.values():
            stream.write(dumps({'prediction':p,'adapter_elapsed_seconds':p.latency_seconds,'requested_at':p.origin,
                                'generated_at':datetime.now(UTC)})+'\n')
    records=build_records(groups,manifest,predictions)
    return data,manifest_file,registration,logfile,records,manifest,plan


@pytest.fixture
def synthetic_research(tmp_path):
    return make_synthetic_research(tmp_path)


def test_complete_abc_pipeline_and_holdout_reuse_guard(synthetic_research):
    data,mf,registration,logfile,records,manifest,plan=synthetic_research
    report=compare(data,mf,logfile,registration)
    assert report['status']=='screening_evaluated'
    assert not report['filter_enabled'] and not report['execution_quality_gate']
    assert len(report['models'])==4
    for result in report['models'].values():
        assert set(result['holdout']['arms'])=={'A','B','C'}
        assert result['holdout_statistical_screen']['status']=='insufficient_model_evidence'
        assert result['holdout']['forecast_metrics']['15']['count']==0
    assert compare(data,mf,logfile,registration)==loads(dumps(report))
    logfile.write_text(logfile.read_text()+'\n')
    with pytest.raises(ValueError): compare(data,mf,logfile,registration)


def test_execution_after_data_and_forecast_availability_and_no_duplicate_candidates(synthetic_research):
    _,_,_,_,records,manifest,plan=synthetic_research
    date='2026-10-20'
    a=run_arm(records,[date],'MES',manifest,plan,'A')
    b=run_arm(records,[date],'MES',manifest,plan,'B')
    assert a[0] and b[0]
    assert a[0][0].entry_at>a[1][0]['origin']
    assert b[0][0].entry_at>b[1][0]['origin']+timedelta(seconds=.01)
    assert len({d['candidate_key'] for d in a[1]})==len(a[1])
    assert [d['candidate_key'] for d in a[1]]==[d['candidate_key'] for d in b[1]]
    for trade in a[0]: assert trade.entry_at.date()==trade.exit_at.date()


def test_changing_test_labels_cannot_change_validation_choice(synthetic_research):
    _,_,_,_,records,manifest,plan=synthetic_research
    before=choose_on_validation(records,['2026-10-20'],'MES','28M',manifest,plan,0.)
    altered=dict(records)
    cash,rows=records[('2026-10-21','MES')]
    changed_rows=[dict(r,targets={h:-1e6 for h in r['targets']}) for r in rows]
    altered[('2026-10-21','MES')]=(cash,changed_rows)
    assert choose_on_validation(altered,['2026-10-20'],'MES','28M',manifest,plan,0.)==before


def test_manifest_hash_costs_roll_and_minute_gaps_fail(synthetic_research,tmp_path):
    data,mf,_,_,_,manifest,_=synthetic_research
    for change in ({'sha256':'0'*64},{'attested_verified':False},{'active_contracts':{}},{'costs':{'MES':manifest['costs']['MES']}}):
        target=tmp_path/'bad.json';target.write_text(dumps(dict(manifest,**change)))
        with pytest.raises((ValueError,KeyError)): validate_dataset(data,target)
    loaded,_=validate_dataset(data,mf)
    groups=group_sessions(loaded[:-1])
    with pytest.raises(ValueError,match='gap'):screen_sessions(groups,manifest)


def test_missing_prediction_rejects_B_but_leaves_A_and_exits(synthetic_research):
    _,_,_,_,records,manifest,plan=synthetic_research
    empty={k:(cash,[dict(row,predictions={key:None for key in row['predictions']}) for row in rows])
           for k,(cash,rows) in records.items()}
    date=['2026-10-20']
    baseline=run_arm(records,date,'MES',manifest,plan,'A')
    without=run_arm(empty,date,'MES',manifest,plan,'A')
    filtered=run_arm(empty,date,'MES',manifest,plan,'B')
    assert baseline==without and baseline[0]
    assert not filtered[0] and any(d['reason']=='missing' for d in filtered[1])


def test_offline_forecast_generator_uses_official_adapter_boundary_and_measured_replay_latency(synthetic_research,tmp_path,monkeypatch):
    data,mf,_,_,_,_,_=synthetic_research
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(set_num_threads=lambda n:None,__version__='SYNTHETIC',
                  get_num_threads=lambda:1,get_num_interop_threads=lambda:1))
    class StubAdapter:
        def __init__(self,name,path):self.name=name
        def predict(self,req):
            assert req.model==self.name
            return replace(prediction(req,delay=0),available_at=datetime.now(UTC),clock='wall')
    monkeypatch.setattr('mnq_timestral.evaluation.OfficialAdapter',StubAdapter)
    output=tmp_path/'generated-stub.jsonl'
    counts=forecast_dataset(data,mf,{'28M':'not-real','209M':'not-real'},output)
    predictions,failures,header=load_forecasts(output,data,mf)
    assert counts['predictions']==352 and not failures
    for p in predictions.values():
        assert p.clock=='replay' and p.available_at.year==2026 and p.available_at.date()==p.origin.date()
        assert p.available_at>p.origin


def test_forecast_log_rejects_tampered_measured_availability(synthetic_research,tmp_path):
    data,mf,_,logfile,_,_,_=synthetic_research
    lines=logfile.read_text().splitlines();row=loads(lines[1]);row['adapter_elapsed_seconds']=30
    lines[1]=dumps(row);bad=tmp_path/'tampered.jsonl';bad.write_text('\n'.join(lines)+'\n')
    with pytest.raises(ValueError,match='readiness'):load_forecasts(bad,data,mf)


def test_consumed_interrupted_holdout_is_not_silently_reopened(synthetic_research):
    data,mf,registration,logfile,_,_,_=synthetic_research
    consumed=Path(str(registration)+'.consumed.json')
    consumed.write_text(dumps({'identity':{'registration_sha256':file_hash(registration),'forecasts_sha256':file_hash(logfile)},
                               'state':'consumed_before_evaluation'}))
    with pytest.raises(ValueError,match='consumed'):compare(data,mf,logfile,registration)


def test_registration_plan_tampering_rejected(synthetic_research):
    data,mf,registration,logfile,_,_,_=synthetic_research
    record=loads(registration.read_text());record['plan']['thresholds']=[10.]
    registration.write_text(dumps(record))
    with pytest.raises(ValueError,match='plan changed'):compare(data,mf,logfile,registration)


def test_audit_f1_full_compare_cannot_confirm_absent_model(tmp_path):
    dates=[(datetime(2026,9,1)+timedelta(days=i)).date().isoformat() for i in range(33)]
    data,mf,registration,logfile,_,_,_=make_synthetic_research(
        tmp_path,dates=dates,holdout=30,only_one_forecast=True,flat_after_dip=True)
    result=compare(data,mf,logfile,registration)['models']['MES/209M']
    holdout=result['holdout'];screen=result['holdout_statistical_screen']
    assert holdout['arms']['A']['trades']==30 and holdout['arms']['A']['net']<0
    assert holdout['arms']['B']['trades']==0
    assert holdout['forecast_metrics']['1']['count']==0
    assert screen['status']=='insufficient_model_evidence' and not screen['research_improvement']
    assert holdout['cash_only_reference']['not_model_value'] is True
    assert holdout['model_evidence']['usable_forecasts']==0


def test_audit_f1_all_stale_forecasts_are_not_model_evidence(tmp_path):
    data,mf,registration,logfile,_,_,_=make_synthetic_research(tmp_path,stale=True)
    report=compare(data,mf,logfile,registration)
    for result in report['models'].values():
        assert result['holdout']['forecast_metrics']['1']['count']>0
        assert result['holdout']['model_evidence']['usable_forecasts']==0
        assert result['holdout_statistical_screen']['status']=='insufficient_model_evidence'
        assert not result['holdout_statistical_screen']['research_improvement']


def test_audit_f2_horizon_one_has_forecasts_but_no_economic_entries(synthetic_research):
    _,_,_,_,records,manifest,plan=synthetic_research
    result=run_arm(records,['2026-10-20'],'MES',manifest,plan,'B',horizon=1)
    assert not result[0]
    assert any(d['reason']=='target_expired' for d in result[1])
    selection=choose_on_validation(records,['2026-10-20'],'MES','28M',manifest,plan,0.)
    assert selection['horizon']!=1
    assert selection['unavailable_economic_horizons']==[1]


def test_audit_f3_stale_direction_cannot_suppress_next_valid_C_entry(synthetic_research):
    _,_,_,_,records,manifest,plan=synthetic_research
    date='2026-10-20';cash,rows=records[(date,'MES')]
    # The same first LONG is either absent or too late; neither may consume directional state.
    missing_rows=[dict(row,predictions=dict(row['predictions'])) for row in rows]
    stale_rows=[dict(row,predictions=dict(row['predictions'])) for row in rows]
    for key in missing_rows[0]['predictions']:
        missing_rows[0]['predictions'][key]=None
        p=stale_rows[0]['predictions'][key]
        stale_rows[0]['predictions'][key]=replace(p,available_at=p.origin+timedelta(seconds=120),latency_seconds=120)
    missing=dict(records);missing[(date,'MES')]=(cash,missing_rows)
    stale=dict(records);stale[(date,'MES')]=(cash,stale_rows)
    expected=run_arm(missing,[date],'MES',manifest,plan,'C')
    actual=run_arm(stale,[date],'MES',manifest,plan,'C')
    assert expected[0]
    assert actual==expected
