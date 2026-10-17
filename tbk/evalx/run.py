"""Run the A/B evaluation: graph agent vs docs-only baseline, bucketed by hop depth.

``python -m tbk.evalx.run`` writes ``data/eval_results.json`` and ``docs/EVAL.md``.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict

from ..agents.qa import answer_question
from ..config import DATA_DIR, ROOT, get_settings
from .baseline_reader import read_answer
from .questions import Question, build_questions

BUCKETS = ["1-hop", "2-hop", "temporal", "3+-hop"]


def f1(pred: set[str], truth: set[str]) -> float:
    if not pred and not truth:
        return 1.0
    if not pred or not truth:
        return 0.0
    tp = len(pred & truth)
    if tp == 0:
        return 0.0
    p, r = tp / len(pred), tp / len(truth)
    return 2 * p * r / (p + r)


def grade(pred: set[str], truth: set[str]) -> dict:
    return {"exact": pred == truth, "f1": round(f1(pred, truth), 3)}


def at_for(q: Question):
    from ..config import NOW
    return NOW


def evaluate(tenants: list[str] | None = None) -> dict:
    tenants = tenants or get_settings().tenants
    rows = []
    for tenant in tenants:
        for q in build_questions(tenant):
            t0 = time.perf_counter()
            g = answer_question(tenant, q.text)
            g_ms = (time.perf_counter() - t0) * 1000
            t0 = time.perf_counter()
            b_pred = read_answer(tenant, q.text)
            b_ms = (time.perf_counter() - t0) * 1000
            rows.append({"id": q.id, "tenant": tenant, "intent": q.intent, "bucket": q.bucket, "question": q.text,
                         "truth": sorted(q.truth), "graph": {"pred": sorted(g.answers), **grade(g.answers, q.truth),
                                                             "grounded_pct": g.verification.get("grounded_pct", 0.0),
                                                             "n_claims": g.verification.get("n_claims", 0),
                                                             "ms": round(g_ms, 1), "error": g.error},
                         "docs": {"pred": sorted(b_pred), **grade(b_pred, q.truth), "ms": round(b_ms, 1)}})
    agg: dict[str, dict] = {}
    for bucket in BUCKETS + ["all"]:
        sel = [r for r in rows if bucket == "all" or r["bucket"] == bucket]
        if not sel:
            continue
        n = len(sel)
        agg[bucket] = {
            "n": n,
            "graph_exact": round(sum(r["graph"]["exact"] for r in sel) / n, 3),
            "docs_exact": round(sum(r["docs"]["exact"] for r in sel) / n, 3),
            "graph_f1": round(sum(r["graph"]["f1"] for r in sel) / n, 3),
            "docs_f1": round(sum(r["docs"]["f1"] for r in sel) / n, 3),
            "graph_grounded_pct": round(sum(r["graph"]["grounded_pct"] for r in sel) / n, 1),
        }
    by_intent: dict[str, dict] = defaultdict(lambda: {"n": 0, "graph": 0, "docs": 0})
    for r in rows:
        d = by_intent[r["intent"]]
        d["n"] += 1
        d["graph"] += r["graph"]["exact"]
        d["docs"] += r["docs"]["exact"]
    out = {"tenants": tenants, "aggregate": agg, "by_intent": by_intent, "rows": rows}
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "eval_results.json").write_text(json.dumps(out, indent=1, default=list))
    write_markdown(out)
    return out


def write_markdown(res: dict) -> None:
    lines = ["# Evaluation: graph agent vs docs-only baseline", "",
             f"Tenants: {', '.join(res['tenants'])}. Same questions, same documents, same embedder. "
             "Ground truth is computed from the generator's model, not from FalkorDB.", "",
             "| Bucket | n | Graph exact | Docs-only exact | Graph F1 | Docs-only F1 | Graph grounded % |", "|---|---|---|---|---|---|---|"]
    for b, a in res["aggregate"].items():
        lines.append(f"| {b} | {a['n']} | {a['graph_exact']:.0%} | {a['docs_exact']:.0%} | {a['graph_f1']:.2f} | "
                     f"{a['docs_f1']:.2f} | {a['graph_grounded_pct']} |")
    lines += ["", "## By question type (exact match, correct / total)", "", "| Intent | Graph | Docs-only |", "|---|---|---|"]
    for k, v in sorted(res["by_intent"].items()):
        lines.append(f"| {k} | {v['graph']}/{v['n']} | {v['docs']}/{v['n']} |")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "EVAL.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    r = evaluate()
    for b, a in r["aggregate"].items():
        print(f"{b:9s} n={a['n']:3d} graph={a['graph_exact']:.0%} docs={a['docs_exact']:.0%} "
              f"(F1 {a['graph_f1']:.2f} vs {a['docs_f1']:.2f}) grounded={a['graph_grounded_pct']}%")
