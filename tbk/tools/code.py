"""Codebase tools: hotspots, bus factor, change impact. Properties they read are materialised at ingest time
(``Service.churn_90d``, ``dependents``, ``commits``, ``top_author_share``) and re-verified by the verifier."""
from __future__ import annotations

from .base import Claim, ToolContext, ToolResult, tool
from .common import clamp_depth
from .people import owners_of, who_knows
from .topology import blast_radius, sid


@tool("hotspots", "Modules most likely to hurt when they change: ranked by lines changed in the last 90 days times (1 + direct "
      "dependents). Churn x fan-in is the classic risk signal.",
      {"top": {"type": "integer", "default": 5}}, [], cypher_ref="Q15 hotspots (churn x fan-in)")
def hotspots(ctx: ToolContext, top: int = 5) -> ToolResult:
    rows = ctx.q("MATCH (s:Service) WHERE s.churn_90d IS NOT NULL AND s.churn_90d > 0 "
                 "RETURN s.id AS id, s.name AS name, s.churn_90d AS churn, s.dependents AS dep, s.commits AS commits, "
                 "s.churn_90d * (1 + s.dependents) AS risk ORDER BY risk DESC LIMIT $top", {"top": clamp_depth(top, 5, 25)})
    claims = [Claim(f"{r['name']} changed {r['churn']} lines in the last 90 days and has {r['dep']} direct dependents",
                    node_ids=[r["id"]], assert_props=[{"node_id": r["id"], "prop": "churn_90d", "value": r["churn"]},
                                                      {"node_id": r["id"], "prop": "dependents", "value": r["dep"]}]) for r in rows]
    return ToolResult("hotspots", {}, rows, claims, summary=f"{len(rows)} hotspot(s)")


@tool("bus_factor", "Modules where one person wrote most of the commits (knowledge concentrated in one head).",
      {"top": {"type": "integer", "default": 5}, "min_share": {"type": "number", "default": 0.7},
       "min_commits": {"type": "integer", "default": 5}}, [], cypher_ref="Q16 bus_factor")
def bus_factor(ctx: ToolContext, top: int = 5, min_share: float = 0.7, min_commits: int = 5) -> ToolResult:
    rows = ctx.q("MATCH (s:Service) WHERE s.commits >= $mc AND s.top_author_share >= $sh "
                 "RETURN s.id AS id, s.name AS name, s.commits AS commits, s.top_author AS author, "
                 "s.top_author_share AS share ORDER BY s.commits * s.top_author_share DESC LIMIT $top",
                 {"mc": int(min_commits), "sh": float(min_share), "top": clamp_depth(top, 5, 25)})
    claims = []
    for r in rows:
        ev = ctx.q("MATCH (p:Person {name:$a})-[au:AUTHORED]->(d:Deploy)-[dp:DEPLOYED_TO]->(s:Service {id:$sid}) "
                   "RETURN ID(au) AS au, ID(dp) AS dp ORDER BY d.ts DESC LIMIT 1", {"a": r["author"], "sid": r["id"]})
        if not ev:
            continue
        claims.append(Claim(f"{r['author']} wrote {round(r['share'] * 100)}% of the {r['commits']} commits to {r['name']}",
                            edge_ids=[ev[0]["au"], ev[0]["dp"]], node_ids=[r["id"]],
                            assert_props=[{"node_id": r["id"], "prop": "top_author_share", "value": r["share"]},
                                          {"node_id": r["id"], "prop": "commits", "value": r["commits"]}]))
    return ToolResult("bus_factor", {}, rows, claims, summary=f"{len(rows)} module(s) depend on one person")


@tool("change_impact", "Impact of a change: given a commit sha or a comma-separated list of modules, the modules that depend on "
      "what changed, the owning teams, and the people best placed to review it.",
      {"sha": {"type": "string", "description": "commit sha (7+ chars)"},
       "modules": {"type": "string", "description": "comma-separated module names, e.g. src/api/,lib/core/"}},
      [], cypher_ref="Q17 change_impact")
def change_impact(ctx: ToolContext, sha: str = "", modules: str = "") -> ToolResult:
    claims: list[Claim] = []
    author = ""
    touched: list[str] = []
    if sha:
        rows = ctx.q("MATCH (p:Person)-[au:AUTHORED]->(d:Deploy)-[dp:DEPLOYED_TO]->(s:Service) "
                     "WHERE d.sha = $sha OR d.id = $id RETURN s.name AS module, p.name AS author, d.sha AS sha, "
                     "d.summary AS subject, ID(au) AS au, ID(dp) AS dp, dp.lines AS lines ORDER BY lines DESC",
                     {"sha": sha[:7], "id": f"dep:{sha[:7]}"})
        for r in rows:
            touched.append(r["module"])
            author = r["author"]
            claims.append(Claim(f"{r['author']} changed {r['module']} in deploy {r['sha']}", edge_ids=[r["au"], r["dp"]]))
    else:
        touched = [m.strip() for m in modules.split(",") if m.strip()]
        known = {r["name"] for r in ctx.q("MATCH (s:Service) RETURN s.name AS name")}
        touched = [m for m in touched if m in known]
    if not touched:
        return ToolResult("change_impact", {}, [], [], summary="no modules found for that change")
    impacted: dict[str, int] = {}
    owners: dict[str, str] = {}
    reviewers: dict[str, int] = {}
    for m in touched[:6]:
        br = blast_radius(ctx, m, depth=4, max_claims=4)
        claims += br.claims
        for r in br.rows:
            impacted.setdefault(r["service"], r["hops"])
        ow = owners_of(ctx, m)
        claims += ow.claims[:1]
        for r in ow.rows:
            if r["team"]:
                owners[r["team"]] = m
        kn = who_knows(ctx, m, top=3)
        for c in kn.claims[:2]:
            claims.append(c)
        for r in kn.rows:
            if r["person"] != author:
                reviewers[r["person"]] = reviewers.get(r["person"], 0) + r["expertise"]
    seen, uniq = set(), []
    for c in claims:
        if c.text not in seen:
            seen.add(c.text)
            uniq.append(c)
    props = ctx.q("MATCH (s:Service) WHERE s.name IN $m RETURN s.name AS name, s.churn_90d AS churn, s.top_author_share AS share, "
                  "s.commits AS commits", {"m": touched})
    factors = []
    for p in props:
        if (p["churn"] or 0) > 1500:
            factors.append(f"{p['name']} is a high-churn module ({p['churn']} lines / 90d)")
        if (p["commits"] or 0) >= 5 and (p["share"] or 0) >= 0.7:
            factors.append(f"{p['name']} is concentrated in one author ({round(p['share'] * 100)}%)")
    risk = min(100, 6 * len(impacted) + (10 if factors else 0) + 4 * len(touched))
    ranked_rev = [p for p, _ in sorted(reviewers.items(), key=lambda kv: -kv[1])][:3]
    return ToolResult("change_impact", {}, [{"touched": touched, "impacted": sorted(impacted, key=impacted.get)[:20],
                                             "impacted_count": len(impacted), "owners": sorted(owners),
                                             "reviewers": ranked_rev, "risk_score": risk, "risk_factors": factors}],
                      uniq, summary=f"{len(touched)} module(s) touched, {len(impacted)} impacted, risk {risk}/100")


@tool("top_contributors", "Who made the most commits to a module (all time), with a sample commit as evidence.",
      {"service": {"type": "string"}, "top": {"type": "integer", "default": 3}}, ["service"], cypher_ref="Q18 top_contributors")
def top_contributors(ctx: ToolContext, service: str, top: int = 3) -> ToolResult:
    rows = ctx.q("MATCH (p:Person)-[au:AUTHORED]->(d:Deploy)-[dp:DEPLOYED_TO]->(s:Service {id:$sid}) "
                 "RETURN p.name AS person, count(d) AS commits, max(d.ts) AS last ORDER BY commits DESC, person LIMIT $top",
                 {"sid": sid(service), "top": clamp_depth(top, 3, 20)})
    claims = []
    for r in rows:
        ev = ctx.q("MATCH (p:Person {name:$a})-[au:AUTHORED]->(d:Deploy)-[dp:DEPLOYED_TO]->(s:Service {id:$sid}) "
                   "RETURN ID(au) AS au, ID(dp) AS dp, d.sha AS sha ORDER BY d.ts DESC LIMIT 1", {"a": r["person"], "sid": sid(service)})
        if ev:
            claims.append(Claim(f"{r['person']} authored deploy {ev[0]['sha']} to {service.replace('svc:', '')} "
                                f"(latest of {r['commits']})", edge_ids=[ev[0]["au"], ev[0]["dp"]]))
    return ToolResult("top_contributors", {}, rows, claims, summary=f"{len(rows)} contributor(s)")
