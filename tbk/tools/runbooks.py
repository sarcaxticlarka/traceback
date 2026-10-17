"""Procedural memory: rank runbooks by smoothed historical success, and write outcomes back."""
from __future__ import annotations

from .base import Claim, ToolContext, ToolResult, tool
from .topology import sid


def success_rate(attempts: int, successes: int) -> float:
    """Laplace-smoothed success rate: (s+1)/(a+2). Unseen runbooks start at 0.5."""
    return (successes + 1.0) / (attempts + 2.0)


@tool("rank_runbooks",
      "Runbooks for an alert signal, ranked by learned success rate (procedural memory); runbooks recorded as fixing the "
      "specific service rank first.",
      {"signal": {"type": "string"}, "service": {"type": "string"}}, ["signal"], cypher_ref="Q5 rank_runbooks")
def rank_runbooks(ctx: ToolContext, signal: str, service: str = "") -> ToolResult:
    rows = ctx.q(
        "MATCH (rb:Runbook)-[fs:FOR_SIGNAL]->(sg:Signal {id:$sg}) "
        "OPTIONAL MATCH (i:Incident)-[:FIXED_WITH {result:'success'}]->(rb), (i)-[:AFFECTED]->(s:Service {id:$sid}) "
        "RETURN rb.id AS id, rb.title AS title, rb.attempts AS attempts, rb.successes AS successes, "
        "ID(fs) AS fs, count(DISTINCT i) AS local_wins",
        {"sg": f"signal:{signal}", "sid": sid(service) if service else ""})
    ranked = sorted(rows, key=lambda r: (-(r["local_wins"] > 0), -success_rate(r["attempts"], r["successes"]), r["id"]))
    claims, out = [], []
    for r in ranked:
        rate = success_rate(r["attempts"], r["successes"])
        claims.append(Claim(f"{r['title']} is a runbook for signal {signal}", edge_ids=[r["fs"]], node_ids=[r["id"]]))
        # counters only ever grow, so the claim is monotone ("at least") and stays true under concurrent writers
        claims.append(Claim(f"{r['title']} has at least {r['attempts']} recorded attempts and {r['successes']} successes",
                            node_ids=[r["id"]],
                            assert_props=[{"node_id": r["id"], "prop": "attempts", "value": r["attempts"], "op": "ge"},
                                          {"node_id": r["id"], "prop": "successes", "value": r["successes"], "op": "ge"}]))
        out.append({"runbook": r["id"], "title": r["title"], "attempts": r["attempts"], "successes": r["successes"],
                    "success_rate": round(rate, 3), "local_wins": r["local_wins"]})
    best = out[0]["title"] if out else None
    return ToolResult("rank_runbooks", {}, out, claims, summary=f"best runbook: {best}")


def record_outcome(ctx: ToolContext, runbook_id: str, ok: bool, episode_id: str | None = None) -> dict:
    """Write an outcome back into the graph (procedural learning). Called by the Remediator, not exposed to the LLM."""
    rows = ctx.q(
        "MATCH (rb:Runbook {id:$id}) SET rb.attempts = rb.attempts + 1, rb.successes = rb.successes + $ok, "
        "rb.last_used = $now RETURN rb.attempts AS attempts, rb.successes AS successes",
        {"id": runbook_id, "ok": 1 if ok else 0, "now": ctx.at})
    if episode_id:
        ctx.q("MATCH (e:Episode {id:$e}), (rb:Runbook {id:$r}) "
              "CREATE (e)-[:OUTCOME {result:$res, ts:$now}]->(rb)",
              {"e": episode_id, "r": runbook_id, "res": "success" if ok else "fail", "now": ctx.at})
    return rows[0] if rows else {}
