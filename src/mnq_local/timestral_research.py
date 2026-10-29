"""Shared causal controls for a later full120-session exploratory extension.

The actual five-session measured experiment remains in timestral_experiment.
No full120-session model experiment is claimed by this helper module.
"""
from mnq_timestral.schema import Request, LEVELS
from mnq_timestral.strategy import Candidate, Filter
from .timestral_experiment import protocol


def manifest():
    return {**protocol(), 'scope':'120 sessions previously observed; extension not yet executed'}


def request_spec(bars,n,variant):
    req=Request(tuple(bars[:n]),bars[n-1].end,model='28M',variant=variant)
    return {'request_key':req.key,'n':n,'origin':req.origin.isoformat(),'variant':variant}


def filter_side(side,bar,prediction,key):
    if not side:return 0,'no_candidate'
    if prediction is None:return 0,'missing'
    candidate=Candidate(bar.symbol,bar.contract,side,prediction.origin,bar.close,key)
    allowed,reason=Filter(enabled=True,horizon=5,edge=.25,tail_level=.5,ttl=90).evaluate(candidate,prediction,bar.end)
    return side if allowed else 0,reason


def combine_scores(parts):
    result={}
    for horizon in sorted({h for p in parts for h in p},key=int):
        rows=[p[horizon] for p in parts if horizon in p and p[horizon]['count']]
        count=sum(r['count'] for r in rows)
        if not count:
            result[horizon]={'count':0};continue
        weighted=lambda k:sum(r[k]*r['count'] for r in rows)/count
        mae,rw=weighted('mae'),weighted('random_walk_mae')
        calls=sum(r['directional_calls'] for r in rows)
        levels=rows[0]['coverage']
        coverage={q:sum(r['coverage'][q]*r['count'] for r in rows)/count for q in levels}
        result[horizon]={'count':count,'mae':mae,'random_walk_mae':rw,
            'mae_skill_vs_random_walk':1-mae/rw if rw else None,
            'directional_calls':calls,'directional_accuracy':sum((r['directional_accuracy'] or 0)*r['directional_calls'] for r in rows)/calls if calls else None,
            'coverage':coverage,'pinball':{q:sum(r['pinball'][q]*r['count'] for r in rows)/count for q in levels},
            'calibration_error':sum(abs(v-float(q)) for q,v in coverage.items())/len(levels),
            'central80_coverage':weighted('central80_coverage'),'central80_width':weighted('central80_width')}
    return result
