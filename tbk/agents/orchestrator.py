"""Runs a whole incident: Triage -> (graph handoff) -> Investigator -> (graph handoff) -> Remediator.

The scheduler is just a loop over ``tasks.claim_next``; agents communicate only through Task/Finding nodes.
"""
from __future__ import annotations

import uuid
import time

from .. import memory, tasks
from ..llm import Goal
from ..providers import resolve_client
from ..switches import graph_switch
from ..tools import ToolContext
from .fallback import run_without_graph
from .investigator import run_investigator
from .remediator import run_remediator
from .triage import run_triage
from .types import AgentReport, RunReport

AGENT_KIND = {"investigate": "investigator", "remediate": "remediator"}


def _alert_ts(tenant: str, alert_id: str) -> int | None:
    from ..graph import get_store
    rows = get_store().query(tenant, "MATCH (a:Alert {id:$a}) RETURN a.ts AS ts", {"a": alert_id}, raw=True)
    return rows[0]["ts"] if rows else None


def run_incident(tenant: str, alert_id: str, *, graph_enabled: bool = True, use_llm: bool | None = None,
                 outcome: bool | None = None, auto_approve: bool = False) -> RunReport:
    t0 = time.perf_counter()
    if not graph_enabled:
        with graph_switch(False):
            return run_without_graph(tenant, alert_id)
    ts = _alert_ts(tenant, alert_id)
    run_id = uuid.uuid4().hex[:10]
    if ts is None:
        return RunReport(run_id, tenant, alert_id, None, True, "none", error=f"unknown alert {alert_id}")
    ctx = ToolContext(tenant, ts)
    llm = resolve_client(use_llm)
    report = RunReport(run_id, tenant, alert_id, None, True, "llm" if llm else "offline-playbook")
    tri, ticket = run_triage(ctx, alert_id, run_id)
    report.agents.append(tri)
    if not ticket:
        report.error = tri.headline
        return report
    incident = ticket["incident"]
    report.incident_id = incident
    goal = Goal("investigate", tenant, ts, alert_id=alert_id, service=ticket["service"], signal=ticket["signal"])
    safety = 0
    while safety < 6:
        safety += 1
        task = tasks.claim_next(ctx, incident, "agent:worker", list(AGENT_KIND))
        if not task:
            break
        try:
            if task["kind"] == "investigate":
                rep, finding = run_investigator(ctx, goal, task_id=task["id"], incident_id=incident, llm=llm)
                rep.task_id = task["id"]
                tasks.complete_task(ctx, task["id"], incident, {"text": rep.headline, "payload": finding,
                                                               "grounded_pct": finding.get("grounded_pct", 0.0)})
            else:
                rep = run_remediator(ctx, task["id"], incident, outcome=outcome, auto_approve=auto_approve)
                tasks.complete_task(ctx, task["id"], incident)
                report.learned = rep.payload.get("learned", {})
            report.agents.append(rep)
        except Exception as e:                         # a failed agent fails its task, it does not take the run down
            tasks.fail_task(ctx, task["id"], str(e))
            report.agents.append(AgentReport(AGENT_KIND[task["kind"]], task_id=task["id"], headline=f"failed: {e}"))
            report.error = str(e)
    claims = [c for a in report.agents for c in a.verification.get("claims", [])]
    report.n_claims = len(claims)
    report.n_withheld = sum(1 for c in claims if c["status"] != "grounded")
    report.grounded_pct = round(100.0 * (report.n_claims - report.n_withheld) / report.n_claims, 1) if claims else 0.0
    inv = next((a for a in report.agents if a.agent == "investigator" and a.payload), None)
    rem = next((a for a in report.agents if a.agent == "remediator"), None)
    report.headline = " ".join(x for x in [inv.headline if inv else "", rem.headline if rem else ""] if x)
    report.llm = inv.payload.get("llm") if inv else None
    report.tasks = tasks.list_tasks(ctx, incident)
    report.actions = memory.list_actions(ctx, incident)
    report.ms = round((time.perf_counter() - t0) * 1000, 1)
    return report
