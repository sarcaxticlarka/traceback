"""Run report structures: what the UI replays and what the evals read."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StepRecord:
    agent: str
    idx: int
    tool: str
    args: dict
    why: str
    summary: str
    n_claims: int
    edge_ids: list[int]
    node_ids: list[str]
    ms: float
    cypher_ref: str
    error: str | None = None


@dataclass
class AgentReport:
    agent: str
    episode_id: str | None = None
    task_id: str | None = None
    steps: list[StepRecord] = field(default_factory=list)
    verification: dict = field(default_factory=dict)       # Verification.to_dict()
    payload: dict = field(default_factory=dict)            # structured result (finding / actions)
    headline: str = ""
    ms: float = 0.0


@dataclass
class RunReport:
    run_id: str
    tenant: str
    alert_id: str
    incident_id: str | None
    graph_enabled: bool
    planner: str
    agents: list[AgentReport] = field(default_factory=list)
    headline: str = ""
    grounded_pct: float = 0.0
    n_claims: int = 0
    n_withheld: int = 0
    tasks: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    learned: dict = field(default_factory=dict)
    error: str | None = None
    ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
