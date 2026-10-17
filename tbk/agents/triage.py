"""Triage: sizes up an alert, opens the incident, and creates the work for the other agents in the graph."""
from __future__ import annotations

import time

from .. import memory, tasks
from ..tools import ToolContext, run_tool
from ..verifier import verify_claims
from .runner import run_tool_loop
from .types import AgentReport


class _TriagePlanner:
    def __init__(self, alert_id: str):
        self.alert_id, self.service = alert_id, ""
        self.signal = ""

    def next(self, history):
        from ..llm import Step
        if not history:
            return Step("get_alert", {"alert_id": self.alert_id}, "Resolve the alert")
        a = history[0]
        if a.error or not a.rows:
            return None
        self.service, self.signal = a.rows[0]["service"], a.rows[0]["signal"]
        if len(history) == 1:
            return Step("blast_radius", {"service": self.service, "depth": 4}, "Size the blast radius to set priority")
        return None


def run_triage(ctx: ToolContext, alert_id: str) -> tuple[AgentReport, dict]:
    """Returns (report, ticket) where ticket holds incident id, task ids, service, signal, priority."""
    t0 = time.perf_counter()
    memory.ensure_agents(ctx)
    planner = _TriagePlanner(alert_id)
    episode = memory.start_episode(ctx, "triage", f"triage {alert_id}")
    results, steps = run_tool_loop(ctx, planner, "triage", episode, max_steps=3)
    alert = results[0].rows[0] if results and results[0].rows else None
    if not alert:
        memory.finish_episode(ctx, episode, "alert-not-found", (time.perf_counter() - t0) * 1000)
        return AgentReport("triage", episode, steps=steps, headline=f"Alert {alert_id} not found"), {}
    blast = results[1].rows if len(results) > 1 else []
    tier0 = sum(1 for r in blast if r["tier"] == 0)
    priority = round(min(1.0, (4 - alert["tier"]) * 0.2 + min(len(blast), 20) * 0.02 + 0.05 * tier0 + 0.1 * (alert["severity"] == 1)), 3)
    incident = memory.open_incident(ctx, alert_id, alert["sid"], alert["severity"], alert["signal"])
    t_inv = tasks.create_task(ctx, "investigate", incident, priority)
    t_rem = tasks.create_task(ctx, "remediate", incident, priority, blocked_by=[t_inv])
    claims = [c for r in results for c in r.claims][:6]
    ver = verify_claims(ctx, claims)
    ms = (time.perf_counter() - t0) * 1000
    memory.finish_episode(ctx, episode, "completed", ms)
    ticket = {"incident": incident, "tasks": {"investigate": t_inv, "remediate": t_rem}, "service": alert["service"],
              "service_id": alert["sid"], "signal": alert["signal"], "priority": priority, "tier": alert["tier"],
              "blast_size": len(blast), "alert_ts": alert["ts"]}
    head = (f"{alert['service']} (tier {alert['tier']}) raised {alert['signal']}; {len(blast)} dependents; "
            f"priority {priority}. Opened {incident} with 2 tasks (investigate → remediate).")
    return AgentReport("triage", episode, None, steps, ver.to_dict(), ticket, head, round(ms, 1)), ticket
