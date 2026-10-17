"""Outcome simulator for the demo. Real incidents would report outcomes from monitoring; here the success of a
runbook is sampled from hidden per-runbook rates that exist only in the generator (never in the graph), so the
Remediator has something genuine to learn from. Everything it writes to the graph is a normal outcome record.
"""
from __future__ import annotations

import hashlib
import json
import random

from . import memory
from .config import DATA_DIR
from .seed.generate import get_dataset
from .tools import ToolContext, run_tool
from .tools.runbooks import record_outcome


def sample_outcome(tenant: str, runbook_id: str, key: str) -> bool:
    p = get_dataset(tenant).meta["runbook_truth"][runbook_id]
    seed = int.from_bytes(hashlib.blake2b(f"{tenant}|{runbook_id}|{key}".encode(), digest_size=8).digest(), "big")
    return random.Random(seed).random() < p


def reset_runbook_stats(ctx: ToolContext) -> None:
    ctx.q("MATCH (rb:Runbook) SET rb.attempts = 0, rb.successes = 0, rb.last_used = 0")


def _one_run(ctx: ToolContext, truth: dict, best: dict, signals: list[str], n: int, epsilon: float, seed: int):
    reset_runbook_stats(ctx)
    rng = random.Random(seed)
    outcomes, picked_best = [], []
    for i in range(n):
        sg = rng.choice(signals)
        ranked = run_tool(ctx, "rank_runbooks", {"signal": sg}).rows
        if not ranked:
            continue
        top_rate = ranked[0]["success_rate"]
        tied = [r for r in ranked if r["success_rate"] == top_rate]
        choice = rng.choice(tied)                                   # break ties randomly: no hidden alphabetical edge
        if rng.random() < epsilon and len(ranked) > 1:
            choice = rng.choice([r for r in ranked if r is not choice])
        ok = sample_outcome(ctx.tenant, choice["runbook"], f"curve{seed}-{i}")
        record_outcome(ctx, choice["runbook"], ok)
        outcomes.append(1 if ok else 0)
        picked_best.append(1 if choice["runbook"] == best[sg] else 0)
    return outcomes, picked_best


def learning_curve(ctx: ToolContext, n: int = 240, epsilon: float = 0.1, window: int = 20, seeds: int = 5) -> dict:
    """Cold-start procedural memory and let the Remediator's ranking learn from simulated outcomes.

    Averaged over ``seeds`` independent cold starts; the policy is: pick the top-ranked runbook (ties random),
    explore a different one with probability ``epsilon``. Ranking itself is the pure ``rank_runbooks`` tool.
    """
    memory.ensure_agents(ctx)
    tenant = ctx.tenant
    truth = get_dataset(tenant).meta["runbook_truth"]
    signals = sorted({rid.split(":", 1)[1].rsplit("-", 3)[0] for rid in truth})   # rb:<signal>-<variant 3 words>
    best = {sg: max((r for r in truth if r.startswith(f"rb:{sg}-")), key=lambda r: truth[r]) for sg in signals}
    runs = [_one_run(ctx, truth, best, signals, n, epsilon, 5 + k) for k in range(seeds)]
    step = max(1, window // 2)
    curve = []
    for end in range(window, n + 1, step):
        w = slice(end - window, end)
        curve.append({"incidents": end,
                      "success_rate": round(sum(sum(o[w]) for o, _ in runs) / (window * seeds), 3),
                      "picked_best": round(sum(sum(p[w]) for _, p in runs) / (window * seeds), 3)})
    out = {"tenant": tenant, "n": n, "epsilon": epsilon, "window": window, "seeds": seeds, "curve": curve,
           "expected_success_best": round(sum(truth[b] for b in best.values()) / len(best), 3),
           "expected_success_random": round(sum(sum(truth[r] for r in truth if r.startswith(f"rb:{sg}-")) / 2
                                                for sg in signals) / len(signals), 3),
           "final_stats": [dict(r, signal=sg) for sg in signals for r in run_tool(ctx, "rank_runbooks", {"signal": sg}).rows]}
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / f"learning_{tenant}.json").write_text(json.dumps(out, indent=1))
    return out
