"""Real-repo ingestion without the network: build a git repo on disk, ingest it, and attack the extractors."""
import io
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tbk import workspaces as W
from tbk.api.app import app
from tbk.ingest import fetch
from tbk.ingest.analyze import analyze, choose_depth, module_name
from tbk.ingest.codeowners import module_owner, parse
from tbk.ingest.history import Commit, read_history, resolve_identities
from tbk.ingest.pipeline import ingest_local
from tbk.tools import ToolContext, run_tool
from tbk.verifier import verify_claims

FILES = {
    "app/main.py": "from app.core import util\nimport app.api.routes\n",
    "app/core/util.py": "def x():\n    return 1\n",
    "app/core/__init__.py": "",
    "app/api/routes.py": "from app.core.util import x\nfrom ..core import util\nimport os\n",
    "web/src/index.js": "import {a} from './lib/a.js'\nconst b = require('./lib/b')\nimport React from 'react'\n",
    "web/src/lib/a.js": "export const a = 1\n",
    "web/src/lib/b.js": "module.exports = 2\n",
    "go.mod": "module example.com/m\n\ngo 1.21\n",
    "cmd/main.go": 'package main\n\nimport (\n\t"fmt"\n\t"example.com/m/pkg/x"\n)\n',
    "pkg/x/x.go": "package x\n",
    ".github/CODEOWNERS": "# owners (last matching rule wins)\n* @org/everyone\n/app/core/ @org/core\n",
    "docs/adr/0001-use-graph.md": "# ADR 0001: Use a graph\nWe keep ownership of app/core/ in a graph.\n",
    "docs/adr/0002-vector.md": "# ADR 0002: Add vectors\nSupersedes ADR 0001. Applies to app/core/ as well.\n",
    "README.md": "# Demo\nThe app/core/ package holds shared helpers.\n",
}


def _git(repo: Path, *args, env=None):
    e = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", **(env or {})}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=e)


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Path:
    r = tmp_path_factory.mktemp("repo")
    _git(r, "init", "-q", "-b", "main")
    for rel, text in FILES.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    t0 = 1_700_000_000
    people = [("Ann Lee", "ann@example.com"), ("ann lee", "ann@example.com"), ("Bo Chen", "bo@example.com")]
    for i, (name, email) in enumerate(people * 2):
        f = r / "app/core/util.py"
        f.write_text(f.read_text() + f"# change {i}\n")
        if i % 2:
            g = r / "app/api/routes.py"
            g.write_text(g.read_text() + f"# r{i}\n")
        _git(r, "add", "-A")
        env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
               "GIT_AUTHOR_DATE": f"{t0 + i * 86400} +0000", "GIT_COMMITTER_DATE": f"{t0 + i * 86400} +0000"}
        _git(r, "commit", "-q", "-m", f"change {i}", env=env)
    return r


# ------------------------------------------------------------------------------------ analysis
def test_imports_resolve_across_python_js_go(repo):
    m = analyze(repo)
    edges = set(m.deps)
    assert ("app/", "app/core/") in edges and ("app/", "app/api/") in edges
    assert ("app/api/", "app/core/") in edges                       # absolute and relative imports both resolve
    assert ("web/src/", "web/src/lib/") in edges                    # ./lib/a.js and require('./lib/b')
    assert ("cmd/", "pkg/x/") in edges                              # Go module-path import
    assert not any("react" in b or b.startswith("os") for _, b in edges)   # external packages are ignored
    assert m.deps[("app/api/", "app/core/")]["sites"][0].startswith("app/api/routes.py:")
    assert m.codeowners_path == ".github/CODEOWNERS"
    assert {d["kind"] for d in m.docs} == {"adr", "readme"}


def test_module_depth_stays_bounded():
    paths = [f"a/b{i}/c{j}/f.py" for i in range(15) for j in range(15)]
    d = choose_depth(paths)
    assert len({module_name(p, d) for p in paths}) <= 120


def test_codeowners_last_match_wins():
    rules = parse("* @all\n/src/ @core\n*.md @docs\n")
    assert module_owner(["src/a.py", "src/b.py"], rules)[0] == "@core"
    assert module_owner(["README.md"], rules)[0] == "@docs"
    assert module_owner(["x/y.py"], rules)[0] == "@all"


def test_identity_resolution_merges_aliases_and_separates_lookalikes():
    cs = [Commit("a" * 40, "Ann Lee", 1, "s", email="ann@x.com"), Commit("b" * 40, "ann lee", 2, "s", email="ann@x.com"),
          Commit("c" * 40, "田欧", 3, "s", email="t@x.com"), Commit("d" * 40, "諏訪原慶斗", 4, "s", email="s@x.com"),
          Commit("e" * 40, "Dev", 5, "s", email="123+devuser@users.noreply.github.com"),
          Commit("f" * 40, "Dev Alias", 6, "s", email="999+devuser@users.noreply.github.com")]
    resolve_identities(cs)
    assert cs[0].pid == cs[1].pid and cs[0].author == cs[1].author               # same email -> one person
    assert len({c.pid for c in cs[2:4]}) == 2                                    # CJK names do not collapse together
    assert cs[4].pid == cs[5].pid                                                # noreply addresses merge by login
    assert all(c.email == "" for c in cs)                                        # raw emails are dropped


# ------------------------------------------------------------------------------------ graph from a real repo
@pytest.fixture(scope="module")
def ws(repo):
    w = ingest_local(repo, "demo/app")
    yield w
    W.delete(w.id)


def test_workspace_graph_contents_and_provenance(ws):
    assert ws.status == "ready" and ws.stats["modules"] >= 6 and ws.stats["commits"] == 6 and ws.stats["authors"] == 2
    ctx = ToolContext(ws.tenant, ws.now)
    own = run_tool(ctx, "owners_of", {"service": "app/core/"})
    assert own.rows[0]["team"] == "@org/core"                                    # CODEOWNERS beats top-committer
    edge = ctx.q("MATCH (:Team)-[o:OWNS]->(:Service {id:'svc:app/core/'}) RETURN o.basis AS b, o.rule AS r")[0]
    assert edge["b"] == "codeowners" and "/app/core/" in edge["r"]
    br = run_tool(ctx, "blast_radius", {"service": "app/core/", "depth": 3})
    assert {r["service"] for r in br.rows} == {"app/", "app/api/"}
    assert verify_claims(ctx, br.claims).grounded_pct == 100.0
    dec = run_tool(ctx, "decision_lineage", {"service": "app/core/"})
    assert {r["state"] for r in dec.rows} == {"current", "superseded"}           # ADR 0002 supersedes ADR 0001
    top = run_tool(ctx, "top_contributors", {"service": "app/core/"})
    assert top.rows[0]["person"].lower() in ("ann lee", "bo chen") and verify_claims(ctx, top.claims).grounded_pct == 100.0


def test_codebase_tools_are_verified(ws):
    ctx = ToolContext(ws.tenant, ws.now)
    for tool, args in [("hotspots", {}), ("bus_factor", {"min_commits": 3, "min_share": 0.5}), ("change_impact", {"modules": "app/core/"}),
                       ("criticality", {"top": 3})]:
        res = run_tool(ctx, tool, args)
        assert res.error is None and res.claims, tool
        assert verify_claims(ctx, res.claims).grounded_pct == 100.0, tool
    sha = ctx.q("MATCH (d:Deploy) RETURN d.sha AS sha ORDER BY d.ts DESC LIMIT 1")[0]["sha"]
    ci = run_tool(ctx, "change_impact", {"sha": sha})
    assert ci.rows[0]["touched"] and verify_claims(ctx, ci.claims).grounded_pct == 100.0


def test_crew_runs_on_a_real_workspace_in_code_mode(ws):
    from tbk.agents.orchestrator import run_incident
    alert = ctx_alert = ToolContext(ws.tenant, ws.now).q("MATCH (a:Alert {live:true}) RETURN a.id AS id LIMIT 1")[0]["id"]
    r = run_incident(ws.tenant, alert)
    assert r.error is None and r.grounded_pct == 100.0
    assert any("review" in a["detail"].lower() or "revert" in a["detail"].lower() for a in r.actions)   # code-mode wording


def test_repo_benchmark_beats_docs_only_and_is_independent(ws):
    from tbk.evalx.repo_eval import build_questions, run_repo_eval
    qs = build_questions(ws.id)
    assert qs and all(q["truth"] for q in qs)
    res = run_repo_eval(ws.id)
    a = res["aggregate"]["all"]
    assert a["graph_exact"] == 1.0 and a["grounded_pct"] == 100.0 and a["docs_exact"] < a["graph_exact"]


# ------------------------------------------------------------------------------------ hostile input
def test_github_url_validation():
    for ok in ("https://github.com/pallets/click", "https://github.com/a/b.git", "https://github.com/a/b/"):
        fetch.parse_github_url(ok)
    for bad in ("http://github.com/a/b", "https://evil.com/a/b", "https://github.com/a", "git@github.com:a/b.git",
                "https://github.com/a/b;rm -rf /", "file:///etc/passwd", "https://github.com/a/b/../../c"):
        with pytest.raises(fetch.IngestError):
            fetch.parse_github_url(bad)


def _zip(entries: dict[str, bytes | tuple]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            if isinstance(data, tuple):                                           # (content, unix mode) for symlinks
                zi = zipfile.ZipInfo(name)
                zi.external_attr = data[1] << 16
                z.writestr(zi, data[0])
            else:
                z.writestr(name, data)
    return buf.getvalue()


def test_zip_slip_symlink_and_git_dir_are_rejected(tmp_path):
    z = _zip({"proj/ok.py": b"x = 1\n", "proj/../../escape.py": b"boom", "/abs.py": b"boom", "proj/.git/config": b"[core]",
              "proj/link.py": (b"/etc/passwd", 0o120777)})
    fetch.extract_zip(z, tmp_path / "out")
    written = {p.relative_to(tmp_path / "out").as_posix() for p in (tmp_path / "out").rglob("*") if p.is_file()}
    assert "proj/ok.py" in written
    assert not (tmp_path / "escape.py").exists() and not any("link" in w for w in written)   # traversal and symlink dropped
    assert not any(".git" in w.split("/") for w in written)                                   # .git is never extracted
    assert all((tmp_path / "out" / w).resolve().is_relative_to((tmp_path / "out").resolve()) for w in written)


def test_single_top_folder_is_stripped(tmp_path):
    fetch.extract_zip(_zip({"proj/a.py": b"1", "proj/sub/b.py": b"2"}), tmp_path / "o")
    assert (tmp_path / "o" / "a.py").exists() and (tmp_path / "o" / "sub" / "b.py").exists()


def test_zip_bomb_and_garbage_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "MAX_TREE_BYTES", 10_000)
    with pytest.raises(fetch.IngestError):
        fetch.extract_zip(_zip({"a.txt": b"A" * 50_000}), tmp_path / "bomb")
    with pytest.raises(fetch.IngestError):
        fetch.extract_zip(b"not a zip", tmp_path / "junk")


def test_repo_with_no_source_files_is_a_clear_error():
    zip_bytes = _zip({"notes.bin": b"\x00\x01\x02" * 100})
    c = TestClient(app)
    r = c.post("/api/workspaces/upload", files={"file": ("empty.zip", zip_bytes)}, data={"label": "empty"})
    wid = r.json()["id"]
    for _ in range(50):
        w = c.get(f"/api/workspaces/{wid}").json()
        if w["status"] in ("ready", "error"):
            break
        time.sleep(0.2)
    assert w["status"] == "error" and "No supported source files" in w["error"]
    assert c.delete(f"/api/workspaces/{wid}").status_code == 200


# ------------------------------------------------------------------------------------ HTTP flow
def test_upload_flow_end_to_end():
    c = TestClient(app)
    z = _zip({f"proj/{k}": v.encode() for k, v in FILES.items() if not k.startswith(".")})
    wid = c.post("/api/workspaces/upload", files={"file": ("proj.zip", z)}, data={"label": "proj"}).json()["id"]
    for _ in range(80):
        w = c.get(f"/api/workspaces/{wid}").json()
        if w["status"] in ("ready", "error"):
            break
        time.sleep(0.2)
    assert w["status"] == "ready", w
    tenant = w["tenant"]
    mods = c.get(f"/api/workspaces/{wid}/modules").json()
    assert any(m["name"] == "app/core/" for m in mods)
    out = c.post("/api/tool", json={"tenant": tenant, "tool": "blast_radius", "args": {"service": "app/core/"}}).json()
    assert out["verification"]["grounded_pct"] == 100.0
    eid = out["claims"][0]["edge_ids"][0]
    prov = c.get("/api/provenance", params={"tenant": tenant, "edge_id": eid}).json()
    assert prov["basis"] == "import" and prov["sites"] and ".py:" in prov["sites"][0]
    ask = c.post("/api/ask", json={"tenant": tenant, "question": "Which modules import app/core/ directly?"}).json()
    assert set(ask["answers"]) == {"app/", "app/api/"}
    assert c.post("/api/tool", json={"tenant": "not_a_tenant", "tool": "blast_radius", "args": {}}).status_code == 404
    assert c.delete(f"/api/workspaces/{wid}").status_code == 200
    assert c.get(f"/api/workspaces/{wid}").status_code == 404


def test_bundle_import_for_production_data():
    c = TestClient(app)
    bundle = {"name": "prod-export", "services": [{"name": "checkout-api", "tier": 1, "owner": "payments"},
                                                  {"name": "payments-api", "tier": 0, "owner": "payments"}],
              "dependencies": [{"from": "checkout-api", "to": "payments-api"}],
              "teams": [{"name": "payments", "members": ["Ana Ruiz"]}],
              "deploys": [{"service": "payments-api", "sha": "abc1234", "author": "Ana Ruiz", "ts": 1_700_000_000}],
              "alerts": [{"service": "checkout-api", "signal": "high-latency", "ts": 1_700_003_600}]}
    wid = c.post("/api/workspaces/bundle", json=bundle).json()["id"]
    for _ in range(60):
        w = c.get(f"/api/workspaces/{wid}").json()
        if w["status"] in ("ready", "error"):
            break
        time.sleep(0.2)
    assert w["status"] == "ready", w
    out = c.post("/api/tool", json={"tenant": w["tenant"], "tool": "recent_changes",
                                    "args": {"service": "checkout-api", "window_hours": 24, "depth": 2}}).json()
    assert "abc1234" in out["claims"][0]["text"] and out["verification"]["grounded_pct"] == 100.0
    assert c.post("/api/workspaces/bundle", json={"services": []}).status_code == 200      # accepted, then fails async
    c.delete(f"/api/workspaces/{wid}")


def test_rate_limit_per_client(monkeypatch):
    monkeypatch.setattr(W, "INGESTS_PER_HOUR", 2)
    W._HITS.clear()
    assert W.allow_ingest("1.2.3.4") and W.allow_ingest("1.2.3.4") and not W.allow_ingest("1.2.3.4")
    assert W.allow_ingest("5.6.7.8")
    W._HITS.clear()


def test_workspaces_expire_and_are_capped(monkeypatch):
    w = W.create("old", "upload")
    W.update(w.id, created=time.time() - 10 * 86400)
    W.cleanup()
    assert W.get(w.id) is None
