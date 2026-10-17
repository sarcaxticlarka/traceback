"""HTTP API for the incident console. Run: ``uvicorn tbk.api.app:app --port 8000``."""
from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from pathlib import Path

import base64

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import isolation, memory, sim, subgraph, tasks
from ..agents.orchestrator import run_incident
from ..agents.qa import answer_question
from ..config import DATA_DIR, NOW, ROOT, get_settings
from ..evalx.baseline_reader import read_answer
from ..graph import get_store
from .. import providers
from ..seed.generate import get_dataset
from ..seed.load import load_dataset
from ..switches import graph_switch
from ..tools import REGISTRY, ToolContext
from ..verifier import clear_vocabulary_cache

app = FastAPI(title="TRACEBACK", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_RUNS: "OrderedDict[str, dict]" = OrderedDict()
_RUNS_LOCK = threading.Lock()


def _tenant(t: str) -> str:
    if t not in get_settings().tenants:
        raise HTTPException(404, f"unknown tenant {t!r}; configured: {get_settings().tenants}")
    return t


def _user_llm(x_llm_providers: str | None) -> list[providers.ProviderConfig]:
    """Per-request provider keys from the frontend (base64 JSON in a header). Held for this request only."""
    if not x_llm_providers:
        return []
    try:
        raw = json.loads(base64.b64decode(x_llm_providers).decode())
        return providers.parse_user_configs(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(400, f"invalid X-LLM-Providers: {str(e)[:160]}")


def _ctx(tenant: str, at: int = NOW) -> ToolContext:
    return ToolContext(_tenant(tenant), at)


class RunRequest(BaseModel):
    tenant: str
    alert_id: str
    graph_enabled: bool = True
    use_llm: bool | None = None
    outcome: bool | None = None
    auto_approve: bool = False


class AskRequest(BaseModel):
    tenant: str
    question: str
    graph_enabled: bool = True
    use_llm: bool | None = None


class ApproveRequest(BaseModel):
    tenant: str
    approver_id: str | None = None


class VerifyRequest(BaseModel):
    tenant: str
    claims: list[dict]


class LearnRequest(BaseModel):
    tenant: str
    n: int = 240


# --------------------------------------------------------------------------------------- system
@app.get("/api/health")
def health():
    try:
        ok = bool(get_store().db.list_graphs() is not None)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    s = get_settings()
    return {"ok": ok, "tenants": s.tenants, "llm": bool(providers.env_configs()), "llm_model": ", ".join(c.provider for c in providers.env_configs()) or None,
            "now": NOW, "graphs": sorted(g for g in get_store().db.list_graphs() if g.startswith("t_"))}


@app.get("/api/llm/providers")
def llm_providers():
    """Presets the frontend can offer, and which providers the server already has keys for (names only)."""
    return {"presets": [{"id": k, "label": v["label"], "default_model": v["model"], "custom_url": k == "custom"}
                        for k, v in providers.PRESETS.items() if k != "custom" or providers.allow_custom_base_url()],
            "server_default": [c.provider for c in providers.env_configs()]}


@app.post("/api/llm/test")
def llm_test(x_llm_providers: str | None = Header(default=None)):
    """Send a one-token request to each supplied provider and report ok / error kind. Never echoes keys."""
    out = []
    for cfg in _user_llm(x_llm_providers):
        t0 = time.perf_counter()
        try:
            r = providers.build_provider(cfg).complete("", [{"role": "user", "content": "Reply with the single word OK."}], None, 16)
            out.append({"provider": cfg.provider, "model": cfg.resolved().model, "ok": True, "ms": round((time.perf_counter() - t0) * 1000),
                        "reply": r.text[:20]})
        except providers.ProviderError as e:
            out.append({"provider": cfg.provider, "model": cfg.resolved().model, "ok": False, "kind": e.kind, "error": str(e)[:160]})
        except ValueError as e:
            out.append({"provider": cfg.provider, "ok": False, "kind": "config", "error": str(e)})
    return out


@app.get("/api/tools")
def tools_catalog():
    return [{"name": t.name, "description": t.description, "cypher_ref": t.cypher_ref,
             "params": t.params, "required": t.required} for t in REGISTRY.values()]


@app.post("/api/admin/reseed")
def reseed(tenant: str = Query(...)):
    _tenant(tenant)
    counts = load_dataset(get_store(), get_dataset(tenant), reset=True)
    clear_vocabulary_cache(tenant)
    with _RUNS_LOCK:
        _RUNS.clear()
    return {"tenant": tenant, "loaded": counts}


# --------------------------------------------------------------------------------------- incidents
@app.get("/api/alerts")
def alerts(tenant: str, live_only: bool = True):
    rows = get_store().query(_tenant(tenant), "MATCH (a:Alert)-[:FIRED_ON]->(s:Service) WHERE $all OR a.live = true "
                             "RETURN a.id AS id, a.ts AS ts, a.severity AS severity, a.signal AS signal, "
                             "s.name AS service, s.tier AS tier ORDER BY ts DESC LIMIT 60", {"all": not live_only})
    return rows


@app.post("/api/run")
def run(req: RunRequest, x_llm_providers: str | None = Header(default=None)):
    _tenant(req.tenant)
    with providers.llm_scope(_user_llm(x_llm_providers)):
        report = run_incident(req.tenant, req.alert_id, graph_enabled=req.graph_enabled, use_llm=req.use_llm,
                              outcome=req.outcome, auto_approve=req.auto_approve).to_dict()
    with _RUNS_LOCK:
        _RUNS[report["run_id"]] = report
        while len(_RUNS) > 200:
            _RUNS.popitem(last=False)
    return report


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    if run_id not in _RUNS:
        raise HTTPException(404, "run not found")
    return _RUNS[run_id]


@app.get("/api/subgraph")
def get_subgraph(tenant: str, edge_ids: str = "", node_ids: str = ""):
    eids = [int(x) for x in edge_ids.split(",") if x.strip()]
    nids = [x for x in node_ids.split(",") if x.strip()]
    return subgraph.evidence_subgraph(_tenant(tenant), eids, nids)


@app.get("/api/graph/services")
def service_map(tenant: str):
    return subgraph.service_map(_tenant(tenant))


@app.get("/api/graph/overview")
def graph_overview(tenant: str):
    return subgraph.overview(_tenant(tenant))


# --------------------------------------------------------------------------------------- company brain
@app.post("/api/ask")
def ask(req: AskRequest, x_llm_providers: str | None = Header(default=None)):
    _tenant(req.tenant)
    baseline = sorted(read_answer(req.tenant, req.question))
    if not req.graph_enabled:
        return {"question": req.question, "graph_enabled": False, "answers": [], "text": "Graph layer is OFF: only "
                "document retrieval is available.", "baseline_docs_only": baseline,
                "verification": {"grounded_pct": 0.0, "n_claims": 0, "claims": []}, "steps": []}
    with graph_switch(True), providers.llm_scope(_user_llm(x_llm_providers)):
        a = answer_question(req.tenant, req.question, llm=providers.resolve_client(req.use_llm)).to_dict()
    a["graph_enabled"] = True
    a["baseline_docs_only"] = baseline
    return a


@app.post("/api/verify")
def verify(req: VerifyRequest):
    """Verify arbitrary claims against the tenant graph (used by the console's 'inject a hallucination' demo)."""
    from ..tools import Claim
    from ..verifier import verify_claims
    ctx = _ctx(req.tenant)
    claims = [Claim.from_dict(c) for c in req.claims[:50]]
    return verify_claims(ctx, claims).to_dict()


# --------------------------------------------------------------------------------------- memory / coordination
@app.get("/api/memory/runbooks")
def runbooks(tenant: str):
    return _ctx(tenant).q("MATCH (rb:Runbook)-[:FOR_SIGNAL]->(s:Signal) RETURN rb.id AS id, rb.title AS title, "
                          "s.name AS signal, rb.attempts AS attempts, rb.successes AS successes, rb.last_used AS last_used "
                          "ORDER BY signal, id")


@app.get("/api/memory/facts")
def facts(tenant: str):
    return memory.current_facts(_ctx(tenant), 40)


@app.get("/api/memory/episodes")
def episodes(tenant: str):
    return memory.recent_episodes(_ctx(tenant), 30)


@app.get("/api/tasks")
def list_tasks(tenant: str, incident: str = ""):
    return tasks.list_tasks(_ctx(tenant), incident or None)


@app.get("/api/actions")
def list_actions(tenant: str, incident: str = ""):
    return memory.list_actions(_ctx(tenant), incident or None)


@app.post("/api/actions/{action_id}/approve")
def approve(action_id: str, req: ApproveRequest):
    if not memory.set_action_status(_ctx(req.tenant), action_id, "executed", req.approver_id):
        raise HTTPException(404, "action not found")
    return {"id": action_id, "status": "executed"}


@app.post("/api/sim/learning")
def learning(req: LearnRequest):
    return sim.learning_curve(_ctx(req.tenant), n=max(60, min(req.n, 600)))


@app.get("/api/sim/learning")
def learning_cached(tenant: str):
    p = DATA_DIR / f"learning_{_tenant(tenant)}.json"
    if not p.exists():
        return sim.learning_curve(_ctx(tenant))
    return json.loads(p.read_text())


# --------------------------------------------------------------------------------------- proof
@app.get("/api/eval")
def eval_results():
    p = DATA_DIR / "eval_results.json"
    if not p.exists():
        from ..evalx.run import evaluate
        return evaluate()
    return json.loads(p.read_text())


@app.post("/api/isolation")
def isolation_check():
    return isolation.check_isolation("helix", "orbit")


@app.get("/api/bench")
def bench_results():
    p = DATA_DIR / "bench_results.json"
    if not p.exists():
        raise HTTPException(404, "run `python -m tbk.bench` first")
    return json.loads(p.read_text())


# --------------------------------------------------------------------------------------- static console
_DIST = ROOT / "web" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = _DIST / path
        return FileResponse(f if f.is_file() else _DIST / "index.html")
