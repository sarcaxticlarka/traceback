"""Flat document retrieval (no graph): the baseline the evaluation compares against, and the kill-switch fallback.

Embeds with the same local embedder as the graph's vector index, so the comparison isolates *relationships*,
not embedding quality. The corpus is the tenant's documents read from the generator, not from FalkorDB.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .embeddings import embed
from .seed.generate import get_dataset


@dataclass
class Hit:
    id: str
    kind: str
    title: str
    body: str
    ts: int
    score: float          # cosine similarity (higher = closer)


class DocIndex:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.matrix = np.array([d["embedding"] for d in docs], dtype=np.float32)

    @classmethod
    @lru_cache(maxsize=8)
    def for_tenant(cls, tenant: str) -> "DocIndex":
        return cls(get_dataset(tenant).docs)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        sims = self.matrix @ np.array(embed(query), dtype=np.float32)
        top = np.argsort(-sims)[:k]
        return [Hit(self.docs[i]["id"], self.docs[i]["kind"], self.docs[i]["title"], self.docs[i]["body"],
                    self.docs[i]["ts"], float(sims[i])) for i in top]
