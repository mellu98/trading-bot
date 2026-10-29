# Final pause isolation: cause NOT IDENTIFIED

## Decision
**FAIL** at unchanged250 ms processing/2 s freshness guards. Noncritical export/dashboard removal reduces measured overhead, but does not eliminate uncensored failures. No production optimization, threshold, queue, Risk, or durability change is justified by this single observational pair. All Timestral/model inference remained OFF.

## Actual separate A/B comparison
This is the ONE authorized missing-contrast opportunity, not a retry-to-PASS or pooled extension of failed ABBA. Fresh normal SDK metadata succeeded for both. Sequential A then B; different message/host-load windows are a confound. Capture-active intervals plus200 ms and any overlapping receipt→processing spans are excluded only from the explicitly uncensored column; raw failures remain.

| Mode | Connected s | Frames (rate/s) | Rejects raw / uncensored | Uncensored max ms | CPU % one core* | Peak RSS MiB |
|---|---:|---:|---:|---:|---:|---:|
| 01-A | 300.814 | 27296 (90.74) | 43 / 40 | 4001.491 | 17.95 | 68.73 |
| 02-B | 300.514 | 22701 (75.54) | 8 / 5 | 1112.105 | 5.96 | 52.73 |

*Lifetime process CPU includes startup/shutdown divided by connected exposure, not exact per-stage CPU. A17.95% vsB5.96% is descriptive. Both completed planned targets/return0, no I/O queue overflow. Neither is production-ready. B is not a deployable full-dashboard fix.

### Queue latency distributions
Raw all-frame quantiles are bounded last20000 samples; counts/max lifetime, including profiler perturbation. Uncensored all-frame p50/p95/p99 cannot be reconstructed because individual sub250 ms samples were not retained; explicitly NA, not silently inferred from rejects. The tail-only column covers uncensored >=250 ms rejection contexts, NOT all frames.

| Mode | Raw p50 / p95 / p99 / max ms | Uncensored rejected-tail p50 / p95 / p99 / max ms |
|---|---|---|
| 01-A | 2.317 / 30.705 / 103.017 / 4001.491 | 387.146 / 3947.521 / 3984.708 / 4001.491 |
| 02-B | 2.828 / 33.200 / 89.322 / 1112.105 | 1099.141 / 1111.740 / 1111.740 / 1112.105 |

### Stage wall quantiles, raw including capture
All stage CPU and complete stage quantiles are in results.json. These are wall times, not model latency or CPU-only costs. Flat protection/real economic strategy evaluation is NA; original hooks remain, no open-position exit was exercised.

| Mode / stage | Count | p50 / p95 / p99 / max ms |
|---|---:|---|
| 01-A / event_loop_lag | 12218 | 1.139 / 17.295 / 53.580 / 4010.749 |
| 01-A / queue_wait | 27296 | 2.317 / 30.705 / 103.017 / 4001.491 |
| 01-A / feed_process | 27296 | 0.025 / 0.157 / 0.521 / 90.134 |
| 01-A / certificate_hook | 27685 | 0.142 / 0.845 / 2.431 / 149.563 |
| 01-A / critical_lock_wait | 3 | 0.012 / 0.012 / 0.012 / 0.085 |
| 01-A / critical_journal_save | 3 | 27.397 / 27.397 / 27.397 / 93.681 |
| 01-A / sqlite_checkpoint | 282 | 5.129 / 60.404 / 194.373 / 480.786 |
| 01-A / observation_publish | 282 | 171.848 / 460.138 / 1157.401 / 4107.148 |
| 01-A / filesystem_export | 282 | 138.954 / 360.812 / 927.834 / 4066.861 |
| 01-A / dashboard_snapshot | 282 | 14.480 / 45.704 / 86.622 / 140.318 |
| 01-A / dashboard_read | 282 | 12.844 / 61.715 / 277.962 / 683.616 |
| 01-A / gc_gen0 | 1051 | 0.264 / 1.562 / 23.811 / 238.032 |
| 01-A / gc_gen1 | 95 | 0.733 / 3.618 / 20.277 / 39.662 |
| 01-A / gc_gen2 | 3 | 59.943 / 59.943 / 59.943 / 87.180 |
| 02-B / event_loop_lag | 13605 | 1.114 / 2.836 / 16.961 / 2100.154 |
| 02-B / queue_wait | 22701 | 2.828 / 33.200 / 89.322 / 1112.105 |
| 02-B / feed_process | 22701 | 0.029 / 0.199 / 0.692 / 1033.992 |
| 02-B / certificate_hook | 23182 | 0.184 / 0.988 / 3.110 / 123.714 |
| 02-B / critical_lock_wait | 3 | 0.011 / 0.011 / 0.011 / 0.012 |
| 02-B / critical_journal_save | 3 | 10.428 / 10.428 / 10.428 / 15.775 |
| 02-B / gc_gen0 | 11 | 0.837 / 2.007 / 2.007 / 2.853 |

| 01-A / owner_snapshot_prepare | 282 | 11.529 / 38.145 / 136.402 / 3437.948 |
| 01-A / owner_state_encode | 282 | 5.414 / 20.167 / 71.312 / 2547.453 |
| 01-A / owner_rest_encode | 212 | 0.067 / 3.205 / 13.371 / 108.353 |
| 01-A / ws_decode | 27296 | 0.007 / 0.055 / 0.161 / 40.466 |
| 01-A / ws_receive_wait_provider_idle_included | 27296 | 0.011 / 64.589 / 229.594 / 3959.962 |
| 01-A / io_queue_wait | 871 | 6.061 / 257.280 / 1179.671 / 4010.453 |
| 01-A / raw_write | 320 | 1.064 / 10.531 / 22.987 / 1588.477 |
| 01-A / rest_evidence_write | 212 | 0.189 / 6.488 / 8.788 / 18.494 |
| 01-A / consumer_iteration | 27685 | 0.231 / 1.449 / 11.502 / 3928.838 |
| 01-A / rest_compare_network_included | 54 | 1414.251 / 2603.256 / 3242.157 / 3296.277 |
| 02-B / owner_rest_encode | 211 | 0.083 / 3.339 / 5.471 / 20.072 |
| 02-B / ws_decode | 22701 | 0.007 / 0.070 / 0.238 / 21.413 |
| 02-B / ws_receive_wait_provider_idle_included | 22701 | 0.012 / 71.406 / 249.495 / 2107.061 |
| 02-B / io_queue_wait | 586 | 0.844 / 12.750 / 1519.629 / 3469.358 |
| 02-B / raw_write | 318 | 0.232 / 6.377 / 11.528 / 3468.754 |
| 02-B / rest_evidence_write | 211 | 0.336 / 7.941 / 89.143 / 1341.417 |
| 02-B / consumer_iteration | 23182 | 0.294 / 1.647 / 6.094 / 1092.067 |
| 02-B / rest_compare_network_included | 53 | 1537.199 / 2293.419 / 2386.932 / 3928.424 |

## Actual stacks and attribution
- Original corrected A1: Python filemtime precedes owner heartbeat resume by84.929 ms (first externally observed bytes precede resume69.370 ms). Snapshot main: json.encoder→ObservedJournal.capture:127→enqueue_observation:154. Worker queue.wait at that instant. This identifies a synchronous owner pause LOCATION, not CPU/GIL/VM/IO causation.
- Native corrected A1 sampling started1133.730 ms AFTER owner resume. POSTPAUSE: predominant kevent/take_gil frames are not cause evidence. Calibration73.5 ms onset is not actual target onset.
- Separate opportunity A: Python main asyncio queue.get/wait_for consumer; worker atomic_json→publish. Native onset46.706 ms AFTER owner resume: POSTPAUSE. Python delivered~797.257 ms before owner resume, but one location cannot distinguish scheduling/GIL/IO.
- Separate B: Python main RiskState.__post_init__ through SpotRuntime._mark_risk (dataclass validation, NOT Timestral inference); worker queue.wait. Python mtime7.126 ms before owner resume. Native began~101.384 ms BEFORE owner resumed, but its1 s aggregate has no per-frame timestamps and is mostly postresume (84/90 main samples kevent). Partial overlap, not proof kevent/GIL caused initial pause.
- The external probe itself can be scheduled late. Record requests, filemtime/first observation, native Date/Time, heartbeat resume, and entire tool-active+200ms windows in results.json. The profiler perturbs execution; no PASS is manufactured by censoring.

## Independent witness, failures, and host
Original corrected ABBA A connected273.471 s then original noncritical16-job I/O queue overflow/failclosed. Other B/B/A attempts had transient fresh exchangeInfo10 s startup timeouts, zero WS exposure, no retries. This is distinct from the already-fixed512-frame receive fairness overflow. Capture ended~220 s before A failed; fatal queue event is not inside its censor window. Calibration17 s A failure occurred with profiling active and is NOT pooled.

Original corrected W:321.854 connected s,23584 frames,73 >=250 ms delays. ALL six delay clusters and16 >=250 ms loop-stall spans are outside the single capture window. Thus local timing disturbances are not solely profiler artifacts. Separate-pair W:609.967 connected s,50717 frames,4 delays, all rejection clusters outside tool-active windows; raw7 loop>=250 ms,5 outside windows. W is raw/noJSON: source age/freshness NA. WS reachability is not latency certification.

Per-rejection-cluster receipt span, independent W overlapping loop events, capture overlap, and nearest5 s OS sample are in results.json. A4 s queue span overlaps W max571.982 ms; B uncensored1112.105 ms queue span overlaps W87.324 ms (not a matching-duration common pause). These distinguish host-common components from D-only delays but do not uniquely identify scheduler/GIL/filesystem.

Pair host true5 s interval statistics: system user [15.0, 51.0], system [17.0, 64.0]%; first-disk MB/s [47.08, 443.58]; load1 range [23.958984375, 58.77783203125]. First iostat uptime row excluded. Physical/virtual disks not summed. Sampler ownCPU 2.67% one core; sampler children inclnative/OScommands 1.50%. Low-overhead is measured, not zero-overhead.

Global host VM counter deltas (not PID attribution), original ABBA: {'Pageins': 312731, 'Pageouts': 5579, 'Swapins': 1248847, 'Swapouts': 1314258}; separate pair: {'Pageins': 1316536, 'Pageouts': 14412, 'Swapins': 2181102, 'Swapouts': 2367603}. VM pages are16384 bytes. These support observed host VM activity only, not exact pause causality.

Read-only host-before/after preserve16 GiB physical RAM, rawpressure2, compressor/VM/pagein/out/swap counters, energy settings/assertions, disk and selected basenames/PID/RSS/decayedCPU only. After: swap22243.38 MiB used/23552 total; disk97% used/13394628 KiB free. These are resource conditions, NOT proof16 GiB is insufficient or disk/VM caused a pause. No process was killed, OS setting changed, or reboot performed.

Largest current basenames (observed snapshots, not attribution):
- com.apple.Virtualization.VirtualMachine: PID69488, RSS445584 KiB, decayedCPU77.1%.
- deleted: PID80853, RSS24192 KiB, decayedCPU51.2%.
- WindowServer: PID172, RSS43600 KiB, decayedCPU49.4%.
- Google Chrome Helper: PID80613, RSS82560 KiB, decayedCPU29.9%.

Energy: recorded pmset AC/battery settings/assertions; no verified sleep/AppNap causal event. AppNap status remains NOT_VERIFIED. Only configured execution host Local(local). Parent's subsequent read-only Docker inventory found the existing local `desktop-linux` context: Docker Desktop/Linux,10 vCPUs,12528381952 bytes VM memory capacity and7 running containers. Capacity is not measured memory consumption. This VM shares the same Mac; no isolated non-production research environment or independent hardware baseline was verified. No container was started, stopped, inspected for secrets or used for execution; no SSH probing, new service or hardware-purchase justification.

## 4h correctness and safety
5 actual native4h REST warmup responses, each256 complete contiguous UTC bars; forming excluded;0 observed OHLCV revisions;0 recorded forward gaps;0 actual NEW4h decisions. Repeated warmup overlap is not forward duplicate bars. **NOT_VERIFIED_REAL_FORWARD**: no actual new4h decision/availability/quote-age causal chain was exercised; synthetic gap/future/duplicate tests are not forward validation.
Runtime uses native1m x=true for ready bars; book has NO source timestamp. Source trade age includes actual clock offset/uncertainty and is not transport latency. A lastRESTclock uncertainty185.658 ms/B148.141 ms. A gap3 with1unrepairable, B gap3; original reconnect/certification logic remained failclosed. Collector polls REST, so WS reconnect semantics do not apply to collector. Every restart bootstrap is warmup only.

Collector stays actionable=false with STABILITY_READINESS_BLOCKED/strict-news/no order capability even if instantaneous feed certificate is true. Economic frozen4h rules unchanged, Timestral disabled. Current forward collection is raw observation, not financial forward validation.

## Tests, recovery, immutability
- Original prefreeze suite:27PASS1.35 s; identical later command26PASS1FAIL14.59 s, existing timing assertion .7579718 s>.15 despite20 callbacks. BOTH verbatim outcomes/provenance preserved; no claim consistently green.
- Additive target-reader/faulthandler and synthetic criticalFULL/gap tests7PASS0.10 s. Opportunity configuration RED FileNotFoundError then8focusedPASS1.43 s. No tests/models/backtests during recording.
- Apparatus race fixed ONLY in additive targets-v2/control-v2/external-v2: atomic replace + retain lastvalid + external-death failclosed. No production patch this mission.
-179 protected path hashes unchanged including ALL Databento, financial Runtime/Risk, frozen strategies/model caches/results. Readonly journal integrityOK; flat/spent,1BUY/1SELL, cash999.76609237980375. No new trades, order HTTP, private API, credentials, or Databento calls. CriticalFULL actual temporary-fixture proof retained; current flat restoration is not a new open-position recovery test.

## Minimum next intervention
ONE manually supervised host-cleanup/restart control on the same machine, only after user authorization and without buying hardware: record resource baseline, then repeat ONLY B300 s+same W at original guards. This discriminates persistent host condition from residual runtime work better than another identical long soak. It remains a proposed test, not performed or guaranteed to PASS. The existing Docker VM is not an independently verified comparison host and contains7 active containers whose workloads must not be disrupted.

## Current processes and reproduction
Executor check in `current-health.json` recorded observer79678/forward79679 and dashboardHTTP200 at that earlier timestamp. **Latest parent check supersedes that operational status:** observer79678 subsequently stopped with `bounded_observation_queue_overflow` → `public_consumer_failed_closed`; localhost8767 now refuses connections. It was NOT automatically restarted into another known-failing loop. Forward79679 remains alive in SIGNALS_ONLY_NON_ACTIONABLE with globalFAIL and zero new4h closes. Read-only journal quick_check remains OK, flat/spent1BUY/1SELL/cash999.76609237980375. See `parent-check.json` for the newer timestamp, health and Docker inventory. Earlier captured health/results remain historical evidence, not an uptime guarantee.

```sh
cd "/Users/locoframe/Desktop/TRADING BOT"
# Analysis only (does not start clients or touch financial state):
PYTHONPATH=src .venv/bin/python reports/binance-spot/pause-ab/analyze.py
# Exact safe observer resume ONLY if existing own observer is stopped; same spent default journal:
./run-binance-paper.sh --report reports/binance-spot/pause-ab/opportunity/observer
# Frozen one-shot measurement command is recorded for reproducibility, NOT authorization for another run:
PYTHONPATH=src .venv/bin/python reports/binance-spot/pause-ab/control-opportunity.py
```

Bare run-binance-paper.sh uses older frozen technical report and will reject current app. Do NOT use --freeze or reset journal. Do not start a duplicate server.

Artifacts: results.json (fullquantiles/CPU/GC/SQLite/cluster correlation), current-health.json, host-before.json, host-after.json, four-hour-audit.json, protected-before.json; main/live is corrected failedABBA; opportunity/live is separate completedAB. Original live is calibration only. Native/Python raw stacks and rawREST/WS evidence retained.

Freeze: originalprotocol ed848ba50071b2d0c56031936b7e7a127128457b2fb70c8d2385c80fa651d1b8; correction8e14c72c79183bfd5d5edb259d42f58800ed56d2cdf9158005b9ae0b0fe9ea8d; opportunitycb70242fe83306067190888058b6dbf3eb0013b1b234ce660e518c995c68e544. Nativegentle-ai receipt unavailable/noGit; parent scoped read-only review, no inventedauthority. skill_resolution: paths-injected.


## 2026-10-28 — Post-reboot B-only control

**Local processing: PASS for this finite window. Overall original250 ms /2 s criteria: FAIL.** No repeat was run: the predeclared first-run freshness condition failed. No complete observer, dashboard, forward collector or model was started/restored. This section supersedes all earlier *current process* claims; those refer to October27.

### Reboot and unchanged boundaries
Boot verified **2026-10-28T00:22:54+01:00**. At preflight uptime was~8 h, load1.12/1.33/1.39, memory-pressure code1 (previously2), and swap0 MiB. During the measurement swap remained0, swap-in/out deltas both0; load1 ranged1.46–2.61. Physical RAM remains16 GiB. Different market/time/traffic and host state mean this is association, not unique proof that reboot or swap caused the old pauses. No service or container-management command was issued; the seven pre-existing containers were not altered or queried through their daemon.

Runtime, strategy, all179 protected files (including Databento), original250 ms/2 s guards,512-frame receive capacity,16-job proof worker and transactional FULL journal were unchanged. Existing B disables only noncritical state copies/publication/dashboard. Journal remains integrityOK, flat/spent1BUY/1SELL, cash999.76609237980375USDT. No real/private order endpoint or credential was used.

### Complete real measurement
Fixed window: **2026-10-28T08:36:50.642786+01:00 → 2026-10-28T08:41:50.741205+01:00**, equivalently **2026-10-28T07:36:50.642786+00:00 → 2026-10-28T07:41:50.741205+00:00**. Conservative observed connected duration B300.098s; independent raw witness300.683s. Startup/cleanup and raw-proof flush grace are not counted. No native profiler or SIGUSR2 dump was triggered: all times are uncensored.

| Metric | Previous B | Post-reboot B |
|---|---:|---:|
| Processing rejects over250 ms | 5 outside profiler (8 raw) | **0** |
| Receipt→processing maximum | 1112.105 ms outside profiler | **5.345 ms** lifetime |
| Queue p50 / p95 / p99 | 2.828 /33.200 /89.322 ms raw | 0.698 /2.791 /3.849 ms |
| Event-loop maximum | Raw previous2.100s includes profiler, not comparable | **29.864 ms** |
| CPU percent of one core | 5.96% | **2.697%** |
| Peak RSS | 52.73 MiB | **60.83 MiB** |
| Frames / second | 75.54 | 36.48 |

CPU is lifetime process CPU (startup/shutdown included) divided by observed connected duration. Traffic is roughly half the old run: CPU/1000 frames is0.739s versus0.789s, so lower absolute CPU is not evidence of an optimization. All10949 local queue samples fit within the20000 bound in this run; counts/max are lifetime and include the short startup/cleanup observations.

Witness:10971 received=10971 processed,0>=250 ms, maximum queue1.151 ms and loop29.951 ms. B:10949 received=10949 feed_process calls,0 receive/I/O overflows,0 unexpected disconnects,0 ring overwrites,0 forced kills; all three diagnostic children returned0.61 OS samples and60 valid five-second iostat interval rows retained, first uptime-average row discarded, no sampler errors,0 captures. No dashboard listener on8767 before/after.

Measurement-window raw integrity is complete:10940 valid JSON lines cover a FIFO prefix extending past the fixed window end, including10882 rows inside it. **Nine received shutdown suffix frames were not persisted after the window**; this existing shutdown-tail behavior is disclosed, not fixed or hidden. No receive overflow occurred; the missing FIFO suffix is strictly beyond the covered window. Recorded2647 trade IDs are contiguous with0 internal gaps. No measurement-window loss is claimed from the old persistent-ID gap.

### Why the unchanged2-second checks still fail
After each component first initialized, quarter-second observations recorded **13 book-stale and67 trade-stale samples**;13 earlier startup samples were UNKNOWN, not silently fresh. These are sampled guard outcomes, not proof of continuous freshness between samples. BookTicker has no source E/T timestamp; book receipt freshness is not transport latency. Maximum book interreceipt silence was4914.321 ms; another2121.049 ms silence contained a REST snapshot with the same before/after bid/ask. This is compatible with quiet/change-only updates, not proof the price was continuously unchanged. Guards remain unchanged and block admission.

Existing source timestamp ages also need care:56 REST clock checks had RTT239.7–3994.0 ms and midpoint offset−318.1..1981.9 ms. The final certificate's6.210s maximum source age is **not** an isolated network-latency measurement. Maximum newly received trade receipt−T was4228.002ms *uncorrected*; E−T for the worst examples was0–1ms. Both aging of the last quote during silence and newly received old events can contribute; no transport/provider cause is assumed.

Offline-only same-event evidence from the already collected records: **40 trades were present in a fully parsed REST response before WS receipt**,38 by>250ms, maximum **1436.593ms**. ID, Decimal price, Decimal quantity and T match exactly. This uses the actual `response_received_mono_ns` recorded **after** `await response.json()` and the raw WS `received_mono_ns`, on the same host monotonic clock, with no wall-clock reconstruction. It establishes relative availability in this run, not universal provider or network latency. Exact40 pairs and provenance are in `reboot-20261028/results.json`.

The original failclosed startup gap remains: persisted ID6796028095 versus first new recorded ID6796855216 (difference827121), with0 internal raw trade gaps. No IDs or recovery rules were reset. This cross-day/restart gap and uncertified news keep operational readiness BLOCKED even if an instantaneous source check later passes. No new4h strategy decision or order was exercised.

### Decision and minimum next experiment
- Measurement integrity: PASS within the explicitly covered300-second window, with the disclosed shutdown suffix.
- Local receipt→processing and event-loop250 ms timing: PASS **only for this window**; repeatability not tested because the2-second requirement failed.
- Source freshness / overall readiness: FAIL / BLOCKED. Neither an economic strategy nor autonomous trading is approved.
- Next minimum discriminating experiment, **not run now**: retain same-event trade IDs/E/T and monotonic receipt on *both* independent WS clients plus the existing REST snapshots in one bounded observation window. That distinguishes per-connection arrival from a shared relay/network effect; it is not another identical runtime soak or a new provider. Also keep restart gap recovery separate; do not bypass it.

No clients, full observer, forward collector or dashboard remain running from this finite test. No hardware/service purchase, Docker operation, runtime patch or new strategy. Reproduction is intentionally one-shot: the finite controller refuses to overwrite run folders. Analysis-only reproduction (no market calls):

```sh
PYTHONPATH=src .venv/bin/python reports/binance-spot/pause-ab/reboot-20261028/analyze.py
```

Protocol SHA256: a3bc01ef0eb583e92ffbad86260eebaf2140d3251f88789bc701f6f186e61e6c. Four synthetic controller tests passed before recording; no tests/models/backtests ran during the window. Exact times, raw data, metric distributions, telemetry, proof counters and SHA checks are retained under `reboot-20261028/`. Native authority/Git tooling was unavailable; no authority receipt or commit is claimed. Skill resolution: paths-injected.
