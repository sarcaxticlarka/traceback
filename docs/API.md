# API

Base: `http://localhost:8765`. `tenant` is `helix` or `orbit`.

| Method & path | Purpose |
|---|---|
| `GET /api/health` | FalkorDB reachable, tenants, LLM availability |
| `GET /api/alerts?tenant=` | Live alerts |
| `POST /api/run` `{tenant, alert_id, graph_enabled?, use_llm?, outcome?, auto_approve?}` | Run the crew; returns the full report |
| `GET /api/runs/{id}` | A previous report |
| `GET /api/subgraph?tenant=&edge_ids=1,2&node_ids=` | Nodes/edges for cited evidence |
| `GET /api/graph/services` · `/api/graph/overview` | Service map; node/edge counts |
| `POST /api/ask` `{tenant, question, graph_enabled?}` | Company-brain answer + docs-only baseline |
| `POST /api/verify` `{tenant, claims[]}` | Verify arbitrary claims |
| `GET /api/memory/{runbooks,facts,episodes}` | Procedural / semantic / episodic memory |
| `GET /api/tasks` · `GET /api/actions` · `POST /api/actions/{id}/approve` | Coordination and approvals |
| `GET/POST /api/sim/learning` | Learning-curve simulation |
| `GET /api/eval` · `POST /api/isolation` · `GET /api/bench` | Proof endpoints |
| `GET /api/tools` | Tool catalog with Cypher refs |
| `POST /api/admin/reseed?tenant=` | Reset a tenant to the seed data |

## MCP

`python -m tbk.mcp_server` (stdio) or `--http 8770`. Every registry tool is exposed with its JSON schema plus `tenant`
and `at`; plus `ask` and `investigate_alert`. Responses include `claims` and a `verification` block.
