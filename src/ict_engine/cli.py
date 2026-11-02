"""Command line: ./run-ict.sh <command>  (see src/ict_engine/README.md)."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from . import config

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "ict"
OUT = ROOT / "reports" / "ict"
CAPITAL_EPICS = ["US100", "US500", "EURUSD", "GBPUSD", "AUDUSD", "BTCUSD"]
CAPITAL_PROFILE = {"US100": "capital-us100-cfd", "US500": "capital-us500-cfd", "EURUSD": "capital-eurusd-cfd",
                   "GBPUSD": "capital-gbpusd-cfd", "AUDUSD": "capital-audusd-cfd", "BTCUSD": "capital-btcusd-cfd"}
FULL_TEST_MARKETS = ["US100", "US500", "EURUSD", "GBPUSD", "AUDUSD"]


# ---------------------------------------------------------------- data
def _load(args, *, symbol=None, epic=None):
    if args.source == "binance":
        from . import data_binance
        return data_binance.load(CACHE, symbol or args.symbol, "5m")
    if args.source == "capital":
        from . import data_capital
        return data_capital.load(CACHE, epic or args.epic)
    if args.source == "csv":
        from . import data_csv
        if not args.csv:
            raise SystemExit("--csv PATH required with --source csv")
        return data_csv.load(args.csv, symbol=symbol or args.symbol, interval_seconds=args.interval_seconds)
    raise SystemExit("unknown source")


def _companion(args, sym):
    """Bars of the SMT companion market, when available locally; None otherwise."""
    if getattr(args, "companion", None) == "none":
        return None, None
    other = args.companion if getattr(args, "companion", None) else config.COMPANION.get(sym)
    if not other:
        return None, None
    try:
        if args.source == "capital":
            bars, _ = _load(args, epic=other)
        elif args.source == "csv":
            bars, _ = _load(args, symbol=other)
        else:
            return None, None
    except (SystemExit, FileNotFoundError):
        print(f"SMT: dati di {other} non disponibili, SMT disattivato per {sym}")
        return None, None
    return bars, other


def _default_profile(args):
    if args.profile:
        return args.profile
    if args.source == "binance":
        return "binance-btcusdt-spot"
    if args.source == "capital":
        return CAPITAL_PROFILE[args.epic]
    return {"MNQ": "cme-mnq", "MES": "cme-mes", "NQ": "cme-nq", "ES": "cme-es"}.get(args.symbol or "", "synthetic")


def _symbol(args):
    return args.epic if args.source == "capital" else (args.symbol or Path(args.csv).stem)


# ---------------------------------------------------------------- commands
def cmd_calibrate(args):
    from . import calibrate, protocol
    from .bars import dedupe_sorted
    bars, meta = _load(args)
    profile = _default_profile(args)
    sym = _symbol(args)
    comp, other = _companion(args, sym)
    clean, _ = dedupe_sorted(bars)
    p = protocol.plan(clean)
    print(f"Taratura frequenza {sym} ({profile}) sul periodo di sviluppo {p['start']} -> {p['dev_end']}, "
          f"obiettivo {args.target} trade/giorno, senza guardare i profitti:")
    from .engine_v2 import CompanionSeries
    out = calibrate.calibrate(clean, meta, profile=profile, overrides=config.parse_overrides(args.set),
                              dev_end=protocol._dt(p["dev_end"]), target=args.target,
                              companion=CompanionSeries(comp) if comp else None,
                              contract_changes=meta.get("contract_changes", ()))
    out["companion"] = other
    path = calibrate.path_for(OUT, profile, sym)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    protocol.register(OUT, {"trial_id": "cal-" + out["calibration_id"], "kind": "calibration", "scope": "dev",
                            "dataset_key": out["market"], "label": path.stem, "engine": "v2",
                            "profile": profile, "chosen_level": out["chosen_level"],
                            "per_day": out["chosen_per_day"], "registered_at_utc": out["calibrated_at_utc"]})
    print(f"Scelto livello {out['chosen_level']}: {out['chosen_per_day']} trade/giorno. Salvato in {path}")
    return path


def cmd_run(args):
    from . import calibrate, protocol, report
    from .news import load_calendar
    bars, meta = _load(args)
    profile = _default_profile(args)
    sym = _symbol(args)
    overrides = config.parse_overrides(args.set)
    calibration = None
    if args.engine == "v2" and args.calibrated:
        path = calibrate.path_for(OUT, profile, sym)
        if not path.exists():
            raise SystemExit(f"nessuna taratura per {sym}: lancia prima './run-ict.sh calibrate ...'")
        calibration = json.loads(path.read_text())
        if calibration.get("data_sha256") != meta.get("data_sha256"):
            raise SystemExit("i dati sono cambiati dopo la taratura: rifai calibrate")
        overrides = {**calibration["chosen_overrides"], **overrides}
    comp, other = _companion(args, sym) if args.engine == "v2" else (None, None)
    events = load_calendar(args.calendar) if args.calendar else None
    tag = "v2" if args.engine == "v2" else ""
    suffix = f"-{config.config_hash(config.build(profile, overrides, engine=args.engine))[:8]}" if overrides else ""
    label = args.label or "-".join(x for x in (args.source, sym, profile, tag) if x) + suffix
    result = protocol.evaluate(bars, meta, profile=profile, overrides=overrides, out_root=OUT, label=label,
                               events=events, unseal=args.unseal_holdout, robustness=args.robustness,
                               engine=args.engine, companion=comp, calibration=calibration)
    path = report.write(result, OUT / label / "REPORT.md")
    v = result["verdict"]
    d = result["dev"]["metrics"]
    print()
    print(f"VERDETTO {sym}: {v['label']}" + (f" — {v['why']}" if v.get("why") else ""))
    print(f"Sviluppo: {d['trades']} trade, R medio {d['mean_R']}, netto {d['net_total']:.2f} "
          f"{result['config']['account_currency']}")
    if result.get("dev_trades_per_day") is not None:
        print(f"Frequenza: {result['dev_trades_per_day']:.2f} trade/giorno")
    print(f"Report: {path}")
    return result


def cmd_full_test(args):
    """Download (if missing) -> calibrate -> run v2 on every market, then a summary table."""
    from . import data_capital
    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    for epic in markets:
        if epic not in CAPITAL_EPICS:
            raise SystemExit(f"{epic} non supportato; disponibili {CAPITAL_EPICS}")
    if not args.skip_download:
        for epic in markets:
            if data_capital.csv_path(CACHE, epic).exists() and not args.refresh:
                print(f"{epic}: dati già scaricati (usa --refresh per riscaricare)")
                continue
            print(f"{epic}: scarico lo storico 5m dal conto DEMO Capital.com (sola lettura)...")
            try:
                m = data_capital.download(CACHE, epic, args.months)
                print(f"  OK: {m['bars']} barre {m['first_start']} -> {m['last_start']}; scartate {m.get('quarantined_bars')}")
            except BaseException as error:  # noqa: BLE001 - keep going with the other markets
                print(f"  ERRORE download {epic}: {error}")
    failures = {}
    for epic in markets:
        ns = argparse.Namespace(source="capital", epic=epic, symbol=None, csv=None, interval_seconds=None,
                                profile=None, set=list(args.set), calendar=args.calendar, label=None,
                                unseal_holdout=False, robustness=not args.no_robustness, engine="v2",
                                calibrated=True, companion=None, target=args.target)
        print(f"\n===== {epic} =====")
        try:
            cmd_calibrate(ns)
            cmd_run(ns)
        except BaseException as error:  # noqa: BLE001
            failures[epic] = f"{type(error).__name__}: {error}"
            print(f"ERRORE {epic}: {failures[epic]}")
            if args.debug:
                traceback.print_exc()
    path = write_summary()
    print(f"\nRiepilogo: {path}")
    if failures:
        print("Mercati non completati: " + "; ".join(f"{k} ({v})" for k, v in failures.items()))


def write_summary() -> Path:
    rows = []
    for res_path in sorted(OUT.glob("*/results.json")):
        r = json.loads(res_path.read_text())
        d = r["dev"]["metrics"]
        b = r["dev"]["bootstrap"]
        st = r["dev_stress"].get("costs_1.5x", {}).get("metrics", {})
        bench = r.get("dev_benchmark_random", {})
        rows.append({
            "label": r["label"], "engine": r.get("engine", "a1"), "symbol": r["config"]["symbol"],
            "months": r["plan"]["months"], "trades": d["trades"], "per_day": r.get("dev_trades_per_day"),
            "win": d["win_rate"], "mean_R": d["mean_R"], "ci": b["ci95"], "pf": d["profit_factor"],
            "r15": st.get("mean_R"), "bench": bench.get("null_mean_R") if bench.get("available") else None,
            "pbench": bench.get("p_value_a1_not_better") if bench.get("available") else None,
            "verdict": r["verdict"]["label"], "holdout": r.get("holdout", {}).get("status"),
        })

    def f(x, k=2, pct=False):
        if x is None:
            return "n/d"
        return f"{x * 100:.0f}%" if pct else f"{x:.{k}f}"
    lines = ["# ICT — riepilogo dei test", "",
             "R = risultato netto / rischio all'ingresso. Periodo: sviluppo (holdout sigillati salvo dove indicato).", "",
             "| Run | Motore | Mesi | Trade | Trade/giorno | Win | R medio | CI95 | PF | R costi 1,5× | R casuale | p vs casuale | Verdetto | Holdout |",
             "|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---|"]
    for r in rows:
        lines.append(f"| {r['label']} | {r['engine']} | {r['months']} | {r['trades']} | {f(r['per_day'])} | "
                     f"{f(r['win'], pct=True)} | {f(r['mean_R'], 3)} | [{f(r['ci'][0], 3)}; {f(r['ci'][1], 3)}] | "
                     f"{f(r['pf'])} | {f(r['r15'], 3)} | {f(r['bench'], 3)} | {f(r['pbench'])} | {r['verdict']} | {r['holdout']} |")
    path = OUT / "RIEPILOGO.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf8")
    return path


def cmd_summary(_args):
    print(write_summary().read_text())


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
    ns = argparse.Namespace(source="binance", symbol="BTCUSDT", epic=None, csv=None, interval_seconds=None,
                            profile=None, set=[], calendar=None, label=None, unseal_holdout=False,
                            robustness=True, engine="a1", calibrated=False, companion=None)
    cmd_run(ns)


def cmd_profiles(_args):
    for name, values in config.PROFILES.items():
        print(f"{name:24s} {values.get('symbol', 'SYNTH'):8s} {values.get('venue', 'SYNTH'):18s} "
              f"{config.ASSET_CLASS.get(name, '')}")


def cmd_selftest(_args):
    import pytest
    sys.exit(pytest.main([str(ROOT / "tests_ict"), "-q", "-p", "no:cacheprovider"]))


def _add_market_args(r):
    r.add_argument("--source", required=True, choices=["binance", "capital", "csv"])
    r.add_argument("--symbol", default=None)
    r.add_argument("--epic", default="US100", choices=CAPITAL_EPICS)
    r.add_argument("--csv", default=None)
    r.add_argument("--interval-seconds", type=int, default=None)
    r.add_argument("--profile", default=None, choices=sorted(config.PROFILES))
    r.add_argument("--set", action="append", default=[], help="override key=value (crea un nuovo trial)")
    r.add_argument("--companion", default=None, help="mercato per l'SMT (default automatico; 'none' per disattivare)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="run-ict.sh", description="ICT research engine (simulation only)")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("full-test", help="ICT v2 su NQ, ES, EURUSD, GBPUSD, AUDUSD: download, taratura, test")
    f.add_argument("--markets", default=",".join(FULL_TEST_MARKETS))
    f.add_argument("--months", type=int, default=36)
    f.add_argument("--target", type=float, default=1.0, help="trade medi per giorno di trading (default 1)")
    f.add_argument("--skip-download", action="store_true")
    f.add_argument("--refresh", action="store_true", help="riscarica anche i mercati già presenti")
    f.add_argument("--no-robustness", action="store_true")
    f.add_argument("--calendar", default=None)
    f.add_argument("--set", action="append", default=[])
    f.add_argument("--debug", action="store_true")
    f.set_defaults(func=cmd_full_test)

    c = sub.add_parser("calibrate", help="tara la frequenza di ICT v2 sul periodo di sviluppo, senza guardare i profitti")
    _add_market_args(c)
    c.add_argument("--target", type=float, default=1.0)
    c.set_defaults(func=cmd_calibrate)

    r = sub.add_parser("run", help="backtest + protocollo di validazione")
    _add_market_args(r)
    r.add_argument("--engine", default="a1", choices=["a1", "v2"])
    r.add_argument("--calibrated", action="store_true", help="v2: usa la taratura salvata da 'calibrate'")
    r.add_argument("--calendar", default=None, help="CSV calendario macro point-in-time")
    r.add_argument("--unseal-holdout", action="store_true", help="apre l'holdout (una sola volta per mercato)")
    r.add_argument("--robustness", action="store_true", help="parametri geometrici ±20%% uno alla volta")
    r.add_argument("--label", default=None)
    r.set_defaults(func=cmd_run)

    q = sub.add_parser("quickstart", help="A1 su BTCUSDT: scarica 36 mesi ufficiali e lancia il test")
    q.add_argument("--months", type=int, default=36)
    q.set_defaults(func=cmd_quickstart)

    d = sub.add_parser("download-binance", help="archivi ufficiali Binance con verifica SHA256")
    d.add_argument("--symbol", default="BTCUSDT")
    d.add_argument("--interval", default="5m", choices=["5m", "1m"])
    d.add_argument("--months", type=int, default=36)
    d.add_argument("--last-month", help="YYYY-MM (default: ultimo mese completo)")
    d.set_defaults(func=cmd_download_binance)

    dc = sub.add_parser("download-capital", help="storico bid/ask 5m dal conto DEMO Capital.com del bot (sola lettura)")
    dc.add_argument("--epic", default="US100", choices=CAPITAL_EPICS)
    dc.add_argument("--months", type=int, default=36)
    dc.set_defaults(func=cmd_download_capital)

    sub.add_parser("summary", help="tabella riassuntiva di tutti i run").set_defaults(func=cmd_summary)
    sub.add_parser("profiles", help="profili strumento disponibili").set_defaults(func=cmd_profiles)
    sub.add_parser("selftest", help="test del motore (parità con il riferimento inclusa)").set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    if getattr(args, "cmd", None) in ("run", "calibrate") and args.source == "binance" and not args.symbol:
        args.symbol = "BTCUSDT"
    if args.cmd == "calibrate":
        args.engine = "v2"
    args.func(args)


if __name__ == "__main__":
    main()
