# Paper V3 — local E2E verified; real IB paper access still missing

The isolated paper runtime is implemented and tested. It is NOT certified for continuous Interactive Brokers paper operation yet: no configured paper account or TWS/Gateway listener was available. No new strategy, data purchase or live trading was introduced. V1/V2 remain frozen.

## Start locally

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
./run-paper.sh                   # Offline preflight, no broker connection
./run-paper.sh --tests           # Paper tests only
./run-paper.sh demo --output "reports/paper-v3/my-new-demo"
```

Use a fresh demo directory. Existing state is never silently overwritten or reset. If the isolated environment must be recreated, run `./adapters/ib_paper/setup.sh`; this installs software dependencies only, not market data or subscriptions. Existing research environments are untouched.

The demo uses3,900already-cached CME minute bars and the unchanged V1 VWAP/Z-score source. Its external broker is a MOCK. Latest verified run:123decisions,33accepted,99order legs,66executions (21stop and12target exits), one persisted restart, ending flat. These numbers are infrastructure evidence, NOT new strategy performance or real IB execution evidence.

## Real paper prerequisites — configure locally, never paste passwords

1. Log into **TWS or IB Gateway PAPER**, using your paper credentials/2FA. No username/password is handled by this project. Use a dedicated paper account with no manual/other-client activity; the managed-account response must contain exactly the configured DU account.
2. Enable the socket API on loopback. Supported endpoints are `127.0.0.1:7497` (TWS paper) or `127.0.0.1:4002` (Gateway paper). Ports alone do not prove paper: every submission additionally requires the actual managed-account whitelist. No live port, live account or live mode is accepted.
3. Use read-only API initially for contract discovery. Enable order API access **only inside the paper session** when ready for technical testing. Configure IB execution/operator timestamps to UTC; explicitly attest that setting with the environment variable below. Broker timestamps lacking a determinable timezone are rejected.
4. Verify paper futures permissions and existing CME market-data entitlements. No subscription or delayed-to-real-time upgrade is purchased automatically.5secondTRADES bars require appropriate existing access; missing access stops the system rather than inventing bars.

```sh
export IB_PAPER_ACCOUNT='DU_REPLACE_WITH_YOUR_ACTUAL_DIGITS'
export IB_PAPER_PORT=7497
export IB_PAPER_CLIENT_ID=71
export IB_PAPER_EXECUTION_TIMEZONE=UTC

./run-paper.sh ib-contracts --month 202612 \
  --contracts "$HOME/.config/mnq-paper/contracts.json"

# Default: receive/reconcile data, strict entries BLOCKED.
./run-paper.sh ib-paper \
  --contracts "$HOME/.config/mnq-paper/contracts.json"

# Explicit infrastructure test ONLY, with the unapproved existing strategy.
# Use a separate persistent state directory because modes are identity-bound.
./run-paper.sh ib-paper --technical-paper \
  --contracts "$HOME/.config/mnq-paper/contracts.json" \
  --state "$PWD/data/paper-v3/technical/state.sqlite"
```

Replace the placeholder with the exact DU identifier. `ib-contracts` is a read-only official metadata query after paper-account/clock validation. Its output contains actual IB `conId`s, expiration and local symbols. **Databento instrument IDs and demo IDs1/2 are NOT IB conIds.** Runtime validates each IB contract's identity, currency, multiplier, expiration and tick before enabling the adapter. No automatic rollover is implemented: dated-contract/config changes require a deliberate flat-state migration, not an automatic new database while exposure exists.

## Stop and observe

```sh
mkdir -p "data/paper-v3"
touch "data/paper-v3/KILL"
```

For an explicitly paused/kill/stale-data halt, after removing the kill request and manually inspecting the paper account:

```sh
./run-paper.sh ib-rearm --technical-paper \
  --contracts "$HOME/.config/mnq-paper/contracts.json" \
  --state "$PWD/data/paper-v3/technical/state.sqlite"
```

This read-only-broker operation requires fresh authenticated paper truth with zero positions and zero working orders. It preserves all P&L, peak, loss/trade counters and session data blocks. It cannot clear global drawdown, uncertain submissions or foreign/mismatched portfolio incidents. Real-paper re-arm behavior still needs the authenticated acceptance test.

Kill is latched in the journal. Removing the file does not silently re-arm a halted account. Ctrl-C/SIGTERM also freezes entries, cancels owned orders and attempts a snapshot-confirmed flatten. Inspect `health.json`, `shutdown.json` and the SQLite journal beside the selected state file. `flat_confirmed` requires a fresh broker snapshot with zero positions AND zero working orders. Disconnected shutdown cannot guarantee flatness: inspect the PAPER account manually. Never delete/reset a state database to resolve a mismatch or uncertain submission.

## What owns what

| Component | Responsibility |
|---|---|
| `mnq_paper.core.Runtime` | Sole local order/position owner, durable intent, idempotency, reconciliation and decision pipeline |
| `Journal` | SQLite WAL/FULL, account-wide single-writer lock, account/config/contract identity, persistent fills and risk |
| `signals.SignalSource` | Replaceable signal interface; default wraps unchanged V1 features/SignalGenerator; cannot override risk |
| Existing `mnq_timestral.strategy.Risk` | Daily loss, drawdown, trade/consecutive-loss and exposure gate |
| `IBPaper` | Official SDK transport, callback queues and temporary snapshot buffers; not a second strategy/execution engine |
| `MockBroker` | External-broker test double only; simulated matching is never claimed as IB behavior certification |
| Timestral | Separate, optional and OFF; never consulted by paper decisions |

## Execution and safety policy

- One contract by default, portfolio exposure blocked while any position/order is outstanding. Integer partial-fill scenarios are tested with the bounded2contract configuration.
- Entries are bounded marketable limits, anchored to the observed signal close±1tick, with a broker-side60secondGTD expiry. This is an explicit infrastructure execution policy, not an unchanged backtest fill assumption.
- Attached target/stop use the existing MES4/2point and MNQ15/8point distances from the known limit. Parent and target have `transmit=False`, final stop `True`; children are GTC with native sibling cancellation. Actual fill quality and exchange behavior still need paper observation.
- Persist the complete intent/IDs BEFORE I/O. Unknown submission is never automatically resent. Execution IDs are idempotent; orderStatus alone never changes positions. Reconcile executions, orders and positions before readiness. Snapshot fills are causally sorted; corrections/foreign state block entries.
- Partial fills/rejections/missing protection trigger cancel/reconcile/flatten, not a claim that an inactive attached stop protected a partial parent. Cancellation and flatten are NOT atomic; disconnects/exchange gaps may delay them. An uncertain flatten is never retried automatically because a second fill could reverse exposure.
- Kill, daily$200loss, global$500drawdown,10trades/day and3consecutive net losses remain enforced locally. Actual fee callbacks have a conservative scenario floor; delayed commissions are persisted even when received before the execution. Mark-to-minute risk is not tick-level or server-wide drawdown protection.
- Lost connection blocks entries and reconnects with bounded exponential backoff; portfolio revalidation is mandatory. Native protection remains at the broker where supported. No guarantee is made while disconnected. Unknown/foreign portfolio activity is never silently adopted or liquidated.
- Exact5secondUnix-ns aggregation requires12bars/minute, correct OHLC/volume and ordering. No gap filling or historical download. Start before09:30NewYork; missing the cash open or a feed gap blocks that session. Uncertified strict news/strategy status always blocks openings; technical mode exists only inside the paper-only adapter.

## Verified versus pending

| Boundary | Evidence |
|---|---|
| Original data/source preservation |309frozen V1/V2 paths and90original/37primary paths unchanged |
| Local end-to-end | Actual cached CME1m input, original signal/risk, SQLite and restart; MOCK broker/fills |
| Official SDK |1051.1 installed from pinned official1051.01archive;235source files verified; actual SDK encoded bracket messages in memory |
| Fault behavior |42executed tests: duplicates, partials, rejected children, missing brackets, stale data, disconnect, crash/ambiguous sends, wrong account/client, UTC, fee ordering and single writer |
| Real paper handshake/data/order/fill | **NOT VERIFIED** — missing authenticated TWS/Gateway paper session/account configuration |
| Continuous unattended operation | Pending real-paper soak, outage/relogin and contract-transition drills, monitoring/OS-sleep controls, data entitlements and account-specific costs |
| Financial validation | No strategy promoted. Requires fresh unseen data, realistic execution/cost validation and certified PIT news; technical paper success does not establish an edge |

No LEAN migration was performed. [LEAN itself is Apache2](https://github.com/QuantConnect/Lean/blob/master/LICENSE) and a manual source build is possible without claiming a mandatory platform subscription. The recommended [LEAN CLI requires paid-organization membership](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started). Docker is now available, but .NET/LEAN image/runtime are not provisioned; replacing the working engine would add migration and duplicate-state risk without solving missing broker access. The existing bounded Python path was selected instead.

## Timestral / hardware

The machine is arm64Mac with16GiB RAM, CPU PyTorch2.14.1 and available MPS. Pinned28M/209M weight sizes (~111MB/~837MB) do not by themselves demonstrate runtime memory, latency or forecast quality. Real checkpoints are not provisioned. The pinned ModifiedMIT license includes company/employer revenue eligibility; that external fact remains unverified, so no eligibility flag, weight download or real-model inference was fabricated. See the preserved `reports/real-simulation/timestral-license.txt` and original model pins. Timestral integration remains disabled.

## Official references

- [IB API download](https://download2.interactivebrokers.com/installers/tws-api/index.html) — official SDK provenance, GPL3license retained with the distribution.
- [IB bracket transmission](https://interactivebrokers.github.io/tws-api/bracket_order.html) and [order-status caveats](https://interactivebrokers.github.io/tws-api/order_submission.html) — duplicates/missing status updates require execution callbacks and reconciliation.
- [IB5second bars](https://www.interactivebrokers.com/docs/tws-api/doc/md/5-second-bars) and [market-data requirements](https://www.interactivebrokers.com/docs/tws-api/doc/md/introduction) — data access is entitlement-dependent; no purchase has been made.

Rollback boundary: remove only the new `src/mnq_paper`, `tests_paper`, `adapters/ib_paper`, `run-paper.sh` and paper-specific artifacts, AFTER any actual paper exposure/orders are independently confirmed flat. V1/V2 sources/data/reports need no rollback. No Git commits or review receipts were created; this workspace has no Git repository/native review facade. CodeGraph was uninitialized and its required facade unavailable, so scoped filesystem inspection was used.
