"""Proof-carrying answers: "no path, no claim".

A claim is accepted only if, re-checked against the tenant's FalkorDB graph:
  1. it cites evidence (edge ids and/or node ids) and is not tagged ``inference``;
  2. every cited edge exists in this tenant's graph;
  3. every cited edge was valid at the claim's time (``vf <= t < vt``), or - for ``ended_edge_ids`` - had ended;
  4. every cited node exists, and asserted node properties match the stored values;
  5. every entity the text mentions (service, person, team, deploy sha, id) is an endpoint of the cited evidence.
Rule 5 is what stops a language model from smuggling an ungrounded name into an otherwise grounded sentence.
Grounded % = accepted / proposed (rejected and inference claims count against it).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from .tools.base import Claim, ToolContext
from .tools.common import edge_facts, entity_key


@dataclass
class VerifiedClaim:
    claim: Claim
    status: str                    # grounded | withheld
    reason: str = ""
    mentions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.claim.to_dict()
        d.update(status=self.status, reason=self.reason, mentions=self.mentions)
        return d


@dataclass
class Verification:
    claims: list[VerifiedClaim]

    @property
    def grounded(self) -> list[VerifiedClaim]:
        return [c for c in self.claims if c.status == "grounded"]

    @property
    def withheld(self) -> list[VerifiedClaim]:
        return [c for c in self.claims if c.status != "grounded"]

    @property
    def grounded_pct(self) -> float:
        return round(100.0 * len(self.grounded) / len(self.claims), 1) if self.claims else 0.0

    def to_dict(self) -> dict:
        return {"grounded_pct": self.grounded_pct, "n_claims": len(self.claims),
                "claims": [c.to_dict() for c in self.claims]}


def _vocab_rows(ctx: ToolContext) -> list[str]:
    keys: list[str] = []
    for r in ctx.q("MATCH (s:Service) RETURN s.name AS k"):
        keys.append(r["k"])
    for r in ctx.q("MATCH (p:Person) RETURN p.name AS k"):
        keys.append(r["k"])
    for r in ctx.q("MATCH (t:Team) RETURN 'team ' + t.name AS k"):
        keys.append(r["k"])
    for r in ctx.q("MATCH (d:Deploy) RETURN d.sha AS k"):
        keys.append(r["k"])
    return [k for k in keys if k]


_cache: dict[str, re.Pattern] = {}


def vocabulary(ctx: ToolContext) -> re.Pattern:
    """Per-tenant regex over every known entity token, longest first; hyphen/colon adjacency blocks partial hits."""
    pat = _cache.get(ctx.tenant)
    if pat is None:
        keys = sorted(set(_vocab_rows(ctx)), key=len, reverse=True)
        pat = re.compile(r"(?<![\w:\-])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w:\-])")
        _cache[ctx.tenant] = pat
    return pat


def clear_vocabulary_cache(tenant: str | None = None) -> None:
    if tenant:
        _cache.pop(tenant, None)
    else:
        _cache.clear()


_ID_TOKEN = re.compile(r"\b(?:inc|alert|dec|fact|rb|ticket|doc|dep):[\w\-]+")


def find_mentions(ctx: ToolContext, text: str) -> list[str]:
    found = [m.group(1) for m in vocabulary(ctx).finditer(text)]
    found += _ID_TOKEN.findall(text)
    return sorted(set(found))


def _close(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(b)))
    return a == b


def verify_claims(ctx: ToolContext, claims: list[Claim]) -> Verification:
    all_edges = sorted({e for c in claims for e in c.edge_ids + c.ended_edge_ids})
    all_nodes = sorted({n for c in claims for n in c.node_ids} | {a["node_id"] for c in claims for a in c.assert_props})
    facts = edge_facts(ctx, all_edges)
    nodes: dict[str, dict] = {}
    if all_nodes:
        for r in ctx.q("MATCH (n) WHERE n.id IN $ids RETURN n.id AS id, labels(n)[0] AS l, n.name AS name, "
                       "n.sha AS sha, properties(n) AS props", {"ids": all_nodes}):
            nodes[r["id"]] = r
    out: list[VerifiedClaim] = []
    for c in claims:
        out.append(_verify_one(ctx, c, facts, nodes))
    return Verification(out)


def _verify_one(ctx: ToolContext, c: Claim, facts: dict, nodes: dict) -> VerifiedClaim:
    def reject(reason: str, mentions=()) -> VerifiedClaim:
        return VerifiedClaim(c, "withheld", reason, list(mentions))

    if c.kind == "inference":
        return reject("inference: not backed by graph evidence")
    if not (c.edge_ids or c.node_ids or c.ended_edge_ids):
        return reject("no supporting path")
    t = c.as_of or ctx.at
    allowed: set[str] = set()
    for eid in c.edge_ids:
        f = facts.get(eid)
        if f is None:
            return reject(f"edge {eid} not found in tenant graph")
        if f["vf"] is not None and not (f["vf"] <= t < f["vt"]):
            return reject(f"edge {eid} ({f['type']}) not valid at claim time")
        allowed |= {f["a_key"], f["b_key"]}
    for eid in c.ended_edge_ids:
        f = facts.get(eid)
        if f is None:
            return reject(f"edge {eid} not found in tenant graph")
        if f["vt"] is None or f["vt"] > t:
            return reject(f"edge {eid} ({f['type']}) has not ended")
        allowed |= {f["a_key"], f["b_key"]}
    for nid in c.node_ids:
        n = nodes.get(nid)
        if n is None:
            return reject(f"node {nid} not found in tenant graph")
        allowed |= {nid, entity_key(n["l"], nid, n["name"], n["sha"])}
    for a in c.assert_props:
        n = nodes.get(a["node_id"])
        if n is None:
            return reject(f"node {a['node_id']} not found in tenant graph")
        if not _close(n["props"].get(a["prop"]), a["value"]):
            return reject(f"property {a['prop']} of {a['node_id']} is {n['props'].get(a['prop'])!r}, claim says {a['value']!r}")
    mentions = find_mentions(ctx, c.text)
    extra = [m for m in mentions if m not in allowed]
    if extra:
        return reject(f"mentions {extra} which the cited evidence does not contain", mentions)
    return VerifiedClaim(c, "grounded", "", mentions)
