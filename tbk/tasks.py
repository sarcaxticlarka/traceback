"""Multi-agent coordination through graph state only.

Agents never call each other. They share ``Task`` nodes:
  (Task)-[:FOR]->(Incident)   (Task)-[:BLOCKED_BY]->(Task)   (Task)-[:PRODUCED]->(Finding)
A task is claimed with a conditional SET (``status:'ready'`` in the MATCH), so two workers racing for the
same task cannot both win: the loser's MATCH returns no row.
"""
from __future__ import annotations

import json
import time

from .memory import new_id
from .tools.base import ToolContext


def _now_ms() -> int:
    return int(time.time() * 1000)


def create_task(ctx: ToolContext, kind: str, incident_id: str, priority: float = 0.5,
                blocked_by: list[str] | None = None) -> str:
    tid = new_id("task")
    status = "blocked" if blocked_by else "ready"
    ctx.q("MATCH (i:Incident {id:$i}) CREATE (t:Task {id:$t, kind:$k, status:$s, priority:$p, created_ts:$c})-[:FOR]->(i)",
          {"i": incident_id, "t": tid, "k": kind, "s": status, "p": priority, "c": _now_ms()})
    for b in blocked_by or []:
        ctx.q("MATCH (t:Task {id:$t}), (b:Task {id:$b}) CREATE (t)-[:BLOCKED_BY]->(b)", {"t": tid, "b": b})
    return tid


def promote_ready(ctx: ToolContext, incident_id: str) -> int:
    rows = ctx.q("MATCH (t:Task {status:'blocked'})-[:FOR]->(:Incident {id:$i}) "
                 "OPTIONAL MATCH (t)-[:BLOCKED_BY]->(b:Task) WHERE b.status <> 'done' "
                 "WITH t, count(b) AS open_blockers WHERE open_blockers = 0 "
                 "SET t.status = 'ready' RETURN count(t) AS n", {"i": incident_id})
    return rows[0]["n"] if rows else 0


def claim_next(ctx: ToolContext, incident_id: str, agent_id: str, kinds: list[str], retries: int = 3) -> dict | None:
    for _ in range(retries):
        cand = ctx.q("MATCH (t:Task {status:'ready'})-[:FOR]->(:Incident {id:$i}) WHERE t.kind IN $kinds "
                     "OPTIONAL MATCH (t)-[:BLOCKED_BY]->(b:Task) WHERE b.status <> 'done' "
                     "WITH t, count(b) AS open_blockers WHERE open_blockers = 0 "
                     "RETURN t.id AS id, t.kind AS kind ORDER BY t.priority DESC, t.created_ts LIMIT 1",
                     {"i": incident_id, "kinds": kinds})
        if not cand:
            return None
        won = ctx.q("MATCH (t:Task {id:$id, status:'ready'}) SET t.status = 'running', t.claimed_by = $a "
                    "RETURN t.id AS id, t.kind AS kind", {"id": cand[0]["id"], "a": agent_id})
        if won:
            return won[0]
    return None


def complete_task(ctx: ToolContext, task_id: str, incident_id: str, finding: dict | None = None) -> str | None:
    fid = None
    if finding is not None:
        fid = new_id("finding")
        ctx.q("MATCH (t:Task {id:$t}) CREATE (t)-[:PRODUCED]->(:Finding {id:$f, text:$text, payload:$p, "
              "grounded_pct:$g, ts:$at})",
              {"t": task_id, "f": fid, "text": finding.get("text", ""), "p": json.dumps(finding.get("payload", {}), default=str),
               "g": finding.get("grounded_pct", 0.0), "at": ctx.at})
    ctx.q("MATCH (t:Task {id:$t}) SET t.status = 'done'", {"t": task_id})
    promote_ready(ctx, incident_id)
    return fid


def fail_task(ctx: ToolContext, task_id: str, reason: str) -> None:
    ctx.q("MATCH (t:Task {id:$t}) SET t.status = 'failed', t.reason = $r", {"t": task_id, "r": reason[:300]})


def upstream_findings(ctx: ToolContext, task_id: str) -> list[dict]:
    """The handoff: a task reads the findings produced by the tasks that blocked it."""
    rows = ctx.q("MATCH (t:Task {id:$t})-[:BLOCKED_BY]->(b:Task)-[:PRODUCED]->(f:Finding) "
                 "RETURN b.kind AS from_kind, f.id AS id, f.text AS text, f.payload AS payload, f.grounded_pct AS grounded",
                 {"t": task_id})
    for r in rows:
        r["payload"] = json.loads(r["payload"]) if r["payload"] else {}
    return rows


def list_tasks(ctx: ToolContext, incident_id: str | None = None) -> list[dict]:
    return ctx.q("MATCH (t:Task)-[:FOR]->(i:Incident) WHERE $i = '' OR i.id = $i "
                 "OPTIONAL MATCH (t)-[:BLOCKED_BY]->(b:Task) "
                 "RETURN t.id AS id, t.kind AS kind, t.status AS status, t.priority AS priority, "
                 "t.claimed_by AS claimed_by, i.id AS incident, t.created_ts AS created_ts, collect(b.id) AS blocked_by "
                 "ORDER BY created_ts DESC LIMIT 60", {"i": incident_id or ""})
