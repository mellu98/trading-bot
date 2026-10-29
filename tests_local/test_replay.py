from dataclasses import replace
import json
import sqlite3
import socket

import pytest

from mnq_local.replay import ReplaySession, ReplayOptions, load_session, ROOT


def test_real_session_quality_and_nanosecond_guard(tmp_path):
    bars, proof = load_session('2026-10-19')
    assert len(bars) == 780 and proof['source_sha256']
    assert {b.symbol for b in bars} == {'MNQ', 'MES'}
    assert all(a.end <= b.end for a, b in zip(bars, bars[1:]))
    text = (ROOT/'reports/real-simulation/bars.csv').read_text()
    bad = tmp_path/'bars.csv'
    bad.write_text(text.replace('1792416600000000000', '1792416600000000001', 1))
    with pytest.raises(ValueError):
        load_session('2026-10-19', bad)


def test_replay_deterministic_restart_and_costs(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Offline replay attempted network'))
    a = ReplaySession(tmp_path/'a')
    a.run()
    expected = a.report()
    assert expected['bars_processed'] == 780 and expected['complete']
    assert expected['trades'] > 0 and expected['fees'] > 0
    assert expected['broker_connected'] is False
    a.close()
    b = ReplaySession(tmp_path/'b')
    b.run(max_steps=157)
    before = len(b.runtime.state['executions'])
    b.close()
    b = ReplaySession(tmp_path/'b')
    assert len(b.runtime.state['executions']) == before
    b.run()
    actual = b.report()
    for key in ('trades', 'gross', 'fees', 'net', 'max_drawdown', 'orders', 'ambiguities'):
        assert actual[key] == expected[key]
    b.close()
    with pytest.raises(ValueError):
        ReplaySession(tmp_path/'b', replace(ReplayOptions(), slippage_ticks=2))


def test_step_crash_rolls_back_broker_and_cursor_together(tmp_path):
    s = ReplaySession(tmp_path)
    s.run(max_steps=90)
    before = json.loads(json.dumps(s.runtime.state))
    original = s.runtime.on_bar
    def fail(bar):
        original(bar)
        raise RuntimeError('injected crash')
    s.runtime.on_bar = fail
    with pytest.raises(RuntimeError):
        s.step()
    s.close()
    s = ReplaySession(tmp_path)
    assert s.runtime.state == before
    s.run(max_steps=1)
    assert s.progress['cursor'] == 91
    s.close()


def test_strict_news_gate_and_kill_persist(tmp_path):
    s = ReplaySession(tmp_path/'strict', replace(ReplayOptions(), strict=True))
    s.run()
    assert s.report()['orders'] == 0
    assert any(d['reason'] == 'strict_news_and_strategy_not_certified' for d in s.runtime.state['decisions'])
    s.close()


def test_local_kill_closes_an_actual_open_simulated_position_once(tmp_path):
    s = ReplaySession(tmp_path)
    while not any(p['quantity'] for p in s.runtime.state['positions'].values()):
        assert s.step()
        assert s.progress['cursor'] < 200
    at = s.now
    s.kill()
    assert s.report()['halt'] == 'kill'
    assert not any(p['quantity'] for p in s.runtime.state['positions'].values())
    assert s.progress['equity'][-1]['equity'] == s.runtime.net()
    flat = [e for e in s.runtime.state['executions'].values()
            if s.runtime.state['orders'][str(e['order_id'])]['role'] == 'flatten']
    assert len(flat) == 1 and flat[0]['at'] == at.isoformat()
    count = s.report()['orders']
    s.run()
    assert s.report()['orders'] == count
    s.close()
    s = ReplaySession(tmp_path/'kill')
    s.run(max_steps=100)
    s.kill()
    assert s.report()['halt'] is not None
    assert not any(p['quantity'] for p in s.runtime.state['positions'].values())
    count = len(s.runtime.state['orders'])
    s.close()
    s = ReplaySession(tmp_path/'kill')
    s.run()
    assert len(s.runtime.state['orders']) == count
    s.close()


def test_source_gap_or_changed_contract_refused(tmp_path):
    source = ROOT/'reports/real-simulation/bars.csv'
    bad = tmp_path/'bars.csv'
    lines = source.read_text().splitlines()
    bad.write_text('\n'.join(lines[:40] + lines[41:])+'\n')
    with pytest.raises(ValueError):
        load_session('2026-10-19', bad)


def test_working_protective_prices_are_visible_in_dashboard_report(tmp_path):
    s = ReplaySession(tmp_path)
    while not s.runtime.state['orders']:
        assert s.step()
        assert s.progress['cursor'] < 200
    working = s.report()['working_orders']
    assert {o['role'] for o in working} == {'entry', 'stop', 'target'}
    assert next(o for o in working if o['role'] == 'stop')['stop'] > 0
    assert next(o for o in working if o['role'] == 'target')['limit'] > 0
    s.close()


def test_conservative_collision_and_limit_execution(tmp_path):
    s = ReplaySession(tmp_path)
    b = s.bars[40]
    s.now = b.end
    s.runtime.last_data = b.end
    assert s.runtime.submit_candidate(b.symbol, 1, b.close, b.end, 'fixture')
    parent = next(o for o in s.broker.orders.values() if o['role'] == 'entry')
    at = b.end
    # Marketable open followed by both exits in the same unknown OHLC path.
    collision = replace(b, start=at, end=at.replace(minute=at.minute+1),
                        available_at=at.replace(minute=at.minute+1),
                        open=parent['limit']-.25, close=parent['limit'],
                        high=parent['limit']+40, low=parent['limit']-40)
    s.now = collision.end
    s.broker.match(collision)
    exits = [s.broker.orders[e['order_id']]['role'] for e in s.broker.executions]
    assert exits == ['entry', 'stop']
    assert s.broker.ambiguities
    assert s.broker.executions[0]['price'] <= parent['limit']
    s.close()


def test_exact_target_touch_is_still_intrabar_ambiguity(tmp_path):
    from datetime import timedelta
    s = ReplaySession(tmp_path)
    b = s.bars[40]
    s.now = b.end
    s.runtime.last_data = b.end
    assert s.runtime.submit_candidate(b.symbol, 1, b.close, b.end, 'exact-touch')
    parent = next(o for o in s.broker.orders.values() if o['role'] == 'entry')
    target = next(o for o in s.broker.orders.values() if o['role'] == 'target')
    stop = next(o for o in s.broker.orders.values() if o['role'] == 'stop')
    at = b.end
    bar = replace(b, start=at, end=at+timedelta(minutes=1), available_at=at+timedelta(minutes=1),
                  open=parent['limit']-.25, close=parent['limit'], high=target['limit'], low=stop['stop'])
    s.broker.match(bar)
    assert any(a['reason'] == 'stop_and_target_same_bar_stop_first' for a in s.broker.ambiguities)
    assert s.broker.orders[stop['id']]['status'] == 'Filled'
    s.close()


def test_no_same_bar_signal_fill_or_future_signal_context(tmp_path):
    s = ReplaySession(tmp_path)
    original = s.runtime.signal_source.evaluate
    def checked(bars, now, state):
        assert all(b.available_at <= now for b in bars)
        assert bars[-1].end == now
        return original(bars, now, state)
    s.runtime.signal_source.evaluate = checked
    s.run()
    for e in s.runtime.state['executions'].values():
        order = s.runtime.state['orders'][str(e['order_id'])]
        if order['role'] == 'entry':
            assert e['at'] >= order['submitted_at']
    s.close()


def test_account_lock_and_invalid_costs(tmp_path):
    s = ReplaySession(tmp_path)
    with pytest.raises(RuntimeError):
        ReplaySession(tmp_path)
    s.close()
    for kw in ({'slippage_ticks': -1}, {'fee_per_side': .1}, {'strategy': 'new_strategy'}):
        with pytest.raises(ValueError):
            ReplayOptions(**kw)


@pytest.mark.parametrize('limit,expected', [({'daily_max_loss': 1}, 'daily_max_loss'),
                                         ({'max_drawdown': 1}, 'max_drawdown')])
def test_real_data_risk_drills(tmp_path, limit, expected):
    s = ReplaySession(tmp_path, replace(ReplayOptions(), **limit))
    s.run()
    assert s.report()['halt'] == expected
    assert not any(p['quantity'] for p in s.runtime.state['positions'].values())
    assert any(not d['accepted'] for d in s.runtime.state['decisions'])
    s.close()


@pytest.mark.parametrize('strategy', ['orb_v2', 'sweep_mss_v2'])
def test_existing_v2_signal_seam_is_prefix_only(strategy):
    from mnq_local.replay import FrozenSource
    bars, _ = load_session('2026-10-19')
    group = tuple(b for b in bars if b.symbol == 'MES')
    source = FrozenSource(strategy)
    for n in (20, 30, 60, 90):
        side, state = source.evaluate(group[:n], group[n-1].end, {})
        assert side in (-1, 0, 1)
        assert state['audit']['known_at'] == group[n-1].end.isoformat()
        with pytest.raises(ValueError):
            source.evaluate(group[:n+1], group[n-1].end, {})
