"""Remediator: reads the Investigator's finding from the graph (handoff), proposes actions, learns from the outcome."""
from __future__ import annotations

import time

from .. import memory, sim, tasks
from ..tools import ToolContext, run_tool
from ..tools.runbooks import record_outcome
from ..verifier import verify_claims
from .scoring import risk_score
from .types import AgentReport, StepRecord

APPROVAL_THRESHOLD = 0.6


def run_remediator(ctx: ToolContext, task_id: str, incident_id: str, *, outcome: bool | None = None,
                   auto_approve: bool = False) -> AgentReport:
    t0 = time.perf_counter()
    episode = memory.start_episode(ctx, "remediator", f"remediate {incident_id}", incident_id)
    upstream = tasks.upstream_findings(ctx, task_id)
    if not upstream:
        memory.finish_episode(ctx, episode, "no-finding", (time.perf_counter() - t0) * 1000)
        return AgentReport("remediator", episode, task_id, headline="No upstream finding to act on.")
    f = upstream[0]["payload"]
    steps: list[StepRecord] = []
    results = []

    def call(tool: str, args: dict, why: str):
        res = run_tool(ctx, tool, args)
        results.append(res)
        memory.log_tool_call(ctx, episode, len(steps), res)
        steps.append(StepRecord("remediator", len(steps), tool, args, why, res.summary, len(res.claims), res.edge_ids,
                                res.node_ids, round(res.ms, 1), res.cypher_ref, res.error))
        return res

    target = f.get("target_service") or f["service"]
    ranked = call("rank_runbooks", {"signal": f["signal"], "service": target}, "Pick the runbook with the best learned record").rows
    verification = verify_claims(ctx, [c for r in results for c in r.claims][:6])   # verify BEFORE writing outcomes back
    suspect = f.get("suspect")
    has_members = bool(f.get("owner_members"))
    tier = min(f.get("blast_tiers") or [2])
    risk = risk_score(f["blast_size"], tier, has_members)
    actions: list[dict] = []

    # 1. page the person who knows the culprit best (low risk, always executed)
    expert = (f.get("experts") or [None])[0]
    if expert and expert.get("person_id"):
        aid = memory.create_action(ctx, "remediator", incident_id, "page", f"Page {expert['person']} for {target}",
                                   0.1, "executed", "Person", expert["person_id"])
        actions.append({"id": aid, "kind": "page", "detail": f"Page {expert['person']} for {target}", "risk": 0.1,
                        "status": "executed"})
    # 2. propose rollback of the suspect deploy; high-risk actions wait for a human
    if suspect:
        status = "executed" if (risk < APPROVAL_THRESHOLD or auto_approve) else "awaiting_approval"
        detail = f"Roll back deploy {suspect['sha']} on {suspect['service']}"
        aid = memory.create_action(ctx, "remediator", incident_id, "propose_rollback", detail, risk, status, "Deploy",
                                   suspect["deploy"])
        actions.append({"id": aid, "kind": "propose_rollback", "detail": detail, "risk": risk, "status": status})
    # 3. apply the top-ranked runbook (simulated execution; outcome recorded back into procedural memory)
    learned: dict = {}
    ok: bool | None = None
    if ranked:
        top = ranked[0]
        ok = outcome if outcome is not None else sim.sample_outcome(ctx.tenant, top["runbook"], f"{incident_id}-{top['attempts']}")
        detail = f"Apply {top['title']} (success rate {top['success_rate']:.0%} over {top['attempts']} attempts)"
        aid = memory.create_action(ctx, "remediator", incident_id, "apply_runbook", detail, risk * 0.5, "executed",
                                   "Runbook", top["runbook"])
        actions.append({"id": aid, "kind": "apply_runbook", "detail": detail, "risk": round(risk * 0.5, 3),
                        "status": "executed"})
        after = record_outcome(ctx, top["runbook"], ok, episode)
        learned["runbook"] = {"id": top["runbook"], "title": top["title"], "ok": ok, **after}
        key = f"best-runbook:{f['signal']}:{target}"
        fact = memory.learn_fact(ctx, key, f"{top['title']} is the preferred fix for {f['signal']} on {target}",
                                 f"svc:{target}", source_uri=f"traceback://run/{incident_id}")
        learned["fact"] = fact
    if suspect:
        learned["root_cause_fact"] = memory.learn_fact(
            ctx, f"root-cause:{f['alert_id']}", f"Root cause of {f['alert_id']} was deploy {suspect['sha']} to {suspect['service']}",
            f"svc:{suspect['service']}", source_uri=f"traceback://run/{incident_id}", confidence=0.7)
    memory.close_incident(ctx, incident_id, bool(ok))
    ms = (time.perf_counter() - t0) * 1000
    memory.finish_episode(ctx, episode, "resolved" if ok else "unresolved", ms)
    pending = [a for a in actions if a["status"] == "awaiting_approval"]
    head = (f"Proposed {len(actions)} action(s); risk {risk:.2f}"
            + (f"; {len(pending)} awaiting human approval" if pending else "")
            + (f". Runbook outcome (simulated): {'success' if ok else 'failure'}." if ok is not None else "."))
    return AgentReport("remediator", episode, task_id, steps, verification.to_dict(),
                       {"actions": actions, "learned": learned, "risk": risk}, head, round(ms, 1))
