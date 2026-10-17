"""Runtime configuration, read once from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Timeline constants shared by the generator, tools and evals (epoch seconds).
DAY = 86_400
T0 = 1_767_225_600            # 2026-01-01T00:00:00Z, start of the synthetic history
NOW = T0 + 280 * DAY          # "present" for the synthetic company (2026-10-08)
INF = 4_102_444_800           # sentinel valid_to for open-ended edges (year 2100)


def _tenants() -> list[str]:
    return [t.strip() for t in os.getenv("TBK_TENANTS", "helix,orbit").split(",") if t.strip()]


@dataclass(frozen=True)
class Settings:
    falkor_host: str = field(default_factory=lambda: os.getenv("FALKORDB_HOST", "localhost"))
    falkor_port: int = field(default_factory=lambda: int(os.getenv("FALKORDB_PORT", "6390")))
    falkor_password: str | None = field(default_factory=lambda: os.getenv("FALKORDB_PASSWORD") or None)
    falkor_ssl: bool = field(default_factory=lambda: os.getenv("FALKORDB_SSL", "") == "1")
    tenants: list[str] = field(default_factory=_tenants)
    embed_dim: int = 256


def get_settings() -> Settings:
    return Settings()
