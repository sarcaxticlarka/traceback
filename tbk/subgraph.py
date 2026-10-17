"""Evidence subgraphs for the UI: the exact nodes/edges an answer cited, plus the live service map."""
from __future__ import annotations

from .config import NOW
from .tools import ToolContext
from .tools.common import edge_facts

_LABEL_NAME = "coalesce(n.name, n.title, n.statement, n.text, n.id)"


def _node_rows(ctx: ToolContext, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    rows = ctx.q(f"MATCH (n) WHERE n.id IN $ids RETURN n.id AS id, labels(n)[0] AS label, {_LABEL_NAME} AS name, "
                 "n.sha AS sha, n.tier AS tier", {"ids": ids})
    return {r["id"]: r for r in rows}


def evidence_subgraph(tenant: str, edge_ids: list[int], node_ids: list[str] | None = None) -> dict:
    ctx = ToolContext(tenant, NOW)
    facts = edge_facts(ctx, sorted(set(edge_ids)))
    ids = {f["aid"] for f in facts.values()} | {f["bid"] for f in facts.values()} | set(node_ids or [])
    nodes = _node_rows(ctx, sorted(ids))
    return {
        "nodes": [{"id": n["id"], "label": n["label"], "name": f"deploy {n['sha']}" if n["label"] == "Deploy" else n["name"],
                   "tier": n["tier"]} for n in nodes.values()],
        "edges": [{"id": f["id"], "source": f["aid"], "target": f["bid"], "type": f["type"], "vf": f["vf"], "vt": f["vt"]}
                  for f in facts.values()],
    }


def service_map(tenant: str, at: int = NOW) -> dict:
    ctx = ToolContext(tenant, at)
    nodes = ctx.q("MATCH (s:Service) RETURN s.id AS id, s.name AS name, s.tier AS tier, s.layer AS layer, "
                  "coalesce(s.pr_score, 0.0) AS pr")
    edges = ctx.q("MATCH (a:Service)-[r:DEPENDS_ON]->(b:Service) WHERE r.vf <= $at AND r.vt > $at "
                  "RETURN ID(r) AS id, a.id AS source, b.id AS target", {"at": at})
    return {"nodes": nodes, "edges": [dict(e, type="DEPENDS_ON") for e in edges]}


def overview(tenant: str) -> dict:
    ctx = ToolContext(tenant, NOW)
    counts = ctx.q("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS n ORDER BY n DESC")
    edges = ctx.q("MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"]
    types = ctx.q("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS n ORDER BY n DESC")
    return {"tenant": tenant, "nodes": counts, "edges": edges, "edge_types": types}
