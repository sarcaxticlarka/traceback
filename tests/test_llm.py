"""LLM layer: provider adapters, failover, key handling, and the agents running on top (no network, no keys)."""
import json
from types import SimpleNamespace as NS

import httpx
import pytest

from tbk import providers
from tbk.agents.compose import llm_rephrase, pool_claims
from tbk.agents.orchestrator import run_incident
from tbk.llm import Goal, LLMPlanner
from tbk.providers import (AnthropicProvider, FailoverClient, LLMResponse, OpenAICompatProvider, ProviderConfig,
                           ProviderError, ToolCall, _to_anthropic, _to_openai)
from tbk.seed.generate import get_dataset
from tbk.tools import ToolContext, run_tool
from tbk.verifier import verify_claims

ds = get_dataset("helix")
LA = ds.meta["live_alerts"][0]


@pytest.fixture(autouse=True)
def _clean():
    providers.reset_cooldowns()
    yield
    providers.reset_cooldowns()


class Scripted:
    """A Provider that replays responses (LLMResponse) or raises (ProviderError) in order."""

    def __init__(self, name, script, key="k"):
        self.name, self.model, self.key_id, self.script, self.calls = name, "m", key, list(script), []

    def complete(self, system, messages, tools, max_tokens=1024):
        self.calls.append(messages[:])
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tc(i, name, **inp):
    return ToolCall(f"c{i}", name, inp)


def reply(text="", *calls, provider="p"):
    return LLMResponse(text, list(calls), provider, "m")


# ------------------------------------------------------------------------------------ conversions
CANON = [
    {"role": "user", "content": "go"},
    {"role": "assistant", "text": "checking", "tool_calls": [{"id": "a", "name": "t1", "input": {"x": 1}},
                                                              {"id": "b", "name": "t2", "input": {}}]},
    {"role": "tool", "tool_call_id": "a", "content": "ra"},
    {"role": "tool", "tool_call_id": "b", "content": "rb"},
]


def test_anthropic_conversion_groups_tool_results_in_one_user_turn():
    out = _to_anthropic(CANON)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert [b["type"] for b in out[1]["content"]] == ["text", "tool_use", "tool_use"]
    assert [b["tool_use_id"] for b in out[2]["content"]] == ["a", "b"]


def test_openai_conversion_uses_tool_role_and_json_arguments():
    out = _to_openai("sys", CANON)
    assert out[0] == {"role": "system", "content": "sys"}
    assert out[2]["tool_calls"][0]["function"]["arguments"] == '{"x": 1}'
    assert [m["role"] for m in out[3:]] == ["tool", "tool"]


# ------------------------------------------------------------------------------------ OpenAI-compatible adapter
def _openai(handler, key="sk-secret"):
    cfg = ProviderConfig("openai", key, "gpt-test", "https://api.openai.com/v1").resolved()
    return OpenAICompatProvider(cfg, transport=httpx.MockTransport(handler))


def test_openai_request_and_tool_call_parsing():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"], seen["body"], seen["url"] = req.headers["authorization"], json.loads(req.content), str(req.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "x1", "type": "function", "function": {"name": "owners_of", "arguments": '{"service": "payments-api"}'}}]}}]})

    p = _openai(handler)
    tools = [{"name": "owners_of", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    r = p.complete("sys", [{"role": "user", "content": "hi"}], tools, 50)
    assert r.tool_calls[0].name == "owners_of" and r.tool_calls[0].input == {"service": "payments-api"}
    assert seen["auth"] == "Bearer sk-secret" and seen["url"].endswith("/chat/completions")
    assert seen["body"]["tools"][0]["function"]["name"] == "owners_of" and seen["body"]["model"] == "gpt-test"


@pytest.mark.parametrize("status,body,kind", [(429, "slow down", "rate_limit"), (429, '{"error":{"code":"insufficient_quota"}}', "quota"),
                                              (401, "bad key", "auth"), (503, "busy", "overloaded"), (400, "oops", "bad_request")])
def test_openai_error_kinds(status, body, kind):
    p = _openai(lambda req: httpx.Response(status, text=body, headers={"retry-after": "7"}))
    with pytest.raises(ProviderError) as e:
        p.complete("", [{"role": "user", "content": "x"}], None)
    assert e.value.kind == kind
    if status == 429 and kind == "rate_limit":
        assert e.value.retry_after == 7.0


def test_api_key_is_scrubbed_from_errors():
    p = _openai(lambda req: httpx.Response(401, text="invalid key sk-secret supplied"), key="sk-secret")
    with pytest.raises(ProviderError) as e:
        p.complete("", [{"role": "user", "content": "x"}], None)
    assert "sk-secret" not in str(e.value) and "***" in str(e.value)


# ------------------------------------------------------------------------------------ Anthropic adapter
def test_anthropic_provider_maps_response_and_errors():
    class RateLimitError(Exception):
        status_code = 429

    ok = NS(content=[NS(type="text", text="hi"), NS(type="tool_use", id="t1", name="blast_radius", input={"service": "x"})])
    cfg = ProviderConfig("anthropic", "k", "claude-test").resolved()
    good = AnthropicProvider(cfg, client=NS(messages=NS(create=lambda **kw: ok)))
    r = good.complete("sys", [{"role": "user", "content": "go"}], [{"name": "blast_radius", "description": "d", "input_schema": {}}])
    assert r.text == "hi" and r.tool_calls[0].name == "blast_radius"

    def boom(**kw):
        raise RateLimitError("429 rate limited")
    bad = AnthropicProvider(cfg, client=NS(messages=NS(create=boom)))
    with pytest.raises(ProviderError) as e:
        bad.complete("", [{"role": "user", "content": "go"}], None)
    assert e.value.kind == "rate_limit"


# ------------------------------------------------------------------------------------ failover
def test_failover_moves_to_next_provider_and_records_why():
    a = Scripted("anthropic", [ProviderError("rate_limit", "429", "anthropic")], key="a")
    b = Scripted("openai", [reply("answered by b")], key="b")
    c = FailoverClient([a, b])
    assert c.complete("", [{"role": "user", "content": "q"}]).text == "answered by b"
    s = c.summary()
    assert s["used"] == "openai/m" and s["failovers"][0]["provider"] == "anthropic" and s["failovers"][0]["kind"] == "rate_limit"


def test_cooldown_skips_a_limited_provider_on_the_next_call():
    a = Scripted("a", [ProviderError("rate_limit", "429", "a", retry_after=60), reply("never")], key="a")
    b = Scripted("b", [reply("one"), reply("two")], key="b")
    c = FailoverClient([a, b])
    c.complete("", [{"role": "user", "content": "1"}])
    c.complete("", [{"role": "user", "content": "2"}])
    assert len(a.calls) == 1 and len(b.calls) == 2           # a was not retried while cooling down


def test_bad_request_is_not_hidden_by_failover():
    a = Scripted("a", [ProviderError("bad_request", "400", "a")], key="a")
    b = Scripted("b", [reply("x")], key="b")
    with pytest.raises(ProviderError):
        FailoverClient([a, b]).complete("", [{"role": "user", "content": "q"}])
    assert not b.calls


def test_all_providers_failing_raises_last_error():
    a = Scripted("a", [ProviderError("quota", "no credit", "a")], key="a")
    b = Scripted("b", [ProviderError("overloaded", "busy", "b")], key="b")
    with pytest.raises(ProviderError) as e:
        FailoverClient([a, b]).complete("", [{"role": "user", "content": "q"}])
    assert e.value.kind == "overloaded"


# ------------------------------------------------------------------------------------ config and key handling
def test_user_configs_validated_and_presets_ignore_custom_urls():
    cfgs = providers.parse_user_configs([{"provider": "openai", "api_key": "k", "base_url": "http://evil.internal"}])
    assert cfgs[0].resolved().base_url == "https://api.openai.com/v1"          # SSRF guard: preset URL wins
    with pytest.raises(ValueError):
        providers.parse_user_configs([{"provider": "nope", "api_key": "k"}])
    with pytest.raises(ValueError):
        providers.parse_user_configs([{"provider": "custom", "api_key": "k", "base_url": "http://127.0.0.1:11434/v1", "model": "m"}])


def test_custom_endpoint_only_when_explicitly_allowed(monkeypatch):
    monkeypatch.setenv("TBK_ALLOW_CUSTOM_BASE_URL", "1")
    cfg = providers.parse_user_configs([{"provider": "custom", "api_key": "k", "base_url": "http://localhost:11434/v1", "model": "llama3"}])[0]
    assert cfg.resolved().base_url == "http://localhost:11434/v1"


def test_request_scoped_keys_come_first_and_do_not_leak_between_requests(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "server-key")
    user = providers.parse_user_configs([{"provider": "groq", "api_key": "user-key"}])
    with providers.llm_scope(user):
        order = [c.provider for c in providers.configured_providers()]
    assert order[0] == "groq" and "openai" in order
    assert [c.provider for c in providers.configured_providers()] == ["openai"]     # scope ended: user key gone


def test_use_llm_false_disables_and_no_keys_means_offline(monkeypatch):
    for v in [p["env"] for p in providers.PRESETS.values() if p["env"]]:
        monkeypatch.delenv(v, raising=False)
    assert providers.resolve_client(None) is None
    with providers.llm_scope(providers.parse_user_configs([{"provider": "openai", "api_key": "k"}])):
        assert providers.resolve_client(None) is not None and providers.resolve_client(False) is None


# ------------------------------------------------------------------------------------ agents on top
def script_investigation(provider_name="p", key="k"):
    return Scripted(provider_name, [
        reply("", tc(1, "get_alert", alert_id=LA["alert"])),
        reply("", tc(2, "recent_changes", service=LA["svc"], window_hours=24, depth=2)),
        reply("", tc(3, "owners_of", service=LA["cause_svc"]), tc(4, "blast_radius", service=LA["cause_svc"])),
        reply("Likely cause found."),
    ], key=key)


def test_llm_planner_drives_tools_and_feeds_results_back():
    prov = script_investigation()
    p = LLMPlanner(Goal("investigate", "helix", LA["ts"], alert_id=LA["alert"]), FailoverClient([prov]))
    ctx, hist, seen = ToolContext("helix", LA["ts"]), [], []
    while (s := p.next(hist)) is not None:
        seen.append(s.tool)
        hist.append(run_tool(ctx, s.tool, s.args))
    assert seen == ["get_alert", "recent_changes", "owners_of", "blast_radius"] and p.final_text == "Likely cause found."
    last_conv = prov.calls[-1]                                   # conversation sent on the final model call
    assert [m["role"] for m in last_conv].count("tool") == 4 and last_conv[-1]["role"] == "tool"


def test_full_run_survives_a_rate_limit_mid_investigation(monkeypatch):
    limited = Scripted("anthropic", [reply("", tc(1, "get_alert", alert_id=LA["alert"])),
                                     ProviderError("rate_limit", "429", "anthropic")], key="a")
    backup = Scripted("openai", [reply("", tc(2, "recent_changes", service=LA["svc"], window_hours=24, depth=2)),
                                 reply("", tc(3, "owners_of", service=LA["cause_svc"])), reply("done")], key="b")
    client = FailoverClient([limited, backup])
    monkeypatch.setattr("tbk.agents.orchestrator.resolve_client", lambda use_llm=None: client)
    r = run_incident("helix", LA["alert"])
    inv = next(a for a in r.agents if a.agent == "investigator")
    assert inv.payload["suspect"]["deploy"] == LA["cause_deploy"]            # the cause was still found
    assert r.llm["failovers"][0]["kind"] == "rate_limit" and r.llm["used"] == "openai/m"
    assert r.grounded_pct == 100.0


def test_all_providers_down_still_returns_a_grounded_partial_report(monkeypatch):
    dead = Scripted("a", [ProviderError("quota", "no credit", "a")], key="a")
    monkeypatch.setattr("tbk.agents.orchestrator.resolve_client", lambda use_llm=None: FailoverClient([dead]))
    r = run_incident("helix", LA["alert"])
    assert r.error is None and r.llm["failovers"][0]["kind"] == "quota"
    inv = next(a for a in r.agents if a.agent == "investigator")
    assert inv.payload["suspect"]["deploy"] == LA["cause_deploy"]          # a full investigation, not a hollow one
    assert r.llm["fell_back_to_playbook"] is True and r.grounded_pct == 100.0
    assert any("playbook" in s.why for s in inv.steps)


def test_rephrase_cannot_smuggle_an_ungrounded_entity():
    ctx = ToolContext("helix", LA["ts"])
    claims = pool_claims([run_tool(ctx, "owners_of", {"service": LA["cause_svc"]})])
    other = next(s for s in ds.model["services"] if s != LA["cause_svc"])
    payload = json.dumps({"claims": [{"i": i, "text": f"{c.text} (also affects {other})"} for i, c in enumerate(claims)]})
    polished = llm_rephrase(claims, FailoverClient([Scripted("a", [reply(payload)])]))
    v = verify_claims(ctx, polished)
    assert v.grounded_pct == 0.0 and all("mentions" in c.reason for c in v.claims)


def test_rephrase_failure_and_faithful_rephrase():
    ctx = ToolContext("helix", LA["ts"])
    claims = pool_claims([run_tool(ctx, "owners_of", {"service": LA["cause_svc"]})])
    assert [c.text for c in llm_rephrase(claims, FailoverClient([Scripted("a", [reply("not json")])]))] == [c.text for c in claims]
    ok = json.dumps({"claims": [{"i": i, "text": f"FYI: {c.text}."} for i, c in enumerate(claims)]})
    assert verify_claims(ctx, llm_rephrase(claims, FailoverClient([Scripted("a", [reply(ok)])]))).grounded_pct == 100.0


# ------------------------------------------------------------------------------------ HTTP surface
def test_api_header_validation_and_provider_listing():
    import base64
    from fastapi.testclient import TestClient
    from tbk.api.app import app
    c = TestClient(app)
    assert any(p["id"] == "openai" for p in c.get("/api/llm/providers").json()["presets"])
    bad = base64.b64encode(json.dumps([{"provider": "nope", "api_key": "k"}]).encode()).decode()
    assert c.post("/api/run", json={"tenant": "helix", "alert_id": LA["alert"]}, headers={"X-LLM-Providers": bad}).status_code == 400
    assert c.post("/api/llm/test", headers={"X-LLM-Providers": "%%%"}).status_code == 400
