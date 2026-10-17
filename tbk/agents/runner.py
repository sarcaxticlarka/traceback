"""The shared tool loop: planner picks a step, the registry runs it, memory records it."""
from __future__ import annotations

from .. import memory
from ..llm import Planner
from ..tools import ToolContext, ToolResult, run_tool
from .types import StepRecord


def run_tool_loop(ctx: ToolContext, planner: Planner, agent: str, episode_id: str | None, max_steps: int = 14,
                  history: list[ToolResult] | None = None, start: int = 0) -> tuple[list[ToolResult], list[StepRecord]]:
    """``history``/``start`` let a fallback planner continue where a failed one stopped (indices keep counting up)."""
    results: list[ToolResult] = list(history or [])
    records: list[StepRecord] = []
    for i in range(start, start + max_steps):
        step = planner.next(results)
        if step is None:
            break
        res = run_tool(ctx, step.tool, step.args)
        results.append(res)
        if episode_id:
            memory.log_tool_call(ctx, episode_id, i, res)
        records.append(StepRecord(agent=agent, idx=i, tool=step.tool, args=step.args, why=step.why, summary=res.summary,
                                  n_claims=len(res.claims), edge_ids=res.edge_ids, node_ids=res.node_ids,
                                  ms=round(res.ms, 1), cypher_ref=res.cypher_ref, error=res.error))
    return results, records
