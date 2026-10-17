"""Cycle-safe, level-synchronous graph walks.

Real dependency graphs (import graphs especially) contain cycles and dense clusters, where enumerating every
variable-length path explodes combinatorially (and FalkorDB aborts queries after its 1 s TIMEOUT). Instead each hop
is one Cypher expansion of the current frontier; the walk keeps the *shortest* path (with edge ids) to every node.
"""
from __future__ import annotations

from dataclasses import dataclass

from .base import ToolContext


@dataclass
class Reached:
    id: str
    name: str
    tier: int | None
    hops: int
    edge_ids: list[int]           # shortest path from the start node (in walk direction)
    names: list[str]              # node names along that path, start first


def walk(ctx: ToolContext, start_id: str, *, direction: str, depth: int, rel: str = "DEPENDS_ON",
         at: int | None = None) -> dict[str, Reached]:
    """Reach every Service from ``start_id`` within ``depth`` hops.

    direction='out': follows (start)-[rel]->(x)   (what the start depends on)
    direction='in' : follows (x)-[rel]->(start)   (what depends on the start)
    Only edges valid at ``at`` (default ctx.at) are followed.
    """
    at = ctx.at if at is None else at
    start = ctx.q("MATCH (s:Service {id:$id}) RETURN s.id AS id, s.name AS name, s.tier AS tier", {"id": start_id})
    if not start:
        return {}
    seen: dict[str, Reached] = {start_id: Reached(start_id, start[0]["name"], start[0]["tier"], 0, [], [start[0]["name"]])}
    frontier = [start_id]
    pattern = (f"(f:Service)-[r:{rel}]->(n:Service)" if direction == "out" else f"(n:Service)-[r:{rel}]->(f:Service)")
    for hop in range(1, depth + 1):
        if not frontier:
            break
        rows = ctx.q(f"MATCH {pattern} WHERE f.id IN $ids AND r.vf <= $at AND r.vt > $at "
                     "RETURN f.id AS fid, n.id AS nid, n.name AS nname, n.tier AS ntier, ID(r) AS eid "
                     "ORDER BY nid, fid", {"ids": frontier, "at": at})
        nxt: list[str] = []
        for r in rows:
            if r["nid"] in seen:
                continue
            parent = seen[r["fid"]]
            seen[r["nid"]] = Reached(r["nid"], r["nname"], r["ntier"], hop, parent.edge_ids + [r["eid"]],
                                     parent.names + [r["nname"]])
            nxt.append(r["nid"])
        frontier = nxt
    return seen
