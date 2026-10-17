"""Ownership and expertise tools (who owns it, who knows it, who has been orphaned)."""
from __future__ import annotations

from .base import Claim, ToolContext, ToolResult, tool
from .common import fmt_day
from .topology import sid


@tool("owners_of", "Team that owns a service (valid at the current time) and that team's current members.",
      {"service": {"type": "string"}, "as_of": {"type": "integer", "description": "optional epoch seconds"}},
      ["service"], cypher_ref="Q3a owners_of")
def owners_of(ctx: ToolContext, service: str, as_of: int | None = None) -> ToolResult:
    at = int(as_of) if as_of else ctx.at
    rows = ctx.q(
        "MATCH (t:Team)-[o:OWNS]->(s:Service {id:$sid}) WHERE o.vf <= $at AND o.vt > $at "
        "OPTIONAL MATCH (p:Person)-[m:MEMBER_OF]->(t) WHERE m.vf <= $at AND m.vt > $at "
        "RETURN t.id AS tid, t.name AS team, ID(o) AS oid, p.id AS pid, p.name AS person, ID(m) AS mid, s.name AS svc",
        {"sid": sid(service), "at": at})
    claims, members = [], []
    seen_team = set()
    for r in rows:
        if r["tid"] not in seen_team:
            seen_team.add(r["tid"])
            claims.append(Claim(f"team {r['team']} owns {r['svc']}", edge_ids=[r["oid"]], as_of=at))
        if r["pid"]:
            members.append(r["person"])
            claims.append(Claim(f"{r['person']} is a member of team {r['team']}", edge_ids=[r["mid"]], as_of=at))
    team = rows[0]["team"] if rows else None
    out = [{"service": service, "team": team, "team_id": rows[0]["tid"], "members": members, "as_of": at}] if rows else []
    return ToolResult("owners_of", {}, out, claims,
                      summary=f"{service} owned by team {team} ({len(members)} current members)" if rows else "no owner found")


@tool("who_knows",
      "People who know a service best, ranked by deploys they authored to it plus 3x incidents they resolved on it. "
      "Only people currently on a team.",
      {"service": {"type": "string"}, "top": {"type": "integer", "default": 3}}, ["service"], cypher_ref="Q3b who_knows")
def who_knows(ctx: ToolContext, service: str, top: int = 3) -> ToolResult:
    active = {r["pid"] for r in ctx.q("MATCH (p:Person)-[m:MEMBER_OF]->(:Team) WHERE m.vf <= $at AND m.vt > $at "
                                      "RETURN DISTINCT p.id AS pid", {"at": ctx.at})}
    deploys = ctx.q("MATCH (p:Person)-[au:AUTHORED]->(d:Deploy)-[dp:DEPLOYED_TO]->(s:Service {id:$sid}) "
                    "WHERE d.ts <= $at RETURN p.id AS pid, p.name AS person, d.sha AS sha, d.ts AS ts, "
                    "ID(au) AS au, ID(dp) AS dp, s.name AS svc ORDER BY d.ts DESC", {"sid": sid(service), "at": ctx.at})
    incidents = ctx.q("MATCH (i:Incident)-[af:AFFECTED]->(s:Service {id:$sid}), (i)-[rb:RESOLVED_BY]->(p:Person) "
                      "WHERE i.ts_open <= $at RETURN p.id AS pid, p.name AS person, i.id AS iid, i.ts_open AS ts, "
                      "ID(af) AS af, ID(rb) AS rb, s.name AS svc ORDER BY i.ts_open DESC", {"sid": sid(service), "at": ctx.at})
    score: dict[str, dict] = {}
    for r in deploys:
        if r["pid"] in active:
            e = score.setdefault(r["pid"], {"person": r["person"], "pid": r["pid"], "deploys": [], "incidents": []})
            e["deploys"].append(r)
    for r in incidents:
        if r["pid"] in active:
            e = score.setdefault(r["pid"], {"person": r["person"], "pid": r["pid"], "deploys": [], "incidents": []})
            e["incidents"].append(r)
    ranked = sorted(score.values(), key=lambda e: (-(len(e["deploys"]) + 3 * len(e["incidents"])), e["person"]))[:top]
    claims, out = [], []
    for e in ranked:
        if e["deploys"]:
            d = e["deploys"][0]
            claims.append(Claim(f"{e['person']} authored deploy {d['sha']} to {d['svc']} (latest of {len(e['deploys'])})",
                                edge_ids=[d["au"], d["dp"]]))
        if e["incidents"]:
            i = e["incidents"][0]
            claims.append(Claim(f"{e['person']} resolved incident {i['iid']} affecting {i['svc']} "
                                f"(latest of {len(e['incidents'])})", edge_ids=[i["af"], i["rb"]], node_ids=[i["iid"]]))
        out.append({"person": e["person"], "person_id": e["pid"], "deploys": len(e["deploys"]), "incidents_resolved": len(e["incidents"]),
                    "expertise": len(e["deploys"]) + 3 * len(e["incidents"])})
    return ToolResult("who_knows", {}, out, claims, summary=f"{len(out)} knowledgeable people for {service}")


@tool("ownership_gaps", "Services whose owning team has no current members (orphaned services), with who left and when.",
      {}, [], cypher_ref="Q12 ownership_gaps")
def ownership_gaps(ctx: ToolContext) -> ToolResult:
    rows = ctx.q(
        "MATCH (t:Team)-[o:OWNS]->(s:Service) WHERE o.vf <= $at AND o.vt > $at "
        "OPTIONAL MATCH (p:Person)-[m:MEMBER_OF]->(t) WHERE m.vf <= $at AND m.vt > $at "
        "WITH t, s, o, count(p) AS active WHERE active = 0 "
        "OPTIONAL MATCH (q:Person)-[m2:MEMBER_OF]->(t) WHERE m2.vt <= $at "
        "RETURN s.name AS svc, s.tier AS tier, t.name AS team, ID(o) AS oid, collect(q.name) AS left_names, "
        "collect(ID(m2)) AS left_edges, collect(m2.vt) AS left_ts", {"at": ctx.at})
    claims, out = [], []
    for r in rows:
        claims.append(Claim(f"team {r['team']} owns {r['svc']}", edge_ids=[r["oid"]]))
        for name, eid, ts in list(zip(r["left_names"], r["left_edges"], r["left_ts"]))[:3]:
            claims.append(Claim(f"{name} left team {r['team']} on {fmt_day(ts)}", ended_edge_ids=[eid]))
        out.append({"service": r["svc"], "team": r["team"], "left": r["left_names"]})
    return ToolResult("ownership_gaps", {}, out, claims, summary=f"{len(out)} orphaned service(s)")


@tool("incident_resolvers", "People who resolved incidents that affected a service (all time), with incident counts.",
      {"service": {"type": "string"}}, ["service"], cypher_ref="Q3c incident_resolvers")
def incident_resolvers(ctx: ToolContext, service: str) -> ToolResult:
    rows = ctx.q("MATCH (i:Incident)-[af:AFFECTED]->(s:Service {id:$sid}), (i)-[rb:RESOLVED_BY]->(p:Person) "
                 "WHERE i.ts_open <= $at RETURN p.name AS person, i.id AS iid, ID(af) AS af, ID(rb) AS rb, s.name AS svc "
                 "ORDER BY i.ts_open DESC", {"sid": sid(service), "at": ctx.at})
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["person"], []).append(r)
    claims, out = [], []
    for person, items in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        i = items[0]
        claims.append(Claim(f"{person} resolved incident {i['iid']} affecting {i['svc']} (latest of {len(items)})",
                            edge_ids=[i["af"], i["rb"]], node_ids=[i["iid"]]))
        out.append({"person": person, "incidents": len(items)})
    return ToolResult("incident_resolvers", {}, out, claims, summary=f"{len(out)} resolver(s)")
