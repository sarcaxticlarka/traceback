"""Dependency-graph tools: alerts, blast radius, dependencies, paths, PageRank, betweenness."""
from __future__ import annotations

from .base import Claim, ToolContext, ToolResult, tool
from .common import clamp_depth, fmt_ts


def sid(service: str) -> str:
    return service if service.startswith("svc:") else f"svc:{service}"


@tool("get_alert", "Look up an alert and the service it fired on.",
      {"alert_id": {"type": "string", "description": "e.g. alert:LIVE-1"}}, ["alert_id"], cypher_ref="Q0 get_alert")
def get_alert(ctx: ToolContext, alert_id: str) -> ToolResult:
    rows = ctx.q("MATCH (a:Alert {id:$id})-[f:FIRED_ON]->(s:Service) "
                 "RETURN a.id AS id, a.ts AS ts, a.severity AS severity, a.signal AS signal, a.summary AS summary, "
                 "s.id AS sid, s.name AS service, s.tier AS tier, ID(f) AS eid", {"id": alert_id})
    claims = [Claim(f"{r['service']} raised alert {r['id']} ({r['signal']}) at {fmt_ts(r['ts'])}",
                    edge_ids=[r["eid"]], node_ids=[r["id"]]) for r in rows]
    return ToolResult("get_alert", {}, rows, claims, summary=f"{len(rows)} alert row(s)")


@tool("blast_radius", "Services that transitively DEPEND ON the given service (what breaks if it fails), with hop counts. "
      "Valid at the current time only.",
      {"service": {"type": "string"}, "depth": {"type": "integer", "default": 4}}, ["service"],
      cypher_ref="Q1 blast_radius")
def blast_radius(ctx: ToolContext, service: str, depth: int = 4, max_claims: int = 8) -> ToolResult:
    n = clamp_depth(depth, 4)
    rows = ctx.q(f"MATCH p=(d:Service)-[:DEPENDS_ON*1..{n}]->(s:Service {{id:$sid}}) "
                 "WHERE ALL(r IN relationships(p) WHERE r.vf <= $at AND r.vt > $at) "
                 "RETURN d.id AS id, d.name AS name, d.tier AS tier, length(p) AS hops, "
                 "[r IN relationships(p) | ID(r)] AS eids, [x IN nodes(p) | x.name] AS names "
                 "ORDER BY hops LIMIT 6000", {"sid": sid(service), "at": ctx.at})
    best: dict[str, dict] = {}
    for r in rows:
        if r["id"] not in best:                          # rows arrive ordered by hops => first is shortest
            best[r["id"]] = r
    ranked = sorted(best.values(), key=lambda r: (r["hops"], r["tier"], r["name"]))
    claims = []
    for r in ranked[:max_claims]:
        chain = " → ".join(r["names"])
        via = f" ({r['hops']} hops: {chain})" if r["hops"] > 1 else ""
        claims.append(Claim(f"{r['name']} depends on {service.replace('svc:', '')}{via}", edge_ids=r["eids"]))
    out = [{"service": r["name"], "tier": r["tier"], "hops": r["hops"]} for r in ranked]
    return ToolResult("blast_radius", {}, out, claims,
                      summary=f"{len(ranked)} services depend on {service} within {n} hops "
                              f"({sum(1 for r in ranked if r['tier'] == 0)} tier-0, "
                              f"{sum(1 for r in ranked if r['tier'] == 1)} tier-1)")


@tool("dependencies", "Services the given service DEPENDS ON (its upstream/downstream suspects), with hop counts.",
      {"service": {"type": "string"}, "depth": {"type": "integer", "default": 2}}, ["service"],
      cypher_ref="Q1b dependencies")
def dependencies(ctx: ToolContext, service: str, depth: int = 2, max_claims: int = 10) -> ToolResult:
    n = clamp_depth(depth, 2)
    rows = ctx.q(f"MATCH p=(s:Service {{id:$sid}})-[:DEPENDS_ON*1..{n}]->(d:Service) "
                 "WHERE ALL(r IN relationships(p) WHERE r.vf <= $at AND r.vt > $at) "
                 "RETURN d.id AS id, d.name AS name, d.tier AS tier, length(p) AS hops, "
                 "[r IN relationships(p) | ID(r)] AS eids, [x IN nodes(p) | x.name] AS names "
                 "ORDER BY hops LIMIT 3000", {"sid": sid(service), "at": ctx.at})
    best: dict[str, dict] = {}
    for r in rows:
        best.setdefault(r["id"], r)
    ranked = sorted(best.values(), key=lambda r: (r["hops"], r["tier"], r["name"]))
    claims = []
    for r in ranked[:max_claims]:
        via = f" ({r['hops']} hops: {' → '.join(r['names'])})" if r["hops"] > 1 else ""
        claims.append(Claim(f"{service.replace('svc:', '')} depends on {r['name']}{via}", edge_ids=r["eids"]))
    return ToolResult("dependencies", {}, [{"service": r["name"], "hops": r["hops"]} for r in ranked], claims,
                      summary=f"{service} depends on {len(ranked)} services within {n} hops")


@tool("dependency_path", "Shortest dependency path from one service to another (how does A rely on B?).",
      {"from_service": {"type": "string"}, "to_service": {"type": "string"}}, ["from_service", "to_service"],
      cypher_ref="Q1c dependency_path")
def dependency_path(ctx: ToolContext, from_service: str, to_service: str) -> ToolResult:
    rows = ctx.q("MATCH p=(a:Service {id:$a})-[:DEPENDS_ON*1..6]->(b:Service {id:$b}) "
                 "WHERE ALL(r IN relationships(p) WHERE r.vf <= $at AND r.vt > $at) "
                 "RETURN length(p) AS hops, [r IN relationships(p) | ID(r)] AS eids, [x IN nodes(p) | x.name] AS names "
                 "ORDER BY hops LIMIT 1", {"a": sid(from_service), "b": sid(to_service), "at": ctx.at})
    if not rows:
        return ToolResult("dependency_path", {}, [], [], summary="no dependency path")
    r = rows[0]
    claim = Claim(f"{r['names'][0]} depends on {r['names'][-1]} through {' → '.join(r['names'])} ({r['hops']} hops)",
                  edge_ids=r["eids"])
    return ToolResult("dependency_path", {}, [{"hops": r["hops"], "path": r["names"]}], [claim],
                      summary=f"path of {r['hops']} hops")


@tool("criticality", "Rank services by PageRank over the dependency graph (most relied-upon first).",
      {"top": {"type": "integer", "default": 10}}, [], cypher_ref="Q7 criticality (algo.pageRank)", writes=False)
def criticality(ctx: ToolContext, top: int = 10) -> ToolResult:
    ctx.q("CALL algo.pageRank('Service','DEPENDS_ON') YIELD node, score SET node.pr_score = score RETURN count(node) AS n")
    rows = ctx.q("MATCH (s:Service) RETURN s.id AS id, s.name AS name, s.tier AS tier, s.pr_score AS score "
                 "ORDER BY score DESC LIMIT $top", {"top": clamp_depth(top, 10, 50)})
    claims = [Claim(f"{r['name']} is criticality rank {i + 1} by PageRank (score {r['score']:.4f})",
                    node_ids=[r["id"]], assert_props=[{"node_id": r["id"], "prop": "pr_score", "value": r["score"]}])
              for i, r in enumerate(rows)]
    return ToolResult("criticality", {}, rows, claims, summary=f"top {len(rows)} by PageRank")


@tool("single_points_of_failure", "Rank services by betweenness centrality: chokepoints that many dependency paths cross.",
      {"top": {"type": "integer", "default": 5}}, [], cypher_ref="Q8 spof (algo.betweenness)")
def single_points_of_failure(ctx: ToolContext, top: int = 5) -> ToolResult:
    ctx.q("CALL algo.betweenness({nodeLabels:['Service'], relationshipTypes:['DEPENDS_ON']}) "
          "YIELD node, score SET node.bt_score = score RETURN count(node) AS n")
    rows = ctx.q("MATCH (s:Service) RETURN s.id AS id, s.name AS name, s.tier AS tier, s.bt_score AS score "
                 "ORDER BY score DESC LIMIT $top", {"top": clamp_depth(top, 5, 50)})
    claims = [Claim(f"{r['name']} is a chokepoint, betweenness {r['score']:.2f}", node_ids=[r["id"]],
                    assert_props=[{"node_id": r["id"], "prop": "bt_score", "value": r["score"]}]) for r in rows]
    return ToolResult("single_points_of_failure", {}, rows, claims, summary=f"top {len(rows)} chokepoints")
