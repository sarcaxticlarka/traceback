"""End-to-end crew behaviour on the planted live alerts."""
import pytest

from tbk import memory, tasks
from tbk.agents.orchestrator import run_incident
from tbk.llm import Goal, InvestigatePlanner
from tbk.seed.generate import get_dataset
from tbk.tools import ToolContext, run_tool

ds = get_dataset("helix")
LIVE = ds.meta["live_alerts"]


@pytest.mark.parametrize("la", LIVE, ids=[a["alert"] for a in LIVE])
def test_root_cause_is_the_planted_deploy(la):
    r = run_incident("helix", la["alert"])
    inv = next(a for a in r.agents if a.agent == "investigator")
    assert inv.payload["suspect"]["deploy"] == la["cause_deploy"]
    assert inv.payload["suspect"]["hops"] == la["depth"]
    assert inv.payload["owner_team"] == la["owner_team"]
    assert r.grounded_pct == 100.0, [c for a in r.agents for c in a.verification["claims"] if c["status"] != "grounded"]


def test_handoff_happens_through_graph_state_only():
    la = LIVE[0]
    r = run_incident("helix", la["alert"])
    kinds = {t["kind"]: t for t in r.tasks}
    assert kinds["investigate"]["status"] == "done" and kinds["remediate"]["status"] == "done"
    assert kinds["remediate"]["blocked_by"] == [kinds["investigate"]["id"]]
    ctx = ToolContext("helix", la["ts"])
    handoff = tasks.upstream_findings(ctx, kinds["remediate"]["id"])
    assert handoff and handoff[0]["payload"]["suspect"]["deploy"] == la["cause_deploy"]


def test_task_claim_is_atomic():
    la = LIVE[1]
    ctx = ToolContext("helix", la["ts"])
    memory.ensure_agents(ctx)
    r = run_incident("helix", la["alert"])
    inc = r.incident_id
    t = tasks.create_task(ctx, "investigate", inc, 0.9)
    first = tasks.claim_next(ctx, inc, "agent:a", ["investigate"])
    second = tasks.claim_next(ctx, inc, "agent:b", ["investigate"])
    assert first and first["id"] == t
    assert second is None


def test_procedural_memory_updates_after_run():
    la = LIVE[2]
    ctx = ToolContext("helix", la["ts"])
    before = {r["runbook"]: r["attempts"] for r in run_tool(ctx, "rank_runbooks", {"signal": la["signal"]}).rows}
    r = run_incident("helix", la["alert"], outcome=True)
    rb = r.learned["runbook"]
    assert rb["attempts"] == before[rb["id"]] + 1


def test_semantic_fact_is_superseded_not_overwritten():
    la = LIVE[3]
    ctx = ToolContext("helix", la["ts"])
    a = memory.learn_fact(ctx, "k:test", "X is preferred", f"svc:{la['svc']}")
    b = memory.learn_fact(ctx, "k:test", "Y is preferred", f"svc:{la['svc']}")
    assert b["superseded"] == [a["id"]]
    old = ctx.q("MATCH (f:Fact {id:$i}) RETURN f.vt AS vt", {"i": a["id"]})[0]["vt"]
    assert old == la["ts"]                                   # closed, not deleted
    assert memory.learn_fact(ctx, "k:test", "Y is preferred", f"svc:{la['svc']}")["created"] is False


def test_kill_switch_removes_grounding():
    r = run_incident("helix", LIVE[0]["alert"], graph_enabled=False)
    assert r.grounded_pct == 0.0 and r.incident_id is None and r.planner == "docs-only"


def test_planner_skips_nothing_and_terminates():
    la = LIVE[0]
    ctx = ToolContext("helix", la["ts"])
    p = InvestigatePlanner(Goal("investigate", "helix", la["ts"], alert_id=la["alert"]))
    hist, seen = [], []
    while (s := p.next(hist)) is not None:
        seen.append(s.tool)
        hist.append(run_tool(ctx, s.tool, s.args))
    assert seen[0] == "get_alert" and "recent_changes" in seen and "owners_of" in seen
    assert seen.count("get_alert") == 1 and seen.count("recent_changes") == 1
    assert len(seen) <= 12
