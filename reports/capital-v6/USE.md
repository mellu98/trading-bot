# Capital.com V6 DEMO — current delivery

## Actual external evidence

- Official DEMO `/time`: HTTP200.
- API key loaded from macOS Keychain without disclosure; DEMO `/session/encryptionKey`: HTTP200 with required response fields.
- **No authenticated account session, live quote, signal from a live feed, DEMO order or broker fill has been verified.** The key endpoint is not proof of account authentication.
- Missing: login identifier and the API key's **custom password**, not the account-login password.

## One human action

In a terminal:

```sh
cd '/Users/locoframe/Desktop/TRADING BOT'
./run-capital-demo.sh setup
```

The already saved key is reused. Enter the login identifier and API custom password at hidden prompts; do not send these through chat. Setup authenticates only against the fixed DEMO REST host, obtains the current account ID from that response, verifies the exact enabled CFD account independently, and stores the credential bundle in macOS Keychain. No account settings, deposits or subscriptions are changed.

The running default monitor detects the completed Keychain setup and proceeds in **signals_only** mode. Its current URL is http://127.0.0.1:8767/ . No order is enabled by saving credentials.

## Commands

```sh
./run-capital-demo.sh                 # default: signals only, localhost8767
./run-capital-demo.sh preflight       # account/positions/market discovery; no order
# Stop the signals-only process first: exactly one owner per account.
./run-capital-demo.sh app --mode diagnostic_demo --technical-test
```

The last command is prepared but **not broker-verified**. It waits for20fresh live quotes, uses the broker-discovered minimum CFD size (at most1unit), requests a native USD2stop/USD4target, verifies a confirmed position with correctly sided protection, then requests and confirms closing. It does not declare a fill on a POST acknowledgement. A completed real roundtrip is required before that diagnostic profile can place autonomous strategy orders. A rejected/uncertain test is not automatically repeated. Strict mode always blocks entries because news/strategies are uncertified.

No production origin, account switch, deposit, leverage change or live activation path exists. Capital documents a **shared WebSocket quote host**; it receives only tokens minted by and verified against the DEMO REST server. This is not a second production authentication route.

## Safety and remaining certification

- Unchanged V3 SQLite Journal and Risk are reused. V3 Runtime itself is futures/DU-account-specific and contains CME multipliers; passing CFDs into it would be unsafe. A small isolated CFD coordinator uses the shared journal/risk and V5 dashboard, with no edits to frozen components.
- Symbols are discovered by API search + detailed instrument metadata; no futures aliases/epics are substituted.
- Native CFD monetary protection is used, never MNQ/MES point values or fixed futures stops. Initial configuration requires a USD DEMO account and USD instruments. Actual minimum size, increment, margin, opening hours, quote resolution and permissions still require authenticated verification.
- Price-only ORB/Sweep use the unchanged causal definitions with explicit API-discovered price-unit scaling. Partial opening sessions, unknown tick size, bar gaps, future/stale/reordered quotes block signals. Joining after09:30NY without a complete opening context waits for the next complete session.
- VWAP is **blocked without verified traded volume**. Quote counts are not relabeled as exchange volume.
- Duplicate/uncertain mutations fail closed; intent commits before network I/O. SIGKILL recovery was tested locally. No uncertain POST is resent.
- Single position, maximum3entry attempts/day, maxUSD20daily loss andUSD30drawdown; known residual/foreign positions block entries. Broker-side stops are non-guaranteed and can gap; nominal USD2 is not an absolute loss guarantee.
- Broker account cash delta + reported UPL is displayed separately from model P&L. Model P&L and independently certified fees remain unavailable; no futures multiplier or zero commission is invented.
- Unconfirmed or very fast closed-before-snapshot positions may require additional broker-history reconciliation; the current implementation blocks rather than inventing a fill.
- Authenticated reconnect, native stop/target acceptance, order cancellation, actual partial fills and multi-session endurance are **not yet certified**. Fixture success is not a Capital broker certification.

## Tests and evidence

25Capital-specific fixture/local-HTTP tests passed, including native limit/cancel state, bracket direction, partial-size mismatch, kill, daily loss, stale/duplicate quotes, exact account checks, wrong-origin rejection, and an actual subprocess SIGKILL after committed intent. Combined original, simulation and local suites:176passes, including both **real cached Timestral model** smoke tests; zero skips. Unchanged adapter environments were not redundantly audited.

1519previously verified paths remain byte-identical. See verification.json, api-key-check.json, public-connectivity.json, tests-regression.txt and dashboard.png. No new paid data or real-money order was requested.
