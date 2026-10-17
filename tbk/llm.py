"""Planner layer: decides *which tool to call next*. Two interchangeable implementations.

* ``InvestigatePlanner`` - deterministic playbook that reacts to tool results (works offline, reproducible).
* ``LLMPlanner``        - tool-use loop over the same tool registry on any provider (Anthropic, OpenAI-compatible)
                          with automatic failover (see ``providers.py``).

The LLM never produces graph facts: facts come from tools as evidence-bearing claims and are verified
afterwards. The LLM only chooses tools and (optionally) selects/rephrases claims.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from .providers import FailoverClient, ProviderError
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
    window_hours: int = 24            # how far back to look for suspect changes (days, not hours, for code repos)


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
            return Step("recent_changes", {"service": service, "window_hours": g.window_hours, "depth": 2},
                        f"Find changes to the service or its dependencies in the last {g.window_hours}h")
        if not _called(h, "blast_radius"):
            return Step("blast_radius", {"service": service, "depth": 4}, "Measure who depends on the failing service")
        suspect = pick_suspect(_last(h, "recent_changes").rows if _last(h, "recent_changes") else [], g.at, g.window_hours)
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

QUESTION_PROMPT = """You answer questions about a company using ONLY the provided graph tools (ownership, dependencies,
deploys, incidents, decisions, time-aware facts). Call the tools you need, then reply with a short plain-text answer.
Never state facts you did not get from a tool. Maximum {max_steps} tool calls."""


class LLMPlanner:
    """Tool-use loop over any provider (Anthropic or OpenAI-compatible) with automatic failover.

    One tool call is surfaced per ``next`` so the orchestrator can run, record and verify it. The conversation is kept
    in a provider-neutral format, so a run can switch providers mid-way if one hits a rate limit.
    """

    def __init__(self, goal: Goal, client: FailoverClient, max_steps: int = 10):
        self.client, self.goal, self.max_steps = client, goal, max_steps
        self.messages: list[dict] = [{"role": "user", "content": self._prompt()}]
        self._pending: list[dict] = []
        self._awaiting: str | None = None
        self._steps = 0
        self.service, self.signal = goal.service, goal.signal
        self.final_text = ""
        self.error: str | None = None

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
            self.messages.append({"role": "tool", "tool_call_id": self._awaiting, "content": payload})
            self._awaiting = None
        if not self._pending:
            system = (SYSTEM_PROMPT if self.goal.kind == "investigate" else QUESTION_PROMPT).format(max_steps=self.max_steps)
            try:
                resp = self.client.complete(system, self.messages, tool_schemas(), 1024)
            except ProviderError as e:
                self.error = f"{e.provider}: {e.kind}"
                return None                       # every provider failed: the orchestrator falls back to what it has
            self.messages.append({"role": "assistant", "text": resp.text,
                                  "tool_calls": [{"id": c.id, "name": c.name, "input": c.input} for c in resp.tool_calls]})
            self._pending = [{"id": c.id, "name": c.name, "input": c.input} for c in resp.tool_calls]
            if not self._pending:
                self.final_text = resp.text
                return None
        call = self._pending.pop(0)
        self._awaiting = call["id"]
        self._steps += 1
        if call["name"] in ("blast_radius", "recent_changes", "dependencies") and call["input"].get("service"):
            self.service = self.service or call["input"]["service"]
        return Step(call["name"], dict(call["input"]), "chosen by model")


def make_planner(goal: Goal, client: FailoverClient | None = None):
    """LLM planner when a provider client is available, otherwise the deterministic playbook."""
    if client is not None and goal.kind in ("investigate", "question"):
        return LLMPlanner(goal, client)
    return InvestigatePlanner(goal)
