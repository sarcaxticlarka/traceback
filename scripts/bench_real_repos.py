"""Ingest real public repositories and benchmark the graph agent vs a docs-only baseline on each.

    python scripts/bench_real_repos.py [owner/repo ...]     ->  docs/BENCH_REAL.md  +  data/bench_real.json

Every number comes from a fresh clone: re-run it to reproduce. Ground truth never touches FalkorDB.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tbk import workspaces as W                      # noqa: E402
from tbk.config import DATA_DIR                      # noqa: E402
from tbk.evalx.repo_eval import run_repo_eval        # noqa: E402
from tbk.ingest.pipeline import start_github         # noqa: E402

DEFAULT = ["pallets/click", "psf/requests", "expressjs/express", "spf13/cobra", "gin-gonic/gin", "tiangolo/fastapi"]


def ingest(slug: str) -> W.Workspace:
    ws = start_github(f"https://github.com/{slug}")
    t0 = time.time()
    while True:
        w = W.get(ws.id)
        if w.status in ("ready", "error"):
            return w
        if time.time() - t0 > 400:
            raise TimeoutError(slug)
        time.sleep(1)


def main(repos: list[str]) -> None:
    results = []
    for slug in repos:
        t0 = time.time()
        w = ingest(slug)
        if w.status != "ready":
            print(f"[{slug}] FAILED: {w.error}")
            results.append({"repo": slug, "error": w.error})
            continue
        r = run_repo_eval(w.id)
        a = r["aggregate"]
        results.append({"repo": slug, "stats": w.stats, "aggregate": a, "by_intent": r["by_intent"], "wall_s": round(time.time() - t0, 1)})
        print(f"[{slug}] {w.stats['files']} files, {w.stats['modules']} modules, {w.stats['module_deps']} deps, {w.stats['commits']} commits | "
              f"graph {a['all']['graph_exact']:.0%} vs docs {a['all']['docs_exact']:.0%} on {a['all']['n']} q | ingest {w.stats['ingest_s']}s")
        W.delete(w.id)
    DATA_DIR.mkdir(exist_ok=True)
    slim = [{k: v for k, v in r.items() if k != "rows"} for r in results]
    (DATA_DIR / "bench_real.json").write_text(json.dumps(slim, indent=1, default=list))
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "bench_real.json").write_text(json.dumps(slim, indent=1, default=list))
    md = ["# Benchmark on real repositories", "",
          "Each repo is cloned fresh (shallow), analysed, loaded into its own FalkorDB graph, and asked auto-generated questions whose "
          "ground truth comes from the static analyser's module model and the raw commit list (never from FalkorDB). The baseline retrieves "
          "8 file chunks (hybrid dense+TF-IDF) and parses the imports in them.", "",
          "| Repository | Files | Modules | Module deps | Commits | Questions | Graph exact | Docs-only exact | Grounded | Ingest |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    tot_q = tot_g = tot_d = 0
    for r in results:
        if "error" in r:
            md.append(f"| {r['repo']} | failed: {r['error']} | | | | | | | | |")
            continue
        s, a = r["stats"], r["aggregate"]["all"]
        tot_q += a["n"]
        tot_g += a["graph_exact"] * a["n"]
        tot_d += a["docs_exact"] * a["n"]
        md.append(f"| [{r['repo']}](https://github.com/{r['repo']}) | {s['files']} | {s['modules']} | {s['module_deps']} | {s['commits']} | "
                  f"{a['n']} | {a['graph_exact']:.0%} | {a['docs_exact']:.0%} | {a['grounded_pct']:.0f}% | {s['ingest_s']} s |")
    if tot_q:
        md.append(f"| **All** | | | | | **{tot_q}** | **{tot_g / tot_q:.0%}** | **{tot_d / tot_q:.0%}** | | |")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "BENCH_REAL.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT)
