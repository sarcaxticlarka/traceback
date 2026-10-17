"""Deterministic local text embedder (hashing trick, unigrams + bigrams, L2-normalised).

No network or API key needed, so the whole system and its evaluation are reproducible offline.
Swap ``embed`` for a hosted model by changing the single function; dimension is in Settings.
"""
from __future__ import annotations

import hashlib
import math
import re

from .config import get_settings

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-_]*")
_STOP = frozenset("the a an of to in on for and or is are was were be by with as at from that this it its".split())


def _tokens(text: str) -> list[str]:
    toks = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]


def embed(text: str, dim: int | None = None) -> list[float]:
    dim = dim or get_settings().embed_dim
    vec = [0.0] * dim
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
        vec[h % dim] += 1.0 if (h >> 63) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
