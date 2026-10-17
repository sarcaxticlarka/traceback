"""Investigator: finds the likely cause of an alert by walking the graph, then proves its claims."""
from __future__ import annotations

import time

from .. import memory
from ..llm import Goal, make_planner
from ..tools import ToolContext, ToolResult
from ..tools.common import fmt_ts
from ..verifier import verify_claims
from .compose import llm_rephrase, pool_claims
from .runner import run_tool_loop
from .scoring import pick_suspect
from .types import AgentReport


def _rows(results: list[ToolResult], tool: str, **match) -> list[dict]:
    for r in reversed(results):
        if r.tool == tool and not r.error and all(r.args.get(k) == v for k, v in match.items()):
            return r.rows
    return []


def build_finding(ctx: ToolContext, goal: Goal, results: list[ToolResult], service: str, signal: str) -> dict:
    changes = _rows(results, "recent_changes")
    suspect = pick_suspect(changes, ctx.at)
    target = suspect["service"] if suspect else service
    owner = (_rows(results, "owners_of", service=target) or [{}])[0]
    experts = _rows(results, "who_knows", service=target)
    blast = _rows(results, "blast_radius", service=target) or _rows(results, "blast_radius")
    sim = _rows(results, "similar_incidents")
    tiers = {r["tier"] for r in blast}
    return {
        "alert_id": goal.alert_id, "service": service, "signal": signal, "at": ctx.at,
        "suspect": suspect, "target_service": target,
        "owner_team": owner.get("team"), "owner_members": owner.get("members", []),
        "experts": [{"person": e["person"], "person_id": e.get("person_id"), "deploys": e["deploys"],
                     "incidents_resolved": e["incidents_resolved"]} for e in experts],
        "blast_size": len(blast), "blast_tier0": sum(1 for r in blast if r["tier"] == 0),
        "blast_tiers": sorted(tiers), "similar": [{"incident": s["incident"], "runbook": s["runbook"], "result": s["result"]} for s in sim],
    }


def headline(f: dict) -> str:
    s = f.get("suspect")
    if not s:
        return (f"No deploy to {f['service']} or its dependencies in the last 24h. "
                f"Blast radius: {f['blast_size']} service(s).")
    age_h = (f["at"] - s["ts"]) / 3600
    where = "to the alerting service" if s["hops"] == 0 else f"{s['hops']} dependency hop(s) away"
    page = f" Page {f['experts'][0]['person']}." if f["experts"] else ""
    owner = f" Owner: team {f['owner_team']}." if f["owner_team"] else ""
    return (f"Likely cause: deploy {s['sha']} to {s['service']} by {s['author']} at {fmt_ts(s['ts'])} "
            f"({age_h:.1f}h before the alert, {where}).{owner}{page} Blast radius: {f['blast_size']} service(s).")


def run_investigator(ctx: ToolContext, goal: Goal, *, task_id: str | None = None, incident_id: str | None = None,
                     use_llm: bool | None = None) -> tuple[AgentReport, dict]:
    t0 = time.perf_counter()
    episode = memory.start_episode(ctx, "investigator", f"investigate {goal.alert_id or goal.service}", incident_id)
    planner = make_planner(goal, use_llm)
    results, steps = run_tool_loop(ctx, planner, "investigator", episode)
    service = getattr(planner, "service", "") or goal.service
    signal = getattr(planner, "signal", "") or goal.signal
    claims = pool_claims(results)
    if use_llm:
        claims = llm_rephrase(claims)
    verification = verify_claims(ctx, claims)
    finding = build_finding(ctx, goal, results, service, signal)
    finding["grounded_pct"] = verification.grounded_pct
    ms = (time.perf_counter() - t0) * 1000
    memory.finish_episode(ctx, episode, "completed" if finding["suspect"] else "no-suspect", ms)
    report = AgentReport("investigator", episode, task_id, steps, verification.to_dict(), finding, headline(finding),
                         round(ms, 1))
    return report, finding
