"""Planner layer: decides *which tool to call next*. Two interchangeable implementations.

* ``InvestigatePlanner`` - deterministic playbook that reacts to tool results (works offline, reproducible).
* ``AnthropicPlanner``  - Claude tool-use loop over the same tool registry (needs ANTHROPIC_API_KEY).

The LLM never produces graph facts: facts come from tools as evidence-bearing claims and are verified
afterwards. The LLM only chooses tools and (optionally) selects/rephrases claims.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from .config import get_settings
from .tools import tool_schemas
from .tools.base import ToolResult
from .agents.scoring import pick_suspect


@dataclass
class Step:
    tool: str
    args: dict
    why: str = ""


@dataclass
class Goal:
    kind: str                         # investigate | question
    tenant: str
    at: int
    alert_id: str = ""
    service: str = ""
    signal: str = ""
    text: str = ""


class Planner(Protocol):
    def next(self, history: list[ToolResult]) -> Step | None: ...


def _last(history: list[ToolResult], tool: str) -> ToolResult | None:
    for r in reversed(history):
        if r.tool == tool and not r.error:
            return r
    return None


def _called(history: list[ToolResult], tool: str, **match) -> bool:
    return any(r.tool == tool and all(r.args.get(k) == v for k, v in match.items()) for r in history)


@dataclass
class InvestigatePlanner:
    """Playbook: alert -> change correlation -> blast radius -> ownership -> expertise -> history."""
    goal: Goal
    max_steps: int = 12
    service: str = ""
    signal: str = ""
    _steps: int = field(default=0, init=False)

    def next(self, history: list[ToolResult]) -> Step | None:
        if self._steps >= self.max_steps:
            return None
        step = self._decide(history)
        if step:
            self._steps += 1
        return step

    def _decide(self, h: list[ToolResult]) -> Step | None:
        g = self.goal
        if g.alert_id and not _called(h, "get_alert"):
            return Step("get_alert", {"alert_id": g.alert_id}, "Resolve the alert to a service and signal")
        alert = _last(h, "get_alert")
        service = (alert.rows[0]["service"] if alert and alert.rows else g.service)
        signal = (alert.rows[0]["signal"] if alert and alert.rows else g.signal)
        self.service, self.signal = service, signal
        if not service:
            return None
        if not _called(h, "recent_changes"):
            return Step("recent_changes", {"service": service, "window_hours": 24, "depth": 2},
                        "Find deploys to the service or its dependencies in the last 24h")
        if not _called(h, "blast_radius"):
            return Step("blast_radius", {"service": service, "depth": 4}, "Measure who depends on the failing service")
        suspect = pick_suspect(_last(h, "recent_changes").rows if _last(h, "recent_changes") else [], g.at)
        target = suspect["service"] if suspect else service
        why_t = "suspect deploy's service" if suspect else "alerting service"
        if target != service and not _called(h, "blast_radius", service=target):
            return Step("blast_radius", {"service": target, "depth": 4}, "Measure what depends on the suspect's service")
        if not _called(h, "owners_of", service=target):
            return Step("owners_of", {"service": target}, f"Who owns the {why_t}?")
        if not _called(h, "who_knows", service=target):
            return Step("who_knows", {"service": target, "top": 3}, f"Who knows the {why_t} best?")
        if not _called(h, "facts_as_of", service=target):
            return Step("facts_as_of", {"service": target}, f"Current escalation knowledge for the {why_t}")
        if not _called(h, "similar_incidents"):
            return Step("similar_incidents", {"service": service, "signal": signal, "top": 4},
                        "Have we seen this pattern near this service before?")
        if not _called(h, "decision_lineage", service=target):
            return Step("decision_lineage", {"service": target}, f"Decisions that constrain the {why_t}")
        return None


SYSTEM_PROMPT = """You are the Investigator agent in an incident-response crew. All company knowledge lives in a graph
database reachable ONLY through your tools. Rules:
- Never state a fact you did not obtain from a tool. Every tool result carries verifiable evidence.
- Work like an SRE: resolve the alert, check recent changes across the dependency scope, measure the blast radius,
  find owners and experts of the most likely culprit, then check history and decisions.
- Prefer few, targeted calls. Stop (reply with plain text, no tool call) once you can name the likely cause, owner and
  who to page. Maximum {max_steps} tool calls."""


class AnthropicPlanner:
    """Claude tool-use loop. One tool call is surfaced per ``next`` so the orchestrator can run, record and verify it."""

    def __init__(self, goal: Goal, client=None, max_steps: int = 10):
        s = get_settings()
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=s.anthropic_key)
        self.client, self.model, self.goal, self.max_steps = client, s.llm_model, goal, max_steps
        self.messages: list[dict] = [{"role": "user", "content": self._prompt()}]
        self._pending: list[dict] = []
        self._awaiting: str | None = None
        self._steps = 0
        self.service, self.signal = goal.service, goal.signal

    def _prompt(self) -> str:
        g = self.goal
        if g.kind == "investigate":
            return f"Investigate {g.alert_id or g.service}. Current time (epoch): {g.at}."
        return f"{g.text}\nCurrent time (epoch): {g.at}."

    def next(self, history: list[ToolResult]) -> Step | None:
        if self._steps >= self.max_steps:
            return None
        if self._awaiting is not None and history:
            res = history[-1]
            payload = json.dumps({"summary": res.summary, "rows": res.rows[:12], "error": res.error}, default=str)
            self.messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": self._awaiting, "content": payload}]})
            self._awaiting = None
        if not self._pending:
            resp = self.client.messages.create(model=self.model, max_tokens=1024,
                                               system=SYSTEM_PROMPT.format(max_steps=self.max_steps),
                                               tools=tool_schemas(), messages=self.messages)
            self.messages.append({"role": "assistant", "content": resp.content})
            self._pending = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if not self._pending:
                return None
        block = self._pending.pop(0)
        self._awaiting = block.id
        self._steps += 1
        if block.name in ("blast_radius", "recent_changes", "dependencies") and block.input.get("service"):
            self.service = self.service or block.input["service"]
        return Step(block.name, dict(block.input), "chosen by model")


def make_planner(goal: Goal, use_llm: bool | None = None):
    s = get_settings()
    use = bool(s.anthropic_key) if use_llm is None else (use_llm and bool(s.anthropic_key))
    if use and goal.kind == "investigate":
        try:
            return AnthropicPlanner(goal)
        except Exception:
            pass
    return InvestigatePlanner(goal)
