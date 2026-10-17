"""Talk to the MCP server over stdio like a real client would."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


async def _session_calls():
    params = StdioServerParameters(command=sys.executable, args=["-m", "tbk.mcp_server"], cwd=str(ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name: t for t in (await s.list_tools()).tools}
            res = await s.call_tool("owners_of", {"service": "payments-api", "tenant": "orbit"})
            ask = await s.call_tool("ask", {"question": "Which team owns payments-api today?", "tenant": "helix"})
            return tools, res, ask


def test_mcp_lists_tools_and_returns_verified_claims():
    tools, res, ask = asyncio.run(_session_calls())
    assert {"blast_radius", "recent_changes", "owners_of", "rank_runbooks", "ask", "investigate_alert"} <= set(tools)
    assert "tenant" in tools["blast_radius"].input_schema["properties"]
    payload = json.loads(res.content[0].text)
    assert payload["verification"]["grounded_pct"] == 100.0 and payload["claims"]
    answer = json.loads(ask.content[0].text)
    assert answer["answers"] and answer["verification"]["grounded_pct"] == 100.0
