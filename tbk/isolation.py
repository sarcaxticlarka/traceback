"""Tenant-isolation proof. Plants a canary person/deploy in one tenant and shows it is invisible to the other.

Run via ``python -m tbk.isolation`` or the API; also asserted in tests. The canary is removed afterwards.
"""
from __future__ import annotations

from .config import NOW
from .graph import get_store
from .tools import ToolContext, run_tool
from .verifier import clear_vocabulary_cache, verify_claims

CANARY_NAME = "Zed Canary"
CANARY_SHA = "ca11ab1"
SERVICE = "payments-api"          # exists in every tenant: the overlapping-name stress case


def _plant(tenant: str) -> None:
    get_store().query(tenant, (
        "MATCH (s:Service {id:$s}) "
        "MERGE (p:Person {id:'person:zed-canary'}) SET p.name = $n "
        "MERGE (d:Deploy {id:'dep:canary'}) SET d.sha = $sha, d.ts = $ts, d.status = 'success', d.summary = 'canary' "
        "MERGE (p)-[:AUTHORED]->(d) MERGE (d)-[:DEPLOYED_TO]->(s)"),
        {"s": f"svc:{SERVICE}", "n": CANARY_NAME, "sha": CANARY_SHA, "ts": NOW - 1800}, raw=True)
    clear_vocabulary_cache(tenant)


def _remove(tenant: str) -> None:
    get_store().query(tenant, "MATCH (n) WHERE n.id IN ['person:zed-canary','dep:canary'] DETACH DELETE n", raw=True)
    clear_vocabulary_cache(tenant)


def check_isolation(a: str = "helix", b: str = "orbit") -> dict:
    report: dict = {"planted_in": a, "probed": b, "checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})

    _plant(a)
    try:
        ctx_a, ctx_b = ToolContext(a, NOW), ToolContext(b, NOW)
        res_a = run_tool(ctx_a, "recent_changes", {"service": SERVICE, "window_hours": 2, "depth": 0})
        res_b = run_tool(ctx_b, "recent_changes", {"service": SERVICE, "window_hours": 2, "depth": 0})
        check("canary visible inside its own tenant", any(CANARY_NAME in c.text for c in res_a.claims),
              f"{len(res_a.claims)} claim(s) in {a}")
        check("canary absent from other tenant's tool output", not any(CANARY_NAME in c.text for c in res_b.claims),
              f"{len(res_b.claims)} claim(s) in {b}")
        raw_b = get_store().query(b, "MATCH (n) WHERE n.id IN ['person:zed-canary','dep:canary'] RETURN count(n) AS n", raw=True)
        check("canary node does not exist in other tenant's graph", raw_b[0]["n"] == 0)
        # overlapping names, different graphs: same question, tenant-specific answers
        oa = run_tool(ctx_a, "owners_of", {"service": SERVICE})
        ob = run_tool(ctx_b, "owners_of", {"service": SERVICE})
        check("same service name resolves independently per tenant",
              oa.rows and ob.rows and (oa.rows[0]["members"] != ob.rows[0]["members"] or oa.rows[0]["team"] != ob.rows[0]["team"]),
              f"{a}: team {oa.rows[0]['team'] if oa.rows else None}; {b}: team {ob.rows[0]['team'] if ob.rows else None}")
        # a claim carrying tenant A's evidence must not verify against tenant B's graph
        ev = [c for c in res_a.claims if CANARY_NAME in c.text]
        if ev:
            v = verify_claims(ctx_b, ev)
            check("tenant-A evidence is rejected by tenant-B verifier", v.grounded_pct == 0.0,
                  v.claims[0].reason if v.claims else "")
        # graph handle routing: tenant slug cannot escape its graph name
        try:
            get_store().graph("bad name; MATCH (n) DETACH DELETE n")
            check("malformed tenant slug rejected", False)
        except ValueError:
            check("malformed tenant slug rejected", True)
    finally:
        _remove(a)
    report["ok"] = all(c["ok"] for c in report["checks"])
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(check_isolation(), indent=2))
