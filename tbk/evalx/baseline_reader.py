"""Docs-only baseline: single-pass retrieval (k=8) + an extractive reader. No graph, no relationships.

The reader is deliberately competent at *reading documents* (it parses READMEs, ADRs, chats and postmortems that
retrieval returns, picks the newest relevant statement, and even closes over the retrieved READMEs for dependents).
What it cannot do is reach documents it did not retrieve, compose across hops, or know facts no document states
(e.g. which deploy sits in a dependency scope, which team has no members left).
"""
from __future__ import annotations

import re

from ..agents.qa import ALERT, DATE, detect_intent, parse_date
from ..baseline import DocIndex, Hit
from ..seed.generate import get_dataset

K = 8


def _svc(ds, text: str) -> str | None:
    names = sorted(ds.model["services"], key=len, reverse=True)
    for n in names:
        if re.search(rf"(?<![\w\-]){re.escape(n)}(?![\w\-])", text):
            return n
    return None


def _readmes(hits: list[Hit]) -> dict[str, dict]:
    out = {}
    for h in hits:
        if h.kind != "readme":
            continue
        mo = re.match(r"(\S+) README\. Owner team: (\S+)\. Tier \d\. Depends on: (.*)\.", h.body)
        if mo:
            deps = set() if mo[3] == "nothing" else {d.strip() for d in mo[3].split(",")}
            out[mo[1]] = {"owner": mo[2], "deps": deps, "ts": h.ts}
    return out


def read_answer(tenant: str, question: str) -> set[str]:
    ds = get_dataset(tenant)
    intent = detect_intent(question)
    svc = _svc(ds, question)
    when = parse_date(question)
    hits = DocIndex.for_tenant(tenant).search(question, K)
    readmes = _readmes(hits)
    chats = [h for h in hits if h.kind == "chat"]

    if intent in ("owner_now", "owner_asof") and svc:
        transfer = next((re.search(r"moved from team (\S+) to team (\S+) on (\d{4}-\d{2}-\d{2})", h.body)
                         for h in chats if svc in h.body and "moved from team" in h.body), None)
        if transfer:
            old, new, d = transfer[1], transfer[2], parse_date(transfer[3])
            return {old} if (when and when < d) else {new}
        if svc in readmes:
            return {readmes[svc]["owner"]}
        return set()
    if intent == "direct_deps" and svc:
        return set(readmes.get(svc, {}).get("deps", set()))
    if intent in ("dependents_2hop", "blast_all", "teams_impacted") and svc:
        depth = 2 if intent == "dependents_2hop" else 6
        found, frontier = set(), {svc}
        for _ in range(depth):
            frontier = {s for s, r in readmes.items() if r["deps"] & frontier} - found - {svc}
            found |= frontier
        if intent == "teams_impacted":
            return {readmes[s]["owner"] for s in found}
        return found
    if intent in ("decision_current", "decision_chain") and svc:
        adrs = sorted((h for h in hits if h.kind == "adr" and svc in h.body), key=lambda h: h.ts)
        stmts = [re.search(r"ADR-\d+: (.*?)\. Decided", h.body)[1] for h in adrs if re.search(r"ADR-\d+: (.*?)\. Decided", h.body)]
        if not stmts:
            return set()
        return {stmts[-1]} if intent == "decision_current" else set(stmts[:-1])
    if intent in ("contact_now", "contact_asof") and svc:
        notes = []
        for h in chats:
            mo = re.search(r"#oncall: (.*?) is the escalation contact for (\S+) from (\d{4}-\d{2}-\d{2})", h.body)
            if mo and mo[2] == svc:
                notes.append((parse_date(mo[3]), mo[1]))
        notes.sort()
        if when:
            notes = [n for n in notes if n[0] <= when]
        return {notes[-1][1]} if notes else set()
    if intent == "who_resolved" and svc:
        out = set()
        for h in hits:
            if h.kind == "postmortem":
                mo = re.search(r"Affected services: (.*?)\. Resolved by (.*?) using", h.body)
                if mo and svc in {x.strip() for x in mo[1].split(",")}:
                    out.add(mo[2])
        return out
    return set()          # page_for_alert, owner_members, orphaned: no document states these
