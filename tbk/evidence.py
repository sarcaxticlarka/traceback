"""Evidence bundles: everything needed to re-check claims without trusting our server.

Edge ids only mean something inside one graph, so a bundle describes each fact *structurally*: relationship type, the two
entities by name, why the edge exists (basis, import sites, ownership rule) and when it was valid. Anyone can then re-derive
those facts from the same source (``python -m tbk.cli verify``) and compare.
"""
from __future__ import annotations

import hashlib
import json
import time

from . import workspaces as W
from .provenance import edge_provenance
from .tools.base import ToolContext

FORMAT = "traceback-evidence/1"
MAX_CLAIMS = 60


def _source(tenant: str) -> dict:
    ws = W.by_tenant(tenant)
    if ws is None:
        return {"kind": "synthetic", "tenant": tenant}
    s = ws.stats or {}
    return {"kind": ws.source, "label": ws.label, "url": ws.url, "head_sha": s.get("head_sha", ""), "max_commits": s.get("max_commits"),
            "module_depth": s.get("module_depth"), "has_history": bool(s.get("history"))}


def build_bundle(ctx: ToolContext, tenant: str, claims: list[dict]) -> dict:
    out = []
    for c in claims[:MAX_CLAIMS]:
        facts = []
        for eid in (c.get("edge_ids") or [])[:12]:
            p = edge_provenance(ctx, tenant, eid)
            if p:
                facts.append({"type": p["type"], "from": p["from"], "to": p["to"], "basis": p["basis"], "sites": p["sites"], "rule": p["rule"],
                              "count": p["count"], "lines": p["lines"], "valid_from": p["valid_from"], "valid_to": p["valid_to"]})
        ended = [e for e in (c.get("ended_edge_ids") or [])[:4]]
        out.append({"text": c.get("text", ""), "status": c.get("status", ""), "tool": c.get("tool", ""), "as_of": c.get("as_of"),
                    "facts": facts, "ended_edge_count": len(ended), "asserted_properties": c.get("assert_props") or []})
    body = {"format": FORMAT, "generated": int(time.time()), "source": _source(tenant), "at": ctx.at, "claims": out}
    canon = json.dumps({k: body[k] for k in ("format", "source", "at", "claims")}, sort_keys=True, separators=(",", ":"), default=str)
    body["sha256"] = hashlib.sha256(canon.encode()).hexdigest()
    return body
