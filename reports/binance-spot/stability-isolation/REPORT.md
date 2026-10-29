# Binance latency isolation: one receive-pump defect fixed; global readiness still FAIL

**Actual result:** all four real-feed arms completed at least600 connected seconds each; the fixed A/D comparison completed another600+ seconds per arm; the final full-runtime soak completed **1902.901 conservative observed connected seconds** excluding startup, cleanup and planned restart downtime. The fairness fix removed fresh-burst queue overflows in the measured fixed runs, but **36 processing-delay rejections remain**. No financial/model experiment, order, credential access or Databento connection occurred.

## Five answers

1. **Where was a concrete defect?** A greedily draining buffered WebSocket reader could enqueue more than512 fresh frames without yielding to its state-owner consumer. Every arm reproduced overflows with low queue delay. A six-line cooperative enqueue helper yields at32 queued frames (1/16 of unchanged capacity). Deterministic513/10000-frame regressions reproduce the old failure and preserve every ordered frame after the fix; a pre-full queue still fails closed.
2. **Is parsing/strategy/Risk the timing culprit?** Not established. In the original balanced matrix, A/B/C/D all had zero≥250ms delay rejections; process CPU rose from roughly1.9% to10.0% of one core across the layers. C ran real Feed and original read-only Risk hooks, but observed **zero complete new4h bars**: active economic strategy workload is **N/A**, not certified. Timestral remained disabled.
3. **Did persistence/GC cause the residual stalls?** Exact attribution remains **INCONCLUSIVE**. One owner encode took613.65ms wall but only5.11ms thread CPU; low CPU does not identify whether scheduling, GIL, page faults or storage caused the wait. Critical FULL durability was retained. Protection was **not exercised** because every runtime remained flat. All stage/CPU/GC/SQLite/dashboard distributions are in `stage-quantiles.json`.
4. **Host or network?** Independent minimal raw-WS witness timer lateness overlaps all14 recorded slow D spans; the strongest D loop interval412.78ms wall/1.42ms thread CPU overlaps401.79ms witness lateness. This demonstrates a shared local scheduling/waiting component; it does not assign its full mechanism. System paging/disk activity is contextual: all three reject-cluster target-PID `ps pagein` deltas were0. No network-latency inference is made from source age or arrival silence. One original D receive timeout/unrepairable trade gap remains unresolved. Old22/35 rejections are not retrospectively explained.
5. **Ready for actionable trading?** **NO — global FAIL/BLOCKED.** A current connection certificate is instantaneous feed eligibility, not a30-minute stability certificate. Raw observation and guarded no-order forward collection are running; original spent1BUY/1SELL/cash and all177 protected paths are preserved.

## Comparison: actual public feed

CPU is percentage of **one core**, from process CPU/connected duration; not whole-machine utilization. RSS is process peak. Rates normalize different market windows but do not eliminate sequential host/market confounds.

| Phase/arm | Connected s | Frames/s | Frames | Queue overflows | ≥250ms rejects | Max queue ms | Max loop lag ms | CPU % one core | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Original A | 600.332 | 222.15 | 133366 | 3 | 0 | 6.126 | 12.371 | 1.86 | 54.45 |
| Original B | 600.113 | 179.77 | 107885 | 3 | 0 | 20.708 | 22.356 | 2.07 | 54.66 |
| Original C | 600.113 | 164.32 | 98608 | 4 | 0 | 20.024 | 44.914 | 3.13 | 55.52 |
| Original D | 603.483 | 152.95 | 92302 | 2 | 0 | 38.444 | 50.319 | 9.99 | 76.31 |
| Fixed paired A | 600.393 | 213.06 | 127920 | 0 | 0 | 156.769 | 169.707 | 1.84 | 54.89 |
| Fixed paired D | 605.129 | 312.07 | 188840 | 0 | 0 | 116.644 | 118.157 | 12.68 | 75.53 |
| Fixed soak D | 1904.616 | 155.86 | 296856 | 0 | 36 | 877.059 | 930.022 | 10.60 | 74.39 |

A: raw WS/no JSON/runtime/persistence. B: JSON only. C: existing Feed + read-only original Risk + frozen closed4h condition, no account/order engine. D: existing full Runtime/journal/dashboard, original spent journal. D instrumentation-only caveat: internal OS probes were externalized to the same sampler used by all arms. D status GETs1/s represent UI load. The corrected sampler itself consumed0.80%/0.76% of one core in original/fixed windows including child processes and continuous iostat.

The first, top-heavy apparatus calibration is preserved separately and **never merged** into these comparisons. Repeated `top -l1` cost about23% of one core; `iostat -c1` was a since-boot average. The additive correction removed repeated top and uses documented continuous5s iostat, discarding its first row. No experiment, source or old raw evidence was overwritten.

## Freshness, disk and GC

| Phase/arm | Feed samples | Book unfresh | Trade unfresh | Max GC wall ms | Rusage input/output blocks |
|---|---:|---:|---:|---:|---:|
| Original A | N/A | N/A | N/A | 5.209 | 0/0 |
| Original B | N/A | N/A | N/A | 2.493 | 0/0 |
| Original C | 613 | 15 | 23 | 16.376 | 0/0 |
| Original D | 603 | 28 | 38 | 29.683 | 0/0 |
| Fixed paired A | N/A | N/A | N/A | 31.613 | 0/0 |
| Fixed paired D | 596 | 4 | 14 | 33.836 | 0/0 |
| Fixed soak D | 1864 | 11 | 57 | 42.625 | 0/0 |

Zero rusage block counters are reported raw, **not** proof of no I/O. macOS counters do not supply process byte attribution here. Actual5s disk0 interval throughput and system CPU are system-wide, not bot-only:

| Window | System busy % p50/p95/p99/max | Disk0 MB/s p50/p95/p99/max | Swap used MiB min–max | Sampler wall ms p50/p95/p99/max |
|---|---|---|---|---|
| fixed | 25.00 / 46.00 / 60.00 / 87.00 | 36.61 / 206.69 / 461.33 / 671.90 | 29014.00–30826.62 | 39.05 / 54.58 / 130.76 / 285.55 |
| main | 33.00 / 46.00 / 61.00 / 70.00 | 14.80 / 99.15 / 175.40 / 272.44 | 29321.19–30056.62 | 41.63 / 56.53 / 83.56 / 145.45 |

A does not parse JSON: source timestamp, trade identity and source freshness are N/A, not fabricated. B has uncorrected source-age distributions from parsed exchange trade timestamps, not certified freshness. C/D use existing source offset/uncertainty and REST trade/book/candle reconciliation. bookTicker has **no exchange source timestamp**. Source age, provider-idle arrival gaps, REST end-to-end time and true network latency are distinct.

## Every residual rejection cluster

| UTC | Rejects | Max receipt→processing ms | Max overlapping independent W lag ms | Target PID pagein delta | OS bracket s |
|---|---:|---:|---:|---:|---:|
| 2026-10-27T15:30:39.667722+00:00 | 32 | 877.059 | 309.813 | 0 | 5.004 |
| 2026-10-27T15:38:27.578543+00:00 | 1 | 262.941 | 68.984 | 0 | 5.005 |
| 2026-10-27T15:43:34.641202+00:00 | 3 | 347.400 | 78.762 | 0 | 5.001 |

The witness retained its events without overwrites. It ran one connection throughout the fixed comparison/soak,614960 frames, no queue overflow; maximum timer lag401.795ms while receipt→processing maximum118.801ms. Application receipt is not kernel/socket arrival: a timer pause can occur before receipt is stamped and therefore need not appear as queue delay. Each slow D span and its witness/CPU/disk/pagein context is preserved in `slow-span-correlation.json`; overlap is not proof that the entire D wait has the same cause.

## Queue and timer distributions

Each cell is **p50 / p95 / p99 / max milliseconds**. These are per-process distributions, not averaged or falsely pooled percentiles. Samples retain the last20000 values; counts/max are lifetime. Full stage wall/thread-CPU/process-CPU distributions, counts and retained sizes are in `stage-quantiles.json`.

| Measurement/segment | Receipt→processing ms | Event-loop lateness ms |
|---|---|---|
| fixed_paired/01-A | 0.14 / 0.54 / 0.82 / 21.97 | 1.09 / 2.11 / 2.17 / 104.31 |
| fixed_paired/02-D | 1.15 / 4.11 / 9.81 / 38.98 | 1.06 / 2.56 / 11.21 / 56.37 |
| fixed_paired/03-D | 0.97 / 3.13 / 4.79 / 116.64 | 0.97 / 3.96 / 11.32 / 118.16 |
| fixed_paired/04-A | 0.18 / 0.56 / 0.83 / 156.77 | 0.96 / 1.16 / 1.89 / 169.71 |
| fixed_soak/soak-1 | 1.07 / 4.28 / 14.19 / 877.06 | 1.06 / 5.09 / 14.73 / 930.02 |
| fixed_soak/soak-2 | 1.01 / 3.73 / 8.96 / 236.79 | 1.85 / 4.04 / 13.38 / 229.62 |
| matrix/01-A | 0.12 / 0.67 / 2.83 / 6.13 | 1.41 / 2.14 / 2.21 / 12.15 |
| matrix/02-B | 0.21 / 0.97 / 1.60 / 15.76 | 1.52 / 2.13 / 2.19 / 22.13 |
| matrix/03-C | 0.39 / 2.40 / 3.45 / 19.15 | 1.43 / 2.13 / 2.22 / 44.91 |
| matrix/04-D | 1.01 / 7.38 / 23.82 / 30.09 | 1.75 / 2.47 / 11.55 / 34.38 |
| matrix/05-D | 1.25 / 13.32 / 33.92 / 38.44 | 1.74 / 2.45 / 9.76 / 50.32 |
| matrix/06-C | 0.57 / 4.94 / 13.80 / 20.02 | 1.50 / 2.13 / 2.29 / 31.62 |
| matrix/07-B | 0.30 / 2.10 / 3.58 / 20.71 | 1.45 / 2.13 / 2.21 / 22.36 |
| matrix/08-A | 0.23 / 1.07 / 1.47 / 5.26 | 1.45 / 2.12 / 2.18 / 12.37 |

### Full-runtime soak stage detail

Wall and CPU are separate; stage spans can overlap. Loop-probe intervals include intentional20ms sleep; reported event-loop lateness excludes it. Protection/active strategy timing is N/A while flat.

| Portion/stage | Wall ms p50/p95/p99/max | Thread CPU ms p50/p95/p99/max |
|---|---|---|
| soak-1/ws_decode | 0.00 / 0.02 / 0.04 / 42.43 | 0.00 / 0.02 / 0.04 / 0.88 |
| soak-1/feed_process | 0.01 / 0.06 / 0.12 / 41.83 | 0.01 / 0.05 / 0.09 / 0.76 |
| soak-1/certificate_hook | 0.06 / 0.32 / 0.57 / 181.36 | 0.06 / 0.28 / 0.48 / 6.35 |
| soak-1/owner_state_encode | 4.39 / 7.65 / 18.20 / 613.65 | 4.16 / 5.86 / 6.47 / 12.96 |
| soak-1/owner_snapshot_prepare | 8.16 / 12.59 / 26.05 / 670.88 | 7.76 / 9.69 / 10.60 / 17.21 |
| soak-1/critical_lock_wait | 0.00 / 0.00 / 0.00 / 0.01 | 0.00 / 0.00 / 0.00 / 0.01 |
| soak-1/critical_journal_save | 4.54 / 4.54 / 4.54 / 5.19 | 3.38 / 3.38 / 3.38 / 4.46 |
| soak-1/sqlite_checkpoint | 1.83 / 11.60 / 20.51 / 229.91 | 1.46 / 3.59 / 4.62 / 8.74 |
| soak-1/dashboard_snapshot | 6.85 / 9.19 / 18.37 / 39.26 | 6.70 / 7.90 / 8.45 / 9.56 |
| soak-1/dashboard_read | 8.85 / 13.00 / 25.06 / 248.37 | 8.42 / 10.94 / 11.93 / 28.93 |
| soak-1/filesystem_export | 39.05 / 62.28 / 122.79 / 292.06 | 36.76 / 48.72 / 65.27 / 74.72 |
| soak-1/observation_publish | 51.12 / 80.03 / 179.33 / 436.49 | 47.15 / 59.55 / 77.16 / 87.43 |
| soak-2/ws_decode | 0.00 / 0.03 / 0.04 / 16.99 | 0.00 / 0.03 / 0.04 / 0.18 |
| soak-2/feed_process | 0.01 / 0.06 / 0.09 / 48.17 | 0.01 / 0.06 / 0.09 / 0.98 |
| soak-2/certificate_hook | 0.07 / 0.33 / 0.56 / 213.06 | 0.07 / 0.31 / 0.53 / 3.31 |
| soak-2/owner_state_encode | 4.73 / 6.35 / 8.50 / 28.86 | 4.59 / 5.87 / 6.29 / 7.17 |
| soak-2/owner_snapshot_prepare | 8.33 / 10.61 / 15.02 / 55.34 | 8.12 / 9.54 / 10.06 / 10.96 |
| soak-2/critical_lock_wait | 0.00 / 0.00 / 0.00 / 0.00 | 0.00 / 0.00 / 0.00 / 0.00 |
| soak-2/critical_journal_save | 4.22 / 4.22 / 4.22 / 5.42 | 4.05 / 4.05 / 4.05 / 5.00 |
| soak-2/sqlite_checkpoint | 1.76 / 11.21 / 17.94 / 48.96 | 1.45 / 3.37 / 4.39 / 7.46 |
| soak-2/dashboard_snapshot | 6.92 / 8.25 / 13.02 / 67.19 | 6.82 / 7.78 / 8.27 / 27.48 |
| soak-2/dashboard_read | 9.04 / 11.68 / 14.11 / 50.97 | 8.78 / 11.21 / 11.76 / 22.75 |
| soak-2/filesystem_export | 40.04 / 49.91 / 67.64 / 273.43 | 38.48 / 44.00 / 50.95 / 60.17 |
| soak-2/observation_publish | 52.23 / 66.02 / 88.98 / 358.45 | 49.44 / 55.84 / 63.16 / 70.60 |

## One precise remaining discriminating test — not executed

If separately authorized, compare matched full-D against **noncritical owner-state export OFF**, keeping all critical AtomicJournal FULL commits, risk, guards and quote processing unchanged, with the same independent witness/probes. Trigger one external stack capture of the owned PID on a heartbeat delay>100ms. That separates working-set/export amplification from shared host scheduling and identifies a blocked stack; it is not a request to raise guards, reboot, close user apps or add more architecture. No further fix/experiment was run.

## Current processes and commands

- Dashboard: http://127.0.0.1:8767 — restored observerPID90258, normal full source including the fairness fix; same `data/binance-spot/paper.sqlite`, flat/spent1BUY/1SELL, cash999.76609237980375. Global readiness remains FAIL regardless of current certificate.
- Guarded forward collectorPID90259, models disabled, no order/account capability. It restarted after the measurements; initial256 native4h candles are warmup only. No newly observed forward4h close is claimed by this mission.
- **Resume only after stopping the existing process:** `./run-binance-paper.sh --report reports/binance-spot/stability-isolation/observer` . Do not use the old default/technical/v3 freeze or reset the journal.
- Forward command: `PYTHONPATH=src .venv/bin/python reports/binance-spot/forward-signals/recorder.py record` . Do not launch a duplicate.
- Exact focused verification before the fixed measurements: `PYTHONPATH=src .venv/bin/python -m pytest -q tests_local/test_binance_fairness.py reports/binance-spot/stability-isolation/test_sampler_v2.py reports/binance-spot/stability-isolation/test_isolation.py tests_local/test_binance_correlated.py tests_local/test_binance_stability.py tests_local/test_binance_spot.py` →36passed in0.94s.
- Analysis reproduction: `.venv/bin/python reports/binance-spot/stability-isolation/analyze.py` (post-measurement summaries only; does not restart or simulate orders). Measurement control scripts are historical execution recipes, **not safe replay commands against existing output folders**.

## Provenance and unchanged boundaries

- Original protocol: `ece0c805872a629e9ea82c4160341389b3c43c2593e78ad4655398b261e0a1f3`. Telemetry-only addendum: `4086fe8e6d387f52db1bb4c6654c36f5ef55e294e06ce2a02e629940906e7c6d`. Fairness addendum: `8d766bf263aa84b7dc2ca9b94fd4aa0b865f8d3f0c9a03344785ff0bccaec844`. Restored observer protocol: `c5a069c0a8618875ece74692dcec4b15931105fdcc2f2cca0e234c83c7f35167`.
- `protected-before.json` and `protected-after.json`:177/177 unchanged, including Databento paths, frozen financial/strategy/Risk code and actual model forecast caches. Only explicitly authorized production change is `src/mnq_local/binance_app.py` fairness helper/callsite/test-freeze path, with exact `fairness.diff` and `binance_app-before-fairness.py` backup.
- No broker/account/private HTTP/key operations; all Databento SDK/network/credentials untouched. Existing journal was not reset. No model inference, financial backtests, or tests during measurement windows.
- Skill resolution: **paths-injected**. Targeted fallback because CodeGraph not initialized and native gentle-ai facade/Git unavailable. Parent performed a scoped read-only review; no native authority receipt or commit is claimed. Rollback unit: helper/callsite/test-source entry plus its regression test; old source/freeze retained. Removing it would restore the demonstrated burst defect.
