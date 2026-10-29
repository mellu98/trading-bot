# Both markets remain supported; shared safety, instrument-specific accounting

Reuse is **YES for lifecycle/safety/UI, PARTIAL for financial execution**. No new common engine or abstraction was introduced. Databento remains blocked before credential access or network until the owner resolves license, entitlement and scoped cost authorization. Binance raw observation is not an actionable strategy.

| Boundary | Existing reusable seam | Required separation |
|---|---|---|
| Data | Binance `Feed/PublicREST`; CME `DatabentoLiveProvider` | Public BTC streams vs licensed GLBX.MDP3 trades/MBP-1; separate timestamp, mapping and gap rules |
| Runtime | `SpotRuntime(Runtime)`; `DatabentoPaperSession(ReplaySession)` | Base Runtime is futures-specific, not universally instrument-neutral. Spot overrides fractional cash/fill/risk accounting; do not inject BTC into futures ContractSpec |
| Risk | Original Risk/state, admission and halt semantics unchanged | Separate accounts/journals and quote currency; Spot USDT is not a certified USD conversion |
| Persistence | AtomicJournal, account locks, WAL/FULL, rollback and recovery | One state owner; worker SQLite connection only for noncritical revision-guarded snapshots. Critical durability can still block under disk/lock stalls |
| Dashboard | Existing Dashboard/Handler/View and loopback controls | BTC8767; future CME8768. No broker route, shared position or mixed ledger |
| Models | Original Timestral paths/evidence preserved | DISABLED in active observation and baseline-only collector |

## Instrument facts used by these seams

| Field | BTCUSDT Spot | MNQ / MES futures |
|---|---|---|
| Price tick | 0.01 USDT/BTC | 0.25 index points |
| Quantity | LOT_SIZE step/min0.00001 BTC; minnotional5 USDT from actual exchangeInfo | Whole dated contracts, explicit DBN mapping; no automatic roll |
| Price-value conversion | BTC quantity × USDT/BTC price change | MNQ2 USD/point, MES5 USD/point; tick0.50/1.25 USD respectively |
| Cash/exposure | USDT cash, long/flat, no margin/short/leverage | Local futures simulator; contract/margin semantics must not be treated as spot cash |
| Current cost model | 0.1% per side,1bp slip, actual observed bid/ask for technical fills | Existing model0.25 broker+0.35 exchange+0.02 regulatory before2026-07-01, else0.01 per contract/side; actual account fees not certified |
| Sessions | 24/7, UTC day rollover | Cash-session strategy bars09:30–16:00 America/New_York; original entry/risk windows remain strategy-specific |
| Capability | Public market data only; existing one-lifetime local technical roundtrip spent | Read-only SDK trades+MBP-1 only after scoped grant; simulated entries OFF, no broker/order API |

## Dedicated personal Databento credential: safe future configuration

Do **not** populate this while permission/subscription remains unresolved. No credential was created, read, displayed or tested in this mission. The old generic Historical service and `DATABENTO_API_KEY` are never fallback sources for live mode.

After the human creates their own personal key and the organization owner resolves the required permissions:
1. Open macOS **Keychain Access** locally. In the login keychain, create a new **password item** whose item/service name is exactly `mnq-databento-personal-live-api-key`, account is the local `$USER`, and password is the full personal `db-…` value. Enter the password in the UI's hidden field, never in chat, environment, shell arguments or logs. Do not rename/overwrite the existing Historical item.
2. The owner must supply a fresh narrowly scoped authorization with `credential_owner_verified=true`, the SHA256 of that exact personal key, license/live-entitlement/cost confirmation, current explicit MNQ/MES mappings and a maximum600s expiry window. Existing grant fields remain false; no blanket activation is implied. A digest can be computed locally from hidden `getpass()` input without printing the secret; do not use the key as a CLI argument.
3. Local preflight checks the grant and intraday context only, **not** live access. Only after all authorization is independently established, the existing10-minute command is:

```sh
./run-databento-live.sh app --seconds 600 \
  --session "$(TZ=America/New_York date +%F)" \
  --contracts reports/databento-live/contracts.json \
  --authorization reports/databento-live/authorization.json \
  --run-dir data/databento-live/personal-readonly-trial --port 8768
```

This command was **not run**. It is only meaningful after09:30 New York on the requested session; do not change the context guard to force it. Grant validation precedes key lookup/SDK construction, actual key digest must match, authorization ID is one-use, duration≤600s, reconnect remains fail-closed and local entries stay disabled. A personal key alone is not a license or spending authorization.

## Verification and rollback

64 focused tests passed before the quiet soak. New key tests use only an injected fake subprocess result; no real Keychain or SDK/network. Original Runtime/Risk and instrument execution paths remain unchanged. Rollback units are the telemetry seam plus its test, the dedicated-live loader plus its test, and the separate no-order forward collector; no financial cache or prior result needs reverting. No Git repository/native gentle-ai facade exists here, so no commit or authority receipt is claimed. Skill resolution: paths-injected.
