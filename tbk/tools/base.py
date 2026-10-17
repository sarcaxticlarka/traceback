"""Tool framework: every graph tool returns rows *plus* evidence-bearing claims.

A ``Claim`` is the unit the verifier checks. It cites graph edge ids (and optionally node ids /
asserted node properties); its text is generated from those edges by the tool, so an answer can
only contain statements the graph can back.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..graph import GraphStore, get_store
from ..switches import GraphDisabled


@dataclass
class Claim:
    text: str
    edge_ids: list[int] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    ended_edge_ids: list[int] = field(default_factory=list)    # edges that must have *ended* by `as_of`
    assert_props: list[dict] = field(default_factory=list)     # [{node_id, prop, value}]
    as_of: int | None = None
    kind: str = "fact"                                         # fact | inference
    tool: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Claim":
        keys = Claim.__dataclass_fields__.keys()
        return Claim(**{k: v for k, v in d.items() if k in keys})


@dataclass
class ToolContext:
    tenant: str
    at: int                       # "now" for temporal validity (epoch seconds)
    store: GraphStore = field(default_factory=get_store)

    def q(self, cypher: str, params: dict | None = None) -> list[dict]:
        return self.store.query(self.tenant, cypher, params)


@dataclass
class ToolResult:
    tool: str
    args: dict
    rows: list[dict] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    summary: str = ""
    cypher_ref: str = ""
    ms: float = 0.0
    error: str | None = None

    @property
    def edge_ids(self) -> list[int]:
        return sorted({e for c in self.claims for e in c.edge_ids + c.ended_edge_ids})

    @property
    def node_ids(self) -> list[str]:
        return sorted({n for c in self.claims for n in c.node_ids})

    def to_dict(self) -> dict:
        return {"tool": self.tool, "args": self.args, "rows": self.rows[:25], "n_rows": len(self.rows),
                "claims": [c.to_dict() for c in self.claims], "summary": self.summary,
                "cypher_ref": self.cypher_ref, "ms": round(self.ms, 1), "error": self.error,
                "edge_ids": self.edge_ids, "node_ids": self.node_ids}


@dataclass
class ToolSpec:
    name: str
    description: str
    params: dict                      # JSON schema "properties" object
    required: list[str]
    fn: Callable[..., ToolResult]
    cypher_ref: str = ""
    writes: bool = False

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": self.params, "required": self.required}}


REGISTRY: dict[str, ToolSpec] = {}


def tool(name: str, description: str, params: dict, required: list[str] | None = None, *,
         cypher_ref: str = "", writes: bool = False):
    def deco(fn):
        REGISTRY[name] = ToolSpec(name, description, params, required or [], fn, cypher_ref or name, writes)
        return fn
    return deco


def run_tool(ctx: ToolContext, name: str, args: dict | None = None) -> ToolResult:
    args = dict(args or {})
    spec = REGISTRY.get(name)
    if spec is None:
        return ToolResult(name, args, error=f"unknown tool {name}")
    missing = [r for r in spec.required if r not in args]
    if missing:
        return ToolResult(name, args, error=f"missing arguments: {missing}", cypher_ref=spec.cypher_ref)
    t0 = time.perf_counter()
    try:
        res = spec.fn(ctx, **args)
    except GraphDisabled as e:
        res = ToolResult(name, args, error=f"graph disabled: {e}")
    except Exception as e:                      # surface query errors to the agent instead of crashing the run
        res = ToolResult(name, args, error=f"{type(e).__name__}: {e}")
    res.tool, res.args, res.cypher_ref = name, args, spec.cypher_ref
    for c in res.claims:
        c.tool = name
    res.ms = (time.perf_counter() - t0) * 1000
    return res


def tool_schemas(include_writes: bool = False) -> list[dict]:
    return [s.schema() for s in REGISTRY.values() if include_writes or not s.writes]
