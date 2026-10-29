# V4 — installation and local tests complete; real Paper authentication blocked

IB Gateway10.50Apple Silicon is installed inside this project. The Mac was locked during native UI access; no login/2FA, authenticated Paper UI, account authorization, API settings or entitlements could be observed. No real IB server test or accepted paper order is claimed.

## Exact safe entrypoints

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
./run-paper-v4.sh status
./run-paper-v4.sh read-only
./run-paper.sh --tests
```

`status` is offline except for checking local4002/7497listeners. `read-only` returns BLOCKED until authorized account/login/API prerequisites exist; it never submits or cancels orders. Gateway application:

`/Users/locoframe/Desktop/TRADING BOT/tools/ibgateway/runtime/IB Gateway 10.50.app`

## Required human action

On the unlocked Mac, complete the **PAPER** login/2FA in that Gateway, select the authorized paper account, enable local API access on4002 with **Read-Only API enabled**, and leave the authenticated session open. Do not paste passwords or2FA into chat/code/logs. Do not choose Live. Application installation did not configure or certify any account.

The exact selected/authorized account must then be configured locally in `data/paper-v4/connection.json` (private0600; template is `reports/paper-v4/connection.example.json`) or `IB_PAPER_ACCOUNT`. A template/null account is not authorization. The account must match the authenticated API and selected UI account. Default client71 owns trading state; initial read-only observer uses72 to avoid client-ID collision. No credential is saved in this file.

## Two independent safety boundaries

1. The official API response must confirm Read-Only for the initial audit. `reqConfigProtoBuf` exposes `api.settings.readOnlyApi` and actual socket port; unsupported/absent fields fail closed. Account summary, positions, order visibility, contract identity and actual5secondMNQ/MES samples are recorded separately. Read-Only may restrict order inventory: missing/refused information means **unverified**, never zero orders. AccountType is not a Paper-mode flag.
2. Before any operational connection or financial mutator, a separate private session evidence file must bind an **observed authenticated Paper UI**, exact authorized/UI/API account, current signed IB listener PID/start/image, unmodified UI evidence and the successful initial actual Read-Only report. Evidence expires after12hours or process replacement. It is external UI/operator evidence, not an API self-certificate. No valid evidence file was created while the Mac was locked. There is no `--force`, `--assume-paper` or automatic evidence issuer.

The [official IB guide](https://interactivebrokers.github.io/tws-api/third_party.html) explains that API clients connect to a running TWS/Gateway and do not distinguish the login mode. DU-prefix and paper-default port are additional allowlist restrictions, NOT proof of Paper. The signed-process/UI/account evidence must actually be checked after login; a JSON schema alone does not certify the session.

The initial successful Read-Only audit writes private contract IDs/inventory to `data/paper-v4/` and a redacted response report to `reports/paper-v4/read-only-report.json`. Databento IDs and local mock IDs are never reused as actual IB conIds. Market-data probes do not buy subscriptions; no samples can indicate closed markets or absent permissions and are not proof of either. API data rights/futures permissions remain unverified until real responses.

## Isolated order acceptance — prepared, NOT executed

Only after independent session proof and actual API writable configuration are verified:

```sh
./run-paper-v4.sh paper-smoke \
  --session-proof "$PWD/data/paper-v4/session.json"
```

This reuses the V3Runtime/SQLite/Risk/adapter and creates at most **one entry intent, one micro contract**, with native bracket and bounded cleanup. Entry uses actual fresh MES5second data inside09:45–15:30NewYork; outside that window no order/state is created. No strategy is introduced or promoted. The dedicated acceptance journal cannot be replaced to retry uncertain orders, reused from an operational run or used to issue a second entry after restart. Target/stop acknowledgement, actual executions and fresh flat/no-orders confirmation are distinct report fields. If disconnected or uncertain, inspect only the paper account manually; no automatic entry/flatten resend is used.

A single integer micro contract cannot deterministically produce an integer partial fill. Partial/cancel-race recovery remains locally tested until genuinely observed; no2contract order is sent to manufacture that case. One bracket cannot prove both mutually exclusive stop and target executions. Missing cases remain pending, not “passed by mock.”

No program automatically disables Read-Only, logs in, handles2FA, changes a subscription or accepts financial account actions. Actual writable access must be enabled only for the independently verified Paper session. The adapter refuses financial mutators by default, even when the account begins DU and the port is4002/7497.

## Continuous runtime and monitoring

```sh
# Initial read-only heartbeat observer, no order capability:
./run-paper-v4.sh watch

# Existing single-owner runtime, strict/unapproved entries remain blocked:
./run-paper-v4.sh run

# Explicit future technical-paper runtime ONLY after authenticated acceptance:
./run-paper-v4.sh run --technical-paper \
  --session-proof "$PWD/data/paper-v4/session.json"
```

Do not run the initial API Read-Only observer concurrently with writable acceptance: Read-Only is a Gateway-wide setting and the observer stops if it is disabled. The operational runtime owns its heartbeat/reconciliation; external status only observes files, never takes over positions/orders. Default state is `data/paper-v4/paper/state.sqlite`; kill file is `data/paper-v4/KILL`. Use the V3explicit rearm procedure with the same exact identity and session proof. Halts never reset P&L/risk counters or clear uncertain/foreign exposure/global drawdown.

Heartbeat uses real `reqCurrentTime` responses, clock bounds and fresh API configuration. New financial mutations are blocked if heartbeat/config evidence is stale. Disconnect invalidates readiness; backoff reconnect and full reconciliation are required. Health records have UTC timestamps; an old green record becomes STALE after15seconds. Missing cash-open data/gaps block the session, with no invented backfill. Native brackets and parentGTD reduce risk while disconnected but do not guarantee execution or hard drawdown limits. Strict news remains blocked; Timestral remains OFF.

## Evidence and certification criteria

- Local suites actually executed: original54passed/2skipped, simulation48passed, Databento123passed, planner44passed, paper V3/V4 54passed: **323passed,2skipped**. The skipped tests require real Timestral checkpoints.
- Actual SDK source/serialization and local SQLite/restart work are real software tests; broker responses/fills in unit/E2E tests are simulated. The cached-data mock replay remains separate and is never written as an actual paper acceptance receipt.
- Authenticated IB tests passed: **0**. Actual accepted IB paper orders: **0**. Purchased subscriptions/data/live orders: **0**.
- V1/V2 309paths, original90/37primary and planner20paths retain original hashes. V3core/Risk/signal ownership was not rewritten; V4hardens transport entrypoints and monitoring.

Continuous Paper certification still requires observed Paper/account proof; real Read-Only inventory/permissions/data; actual bracket/GTD/OCA/cancel/fill and risk-stop evidence; crash/reconnect/relogin/reauthentication drills with no duplicate or unprotected exposure; fresh-state/fee and stale-data behavior; and a monitored multi-session soak. Record unsupported/unobserved cases explicitly. Infrastructure success does not approve a strategy, replace independent financial validation or certify the news calendar.

Official installation: [IB Gateway download](https://www.interactivebrokers.com/en/trading/ibgateway-latest.php), [install4j documented unattended installation](https://www.ej-technologies.com/resources/install4j/help/doc/installers/options.html). Installer/application signatures were verified as Interactive Brokers LLC, teamL6H6D9Q7DY; the notarized installer was installed into a new project directory without replacing another application. Exact provenance is in installation.json. No authentication protection was bypassed to work around the locked Mac.
