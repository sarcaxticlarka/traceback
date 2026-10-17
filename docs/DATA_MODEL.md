# Graph data model

One FalkorDB graph per tenant (`t_helix`, `t_orbit`). Time-varying relationships carry `vf` (valid from) and `vt`
(valid to; `4102444800` = open-ended), as epoch seconds. A query "as of t" keeps edges with `vf <= t < vt`.

```mermaid
graph LR
  Person -- "MEMBER_OF {vf,vt}" --> Team
  Team -- "OWNS {vf,vt}" --> Service
  Service -- "DEPENDS_ON {vf,vt}" --> Service
  Person -- AUTHORED --> Deploy
  Deploy -- DEPLOYED_TO --> Service
  Alert -- FIRED_ON --> Service
  Incident -- TRIGGERED_BY --> Alert
  Incident -- AFFECTED --> Service
  Incident -- CAUSED_BY --> Deploy
  Incident -- RESOLVED_BY --> Person
  Incident -- "FIXED_WITH {result}" --> Runbook
  Incident -- DOCUMENTED_IN --> Doc
  Runbook -- FOR_SIGNAL --> Signal
  Decision -- CONSTRAINS --> Service
  Decision -- SUPERSEDES --> Decision
  Decision -- DECIDED_IN_DOC --> Doc
  Doc -- DERIVED_FROM --> Source
  Doc -- "MENTIONS_SERVICE / MENTIONS_PERSON" --> Service
  Fact -- ABOUT_SERVICE --> Service
  Fact -- SUPERSEDES --> Fact
  Fact -- SUPPORTED_BY --> Source
  Agent -- RAN --> Episode
  Episode -- ABOUT --> Incident
  Episode -- "CALLED {order}" --> ToolCall
  Episode -- "OUTCOME {result}" --> Runbook
  Task -- FOR --> Incident
  Task -- BLOCKED_BY --> Task
  Task -- PRODUCED --> Finding
  Agent -- PROPOSED --> Action
  Action -- FOR --> Incident
  Action -- TARGETS --> Person
```

## Nodes

| Label | Key properties | Role |
|---|---|---|
| `Service` | `id` (`svc:name`), `name`, `tier` 0-3, `layer`, `pr_score`, `bt_score` | topology; PageRank/betweenness are materialised by the algorithm tools |
| `Person`, `Team` | `id`, `name` | ownership and expertise |
| `Deploy` | `sha`, `ts`, `status` | change events |
| `Alert`, `Incident` | `ts`, `severity`, `signal`, `embedding` (Incident) | events; incidents are vector-indexed |
| `Doc`, `Source` | `kind` (readme/runbook/postmortem/adr/chat), `title`, `body`, `embedding` | knowledge; every `Doc` points to a `Source` (provenance) |
| `Decision`, `Fact` | `statement`/`text`, `vf`, `vt` | institutional memory with validity |
| `Runbook`, `Signal` | `attempts`, `successes`, `last_used` | procedural memory |
| `Agent`, `Episode`, `ToolCall` | `ts`, `goal`, `outcome`, `latency_ms`; `tool`, `args`, `n_claims` | episodic memory |
| `Task`, `Finding`, `Action` | `status`, `priority`; `payload` (JSON), `grounded_pct`; `risk`, `status` | coordination and acting |

Notes: FalkorDB has no label expressions, so "either/or" edge targets are separate relationship types
(`MENTIONS_SERVICE`, `MENTIONS_PERSON`, `ABOUT_SERVICE`, `ABOUT_PERSON`). Lists/maps are stored as JSON strings
where needed (`Finding.payload`, `ToolCall.args`).

## Indexes

Range index on `id` for every label; `Task.status`, `Deploy.ts`, `Alert.live`, `Doc.kind`, `Episode.ts`;
vector indexes (cosine, dim 256) on `Doc.embedding` and `Incident.embedding`. See `tbk/seed/load.py`.

## Planted facts (so evaluation and demos have something real to find)

6 ownership transfers (some READMEs left stale) · 4 services owned by a team with no remaining members · 8 dependency
edges ended mid-history · 12 decision chains (1-4 long) · 8 escalation-contact facts that supersede each other ·
8 signals × 2 runbooks with hidden success rates · 5 live alerts whose cause is one deploy 0-2 dependency hops away,
with in-scope older decoys and out-of-scope recent decoys (so "latest deploy overall" is wrong).
