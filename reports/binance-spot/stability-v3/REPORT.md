# Stability-v3: bounded correlated observation; actionability remains blocked

Actual620.160s,602samples, plannedflat restart45907→46903,0HTTPerrors.35processing-delay rejections in one206.979s cluster;0in second process.0queue overflow.415/602certificate samples valid(68.94%); sampling is not proof of continuous certification. Trade-gap observations2+1 are distinct from queue drops. No tests, model inference, backtests or strategy jobs ran during this window. No guard was relaxed.

**Global stability: FAIL/BLOCKED.** A current `certificate.passed=true` is only the current connection’s instantaneous feed checks; it is NOT620s stability certification. The forward collector hardcodes `STABILITY_READINESS_BLOCKED` and `actionable=false` regardless of that instantaneous value. Its bounded operational status is persisted separately in `data/binance-spot/forward-signals/operational-status.json`.

## What the new evidence establishes

- First queue rejection:259.621ms since application receipt, max277.030ms. Overlapping feed processing consumed97.118ms wall but0.186ms owner-thread CPU/1.039ms whole-process CPU. Overlapping worker filesystem export consumed1249.128ms wall/75.837ms thread CPU. Loop probe interval783.223ms wall includes20ms intentional sleep; measured scheduling lag763.218ms.
- No GC or critical save overlaps this reject cluster; no telemetry-ring overwrite. Critical writes did not cause this first cluster. Separate actual GCgen2 maxima49.626ms/36.915ms and criticalsave8.017ms/6.502ms are measured, not retroactive explanations.
- This proves local application waiting rather than CPU-saturated JSON in the measured owner interval. It does NOT uniquely distinguish OS preemption/page fault, filesystem wait or all GIL effects. Worker I/O overlap is correlation, not proof it caused the queue stall. Original22rejects lack this telemetry and remain unattributed.
- System-wide OS counters show active paging during this quiet control, not merely occupied swap. Swapused27495.56–30064.56MiB; botRSS37424–63904KiB. Over the measured host span:253914pageins/5103pageouts,1568702swapins/1674672swapouts with16384byte pages. These counters include other applications, NOT bot-only faults.
- The5.0613s sample bracket around the rejection (exact interval inanalysis.json) records paging/load context; this cannot assign an individual fault to this process. No app was closed or OS setting changed.

## Changes and verification

64focusedtestsPASS before soak, with RED proof for new timing/GC/host and dedicated-key regressions. Receipt is stamped before decoding/instrumentation. Correlated stage wall/threadCPU/processCPU and GC events are bounded; OS probes run only in existing I/O worker. State ownership, criticalFULLdurability,250msprocessing/2sfreshness and original Risk remain unchanged.132protectedfinancialsource/protocol/result/cache paths match before/after. No financial execution or model source was modified.

Dedicated Databento live service eliminates generic Historical/env fallback; owner/grant/digest checks still precede connection. No key/SDK/Databento network was accessed. SeeINTERFACES.md for safe future configuration and10minute command. NoGit/gentlefacade: no commit or native authority receipt claimed.

## Operating status and exact commands

- Dashboard:http://127.0.0.1:8767 — observerPID46903, samepaper.sqlite, flat/spent1BUY1SELL; cash999.76609237980375USDT. RawquotesRUNNING; actionable strategyBLOCKED. Original successful technical roundtrip is not erased by failedstabilityreadiness.
- Resume ONLY after stopping that observer, withoutreset/freeze: `./run-binance-paper.sh --report reports/binance-spot/stability-v3` . Baredefaultlauncher usesoldertechnicalfreeze and must not be used for this source.
- Baseline-only forward collectorPID48288: `PYTHONPATH=src .venv/bin/python reports/binance-spot/forward-signals/recorder.py record` . Started AFTERsoak; no model/account/order engine. Initial256nativeclosed4hbars arewarmup only, latestend12:00Z; nextnew4hclose16:00Z. Allsignals log actionable=false withstability/news/noorder rejections. No maturefutureoutcome or newforward signal is claimed now.
- Reproduce focused tests: `PYTHONPATH=src:tests_local:adapters/databento_planner/src .venv/bin/python -m pytest -q reports/binance-spot/forward-signals/test_recorder.py tests_local/test_databento_live_key.py tests_local/test_databento_cli.py tests_local/test_databento_live.py tests_local/test_binance_correlated.py tests_local/test_binance_stability.py tests_local/test_binance_spot.py` .

## Stage distributions

Milliseconds. Each process lifetime includes startup shortly before controller window; rollinglast20000 samples, count/maxlifetime. CPU suffixes are measured thread/whole-process CPU, NOT wall. `ws_receive_wait_provider_idle_included` includes provider silence; not networklatency. `rest_compare_network_included` is end-to-end REST workload, not isolatednetwork. Flat observation did not execute the protection hook; protection and active strategy workload are N/A. Rawsourceeventage versus localreceipt is distinct from networklatency; booksource timestamp unavailable.

### after_restart

| Stage | count | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| certificate_hook | 19817 | 0.073084 | 0.448042 | 0.680583 | 53.560167 |
| certificate_hook.process_cpu | 19817 | 0.072000 | 0.415000 | 0.573000 | 6.081000 |
| certificate_hook.thread_cpu | 19817 | 0.072125 | 0.412583 | 0.568250 | 3.523625 |
| consumer_iteration | 19817 | 0.119625 | 0.688792 | 8.535375 | 157.504542 |
| critical_journal_save | 3 | 4.093625 | 4.093625 | 4.093625 | 6.501584 |
| critical_journal_save.process_cpu | 3 | 4.076000 | 4.076000 | 4.076000 | 5.260000 |
| critical_journal_save.thread_cpu | 3 | 4.074042 | 4.074042 | 4.074042 | 5.256000 |
| critical_lock_wait | 3 | 0.006458 | 0.006458 | 0.006458 | 0.008500 |
| critical_lock_wait.process_cpu | 3 | 0.007000 | 0.007000 | 0.007000 | 0.008000 |
| critical_lock_wait.thread_cpu | 3 | 0.006000 | 0.006000 | 0.006000 | 0.007542 |
| dashboard_read | 307 | 8.236709 | 11.198208 | 17.149708 | 49.326625 |
| dashboard_read.process_cpu | 307 | 7.915000 | 9.606000 | 10.757000 | 30.596000 |
| dashboard_read.thread_cpu | 307 | 7.859250 | 9.483291 | 10.509709 | 30.351625 |
| dashboard_snapshot | 301 | 6.791083 | 10.420042 | 22.710084 | 33.423041 |
| dashboard_snapshot.process_cpu | 301 | 6.607000 | 7.717000 | 8.856000 | 26.829000 |
| dashboard_snapshot.thread_cpu | 301 | 6.579084 | 7.660375 | 8.518250 | 26.762291 |
| event_loop_lag | 14853 | 1.080541 | 2.246667 | 11.574541 | 280.514000 |
| feed_process | 19363 | 0.016917 | 0.093167 | 0.173042 | 22.154416 |
| feed_process.process_cpu | 19363 | 0.017000 | 0.088000 | 0.124000 | 1.013000 |
| feed_process.thread_cpu | 19363 | 0.016708 | 0.086375 | 0.120667 | 0.464167 |
| filesystem_export | 300 | 27.617334 | 50.480791 | 100.663333 | 143.372459 |
| filesystem_export.process_cpu | 300 | 25.292000 | 44.268000 | 58.136000 | 63.818000 |
| filesystem_export.thread_cpu | 300 | 24.700875 | 42.626209 | 54.617041 | 60.031959 |
| gc_gen0 | 1130 | 0.116792 | 0.325041 | 0.589042 | 4.447250 |
| gc_gen0.process_cpu | 1130 | 0.114000 | 0.303000 | 0.422000 | 0.661000 |
| gc_gen0.thread_cpu | 1130 | 0.111750 | 0.295459 | 0.409000 | 0.549791 |
| gc_gen1 | 102 | 0.295166 | 0.885292 | 1.209333 | 3.318583 |
| gc_gen1.process_cpu | 102 | 0.288000 | 0.582000 | 0.723000 | 2.617000 |
| gc_gen1.thread_cpu | 102 | 0.287375 | 0.579375 | 0.716583 | 2.613750 |
| gc_gen2 | 3 | 30.806041 | 30.806041 | 30.806041 | 36.914792 |
| gc_gen2.process_cpu | 3 | 22.510000 | 22.510000 | 22.510000 | 25.231000 |
| gc_gen2.thread_cpu | 3 | 22.447083 | 22.447083 | 22.447083 | 24.988417 |
| host_os_sample | 60 | 20.613041 | 33.989708 | 36.233084 | 36.286208 |
| host_os_sample.process_cpu | 60 | 8.353000 | 16.908000 | 20.141000 | 21.567000 |
| host_os_sample.thread_cpu | 60 | 7.434500 | 10.402708 | 11.529000 | 12.637666 |
| io_queue_wait | 914 | 2.057375 | 32.739958 | 57.524375 | 184.721666 |
| loop_probe_interval | 20 | 60.344000 | 181.565666 | 181.565666 | 300.534292 |
| loop_probe_interval.process_cpu | 20 | 6.760000 | 34.755000 | 34.755000 | 35.014000 |
| loop_probe_interval.thread_cpu | 20 | 1.175041 | 10.720125 | 10.720125 | 14.151292 |
| observation_publish | 300 | 39.844125 | 69.157875 | 121.234917 | 223.078583 |
| observation_publish.process_cpu | 300 | 36.245000 | 58.707000 | 69.429000 | 77.357000 |
| observation_publish.thread_cpu | 300 | 34.975250 | 54.619625 | 66.863500 | 73.597292 |
| owner_rest_encode | 234 | 0.050584 | 2.232208 | 4.236583 | 9.666500 |
| owner_rest_encode.process_cpu | 234 | 0.048000 | 1.987000 | 2.245000 | 2.889000 |
| owner_rest_encode.thread_cpu | 234 | 0.047500 | 1.984417 | 2.240209 | 2.886708 |
| owner_snapshot_prepare | 301 | 8.051959 | 12.568709 | 24.294750 | 140.573250 |
| owner_snapshot_prepare.process_cpu | 301 | 7.572000 | 9.561000 | 10.789000 | 11.348000 |
| owner_snapshot_prepare.thread_cpu | 301 | 7.413458 | 9.285250 | 10.587959 | 10.998792 |
| owner_state_encode | 301 | 4.224792 | 7.519125 | 9.823000 | 38.334208 |
| owner_state_encode.process_cpu | 301 | 3.912000 | 5.662000 | 6.135000 | 6.919000 |
| owner_state_encode.thread_cpu | 301 | 3.892583 | 5.544667 | 6.013875 | 6.645292 |
| queue_wait | 19363 | 0.644833 | 7.035666 | 12.985125 | 73.148333 |
| raw_write | 319 | 0.299083 | 4.851791 | 7.572083 | 25.617250 |
| raw_write.process_cpu | 319 | 0.323000 | 4.054000 | 5.080000 | 7.817000 |
| raw_write.thread_cpu | 319 | 0.106417 | 0.210542 | 0.264625 | 0.355458 |
| rest_compare_network_included | 60 | 1120.075541 | 1486.223625 | 2243.538083 | 6882.818833 |
| rest_evidence_write | 234 | 0.097125 | 0.757042 | 4.817292 | 11.389708 |
| rest_evidence_write.process_cpu | 234 | 0.109000 | 0.569000 | 1.063000 | 11.696000 |
| rest_evidence_write.thread_cpu | 234 | 0.077041 | 0.200625 | 0.246291 | 0.290167 |
| sqlite_checkpoint | 301 | 1.913375 | 13.007042 | 18.437500 | 41.213333 |
| sqlite_checkpoint.process_cpu | 301 | 1.898000 | 6.123000 | 12.757000 | 14.091000 |
| sqlite_checkpoint.thread_cpu | 301 | 1.643792 | 3.792125 | 5.942958 | 6.762708 |
| ws_decode | 19363 | 0.006834 | 0.044459 | 0.074417 | 8.130166 |
| ws_decode.process_cpu | 19363 | 0.007000 | 0.043000 | 0.061000 | 0.695000 |
| ws_decode.thread_cpu | 19363 | 0.006667 | 0.040791 | 0.056708 | 0.690042 |
| ws_receive_wait_provider_idle_included | 19363 | 0.012375 | 79.668583 | 280.946042 | 1393.930541 |

### before_restart

| Stage | count | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| certificate_hook | 23891 | 0.072000 | 0.474959 | 0.786583 | 73.759833 |
| certificate_hook.process_cpu | 23891 | 0.071000 | 0.437000 | 0.605000 | 7.780000 |
| certificate_hook.thread_cpu | 23891 | 0.070792 | 0.434042 | 0.600542 | 2.238875 |
| consumer_iteration | 23891 | 0.109917 | 0.713500 | 7.924167 | 157.049250 |
| critical_journal_save | 3 | 5.035416 | 5.035416 | 5.035416 | 8.016917 |
| critical_journal_save.process_cpu | 3 | 3.372000 | 3.372000 | 3.372000 | 3.914000 |
| critical_journal_save.thread_cpu | 3 | 3.369250 | 3.369250 | 3.369250 | 3.911084 |
| critical_lock_wait | 3 | 0.005833 | 0.005833 | 0.005833 | 0.006333 |
| critical_lock_wait.process_cpu | 3 | 0.005000 | 0.005000 | 0.005000 | 0.007000 |
| critical_lock_wait.thread_cpu | 3 | 0.005167 | 0.005167 | 0.005167 | 0.005667 |
| dashboard_read | 295 | 8.092000 | 14.307458 | 38.792833 | 56.571667 |
| dashboard_read.process_cpu | 295 | 7.701000 | 9.924000 | 19.194000 | 33.869000 |
| dashboard_read.thread_cpu | 295 | 7.576375 | 9.864583 | 11.351458 | 33.685792 |
| dashboard_snapshot | 286 | 6.584334 | 9.092209 | 14.100042 | 167.188375 |
| dashboard_snapshot.process_cpu | 286 | 6.440000 | 7.704000 | 8.233000 | 9.898000 |
| dashboard_snapshot.thread_cpu | 286 | 6.399542 | 7.666000 | 8.168125 | 9.009958 |
| event_loop_lag | 14037 | 1.078750 | 2.682583 | 13.114917 | 763.218041 |
| feed_process | 23528 | 0.013375 | 0.089459 | 0.179333 | 97.118416 |
| feed_process.process_cpu | 23528 | 0.013000 | 0.082000 | 0.120000 | 4.111000 |
| feed_process.thread_cpu | 23528 | 0.013208 | 0.080125 | 0.117083 | 0.299042 |
| filesystem_export | 285 | 32.448750 | 59.487750 | 166.901584 | 1249.128333 |
| filesystem_export.process_cpu | 285 | 31.074000 | 48.612000 | 72.983000 | 233.195000 |
| filesystem_export.thread_cpu | 285 | 30.346875 | 46.874583 | 64.526208 | 75.837459 |
| gc_gen0 | 1076 | 0.106000 | 0.361458 | 0.772250 | 2.887167 |
| gc_gen0.process_cpu | 1076 | 0.104000 | 0.325000 | 0.465000 | 1.385000 |
| gc_gen0.thread_cpu | 1076 | 0.102791 | 0.320542 | 0.427958 | 1.383083 |
| gc_gen1 | 97 | 0.312875 | 0.809875 | 1.125125 | 5.328250 |
| gc_gen1.process_cpu | 97 | 0.307000 | 0.595000 | 0.936000 | 4.441000 |
| gc_gen1.thread_cpu | 97 | 0.304875 | 0.576000 | 0.932917 | 4.438584 |
| gc_gen2 | 3 | 36.180833 | 36.180833 | 36.180833 | 49.625542 |
| gc_gen2.process_cpu | 3 | 20.878000 | 20.878000 | 20.878000 | 26.960000 |
| gc_gen2.thread_cpu | 3 | 20.735167 | 20.735167 | 20.735167 | 26.776042 |
| host_os_sample | 57 | 20.528167 | 35.317167 | 52.002208 | 106.345750 |
| host_os_sample.process_cpu | 57 | 8.913000 | 15.317000 | 16.187000 | 16.653000 |
| host_os_sample.thread_cpu | 57 | 7.361500 | 12.683208 | 13.777083 | 13.969375 |
| io_queue_wait | 874 | 2.801708 | 40.686459 | 64.276125 | 504.760000 |
| loop_probe_interval | 32 | 58.231958 | 95.213625 | 244.586834 | 783.223166 |
| loop_probe_interval.process_cpu | 32 | 10.356000 | 36.341000 | 36.492000 | 139.941000 |
| loop_probe_interval.thread_cpu | 32 | 1.984000 | 14.171458 | 33.835375 | 110.722333 |
| observation_publish | 285 | 43.700416 | 78.455083 | 213.141375 | 1435.173125 |
| observation_publish.process_cpu | 285 | 41.817000 | 62.943000 | 84.883000 | 250.543000 |
| observation_publish.thread_cpu | 285 | 40.099083 | 58.740125 | 75.794125 | 91.488666 |
| owner_rest_encode | 217 | 0.047083 | 1.926833 | 2.207625 | 2.781250 |
| owner_rest_encode.process_cpu | 217 | 0.047000 | 1.871000 | 2.025000 | 2.777000 |
| owner_rest_encode.thread_cpu | 217 | 0.045125 | 1.869625 | 2.024375 | 2.775958 |
| owner_snapshot_prepare | 286 | 8.024458 | 11.816416 | 17.498458 | 25.991292 |
| owner_snapshot_prepare.process_cpu | 286 | 7.597000 | 9.798000 | 10.558000 | 10.956000 |
| owner_snapshot_prepare.thread_cpu | 286 | 7.467500 | 9.486958 | 10.267500 | 10.725375 |
| owner_state_encode | 286 | 4.083583 | 6.696542 | 11.130166 | 15.976875 |
| owner_state_encode.process_cpu | 286 | 3.844000 | 5.432000 | 6.206000 | 6.665000 |
| owner_state_encode.thread_cpu | 286 | 3.838583 | 5.348958 | 6.035875 | 6.509333 |
| queue_wait | 23528 | 0.953958 | 15.427625 | 133.405542 | 277.030000 |
| raw_write | 314 | 0.272959 | 4.763625 | 6.214167 | 7.720375 |
| raw_write.process_cpu | 314 | 0.323000 | 4.278000 | 4.885000 | 5.876000 |
| raw_write.thread_cpu | 314 | 0.096375 | 0.213125 | 0.312250 | 0.483084 |
| rest_compare_network_included | 56 | 1161.780916 | 2141.661583 | 2507.526375 | 2667.544375 |
| rest_evidence_write | 217 | 0.100542 | 1.163041 | 5.400167 | 179.683542 |
| rest_evidence_write.process_cpu | 217 | 0.108000 | 0.792000 | 2.518000 | 7.341000 |
| rest_evidence_write.thread_cpu | 217 | 0.081292 | 0.227000 | 0.258500 | 0.317416 |
| sqlite_checkpoint | 286 | 2.022208 | 11.786958 | 26.908666 | 32.135708 |
| sqlite_checkpoint.process_cpu | 286 | 1.905000 | 5.716000 | 15.615000 | 18.962000 |
| sqlite_checkpoint.thread_cpu | 286 | 1.690791 | 3.714542 | 5.070292 | 6.374208 |
| ws_decode | 23528 | 0.005250 | 0.042250 | 0.072875 | 5.755958 |
| ws_decode.process_cpu | 23528 | 0.005000 | 0.041000 | 0.060000 | 0.253000 |
| ws_decode.thread_cpu | 23528 | 0.005166 | 0.038875 | 0.056166 | 0.246125 |
| ws_receive_wait_provider_idle_included | 23528 | 0.006792 | 82.608333 | 233.616917 | 1122.047250 |

## Evidence and limits

`analysis.json`, `stage-quantiles.json`, `correlated-events.jsonl`, `host-samples.jsonl`, `soak-samples.jsonl`, bothprocessmetrics/state snapshots, `controlled-restart.json`, `protected-before.json`/`protected-after.json`, `scoped.diff` and testlogs are preserved. Actualduration/CPU/OS bracket values are authoritative inJSON. No claim of networklatency, stablecriticaldiskunderfault, universalhostcause or validated economicstrategy. Skillresolution:paths-injected.
