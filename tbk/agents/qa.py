"""Company-brain Q&A: natural-language question -> graph tools -> verified, sourced answer.

Routing is a transparent rule-based parser (intent regex + entity vocabulary from the tenant graph). It is the
offline counterpart of letting an LLM choose tools (``AnthropicPlanner`` does that for free-form questions);
keeping it deterministic makes the evaluation reproducible.
"""
from __future__ import annotations

import calendar
import re
import time
from dataclasses import dataclass, field

from ..config import NOW
from ..tools import ToolContext, ToolResult, run_tool
from ..verifier import vocabulary, verify_claims
from .compose import all_claims
from .scoring import pick_suspect

DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
ALERT = re.compile(r"alert:[A-Za-z0-9\-]+")

INTENTS: list[tuple[str, re.Pattern]] = [
    ("page_for_alert", re.compile(r"authored the deploy .*responsible for alert|who authored .*alert", re.I)),
    ("orphaned", re.compile(r"owned by a team with no current members|orphaned", re.I)),
    ("teams_impacted", re.compile(r"which teams own services .*impacted|teams .*impacted", re.I)),
    ("blast_all", re.compile(r"full blast radius|blast radius if", re.I)),
    ("dependents_2hop", re.compile(r"depend on .* within 2 hops", re.I)),
    ("direct_deps", re.compile(r"directly depend on|direct dependencies", re.I)),
    ("contact_asof", re.compile(r"escalation contact .* on \d{4}-\d{2}-\d{2}", re.I)),
    ("contact_now", re.compile(r"escalation contact", re.I)),
    ("decision_chain", re.compile(r"earlier decisions|superseded", re.I)),
    ("decision_current", re.compile(r"current decision", re.I)),
    ("who_resolved", re.compile(r"resolved incidents", re.I)),
    ("owner_members", re.compile(r"members of the team that owns", re.I)),
    ("owner_asof", re.compile(r"team owned .* on \d{4}-\d{2}-\d{2}", re.I)),
    ("owner_now", re.compile(r"which team owns|who owns", re.I)),
]


@dataclass
class Answer:
    question: str
    intent: str
    answers: set[str] = field(default_factory=set)
    text: str = ""
    steps: list[dict] = field(default_factory=list)
    verification: dict = field(default_factory=dict)
    ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {"question": self.question, "intent": self.intent, "answers": sorted(self.answers), "text": self.text,
                "steps": self.steps, "verification": self.verification, "ms": self.ms, "error": self.error}


def parse_date(text: str) -> int | None:
    m = DATE.search(text)
    return calendar.timegm((int(m[1]), int(m[2]), int(m[3]), 12, 0, 0)) if m else None


def find_service(ctx: ToolContext, text: str) -> str | None:
    best = None
    for m in vocabulary(ctx).finditer(text):
        k = m.group(1)
        if k in _service_names(ctx):
            best = best or k
    return best


_names_cache: dict[str, set[str]] = {}


def _service_names(ctx: ToolContext) -> set[str]:
    if ctx.tenant not in _names_cache:
        _names_cache[ctx.tenant] = {r["n"] for r in ctx.q("MATCH (s:Service) RETURN s.name AS n")}
    return _names_cache[ctx.tenant]


def detect_intent(text: str) -> str:
    for name, pat in INTENTS:
        if pat.search(text):
            return name
    return "freeform"


def answer_question(tenant: str, question: str, at: int = NOW) -> Answer:
    t0 = time.perf_counter()
    ctx = ToolContext(tenant, at)
    intent = detect_intent(question)
    ans = Answer(question, intent)
    results: list[ToolResult] = []

    def call(tool: str, **args) -> ToolResult:
        r = run_tool(ctx, tool, args)
        results.append(r)
        ans.steps.append({"tool": tool, "args": args, "summary": r.summary, "n_claims": len(r.claims), "ms": round(r.ms, 1),
                          "cypher_ref": r.cypher_ref, "error": r.error})
        return r

    try:
        svc = find_service(ctx, question)
        when = parse_date(question)
        if intent == "orphaned":
            ans.answers = {r["service"] for r in call("ownership_gaps").rows}
        elif intent == "page_for_alert":
            m = ALERT.search(question)
            alert = call("get_alert", alert_id=m.group(0)) if m else None
            if alert and alert.rows:
                ctx.at = alert.rows[0]["ts"]
                changes = call("recent_changes", service=alert.rows[0]["service"], window_hours=24, depth=2)
                sus = pick_suspect(changes.rows, ctx.at)
                if sus:
                    ans.answers = {sus["author"]}
        elif svc is None:
            ans.error = "no service recognised in the question"
        elif intent == "owner_now":
            ans.answers = {r["team"] for r in call("owners_of", service=svc).rows if r["team"]}
        elif intent == "owner_asof":
            ans.answers = {r["team"] for r in call("owners_of", service=svc, as_of=when).rows if r["team"]}
        elif intent == "owner_members":
            ans.answers = {m for r in call("owners_of", service=svc).rows for m in r["members"]}
        elif intent == "direct_deps":
            ans.answers = {r["service"] for r in call("dependencies", service=svc, depth=1).rows}
        elif intent == "dependents_2hop":
            ans.answers = {r["service"] for r in call("blast_radius", service=svc, depth=2, max_claims=12).rows}
        elif intent == "blast_all":
            ans.answers = {r["service"] for r in call("blast_radius", service=svc, depth=6, max_claims=12).rows}
        elif intent == "teams_impacted":
            ans.answers = {"team " + r["team"] for r in call("impacted_teams", service=svc).rows}
            ans.answers = {a[5:] for a in ans.answers}
        elif intent in ("decision_current", "decision_chain"):
            rows = call("decision_lineage", service=svc).rows
            want = "current" if intent == "decision_current" else "superseded"
            ans.answers = {r["statement"] for r in rows if r["state"] == want}
        elif intent in ("contact_asof", "contact_now"):
            rows = call("facts_as_of", service=svc, **({"as_of": when} if when else {})).rows
            ans.answers = {r["person"] for r in rows}
        elif intent == "who_resolved":
            ans.answers = {r["person"] for r in call("incident_resolvers", service=svc).rows}
        else:
            hits = call("search_docs", query=question, top=5)
            ans.text = "Could not map the question to a graph tool; closest documents: " + ", ".join(
                r["id"] for r in hits.rows)
    except Exception as e:
        ans.error = f"{type(e).__name__}: {e}"
    claims = all_claims(results, cap=14)
    ver = verify_claims(ctx, claims) if claims else None
    ans.verification = ver.to_dict() if ver else {"grounded_pct": 0.0, "n_claims": 0, "claims": []}
    if ans.answers and not ans.text:
        ans.text = "; ".join(sorted(ans.answers))
    ans.ms = round((time.perf_counter() - t0) * 1000, 1)
    return ans
