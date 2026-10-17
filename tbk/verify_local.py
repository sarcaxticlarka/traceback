"""Re-verify an evidence bundle on your own machine: no TRACEBACK server, no FalkorDB, no LLM.

The source (the repository at the analysed commit, the generated demo company, or your own JSON bundle) is re-analysed in
memory with the same deterministic ingestion code, and every fact in the bundle is looked up in the result: same relationship,
same two entities, same basis, same import sites / ownership rule / counts. What this proves: the claims are reproducible from
the source *by code you can read and run yourself*. What it does not: that the analyser has no bug, which is why
``--show-sources`` prints the raw source line behind every import so a human can check a sample by eye.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

from .evidence import FORMAT
from .ingest import fetch
from .ingest.analyze import analyze
from .ingest.build import build_dataset
from .ingest.bundle import build_bundle as build_catalog
from .ingest.history import head_sha, read_history
from .seed.generate import Dataset, generate

RUNTIME = re.compile(r"^(ep|task|act|finding|tc|fact):|~")          # created by agent runs, not part of the source


def _name(row: dict) -> str:
    return str(row.get("name") or row.get("sha") or row["id"])


def index(ds: Dataset) -> tuple[dict, dict]:
    disp = {r["id"]: (label, _name(r)) for label, rows in ds.nodes.items() for r in rows}
    edges: dict[tuple, dict] = {}
    for e in ds.edges:
        a, b = disp.get(e.src_id), disp.get(e.dst_id)
        if a and b:
            edges.setdefault((e.type, a[0], a[1], b[0], b[1]), e.props)
    return disp, edges


def _eq(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(b)))
    return a == b


def _fact_check(f: dict, edges: dict, synthetic: bool) -> tuple[str, str]:
    a, b = f["from"], f["to"]
    if RUNTIME.search(str(a["name"])) or RUNTIME.search(str(b["name"])):
        return "runtime", "created while the agents ran, not derivable from the source"
    props = edges.get((f["type"], a["label"], a["name"], b["label"], b["name"]))
    if props is None:
        return "mismatch", f"no {f['type']} between {a['name']} and {b['name']} in the re-derived graph"
    basis = props.get("basis") or ("synthetic" if synthetic else "derived")
    if f.get("basis") and basis != f["basis"]:
        return "mismatch", f"basis differs: bundle says {f['basis']}, re-derived {basis}"
    if f.get("sites") is not None:
        mine = json.loads(props["sites"]) if isinstance(props.get("sites"), str) and props["sites"].startswith("[") else None
        if mine is not None and sorted(mine) != sorted(f["sites"]):
            return "mismatch", "import sites differ"
    for k, pk in (("count", "count"), ("lines", "lines"), ("valid_from", "vf"), ("valid_to", "vt")):
        if f.get(k) is not None and props.get(pk) is not None and not _eq(props[pk], f[k]):
            return "mismatch", f"{k} differs: bundle {f[k]}, re-derived {props[pk]}"
    if f.get("rule") and props.get("rule") != f["rule"]:
        return "mismatch", "ownership rule differs"
    return "verified", ""


def _prop_check(p: dict, ds: Dataset) -> tuple[str, str]:
    node = next((r for rows in ds.nodes.values() for r in rows if r["id"] == p["node_id"]), None)
    if node is None:
        return ("runtime", "node created while the agents ran") if RUNTIME.search(p["node_id"]) else ("mismatch", f"{p['node_id']} not found")
    cur = node.get(p["prop"])
    if cur is None:
        return "runtime", f"{p['prop']} is computed at run time (e.g. PageRank)"
    ok = (isinstance(cur, (int, float)) and cur >= p["value"]) if p.get("op") == "ge" else _eq(cur, p["value"])
    return ("verified", "") if ok else ("mismatch", f"{p['prop']} of {p['node_id']} is {cur!r}, bundle says {p['value']!r}")


def verify_bundle(bundle: dict, ds: Dataset, source_kind: str, root: Path | None = None, show_sources: bool = False) -> dict:
    if bundle.get("format") != FORMAT:
        raise ValueError(f"unsupported bundle format {bundle.get('format')!r} (expected {FORMAT})")
    _, edges = index(ds)
    synthetic = source_kind == "synthetic"
    results, counts = [], {"verified": 0, "mismatch": 0, "unchecked": 0, "runtime": 0}
    for c in bundle["claims"]:
        parts, details = [], []
        for f in c.get("facts", []):
            v, why = _fact_check(f, edges, synthetic)
            parts.append(v)
            if v != "verified":
                details.append(f"{f['from']['name']} -{f['type']}-> {f['to']['name']}: {why}")
        for p in c.get("asserted_properties", []):
            v, why = _prop_check(p, ds)
            parts.append(v)
            if v != "verified":
                details.append(why)
        if not parts:
            verdict = "unchecked"
        elif "mismatch" in parts:
            verdict = "mismatch"
        elif all(p == "verified" for p in parts):
            verdict = "verified"
        elif "verified" in parts:
            verdict = "verified"                                      # verified part + only run-time-created parts
        else:
            verdict = "runtime"
        counts[verdict] += 1
        row = {"text": c["text"], "verdict": verdict, "details": details}
        if show_sources and root is not None:
            row["sources"] = _source_lines(root, c.get("facts", []))
        results.append(row)
    return {"source": bundle.get("source"), "bundle_sha256": bundle.get("sha256"), "counts": counts, "claims": results}


def _source_lines(root: Path, facts: list[dict]) -> list[str]:
    out = []
    for f in facts:
        for site in (f.get("sites") or [])[:3]:
            m = re.match(r"(.+?):(\d+) → (.+)", site)
            if not m:
                continue
            try:
                line = (root / m.group(1)).read_text("utf-8", "ignore").splitlines()[int(m.group(2)) - 1].strip()
            except (OSError, IndexError):
                line = "(file or line not found)"
            out.append(f"{m.group(1)}:{m.group(2)}  {line}")
    return out


# ------------------------------------------------------------------------------------------ rebuilding the source
def rebuild(bundle: dict, repo: str | None = None, data: str | None = None, log=print) -> tuple[Dataset, str, Path | None, list[str]]:
    """Return (dataset, source_kind, repo_root, notes) re-derived from the source named in the bundle."""
    src, notes, tmp = bundle["source"], [], None
    kind = src.get("kind")
    if kind == "synthetic":
        log(f"Regenerating the deterministic demo company '{src['tenant']}' …")
        return generate(src["tenant"]), "synthetic", None, notes
    if kind == "bundle":
        if not data:
            raise ValueError("This bundle came from an uploaded JSON catalogue: pass it with --data catalogue.json")
        return build_catalog("verify", json.loads(Path(data).read_text()))[0], "bundle", None, notes
    target = repo or src.get("url")
    if not target:
        raise ValueError("Pass --repo PATH (the same folder you analysed) or --repo URL")
    if str(target).startswith("http"):
        tmp = Path(tempfile.mkdtemp(prefix="tbk-verify-"))
        log(f"Cloning {target} (read-only) …")
        fetch.clone_github(target, tmp / "src", depth=int(src.get("max_commits") or 1500))
        root = tmp / "src"
        if src.get("head_sha"):
            if fetch.checkout_sha(root, src["head_sha"], int(src.get("max_commits") or 1500)):
                log(f"Pinned to the analysed commit {src['head_sha'][:10]}")
            else:
                notes.append("Could not check out the analysed commit; results may differ if the repository changed.")
    else:
        root = Path(target).resolve()
        if not root.is_dir():
            raise ValueError(f"not a directory: {target}")
        if src.get("head_sha"):
            here = head_sha(root)
            if here and here != src["head_sha"]:
                notes.append(f"Your checkout is at {here[:10]} but the analysis was of {src['head_sha'][:10]}; mismatches may reflect newer changes.")
    log("Re-analysing source and history …")
    model = analyze(root)
    commits = read_history(root, int(src.get("max_commits") or 1500)) if src.get("has_history") else []
    ds, _ = build_dataset("verify", src.get("label", "repo"), model, commits, "")
    return ds, kind, root, notes
