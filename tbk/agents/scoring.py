"""Deterministic, explainable scoring used by agents (kept out of the LLM on purpose)."""
from __future__ import annotations

import math


def pick_suspect(rows: list[dict], at: int) -> dict | None:
    """Rank deploys from ``recent_changes`` by dependency proximity and recency.

    score = 1/(1+hops) * exp(-age_hours/12): a deploy to the alerting service itself or its nearest
    dependency, shortly before the alert, is the prime suspect.
    """
    best, best_score = None, -1.0
    for r in rows:
        age_h = max(0.0, (at - r["ts"]) / 3600.0)
        score = (1.0 / (1.0 + r["hops"])) * math.exp(-age_h / 12.0)
        if score > best_score:
            best, best_score = dict(r, score=round(score, 4)), score
    return best


def risk_score(blast_size: int, tier: int, owner_has_members: bool, rank_penalty: float = 0.0) -> float:
    """0..1 risk of acting automatically: wide blast radius, critical tier and orphaned ownership raise it."""
    size = min(1.0, blast_size / 25.0)
    tier_w = {0: 1.0, 1: 0.7, 2: 0.4, 3: 0.2}.get(tier, 0.4)
    risk = 0.45 * size + 0.35 * tier_w + (0.0 if owner_has_members else 0.2) + rank_penalty
    return round(min(1.0, risk), 3)
