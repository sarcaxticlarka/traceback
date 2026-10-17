"""Benchmark the graph agent against a docs-only baseline on a *real* repository workspace.

Ground truth is computed from the analyser's own module model and the raw commit list (``model.json`` /
``commits.json``), never from FalkorDB. The baseline sees the same files the graph was built from (README, docs and
source chunks) through hybrid retrieval (k=8) and a reader that parses the imports in the chunks it retrieved.
"""
from __future__ import annotations

import json
import math
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

from .. import workspaces as W
from ..agents.qa import answer_question, detect_intent
from ..baseline import DocIndex
from ..ingest.analyze import FileInfo, RepoModel, extract_imports, module_name
from ..ingest.build import MAX_DEPLOY_MODULES
from ..ingest.history import is_bot
from .run import f1, grade

K = 8


def _load(wid: str):
    d = W.workspace_dir(wid)
    return (json.loads((d / "model.json").read_text()), json.loads((d / "corpus.json").read_text()),
            json.loads((d / "commits.json").read_text()))


def _bfs(adj: dict[str, set[str]], start: str, depth: int) -> set[str]:
    seen, frontier = {start}, {start}
    for _ in range(depth):
        frontier = {y for x in frontier for y in adj.get(x, ())} - seen
        seen |= frontier
    return seen - {start}


def build_questions(wid: str, seed: int = 3, per_type: int = 6) -> list[dict]:
    model, _, commits = _load(wid)
    out_adj, in_adj = defaultdict(set), defaultdict(set)
    for d in model["deps"]:
        out_adj[d["src"]].add(d["dst"])
        in_adj[d["dst"]].add(d["src"])
    depth = model["module_depth"]
    per_module: dict[str, Counter] = defaultdict(Counter)
    for c in commits:
        if is_bot(c["author"]):
            continue
        lines: dict[str, int] = defaultdict(int)
        for path, n in c["files"]:
            m = module_name(path, depth)
            if m in model["modules"]:
                lines[m] += n
        for m, _ in sorted(lines.items(), key=lambda kv: -kv[1])[:MAX_DEPLOY_MODULES]:
            per_module[m][c["author"]] += 1
    rng = random.Random(seed)
    qs: list[dict] = []

    def pick(cands, n):
        cands = sorted(cands)
        return rng.sample(cands, min(n, len(cands)))

    def add(intent, bucket, text, truth):
        qs.append({"id": f"{wid}-{len(qs):02d}", "intent": intent, "bucket": bucket, "question": text, "truth": sorted(truth)})

    for m in pick([m for m in model["modules"] if out_adj[m]], per_type):
        add("direct_deps", "1-hop", f"Which modules does {m} directly depend on?", out_adj[m])
    for m in pick([m for m in model["modules"] if in_adj[m]], per_type):
        add("direct_dependents", "1-hop", f"Which modules import {m} directly?", in_adj[m])
    uniq = [m for m, c in per_module.items() if sum(c.values()) >= 5 and [n for _, n in c.most_common(2)][0] != ([n for _, n in c.most_common(2)] + [-1])[1]]
    for m in pick(uniq, per_type):
        add("top_committer", "1-hop", f"Who made the most commits to {m}?", {per_module[m].most_common(1)[0][0]})
    for m in pick([m for m in model["modules"] if len(_bfs(in_adj, m, 2)) >= 2], per_type):
        add("dependents_2hop", "2-hop", f"Which modules depend on {m} within 2 hops?", _bfs(in_adj, m, 2))
    for m in pick([m for m in model["modules"] if len(_bfs(in_adj, m, 6)) >= 3], per_type):
        add("blast_all", "3+-hop", f"What is the full blast radius if {m} fails?", _bfs(in_adj, m, 6))
    return qs


class _DocsOnly:
    """Hybrid retrieval over file chunks + a reader that parses imports in what it retrieved."""

    def __init__(self, wid: str):
        model, corpus, _ = _load(wid)
        self.model = model
        docs = [{"id": c["path"], "kind": "src", "title": c["path"], "body": c["text"], "ts": 0,
                 "embedding": __import__("tbk.embeddings", fromlist=["embed"]).embed(c["path"] + " " + c["text"][:800])} for c in corpus]
        self.idx = DocIndex(docs)
        self.texts = {c["path"]: c["text"] for c in corpus}
        m = RepoModel(root="", module_depth=model["module_depth"])
        m.files = {p: FileInfo(p, f["lang"], f["loc"], 0) for p, f in model["files"].items()}
        self.rm = m

    def answer(self, question: str) -> set[str]:
        intent = detect_intent(question)
        mod = next((x for x in sorted(self.model["modules"], key=len, reverse=True) if x in question), None)
        if not mod or intent in ("top_committer",):
            return set()
        hits = {h.id for h in self.idx.search(question, K) if h.id in self.rm.files}
        edges = defaultdict(set)
        for src, dst, _ in extract_imports(self.rm, only=hits, texts=self.texts):
            a, b = self.rm.module_of(src), self.rm.module_of(dst)
            if a != b and a in self.model["modules"] and b in self.model["modules"]:
                edges[a].add(b)
        if intent == "direct_deps":
            return set(edges.get(mod, set()))
        rev = defaultdict(set)
        for a, bs in edges.items():
            for b in bs:
                rev[b].add(a)
        depth = {"direct_dependents": 1, "dependents_2hop": 2}.get(intent, 6)
        return _bfs(rev, mod, depth)


def run_repo_eval(wid: str) -> dict:
    ws = W.get(wid)
    qs = build_questions(wid)
    base = _DocsOnly(wid)
    rows = []
    for q in qs:
        truth = set(q["truth"])
        t0 = time.perf_counter()
        g = answer_question(ws.tenant, q["question"], at=ws.now)
        g_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        b = base.answer(q["question"])
        b_ms = (time.perf_counter() - t0) * 1000
        rows.append({**q, "graph": {"pred": sorted(g.answers), **grade(g.answers, truth), "grounded_pct": g.verification.get("grounded_pct", 0.0),
                                    "n_claims": g.verification.get("n_claims", 0), "ms": round(g_ms, 1), "error": g.error},
                     "docs": {"pred": sorted(b), **grade(b, truth), "ms": round(b_ms, 1)}})
    agg = {}
    for bucket in ["1-hop", "2-hop", "3+-hop", "all"]:
        sel = [r for r in rows if bucket == "all" or r["bucket"] == bucket]
        if sel:
            n = len(sel)
            agg[bucket] = {"n": n, "graph_exact": round(sum(r["graph"]["exact"] for r in sel) / n, 3),
                           "docs_exact": round(sum(r["docs"]["exact"] for r in sel) / n, 3),
                           "graph_f1": round(sum(r["graph"]["f1"] for r in sel) / n, 3),
                           "docs_f1": round(sum(r["docs"]["f1"] for r in sel) / n, 3),
                           "grounded_pct": round(sum(r["graph"]["grounded_pct"] for r in sel) / n, 1),
                           "graph_p50_ms": round(sorted(r["graph"]["ms"] for r in sel)[n // 2], 1)}
    by_intent: dict[str, dict] = defaultdict(lambda: {"n": 0, "graph": 0, "docs": 0})
    for r in rows:
        d = by_intent[r["intent"]]
        d["n"] += 1
        d["graph"] += r["graph"]["exact"]
        d["docs"] += r["docs"]["exact"]
    res = {"workspace": wid, "label": ws.label, "stats": {k: ws.stats.get(k) for k in ("files", "modules", "module_deps", "commits", "authors")},
           "aggregate": agg, "by_intent": by_intent, "rows": rows}
    (W.workspace_dir(wid) / "eval.json").write_text(json.dumps(res, default=list))
    return res


if __name__ == "__main__":
    import sys
    r = run_repo_eval(sys.argv[1])
    for b, a in r["aggregate"].items():
        print(f"{b:7s} n={a['n']:3d} graph={a['graph_exact']:.0%} docs={a['docs_exact']:.0%} grounded={a['grounded_pct']}%")
