"""Deterministic synthetic company generator.

Produces graph nodes/edges *and* an independent plain-Python model of the same facts
(``Dataset.model``) so evaluation ground truth never needs to be read back from FalkorDB.

Planted facts (so the demo and evals have something real to find):
  * ownership transfers (6 services change team mid-history; some READMEs stay stale)
  * 4 "ghost" services owned by a team whose members have all left
  * ended (deprecated) dependency edges
  * decision chains where later decisions supersede earlier ones
  * escalation-contact facts that supersede each other over time
  * two recurring incident patterns (cache-redis, db-proxy) and runbooks with hidden success rates
  * 5 live alerts whose root cause is a single deploy 0-2 hops away in the dependency graph
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from ..config import DAY, INF, NOW, T0
from . import catalog as C

SEEDS = {"helix": 7, "orbit": 11}


def day_str(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


@dataclass
class Edge:
    type: str
    src_label: str
    src_id: str
    dst_label: str
    dst_id: str
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class Dataset:
    tenant: str
    nodes: dict[str, list[dict]] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    model: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def add(self, label: str, **props) -> dict:
        self.nodes.setdefault(label, []).append(props)
        return props

    def link(self, type_: str, sl: str, sid: str, dl: str, did: str, **props) -> None:
        self.edges.append(Edge(type_, sl, sid, dl, did, props))

    @property
    def docs(self) -> list[dict]:
        return self.nodes.get("Doc", [])


class _Gen:
    def __init__(self, tenant: str):
        self.t = tenant
        self.rng = random.Random(SEEDS.get(tenant, abs(hash(tenant)) % 1000))
        self.ds = Dataset(tenant)
        self.svc_layer: dict[str, int] = {}
        self.svc_team: dict[str, str] = {}
        self.own: list[dict] = []      # {team, svc, vf, vt}
        self.member: list[dict] = []   # {person, team, vf, vt}
        self.deps: list[dict] = []     # {src, dst, vf, vt}
        self.deploys: list[dict] = []
        self.incidents: list[dict] = []
        self.runbooks: list[dict] = []
        self.runbook_truth: dict[str, float] = {}

    # ---------------------------------------------------------------- helpers
    def owner_at(self, svc: str, t: int) -> str | None:
        for o in self.own:
            if o["svc"] == svc and o["vf"] <= t < o["vt"]:
                return o["team"]
        return None

    def members_at(self, team: str, t: int) -> list[str]:
        return [m["person"] for m in self.member if m["team"] == team and m["vf"] <= t < m["vt"]]

    def active_people(self, t: int) -> list[str]:
        return sorted({m["person"] for m in self.member if m["vf"] <= t < m["vt"]})

    def deps_at(self, svc: str, t: int) -> list[str]:
        return [d["dst"] for d in self.deps if d["src"] == svc and d["vf"] <= t < d["vt"]]

    def dependents_at(self, svc: str, t: int) -> list[str]:
        return [d["src"] for d in self.deps if d["dst"] == svc and d["vf"] <= t < d["vt"]]

    def scope(self, svc: str, t: int, depth: int) -> set[str]:
        seen, frontier = {svc}, {svc}
        for _ in range(depth):
            frontier = {x for f in frontier for x in self.deps_at(f, t)} - seen
            seen |= frontier
        return seen

    def pick_author(self, svc: str, t: int) -> str:
        team = self.owner_at(svc, t)
        pool = self.members_at(team, t) if team else []
        if pool and self.rng.random() < 0.9:
            return self.rng.choice(pool)
        return self.rng.choice(self.active_people(t))

    # ---------------------------------------------------------------- stages
    def build(self) -> Dataset:
        self.people_and_teams()
        self.services_and_deps()
        self.ownership()
        self.runbooks_and_signals()
        self.history_deploys_incidents()
        self.decisions()
        self.facts()
        self.live_alerts()
        self.tickets()
        self.service_readmes()
        self.finish()
        return self.ds

    def people_and_teams(self) -> None:
        ds, rng = self.ds, self.rng
        names = [f"{f} {l}" for f in C.FIRST for l in C.LAST]
        rng.shuffle(names)
        names = names[:40]
        for team in C.TEAMS + [C.LEGACY_TEAM]:
            ds.add("Team", id=f"team:{team}", name=team)
        self.people = []
        for i, nm in enumerate(names):
            pid = f"person:{nm.lower().replace(' ', '-')}"
            self.people.append(pid)
            ds.add("Person", id=pid, name=nm, role=rng.choice(["SWE", "SRE", "EM", "Staff SWE"]))
        pool = self.people[:]
        legacy = [pool.pop() for _ in range(3)]
        for i, p in enumerate(pool):
            team = C.TEAMS[i % len(C.TEAMS)]
            self.member.append({"person": p, "team": team, "vf": T0, "vt": INF})
        # a few people change teams mid-history
        for p in rng.sample(pool, 4):
            m = next(x for x in self.member if x["person"] == p)
            tx = T0 + rng.randint(100, 220) * DAY
            new_team = rng.choice([t for t in C.TEAMS if t != m["team"]])
            m["vt"] = tx
            self.member.append({"person": p, "team": new_team, "vf": tx, "vt": INF})
        # legacy team: everyone has left
        for p in legacy:
            self.member.append({"person": p, "team": C.LEGACY_TEAM, "vf": T0, "vt": NOW - rng.randint(20, 60) * DAY})
        for m in self.member:
            ds.link("MEMBER_OF", "Person", m["person"], "Team", f"team:{m['team']}", vf=m["vf"], vt=m["vt"])

    def services_and_deps(self) -> None:
        ds, rng = self.ds, self.rng
        by_layer = C.SERVICES_BY_LAYER
        indeg: dict[str, int] = {}
        for layer, names in by_layer.items():
            for n in names:
                self.svc_layer[n] = layer
                indeg[n] = 1
        for layer in range(1, 5):
            for n in by_layer[layer]:
                k = rng.randint(2, 4)
                chosen: set[str] = set()
                for _ in range(k * 3):
                    lo = layer - 1 if rng.random() < 0.7 else rng.randint(0, layer - 1)
                    cands = by_layer[lo]
                    w = [indeg[c] ** 1.4 for c in cands]            # preferential attachment -> hubs
                    pick = rng.choices(cands, weights=w)[0]
                    chosen.add(pick)
                    if len(chosen) >= k:
                        break
                for dst in sorted(chosen):
                    indeg[dst] += 1
                    self.deps.append({"src": n, "dst": dst, "vf": T0, "vt": INF})
        # guarantee every infrastructure hub is genuinely depended upon (recurring-incident realism)
        for hub in by_layer[0]:
            have = {d["src"] for d in self.deps if d["dst"] == hub}
            need = 6 if hub in C.SPECIAL_SIGNALS else 4
            for src in rng.sample([s for s in by_layer[1] + by_layer[2] if s not in have], max(0, need - len(have))):
                self.deps.append({"src": src, "dst": hub, "vf": T0, "vt": INF})
        # deprecate some edges mid-history (kept in graph with a closed validity window)
        for d in rng.sample([d for d in self.deps if self.svc_layer[d["src"]] >= 2], 8):
            d["vt"] = T0 + rng.randint(150, 250) * DAY
        for layer, names in by_layer.items():
            for n in names:
                ds.add("Service", id=f"svc:{n}", name=n, tier=C.TIER_BY_LAYER[layer], layer=layer)
        for d in self.deps:
            ds.link("DEPENDS_ON", "Service", f"svc:{d['src']}", "Service", f"svc:{d['dst']}",
                    vf=d["vf"], vt=d["vt"])

    def team_for(self, svc: str) -> str:
        low = svc.lower()
        for team, kws in C.TEAM_KEYWORDS.items():
            if any(k in low for k in kws):
                return team
        return self.rng.choice(C.TEAMS)

    def ownership(self) -> None:
        ds, rng = self.ds, self.rng
        for svc in self.svc_layer:
            team = C.LEGACY_TEAM if svc in C.GHOST_SERVICES else self.team_for(svc)
            self.svc_team[svc] = team
            self.own.append({"team": team, "svc": svc, "vf": T0, "vt": INF})
        transferable = [s for s in self.svc_layer if s not in C.GHOST_SERVICES and self.svc_layer[s] >= 2]
        self.transfers: list[dict] = []
        for svc in rng.sample(transferable, 6):
            old = self.svc_team[svc]
            new = rng.choice([t for t in C.TEAMS if t != old])
            tx = T0 + rng.randint(120, 200) * DAY
            o = next(x for x in self.own if x["svc"] == svc)
            o["vt"] = tx
            self.own.append({"team": new, "svc": svc, "vf": tx, "vt": INF})
            self.transfers.append({"svc": svc, "old": old, "new": new, "ts": tx})
        for o in self.own:
            ds.link("OWNS", "Team", f"team:{o['team']}", "Service", f"svc:{o['svc']}", vf=o["vf"], vt=o["vt"])

    def runbooks_and_signals(self) -> None:
        ds, rng = self.ds, self.rng
        for sig in C.ALL_SIGNALS:
            ds.add("Signal", id=f"signal:{sig}", name=sig)
            good, bad = rng.sample([0.78, 0.84, 0.72], 1)[0], rng.choice([0.25, 0.35, 0.4])
            variants = [("rollback-and-verify", good), ("scale-and-wait", bad)]
            rng.shuffle(variants)
            for variant, p in variants:
                rid = f"rb:{sig}-{variant}"
                steps = C.RUNBOOK_STEPS[sig]
                title = f"{sig} runbook ({variant})"
                rb = {"id": rid, "title": title, "signal": sig, "attempts": 0, "successes": 0, "last_used": 0,
                      "steps": steps}
                self.runbooks.append(rb)
                self.runbook_truth[rid] = p
                ds.add("Runbook", id=rid, title=title, attempts=0, successes=0, last_used=0)
                ds.link("FOR_SIGNAL", "Runbook", rid, "Signal", f"signal:{sig}")
                body = f"Runbook {title}. Signal: {sig}. Steps: " + "; ".join(f"{i+1}. {s}" for i, s in enumerate(steps))
                self.add_doc(f"doc:{rid}", "runbook", title, body, NOW - rng.randint(30, 200) * DAY)

    def add_doc(self, doc_id: str, kind: str, title: str, body: str, ts: int, mentions_svc=(), mentions_person=()) -> None:
        ds = self.ds
        ds.add("Doc", id=doc_id, kind=kind, title=title, body=body, ts=ts)
        src_id = f"src:{doc_id}"
        ds.add("Source", id=src_id, kind=kind,
               uri=f"https://wiki.{self.t}.example/{kind}/{doc_id.split(':', 1)[1]}", ts=ts)
        ds.link("DERIVED_FROM", "Doc", doc_id, "Source", src_id)
        for s in dict.fromkeys(mentions_svc):
            ds.link("MENTIONS_SERVICE", "Doc", doc_id, "Service", f"svc:{s}")
        for p in dict.fromkeys(mentions_person):
            ds.link("MENTIONS_PERSON", "Doc", doc_id, "Person", p)

    def pname(self, pid: str) -> str:
        return pid.split(":", 1)[1].replace("-", " ").title()

    def history_deploys_incidents(self) -> None:
        ds, rng = self.ds, self.rng
        services = sorted(self.svc_layer)
        weights = [1.0 + (4 - self.svc_layer[s]) * 0.3 for s in services]
        for n in range(600):
            ts = rng.randint(T0 + 3 * DAY, NOW - 48 * 3600)
            svc = rng.choices(services, weights=weights)[0]
            self.deploys.append({"id": f"dep:D{n:05d}", "svc": svc, "ts": ts, "sha": f"{rng.getrandbits(28):07x}",
                                 "author": self.pick_author(svc, ts), "status": "success"})
        self.deploys.sort(key=lambda d: d["ts"])
        # re-id after sorting so ids are chronological
        for i, d in enumerate(self.deploys):
            d["id"] = f"dep:D{i:05d}"
        candidates = rng.sample(self.deploys, 120)
        for i, d in enumerate(sorted(candidates, key=lambda x: x["ts"])):
            d["status"] = "failed"
            open_ts = d["ts"] + rng.randint(600, 7200)
            svc = d["svc"]
            dependents = sorted(self.scope_up(svc, open_ts, 2) - {svc})
            affected = [svc] + rng.sample(dependents, min(len(dependents), rng.randint(0, 3)))
            signal = C.SPECIAL_SIGNALS.get(svc) or rng.choice(C.GENERAL_SIGNALS)
            owner = self.owner_at(svc, open_ts)
            pool = self.members_at(owner, open_ts) or self.active_people(open_ts)
            resolver = rng.choice(pool)
            rb = rng.choice([r for r in self.runbooks if r["signal"] == signal])
            ok = rng.random() < self.runbook_truth[rb["id"]]
            sev = 1 if (self.svc_layer[svc] == 0 or len(affected) >= 3) else rng.choice([2, 3])
            inc_id, alert_id, doc_id = f"inc:I{i:04d}", f"alert:A{i:04d}", f"doc:pm-I{i:04d}"
            close_ts = open_ts + rng.randint(1800, 28800)
            title = f"{signal} on {svc} after deploy {d['sha']}"
            inc = {"id": inc_id, "svc": svc, "deploy": d["id"], "ts_open": open_ts, "ts_close": close_ts,
                   "severity": sev, "signal": signal, "resolver": resolver, "affected": affected, "runbook": rb["id"],
                   "ok": ok, "title": title}
            self.incidents.append(inc)
            rb["attempts"] += 1
            rb["successes"] += int(ok)
            rb["last_used"] = max(rb["last_used"], open_ts)
            ds.add("Alert", id=alert_id, ts=open_ts - rng.randint(60, 300), severity=sev, signal=signal,
                   summary=f"{signal} detected on {svc}", live=False)
            ds.link("FIRED_ON", "Alert", alert_id, "Service", f"svc:{svc}")
            ds.add("Incident", id=inc_id, ts_open=open_ts, ts_close=close_ts, severity=sev, title=title,
                   summary=f"{signal} on {svc}; resolved by {self.pname(resolver)}; deploy {d['sha']} implicated",
                   signal=signal)
            ds.link("TRIGGERED_BY", "Incident", inc_id, "Alert", alert_id)
            ds.link("CAUSED_BY", "Incident", inc_id, "Deploy", d["id"])
            ds.link("RESOLVED_BY", "Incident", inc_id, "Person", resolver)
            ds.link("FIXED_WITH", "Incident", inc_id, "Runbook", rb["id"], result="success" if ok else "fail",
                    ts=close_ts)
            for a in affected:
                ds.link("AFFECTED", "Incident", inc_id, "Service", f"svc:{a}")
            body = (f"Postmortem {inc_id}: {title}. On {day_str(open_ts)} deploy {d['sha']} to {svc} by "
                    f"{self.pname(d['author'])} caused {signal}. Affected services: {', '.join(affected)}. "
                    f"Resolved by {self.pname(resolver)} using {rb['title']} ({'worked' if ok else 'did not work'}). "
                    f"Severity {sev}.")
            self.add_doc(doc_id, "postmortem", f"Postmortem {inc_id}", body, close_ts + DAY,
                         mentions_svc=affected, mentions_person=[resolver, d["author"]])
            ds.link("DOCUMENTED_IN", "Incident", inc_id, "Doc", doc_id)
        for d in self.deploys:
            ds.add("Deploy", id=d["id"], sha=d["sha"], ts=d["ts"], status=d["status"],
                   summary=f"deploy {d['sha']} to {d['svc']}")
            ds.link("DEPLOYED_TO", "Deploy", d["id"], "Service", f"svc:{d['svc']}")
            ds.link("AUTHORED", "Person", d["author"], "Deploy", d["id"])
        for rb in self.runbooks:                     # persist historical procedural stats
            node = next(n for n in ds.nodes["Runbook"] if n["id"] == rb["id"])
            node.update(attempts=rb["attempts"], successes=rb["successes"], last_used=rb["last_used"])
        # a sprinkle of chat threads about incidents
        for inc in rng.sample(self.incidents, 20):
            body = (f"#incident-room: {self.pname(inc['resolver'])}: seeing {inc['signal']} on {inc['svc']}, "
                    f"looks related to the deploy. Rolling {'back' if inc['ok'] else 'forward'}.")
            self.add_doc(f"doc:chat-{inc['id'][4:]}", "chat", f"Chat about {inc['id']}", body, inc["ts_open"] + 600,
                         mentions_svc=[inc["svc"]], mentions_person=[inc["resolver"]])

    def scope_up(self, svc: str, t: int, depth: int) -> set[str]:
        seen, frontier = {svc}, {svc}
        for _ in range(depth):
            frontier = {x for f in frontier for x in self.dependents_at(f, t)} - seen
            seen |= frontier
        return seen

    def decisions(self) -> None:
        ds, rng = self.ds, self.rng
        services = [s for s in self.svc_layer if self.svc_layer[s] in (1, 2, 3)]
        lengths = [4, 3, 3, 3, 3, 3, 3, 3, 3, 2, 1, 1]       # 12 chains, 30 decisions
        n = 0
        self.decision_chains: list[list[str]] = []
        for length, svc in zip(lengths, rng.sample(services, len(lengths))):
            chain: list[str] = []
            ts = T0 + rng.randint(5, 60) * DAY
            for k in range(length):
                tech, purpose = rng.choice(C.TECH_CHOICES)
                did, doc_id = f"dec:D{n:03d}", f"doc:adr-{n:03d}"
                stmt = f"Use {tech} for {purpose} in {svc}"
                ds.add("Decision", id=did, statement=stmt, ts=ts)
                ds.link("CONSTRAINS", "Decision", did, "Service", f"svc:{svc}")
                author = rng.choice(self.members_at(self.owner_at(svc, ts) or "platform", ts) or self.active_people(ts))
                body = f"ADR-{n:03d}: {stmt}. Decided {day_str(ts)} by {self.pname(author)}."
                if chain:
                    body += f" Supersedes ADR of {chain[-1]}."
                    ds.link("SUPERSEDES", "Decision", did, "Decision", chain[-1])
                self.add_doc(doc_id, "adr", f"ADR-{n:03d}", body, ts, mentions_svc=[svc], mentions_person=[author])
                ds.link("DECIDED_IN_DOC", "Decision", did, "Doc", doc_id)
                ds.link("DECIDED_BY", "Decision", did, "Person", author)
                chain.append(did)
                n += 1
                ts += rng.randint(25, 70) * DAY
            self.decision_chains.append(chain)
            self.model_decisions = getattr(self, "model_decisions", {})
            self.model_decisions[svc] = chain

    def facts(self) -> None:
        ds, rng = self.ds, self.rng
        self.fact_chains: list[dict] = []
        fid = 0
        for svc in rng.sample([s for s in self.svc_layer if self.svc_layer[s] >= 2], 8):
            people = rng.sample(self.active_people(NOW), 2)
            switch = T0 + rng.randint(120, 220) * DAY
            ids = []
            for k, (p, vf, vt) in enumerate([(people[0], T0 + 20 * DAY, switch), (people[1], switch, INF)]):
                f_id, doc_id = f"fact:F{fid:03d}", f"doc:fact-F{fid:03d}"
                text = f"{self.pname(p)} is the escalation contact for {svc}"
                ds.add("Fact", id=f_id, text=text, confidence=0.9, vf=vf, vt=vt, recorded_at=vf + DAY)
                ds.link("ABOUT_SERVICE", "Fact", f_id, "Service", f"svc:{svc}")
                ds.link("ABOUT_PERSON", "Fact", f_id, "Person", p)
                self.add_doc(doc_id, "chat", f"Contact note {svc}", f"#oncall: {text} from {day_str(vf)}.", vf + DAY,
                             mentions_svc=[svc], mentions_person=[p])
                ds.link("SUPPORTED_BY", "Fact", f_id, "Source", f"src:{doc_id}")
                if ids:
                    ds.link("SUPERSEDES", "Fact", f_id, "Fact", ids[-1])
                ids.append(f_id)
                fid += 1
            self.fact_chains.append({"svc": svc, "switch": switch, "old": people[0], "new": people[1], "ids": ids})

    def _pick_live_targets(self) -> list[tuple[str, int, str]]:
        """Pick 5 (alerting service, depth, cause service) with globally unambiguous ground truth: no alert's cause
        service sits inside another alert's 2-hop dependency scope."""
        rng, base = self.rng, NOW - 1200
        depths = [2, 1, 2, 0, 1]
        preferred = ["checkout-api", "payments-api", "web-bff", "search-api", "orders-api"]
        pool = sorted(s for s, l in self.svc_layer.items() if l >= 3)

        def attempt(svcs: list[str]):
            chosen = []
            for svc, depth in zip(svcs, depths):
                scope = self.scope(svc, base, 2)
                ring = {svc} if depth == 0 else self.scope(svc, base, depth) - self.scope(svc, base, depth - 1)
                if not ring:
                    return None
                chosen.append((svc, depth, rng.choice(sorted(ring)), scope))
            ok = all(chosen[i][2] not in chosen[j][3] for i in range(5) for j in range(5) if i != j)
            return chosen if ok else None

        for svcs in [preferred] * 400 + [rng.sample(pool, 5) for _ in range(4000)]:
            got = attempt(svcs)
            if got:
                return [(a, b, c) for a, b, c, _ in got]
        raise RuntimeError("could not plant unambiguous live alerts")

    def live_alerts(self) -> None:
        ds, rng = self.ds, self.rng
        self.live: list[dict] = []
        for i, (svc, depth, cause_svc) in enumerate(self._pick_live_targets()):
            now = NOW - rng.randint(5, 40) * 60
            scope = self.scope(svc, now, 2)
            dep_ts = now - rng.randint(2, 6) * 3600
            author = self.pick_author(cause_svc, dep_ts)
            did = f"dep:L{i:03d}"
            d = {"id": did, "svc": cause_svc, "ts": dep_ts, "sha": f"{rng.getrandbits(28):07x}", "author": author,
                 "status": "success"}
            self.deploys.append(d)
            ds.add("Deploy", id=did, sha=d["sha"], ts=dep_ts, status="success", summary=f"deploy {d['sha']} to {cause_svc}")
            ds.link("DEPLOYED_TO", "Deploy", did, "Service", f"svc:{cause_svc}")
            ds.link("AUTHORED", "Person", author, "Deploy", did)
            # decoys: older deploys (>30h) on other services in scope
            for other in rng.sample(sorted(scope - {cause_svc}), min(2, len(scope) - 1)):
                ots = now - rng.randint(30, 200) * 3600
                oid = f"dep:X{i}{other[:3]}{rng.randint(0,999)}"
                oa = self.pick_author(other, ots)
                self.deploys.append({"id": oid, "svc": other, "ts": ots, "sha": f"{rng.getrandbits(28):07x}",
                                     "author": oa, "status": "success"})
                ds.add("Deploy", id=oid, sha=self.deploys[-1]["sha"], ts=ots, status="success",
                       summary=f"deploy {self.deploys[-1]['sha']} to {other}")
                ds.link("DEPLOYED_TO", "Deploy", oid, "Service", f"svc:{other}")
                ds.link("AUTHORED", "Person", oa, "Deploy", oid)
            signal = rng.choice(["high-latency", "error-rate"])
            aid = f"alert:LIVE-{i + 1}"
            ds.add("Alert", id=aid, ts=now, severity=1 if depth else 2, signal=signal,
                   summary=f"{signal} on {svc} (live)", live=True)
            ds.link("FIRED_ON", "Alert", aid, "Service", f"svc:{svc}")
            owner = self.owner_at(cause_svc, now)
            self.live.append({"alert": aid, "svc": svc, "ts": now, "signal": signal, "cause_svc": cause_svc,
                              "cause_deploy": did, "author": author, "depth": depth, "owner_team": owner})
        # decoys: recent deploys on services OUTSIDE every live alert's 2-hop scope, so "most recent deploy overall"
        # (what a flat log or vector search sees) is wrong and only dependency-scoped reasoning finds the cause
        in_scope: set[str] = set()
        for la in self.live:
            in_scope |= self.scope(la["svc"], la["ts"], 2)
        outside = sorted(set(self.svc_layer) - in_scope)
        for k, svc in enumerate(rng.sample(outside, 8)):
            ts = NOW - rng.randint(1, 20) * 3600
            did = f"dep:Y{k:03d}"
            author = self.pick_author(svc, ts)
            self.deploys.append({"id": did, "svc": svc, "ts": ts, "sha": f"{rng.getrandbits(28):07x}", "author": author,
                                 "status": "success"})
            ds.add("Deploy", id=did, sha=self.deploys[-1]["sha"], ts=ts, status="success",
                   summary=f"deploy {self.deploys[-1]['sha']} to {svc}")
            ds.link("DEPLOYED_TO", "Deploy", did, "Service", f"svc:{svc}")
            ds.link("AUTHORED", "Person", author, "Deploy", did)

    def tickets(self) -> None:
        ds, rng = self.ds, self.rng
        for n in range(80):
            svc = rng.choice(sorted(self.svc_layer))
            ts = rng.randint(T0, NOW)
            ds.add("Ticket", id=f"ticket:T{n:03d}", title=rng.choice(
                ["Reduce p99", "Add alerting", "Upgrade runtime", "Fix flaky test", "Document runbook"]) + f" for {svc}",
                   status=rng.choice(["open", "closed", "in-progress"]), ts=ts)
            ds.link("ABOUT", "Ticket", f"ticket:T{n:03d}", "Service", f"svc:{svc}")

    def service_readmes(self) -> None:
        ds, rng = self.ds, self.rng
        stale = {tr["svc"]: tr for tr in self.transfers}
        for svc in sorted(self.svc_layer):
            deps = self.deps_at(svc, NOW)
            tr = stale.get(svc)
            # README of transferred services was last edited before the transfer => stale owner (realistic doc rot)
            owner = tr["old"] if tr and rng.random() < 0.75 else self.owner_at(svc, NOW)
            ts = (tr["ts"] - 20 * DAY) if (tr and owner == tr["old"]) else NOW - rng.randint(5, 60) * DAY
            body = (f"{svc} README. Owner team: {owner}. Tier {C.TIER_BY_LAYER[self.svc_layer[svc]]}. "
                    f"Depends on: {', '.join(deps) if deps else 'nothing'}.")
            self.add_doc(f"doc:readme-{svc}", "readme", f"{svc} README", body, ts, mentions_svc=[svc] + deps)
        for tr in self.transfers:
            if rng.random() < 0.5:
                self.add_doc(f"doc:chat-transfer-{tr['svc']}", "chat", f"Ownership change {tr['svc']}",
                             f"#eng-announce: {tr['svc']} moved from team {tr['old']} to team {tr['new']} on "
                             f"{day_str(tr['ts'])}.", tr["ts"], mentions_svc=[tr["svc"]])

    def finish(self) -> None:
        from ..embeddings import embed
        for d in self.ds.nodes["Doc"]:
            d["embedding"] = embed(d["title"] + " " + d["body"])
        for inc in self.ds.nodes["Incident"]:
            inc["embedding"] = embed(inc["title"] + " " + inc["summary"])
        self.ds.model = {
            "services": self.svc_layer, "deps": self.deps, "own": self.own, "member": self.member,
            "deploys": self.deploys, "incidents": self.incidents, "transfers": self.transfers,
            "decision_chains": self.decision_chains, "fact_chains": self.fact_chains,
            "decisions_by_svc": getattr(self, "model_decisions", {}),
        }
        self.ds.meta = {"runbook_truth": self.runbook_truth, "live_alerts": self.live,
                        "ghost_services": C.GHOST_SERVICES, "now": NOW}


def generate(tenant: str) -> Dataset:
    return _Gen(tenant).build()


@lru_cache(maxsize=8)
def get_dataset(tenant: str) -> Dataset:
    return generate(tenant)
