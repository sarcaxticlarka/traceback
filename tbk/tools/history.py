"""Institutional-memory tools: similar incidents, decision lineage, time-aware facts, document search."""
from __future__ import annotations

from ..embeddings import embed
from .base import Claim, ToolContext, ToolResult, tool
from .common import fmt_day
from .topology import sid
from .walk import walk


@tool("similar_incidents",
      "Past incidents that are semantically similar to the signal on this service AND structurally close "
      "(affected service within 2 dependency hops, either direction). Hybrid vector + graph retrieval.",
      {"service": {"type": "string"}, "signal": {"type": "string"}, "top": {"type": "integer", "default": 4}},
      ["service"], cypher_ref="Q4 similar_incidents (vector + traversal)")
def similar_incidents(ctx: ToolContext, service: str, signal: str = "", top: int = 4) -> ToolResult:
    name = service.replace("svc:", "")
    scope_ids = list(set(walk(ctx, sid(service), direction="out", depth=2)) | set(walk(ctx, sid(service), direction="in", depth=2))) \
        or [sid(service)]
    qvec = embed(f"{signal} on {name}")
    # vector index + property filters combine poorly in FalkorDB, so retrieve first, then traverse
    rows = ctx.q("CALL db.idx.vector.queryNodes('Incident','embedding',40,vecf32($v)) YIELD node, score "
                 "MATCH (node)-[af:AFFECTED]->(x:Service) WHERE x.id IN $scope "
                 "MATCH (node)-[cb:CAUSED_BY]->(d:Deploy) "
                 "OPTIONAL MATCH (node)-[fw:FIXED_WITH]->(rb:Runbook) "
                 "RETURN node.id AS iid, node.title AS title, node.signal AS signal, score, x.name AS svc, "
                 "ID(af) AS af, ID(cb) AS cb, d.sha AS sha, rb.title AS rb, ID(fw) AS fw, fw.result AS result "
                 "ORDER BY score LIMIT 60", {"v": qvec, "scope": scope_ids})
    seen, picked = set(), []
    for r in rows:
        if r["iid"] in seen:
            continue
        seen.add(r["iid"])
        picked.append(r)
        if len(picked) >= top:
            break
    claims, out = [], []
    for r in picked:
        claims.append(Claim(f"incident {r['iid']} affected {r['svc']} and was caused by deploy {r['sha']}",
                            edge_ids=[r["af"], r["cb"]], node_ids=[r["iid"]]))
        if r["fw"] is not None:
            claims.append(Claim(f"incident {r['iid']} was fixed with {r['rb']} ({r['result']})", edge_ids=[r["fw"]],
                                node_ids=[r["iid"]]))
        out.append({"incident": r["iid"], "signal": r["signal"], "service": r["svc"], "runbook": r["rb"],
                    "result": r["result"], "distance": round(r["score"], 3)})
    return ToolResult("similar_incidents", {}, out, claims, summary=f"{len(out)} similar incident(s)")


@tool("decision_lineage",
      "Engineering decisions that constrain a service, newest first, with the decisions each one superseded and the "
      "source document it was recorded in.",
      {"service": {"type": "string"}}, ["service"], cypher_ref="Q9 decision_lineage")
def decision_lineage(ctx: ToolContext, service: str) -> ToolResult:
    rows = ctx.q(
        "MATCH (d:Decision)-[c:CONSTRAINS]->(s:Service {id:$sid}) "
        "OPTIONAL MATCH (d)-[sup:SUPERSEDES]->(old:Decision) "
        "OPTIONAL MATCH (d)-[di:DECIDED_IN_DOC]->(doc:Doc) "
        "RETURN d.id AS did, d.statement AS stmt, d.ts AS ts, ID(c) AS c, ID(sup) AS sup, old.id AS old, "
        "ID(di) AS di, doc.id AS doc ORDER BY d.ts DESC", {"sid": sid(service)})
    superseded = {r["old"] for r in rows if r["old"]}
    claims, out = [], []
    for r in rows:
        state = "superseded" if r["did"] in superseded else "current"
        claims.append(Claim(f"decision {r['did']} ({state}): {r['stmt']}", edge_ids=[r["c"]] + ([r["di"]] if r["di"] is not None else []),
                            node_ids=[r["did"]], assert_props=[{"node_id": r["did"], "prop": "statement", "value": r["stmt"]}]))
        if r["sup"] is not None:
            claims.append(Claim(f"decision {r['did']} superseded decision {r['old']}", edge_ids=[r["sup"], r["c"]]))
        out.append({"decision": r["did"], "statement": r["stmt"], "state": state, "date": fmt_day(r["ts"]),
                    "supersedes": r["old"], "doc": r["doc"]})
    return ToolResult("decision_lineage", {}, out, claims, summary=f"{len(out)} decision(s), "
                      f"{sum(1 for o in out if o['state'] == 'current')} current")


@tool("facts_as_of", "Knowledge recorded about a service that was true at a point in time (time-travel; default now).",
      {"service": {"type": "string"}, "as_of": {"type": "integer"}}, ["service"], cypher_ref="Q13 facts_as_of")
def facts_as_of(ctx: ToolContext, service: str, as_of: int | None = None) -> ToolResult:
    at = int(as_of) if as_of else ctx.at
    rows = ctx.q(
        "MATCH (f:Fact)-[ab:ABOUT_SERVICE]->(s:Service {id:$sid}) WHERE f.vf <= $at AND f.vt > $at "
        "MATCH (f)-[ap:ABOUT_PERSON]->(p:Person) OPTIONAL MATCH (f)-[sb:SUPPORTED_BY]->(src:Source) "
        "RETURN f.id AS fid, f.text AS text, f.vf AS vf, ID(ab) AS ab, ID(ap) AS ap, ID(sb) AS sb, src.uri AS uri, p.name AS person",
        {"sid": sid(service), "at": at})
    claims, out = [], []
    for r in rows:
        eids = [r["ab"], r["ap"]] + ([r["sb"]] if r["sb"] is not None else [])
        claims.append(Claim(f"{r['text']} (valid as of {fmt_day(at)})", edge_ids=eids, node_ids=[r["fid"]], as_of=at,
                            assert_props=[{"node_id": r["fid"], "prop": "text", "value": r["text"]}]))
        out.append({"fact": r["text"], "person": r["person"], "since": fmt_day(r["vf"]), "source": r["uri"]})
    return ToolResult("facts_as_of", {}, out, claims, summary=f"{len(out)} fact(s) valid on {fmt_day(at)}")


@tool("search_docs", "Semantic search over documents (READMEs, runbooks, postmortems, ADRs, chats) stored in the graph.",
      {"query": {"type": "string"}, "top": {"type": "integer", "default": 5}}, ["query"], cypher_ref="Q14 search_docs (vector)")
def search_docs(ctx: ToolContext, query: str, top: int = 5) -> ToolResult:
    rows = ctx.q("CALL db.idx.vector.queryNodes('Doc','embedding',$k,vecf32($v)) YIELD node, score "
                 "RETURN node.id AS id, node.kind AS kind, node.title AS title, node.body AS body, score "
                 "ORDER BY score", {"k": max(1, min(int(top), 20)), "v": embed(query)})
    claims = [Claim(f"document {r['id']} ({r['kind']}) matches the query", node_ids=[r["id"]]) for r in rows]
    out = [{"id": r["id"], "kind": r["kind"], "title": r["title"], "snippet": r["body"][:200],
            "distance": round(r["score"], 3)} for r in rows]
    return ToolResult("search_docs", {}, out, claims, summary=f"{len(out)} document(s)")
