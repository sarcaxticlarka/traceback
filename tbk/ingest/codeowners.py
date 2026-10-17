"""CODEOWNERS parsing (GitHub semantics: last matching pattern wins)."""
from __future__ import annotations

import re
from collections import Counter

Rule = tuple[re.Pattern, list[str], str]


def _pattern_to_regex(pat: str) -> re.Pattern:
    """gitignore-style glob -> regex. A pattern with a slash anywhere but the end is anchored to the repo root."""
    anchored = pat.startswith("/") or "/" in pat.rstrip("/")
    body = pat.strip("/")
    rx, i = "", 0
    while i < len(body):
        if body[i:i + 3] == "**/":
            rx += "(?:.*/)?"
            i += 3
        elif body[i:i + 2] == "**":
            rx += ".*"
            i += 2
        else:
            c = body[i]
            rx += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
            i += 1
    return re.compile(f"^{'' if anchored else '(?:.*/)?'}{rx}(?:/.*)?$")


def parse(text: str) -> list[Rule]:
    rules: list[Rule] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            rules.append((_pattern_to_regex(parts[0]), [o for o in parts[1:] if o.startswith("@") or "@" in o], raw.strip()))
        except re.error:
            continue
    return rules


def owners_for(path: str, rules: list[Rule]) -> tuple[list[str], str] | None:
    hit = None
    for rx, owners, raw in rules:
        if rx.match(path):
            hit = (owners, raw)
    return hit


def module_owner(files: list[str], rules: list[Rule]) -> tuple[str, str] | None:
    """Most common owner across a module's files, with the rule line that assigned it."""
    votes: Counter = Counter()
    rule_of: dict[str, str] = {}
    for f in files[:80]:
        hit = owners_for(f, rules)
        if hit and hit[0]:
            votes[hit[0][0]] += 1
            rule_of.setdefault(hit[0][0], hit[1])
    if not votes:
        return None
    owner = votes.most_common(1)[0][0]
    return owner, rule_of[owner]
