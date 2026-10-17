"""Bring-your-own-data importer: a small JSON document describing services, dependencies, owners, deploys and alerts.

This is the path for production data: export it from your service catalog (Backstage, OpsLevel, Cortex), your deploy tool
or PagerDuty, map it to this shape, and upload. See docs/REAL_WORLD.md for the field mapping.
"""
from __future__ import annotations

import re
import time

from ..config import INF
from ..seed.generate import Dataset
from .fetch import IngestError
from .history import uid

MAX_ITEMS = 5000


def _s(v, n=120) -> str:
    return str(v if v is not None else "")[:n]


def build_bundle(tenant: str, data: dict) -> tuple[Dataset, dict]:
    if not isinstance(data, dict) or not isinstance(data.get("services"), list) or not data["services"]:
        raise IngestError("Bundle must be a JSON object with a non-empty 'services' list.")
    ds = Dataset(tenant)
    stamps = [int(x.get("ts")) for key in ("deploys", "alerts") for x in (data.get(key) or []) if isinstance(x, dict) and x.get("ts")]
    now = int(data.get("now") or (max(stamps) + 3600 if stamps else time.time()))     # "present" = just after the latest event
    services = {}
    for sv in data["services"][:MAX_ITEMS]:
        name = _s(sv.get("name") if isinstance(sv, dict) else sv, 80).strip()
        if not name or name in services:
            continue
        services[name] = sv if isinstance(sv, dict) else {}
        ds.add("Service", id=f"svc:{name}", name=name, tier=int(services[name].get("tier", 2)), layer=0,
               loc=0, commits=0, churn_90d=0, dependents=0, dependencies=0)
    deps = 0
    for d in (data.get("dependencies") or [])[:MAX_ITEMS]:
        a, b = _s(d.get("from")), _s(d.get("to"))
        if a in services and b in services and a != b:
            ds.link("DEPENDS_ON", "Service", f"svc:{a}", "Service", f"svc:{b}", vf=0, vt=INF, count=1, sites='["bundle"]', basis="bundle")
            deps += 1
    teams, people = {}, {}

    def team(n):
        if n not in teams:
            teams[n] = f"team:{uid(n)}"
            ds.add("Team", id=teams[n], name=n)
        return teams[n]

    def person(n):
        if n not in people:
            people[n] = f"person:{uid(n)}"
            ds.add("Person", id=people[n], name=n, role="member")
        return people[n]

    for t in data.get("teams") or []:
        tn = _s(t.get("name"), 60)
        if tn:
            for m in t.get("members") or []:
                ds.link("MEMBER_OF", "Person", person(_s(m, 60)), "Team", team(tn), vf=0, vt=INF, basis="bundle")
    for name, sv in services.items():
        if sv.get("owner"):
            ds.link("OWNS", "Team", team(_s(sv["owner"], 60)), "Service", f"svc:{name}", vf=0, vt=INF, basis="bundle", rule="bundle owner field")
    n_dep = 0
    for d in (data.get("deploys") or [])[:MAX_ITEMS]:
        svc, sha = _s(d.get("service")), re.sub(r"[^A-Za-z0-9]", "", _s(d.get("sha"), 12))[:7]
        if svc in services and sha:
            did = f"dep:{sha}"
            ds.add("Deploy", id=did, sha=sha, ts=int(d.get("ts") or now), status="success", summary=_s(d.get("summary")))
            ds.link("DEPLOYED_TO", "Deploy", did, "Service", f"svc:{svc}", lines=0, basis="bundle")
            if d.get("author"):
                ds.link("AUTHORED", "Person", person(_s(d["author"], 60)), "Deploy", did, basis="bundle")
            n_dep += 1
    for i, a in enumerate((data.get("alerts") or [])[:20], 1):
        svc = _s(a.get("service"))
        if svc in services:
            aid = f"alert:LIVE-{i}"
            ds.add("Alert", id=aid, ts=int(a.get("ts") or now), severity=int(a.get("severity", 2)), signal=_s(a.get("signal") or "alert", 60),
                   summary=f"{_s(a.get('signal') or 'alert')} on {svc}", live=True)
            ds.link("FIRED_ON", "Alert", aid, "Service", f"svc:{svc}")
    for sid_ in {e.dst_id for e in ds.edges if e.type == "DEPENDS_ON"}:
        for n in ds.nodes["Service"]:
            if n["id"] == sid_:
                n["dependents"] += 1
    summary = {"files": 0, "modules": len(services), "loc": 0, "languages": {}, "module_deps": deps, "file_imports": deps, "commits": n_dep,
               "authors": len(people), "docs": 0, "decisions": 0, "has_codeowners": False, "owners_from": {"bundle": len(teams)},
               "history": n_dep > 0, "now": now, "module_depth": 0, "hotspots": []}
    return ds, summary
