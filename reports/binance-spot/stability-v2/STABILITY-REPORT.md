# Spot observer: isolation implemented, stability target NOT passed

A real 620.328s public-feed observation completed with 568 samples and a controlled flat process/WebSocket shutdown/restart. The fixed250ms processing/2s freshness guards still failed closed under measured local stalls. Readiness remains **BLOCKED**; the remaining host/scheduler/GIL/storage cause is **UNRESOLVED**, not blamed on Binance.

## What changed

Only binance_app.py and a new focused test file: one bounded noncritical I/O worker handles raw/REST writes, exports, View copies and full-state observation checkpoints. Immutable JSON snapshots are prepared by the sole mutable-state owner. Worker SQLite connections are created/closed in the worker; the owner retains its original connection. Revision guard skips stale checkpoints after newer critical writes. Critical intents/fills/halt transactions still use unchanged AtomicJournal, synchronously and atomically. Actual lock wait, durable commit, owner snapshot wall time and worker I/O are measured separately (not owner CPU time). No guarantee that a critical durable write bypasses a stalled disk.

19 focused tests passed after RED, including slow checkpoint/dashboard while consuming every quote, old checkpoint vs newer atomic halt, actual slow SQLite commit/critical lock contention, queue overflow and unchanged250ms rejection. Actual soak was FLAT: no active protection/economic strategy timing is claimed. Those hooks were exercised only with synthetic fixtures.

## Actual observation

- Observer84032→87703, same paper.sqlite; no reset, secondBUY or extraSELL. Final cash999.76609237980375USDT,1BUY/1SELL, flat/spent. Restart at elapsed301.728s; cached data is not certified across connection epoch.
- Certificates true 103/568 (18.13%). False predicate counts are nonexclusive and preserved in verification.json; no thresholds were relaxed.
- Processing rejects496 before/1242 after restart; WS bounded queue overflow1/1, trade-gap observations10/8, old-connection event discards62 after restart. These counters are not evidence of provider-origin packet loss; rejected local queued trades and connection boundaries can create ID discontinuities. REST and source/receipt evidence is retained.
- First observed rejection bracket96.311–97.785s (already32 by first observed sample); after restart409.612–413.943s (first observed1). Stage summaries do not timestamp individual stage anomalies, so they cannot establish whether a particular later reconnect FULL commit caused an earlier backlog. No such claim is made.
- Local HTTP client response p50/p95/p99/max: 17.690/211.956/1172.234/3216.675ms.0request errors during measured samples. First shell-background launch died with tool completion; its invalid attempt is preserved/excluded, not counted as feed failure.
- Same-host focused offline tests, public archive acquisition and research replay ran during this soak. This is not an isolated-load benchmark. Broad stage/loop stalls were measured, but their residual scheduler/GIL/disk attribution cannot be uniquely determined from the available telemetry.

## Stage timings

All values milliseconds, rolling quantiles over last bounded20000 samples per stage, lifetime count/max. Values below are p50/p95/p99/max. Do not pool these two process distributions.

| Stage (p50/p95/p99/max ms; lifetime N) | Before restart | After restart |
|---|---|---|
| certificate_hook | 0.110/0.729/2.259/831.310 (N=36515) | 0.075/0.561/1.986/292.241 (N=37655) |
| consumer_iteration | 0.168/1.250/9.816/1069.068 (N=36515) | 0.106/0.964/7.411/2212.749 (N=37655) |
| critical_journal_save | 7.678/408.227/408.227/1432.397 (N=6) | 5.122/34.083/34.083/72.263 (N=6) |
| critical_lock_wait | 0.002/0.089/0.089/6.559 (N=6) | 0.002/0.004/0.004/0.005 (N=6) |
| dashboard_read | 8.663/54.930/237.286/372.348 (N=280) | 8.044/56.686/487.187/1670.796 (N=287) |
| dashboard_snapshot | 7.757/31.476/148.570/1470.538 (N=286) | 7.744/52.142/115.896/828.777 (N=296) |
| event_loop_lag | 1.090/8.301/42.286/2261.424 (N=12729) | 1.078/9.216/37.689/5416.985 (N=13209) |
| feed_process | 0.020/0.156/0.654/133.910 (N=36235) | 0.011/0.106/0.541/46.382 (N=37338) |
| filesystem_export | 35.845/391.323/1162.021/1940.698 (N=285) | 41.305/263.122/1668.489/3866.697 (N=295) |
| io_queue_wait | 4.022/255.989/2454.680/3742.530 (N=809) | 3.668/142.577/1307.906/3733.995 (N=841) |
| observation_publish | 49.178/536.872/1907.404/5909.540 (N=285) | 56.199/451.057/2472.617/3966.929 (N=295) |
| owner_rest_encode | 0.041/3.633/17.352/76.841 (N=185) | 0.040/3.168/8.860/9.446 (N=192) |
| owner_snapshot_prepare | 8.711/66.860/137.599/152.162 (N=286) | 8.614/60.396/283.915/919.826 (N=296) |
| owner_state_encode | 4.630/37.935/74.010/108.710 (N=286) | 4.357/30.367/161.355/531.570 (N=296) |
| queue_wait | 1.458/121.990/301.806/2128.280 (N=36235) | 1.728/79.413/447.101/3024.030 (N=37338) |
| raw_write | 0.533/8.755/23.318/108.253 (N=338) | 0.291/7.833/40.087/1497.942 (N=353) |
| rest_compare_network_included | 1567.522/4789.422/6767.624/7622.761 (N=46) | 1711.084/4981.570/5995.382/8737.028 (N=48) |
| rest_evidence_write | 0.133/6.366/8.915/106.266 (N=185) | 0.134/5.112/13.880/21.945 (N=192) |
| sqlite_checkpoint | 2.939/70.921/165.229/5522.255 (N=285) | 2.948/47.144/179.860/426.799 (N=296) |
| ws_decode | 0.005/0.040/0.151/45.278 (N=36236) | 0.004/0.032/0.126/312.097 (N=37339) |
| ws_receive_wait_provider_idle_included | 0.007/58.802/170.486/8074.811 (N=36236) | 0.005/51.375/178.918/3610.695 (N=37339) |

Actual position-protection and economic-strategy hook: N/A in this flat observation. Owner stage measurements are wall durations; the standalone parent diagnostic is the separate thread-CPU measurement.

WSreceive wait includes provider idle and application-loop scheduling. Receipt stamps occur when the application sees a message, not at kernel arrival. Corrected trade sourceage/REST clock uncertainty is NOT measured transport latency; bookTicker has no source timestamp. Exact source-clock ranges are in verification.json. Original22rejects/595s had insufficient stage telemetry; this new instrumented run does not retroactively explain them.

## Commands and boundary

```sh
PYTHONPATH=src:tests_local .venv/bin/python -m pytest -q tests_local/test_binance_stability.py tests_local/test_binance_spot.py
./run-binance-paper.sh --report reports/binance-spot/stability-v2
.venv/bin/python reports/binance-spot/stability-v2/analyze.py
```
The observer is already running on127.0.0.1:8767; do not start another owner against the same journal. process.json and observer.pid identify the current process. The launcher default still references the prior technical report, whose frozen code identity is preserved; use the explicit current report path.

Protected core.py, replay.py, binance_spot.py and rejected-SMA protocol/freeze/results checksums match before/after. Snapshot before/binance_spot.py preserves the old frozen execution bytes. Rollback boundary: restore only binance_app.py from before/binance_app.py and use its prior frozen technical protocol; remove the new stability test only if deliberately rolling back this work unit. Do not remove/reset paper.sqlite or overwrite prior results.

No Git repository/commits; gentle-ai unavailable and CodeGraph NotInitialized, targeted fallback. skill_resolution: paths-injected.

## One additional quiet-host diagnostic (not a replacement soak)

After all92tests and both economic replays finished, one bounded control ran 180.847s: 174 samples, 19 eligible (10.92%), 106 additional processing rejections,4trade-gap observations,1unrepairable-gap flag,0new queue overflows;18711messages. Existing PID87703 stayed flat/spent. No executor heavy tasks ran; other host workloads were not controlled. This does NOT override the failed620s test.

Local HTTP p50/p95/p99/max: 17.215/50.884/447.789/988.945ms. Stage control evidence reports count/new-lifetime-record deltas only; rolling/lifetime stage percentiles are not falsely labeled isolated control percentiles.

Raw macOS evidence: swap25511.50→25697.00MiB used of26624MiB; load8.77/11.28/11.82→6.16/9.36/10.95. kern.memorystatus_vm_pressure_level=2 raw value, no unverified label. Resource snapshots include vm_stat and processCPU/RSS. No settings/apps were changed. Parent20 standalone encodes of~384KB state had median wall1.29373ms and median threadCPU1.22621ms; this is outside the hot path, NOT proof of the old22reject cause.

Heavy research/test concurrency alone is therefore NOT necessary for residual rejects. Host memory/scheduling pressure remains a supported hypothesis, but separating scheduler/GIL/storage effects is UNRESOLVED. No provider-delay attribution and no readiness promotion.
