"""Flat document retrieval (no graph): the baseline the evaluation compares against, and the kill-switch fallback.

Hybrid retriever, as a competent RAG stack would use: dense hashed embeddings (same embedder as the graph's
vector index) fused with sparse TF-IDF over whole tokens (so exact service names like ``email-sender`` match).
The corpus is the tenant's documents read from the generator, not from FalkorDB. The comparison therefore
isolates *relationships*, not retrieval quality.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .embeddings import embed
from .seed.generate import get_dataset

_TOK = re.compile(r"[a-z0-9][a-z0-9\-_:.]*[a-z0-9]|[a-z0-9]")
DENSE_W, SPARSE_W = 0.3, 0.7


@dataclass
class Hit:
    id: str
    kind: str
    title: str
    body: str
    ts: int
    score: float          # fused similarity (higher = closer)


def _tokens(text: str) -> list[str]:
    return [t.strip(".:") for t in _TOK.findall(text.lower())]


class DocIndex:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.dense = np.array([d["embedding"] for d in docs], dtype=np.float32)
        counts = [Counter(_tokens(d["title"] + " " + d["body"])) for d in docs]
        df = Counter(t for c in counts for t in c)
        self.vocab = {t: i for i, t in enumerate(sorted(df))}
        n = len(docs)
        self.idf = np.zeros(len(self.vocab), dtype=np.float32)
        for t, i in self.vocab.items():
            self.idf[i] = math.log((1 + n) / (1 + df[t])) + 1.0
        self.sparse = np.zeros((n, len(self.vocab)), dtype=np.float32)
        for r, c in enumerate(counts):
            for t, f in c.items():
                self.sparse[r, self.vocab[t]] = (1 + math.log(f)) * self.idf[self.vocab[t]]
        norms = np.linalg.norm(self.sparse, axis=1, keepdims=True)
        self.sparse /= np.where(norms == 0, 1.0, norms)

    @classmethod
    @lru_cache(maxsize=8)
    def for_tenant(cls, tenant: str) -> "DocIndex":
        return cls(get_dataset(tenant).docs)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        q_dense = np.array(embed(query), dtype=np.float32)
        q_sparse = np.zeros(len(self.vocab), dtype=np.float32)
        for t, f in Counter(_tokens(query)).items():
            if t in self.vocab:
                q_sparse[self.vocab[t]] = (1 + math.log(f)) * self.idf[self.vocab[t]]
        nrm = np.linalg.norm(q_sparse)
        if nrm:
            q_sparse /= nrm
        sims = DENSE_W * (self.dense @ q_dense) + SPARSE_W * (self.sparse @ q_sparse)
        top = np.argsort(-sims)[:k]
        return [Hit(self.docs[i]["id"], self.docs[i]["kind"], self.docs[i]["title"], self.docs[i]["body"],
                    self.docs[i]["ts"], float(sims[i])) for i in top]
