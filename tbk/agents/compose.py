"""Claim composition: choose which evidence-backed claims go into an answer, optionally let an LLM rephrase.

Rephrasing is safe by construction: the verifier re-checks that the final text mentions only entities that the
cited evidence contains, so a model cannot introduce an ungrounded name.
"""
from __future__ import annotations

import json
import re

from ..tools import Claim, ToolResult

# tool -> max claims taken, in presentation order
INVESTIGATION_ORDER = [("get_alert", 1), ("recent_changes", 3), ("owners_of", 4), ("who_knows", 4), ("facts_as_of", 2),
                       ("blast_radius", 5), ("similar_incidents", 4), ("decision_lineage", 4)]


def pool_claims(results: list[ToolResult], order: list[tuple[str, int]] = INVESTIGATION_ORDER) -> list[Claim]:
    out: list[Claim] = []
    seen: set[str] = set()
    for tool, cap in order:
        taken = 0
        for r in results:
            if r.tool != tool or r.error:
                continue
            for c in r.claims:
                if taken >= cap or c.text in seen:
                    continue
                seen.add(c.text)
                out.append(c)
                taken += 1
    return out


def all_claims(results: list[ToolResult], cap: int = 12) -> list[Claim]:
    out, seen = [], set()
    for r in results:
        if r.error:
            continue
        for c in r.claims:
            if c.text not in seen and len(out) < cap:
                seen.add(c.text)
                out.append(c)
    return out


REPHRASE_PROMPT = """Rewrite each numbered claim as one clear sentence for an on-call engineer. Keep every entity name
exactly as written and do not add any entity, number or fact that is not in the claim. Reply with JSON only:
{{"claims": [{{"i": <number>, "text": "<sentence>"}}]}}

{claims}"""


def llm_rephrase(claims: list[Claim], client=None) -> list[Claim]:
    """Optional: ask a provider (with failover) to polish claim text. Any failure returns the claims unchanged."""
    if client is None or not claims:
        return claims
    numbered = "\n".join(f"{i}. {c.text}" for i, c in enumerate(claims))
    try:
        resp = client.complete("", [{"role": "user", "content": REPHRASE_PROMPT.format(claims=numbered)}], None, 1500)
        data = json.loads(re.search(r"\{.*\}", resp.text, re.S).group(0))
        by_i = {int(x["i"]): str(x["text"]) for x in data["claims"]}
    except Exception:
        return claims
    out = []
    for i, c in enumerate(claims):
        if i in by_i and by_i[i].strip():
            d = c.to_dict()
            d["text"] = by_i[i].strip()
            out.append(Claim.from_dict(d))
        else:
            out.append(c)
    return out
