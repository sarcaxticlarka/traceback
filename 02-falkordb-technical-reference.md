# 02 — FalkorDB Technical Reference (verified vs. unverified)

Everything under **VERIFIED** came from FalkorDB docs fetched on 2026-10-17. Everything under **UNVERIFIED** must be tested before you depend on it. Do the 30-minute spike in doc 05 first.

## VERIFIED

### Run it
```bash
docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest
```
(`docker pull falkordb/falkordb:latest` is quoted on the event page; port 3000 serves FalkorDB Browser in the combined image per the Graphiti docs.) FalkorDB speaks the Redis protocol on 6379. Official clients: Python, Node.js, Java, Rust, Go, PHP, C#.

### Python client
```python
from falkordb import FalkorDB
db = FalkorDB(host='localhost', port=6379)
g = db.select_graph('tenant_acme')          # one instance, many isolated graphs
res = g.query("MATCH (n) RETURN count(n)")
for row in res.result_set: print(row)
```
Query parameters: prefix form `CYPHER name='Alice' MATCH (n {name: $name}) RETURN n` (the client handles this when you pass `params`; confirm in your client version).

### Multi-graph = multi-tenancy
One FalkorDB instance can hold thousands of isolated graphs (stated on the event page and in the agentic-memory docs). This is your tenant and per-agent isolation primitive. Different frameworks can share an instance using different graph names.

### Cypher
FalkorDB implements a **subset of OpenCypher** with extensions. Listed clauses: MATCH, OPTIONAL MATCH, WHERE, RETURN, ORDER BY, SKIP, LIMIT, CREATE, MERGE, DELETE, REMOVE, SET, WITH, UNION, UNWIND, FOREACH, CALL {}. Comments `//` and `/* */`. Three index types: range, full-text (via RediSearch, with stemming and scoring), vector.

### Vector index
```cypher
CREATE VECTOR INDEX FOR (d:Doc) ON (d.embedding)
OPTIONS {dimension:768, similarityFunction:'cosine', M:32, efConstruction:200}
```
- `dimension` 1–4096 (required); `similarityFunction` `'euclidean'` or `'cosine'` (required); `M` default 16; `efConstruction` default 200; `efRuntime` default 10 (tunable per query).
- Insert: `CREATE (d:Doc {text:$t, embedding: vecf32($vec)})`
- Query:
```cypher
CALL db.idx.vector.queryNodes('Doc', 'embedding', 10, vecf32($qvec)) YIELD node, score
```
- Also `db.idx.vector.queryRelationships` for edges.
- Caveats from docs: results approximate; **vector queries don't combine well with property filters** (so filter *after* retrieval or traverse from the hits); memory ≈ vectors × dims × 4 bytes + ~20%.

### Algorithms (all `CALL algo.<name>(...) YIELD ...`)
- Pathfinding: BFS, SPpath, A*, SSpath, MSF
- Centrality: PageRank, Betweenness, Harmonic
- Community: WCC, CDLP
- Flow: MaxFlow
- Most take optional `nodeLabels` / `relationshipTypes` filters.

**Verified exact syntax:**
```cypher
CALL algo.pageRank('Service', 'DEPENDS_ON') YIELD node, score
RETURN node.name, score ORDER BY score DESC
```
(label and relationship-type both optional; yields `node`, `score`.)

The FAQ names `algo.SPpaths` and `algo.SSpaths` for shortest-path and single-source paths.

### Known Cypher limitations (use these to avoid debugging at 3 AM)
1. A relationship in a pattern not referenced elsewhere only checks "at least one matching relation exists". If you need distinct edges, reference the alias (workaround: `WHERE ID(e) >= 0`).
2. `LIMIT` does **not** stop eager operations: CREATE/SET/DELETE/MERGE and aggregating projections execute fully first. Don't use `UNWIND … CREATE … LIMIT 1` expecting one node.
3. `<>` filters aren't index-optimised. Check with `GRAPH.EXPLAIN`.
4. No aggregation functions (`count/sum/avg`) inside pattern comprehensions; aggregate in a prior `WITH`/`RETURN` or use `size()` on a list comprehension.
5. "Label expressions are not yet supported" (e.g. `:A|B`). Query labels separately or use `UNION`.

### Agent-memory ecosystem (documented by FalkorDB)
- **Graphiti** — temporally-aware knowledge graph for multi-agent persistent memory.
- **Graphiti MCP Server** — experimental; for Claude Desktop/Cursor/VS Code. Combined image runs FalkorDB + MCP.
  - Endpoints: FalkorDB 6379, Browser http://localhost:3000, MCP http://localhost:8000/mcp/, health /health.
  - Tools: `add_episode`, `search_nodes`, `search_facts`, `get_entity_edge`, `get_episodes`, `delete_entity_edge`, `delete_episode`, `clear_graph`. Arg schemas not documented → introspect the server's tool list.
  - Schema: `Entity {name, entity_type, summary}`, `Episode {name, content, timestamp, source}`; edges `RELATES_TO`, `MENTIONED_IN`, `OCCURRED_AFTER`.
  - Needs an LLM key (OpenAI default; Anthropic/Google/Groq/Azure possible). 429s → lower `SEMAPHORE_LIMIT`. Containers lose data on restart without a volume.
  - No REST API; only `/mcp/` and `/health`.
- **Cognee** (graph+vector memory), **Mem0** (graph memory backend, per-user isolation).
- Other integrations named on the site: GraphRAG-SDK, QueryWeaver (graph-powered text-to-SQL), MCP, LangChain, LlamaIndex.

**Strategic note:** these frameworks exist, so judges will have seen "Graphiti + FalkorDB" many times. Using Graphiti as your *whole* memory layer is the average entry. Your own temporal/provenance schema, with Graphiti at most as an optional ingest comparison, is what differentiates and also satisfies rule 9 ("original work is judged").

## UNVERIFIED — test in the first hour

| Item | Why it matters | 30-second test |
|---|---|---|
| Exact names/args of `algo.WCC`, `algo.betweenness`, `algo.CDLP`, `algo.SPpaths`, `algo.BFS` | Your tools layer calls them | In Browser run `CALL dbms.procedures()` (or `SHOW PROCEDURES`; one of these lists them) and copy exact names |
| `shortestPath()` / `allShortestPaths()` in MATCH | Escalation-path and "how are A and B connected" | `MATCH p=shortestPath((a)-[*..6]-(b)) RETURN p` on toy data |
| Variable-length traversal performance on ~10–50k edges | Blast-radius query speed in the live demo | Generate the synthetic graph, time `MATCH (s:Service{name:$n})<-[:DEPENDS_ON*1..6]-(d) RETURN DISTINCT d` |
| Storing arrays/maps as properties | Evidence payloads on nodes | Try `SET n.tags=['a','b']`; maps are generally NOT supported as properties → store JSON string |
| Datetime handling | Bitemporal edges | Store epoch ints (`valid_from`, `valid_to`) to avoid surprises |
| Concurrency behaviour under parallel writers | Track 2 claim | Run 50 concurrent `MERGE` writers on separate and same graphs; record throughput |
| FalkorDB Cloud free-tier limits | Deployment | Check cloud console: memory cap, connection string format, TLS |
| `GRAPH.EXPLAIN` / `GRAPH.PROFILE` availability via client | Evidence for README ("we use indexes") | `g.explain(query)` / `g.profile(query)` in Python client |

## Handy Cypher patterns to test immediately

```cypher
// idempotent upsert (use for ingestion)
MERGE (s:Service {id:$id}) SET s.name=$name, s.tier=$tier

// range index for lookups
CREATE INDEX FOR (s:Service) ON (s.id)
// full-text
CALL db.idx.fulltext.createNodeIndex('Doc','title','body')
CALL db.idx.fulltext.queryNodes('Doc', 'timeout redis') YIELD node, score
```
(Full-text procedure names are from memory of the RediSearch-backed API; verify.)
