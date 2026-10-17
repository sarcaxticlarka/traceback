"""End-to-end ingestion: fetch -> analyze -> history -> build graph -> load into FalkorDB -> persist model."""
from __future__ import annotations

import contextvars
import json
import shutil
import threading
import time
import traceback
from pathlib import Path

from .. import workspaces as W
from ..graph import get_store
from ..seed.load import load_dataset
from ..subgraph import overview
from ..verifier import clear_vocabulary_cache
from . import fetch
from .analyze import RepoModel, analyze
from .build import build_dataset
from .history import head_sha, read_history
from .limits import MAX_COMMITS


def _progress(wid: str, stage: str, pct: int, message: str = "") -> None:
    W.update(wid, status="running", stage=stage, pct=pct, message=message)


def process_tree(wid: str, root: Path, label: str, *, blob_base: str = "", with_history: bool = True) -> dict:
    ws = W.get(wid)
    t0 = time.time()
    _progress(wid, "analyze", 30, "Parsing sources and resolving imports")
    model: RepoModel = analyze(root)
    if not model.files:
        raise fetch.IngestError("No supported source files found (Python, JS/TS, Go, Java/Kotlin, C/C++, ...).")
    commits, sha = [], ""
    if with_history:
        _progress(wid, "history", 50, "Reading git history")
        commits = read_history(root, MAX_COMMITS)
        sha = head_sha(root)
    _progress(wid, "build", 65, "Building the knowledge graph")
    ds, summary = build_dataset(ws.tenant, label, model, commits, blob_base)
    _progress(wid, "load", 80, "Loading into FalkorDB")
    counts = load_dataset(get_store(), ds, reset=True)
    clear_vocabulary_cache(ws.tenant)
    ov = overview(ws.tenant)
    summary.update(graph_nodes=sum(n["n"] for n in ov["nodes"]), graph_edges=ov["edges"], ingest_s=round(time.time() - t0, 1),
                   skipped=dict(model.skipped), codeowners_path=model.codeowners_path, head_sha=sha, max_commits=MAX_COMMITS)
    d = W.workspace_dir(wid)
    (d / "model.json").write_text(json.dumps(model.to_json()))
    (d / "corpus.json").write_text(json.dumps(model.corpus))
    (d / "commits.json").write_text(json.dumps([{"sha": c.sha[:7], "author": c.author, "ts": c.ts, "subject": c.subject,
                                                 "files": c.files[:60]} for c in commits[:MAX_COMMITS]]))
    return summary


def _run(wid: str, work) -> None:
    try:
        summary = work()
        ws = W.get(wid)
        W.update(wid, status="ready", stage="ready", pct=100, message="Ready", stats=summary, now=summary["now"])
    except fetch.IngestError as e:
        W.update(wid, status="error", stage="error", error=str(e), message=str(e))
        _cleanup_graph(wid)
    except Exception as e:                                   # never leak internals/paths to the client
        traceback.print_exc()
        W.update(wid, status="error", stage="error", error="Unexpected error while analysing this repository.",
                 message=f"{type(e).__name__}")
        _cleanup_graph(wid)


def _cleanup_graph(wid: str) -> None:
    ws = W.get(wid)
    if ws:
        try:
            get_store().drop(ws.tenant)
        except Exception:
            pass


def start_github(url: str) -> W.Workspace:
    owner, repo = fetch.parse_github_url(url)
    ws = W.create(f"{owner}/{repo}", "github", f"https://github.com/{owner}/{repo}")

    def work():
        tmp = W.workspace_dir(ws.id) / "src"
        try:
            _progress(ws.id, "fetch", 8, f"Cloning {owner}/{repo} (shallow, read-only)")
            fetch.clone_github(url, tmp)
            return process_tree(ws.id, tmp, f"{owner}/{repo}", blob_base=f"https://github.com/{owner}/{repo}/blob/HEAD")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    threading.Thread(target=contextvars.copy_context().run, args=(_run, ws.id, work), daemon=True).start()
    return ws


def start_upload(label: str, *, zip_bytes: bytes | None = None, files: list[tuple[str, bytes]] | None = None) -> W.Workspace:
    ws = W.create(label or "upload", "upload")

    def work():
        tmp = W.workspace_dir(ws.id) / "src"
        try:
            _progress(ws.id, "fetch", 8, "Unpacking upload safely")
            if zip_bytes is not None:
                fetch.extract_zip(zip_bytes, tmp)
            else:
                fetch.write_uploaded_files(files or [], tmp)
            return process_tree(ws.id, tmp, ws.label, with_history=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    threading.Thread(target=contextvars.copy_context().run, args=(_run, ws.id, work), daemon=True).start()
    return ws


def ingest_local(path: Path, label: str, with_history: bool = True) -> W.Workspace:
    """Synchronous ingest of a local checkout (used by the CLI and tests)."""
    ws = W.create(label, "upload")
    try:
        summary = process_tree(ws.id, path, label, with_history=with_history)
        W.update(ws.id, status="ready", stage="ready", pct=100, stats=summary, now=summary["now"])
    except Exception as e:
        W.update(ws.id, status="error", error=str(e))
        raise
    return W.get(ws.id)


def start_bundle(data: dict, label: str = "bundle") -> W.Workspace:
    from .bundle import build_bundle
    ws = W.create(_label(data, label), "bundle")

    def work():
        _progress(ws.id, "build", 40, "Building the graph from your bundle")
        ds, summary = build_bundle(ws.tenant, data)
        _progress(ws.id, "load", 80, "Loading into FalkorDB")
        load_dataset(get_store(), ds, reset=True)
        clear_vocabulary_cache(ws.tenant)
        ov = overview(ws.tenant)
        summary.update(graph_nodes=sum(n["n"] for n in ov["nodes"]), graph_edges=ov["edges"], ingest_s=0.0, skipped={})
        return summary

    threading.Thread(target=contextvars.copy_context().run, args=(_run, ws.id, work), daemon=True).start()
    return ws


def _label(data: dict, default: str) -> str:
    return str(data.get("name") or default)[:80]
