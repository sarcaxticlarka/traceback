"""Evaluation questions with ground truth computed from the generator's plain-Python model (never from FalkorDB)."""
from __future__ import annotations

import calendar
import random
import time
from dataclasses import dataclass

from ..config import DAY, NOW
from ..seed.generate import Dataset, get_dataset


@dataclass
class Question:
    id: str
    tenant: str
    intent: str
    bucket: str            # 1-hop | 2-hop | 3+-hop | temporal
    text: str
    truth: set[str]


def noon(ts: int) -> int:
    t = time.gmtime(ts)
    return calendar.timegm((t.tm_year, t.tm_mon, t.tm_mday, 12, 0, 0))


def day(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


class Model:
    """Time-aware queries over the dataset's plain model."""

    def __init__(self, ds: Dataset):
        self.ds, self.m = ds, ds.model

    def owner(self, svc: str, t: int) -> str | None:
        return next((o["team"] for o in self.m["own"] if o["svc"] == svc and o["vf"] <= t < o["vt"]), None)

    def members(self, team: str, t: int) -> set[str]:
        names = {p["id"]: p["name"] for p in self.ds.nodes["Person"]}
        return {names[x["person"]] for x in self.m["member"] if x["team"] == team and x["vf"] <= t < x["vt"]}

    def deps(self, svc: str, t: int) -> set[str]:
        return {d["dst"] for d in self.m["deps"] if d["src"] == svc and d["vf"] <= t < d["vt"]}

    def dependents(self, svc: str, t: int, depth: int) -> set[str]:
        seen, frontier = {svc}, {svc}
        for _ in range(depth):
            frontier = {d["src"] for d in self.m["deps"] if d["dst"] in frontier and d["vf"] <= t < d["vt"]} - seen
            seen |= frontier
        return seen - {svc}

    def decision_stmt(self) -> dict[str, str]:
        return {d["id"]: d["statement"] for d in self.ds.nodes["Decision"]}

    def resolvers(self, svc: str) -> set[str]:
        names = {p["id"]: p["name"] for p in self.ds.nodes["Person"]}
        return {names[i["resolver"]] for i in self.m["incidents"] if svc in i["affected"] and i["ts_open"] <= NOW}

    def orphaned(self, t: int) -> set[str]:
        out = set()
        for o in self.m["own"]:
            if o["vf"] <= t < o["vt"] and not self.members(o["team"], t):
                out.add(o["svc"])
        return out


def build_questions(tenant: str, seed: int = 21) -> list[Question]:
    ds = get_dataset(tenant)
    M, m = Model(ds), ds.model
    rng = random.Random(seed)
    qs: list[Question] = []

    def add(intent: str, bucket: str, text: str, truth: set[str]) -> None:
        qs.append(Question(f"{tenant}-{len(qs):02d}", tenant, intent, bucket, text, set(truth)))

    services = sorted(m["services"])
    mid_layer = [s for s in services if m["services"][s] >= 2]
    transferred = [t["svc"] for t in m["transfers"]]

    for svc in rng.sample(mid_layer, 4):
        add("owner_now", "1-hop", f"Which team owns {svc} today?", {M.owner(svc, NOW)})
    for svc in rng.sample([s for s in mid_layer if M.deps(s, NOW)], 4):
        add("direct_deps", "1-hop", f"Which services does {svc} directly depend on?", M.deps(svc, NOW))
    for ch in rng.sample(m["fact_chains"], 3):
        names = {p["id"]: p["name"] for p in ds.nodes["Person"]}
        add("contact_now", "1-hop", f"Who is the escalation contact for {ch['svc']}?", {names[ch["new"]]})
    for svc in rng.sample([s for s in services if len(M.resolvers(s)) >= 2], 3):
        add("who_resolved", "1-hop", f"Who has resolved incidents affecting {svc}?", M.resolvers(svc))
    for svc in rng.sample(mid_layer, 3):
        team = M.owner(svc, NOW)
        add("owner_members", "2-hop", f"Who are the current members of the team that owns {svc}?", M.members(team, NOW))
    cands2 = [s for s in services if 2 <= len(M.dependents(s, NOW, 2)) <= 12]
    for svc in rng.sample(cands2, 4):
        add("dependents_2hop", "2-hop", f"Which services depend on {svc} within 2 hops?", M.dependents(svc, NOW, 2))
    for tr in rng.sample(m["transfers"], 4):
        d = noon(tr["ts"] - 30 * DAY)
        add("owner_asof", "temporal", f"Which team owned {tr['svc']} on {day(d)}?", {tr["old"]})
    for ch in rng.sample(m["fact_chains"], 3):
        names = {p["id"]: p["name"] for p in ds.nodes["Person"]}
        d = noon(ch["switch"] - 20 * DAY)
        add("contact_asof", "temporal", f"Who was the escalation contact for {ch['svc']} on {day(d)}?", {names[ch["old"]]})
    cands3 = [s for s in services if 3 <= len(M.dependents(s, NOW, 6)) <= 14]
    for svc in rng.sample(cands3, 4):
        add("blast_all", "3+-hop", f"What is the full blast radius if {svc} fails?", M.dependents(svc, NOW, 6))
    for svc in rng.sample(cands3, 4):
        deps = M.dependents(svc, NOW, 6)
        add("teams_impacted", "3+-hop", f"Which teams own services that would be impacted if {svc} fails?",
            {M.owner(d, NOW) for d in deps})
    names = {p["id"]: p["name"] for p in ds.nodes["Person"]}
    for la in ds.meta["live_alerts"]:
        add("page_for_alert", "3+-hop", f"Who authored the deploy most likely responsible for {la['alert']}?",
            {names[la["author"]]})
    stmt = M.decision_stmt()
    chains = [c for c in m["decision_chains"] if len(c) >= 2]
    for chain in rng.sample(chains, 3):
        svc = next(s for s, c in m["decisions_by_svc"].items() if c == chain)
        add("decision_current", "3+-hop", f"What is the current decision constraining {svc}?", {stmt[chain[-1]]})
    for chain in rng.sample(chains, 3):
        svc = next(s for s, c in m["decisions_by_svc"].items() if c == chain)
        add("decision_chain", "3+-hop", f"Which earlier decisions were superseded for {svc}?", {stmt[d] for d in chain[:-1]})
    add("orphaned", "3+-hop", "Which services are owned by a team with no current members?", M.orphaned(NOW))
    return qs
