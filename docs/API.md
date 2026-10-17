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
| `GET /api/llm/providers` | Provider presets for the UI and which providers the server has default keys for (names only) |
| `POST /api/llm/test` | One-token check of each supplied provider key; returns ok / error kind, never echoes keys |
| `POST /api/workspaces/github` `{url}` | Analyse a public GitHub repo (async; poll `GET /api/workspaces/{id}`) |
| `POST /api/workspaces/upload` (multipart `file`, `label`) | Analyse a zip of source files (no `.git` is read) |
| `POST /api/workspaces/bundle` `{services, dependencies, teams, deploys, alerts}` | Build a graph from exported catalogue data |
| `GET /api/workspaces?ids=a,b` · `GET/DELETE /api/workspaces/{id}` | Only the ids you pass; status, stats, delete |
| `GET /api/workspaces/{id}/modules` · `/commits` | Module table and recent commits |
| `POST/GET /api/workspaces/{id}/benchmark` | Run / read the per-repo benchmark |
| `POST /api/tool` `{tenant, tool, args}` | Run any graph tool and verify its claims |
| `POST /api/impact` `{tenant, sha or modules}` | Change impact: touched, impacted, owners, reviewers, risk |
| `GET /api/provenance?tenant=&edge_id=` | Why an edge exists: basis, import sites, ownership rule |
| `GET /api/bench/real` | Real-repo benchmark results |
| `POST /api/audit` `{tenant, claims}` + `X-LLM-Providers` | Independent audit by the caller's own LLM key(s); 400 without one (server keys are not used) |
| `GET /api/tools` | Tool catalog with Cypher refs |
| `POST /api/admin/reseed?tenant=` | Reset a tenant to the seed data |

## Bringing your own LLM keys

`POST /api/run` and `POST /api/ask` accept an `X-LLM-Providers` header: base64 of a JSON list, in priority order,
`[{"provider": "openai", "api_key": "...", "model": "optional", "base_url": "only for provider=custom"}]`.
Providers: `anthropic`, `openai`, `gemini`, `groq`, `openrouter`, `mistral`, `deepseek`, `custom` (needs
`TBK_ALLOW_CUSTOM_BASE_URL=1`). `use_llm`: `true` use them, `null` auto (user keys, then server keys, else offline),
`false` never. The response's `llm` field lists the provider that answered and every failover (never keys).

## MCP

`python -m tbk.mcp_server` (stdio) or `--http 8770`. Every registry tool is exposed with its JSON schema plus `tenant`
and `at`; plus `ask` and `investigate_alert`. Responses include `claims` and a `verification` block.
