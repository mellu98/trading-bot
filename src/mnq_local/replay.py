"""Causal CME replay, atomic local recovery, and explicit synthetic execution."""
from contextlib import contextmanager
from copy import deepcopy
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from mnq_timestral.schema import Bar, NY, UTC
from mnq_timestral.evaluation import POINT_VALUE
from mnq_paper.core import ContractSpec, Journal, PaperConfig, Runtime, TERMINAL
from mnq_paper.mock import MockBroker
from mnq_paper.signals import VwapV1Source

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'reports/real-simulation/bars.csv'


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    with temp.open('w') as f:
        json.dump(data, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        import os
        os.fsync(f.fileno())
    temp.replace(path)


@dataclass(frozen=True)
class ReplayOptions:
    session: str = '2026-10-19'
    strategy: str = 'vwap_v1'
    strict: bool = False
    slippage_ticks: int = 1
    fee_per_side: float = .61
    daily_max_loss: float = 200.
    max_drawdown: float = 500.
    max_trades: int = 10
    max_consecutive_losses: int = 3

    def __post_init__(self):
        datetime.strptime(self.session, '%Y-%m-%d')
        if self.strategy not in ('vwap_v1', 'orb_v2', 'sweep_mss_v2'):
            raise ValueError('Only frozen existing strategy families are supported')
        if type(self.strict) is not bool:
            raise ValueError('Boolean strict mode required')
        if type(self.slippage_ticks) is not int or not 0 <= self.slippage_ticks <= 20:
            raise ValueError('Slippage must be 0..20 whole ticks')
        if not math.isfinite(self.fee_per_side) or self.fee_per_side < .61:
            raise ValueError('Fee must respect the unchanged V3 conservative floor of $0.61 per side')
        self.paper_config()

    def paper_config(self):
        # An internal mock namespace, never an IB account credential.
        return PaperConfig('DU000000', mode='strict_paper' if self.strict else 'technical_paper',
            strategy_id=self.strategy, daily_max_loss=self.daily_max_loss,
            max_drawdown=self.max_drawdown, max_trades=self.max_trades,
            max_consecutive_losses=self.max_consecutive_losses)


def load_session(day, source=SOURCE):
    source = Path(source)
    expected = json.loads((ROOT/'reports/real-simulation/data-quality.json').read_text())['bars_csv_sha256']
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if sha != expected:
        raise ValueError('Source checksum differs from the verified CME acquisition')
    bars = []
    with source.open() as f:
        for row in csv.DictReader(f):
            ns = int(row.pop('ts_event_ns'))
            # Validate integer ns BEFORE the datetime-based V3 boundary.
            if ns % (60*10**9):
                raise ValueError('Original timestamp is not an exact UNIX nanosecond minute')
            start = datetime.fromisoformat(row['start'])
            if start.tzinfo is None or start.utcoffset() != timedelta(0):
                raise ValueError('Explicit UTC required before timestamp conversion')
            if (start-datetime(1970, 1, 1, tzinfo=UTC))//timedelta(minutes=1) != ns//(60*10**9):
                raise ValueError('UNIX ns and start disagree')
            for key in ('open', 'high', 'low', 'close', 'volume'):
                row[key] = float(row[key])
            bar = Bar.from_dict(row)
            if bar.start.astimezone(NY).date().isoformat() == day:
                bars.append(bar)
    if len(bars) != 780:
        raise ValueError('A complete owned cash session of 390 bars per micro is required')
    if bars != sorted(bars, key=lambda b: (b.available_at, b.symbol)):
        raise ValueError('Reordered input is refused, never silently sorted')
    for symbol in ('MES', 'MNQ'):
        group = [b for b in bars if b.symbol == symbol]
        if len(group) != 390 or len({b.contract for b in group}) != 1:
            raise ValueError('Duplicate, incomplete or mixed contract session')
        anchor = datetime.fromisoformat(day).replace(hour=9, minute=30, tzinfo=NY)
        if any(b.start != anchor+timedelta(minutes=i) or b.available_at != b.end for i, b in enumerate(group)):
            raise ValueError('Gap, delayed availability or wrong cash-session timezone')
    return bars, {'dataset': 'GLBX.MDP3', 'schema': 'ohlcv-1m', 'source_sha256': sha,
        'session': day, 'bars': len(bars), 'timezone': 'America/New_York',
        'availability_assumption': 'interval end; historical feed latency not measured',
        'contract_selection': 'explicit acquired MNQZ6/MESZ6 for October; no volume-based future mapping',
        'gap_count': 0, 'duplicates': 0}


class FrozenSource:
    def __init__(self, name):
        self.identity = name

    def evaluate(self, bars, now, state):
        # Rebuild only the observed prefix using the exact frozen V2 definition.
        from mnq_sim.strategies import PriceStrategy, StrategyConfig
        strategy = PriceStrategy(StrategyConfig('orb' if self.identity == 'orb_v2' else 'sweep_mss'))
        side = 0
        for bar in bars:
            if bar.available_at > now:
                raise ValueError('Future signal context')
            side = strategy.on_bar(bar)
        return side, {'audit': strategy.audit}


class AtomicJournal(Journal):
    """Same V3 journal and owner; local-only side effects commit once per bar."""
    def __init__(self, *args, **kwargs):
        self.pending = None
        super().__init__(*args, **kwargs)

    def save(self, kind, body=None):
        if self.pending is not None:
            self.pending.append((kind, body or {}))
        else:
            super().save(kind, body)

    @contextmanager
    def bar_transaction(self):
        if self.pending is not None:
            raise RuntimeError('Nested replay transaction')
        before = deepcopy(self.state)
        self.pending = []
        try:
            yield
            encoded = json.dumps(self.state, sort_keys=True, allow_nan=False)
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO snapshot VALUES(1,?)', (encoded,))
                self.db.executemany('INSERT INTO journal(kind,body) VALUES(?,?)',
                    [(kind, json.dumps(body, sort_keys=True, allow_nan=False)) for kind, body in self.pending])
        except BaseException:
            self.state.clear()
            self.state.update(before)
            raise
        finally:
            self.pending = None


class ReplayBroker(MockBroker):
    kind = 'LOCAL_SYNTHETIC_EXECUTION_NOT_BROKER_PAPER'

    def __init__(self, config, specs, owner, clock, options):
        super().__init__(config, specs)
        self.owner, self.clock, self.options = owner, clock, options
        self.restore()

    def restore(self):
        value = self.owner.state['local_replay'].get('broker', {})
        self.orders = {int(k): v for k, v in deepcopy(value.get('orders', {})).items()}
        self.executions = deepcopy(value.get('executions', []))
        self.positions = deepcopy(value.get('positions', {}))
        self.ambiguities = deepcopy(value.get('ambiguities', []))

    def save(self):
        self.owner.state['local_replay']['broker'] = deepcopy({'orders': self.orders,
            'executions': self.executions, 'positions': self.positions, 'ambiguities': self.ambiguities})

    def submit(self, orders):
        stamped = [{**o, 'submitted_at': self.clock().isoformat()} for o in orders]
        super().submit(stamped)
        # The core's order identity is unchanged; the extra field is local audit only.
        for o in stamped:
            self.owner.state['orders'][str(o['id'])]['submitted_at'] = o['submitted_at']

    def snapshot(self):
        result = super().snapshot()
        result['commissions'] = [{'exec_id': e['exec_id'], 'commission': self.options.fee_per_side*e['quantity'],
            'currency': 'USD'} for e in self.executions]
        return result

    def liquidation_cost_per_contract(self, symbol):
        # Quotes/marks already contain any bid/ask component. This is only
        # the still-unpaid closing fee and configured adverse slippage.
        return self.options.fee_per_side+self.options.slippage_ticks*.25*POINT_VALUE[symbol]

    def match(self, bar):
        slip = self.options.slippage_ticks*.25
        new_entries = set()
        for order in list(self.orders.values()):
            if order['symbol'] != bar.symbol or order['status'] in TERMINAL:
                continue
            if datetime.fromisoformat(order['submitted_at']) > bar.start:
                continue
            side = order['side']
            if order['role'] == 'flatten':
                self.fill(order['id'], order['quantity']-order['filled'], bar.open+side*slip,
                    f'replay-{order["id"]}', bar.start)
            elif order['role'] == 'entry':
                expiry = datetime.strptime(order['good_till'], '%Y%m%d %H:%M:%S UTC').replace(tzinfo=UTC)
                if bar.start >= expiry:
                    self.cancel(order['id'])
                    for child in self.orders.values():
                        if child['parent_id'] == order['id']:
                            self.cancel(child['id'])
                    continue
                price = bar.open+side*slip
                open_fill = side*(price-order['limit']) <= 0
                touched = bar.low <= order['limit'] if side == 1 else bar.high >= order['limit']
                if open_fill or touched:
                    if not open_fill:
                        price = order['limit']
                        new_entries.add(order['id'])
                        self.ambiguities.append({'at': bar.end.isoformat(), 'order_id': order['id'],
                            'reason': 'intrabar_limit_entry_sequence_unknown'})
                    self.fill(order['id'], order['quantity']-order['filled'], price,
                        f'replay-{order["id"]}', bar.start if open_fill else bar.end)
        for parent in list(self.orders.values()):
            if parent['symbol'] != bar.symbol or parent['role'] != 'entry' or parent['status'] != 'Filled':
                continue
            children = [o for o in self.orders.values() if o['parent_id'] == parent['id'] and o['status'] not in TERMINAL]
            stop = next((o for o in children if o['role'] == 'stop'), None)
            target = next((o for o in children if o['role'] == 'target'), None)
            if not stop or not target:
                continue
            side = parent['side']
            hit_stop = bar.low <= stop['stop'] if side == 1 else bar.high >= stop['stop']
            touched_target = bar.high >= target['limit'] if side == 1 else bar.low <= target['limit']
            # A target limit needs a conservative one-slippage-tick penetration.
            hit_target = bar.high >= target['limit']+slip if side == 1 else bar.low <= target['limit']-slip
            if hit_stop and touched_target:
                self.ambiguities.append({'at': bar.end.isoformat(), 'order_id': parent['id'],
                    'reason': 'stop_and_target_same_bar_stop_first'})
            if hit_stop:
                price = (min(bar.open, stop['stop']) if side == 1 else max(bar.open, stop['stop']))-side*slip
                self.fill(stop['id'], stop['quantity'], price, f'replay-{stop["id"]}', bar.end)
            elif hit_target and parent['id'] not in new_entries:
                self.fill(target['id'], target['quantity'], target['limit'], f'replay-{target["id"]}', bar.end)
        self.save()


class ReplaySession:
    def __init__(self, folder, options=ReplayOptions()):
        self.folder, self.options = Path(folder), options
        self.bars, self.proof = load_session(options.session)
        self.specs = [ContractSpec(s, next(b.contract for b in self.bars if b.symbol == s), i, '20261218')
            for i, s in enumerate(('MES', 'MNQ'), 1)]
        self.now = self.bars[0].start
        self.journal = AtomicJournal(self.folder/'state.sqlite', options.paper_config(), self.specs,
            lock_root=self.folder/'locks')
        meta = {'options': asdict(options), 'source': self.proof}
        previous = self.journal.state.get('local_replay')
        if previous and previous['identity'] != meta:
            self.journal.close()
            raise ValueError('Replay source, strategy or cost configuration changed; use a new run directory')
        self.journal.state.setdefault('local_replay', {'identity': meta, 'cursor': 0, 'equity': [], 'broker': {}, 'complete': False})
        self.progress = self.journal.state['local_replay']
        if self.progress['cursor']:
            self.now = self.bars[self.progress['cursor']-1].end
        self.broker = ReplayBroker(options.paper_config(), self.specs, self.journal, lambda: self.now, options)
        self.runtime = Runtime(options.paper_config(), self.specs, self.journal, self.broker, clock=lambda: self.now,
            signal_source=VwapV1Source() if options.strategy == 'vwap_v1' else FrozenSource(options.strategy))
        self.runtime.last_data_by_symbol = {s: datetime.fromisoformat(t) for s, t in self.runtime.state['last_bar'].items()}
        self.runtime.last_data = max(self.runtime.last_data_by_symbol.values(), default=None)
        # Recovery reconciles into memory only; crash never advances broker/cursor separately.
        with self.journal.bar_transaction():
            self.runtime.reconcile(self.broker.snapshot())
        self.progress = self.journal.state['local_replay']

    def step(self):
        if self.progress['complete']:
            return False
        index = self.progress['cursor']
        bar = self.bars[index]
        old_now = self.now
        try:
            with self.journal.bar_transaction():
                self.now = bar.end
                self.broker.match(bar)
                self.runtime.reconcile(self.broker.snapshot())
                self.runtime.on_bar(bar)
                self.runtime.reconcile(self.broker.snapshot())
                self.progress['cursor'] = index+1
                unrealized = sum(p['quantity']*(p['mark']-p['average'])*POINT_VALUE[s]
                    for s, p in self.runtime.state['positions'].items())
                self.progress['equity'].append({'at': bar.end.isoformat(), 'realized_net': self.runtime.net(),
                    'equity': self.runtime.net()+unrealized})
                if index+1 == len(self.bars):
                    self._stop_flat('session_flatten')
                    self.progress['complete'] = True
                self.broker.save()
                self.journal.save('replay_cursor', {'index': index+1})
        except BaseException:
            self.now = old_now
            self.progress = self.journal.state['local_replay']
            self.broker.restore()
            self.runtime.ready = False
            self.runtime.last_data_by_symbol = {s: datetime.fromisoformat(t) for s, t in self.runtime.state['last_bar'].items()}
            self.runtime.last_data = max(self.runtime.last_data_by_symbol.values(), default=None)
            raise
        return True

    def _stop_flat(self, reason):
        self.runtime.stop(reason)
        self.runtime.reconcile(self.broker.snapshot())
        # Technical local kill closes at the last OBSERVED close with adverse cost.
        # This is explicitly synthetic, not an invented future market quote.
        for order in list(self.broker.orders.values()):
            if order['role'] == 'flatten' and order['status'] not in TERMINAL:
                mark = self.runtime.state['positions'][order['symbol']]['mark']
                self.broker.fill(order['id'], order['quantity'], mark+order['side']*.25*self.options.slippage_ticks,
                    f'replay-{order["id"]}', self.now)
        self.runtime.reconcile(self.broker.snapshot())
        self.broker.save()
        final_equity = self.runtime.net()
        if self.progress['equity'] and self.progress['equity'][-1]['equity'] != final_equity:
            self.progress['equity'].append({'at': self.now.isoformat(),
                'realized_net': final_equity, 'equity': final_equity})

    def kill(self):
        with self.journal.bar_transaction():
            self._stop_flat('kill')
            self.journal.save('local_kill')

    def run(self, max_steps=None):
        count = 0
        while max_steps is None or count < max_steps:
            if not self.step():
                break
            count += 1
        self.export()

    def trades(self):
        rows = []
        for n, cycle in enumerate(self.runtime.state['closed_cycles'], 1):
            fills = [self.runtime.state['executions'][e] for e in cycle['exec_ids']]
            entry, exit = fills[0], fills[-1]
            gross, fees = sum(e['gross'] for e in fills), sum(e['fee'] for e in fills)
            rows.append({'trade': n, 'symbol': entry['symbol'], 'contract': self.runtime.specs[entry['symbol']].local_symbol,
                'side': 'LONG' if entry['side'] == 1 else 'SHORT', 'entry_at': entry['at'], 'exit_at': exit['at'],
                'entry': entry['price'], 'exit': exit['price'], 'quantity': entry['quantity'],
                'exit_reason': self.runtime.state['orders'][str(exit['order_id'])]['role'],
                'gross': round(gross, 8), 'fees': round(fees, 8), 'net': round(gross-fees, 8),
                'execution': 'LOCAL_OHLC_SYNTHETIC_NOT_BROKER'})
        return rows

    def report(self):
        rows = self.trades()
        peak, dd = 0., 0.
        for event in self.progress['equity']:
            peak = max(peak, event['equity'])
            dd = max(dd, peak-event['equity'])
        fees = sum(e['fee'] for e in self.runtime.state['executions'].values())
        return {'mode': 'HISTORICAL_REPLAY', 'execution': self.broker.kind, 'strategy': self.options.strategy,
            'session': self.options.session, 'strict_news': self.options.strict, 'strategy_approved': False,
            'broker_connected': False, 'future_broker_paper': 'NOT_CONNECTED', 'timestral': 'DISABLED',
            'bars_processed': self.progress['cursor'], 'bars_total': len(self.bars),
            'complete': self.progress['complete'], 'replay_time': self.now.isoformat(),
            'trades': len(rows), 'orders': len(self.runtime.state['orders']),
            'gross': round(self.runtime.state['gross'], 8), 'fees': round(fees, 8),
            'net': round(self.runtime.net(), 8), 'max_drawdown': round(dd, 8),
            'positions': deepcopy(self.runtime.state['positions']), 'halt': self.runtime.state['halt'],
            'working_orders': [deepcopy(o) for o in self.runtime.state['orders'].values() if o['status'] not in TERMINAL],
            'accepted': sum(d['accepted'] for d in self.runtime.state['decisions']),
            'rejected': sum(not d['accepted'] for d in self.runtime.state['decisions']),
            'ambiguities': len(self.broker.ambiguities), 'source': self.proof, 'costs': asdict(self.options),
            'financial_validation': False, 'news_certified': False,
            'runtime_policy': 'Unchanged V3: 20-bar warmup; 09:45–15:30 entries; one-tick bounded entry limit; fixed symbol brackets. V2 plugins use this operational envelope, not the frozen research execution model.',
            'intrabar_policy': 'stop-first; target penetration; intrabar-entry bar target deferred; no path accuracy claim'}

    def export(self):
        atomic_json(self.folder/'summary.json', self.report())
        atomic_json(self.folder/'state-export.json', self.runtime.state)
        atomic_json(self.folder/'ambiguities.json', self.broker.ambiguities)
        for name, rows in [('trades', self.trades()), ('decisions', self.runtime.state['decisions']),
                           ('orders', list(self.runtime.state['orders'].values())),
                           ('executions', list(self.runtime.state['executions'].values())),
                           ('equity', self.progress['equity'])]:
            path = self.folder/(name+'.csv')
            with path.open('w', newline='') as f:
                if rows:
                    writer = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
                    writer.writeheader()
                    writer.writerows(rows)

    def close(self):
        self.journal.close()
