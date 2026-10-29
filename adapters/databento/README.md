# Databento ingestion, isolated from Timestral

Simulation-only historical adapter for `GLBX.MDP3`, `MNQ.v.0` / `MES.v.0`,
`ohlcv-1m`, `ohlcv-1s`, `trades`, and `mbp-1`. Existing Timestral code,
configuration, environment, tests, and reports are not dependencies or modified.

## Free preflight first

From the project root:

```sh
uv --directory adapters/databento sync --frozen
# macOS: replace the rejected shared key locally; -w LAST prompts securely.
# Enter the replacement only at the prompts, never in chat or command arguments.
security add-generic-password -U -a "$USER" -s mnq-databento-api-key -w
export DATABENTO_API_KEY="$(security find-generic-password -a "$USER" -s mnq-databento-api-key -w)"
uv --directory adapters/databento run --frozen mnq-data preflight \
  --start 2026-10-23T13:30:00Z --end 2026-10-23T13:40:00Z \
  --history --output ../../reports/databento/preflight-new.json
```

Other environments: supply `DATABENTO_API_KEY` through the process environment or
a secret manager, not a source file or CLI argument. Do not enable shell tracing,
SDK HTTP debugging, or print the environment. Revoke/rotate a key shared in chat.
No `.env` loader is used. Reports never contain credentials or raw SDK exceptions.
The adapter pins Databento **0.88.0** and all transitive dependencies in its own
`uv.lock`; it does not install into the Timestral environment.

`preflight` invokes only official free metadata and symbology endpoints. It reports:
- Dataset/schema bounds; per-root/schema counts, uncompressed billable bytes, USD
  `metadata.get_cost` estimate, exact request digest and 15-minute quote expiry.
- Two-stage continuous → instrument ID → raw quarter-contract mappings, validity
  intervals and roll changes. Volume rank uses prior-day volume; calendar rank is
  supplied for comparison. Prices are not back-adjusted; mappings use UTC dates.
- Dataset daily conditions. With `--history`, full-dataset continuous mapping history.

A mapping's first date is **not** the first actual trade. Dataset bounds are **not**
MNQ/MES record coverage. Positive counts prove presence only in the quoted interval.
Authentication failures produce `not_verified` and null cost: never a fabricated
zero-price quote or a claim of historical availability.

## Download only after explicit authorization

**This session has NOT authorized downloads.** A key or a successful quote is not
purchase approval. After the human approves the exact preflight, invoke separately:

```sh
uv --directory adapters/databento run --frozen mnq-data download \
  --preflight ../../reports/databento/preflight-new.json \
  --approve-request-sha256 HUMAN_APPROVED_REQUEST_DIGEST \
  --max-usd HUMAN_APPROVED_USD_LIMIT --output data/sample-001
```

Create `adapters/databento/data/` beforehand. Output must be a new directory. An
exclusive job directory and disk-capacity check precede any paid call. All eight
requests are requoted before the first download; stale, changed, incomplete,
empty, or over-cap plans fail closed. Explicit approval is required even at $0.
Quote freshness is checked before every charged partition. Expiry stops the job
without automatically requoting or continuing; quarantine records attempted and
completed partitions. This is a **client-side estimate cap, not a vendor-enforced spending limit**.
`get_range` can charge before a local write or download fails. No automatic paid
retry occurs. `INCOMPLETE.json` quarantines a failed job: retain it for billing
reconciliation; do not simply retry. No live, batch or definition endpoints exist.

## Local quality and staging

```sh
uv --directory adapters/databento run --frozen mnq-data normalize \
  --job data/sample-001 --output data/sample-001-normalized \
  --bar-latency-ms EXPLICIT_RESEARCH_ASSUMPTION
uv --directory adapters/databento run --frozen pytest -q
```

Normalization verifies raw SHA-256 and DBN schema/dataset, actual quarter contracts,
interval membership, nanosecond clocks, OHLC/tick validity, positive traded volume,
duplicated/out-of-order bars and undefined prices. Event queries are bounded by
`ts_recv`, not necessarily monotone exchange `ts_event`. Both clocks, sequences,
flags, actions, event sizes and BBO are preserved in JSONL. MBP book size is **not**
traded volume. Undefined quotes become null, not executable prices. Suspect clock/
book flags are counted. Same-timestamp ticks are not automatically deduplicated.

Timestamp input accepts aware ISO dates with explicit `Z` or numeric UTC offset
and at most nine fractional digits, aware `pandas.Timestamp`, or unambiguous aware
`datetime`. Validation precedes parsing. Naive/local ambiguous dates, unknown
`-00:00` offsets, unitless numeric epochs, NaT, and out-of-int64-nanosecond values
are rejected; no input is silently rounded. Internal clocks use UNIX ns and
canonical UTC text retains exact precision through plans, hashes, SDK requests,
and quality checks. Equivalent offsets produce the same request digest.

OHLCV request bounds must align with the 1m/1s grid before any metadata call;
event-stream bounds may use exact nanoseconds and are end-exclusive. Gap inventory includes requested leading/trailing spans,
empty partitions and missing spans split at contract mapping boundaries. Without
request bounds only observed interior gaps are known; event streams assume no
regular grid. Missing bars are reported without forward fill: absent trades, exchange closures
and feed loss cannot be distinguished without an authoritative calendar. Quality
checks are structural, not an independent vendor-data audit. Initial 10-minute
samples cannot support an economic claim or the baseline's 70-session evaluation.

Layout: `raw/*.dbn.zst`, `preflight.json`, `provenance.json`; local normalization adds
per-schema JSONL, `quality.json`, and optional `abc-staging/bars.csv`. Minute CSV
columns match the existing A/B/C loader. `available_at` is bar end plus an explicit
latency **assumption**, never bar start. Its `manifest.staging.json` intentionally
has `attested_verified: false` / `research_ready: false`: source/license audit,
calendar/news, NY-date contract policy, real availability and transaction costs
remain externally verifiable prerequisites. No fake fees, sessions or attestations
are generated. No baseline backtest gate is bypassed.

Raw DBN, clocks and mappings are retained for a future LEAN converter. This adapter
does not implement a LEAN converter, order routing, live execution or performance
reporting. Rollback boundary: remove only `adapters/databento/` and the new
`reports/databento/` artifacts; existing Timestral paths remain unchanged.

Official references: [Historical API](https://databento.com/docs/api-historical),
[Python SDK](https://github.com/databento/databento-python),
[Symbology](https://databento.com/docs/standards-and-conventions/symbology).
