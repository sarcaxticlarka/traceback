# Concurrency benchmark

Local FalkorDB (single container), 2 tenants (helix, orbit), Python client, threads.

| Test | Result |
|---|---|
| 40 full agent crews at once (triage → investigator → remediator; reads+writes) | 19.4 incidents/s, p50 1844.6 ms, p95 2058.5 ms, 40/40 fully grounded, 0 errors |
| 400 concurrent graph reads (32 threads) | 341.6 ops/s, p50 41.1 ms, p95 152.0 ms |
| 100 workers racing to claim one task | 1 winner(s); exactly one: True |
