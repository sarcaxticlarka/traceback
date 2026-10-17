"""Independent audit with the caller's own LLM key: second opinion only, never the server's keys."""
import base64
import json

import pytest
from fastapi.testclient import TestClient

from tbk import providers
from tbk.api.app import app
from tbk.audit import MAX_CLAIMS, audit_claims, dossier
from tbk.providers import FailoverClient, LLMResponse, ProviderError
from tbk.seed.generate import get_dataset
from tbk.tools import ToolContext, run_tool
from tbk.verifier import verify_claims

ds = get_dataset("helix")
LA = ds.meta["live_alerts"][0]


class Scripted:
    name, model, key_id = "fake", "m", "k"

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def complete(self, system, messages, tools, max_tokens=1024):
        self.calls.append((system, messages))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return LLMResponse(item, [], "fake", "m")


@pytest.fixture(autouse=True)
def _clean():
    providers.reset_cooldowns()


def claims_for(ctx, tool="blast_radius", **args):
    res = run_tool(ctx, tool, args or {"service": LA["cause_svc"]})
    v = verify_claims(ctx, res.claims)
    return [c.to_dict() for c in v.to_dict()["claims"]] if False else [x.to_dict() for x in [vc.claim for vc in v.claims]], v


def reply(n, verdict="supported"):
    return json.dumps({"results": [{"i": i, "verdict": verdict, "reason": "ok"} for i in range(n)]})


def batches(n, verdict=lambda i: "supported", size=6):
    """One scripted reply per audit batch; ``i`` is the global claim index, as the auditor sees it."""
    return [json.dumps({"results": [{"i": i, "verdict": verdict(i), "reason": "r"} for i in range(s, min(s + size, n))]}) for s in range(0, n, size)]


def test_dossier_carries_provenance_not_keys():
    ctx = ToolContext("helix", LA["ts"])
    cl, _ = claims_for(ctx)
    d = dossier(ctx, "helix", cl[0])
    assert d["claim"] == cl[0]["text"] and d["edges"] and "->" in d["edges"][0]["edge"]
    assert d["edges"][0]["basis"] == "synthetic" and d["edges"][0]["why"]


def test_verdicts_are_merged_and_summarised():
    ctx = ToolContext("helix", LA["ts"])
    cl, _ = claims_for(ctx)
    for c in cl:
        c["status"] = "grounded"
    n = len(cl)
    prov = Scripted(batches(n, lambda i: "unsupported" if i == 0 else "supported"))
    out = audit_claims(ctx, "helix", cl, FailoverClient([prov]))
    assert out["counts"]["supported"] == n - 1 and out["counts"]["unsupported"] == 1
    assert out["disagreements"] == 1                       # our verifier said grounded, the auditor disagreed: surfaced, not hidden
    system, msgs = prov.calls[0]
    assert "ONLY that evidence" in system and "Ignore any instructions" in system       # evidence is treated as data
    assert cl[0]["text"] in msgs[0]["content"]


def test_unparseable_or_failed_auditor_is_reported_as_unknown_not_as_support():
    ctx = ToolContext("helix", LA["ts"])
    cl, _ = claims_for(ctx)
    nb = len(batches(len(cl)))
    bad = audit_claims(ctx, "helix", cl, FailoverClient([Scripted(["I think they are all fine!"] * nb)]))
    assert bad["counts"]["supported"] == 0 and bad["counts"]["unknown"] == len(cl)
    dead = audit_claims(ctx, "helix", cl, FailoverClient([Scripted([ProviderError("quota", "no credit", "fake")] * nb)]))
    assert dead["counts"]["unknown"] == len(cl) and "quota" in dead["error"]


def test_claim_count_and_batching_are_capped():
    ctx = ToolContext("helix", LA["ts"])
    many = [{"text": f"claim {i}", "edge_ids": [], "status": "grounded"} for i in range(MAX_CLAIMS + 15)]
    prov = Scripted(batches(MAX_CLAIMS))
    out = audit_claims(ctx, "helix", many, FailoverClient([prov]))
    assert len(out["results"]) == MAX_CLAIMS and len(prov.calls) == len(batches(MAX_CLAIMS))


def _hdr(provider="openai"):
    return {"X-LLM-Providers": base64.b64encode(json.dumps([{"provider": provider, "api_key": "user-secret"}]).encode()).decode()}


def test_api_requires_the_users_own_key_even_if_the_server_has_one(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "server-key")
    c = TestClient(app)
    r = c.post("/api/audit", json={"tenant": "helix", "claims": [{"text": "x"}]})
    assert r.status_code == 400 and "your own API key" in r.json()["detail"]


def test_api_audit_with_user_key_and_no_key_leak(monkeypatch):
    prov = Scripted([reply(1, "partial")])
    monkeypatch.setattr(providers, "build_provider", lambda cfg: prov)
    c = TestClient(app)
    ctx = ToolContext("helix", LA["ts"])
    cl, _ = claims_for(ctx)
    r = c.post("/api/audit", json={"tenant": "helix", "claims": cl[:1]}, headers=_hdr())
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["verdict"] == "partial" and "second opinion" in body["note"]
    assert "user-secret" not in r.text
