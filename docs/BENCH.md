# Concurrency benchmark

Local FalkorDB (single container), 2 tenants (helix, orbit), Python client, threads.

| Test | Result |
|---|---|
| 50 full agent crews at once (triage → investigator → remediator; reads+writes) | 19.42 incidents/s, p50 2090.8 ms, p95 2566.5 ms, 50/50 fully grounded, 0 errors |
| 400 concurrent graph reads (32 threads) | 343.8 ops/s, p50 39.7 ms, p95 140.2 ms |
| 100 workers racing to claim one task | 1 winner(s); exactly one: True |
