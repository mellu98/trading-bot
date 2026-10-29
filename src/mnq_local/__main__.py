"""One-command local application. No broker or AI decision mode exists here."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import signal
import threading
import time

from .dashboard import Dashboard, View
from .replay import ROOT, ReplayOptions, ReplaySession, atomic_json


def verify_frozen():
    import hashlib
    manifest = json.loads((ROOT/'reports/local-v5/prior-evidence-sha256.json').read_text())
    for name, expected in manifest['files'].items():
        path = ROOT/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Previous evidence changed: '+name)
    return len(manifest['files'])


def sandbox_preflight(output):
    from .tasty import TokenProvider, SandboxHTTP, SandboxError, BASE
    result = {'environment': 'TASTYTRADE_SANDBOX_ONLY', 'base_url': BASE, 'orders_sent': 0,
        'authenticated': False, 'market_data': 'NOT_AVAILABLE', 'financial_validation': False,
        'required_environment': ['TASTY_SANDBOX_REFRESH_TOKEN', 'TASTY_SANDBOX_CLIENT_SECRET', 'TASTY_SANDBOX_ACCOUNT']}
    account = os.environ.get('TASTY_SANDBOX_ACCOUNT')
    if not account or not all(os.environ.get(k) for k in result['required_environment']):
        result['status'] = 'BLOCKED_MISSING_SANDBOX_ACCOUNT_AND_PERSONAL_OAUTH_GRANT'
    else:
        try:
            http = SandboxHTTP(TokenProvider.from_env())
            value = http.request('GET', '/customers/me/accounts')
            matches = [a for a in value.get('data', {}).get('items', []) if a.get('account', {}).get('account-number') == account]
            if len(matches) != 1:
                raise SandboxError('Exact authorized sandbox account not returned')
            result.update(status='AUTHENTICATED_ACCOUNT_READ_ONLY', authenticated=True)
        except SandboxError as e:
            result.update(status='BLOCKED_AUTHENTICATION_OR_PERMISSIONS', http_status=e.status)
    atomic_json(output, result)
    print(json.dumps(result, indent=2))


def model_check(output):
    import platform
    import subprocess
    import hashlib
    from mnq_timestral.model import PINS
    # No affirmative legal eligibility is inferred from hardware or a public URL.
    result = {'timestral_enabled_in_trading': False, 'real_inference_performed': False,
        'code_license': 'Apache-2.0', 'weights_license': 'Modified MIT',
        'eligibility': 'UNVERIFIED_COMPANY_OR_EMPLOYER_PRIOR_MONTH_REVENUE',
        'restriction': 'No rights if company/employer consolidated prior-month global revenue exceeds USD20M',
        'status': 'BLOCKED_LICENSE_ELIGIBILITY_NOT_ESTABLISHED', 'machine': platform.machine(),
        'checkpoint_revisions': {name: pin.revision for name, pin in PINS.items()},
        'checkpoint_weights_bytes': {name: pin.weights_bytes for name, pin in PINS.items()},
        'models_downloaded': False, 'financial_predictive_ability': 'NOT_VALIDATED'}
    result['licenses'] = {name: {'revision': pin.revision,
        'sha256': hashlib.sha256((ROOT/f'reports/local-v5/Timestral-{name}-LICENSE.txt').read_bytes()).hexdigest()}
        for name, pin in PINS.items()}
    probe = '''import json,inspect,torch
from mnq_timestral.model import verify_source
from timestral import TimestralForecaster
verify_source()
print(json.dumps(dict(official_source_integrity_verified=True,torch_version=torch.__version__,cpu_threads=torch.get_num_threads(),mps_available=torch.backends.mps.is_available(),cuda_available=torch.cuda.is_available(),loading_api=str(inspect.signature(TimestralForecaster.from_pretrained)),forecast_api=str(inspect.signature(TimestralForecaster.forecast)))))'''
    checked = subprocess.run([str(ROOT/'.venv/bin/python'), '-c', probe], capture_output=True, text=True, timeout=45)
    if checked.returncode == 0:
        result.update(json.loads(checked.stdout))
    else:
        result['official_source_integrity_verified'] = False
    result['ram_bytes'] = int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True))
    result['real_latency_seconds'] = None
    atomic_json(output, result)
    print(json.dumps(result, indent=2))


def app(args):
    options = ReplayOptions(args.session, args.strategy, args.strict_news, args.slippage_ticks, args.fee_per_side,
        args.daily_max_loss, args.max_drawdown, args.max_trades, args.max_consecutive_losses)
    folder = Path(args.run_dir) if args.run_dir else ROOT/'data/local-v5'/f'{args.session}-{args.strategy}'
    session = ReplaySession(folder, options)
    if args.headless:
        try:
            session.run(args.max_steps)
            print(json.dumps(session.report(), indent=2))
        finally:
            session.close()
        return
    view, commands = View(), queue.Queue()
    server = None
    stopped = [False]
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.__setitem__(0, True))
    paused = args.paused
    last_health = 0.
    try:
        server = Dashboard(('127.0.0.1', args.port), view, commands, folder)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        print(f'LOCAL HISTORICAL REPLAY ONLY — dashboard http://127.0.0.1:{server.server_port}', flush=True)
        print('State: '+str(folder.resolve())+'; Ctrl-C checkpoints for exact resume. No broker connection.', flush=True)
        while not stopped[0]:
            while not commands.empty():
                action = commands.get_nowait()
                if action == 'pause':
                    paused = True
                    session.export()
                elif action == 'resume':
                    paused = False
                elif action == 'kill':
                    session.kill()
                    session.export()
                    paused = True
            if not paused and not session.progress['complete']:
                session.step()
                if session.progress['cursor'] % 30 == 0 or session.progress['complete']:
                    session.export()
            phase = 'COMPLETE' if session.progress['complete'] else 'PAUSED' if paused else 'RUNNING'
            view.update(session.report(), session.trades(), session.runtime.state['decisions'], session.progress['equity'], phase)
            if time.monotonic()-last_health >= 1:
                atomic_json(folder/'health.json', {'pid': os.getpid(), 'updated_at': datetime.now(timezone.utc).isoformat(),
                    'phase': phase, 'mode': 'HISTORICAL_REPLAY', 'broker_connected': False,
                    'replay_time': session.now.isoformat(), 'cursor': session.progress['cursor']})
                last_health = time.monotonic()
            time.sleep(max(args.delay, .01) if not paused and not session.progress['complete'] else .2)
    finally:
        session.export()
        atomic_json(folder/'health.json', {'pid': os.getpid(), 'phase': 'STOPPED_CHECKPOINTED',
            'updated_at': datetime.now(timezone.utc).isoformat(), 'broker_connected': False,
            'cursor': session.progress['cursor'], 'mode': 'HISTORICAL_REPLAY'})
        if server:
            server.shutdown()
            server.server_close()
        session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('app', help='Start offline replay and local dashboard; reuses its exact checkpoint')
    run.add_argument('--session', default='2026-10-19')
    run.add_argument('--strategy', choices=['vwap_v1', 'orb_v2', 'sweep_mss_v2'], default='vwap_v1')
    run.add_argument('--run-dir')
    run.add_argument('--port', type=int, default=8765)
    run.add_argument('--delay', type=float, default=.02, help='Wall seconds per observed bar, not forecast time')
    run.add_argument('--paused', action='store_true')
    run.add_argument('--headless', action='store_true')
    run.add_argument('--max-steps', type=int)
    run.add_argument('--strict-news', action='store_true')
    run.add_argument('--slippage-ticks', type=int, default=1)
    run.add_argument('--fee-per-side', type=float, default=.61)
    run.add_argument('--daily-max-loss', type=float, default=200.)
    run.add_argument('--max-drawdown', type=float, default=500.)
    run.add_argument('--max-trades', type=int, default=10)
    run.add_argument('--max-consecutive-losses', type=int, default=3)
    sub.add_parser('verify-frozen')
    tasty = sub.add_parser('sandbox-preflight', help='No registration, no orders; read-only if secrets already configured')
    tasty.add_argument('--output', default=str(ROOT/'reports/local-v5/sandbox-preflight.json'))
    model = sub.add_parser('timestral-check', help='Record legal eligibility blocker; never assume rights or download weights')
    model.add_argument('--output', default=str(ROOT/'reports/local-v5/timestral-status.json'))
    args = parser.parse_args()
    if args.command == 'app':
        if not math.isfinite(args.delay) or args.delay < 0 or (args.max_steps is not None and args.max_steps < 0):
            parser.error('Nonnegative finite replay speed/step bounds required')
        app(args)
    elif args.command == 'sandbox-preflight':
        sandbox_preflight(args.output)
    elif args.command == 'timestral-check':
        model_check(args.output)
    else:
        print(json.dumps({'previous_files_unchanged': verify_frozen()}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, ConnectionError, OSError) as e:
        # Do not print arbitrary external broker exceptions or payloads here.
        if isinstance(e, ConnectionError):
            raise SystemExit('External sandbox unavailable; local application is unaffected') from None
        raise SystemExit(str(e)) from None
