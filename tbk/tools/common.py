"""Shared helpers: entity display names, edge fact fetching, timestamp formatting."""
from __future__ import annotations

import time
from typing import Any

from .base import ToolContext

NODE_FIELDS = "labels({v})[0] AS {p}l, {v}.id AS {p}id, {v}.name AS {p}name, {v}.sha AS {p}sha"


def fmt_ts(ts: int | float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(ts)) if ts else "n/a"


def fmt_day(ts: int | float | None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else "n/a"


def entity_key(label: str | None, nid: str | None, name: str | None, sha: str | None) -> str:
    """The token that represents an entity in claim text (and in the verifier's vocabulary)."""
    if label == "Service" or label == "Person":
        return name or (nid or "")
    if label == "Team":
        return f"team {name}"
    if label == "Deploy":
        return sha or (nid or "")
    return nid or ""


def display(label: str | None, nid: str | None, name: str | None, sha: str | None) -> str:
    if label == "Deploy":
        return f"deploy {sha}"
    return entity_key(label, nid, name, sha)


def edge_facts(ctx: ToolContext, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    rows = ctx.q(
        "MATCH (a)-[r]->(b) WHERE ID(r) IN $ids RETURN ID(r) AS id, type(r) AS type, "
        "labels(a)[0] AS al, a.id AS aid, a.name AS aname, a.sha AS asha, "
        "labels(b)[0] AS bl, b.id AS bid, b.name AS bname, b.sha AS bsha, "
        "r.vf AS vf, r.vt AS vt, r.result AS result", {"ids": list(ids)})
    out = {}
    for r in rows:
        r["a_key"] = entity_key(r["al"], r["aid"], r["aname"], r["asha"])
        r["b_key"] = entity_key(r["bl"], r["bid"], r["bname"], r["bsha"])
        out[r["id"]] = r
    return out


def valid_clause(rel: str = "r", at: str = "$at") -> str:
    return f"{rel}.vf <= {at} AND {rel}.vt > {at}"


def clamp_depth(depth: Any, default: int = 3, hi: int = 6) -> int:
    try:
        return max(1, min(int(depth), hi))
    except (TypeError, ValueError):
        return default
