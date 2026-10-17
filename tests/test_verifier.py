"""'No path, no claim': the verifier must reject fabricated, expired and over-reaching claims."""
from tbk.tools import Claim, ToolContext, run_tool
from tbk.verifier import verify_claims


def _one(ctx, claim):
    return verify_claims(ctx, [claim]).claims[0]


def test_tool_claims_are_grounded(ctx, ds):
    la = ds.meta["live_alerts"][0]
    for name, args in [("blast_radius", {"service": la["svc"]}), ("recent_changes", {"service": la["svc"]}),
                       ("owners_of", {"service": la["cause_svc"]}), ("criticality", {})]:
        res = run_tool(ctx, name, args)
        assert res.claims, name
        assert verify_claims(ctx, res.claims).grounded_pct == 100.0, name


def test_fabricated_edge_rejected(ctx):
    v = _one(ctx, Claim("checkout-api depends on auth-service", edge_ids=[99_999_999]))
    assert v.status == "withheld" and "not found" in v.reason


def test_no_evidence_rejected(ctx):
    v = _one(ctx, Claim("checkout-api depends on auth-service"))
    assert v.status == "withheld" and "no supporting path" in v.reason


def test_inference_never_grounded(ctx):
    res = run_tool(ctx, "blast_radius", {"service": "auth-service"})
    c = res.claims[0]
    c.kind = "inference"
    assert _one(ctx, c).status == "withheld"


def test_smuggled_entity_rejected(ctx, ds):
    la = ds.meta["live_alerts"][0]
    c = run_tool(ctx, "blast_radius", {"service": la["svc"]}).claims[0]
    c.text += " and also payments-api is down"      # name not in the cited edges (checkout-api's own chain)
    other = "payments-api" if "payments-api" not in c.text.split(" and also")[0] else "ledger-store"
    c.text = c.text.replace("payments-api", other)
    v = _one(ctx, c)
    assert v.status == "withheld" and "mentions" in v.reason


def test_expired_edge_rejected_at_current_time(ds):
    dep = next(d for d in ds.model["deps"] if d["vt"] < ds.meta["now"])
    ctx = ToolContext("helix", ds.meta["now"])
    rows = ctx.q("MATCH (a:Service {id:$a})-[r:DEPENDS_ON]->(b:Service {id:$b}) RETURN ID(r) AS id",
                 {"a": f"svc:{dep['src']}", "b": f"svc:{dep['dst']}"})
    eid = rows[0]["id"]
    text = f"{dep['src']} depends on {dep['dst']}"
    assert _one(ctx, Claim(text, edge_ids=[eid])).status == "withheld"                       # no longer true
    past = Claim(text, edge_ids=[eid], as_of=dep["vf"] + 86_400)
    assert _one(ctx, past).status == "grounded"                                               # true back then
    assert _one(ctx, Claim(text, ended_edge_ids=[eid])).status == "grounded"                  # "it ended" is provable


def test_ended_edge_claim_requires_ended(ctx):
    owns = run_tool(ctx, "owners_of", {"service": "payments-api"}).claims[0]
    bad = Claim(owns.text, ended_edge_ids=owns.edge_ids)
    assert _one(ctx, bad).status == "withheld"


def test_asserted_property_must_match(ctx):
    res = run_tool(ctx, "criticality", {"top": 1})
    c = res.claims[0]
    assert _one(ctx, c).status == "grounded"
    c.assert_props[0]["value"] = c.assert_props[0]["value"] + 0.5
    assert _one(ctx, c).status == "withheld"


def test_grounded_pct_counts_rejections(ctx):
    good = run_tool(ctx, "blast_radius", {"service": "auth-service"}).claims[0]
    bad = Claim("made up", edge_ids=[99_999_999])
    assert verify_claims(ctx, [good, bad]).grounded_pct == 50.0


def test_cross_tenant_edge_ids_do_not_leak(ds):
    """Edge ids are per-graph: a claim built from helix evidence is checked against orbit's graph, not helix's."""
    helix = ToolContext("helix", ds.meta["now"])
    res = run_tool(helix, "owners_of", {"service": "payments-api"})
    orbit = ToolContext("orbit", ds.meta["now"])
    v = verify_claims(orbit, res.claims)
    # same ids may exist in orbit but they belong to different entities -> names don't line up
    assert v.grounded_pct < 100.0


def test_monotone_counter_claim_survives_concurrent_growth(ctx):
    res = run_tool(ctx, "rank_runbooks", {"signal": "error-rate"})
    stat = next(c for c in res.claims if c.assert_props)
    assert _one(ctx, stat).status == "grounded"
    ctx.q("MATCH (rb:Runbook {id:$i}) SET rb.attempts = rb.attempts + 5", {"i": stat.assert_props[0]["node_id"]})
    assert _one(ctx, stat).status == "grounded"            # counters grew since the read: the claim is still true
    stat.assert_props[0]["value"] += 1000                  # but an inflated minimum is rejected
    assert _one(ctx, stat).status == "withheld"
