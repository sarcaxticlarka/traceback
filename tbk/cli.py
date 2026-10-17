"""Command line: analyse a repo, or comment on the blast radius of a change (for CI / PR bots).

    python -m tbk.cli analyze https://github.com/pallets/click
    python -m tbk.cli analyze ./my-checkout
    python -m tbk.cli impact . --base origin/main --head HEAD      # markdown suitable for a PR comment
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import workspaces as W
from .ingest import fetch
from .ingest.pipeline import ingest_local
from .tools import ToolContext, run_tool
from .verifier import verify_claims


def _ingest(target: str, history: bool = True) -> tuple[W.Workspace, Path | None]:
    if target.startswith("http"):
        owner, repo = fetch.parse_github_url(target)
        tmp = Path(tempfile.mkdtemp(prefix="tbk-"))
        fetch.clone_github(target, tmp / "src")
        return ingest_local(tmp / "src", f"{owner}/{repo}", history), tmp
    p = Path(target).resolve()
    if not p.is_dir():
        sys.exit(f"not a directory: {target}")
    return ingest_local(p, p.name, history), None


def _grounded(ctx: ToolContext, res) -> list[str]:
    v = verify_claims(ctx, res.claims)
    return [c.claim.text for c in v.grounded], v.grounded_pct


def cmd_analyze(a) -> int:
    ws, tmp = _ingest(a.target)
    try:
        s = ws.stats
        print(f"\n{ws.label}: {s['files']} files · {s['modules']} modules · {s['module_deps']} module dependencies "
              f"({s['file_imports']} imports) · {s['commits']} commits · {s['authors']} authors · graph {s['graph_nodes']} nodes / {s['graph_edges']} edges "
              f"· {s['ingest_s']}s")
        ctx = ToolContext(ws.tenant, ws.now)
        for tool, title in [("hotspots", "Hotspots (churn x fan-in)"), ("bus_factor", "Bus factor"), ("criticality", "Most relied-upon (PageRank)")]:
            res = run_tool(ctx, tool, {"top": 5})
            texts, pct = _grounded(ctx, res)
            print(f"\n## {title}" + (f"  [verified {pct:.0f}%]" if texts else "  [none found]"))
            for t in texts:
                print(" -", t)
        if a.keep:
            print(f"\nworkspace kept: tenant {ws.tenant} (id {ws.id})")
        return 0
    finally:
        if not a.keep:
            W.delete(ws.id)
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def cmd_impact(a) -> int:
    repo = Path(a.path).resolve()
    env = {"GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": "/nonexistent"}
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", f"{a.base}...{a.head}"], capture_output=True, text=True, env=env)
    if diff.returncode != 0:
        sys.exit(diff.stderr.strip() or "git diff failed")
    files = [f for f in diff.stdout.split() if f]
    ws, _ = _ingest(str(repo))
    try:
        from .ingest.analyze import module_name
        ctx = ToolContext(ws.tenant, ws.now)
        depth = ws.stats["module_depth"]
        known = {r["name"] for r in ctx.q("MATCH (s:Service) RETURN s.name AS name")}
        touched = sorted({module_name(f, depth) for f in files} & known)
        if not touched:
            print("### TRACEBACK impact\n\nNo analysed source modules were changed.")
            return 0
        res = run_tool(ctx, "change_impact", {"modules": ",".join(touched)})
        row = res.rows[0]
        texts, pct = _grounded(ctx, res)
        print(f"### TRACEBACK impact: risk {row['risk_score']}/100\n")
        print(f"**Touches** {', '.join(f'`{m}`' for m in row['touched'])}  ·  **{row['impacted_count']} modules depend on this** "
              f"· **owners** {', '.join(row['owners']) or 'unknown'}")
        if row["reviewers"]:
            print(f"\n**Suggested reviewers:** {', '.join(row['reviewers'])}")
        for f in row["risk_factors"]:
            print(f"\n- ⚠ {f}")
        print(f"\n<details><summary>Evidence ({len(texts)} verified claims, {pct:.0f}% grounded)</summary>\n")
        for t in texts:
            print(f"- {t}")
        print("\n</details>")
        return 0
    finally:
        W.delete(ws.id)


def cmd_verify(a) -> int:
    """Re-check an evidence bundle from the source, with no server, database or LLM involved."""
    import json
    from .verify_local import rebuild, verify_bundle
    bundle = json.loads(Path(a.bundle).read_text())
    ds, kind, root, notes = rebuild(bundle, a.repo, a.data)
    rep = verify_bundle(bundle, ds, kind, root, a.show_sources)
    c = rep["counts"]
    mark = {"verified": "✓", "mismatch": "✗", "unchecked": "?", "runtime": "~"}
    print(f"\nBundle {str(rep['bundle_sha256'])[:12]} · source: {bundle['source'].get('label') or bundle['source'].get('tenant')} · {len(rep['claims'])} claims\n")
    for r in rep["claims"]:
        print(f" {mark[r['verdict']]} {r['text']}")
        for d in r["details"]:
            print(f"      {d}")
        for line in r.get("sources", []):
            print(f"      source: {line}")
    print(f"\n{c['verified']} verified · {c['mismatch']} mismatched · {c['runtime']} run-time only · {c['unchecked']} unchecked")
    for n in notes:
        print("note:", n)
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1))
    if tmp := getattr(a, "_tmp", None):
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if c["mismatch"] == 0 else 1


def main() -> None:
    ap = argparse.ArgumentParser(prog="tbk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyze", help="ingest a GitHub URL or local folder and print hotspots, bus factor, criticality")
    p.add_argument("target")
    p.add_argument("--keep", action="store_true", help="keep the workspace graph afterwards")
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("impact", help="markdown impact report for the changes between two refs of a local repo")
    p.add_argument("path")
    p.add_argument("--base", default="origin/main")
    p.add_argument("--head", default="HEAD")
    p.set_defaults(fn=cmd_impact)
    p = sub.add_parser("verify", help="re-verify an evidence bundle from the source: no server, database or LLM needed")
    p.add_argument("bundle", help="evidence bundle JSON downloaded from the console")
    p.add_argument("--repo", help="local folder or GitHub URL of the analysed source (defaults to the URL in the bundle)")
    p.add_argument("--data", help="your original JSON catalogue (for bundles built from one)")
    p.add_argument("--show-sources", action="store_true", help="print the raw source line behind each import so you can check by eye")
    p.add_argument("--json", help="write the full verification report here")
    p.set_defaults(fn=cmd_verify)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
