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


def learning_curve(ctx: ToolContext, n: int = 120, epsilon: float = 0.15, window: int = 20, seed: int = 5) -> dict:
    """Cold-start the procedural memory and let the Remediator's ranking learn from simulated outcomes."""
    memory.ensure_agents(ctx)
    tenant = ctx.tenant
    truth = get_dataset(tenant).meta["runbook_truth"]
    signals = sorted({rid.split(":", 1)[1].rsplit("-", 2)[0] for rid in truth})
    best = {}
    for sg in signals:
        rbs = [r for r in truth if r.startswith(f"rb:{sg}-")]
        best[sg] = max(rbs, key=lambda r: truth[r])
    reset_runbook_stats(ctx)
    rng = random.Random(seed)
    ep_outcomes, picked_best = [], []
    for i in range(n):
        sg = rng.choice(signals)
        ranked = run_tool(ctx, "rank_runbooks", {"signal": sg}).rows
        if not ranked:
            continue
        choice = ranked[0] if rng.random() > epsilon or len(ranked) == 1 else rng.choice(ranked[1:])
        ok = sample_outcome(tenant, choice["runbook"], f"curve{seed}-{i}")
        record_outcome(ctx, choice["runbook"], ok)
        ep_outcomes.append(1 if ok else 0)
        picked_best.append(1 if choice["runbook"] == best[sg] else 0)
    curve = []
    for end in range(window, len(ep_outcomes) + 1, max(1, window // 2)):
        w = slice(end - window, end)
        curve.append({"incidents": end, "success_rate": round(sum(ep_outcomes[w]) / window, 3),
                      "picked_best": round(sum(picked_best[w]) / window, 3)})
    out = {"tenant": tenant, "n": n, "epsilon": epsilon, "window": window, "curve": curve,
           "final_stats": run_tool(ctx, "rank_runbooks", {"signal": signals[0]}).rows,
           "expected_success_best": round(sum(truth[b] for b in best.values()) / len(best), 3),
           "expected_success_random": round(sum(sum(truth[r] for r in truth if r.startswith(f'rb:{sg}-')) / 2
                                                for sg in signals) / len(signals), 3)}
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / f"learning_{tenant}.json").write_text(json.dumps(out, indent=1))
    return out
