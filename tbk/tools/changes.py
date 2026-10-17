"""Change-correlation tool: deploys near an alert, across the service's dependency scope."""
from __future__ import annotations

from .base import Claim, ToolContext, ToolResult, tool
from .common import clamp_depth, fmt_ts
from .topology import sid
from .walk import walk


@tool("recent_changes",
      "Deploys in the last N hours to the service or anything it depends on (up to `depth` hops), with the author and the "
      "dependency path that connects the deployed service to the alerting one. Prime suspects for root cause.",
      {"service": {"type": "string"}, "window_hours": {"type": "integer", "default": 24},
       "depth": {"type": "integer", "default": 2}}, ["service"], cypher_ref="Q2 recent_changes")
def recent_changes(ctx: ToolContext, service: str, window_hours: int = 24, depth: int = 2) -> ToolResult:
    n = clamp_depth(depth, 2, 4)
    since = ctx.at - int(window_hours) * 3600
    scope = walk(ctx, sid(service), direction="out", depth=n)
    rows = ctx.q(
        "MATCH (a:Person)-[au:AUTHORED]->(d:Deploy)-[dp:DEPLOYED_TO]->(x:Service) "
        "WHERE x.id IN $ids AND d.ts >= $since AND d.ts <= $at "
        "RETURN d.id AS did, d.sha AS sha, d.ts AS ts, d.status AS status, x.id AS xid, x.name AS svc, a.name AS author, "
        "a.id AS aid, ID(au) AS au, ID(dp) AS dp ORDER BY ts DESC LIMIT 400",
        {"ids": list(scope), "at": ctx.at, "since": since})
    for r in rows:
        reach = scope[r["xid"]]
        r.update(hops=reach.hops, eids=reach.edge_ids, names=reach.names)
    best: dict[str, dict] = {}
    for r in rows:
        best.setdefault(r["did"], r)
    ranked = sorted(best.values(), key=lambda r: (r["hops"], -r["ts"]))
    claims, out = [], []
    for r in ranked:
        via = "" if r["hops"] == 0 else f"; {service.replace('svc:', '')} reaches {r['svc']} via {' → '.join(r['names'])}"
        text = f"deploy {r['sha']} to {r['svc']} by {r['author']} at {fmt_ts(r['ts'])}{via}"
        claims.append(Claim(text, edge_ids=[r["au"], r["dp"]] + r["eids"], node_ids=[r["did"]]))
        out.append({"deploy": r["did"], "sha": r["sha"], "service": r["svc"], "author": r["author"],
                    "author_id": r["aid"], "ts": r["ts"], "hops": r["hops"]})
    return ToolResult("recent_changes", {}, out, claims,
                      summary=f"{len(ranked)} deploy(s) in the last {window_hours}h within {n} hops of {service}")
