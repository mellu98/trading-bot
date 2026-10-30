"""Command line: ./run-ict.sh <command>  (see src/ict_engine/README.md)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "ict"
OUT = ROOT / "reports" / "ict"


def _load(args):
    if args.source == "binance":
        from . import data_binance
        return data_binance.load(CACHE, args.symbol, "5m")
    if args.source == "capital":
        from . import data_capital
        return data_capital.load(CACHE, args.epic)
    if args.source == "csv":
        from . import data_csv
        if not args.csv:
            raise SystemExit("--csv PATH required with --source csv")
        return data_csv.load(args.csv, symbol=args.symbol, interval_seconds=args.interval_seconds)
    raise SystemExit("unknown source")


def _default_profile(args):
    if args.profile:
        return args.profile
    if args.source == "binance":
        return "binance-btcusdt-spot"
    if args.source == "capital":
        return {"US100": "capital-us100-cfd", "US500": "capital-us500-cfd", "BTCUSD": "capital-btcusd-cfd"}[args.epic]
    return {"MNQ": "cme-mnq", "MES": "cme-mes"}.get(args.symbol or "", "synthetic")


def cmd_run(args):
    from . import protocol, report
    from .news import load_calendar
    bars, meta = _load(args)
    profile = _default_profile(args)
    overrides = config.parse_overrides(args.set)
    events = load_calendar(args.calendar) if args.calendar else None
    name = args.epic if args.source == "capital" else (args.symbol or Path(args.csv).stem)
    label = args.label or f"{args.source}-{name}-{profile}" + (f"-{config.config_hash(config.build(profile, overrides))[:8]}" if overrides else "")
    result = protocol.evaluate(bars, meta, profile=profile, overrides=overrides, out_root=OUT, label=label,
                               events=events, unseal=args.unseal_holdout, robustness=args.robustness)
    path = report.write(result, OUT / label / "REPORT.md")
    v = result["verdict"]
    print()
    print(f"VERDETTO: {v['label']}" + (f" — {v['why']}" if v.get("why") else ""))
    d = result["dev"]["metrics"]
    print(f"Sviluppo: {d['trades']} trade, R medio {d['mean_R']}, netto {d['net_total']:.2f} {result['config']['account_currency']}")
    print(f"Report: {path}")


def cmd_download_binance(args):
    from . import data_binance
    last = tuple(int(x) for x in args.last_month.split("-")) if args.last_month else None
    print(f"Scarico {args.months} mesi di {args.symbol} {args.interval} da data.binance.vision (verifica SHA256)...")
    m = data_binance.download(CACHE, args.symbol, args.interval, args.months, last)
    print(f"OK: {len(m['files'])} archivi verificati ({m['months'][0]} -> {m['months'][-1]})")


def cmd_download_capital(args):
    from . import data_capital
    print(f"Scarico lo storico 5m di {args.epic} dal conto DEMO Capital.com (sola lettura)...")
    m = data_capital.download(CACHE, args.epic, args.months)
    print(f"OK: {m['bars']} barre, {m['first_start']} -> {m['last_start']}; stop: {m['stopped_by'] or 'periodo completo'}")


def cmd_quickstart(args):
    args.symbol, args.interval, args.last_month = "BTCUSDT", "5m", None
    cmd_download_binance(args)
    args.source, args.profile, args.set, args.calendar = "binance", None, [], None
    args.label, args.epic, args.csv, args.interval_seconds = None, None, None, None
    args.unseal_holdout = False
    args.robustness = True
    cmd_run(args)


def cmd_profiles(_args):
    for name, values in config.PROFILES.items():
        print(f"{name:24s} {values.get('symbol', 'SYNTH'):8s} {values.get('venue', 'SYNTH')}")


def cmd_selftest(_args):
    import pytest
    sys.exit(pytest.main([str(ROOT / "tests_ict"), "-q", "-p", "no:cacheprovider"]))


def main(argv=None):
    p = argparse.ArgumentParser(prog="run-ict.sh", description="ICT A1 research engine (simulation only)")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("quickstart", help="scarica 36 mesi BTCUSDT 5m ufficiali e lancia il test completo")
    q.add_argument("--months", type=int, default=36)
    q.set_defaults(func=cmd_quickstart)

    d = sub.add_parser("download-binance", help="archivi ufficiali Binance con verifica SHA256")
    d.add_argument("--symbol", default="BTCUSDT")
    d.add_argument("--interval", default="5m", choices=["5m", "1m"])
    d.add_argument("--months", type=int, default=36)
    d.add_argument("--last-month", help="YYYY-MM (default: ultimo mese completo)")
    d.set_defaults(func=cmd_download_binance)

    c = sub.add_parser("download-capital", help="storico bid/ask 5m dal conto DEMO Capital.com del bot (sola lettura)")
    c.add_argument("--epic", default="US100", choices=["US100", "US500", "BTCUSD"])
    c.add_argument("--months", type=int, default=36)
    c.set_defaults(func=cmd_download_capital)

    r = sub.add_parser("run", help="backtest + protocollo di validazione")
    r.add_argument("--source", required=True, choices=["binance", "capital", "csv"])
    r.add_argument("--symbol", default=None)
    r.add_argument("--epic", default="US100", choices=["US100", "US500", "BTCUSD"])
    r.add_argument("--csv", default=None)
    r.add_argument("--interval-seconds", type=int, default=None)
    r.add_argument("--profile", default=None, choices=sorted(config.PROFILES))
    r.add_argument("--set", action="append", default=[], help="override key=value (crea un nuovo trial)")
    r.add_argument("--calendar", default=None, help="CSV calendario macro point-in-time")
    r.add_argument("--unseal-holdout", action="store_true", help="apre l'holdout (una sola volta per config)")
    r.add_argument("--robustness", action="store_true", help="parametri geometrici ±20%% uno alla volta")
    r.add_argument("--label", default=None)
    r.set_defaults(func=cmd_run)

    sub.add_parser("profiles", help="profili strumento disponibili").set_defaults(func=cmd_profiles)
    sub.add_parser("selftest", help="test del motore (parità con il riferimento inclusa)").set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    if args.cmd == "run" and args.source == "binance" and not args.symbol:
        args.symbol = "BTCUSDT"
    args.func(args)


if __name__ == "__main__":
    main()
