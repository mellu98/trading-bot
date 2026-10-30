"""Human report (Italian) written next to results.json."""
from __future__ import annotations

from pathlib import Path


def _f(x, digits=3, pct=False):
    if x is None:
        return "n/d"
    if pct:
        return f"{x * 100:.{max(digits - 1, 1)}f}%"
    return f"{x:.{digits}f}"


def _period_row(name, ev):
    m, b = ev["metrics"], ev["bootstrap"]
    ci = b["ci95"]
    return (f"| {name} | {m['trades']} | {_f(m['win_rate'], 3, True)} | {_f(m['mean_R'])} | "
            f"[{_f(ci[0])}; {_f(ci[1])}] | {_f(b['p_one_sided'])} | {_f(m['profit_factor'], 2)} | "
            f"{_f(m['max_drawdown'], 3, True)} | {_f(m['net_total'], 2)} |")


VERDICT_TEXT = {
    "REJECT": "La strategia perde dopo i costi sul campione fuori campione. Archiviare questa versione.",
    "REJECT (screening)": "Già nel periodo di sviluppo l'aspettativa netta è negativa o nulla. Non ha senso aprire l'holdout: archiviare questa versione o cambiare ipotesi (nuovo trial).",
    "RESEARCH": "Evidenze insufficienti o criteri non soddisfatti. Nessun paper trading, nessun capitale.",
    "CANDIDATE": "Aspettativa positiva nello sviluppo. Prossimo passo: aprire l'holdout UNA volta, senza modificare nulla prima.",
    "PAPER TRADE": "Tutti i gate superati: si può passare al paper trading (60 giorni, 100 fill) secondo la roadmap. Nessun capitale reale.",
}


def write(result: dict, path: Path) -> Path:
    v = result["verdict"]
    cur = result["config"]["account_currency"]
    L = []
    L.append(f"# ICT A1 — {result['label']}")
    L.append("")
    L.append(f"**Verdetto: {v['label']}.** {VERDICT_TEXT.get(v['label'], '')}")
    if v.get("why"):
        L.append("")
        L.append(f"Motivo: {v['why']}.")
    if v.get("failed"):
        L.append("")
        L.append("Gate non superati: " + ", ".join(f"`{x}`" for x in v["failed"]) + ".")
    L.append("")
    L.append("## Cosa è stato testato")
    L.append("")
    cfg = result["config"]
    L.append(f"- Strategia {result['strategy_version']} (sweep → MSS con displacement → FVG immediato, entry limit al 50% del FVG, "
             f"stop oltre lo sweep, target sulla liquidità opposta, net RR ≥ {cfg['min_net_rr']}), parametri del pacchetto "
             f"{'invariati' if result['baseline_matches_package'] else 'DIVERSI dal pacchetto'}.")
    L.append(f"- Mercato: {cfg['symbol']} su {cfg['venue']}, M5, sessione {cfg['session_start']}–{cfg['session_end']} New York, "
             f"{'long e short' if cfg['short_allowed'] else 'solo long'}.")
    L.append(f"- Dati: {result['data'].get('source')}; {result['plan']['months']} mesi completi "
             f"({result['plan']['start']} → {result['plan']['end']}); {result['data']['quality']['segments']} segmenti continui, "
             f"{result['data']['quality']['missing_bars_total']} barre mancanti.")
    L.append(f"- Costi base: fee {cfg['fee_rate'] * 100:.3f}% per lato"
             + (f", {cfg['unit_fee_eur']} per contratto a/r" if cfg["unit_fee_eur"] else "")
             + (f", slippage {cfg['slippage_bps']} bp" if cfg["slippage_bps"] is not None else f", slippage {cfg['slippage_price']}")
             + f" su stop/uscite a mercato; spread: {result['spread_source']}.")
    L.append(f"- Filtro news: {result['news_filter']}.")
    L.append(f"- Rischio per trade {cfg['risk_fraction'] * 100:.2f}% del capitale, conto iniziale {cfg['initial_equity']} {cur}.")
    L.append("")
    L.append("## Risultati (R = risultato netto / rischio stimato all'ingresso)")
    L.append("")
    L.append(f"| Periodo | Trade | Win rate | R medio | CI95 R medio | p (R≤0) | PF | Max DD | Netto {cur} |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    L.append(_period_row(f"Sviluppo {result['dev']['from']}→{result['dev']['to']}", result["dev"]))
    for scen, ev in result["dev_stress"].items():
        L.append(_period_row(f"Sviluppo, {scen}", ev))
    L.append(_period_row("Sviluppo, limite ottimistico (solo diagnostica)", result["dev_optimistic_bound"]))
    h = result.get("holdout", {})
    if h.get("period"):
        L.append(_period_row(f"**Holdout {h['period']['from']}→{h['period']['to']}**", h["period"]))
        L.append(_period_row("Holdout, costi 1,5×", h["costs_1.5x"]))
    L.append("")
    L.append(f"Holdout: {h.get('status')}" + (f" — {h['why']}" if h.get("why") else "") + ".")
    L.append("")
    L.append("### Stabilità per fold (sviluppo)")
    L.append("")
    L.append("| Fold | Trade | R medio | Netto |")
    L.append("|---|---:|---:|---:|")
    for f in result["dev_folds"]:
        m = f["metrics"]
        L.append(f"| {f['from']}→{f['to']} | {m['trades']} | {_f(m['mean_R'])} | {_f(m['net_total'], 2)} |")
    b = result["dev_benchmark_random"]
    L.append("")
    L.append("### Confronto con ingressi casuali abbinati")
    L.append("")
    if b.get("available"):
        L.append(f"Stessa ora, direzione e geometria stop/target, ingresso casuale: R medio nullo {_f(b['null_mean_R'])} "
                 f"(5°–95° percentile {_f(b['null_p5'])}…{_f(b['null_p95'])}) contro A1 {_f(b['a1_mean_R'])}; "
                 f"p che A1 non sia migliore = {_f(b['p_value_a1_not_better'])}.")
    else:
        L.append(f"Non disponibile: {b.get('reason')}.")
    m = result["dev"]["metrics"]
    L.append("")
    L.append("### Dettagli sviluppo")
    L.append("")
    L.append(f"- Long/short: {m['longs']}/{m['shorts']}; uscite: {m['exit_reasons']}; barre ambigue (stop e target nella stessa barra): {m['ambiguous_bars']}.")
    L.append(f"- Fee totali {_f(m['fees_total'], 2)} {cur}; fee burden {_f(m['fee_burden'], 3)} (fee / profitti lordi dei trade vincenti).")
    L.append(f"- Sharpe in eccesso su un tasso privo di rischio costante del {m['rf_annual_assumed']:.0%} (approssimazione del T-bill): "
             f"{_f(m['sharpe_excess'], 2)}; esposizione {_f(m['exposure'], 3, True)} del tempo.")
    L.append(f"- Giorni con trade {m['days_with_trades']} su {m['days']}; massima serie di perdite {m['max_consecutive_losses']}.")
    dc = result["dev_decision_counts"]
    funnel = ["SWEEP_CONFIRMED", "SKIP_SWEEP_INVALIDATED", "SKIP_MSS_EXPIRED", "SKIP_FVG_EXPIRED", "SKIP_NO_TARGET",
              "SKIP_ENTRY_OR_STOP", "SKIP_NET_RR", "SKIP_SHORT_UNSUPPORTED", "SKIP_MINIMUM_SIZE",
              "SKIP_SPREAD_TOO_HIGH", "SKIP_SLIPPAGE", "ENTER_LONG", "ENTER_SHORT"]
    L.append("- Imbuto dei setup: " + ", ".join(f"{k} {dc.get(k, 0)}" for k in funnel) + ".")
    L.append(f"- Ordini cancellati: {result['dev_cancels']}.")
    acc = result["account_view_dev"]
    L.append(f"- Vista conto con le regole del pacchetto (stop al drawdown 8%): da {acc['initial_equity']} a "
             f"{_f(acc['final_equity'], 2)} {acc['currency']} con {acc['trades']} trade"
             + (f"; il bot si sarebbe fermato il {acc['halted_at'][:10]}" if acc["halted_at"] else "; nessun arresto per drawdown")
             + ("." if acc["sizing_realistic"] else " (profilo di ricerca: dimensione del conto non realistica, leggere solo le R)."))
    if result.get("robustness"):
        r = result["robustness"]
        L.append(f"- Robustezza ±20%: {r['share_positive'] * 100:.0f}% dei vicini con R medio > 0.")
    hd = result.get("holm_dev")
    if hd:
        L.append(f"- Holm sulla famiglia di {hd['family_size']} trial registrati: soglia {_f(hd['threshold'], 4)}, "
                 f"{'significativo' if hd['reject'] else 'non significativo'}.")
    L.append("")
    L.append("## Limiti")
    L.append("")
    L.append("- Barre OHLC: ordine intrabar sconosciuto, quindi stop prima del target (limite prudente); il limite ottimistico è solo diagnostica.")
    L.append("- Nessun fill parziale, coda o latenza reale: i risultati non possono qualificare il live (protocollo 07).")
    if result["spread_source"] != "native_bid_ask":
        L.append("- Spread storico non disponibile: valore assunto. Per il protocollo l'esito massimo resta RESEARCH finché non si testa su bid/ask reali.")
    if result["news_filter"].startswith("not_applied"):
        L.append("- Filtro news non applicato: manca un calendario storico point-in-time.")
    L.append("- Nessun numero qui è una previsione di guadagno futuro.")
    L.append("")
    L.append(f"Config hash `{result['config_hash'][:16]}`, strategy hash `{result['strategy_hash'][:16]}`, "
             f"dati `{result['data'].get('data_sha256', '')[:16]}`. Registro trial: `{result['registry']}`.")
    path.write_text("\n".join(L) + "\n", encoding="utf8")
    return path
