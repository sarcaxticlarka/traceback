"""Re-verifying evidence bundles on your own machine: no server, no FalkorDB, no LLM."""
import json
import shutil
from argparse import Namespace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tbk import workspaces as W
from tbk.api.app import app
from tbk.cli import cmd_verify
from tbk.evidence import FORMAT, build_bundle
from tbk.ingest.pipeline import ingest_local
from tbk.seed.generate import get_dataset
from tbk.tools import ToolContext, run_tool
from tbk.verifier import verify_claims
from tbk.verify_local import rebuild, verify_bundle
from tests.test_ingest import FILES, repo  # noqa: F401  (fixture)


def claims(ctx, calls):
    out = []
    for tool, args in calls:
        res = run_tool(ctx, tool, args)
        out += [vc.to_dict() for vc in verify_claims(ctx, res.claims).claims]
    return out


@pytest.fixture(scope="module")
def ws(repo):
    w = ingest_local(repo, "demo/app")
    yield w
    W.delete(w.id)


@pytest.fixture
def bundle(ws):
    ctx = ToolContext(ws.tenant, ws.now)
    cl = claims(ctx, [("blast_radius", {"service": "app/core/"}), ("owners_of", {"service": "app/core/"}),
                      ("top_contributors", {"service": "app/core/"}), ("hotspots", {"top": 3})])
    return build_bundle(ctx, ws.tenant, cl)


def test_bundle_is_structural_not_tied_to_edge_ids(bundle):
    assert bundle["format"] == FORMAT and len(bundle["sha256"]) == 64 and bundle["source"]["kind"] == "upload"
    f = bundle["claims"][0]["facts"][0]
    assert {"type", "from", "to", "basis"} <= set(f) and f["from"]["name"] and "edge_ids" not in json.dumps(bundle["claims"][0])
    assert bundle["source"]["head_sha"] and len(bundle["source"]["head_sha"]) == 40            # the analysed commit is pinned


def test_every_claim_reverifies_from_the_source_alone(bundle, repo):
    ds, kind, root, notes = rebuild(bundle, repo=str(repo), log=lambda *_: None)
    rep = verify_bundle(bundle, ds, kind, root, show_sources=True)
    assert rep["counts"]["mismatch"] == 0 and rep["counts"]["verified"] >= len(bundle["claims"]) - 1
    imports = [s for r in rep["claims"] for s in r.get("sources", [])]
    assert imports and all("import" in s or "require" in s or "from" in s for s in imports)    # the raw source lines are shown
    assert not notes                                                                           # checkout is at the analysed commit


def test_tampered_bundle_is_caught(bundle, repo):
    ds, kind, root, _ = rebuild(bundle, repo=str(repo), log=lambda *_: None)
    forged = json.loads(json.dumps(bundle))
    dep = next(c for c in forged["claims"] if any(f["type"] == "DEPENDS_ON" for f in c["facts"]))
    fact = next(f for f in dep["facts"] if f["type"] == "DEPENDS_ON")
    fact["to"]["name"] = "web/src/"                                         # claim a dependency that does not exist
    assert verify_bundle(forged, ds, kind)["counts"]["mismatch"] >= 1
    forged2 = json.loads(json.dumps(bundle))
    next(f for c in forged2["claims"] for f in c["facts"] if f["type"] == "DEPENDS_ON")["sites"] = ["app/main.py:99 → app/core/util.py"]
    assert verify_bundle(forged2, ds, kind)["counts"]["mismatch"] >= 1       # fabricated import line


def test_changed_source_no_longer_supports_the_claim(bundle, repo, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(repo, copy)
    p = copy / "app/api/routes.py"
    p.write_text("import os\n")                                              # the import the claim relies on is gone
    (copy / "app/main.py").write_text("import os\n")
    ds, kind, root, notes = rebuild(bundle, repo=str(copy), log=lambda *_: None)
    rep = verify_bundle(bundle, ds, kind, root)
    assert rep["counts"]["mismatch"] >= 1


def test_cli_exit_code_reflects_result(bundle, repo, tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps(bundle))
    assert cmd_verify(Namespace(bundle=str(good), repo=str(repo), data=None, show_sources=True, json=str(tmp_path / "r.json"))) == 0
    out = capsys.readouterr().out
    assert "verified" in out and "source:" in out and (tmp_path / "r.json").exists()
    bad = json.loads(json.dumps(bundle))
    next(f for c in bad["claims"] for f in c["facts"] if f["type"] == "DEPENDS_ON")["to"]["name"] = "nowhere/"
    badp = tmp_path / "bad.json"
    badp.write_text(json.dumps(bad))
    assert cmd_verify(Namespace(bundle=str(badp), repo=str(repo), data=None, show_sources=False, json=None)) == 1


def test_demo_company_bundles_verify_by_regeneration_without_any_database():
    ds = get_dataset("helix")
    la = ds.meta["live_alerts"][0]
    ctx = ToolContext("helix", la["ts"])
    cl = claims(ctx, [("blast_radius", {"service": la["svc"]}), ("recent_changes", {"service": la["svc"], "window_hours": 24, "depth": 2}),
                      ("owners_of", {"service": la["cause_svc"]}), ("criticality", {"top": 3})])
    b = build_bundle(ctx, "helix", cl)
    assert b["source"]["kind"] == "synthetic"
    d, kind, root, _ = rebuild(b, log=lambda *_: None)
    rep = verify_bundle(b, d, kind)
    assert rep["counts"]["mismatch"] == 0 and rep["counts"]["verified"] >= 8
    b["claims"][1]["facts"][0]["to"]["name"] = "ledger-store" if b["claims"][1]["facts"][0]["to"]["name"] != "ledger-store" else "db-proxy"
    assert verify_bundle(b, d, kind)["counts"]["mismatch"] >= 1


def test_api_endpoint_builds_bundle(ws):
    c = TestClient(app)
    ctx = ToolContext(ws.tenant, ws.now)
    cl = claims(ctx, [("blast_radius", {"service": "app/core/"})])
    r = c.post("/api/evidence-bundle", json={"tenant": ws.tenant, "claims": cl})
    assert r.status_code == 200 and r.json()["format"] == FORMAT and r.json()["claims"][0]["facts"]


def test_learned_counters_are_runtime_not_mismatch():
    """Runbook counters grow as the crew learns; the pristine source can't reproduce them, so they are 'run-time only'."""
    from tbk.verify_local import _prop_check
    ds = get_dataset("helix")
    rb = next(r for r in ds.nodes["Runbook"])
    base = rb["attempts"]
    assert _prop_check({"node_id": rb["id"], "prop": "attempts", "value": base, "op": "ge"}, ds)[0] == "verified"
    assert _prop_check({"node_id": rb["id"], "prop": "attempts", "value": base + 9, "op": "ge"}, ds)[0] == "runtime"
    assert _prop_check({"node_id": rb["id"], "prop": "attempts", "value": base + 9}, ds)[0] == "mismatch"      # exact claims stay strict
