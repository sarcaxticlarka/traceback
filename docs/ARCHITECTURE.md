# Architecture

## Flow of one incident

1. `POST /api/run` → `agents.orchestrator.run_incident(tenant, alert_id)`.
2. **Triage** (`agents/triage.py`) calls `get_alert` + `blast_radius`, opens an `Incident`, creates two `Task` nodes
   (`investigate`, then `remediate` `BLOCKED_BY` it).
3. The scheduler loop calls `tasks.claim_next`: a Cypher query for ready tasks with no open blockers, then a
   conditional `SET status='running' WHERE status='ready'` so two workers cannot both claim a task.
4. **Investigator** runs a planner loop (`llm.py`): the planner picks a tool, `tools.run_tool` executes it, `memory`
   logs an `Episode`/`ToolCall`. Claims are pooled (`agents/compose.py`), verified (`verifier.py`), and the structured
   result is stored as a `Finding`.
5. **Remediator** reads the `Finding` via `tasks.upstream_findings` (the handoff), ranks runbooks, creates `Action`
   nodes (risk-gated), writes the outcome back to `Runbook` counters and `Fact`s, closes the incident.
6. The report (steps, claims, grounded %, tasks, actions) is returned; the console replays the cited subgraph.

## Modules

| Module | Responsibility |
|---|---|
| `graph.py` | Only way to get a graph handle; tenant slug → `t_<slug>`; in-flight gate + retry on FalkorDB queue limit |
| `switches.py` | Per-request kill switch (`contextvars`) → `GraphDisabled` |
| `tools/` | Registry of Cypher/algorithm tools; each returns rows **and** `Claim`s carrying edge ids |
| `verifier.py` | "No path, no claim" (rules below) |
| `memory.py` | Episodes, tool calls, supersedable facts, incidents, actions |
| `tasks.py` | Task graph, atomic claim, handoff |
| `agents/` | triage, investigator, remediator, qa (company brain), orchestrator, scoring, fallback (graph off) |
| `providers.py` | Anthropic + OpenAI-compatible adapters, `FailoverClient` (cool-downs, error classification), request-scoped keys |
| `llm.py` | `InvestigatePlanner` (offline) and `LLMPlanner` (provider-agnostic tool-use loop) |
| `seed/` | Deterministic synthetic company + bulk loader |
| `evalx/`, `bench.py`, `isolation.py`, `sim.py` | Proof: A/B eval, concurrency, tenant canary, learning curve |
| `api/app.py`, `mcp_server.py` | HTTP and MCP surfaces over the same tools |

## Verifier rules

A claim is grounded only if, re-checked in the tenant's graph: (1) it cites evidence and is not an inference; (2) every
cited edge exists; (3) each was valid at the claim time (`vf <= t < vt`), or for `ended_edge_ids` had ended;
(4) cited nodes exist and asserted properties match (`op:"ge"` for monotone counters); (5) every entity token the text
mentions (services, people, `team X`, deploy shas, typed ids) is an endpoint of the cited evidence.
Grounded % = grounded / proposed.

## Design decisions

- **Claims come from tools, not the LLM.** The LLM chooses tools and may rephrase; rule 5 rejects added entities.
- **Counter claims are monotone** ("at least N attempts"): exact-count claims went stale under concurrent writers
  (found by the benchmark).
- **Edge ids as evidence.** `ID(r)` is stable within a graph and is re-resolvable by the verifier.
- **Tenant = graph.** Isolation is structural, not a `WHERE tenant=` filter.
- **Admission control.** FalkorDB queues ≤25 queries by default; the client gates 16 in flight and retries.
- **Cypher limits worked around:** `shortestPath` only in `WITH/RETURN` and directed (we use bounded variable-length
  paths ordered by length); variable-length bounds can't be parameters (depth is int-clamped and interpolated); vector
  search doesn't combine with property filters (retrieve, then traverse).

## LLM provider layer

- Conversations use a provider-neutral format (`user` / `assistant{text, tool_calls}` / `tool`), converted per
  provider, so a run can switch providers between model turns without losing context.
- `FailoverClient` classifies errors (`rate_limit`, `quota`, `overloaded`, `timeout`, `network`, `auth`,
  `bad_request`). All but `bad_request` fail over to the next provider; the failing key is put on cool-down
  (`Retry-After` honoured). If every provider fails, the Investigator returns what it has gathered (graph tools it
  already ran remain verified) instead of crashing.
- User keys travel per request (`X-LLM-Providers`), live in a `contextvar` for the request, and are never persisted,
  logged or returned. Preset provider URLs are fixed; custom URLs need an explicit server flag.

## Ingestion pipeline (real data)

`ingest/fetch.py` (safe clone / zip) → `analyze.py` (walk tree, resolve imports, choose module depth ≤120, build module graph)
→ `history.py` (git log, identity resolution by hashed email) → `codeowners.py` → `build.py` (same schema the agents use:
`Service` = module, `Deploy` = commit, `Team`/`OWNS` from CODEOWNERS or top committer, docs and decisions, auto-generated reported
issues) → `seed/load.py` (bulk load into `t_repo_<id>`) → `workspaces.py` (registry, 12 h TTL, caps, rate limit).

Design decisions: edges carry provenance (`sites`, `basis`, `rule`); traversal tools use level-by-level BFS (`tools/walk.py`)
because real import graphs have cycles and FalkorDB aborts slow queries (1 s default); identities are merged by hashed email
with a collision-free id (`slug-hash`) because name slugs merged look-alike and non-ASCII names in the first benchmark run;
properties used by claims (`churn_90d`, `dependents`, `top_author_share`) are materialised at ingest and re-asserted by the verifier.
