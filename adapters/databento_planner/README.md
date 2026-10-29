# Plan Databento cash-session research without buying data

This isolated package compares **actual free vendor quotes** for MNQ/MES `GLBX.MDP3` `ohlcv-1m` over 1, 5, 20 and 60 completed NY cash sessions. It does not change the verified adapter or Timestral. **The CLI has no acquisition command.**

## Run

From `/Users/locoframe/Desktop/TRADING BOT`:

```sh
PYTHONDONTWRITEBYTECODE=1 adapters/databento_planner/.venv/bin/python -m databento_planner compare
```

The output directory must be a strict nonsymlink descendant under `/Users/locoframe/Desktop/TRADING BOT/reports/databento/planning`; initial failure/audit reports are never overwritten. The default NEW `correction-study` folder atomically updates only its own complete/partial study reports. For a separate study, pass `--output /Users/locoframe/Desktop/TRADING\ BOT/reports/databento/planning/another-run`. `--as-of` accepts an explicit aware timestamp; the default is now UTC. Each invocation makes at most60 NEW free calls within a240s transport budget (`--max-calls`1–60, `--max-seconds`≤300). Repeat the SAME command/output/as-of to resume exact atomic per-endpoint checkpoints, newest sessions first. No completed response is requested again. Partial scenario totals remain null until every required metric is present. Per-response checked/expiry times are retained; expired quotes remain historical study evidence but cannot authorize acquisition.

Credentials load automatically from macOS Keychain service `mnq-databento-api-key`, account `$USER`. Keychain wins over an environment value. Only a single CLI transport newline is removed. A bare 29-character body may receive the documented `db-` prefix **in memory only for free metadata**; the report distinguishes this from a complete stored key. No credential, fragment, fingerprint, raw SDK error, or Authorization header is written. All HTTP remains single-threaded; SDK process-global transport patches are not used concurrently. Keychain is never changed.

## Offline cache plan

```sh
PYTHONDONTWRITEBYTECODE=1 adapters/databento_planner/.venv/bin/python -m databento_planner cache-plan \
  --comparison '/Users/locoframe/Desktop/TRADING BOT/reports/databento/planning/correction-study/cost-comparison-complete.json' \
  --sessions 5 \
  --cache '/Users/locoframe/Desktop/TRADING BOT/adapters/databento_planner/cache' \
  --output '/Users/locoframe/Desktop/TRADING BOT/reports/databento/planning/cache-plan-5.json'
```

Local raw coverage uses dataset, schema, actual contract/instrument ID, publisher, source revision and normalizer/source hash identity—not the whole expanding scenario hash. Trusted interval union/subtraction reuses overlaps. Quote reports, fixtures and incomplete files do not count. Registration requires completed provenance, exact SDK DBN metadata, publisher/instrument checks, record bounds/structure, raw SHA256 and confined nonsymlink paths. Coverage means a completed raw query, not a fabricated full record grid. Structural checks do not make data ABC-ready.

Hashes and unsigned receipts prove **local consistency, not vendor authenticity or latest vendor revision**. Known corruption/staleness requires manual quarantine and replanning; the planner never automatically repurchases it. If a cache hit splits an existing quote, the new exact misses have unknown cost until separately requoted—no proportional price estimates.

## Future acquisition gate (not connected to a paid SDK backend)

`execute_approved` is an injected, fake-backend-tested boundary, not an enabled production downloader. `configured_cap` defaults to `0`; an `Approval(exact_job_digest, max_usd, new_nonce)` is required **for every job, including $0**. A future human-approved integration must provide the backend and explicitly set the configuration cap. CLI planning never creates an approval or calls this executor.

The digest binds actual contracts, exact intervals/cache misses, quoted price and expiry. A cache file lock, durable reservation/consumed nonce, exclusive destination, disk/output checks, cumulative Decimal cap and fresh quote/TTL **before every charged partition** prevent overlapping jobs and retries from silently expanding approval. Failure stays INCOMPLETE; no paid retry or automatic cache admission occurs. Client estimates are **not a vendor-guaranteed billing limit**.

| Boundary | Meaning |
|---|---|
| Session window | XNYS 09:30 NY to actual close, including half days/DST; NOT full CME Globex |
| Roll selection | Provider previous-day-volume rank0, resolved to actual raw contracts and instrument IDs; no back adjustment or guessed expiry |
| Vendor conditions | Each selected date must be available; missing/degraded/unavailable is rejected |
| Counts | Presence/count consistency only; not proof of gap-free acquired data |
| Entitlements | Successful metadata access only; paid entitlement, license acceptance and balance untested |
| Tier2 | `ohlcv-1s` + `mbp-1` configured only; never quoted here; new scope/budget/approval required |

Five sessions is the minimum useful multiday technical sample; one is the cheapest smoke test. None of 1/5/20/60 meets default ABC splitting: 70 joint sessions for one fold, 90 for both statistical count floors. No gates are loosened and no performance claim is made.

## Verify / rollback

```sh
PYTHONDONTWRITEBYTECODE=1 adapters/databento_planner/.venv/bin/python -m pytest -p no:cacheprovider -q adapters/databento_planner/tests
```

Tests use synthetic metadata/DBN only in temporary directories. Remove only the NEW `/Users/locoframe/Desktop/TRADING BOT/adapters/databento_planner` tree and new planning outputs to roll back. Do not remove the pre-existing planning integrity/interface reports. Existing source/tests/environments/egg-info/reports remain immutable.
