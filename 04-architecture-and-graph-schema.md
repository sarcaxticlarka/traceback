# 04 — Architecture & Graph Schema

## Stack (optimise for speed, not novelty)

| Layer | Choice | Why |
|---|---|---|
| Graph | FalkorDB (Docker locally; FalkorDB Cloud or a VM container for deploy) | Required |
| Backend | Python 3.11 + FastAPI | `falkordb` client + MCP Python SDK + LLM SDK are all first-class |
| Agents | Hand-rolled tool loop (≈150 lines) on the Claude API with tool use | Keeps logic visible and defensible (rule 12); avoid heavy frameworks you can't explain |
| LLM | Claude (disclose in README). Cheaper model for phrasing/extraction, stronger for planning | Model IDs: check current list before coding |
| Embeddings | One embedding model (any); store as `vecf32` | Needed for the vector baseline and for hybrid similar-incident search |
| MCP | Python MCP server exposing the graph tools | Satisfies "tool selection through MCP" |
| Frontend | React + Vite + `react-force-graph` or Cytoscape.js | You already work in React; subgraph replay animation is easy |
| Deploy | Frontend on Vercel/Netlify; API + FalkorDB on one Render/Fly/Railway/VM service, or API + FalkorDB Cloud | Pick one by H6 and deploy a hello-world to it immediately |
| Data | `seed/generate.py`, deterministic with a seed → reproducible ground truth for evals | Rule 6 (synthetic) + eval correctness |

Monorepo layout:
```
traceback/
  README.md                 # data model, queries, setup, AI-usage, track mapping
  docker-compose.yml        # falkordb + api (+ web)
  seed/generate.py          # synthetic company, 2 tenants, ground-truth Q&A
  seed/docs/                # generated runbooks, postmortems, ADRs, chat threads (markdown)
  api/
    graph.py                # FalkorDB access, tenant→graph routing
    tools.py                # the named queries/algorithms (single source of truth)
    mcp_server.py           # same tools over MCP
    agents/{triage,investigator,remediator}.py
    verifier.py             # proof-carrying check
    memory.py               # episodic/semantic/procedural writers + readers
    scheduler.py            # next-ready-task query
  eval/{questions.json,run_graph.py,run_vector.py,grade.py,results.md}
  bench/bench_concurrency.py
  tests/test_isolation.py tests/test_verifier.py
  web/                      # incident console
  QUERIES.md                # every Cypher query the product depends on (submission requirement)
```

## Tenant model

- **Company graph per tenant:** `t_helix`, `t_orbit` (operational data + knowledge + memory for that tenant).
- **Agent scratch (optional):** `t_helix__agent_triage` for private working memory if you want to demonstrate agent-level isolation. Shared state lives in the tenant graph via `Task` nodes.
- `graph.py::g(tenant)` is the **only** way to obtain a graph handle; every tool takes `tenant` and has no way to reach another graph. The isolation test calls every tool for both tenants and asserts disjoint `node_ids`.

## Graph data model

### Operational / company knowledge
```
(:Person   {id, name, role, email_hash})
(:Team     {id, name})
(:Service  {id, name, tier, lang})                # tier 0..3 (0 = most critical)
(:Deploy   {id, sha, ts, status, summary})
(:Alert    {id, ts, severity, signal, summary})
(:Incident {id, ts_open, ts_close, severity, title, summary, embedding})
(:Ticket   {id, title, status, ts})
(:Doc      {id, kind, title, body, ts, embedding})  # kind: runbook|postmortem|adr|chat|readme
(:Decision {id, statement, ts})
(:Source   {id, kind, uri, ts})                   # provenance anchor

(:Person)-[:MEMBER_OF {valid_from, valid_to}]->(:Team)
(:Team)-[:OWNS {valid_from, valid_to}]->(:Service)
(:Service)-[:DEPENDS_ON {valid_from, valid_to, kind}]->(:Service)
(:Person)-[:AUTHORED]->(:Deploy)-[:DEPLOYED_TO]->(:Service)
(:Alert)-[:FIRED_ON]->(:Service)
(:Incident)-[:TRIGGERED_BY]->(:Alert)
(:Incident)-[:AFFECTED]->(:Service)
(:Incident)-[:CAUSED_BY]->(:Deploy)
(:Incident)-[:RESOLVED_BY]->(:Person)
(:Incident)-[:DOCUMENTED_IN]->(:Doc)
(:Ticket)-[:ABOUT]->(:Service)
(:Decision)-[:DECIDED_IN]->(:Doc|:Ticket)         # two edge types in practice: DECIDED_IN_DOC / DECIDED_IN_TICKET
(:Decision)-[:SUPERSEDES]->(:Decision)
(:Decision)-[:CONSTRAINS]->(:Service)
(:Doc)-[:MENTIONS]->(:Service|:Person)            # likewise split by target label (no label expressions)
(:Doc)-[:DERIVED_FROM]->(:Source)
```
FalkorDB lacks label expressions, so model "either/or" targets as distinct relationship types or a shared super-label (e.g. also give Doc and Ticket the label `:Artifact`).

### Memory layer
```
(:Agent    {id, kind})                                      # triage | investigator | remediator
(:Episode  {id, ts, goal, outcome, latency_ms})             # episodic
(:Agent)-[:RAN]->(:Episode)-[:ABOUT]->(:Incident)
(:Episode)-[:CALLED {order, args_json}]->(:ToolCall {id, tool, result_hash})
(:Episode)-[:USED]->(:Runbook)
(:Episode)-[:OUTCOME {result:'success|fail', ts}]->(:Runbook)

(:Fact {id, text, confidence, valid_from, valid_to, recorded_at})   # semantic
(:Fact)-[:ABOUT]->(:Service|:Person…)                               # split by target label
(:Fact)-[:SUPPORTED_BY]->(:Source)
(:Fact)-[:SUPERSEDES]->(:Fact)

(:Runbook {id, title, attempts, successes, last_used})      # procedural
(:Runbook)-[:FOR_SIGNAL]->(:Signal {name})
(:Runbook)-[:FIXES]->(:Service)

(:Task {id, kind, status, created_ts})                      # coordination
(:Task)-[:ASSIGNED_TO]->(:Agent)
(:Task)-[:BLOCKED_BY]->(:Task)
(:Task)-[:FOR]->(:Incident)
(:Task)-[:PRODUCED]->(:Finding {id, text, confidence})
(:Finding)-[:SUPPORTED_BY_EDGE {edge_id}]->(:Evidence {id, edge_ids_json})   # evidence pins for verifier

(:Action {id, kind, status, risk, ts})                      # stretch
(:Action)-[:PROPOSED_BY]->(:Agent), (:Action)-[:APPROVED_BY]->(:Person)
```
Property storage: strings, numbers, booleans, vectors (`vecf32`). Store lists/maps as JSON strings to be safe; timestamps as epoch ints.

### Indexes
```cypher
CREATE INDEX FOR (s:Service) ON (s.id)
CREATE INDEX FOR (p:Person) ON (p.id)
CREATE INDEX FOR (i:Incident) ON (i.id)
CREATE INDEX FOR (t:Task) ON (t.status)
CREATE VECTOR INDEX FOR (i:Incident) ON (i.embedding) OPTIONS {dimension:768, similarityFunction:'cosine'}
CREATE VECTOR INDEX FOR (d:Doc) ON (d.embedding) OPTIONS {dimension:768, similarityFunction:'cosine'}
```
(match `dimension` to your embedding model.)

## Core queries (the ones QUERIES.md must list)

Validate each in FalkorDB Browser before wiring; see doc 02 for known limitations.

```cypher
// Q1 blast radius: everything that transitively depends on a failing service (valid at $t)
MATCH (s:Service {id:$sid})
MATCH p=(d:Service)-[:DEPENDS_ON*1..6]->(s)
WHERE ALL(r IN relationships(p) WHERE r.valid_from <= $t AND (r.valid_to IS NULL OR r.valid_to > $t))
RETURN d.id AS service, d.tier AS tier, min(length(p)) AS hops
ORDER BY tier, hops

// Q2 recent changes near an alert: deploys to the service or its direct dependencies
MATCH (s:Service {id:$sid})
OPTIONAL MATCH (dep:Service)<-[:DEPENDS_ON]-(s)
WITH s, collect(dep) + [s] AS scope
UNWIND scope AS x
MATCH (a:Person)-[:AUTHORED]->(d:Deploy)-[:DEPLOYED_TO]->(x)
WHERE d.ts >= $since AND d.ts <= $t
RETURN x.id AS service, d.id AS deploy, d.sha, d.ts, a.id AS author
ORDER BY d.ts DESC

// Q3 who owns it (as of t) and who actually knows it (inferred expertise)
MATCH (t:Team)-[o:OWNS]->(s:Service {id:$sid})
WHERE o.valid_from <= $t AND (o.valid_to IS NULL OR o.valid_to > $t)
OPTIONAL MATCH (p:Person)-[m:MEMBER_OF]->(t)
WHERE m.valid_from <= $t AND (m.valid_to IS NULL OR m.valid_to > $t)
RETURN t.name AS team, collect(p.name) AS members

MATCH (p:Person)-[:AUTHORED]->(:Deploy)-[:DEPLOYED_TO]->(s:Service {id:$sid})
WITH p, count(*) AS deploys
OPTIONAL MATCH (i:Incident)-[:RESOLVED_BY]->(p), (i)-[:AFFECTED]->(:Service {id:$sid})
RETURN p.name AS person, deploys, count(i) AS incidents_resolved,
       deploys + 3*count(i) AS expertise
ORDER BY expertise DESC LIMIT 5

// Q4 structurally + semantically similar past incidents (hybrid)
CALL db.idx.vector.queryNodes('Incident','embedding',20,vecf32($qvec)) YIELD node AS inc, score
MATCH (inc)-[:AFFECTED]->(s:Service)<-[:DEPENDS_ON*0..2]-(:Service {id:$sid})
RETURN DISTINCT inc.id AS incident, inc.title, score
ORDER BY score LIMIT 5
// NOTE: vector index + property filter combine poorly → retrieve first, then traverse (as above).

// Q5 runbook ranking (procedural memory)
MATCH (rb:Runbook)-[:FOR_SIGNAL]->(:Signal {name:$signal})
OPTIONAL MATCH (rb)-[:FIXES]->(s:Service {id:$sid})
RETURN rb.id, rb.title, rb.attempts, rb.successes,
       (rb.successes + 1.0) / (rb.attempts + 2.0) AS success_rate,
       CASE WHEN s IS NULL THEN 0 ELSE 1 END AS service_match
ORDER BY service_match DESC, success_rate DESC LIMIT 3

// Q6 update procedural memory from an episode outcome (called by Remediator)
MATCH (e:Episode {id:$eid})-[:USED]->(rb:Runbook)
SET rb.attempts = rb.attempts + 1,
    rb.successes = rb.successes + $ok,
    rb.last_used = $now
CREATE (e)-[:OUTCOME {result:$result, ts:$now}]->(rb)

// Q7 criticality (algorithm as tool)
CALL algo.pageRank('Service','DEPENDS_ON') YIELD node, score
RETURN node.id AS service, score ORDER BY score DESC LIMIT 10

// Q8 single points of failure (name/args to be confirmed in doc 02 spike)
// CALL algo.betweenness(...) YIELD node, score RETURN node.id, score ORDER BY score DESC

// Q9 decision lineage: why is the service the way it is?
MATCH (s:Service {id:$sid})<-[:CONSTRAINS]-(d:Decision)
OPTIONAL MATCH (d)-[:SUPERSEDES*0..5]->(old:Decision)
OPTIONAL MATCH (d)-[:DECIDED_IN_DOC]->(doc:Doc)-[:DERIVED_FROM]->(src:Source)
RETURN d.statement, d.ts, collect(DISTINCT old.statement) AS superseded, doc.title, src.uri
ORDER BY d.ts DESC

// Q10 coordination: next ready task (no unfinished blockers)
MATCH (t:Task {status:'ready'})-[:FOR]->(:Incident {id:$iid})
OPTIONAL MATCH (t)-[:BLOCKED_BY]->(b:Task) WHERE b.status <> 'done'
WITH t, count(b) AS open_blockers
WHERE open_blockers = 0
RETURN t.id, t.kind ORDER BY t.created_ts LIMIT 1
// Claim atomically: MATCH (t:Task {id:$id, status:'ready'}) SET t.status='running' RETURN t.id
// (check returned row count; if 0 someone else claimed it)

// Q11 verifier: re-fetch claimed edges and check validity at t
MATCH (a)-[r]->(b) WHERE ID(r) IN $edge_ids
RETURN ID(r) AS id, type(r) AS type, ID(a) AS src, ID(b) AS dst,
       r.valid_from AS vf, r.valid_to AS vt
```

## Agent loop (small enough to defend line by line)

```
Triage:        alert → create Task(investigate) with FOR→Incident; write Episode
Investigator:  claim Task → loop: LLM picks tool (MCP) → run → record ToolCall + evidence edge ids
               → emit Findings = structured claims over evidence → verifier → store Verified Findings
               → create Task(remediate) BLOCKED_BY investigate
Remediator:    claim Task → rank_runbooks + risk(blast, pagerank) → propose Action
               → (approval gate if risk high) → execute (simulated) → write OUTCOME → update Runbook stats
               → write Fact(s) learned, with SUPPORTED_BY → Source
```

## Verifier rules (precise, so you can explain them)
1. Each claim has `edge_ids` (non-empty) or is tagged `inference` and excluded from "Grounded %".
2. All edge ids exist in the tenant graph; none belong to another graph (guaranteed by routing).
3. Temporal validity at query time `t` holds for every edge with `valid_from`/`valid_to`.
4. Claim text is generated from a **template keyed by edge types** (`"{a} depends on {b}"`), and the LLM may only rephrase; the verifier compares entity names in the final sentence against the entities of the cited edges and rejects extras.
5. Grounded % = grounded claims / total claims proposed (including rejected ones, so the number is honest).

## Evaluation design
- Ground truth from construction: `generate.py` emits `questions.json` with the true answer set (e.g. exact set of services in the 3-hop blast radius, true last owner on date X).
- Question buckets: 1-hop (owner of X), 2-hop (who deployed to deps of X last week), 3-hop (teams whose services transitively depend on X), 4+-hop / temporal (decision chain, as-of ownership).
- Baseline: chunk docs, embed, top-k, ask the same LLM with the same prompt budget. No graph.
- Metric: exact-match / set F1 against ground truth + grounded %. Chart by hop bucket.
- Run each system 3×, report mean and spread.

## Synthetic data spec (make it feel real)
- 2 tenants × (60–120 services, 40 people, 8 teams, 600 deploys, 120 incidents, 80 tickets, 150 docs).
- Dependency graph with realistic skew: a few hub services (auth, db proxy, message bus) with high in-degree so PageRank/betweenness give meaningful answers.
- Planted facts for evals: ownership transfers, a renamed service, a deprecated dependency, 3 superseded decisions, 2 recurring incident patterns (so procedural memory has something to learn), a couple of "ghost owner" services (owner left the company → ownership-gap detection).
- Docs generated by templates + light LLM paraphrase, saved to `seed/docs/` and committed so the dataset is reproducible without an API key.
- Same service names across tenants to stress isolation tests.
