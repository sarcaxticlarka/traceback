"""Agent memory in the graph: episodic (what ran), semantic (what is known, with validity), procedural (runbooks).

Procedural memory lives in ``tools.runbooks`` (``rank_runbooks`` / ``record_outcome``); this module covers
episodes, tool-call traces, supersedable facts and incident/action bookkeeping.
"""
from __future__ import annotations

import json
import uuid

from .config import INF
from .tools.base import ToolContext, ToolResult

AGENT_KINDS = ("triage", "investigator", "remediator")


def new_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:10]}"


def ensure_agents(ctx: ToolContext) -> None:
    for kind in AGENT_KINDS:
        ctx.q("MERGE (a:Agent {id:$id}) SET a.kind = $kind", {"id": f"agent:{kind}", "kind": kind})


# ----------------------------------------------------------------------------- episodic memory
def start_episode(ctx: ToolContext, agent: str, goal: str, incident_id: str | None = None) -> str:
    eid = new_id("ep")
    ctx.q("MATCH (a:Agent {id:$a}) CREATE (a)-[:RAN]->(e:Episode {id:$e, ts:$ts, goal:$goal, outcome:'running', "
          "latency_ms:0})", {"a": f"agent:{agent}", "e": eid, "ts": ctx.at, "goal": goal})
    if incident_id:
        ctx.q("MATCH (e:Episode {id:$e}), (i:Incident {id:$i}) CREATE (e)-[:ABOUT]->(i)", {"e": eid, "i": incident_id})
    return eid


def log_tool_call(ctx: ToolContext, episode_id: str, order: int, res: ToolResult) -> None:
    ctx.q("MATCH (e:Episode {id:$e}) CREATE (e)-[:CALLED {order:$o}]->(:ToolCall {id:$id, tool:$tool, args:$args, "
          "n_rows:$n, n_claims:$c, ms:$ms, error:$err})",
          {"e": episode_id, "o": order, "id": new_id("tc"), "tool": res.tool, "args": json.dumps(res.args, default=str),
           "n": len(res.rows), "c": len(res.claims), "ms": round(res.ms, 1), "err": res.error or ""})


def finish_episode(ctx: ToolContext, episode_id: str, outcome: str, latency_ms: float) -> None:
    ctx.q("MATCH (e:Episode {id:$e}) SET e.outcome = $o, e.latency_ms = $l",
          {"e": episode_id, "o": outcome, "l": round(latency_ms, 1)})


def recent_episodes(ctx: ToolContext, limit: int = 20) -> list[dict]:
    return ctx.q("MATCH (a:Agent)-[:RAN]->(e:Episode) OPTIONAL MATCH (e)-[c:CALLED]->(tc:ToolCall) "
                 "RETURN e.id AS id, a.kind AS agent, e.goal AS goal, e.outcome AS outcome, e.ts AS ts, "
                 "e.latency_ms AS latency_ms, count(tc) AS tool_calls ORDER BY ts DESC LIMIT $n", {"n": limit})


# ----------------------------------------------------------------------------- semantic memory
def learn_fact(ctx: ToolContext, key: str, text: str, service_id: str, source_uri: str = "",
               confidence: float = 0.8) -> dict:
    """Record a fact valid from now. A different current fact with the same ``key`` is closed (vt = now) and superseded."""
    same = ctx.q("MATCH (f:Fact {key:$k, text:$t}) WHERE f.vt > $at RETURN f.id AS id", {"k": key, "t": text, "at": ctx.at})
    if same:
        return {"id": same[0]["id"], "created": False, "superseded": []}
    old = ctx.q("MATCH (f:Fact {key:$k}) WHERE f.vt > $at SET f.vt = $at RETURN f.id AS id", {"k": key, "at": ctx.at})
    fid = new_id("fact")
    ctx.q("MATCH (s:Service {id:$s}) CREATE (f:Fact {id:$f, key:$k, text:$t, confidence:$c, vf:$at, vt:$inf, "
          "recorded_at:$at})-[:ABOUT_SERVICE]->(s)",
          {"s": service_id, "f": fid, "k": key, "t": text, "c": confidence, "at": ctx.at, "inf": INF})
    if source_uri:
        sid_ = f"src:{fid[5:]}"
        ctx.q("MATCH (f:Fact {id:$f}) CREATE (f)-[:SUPPORTED_BY]->(:Source {id:$s, kind:'agent-run', uri:$u, ts:$at})",
              {"f": fid, "s": sid_, "u": source_uri, "at": ctx.at})
    for o in old:
        ctx.q("MATCH (n:Fact {id:$n}), (o:Fact {id:$o}) CREATE (n)-[:SUPERSEDES]->(o)", {"n": fid, "o": o["id"]})
    return {"id": fid, "created": True, "superseded": [o["id"] for o in old]}


def current_facts(ctx: ToolContext, limit: int = 30) -> list[dict]:
    return ctx.q("MATCH (f:Fact)-[:ABOUT_SERVICE]->(s:Service) WHERE f.vf <= $at AND f.vt > $at "
                 "OPTIONAL MATCH (f)-[:SUPERSEDES]->(o:Fact) "
                 "RETURN f.id AS id, f.text AS text, s.name AS service, f.vf AS since, count(o) AS supersedes "
                 "ORDER BY since DESC LIMIT $n", {"at": ctx.at, "n": limit})


# ----------------------------------------------------------------------------- incidents and actions
def open_incident(ctx: ToolContext, alert_id: str, service_id: str, severity: int, signal: str, run_id: str = "") -> str:
    iid = "inc:" + alert_id.split(":", 1)[1] + (f"~{run_id[:4]}" if run_id else "")
    ctx.q("MATCH (a:Alert {id:$a}), (s:Service {id:$s}) "
          "MERGE (i:Incident {id:$i}) SET i.ts_open = $at, i.severity = $sev, i.signal = $sig, i.title = $title, "
          "i.summary = $title, i.status = 'open' "
          "MERGE (i)-[:TRIGGERED_BY]->(a) MERGE (i)-[:AFFECTED]->(s)",
          {"a": alert_id, "s": service_id, "i": iid, "at": ctx.at, "sev": severity, "sig": signal,
           "title": f"{signal} on {service_id[4:]} (live)"})
    return iid


def close_incident(ctx: ToolContext, incident_id: str, resolved: bool) -> None:
    ctx.q("MATCH (i:Incident {id:$i}) SET i.ts_close = $at, i.status = $s",
          {"i": incident_id, "at": ctx.at, "s": "resolved" if resolved else "unresolved"})


def create_action(ctx: ToolContext, agent: str, incident_id: str, kind: str, detail: str, risk: float,
                  status: str, target_label: str | None = None, target_id: str | None = None) -> str:
    aid = new_id("act")
    ctx.q("MATCH (g:Agent {id:$g}), (i:Incident {id:$i}) "
          "CREATE (g)-[:PROPOSED]->(a:Action {id:$a, kind:$k, detail:$d, risk:$r, status:$s, ts:$at})-[:FOR]->(i)",
          {"g": f"agent:{agent}", "i": incident_id, "a": aid, "k": kind, "d": detail, "r": round(risk, 3), "s": status,
           "at": ctx.at})
    if target_label and target_id:
        ctx.q(f"MATCH (a:Action {{id:$a}}), (t:{target_label} {{id:$t}}) CREATE (a)-[:TARGETS]->(t)",
              {"a": aid, "t": target_id})
    return aid


def set_action_status(ctx: ToolContext, action_id: str, status: str, approver_id: str | None = None) -> bool:
    rows = ctx.q("MATCH (a:Action {id:$a}) SET a.status = $s RETURN a.id AS id", {"a": action_id, "s": status})
    if rows and approver_id:
        ctx.q("MATCH (a:Action {id:$a}), (p:Person {id:$p}) MERGE (a)-[:APPROVED_BY]->(p)", {"a": action_id, "p": approver_id})
    return bool(rows)


def list_actions(ctx: ToolContext, incident_id: str | None = None) -> list[dict]:
    return ctx.q("MATCH (g:Agent)-[:PROPOSED]->(a:Action)-[:FOR]->(i:Incident) WHERE $i = '' OR i.id = $i "
                 "RETURN a.id AS id, a.kind AS kind, a.detail AS detail, a.risk AS risk, a.status AS status, "
                 "a.ts AS ts, i.id AS incident, g.kind AS agent ORDER BY ts DESC LIMIT 50", {"i": incident_id or ""})
