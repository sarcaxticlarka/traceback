# 03 — TRACEBACK: concept, features, differentiators

> **The agent that can't say anything it can't trace.**
> Incident-response agent crew whose world, memory and coordination all live in FalkorDB. Every answer is a graph path with edge IDs; a verifier blocks claims without one.

## Why this idea (decision logic)

Candidate ideas considered and why they lost:

| Idea | Verdict |
|---|---|
| Fraud ring investigator | Strong for Track 1 only; heavily done; synthetic data looks fake; weak on memory/company brain |
| Codebase navigator | Cheap, but "repo explainer" is the most common entry |
| Pure agent-memory layer (Graphiti wrapper) | Framework already exists → "original work" risk; hard to demo visually |
| Generic "company brain" chatbot | Crowded; sources/tracing is the only differentiator, nothing to *act* on |
| **Incident-response crew (TRACEBACK)** | Naturally graph-shaped (dependencies, ownership, deploys, past incidents); has real *actions*; has memory + handoffs; has docs/decisions; demo is vivid (an alert fires, a graph lights up) |

The key insight: **incident response is the one domain where all three tracks' focus bullets occur organically**:

| Track focus bullet | Where it appears in TRACEBACK |
|---|---|
| T1 multi-hop reasoning | Alert → service → dependency chain → recent deploys → authors → owners |
| T1 algorithms as tools | PageRank = criticality, WCC/BFS = blast radius, shortest path = escalation, betweenness = single points of failure |
| T1 action | Page the right human, open a ticket, propose rollback, quarantine a deploy (simulated, with approval gate) |
| T1 MCP tool selection | All graph tools exposed via an MCP server; agent chooses among them |
| T2 episodic/semantic/procedural memory | Past incidents (episodic), learned facts (semantic), runbooks with success stats (procedural) |
| T2 shared state & handoffs | Triage → Investigator → Remediator agents coordinate through Task nodes |
| T2 concurrency | Many simultaneous incidents; load script |
| T2 per-tenant memory | Each customer company = its own graph; leak test |
| T3 docs/tickets/chats in one graph | Runbooks, postmortems, ADRs, tickets, chat threads ingested and linked |
| T3 who owns / who knows | `OWNS` + expertise inferred from commits/incidents |
| T3 decisions traced to source | Decision nodes with `DECIDED_IN → Source` |
| T3 knowledge stays current | Bitemporal facts, `SUPERSEDES` edges, "as-of" queries |

## The 12 features, ranked by judge impact ÷ build cost

Legend: **MVP** = must exist by the ~H18 checkpoint. **STRONG** = likely differentiator. **STRETCH** = only if ahead.

### 1. [MVP] Proof-carrying answers ("no path, no claim")
Agent output is structured: `claims: [{text, edge_ids[], node_ids[]}]`. A verifier re-fetches those edges from FalkorDB and checks (a) they exist, (b) they are valid at the as-of time, (c) the claim text was *generated from* a template over those edges (LLM only phrases it). Unsupported claims are dropped and shown as "withheld: no supporting path". The UI shows a **Grounded %** badge for every answer.
- Hits: explainable results (T1), clear sources (T3), traceable decisions (tagline).
- Cost: moderate. This is the soul of the project; protect time for it.

### 2. [MVP] Blast-radius & root-cause engine (Cypher + algorithms as tools)
Tools the agent can call (each a named, parameterised Cypher/algorithm):
`blast_radius(service, depth)`, `critical_path(service)`, `recent_changes(service, window)`, `owners_of(service)`, `who_knows(topic)`, `similar_incidents(incident)`, `escalation_path(from, to)`, `spof_scan()`, `decision_lineage(entity)`.
- Hits: T1 multi-hop, algorithms as tools.

### 3. [MVP] Live graph explainer view
Frontend renders only the *subgraph the agent used*, edges highlighted in order of traversal (animated "replay of reasoning"). Clicking a claim highlights its edges.
- This is the demo money-shot. Low backend cost, high perceived depth.

### 4. [MVP] Persistent three-layer memory
- **Episodic:** `(:Episode)` per agent run: what was asked, which tools, which result, outcome.
- **Semantic:** `(:Fact {text, valid_from, valid_to, confidence})-[:SUPPORTED_BY]->(:Source)`, with `SUPERSEDES` when facts change.
- **Procedural:** `(:Runbook)` with `attempts`, `successes`, updated from episode outcomes; `rank_runbooks(incident)` orders by structural similarity × success rate. The agent literally gets better at remediation over time and the improvement is visible as a chart.
- Hits: all of T2's first bullet; "keeping knowledge current" (T3).

### 5. [MVP] Multi-agent handoff via shared graph state
Three agents (Triage, Investigator, Remediator) never call each other. They read/write `Task` nodes: `(:Task {status})-[:ASSIGNED_TO]->(:Agent)`, `-[:BLOCKED_BY]->(:Task)`, `-[:PRODUCED]->(:Finding)`. A scheduler picks the next ready task with a single Cypher query. A human can open the graph and see exactly where the crew is.
- Hits: shared state and handoffs (T2).

### 6. [STRONG] The A/B evaluation harness ("Does the graph earn its place?")
30–40 questions bucketed by hop depth (1, 2, 3, 4+). Two systems answer each: baseline vector-RAG over the same documents vs. TRACEBACK. Automatic grading against a ground truth generated *by construction* from the synthetic graph (you know the right answer because you generated the data). Output: accuracy-by-hop-depth chart in README and demo.
- Directly answers rule 3. Almost no one will do it. The expected shape (baseline decays as hops increase, graph stays flat) is the headline.
- Honesty note: report whatever you get. If vector RAG wins on 1-hop, say so; judges trust that.

### 7. [STRONG] "Kill the graph" switch
A toggle in the UI/CLI that disables the FalkorDB tool layer; the agent falls back to docs-only. Demo shows it failing on multi-hop questions and on tracing. One sentence in the video: "This is rule 3 in one button."

### 8. [STRONG] Bitemporal time travel
Every edge/fact has `valid_from`/`valid_to` (when true in the world) and `recorded_at` (when we learned it). Query "who owned payments-api on March 3?" and "what did we *believe* on March 3?" Ownership changes, service renames, deprecated dependencies, superseded decisions are all in the synthetic data on purpose.
- Hits: "keeping knowledge current" (T3), "update over time" (T2).

### 9. [STRONG] Tenant isolation proof + concurrency benchmark
- Two tenants (`tenant_helix`, `tenant_orbit`) with deliberately overlapping names ("payments-api" exists in both). An automated test asks the same question per tenant and asserts zero cross-tenant node IDs in any result or claim. Show green test run in video.
- `bench_concurrency.py`: N parallel agent sessions (e.g. 50) doing mixed reads/writes against separate and shared graphs; print p50/p95 latency and ops/sec. Put the table in README.
- Hits: T2 bullets 4 and 5.

### 10. [STRONG] Decision lineage
`Decision` nodes: what was decided, by whom, in which doc/ticket/thread, what it superseded, what it constrains. `decision_lineage(service)` returns the chain. Question like "Why is checkout still on the old queue?" is answered as a path: Decision → Postmortem → Incident → Deploy → Ticket.
- Hits: T3.

### 11. [STRETCH] Approval-gated actions with graph-computed risk
Actions (`page`, `open_ticket`, `propose_rollback`) are simulated side effects written to the graph as `Action` nodes with `RISK = f(blast radius, criticality PageRank, recent failures)`. Above a threshold a human approval is required. Shows "acts" without needing real integrations.

### 12. [STRETCH] Public data mode
Optional import of a real public GitHub repo's commits/issues/PRs (public, allowed) into the same schema to prove it isn't only a synthetic toy; and a Graphiti ingest comparison panel. Only if everything else is green.

## Explicitly NOT building

- Real Slack/PagerDuty/Jira integrations (private/auth data, rule 6, huge time sink). Simulate with synthetic feeds.
- Fine-tuning, custom embedding models.
- Auth system, billing, user accounts beyond a tenant dropdown.
- A generic "chat with anything" UI. The product is narrowly an incident console.
- Neo4j-style features FalkorDB lacks (label expressions, APOC).

## What makes this "no one else would think of it"

Not the domain. These three combinations:
1. **Withholding as a feature.** Most agents optimise for answering. This one visibly refuses to assert untraceable claims and *measures* how often (Grounded %). Judges reading "makes decisions you can trace" will see the tagline taken literally.
2. **Procedural memory with a visible learning curve.** Runbook success rate rising across simulated incidents, backed by `Episode → OUTCOME` edges, is concrete proof of "memory that updates over time".
3. **Falsifiable graph claim.** The A/B chart plus kill-switch turns "graph matters" from an assertion into an experiment.

## Track entry strategy

Enter **all three**, naming each, and lead the README/video with a track-mapping table (the one in this doc). Primary framing: Track 1 (Act) in the first 60 seconds of the video, Track 2 in the middle, Track 3 in the finale. Judges for each track should find their bullet list covered by name.

If the schedule slips, drop in this order: Track 3 specifics (decision lineage depth) → bitemporal polish → concurrency benchmark. Never drop: proof-carrying answers, A/B harness, deployed demo, video.
