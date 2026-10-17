"""The LLM paths, exercised with a scripted fake client (no network, no key)."""
from types import SimpleNamespace as NS

from tbk.agents.compose import llm_rephrase, pool_claims
from tbk.llm import AnthropicPlanner, Goal
from tbk.seed.generate import get_dataset
from tbk.tools import ToolContext, run_tool
from tbk.verifier import verify_claims

ds = get_dataset("helix")
LA = ds.meta["live_alerts"][0]


class FakeClient:
    """messages.create returns scripted responses in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return NS(content=self.responses.pop(0))


def tool_use(i, name, **inp):
    return NS(type="tool_use", id=f"tu{i}", name=name, input=inp)


def test_anthropic_planner_drives_tools_and_stops():
    client = FakeClient([
        [tool_use(1, "get_alert", alert_id=LA["alert"])],
        [tool_use(2, "recent_changes", service=LA["svc"], window_hours=24, depth=2)],
        [NS(type="text", text="done")],
    ])
    p = AnthropicPlanner(Goal("investigate", "helix", LA["ts"], alert_id=LA["alert"]), client=client)
    ctx = ToolContext("helix", LA["ts"])
    hist, seen = [], []
    while (s := p.next(hist)) is not None:
        seen.append(s.tool)
        hist.append(run_tool(ctx, s.tool, s.args))
    assert seen == ["get_alert", "recent_changes"]
    # the tool_result for step 1 was fed back before the model was asked for step 2
    fed_back = [m for m in client.calls[1]["messages"] if isinstance(m["content"], list)
                and isinstance(m["content"][0], dict) and m["content"][0].get("type") == "tool_result"]
    assert fed_back and fed_back[0]["content"][0]["tool_use_id"] == "tu1"
    assert client.calls[0]["tools"], "tool schemas are passed to the model"


def test_rephrase_cannot_smuggle_an_ungrounded_entity():
    ctx = ToolContext("helix", LA["ts"])
    res = run_tool(ctx, "owners_of", {"service": LA["cause_svc"]})
    claims = pool_claims([res])
    other_service = next(s for s in ds.model["services"] if s != LA["cause_svc"])
    payload = ('{"claims": [' + ",".join(
        f'{{"i": {i}, "text": "{c.text} (also affects {other_service})"}}' for i, c in enumerate(claims)) + "]}")
    client = FakeClient([[NS(type="text", text=payload)]])
    polished = llm_rephrase(claims, client=client)
    v = verify_claims(ctx, polished)
    assert v.grounded_pct == 0.0
    assert all("mentions" in c.reason for c in v.claims)


def test_rephrase_failure_falls_back_to_original_claims():
    ctx = ToolContext("helix", LA["ts"])
    claims = pool_claims([run_tool(ctx, "owners_of", {"service": LA["cause_svc"]})])
    client = FakeClient([[NS(type="text", text="not json at all")]])
    assert [c.text for c in llm_rephrase(claims, client=client)] == [c.text for c in claims]


def test_faithful_rephrase_stays_grounded():
    ctx = ToolContext("helix", LA["ts"])
    claims = pool_claims([run_tool(ctx, "owners_of", {"service": LA["cause_svc"]})])
    payload = '{"claims": [' + ",".join(f'{{"i": {i}, "text": "FYI: {c.text}."}}' for i, c in enumerate(claims)) + "]}"
    polished = llm_rephrase(claims, client=FakeClient([[NS(type="text", text=payload)]]))
    assert verify_claims(ctx, polished).grounded_pct == 100.0
