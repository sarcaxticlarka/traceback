"""MCP server exposing the graph tools (and the crew) to any MCP client (Claude Desktop, Cursor, custom agents).

Run:  ``python -m tbk.mcp_server``            (stdio)
      ``python -m tbk.mcp_server --http 8770`` (streamable HTTP)
Every registry tool becomes an MCP tool with the same JSON schema plus a ``tenant`` argument, and every response
carries verified claims (edge ids + grounded %), so MCP clients also get "no path, no claim".
"""
from __future__ import annotations

import argparse
import inspect
import json
from inspect import Parameter, Signature

from mcp.server.mcpserver import MCPServer

from .agents.orchestrator import run_incident
from .agents.qa import answer_question
from .config import NOW, get_settings
from .tools import REGISTRY, ToolContext, run_tool
from .tools.base import ToolSpec
from .verifier import verify_claims

_TYPES = {"string": str, "integer": int, "number": float, "boolean": bool}


def _wrap(spec: ToolSpec):
    tenants = get_settings().tenants

    def fn(**kw):
        tenant = kw.pop("tenant", tenants[0])
        at = kw.pop("at", None) or NOW
        args = {k: v for k, v in kw.items() if v is not None}
        ctx = ToolContext(tenant, int(at))
        res = run_tool(ctx, spec.name, args)
        ver = verify_claims(ctx, res.claims) if res.claims and not res.error else None
        out = res.to_dict()
        out["verification"] = ver.to_dict() if ver else None
        return json.dumps(out, default=str)

    params = []
    for name in spec.required:
        params.append(Parameter(name, Parameter.KEYWORD_ONLY, annotation=_TYPES.get(spec.params[name].get("type"), str)))
    params.append(Parameter("tenant", Parameter.KEYWORD_ONLY, default=tenants[0], annotation=str))
    for name, p in spec.params.items():
        if name in spec.required:
            continue
        ann = _TYPES.get(p.get("type"), str)
        params.append(Parameter(name, Parameter.KEYWORD_ONLY, default=p.get("default"), annotation=ann | None))
    params.append(Parameter("at", Parameter.KEYWORD_ONLY, default=None, annotation=int | None))
    fn.__signature__ = Signature(params)
    fn.__annotations__ = {p.name: p.annotation for p in params} | {"return": str}
    fn.__name__ = spec.name
    return fn


def build_server() -> MCPServer:
    server = MCPServer("traceback", instructions=(
        "Graph-backed incident-response tools over a FalkorDB company graph. Every result includes claims with "
        "edge ids and a verification block; trust only claims with status 'grounded'."))
    for spec in REGISTRY.values():
        if spec.writes:
            continue
        server.add_tool(_wrap(spec), name=spec.name, description=f"{spec.description} [{spec.cypher_ref}]")

    def ask(question: str, tenant: str = get_settings().tenants[0]) -> str:
        """Answer a company question from the graph with verified, sourced claims."""
        return json.dumps(answer_question(tenant, question).to_dict(), default=str)

    def investigate_alert(alert_id: str, tenant: str = get_settings().tenants[0]) -> str:
        """Run the Triage → Investigator → Remediator crew on an alert; returns the full run report."""
        return json.dumps(run_incident(tenant, alert_id).to_dict(), default=str)

    server.add_tool(ask, name="ask", description="Natural-language question answered from the company graph (verified).")
    server.add_tool(investigate_alert, name="investigate_alert",
                    description="Run the multi-agent incident crew on an alert id such as alert:LIVE-1.")
    return server


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", type=int, default=0, help="serve streamable HTTP on this port instead of stdio")
    a = ap.parse_args()
    server = build_server()
    if a.http:
        server.settings.port = a.http  # type: ignore[attr-defined]
        server.run("streamable-http")
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
