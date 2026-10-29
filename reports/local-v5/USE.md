# Run the local application

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
./run-local.sh
```

Open **http://127.0.0.1:8765**. If it is already running, use that page rather than starting a second owner.
The default replays 19 October 2026, then keeps the completed dashboard open. No broker connection is attempted.
Ctrl-C checkpoints the replay; the same command resumes it, without duplicating trades. Completed runs stay completed.

## Reproduce

```sh
# A separate complete, deterministic run (choose an unused path).
./run-local.sh app --headless --run-dir data/local-v5/reproduce-01
# Another already-owned session; October 19–23 are supported by this cache.
./run-local.sh app --session 2026-10-20 --port 8766
# Separate strict mode: missing certified news/strategy blocks ALL entries.
./run-local.sh app --strict-news --headless --run-dir data/local-v5/strict-01
./run-local.sh --tests
./run-local.sh verify-frozen
./run-local.sh sandbox-preflight
./run-local.sh timestral-check
```

Options: `--strategy vwap_v1|orb_v2|sweep_mss_v2`, `--paused`, `--delay 0.2`,
`--fee-per-side 0.61`, `--slippage-ticks 1`, and the existing risk limits.
Changing session, costs, risk or strategy requires a different run directory; no automatic state reset exists.
All three strategies are unapproved. V2 candidates reuse the frozen definitions, but this application
uses V3's 20-bar warmup, entry window, fixed brackets and bounded-limit execution policy, not V2's research execution model.

## What is real, and what is not

| Component | Evidence |
|---|---|
| CME input | Owned GLBX.MDP3 OHLCV-1m; acquisition CSV hash checked before replay; 390 bars per instrument/session |
| Decision/risk/journal | Unchanged V3 Runtime and Risk; local atomic-bar Journal subclass |
| Executions | Local synthetic OHLC matching; never broker or exchange executions |
| Intrabar | Stop-first if both levels touched; adverse stop slippage; target penetration; intrabar-entry target deferred and flagged |
| Restart | SIGKILL of an actual process plus exact trade/metric replay comparison; broker state and cursor share one SQLite commit |
| Dashboard | Loopback only; no live switch; controls limited to pause/resume/local kill; CSRF token + exact Host/Origin |
| tastytrade | Contract-fixture tests only; public sandbox request returned 401, NOT authenticated verification |
| Timestral | Official installed source integrity and pinned licenses verified; weights not provisioned, real inference not run |

Each run directory contains `state.sqlite`, `summary.json`, `trades.csv`, `orders.csv`,
`executions.csv`, `decisions.csv`, `equity.csv`, and `ambiguities.json`. Risk halts are persistent.
A local kill cancels local orders and closes at the last observed historical mark with adverse slippage;
that emergency price is synthetic. A paused historical clock does not pretend to be a current market feed.
One-minute bars do not establish tick-level order sequencing or execution quality. All sessions were already observed.

## Sandbox boundary

`src/mnq_local/tasty.py` exposes the V3 broker seam: connect, snapshot, submit, cancel, poll, reconnect, close.
It allows **only** `https://api.cert.tastyworks.com`, refuses redirects and market-data endpoints,
uses at most one micro, persists submission intents before POST, and never retries an uncertain order.
Accepted orders with lost HTTP replies can be rebound by unique external identifiers, without another POST.
Absent/partial/conflicting evidence blocks. A daily sandbox reset is NOT silently treated as a reconciled flat account.
REST polling supplies order/position updates; no WebSocket certification is claimed.
No executable command joins sandbox artificial fills to the CME financial simulator.

External prerequisites, not created here: sandbox user/account and personal OAuth grant.
Configure `TASTY_SANDBOX_ACCOUNT`, `TASTY_SANDBOX_REFRESH_TOKEN`, `TASTY_SANDBOX_CLIENT_SECRET`
through a private process environment/secret manager, never source, shell history, logs or chat.
`sandbox-preflight` is read-only and does not register an account or send orders.
Sandbox fills are artificial (market at $1; limits below $3 fill; higher limits remain working),
there is no market data, and state resets every 24 hours. They cannot validate economic performance.

## Remaining external gates

- Real sandbox authentication/order acceptance: credentials are absent; contract tests are not certification.
- Timestral weights use Modified MIT, **not** the repository's Apache-2.0. Both pinned licenses exclude
  use if company/employer consolidated worldwide revenue exceeded $20M in the preceding month.
  Applicability is unknown; no eligibility attestation was invented and no weights were downloaded.
- Certified point-in-time news calendar, independent strategy validation and finer execution data remain absent.
- No scheduler, login automation, live account, production endpoint, or real-money execution was enabled.

Official sources: [Sandbox](https://developer.tastytrade.com/docs/sandbox/),
[OAuth](https://developer.tastytrade.com/docs/oauth2/),
[Orders OpenAPI](https://developer.tastytrade.com/openapi/orders.json),
[Timestral](https://github.com/mistralai/timestral).
