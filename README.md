# TRACEBACK — the agent that can't say anything it can't trace

An incident-response agent crew whose entire world — company data, memory, and coordination state — lives in
**FalkorDB**. Every answer is a path through the graph, and a verifier re-queries the graph and **withholds any
claim it cannot confirm** ("no path, no claim").

*Built for Graph Hacks: Context for AI Agents (FalkorDB × WeMakeDevs).*
**Tracks entered:** Agents That Act on Connected Data · Agent Memory and Coordination · Company Brain

![console](docs/screenshot-incident.png)

## What it does

A synthetic company ("helix", plus a second tenant "orbit" with overlapping service names) has 80 services, 40
people, 9 teams, ~620 deploys, ~120 incidents, ~290 documents and 32 engineering decisions, all in a graph. When an
alert fires, three agents run:

| Agent | Does | Reads/writes (all in the graph) |
|---|---|---|
| **Triage** | sizes the alert, opens the incident, creates tasks | `Incident`, `Task` nodes |
| **Investigator** | walks the dependency graph to the likely cause, owner and expert; produces claims; verifier checks them | reads topology, deploys, ownership; writes `Episode`, `ToolCall`, `Finding` |
| **Remediator** | reads the Investigator's `Finding` **through the graph**, ranks runbooks by learned success, proposes actions (risk-gated), records the outcome | writes `Action`, updates `Runbook` stats, writes superseding `Fact`s |

Agents never call each other: the only channel is `Task`/`Finding` nodes.

## Why the graph is necessary (hackathon rule 3)

1. **Kill switch.** The console header has a *FalkorDB graph: ON/OFF* switch. Off, the product falls back to
   document retrieval: no dependency scope, no ownership, no handoff, **0% verifiable claims**.
2. **A/B evaluation** (`make eval`, [docs/EVAL.md](docs/EVAL.md)): 96 questions over 2 tenants, same documents, same
   embedder, hybrid retrieval + extractive reader as the baseline. Ground truth is computed from the *generator's own
   model*, never read back from FalkorDB.

| Relationships needed | n | Graph agent | Docs-only |
|---|---|---|---|
| 1 hop | 28 | 100% | 89% |
| 2 hops | 14 | 100% | 29% |
| Temporal (as-of) | 14 | 100% | 86% |
| 3+ hops | 40 | 100% | 10% |
| **All** | 96 | **100%** (100% grounded) | **47%** |

Read this honestly: the baseline is competent at single lookups and collapses as answers need composed relationships
(*which teams own anything that depends on auth-service*, *who authored the deploy responsible for this alert*,
*which services are owned by a team with nobody left*). The graph agent's 100% shows its Cypher tools reproduce an
independently computed model; it does **not** claim general reasoning ability.

## Track coverage

| Track focus | Where it lives |
|---|---|
| **T1** multi-hop reasoning | `recent_changes` (alert → dependencies ≤2 hops → deploy → author), `blast_radius`, `impacted_teams` |
| **T1** graph queries and algorithms as agent tools | 17 tools in `tbk/tools/`; `algo.pageRank` (criticality), `algo.betweenness` (single points of failure) |
| **T1** tool selection through MCP | `tbk/mcp_server.py` serves every tool + `ask` + `investigate_alert` (tested with a real MCP client) |
| **T1** actions from what the graph shows | `page`, `propose_rollback`, `apply_runbook` as `Action` nodes with graph-derived risk and an approval gate |
| **T1** explainable results | evidence subgraph replay + per-claim edge ids + verifier |
| **T2** episodic / semantic / procedural | `Episode`+`ToolCall` · `Fact` with `vf/vt` and `SUPERSEDES` · `Runbook` counters + ranking query ([learning curve](#memory-that-learns)) |
| **T2** shared state & handoffs | `Task` / `BLOCKED_BY` / `PRODUCED→Finding`; atomic claim ([tasks.py](tbk/tasks.py)) |
| **T2** high-concurrency reads/writes | [docs/BENCH.md](docs/BENCH.md): 40 crews at once, 100-way task race → exactly 1 winner |
| **T2** separate memory per tenant | one graph per tenant (`t_helix`, `t_orbit`); canary isolation test |
| **T3** docs, tickets, chats in one graph | READMEs, runbooks, postmortems, ADRs, chats → `Doc`/`Source` nodes with `MENTIONS_*` edges |
| **T3** who owns / who knows | `owners_of`, `who_knows`, `incident_resolvers`, `ownership_gaps` |
| **T3** decisions traced to source | `decision_lineage`: `Decision -[SUPERSEDES]-> Decision`, `DECIDED_IN_DOC -> Doc -[DERIVED_FROM]-> Source` |
| **T3** knowledge kept current | every ownership/dependency/membership edge has a validity window; `facts_as_of` time-travels; stale READMEs lose to the graph |
| **T3** answers with sources | each claim cites edge ids; `Source.uri` surfaced |

## Proof-carrying answers

A `Claim` cites graph edges (and/or nodes). The verifier ([tbk/verifier.py](tbk/verifier.py)) accepts it only if,
re-checked against that tenant's graph: the edges exist; they were valid at the claim's time; cited nodes exist and
asserted properties match; and **every entity the text mentions is an endpoint of the cited evidence** (so a language
model cannot smuggle an ungrounded name into a grounded sentence). Grounded % counts rejected claims against the
score. The console has an **Inject hallucination** button that shows a fabricated edge, an extra entity and a bare
inference being withheld, with reasons.

## Memory that learns

The console's *Agent memory* tab draws this live. Procedural memory is two counters on `Runbook` nodes plus a ranking
query; outcomes (simulated from hidden per-runbook rates that never enter the graph) are written back after each
incident. Averaged over 5 cold starts of 240 incidents each, the better runbook is chosen **70%** of the time in the
first 20 incidents (chance is 50%) and **~86%** afterwards (the policy explores 10% of the time, which caps it near
90%). Resolution rate settles at ~0.74 against an always-best ceiling of 0.81 and a random floor of 0.58.

## Graph data model

See [docs/DATA_MODEL.md](docs/DATA_MODEL.md). Highlights: `Service-[DEPENDS_ON{vf,vt}]->Service`,
`Team-[OWNS{vf,vt}]->Service`, `Person-[MEMBER_OF{vf,vt}]->Team`, `Person-[AUTHORED]->Deploy-[DEPLOYED_TO]->Service`,
`Incident-[AFFECTED|CAUSED_BY|RESOLVED_BY|FIXED_WITH]->…`, memory (`Episode`, `Fact`, `Runbook`) and coordination
(`Task`, `Finding`, `Action`) nodes. FalkorDB features used: variable-length paths with `ALL(...)` predicates,
vector indexes (`db.idx.vector.queryNodes`, cosine), range indexes, `algo.pageRank`, `algo.betweenness`,
multi-graph tenancy, `ID(r)` evidence addressing.

## Queries and algorithms the product depends on

[QUERIES.md](QUERIES.md) is **generated from the code that runs them** (`make queries`). Index of tools:

`get_alert` · `blast_radius` · `dependencies` · `dependency_path` · `impacted_teams` · `criticality` (PageRank) ·
`single_points_of_failure` (betweenness) · `recent_changes` · `owners_of` · `who_knows` · `incident_resolvers` ·
`ownership_gaps` · `similar_incidents` (vector + traversal) · `decision_lineage` · `facts_as_of` · `search_docs` ·
`rank_runbooks`

## Quick start

Prerequisites: Docker, Python ≥3.11, Node ≥18.

```bash
make db        # FalkorDB on :6390 (Browser UI on :3010)
make setup     # venv + deps + console deps
make seed      # generate & load both tenants (<1 s)
make web       # build console
make api       # http://localhost:8765
make test      # 32 tests
```

Or everything in containers: `docker compose up --build` → http://localhost:8765.

Optional: `ANTHROPIC_API_KEY=…` switches the Investigator to a Claude tool-use planner and enables LLM phrasing of
claims (the verifier still gates every sentence). Without a key the deterministic playbook planner runs.

Other entry points: `make eval`, `make bench`, `python -m tbk.isolation`, `python -m tbk.mcp_server` (stdio) or
`--http 8770`.

MCP client config (Claude Desktop):

```json
{ "mcpServers": { "traceback": { "command": "/ABS/PATH/.venv/bin/python", "args": ["-m", "tbk.mcp_server"],
                                  "cwd": "/ABS/PATH/traceback" } } }
```

## Architecture

```
alert ─▶ Triage ─▶ Task(investigate) ─▶ Investigator ─▶ Finding ─▶ Task(remediate) ─▶ Remediator
            │            graph              │  tools (Cypher/algorithms)  │  graph          │ runbook ranking,
            ▼                               ▼                             ▼                 ▼ actions, outcomes
        ┌────────────────────────── FalkorDB: one graph per tenant ───────────────────────────┐
        └──────────────────── Verifier re-queries the same graph ◀── Claims (edge ids) ◀───────┘
```

`tbk/` modules: `graph.py` (tenant routing, admission control) · `tools/` (registry + Cypher) · `verifier.py` ·
`memory.py`, `tasks.py` · `agents/` (triage, investigator, remediator, qa, orchestrator) · `llm.py` (planners) ·
`seed/` (generator, loader) · `evalx/` · `api/` · `mcp_server.py` · `web/` (React console).

## Honest limitations

- **All data is synthetic** (`tbk/seed/generate.py`, deterministic), including the "live" alerts. No private data.
- **Runbook outcomes are simulated**; real outcomes would come from monitoring.
- **Default planner is a deterministic playbook.** The Claude planner/phraser path is implemented and unit-tested
  with a scripted fake client, but has **not** been run against the live API in this build.
- The Company-brain question router is rule-based (intent regex + entity vocabulary), not an LLM.
- The baseline reader is extractive and generous by design; a strong LLM reader would narrow the 1-hop gap but cannot
  reach documents that retrieval did not return or facts that no document states.
- FalkorDB's `MAX_QUEUED_QUERIES` defaults to 25: the client gates in-flight queries and retries with backoff
  (found by the benchmark; see `graph.py`).
- Cypher subset limits that shaped the design: `shortestPath` only in `WITH/RETURN` and directed, no label
  expressions, vector search doesn't combine with property filters (we retrieve, then traverse).

## AI usage disclosure

See [AI_USAGE.md](AI_USAGE.md).
