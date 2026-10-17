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
| `llm.py` | `InvestigatePlanner` (offline) and `AnthropicPlanner` (tool-use loop) |
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
