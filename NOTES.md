# Phase 0 spike results (FalkorDB, verified locally on `falkordb/falkordb:latest`)

Run: `python spike/spike.py` (needs FalkorDB on port 6390).

| Capability | Result |
|---|---|
| Algorithms | `algo.AStar, betweenness, BFS, HarmonicCentrality, labelPropagation, maxFlow, MSF, pageRank, SPpaths, SSpaths, WCC` all present (`CALL dbms.procedures()`) |
| `algo.pageRank('Label','REL')` | works, yields `node, score` |
| `algo.WCC()` | yields `node, componentId` |
| `algo.betweenness({nodeLabels:[..], relationshipTypes:[..]})` | works, yields `node, score` |
| `algo.BFS(startNode, maxDepth, relType)` | works, yields `nodes, edges` |
| `shortestPath` | **only allowed in WITH/RETURN**: `MATCH (a),(b) WITH shortestPath((a)-[:R*]->(b)) AS p RETURN length(p)` |
| Variable-length paths + `ALL(r IN relationships(p) WHERE ...)` | works |
| `ID(r)` on edges, `IN [..]` | works |
| Vector index + `db.idx.vector.queryNodes` | works; **score is a distance (lower = closer)** |
| Full-text `db.idx.fulltext.createNodeIndex/queryNodes` | present |
| List properties | accepted |
| `g.explain()` | works |
| Query params | work via client |

Local ports: our container `traceback-falkordb` uses 6390 (redis) and 3010 (Browser UI) so it doesn't collide with another FalkorDB already on 6379/3000.
