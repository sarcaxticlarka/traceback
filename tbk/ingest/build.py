"""RepoModel + git history -> the same graph schema the agents already use (Service=module, Deploy=commit, ...).

Every relationship records *why it exists* (import sites, CODEOWNERS rule, git) so claims can be traced to source.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from ..config import INF
from ..embeddings import embed
from ..seed.generate import Dataset
from .analyze import RepoModel
from .codeowners import module_owner, parse as parse_codeowners
from .history import Commit, is_bot, module_stats, uid

MAX_DEPLOY_MODULES = 8


def _tiers(modules: list[str], dependents: dict[str, int]) -> dict[str, int]:
    order = sorted(modules, key=lambda m: (-dependents[m], m))
    n = len(order)
    return {m: (0 if i < max(1, n // 10) and dependents[m] > 0 else 1 if i < n * 3 // 10 and dependents[m] > 0
                else 2 if i < n * 6 // 10 else 3) for i, m in enumerate(order)}


def build_dataset(tenant: str, label: str, model: RepoModel, commits: list[Commit], blob_base: str = "") -> tuple[Dataset, dict]:
    ds = Dataset(tenant)
    humans = [c for c in commits if not is_bot(c.author)]
    now = (max(c.ts for c in commits) + 3600) if commits else 1_700_000_000
    mods = sorted(model.modules)
    dependents: dict[str, int] = Counter()
    dependencies: dict[str, int] = Counter()
    for (a, b) in model.deps:
        dependents[b] += 1
        dependencies[a] += 1
    stats = module_stats(humans, model.module_of, set(mods), now)
    tier = _tiers(mods, dependents)

    # ------------------------------------------------------------------ services (modules)
    for name in mods:
        m, s = model.modules[name], stats[name]
        ds.add("Service", id=f"svc:{name}", name=name, tier=tier[name], layer=0, files=m["files"], loc=m["loc"],
               langs=",".join(m["langs"]), commits=s["commits"], churn_90d=s["churn_90d"],
               top_author=s["top_author"], top_author_share=s["top_author_share"], last_commit_ts=s["last_ts"],
               dependents=dependents[name], dependencies=dependencies[name])
    for (a, b), d in sorted(model.deps.items()):
        ds.link("DEPENDS_ON", "Service", f"svc:{a}", "Service", f"svc:{b}", vf=0, vt=INF, count=d["count"],
                sites=json.dumps(d["sites"]), basis="import")

    # ------------------------------------------------------------------ people and ownership
    people: dict[str, str] = {}                                   # person id suffix -> display name
    for c in humans:
        people.setdefault(c.pid, c.author)
    for sl, nm in people.items():
        ds.add("Person", id=f"person:{sl}", name=nm, role="contributor")
    person_commits: dict[str, Counter] = defaultdict(Counter)     # person -> module -> commits
    recent = now - 365 * 86400
    for c in humans:
        seen = set()
        for path, _ in c.files:
            mo = model.module_of(path)
            if mo in model.modules and mo not in seen and c.ts >= recent:
                seen.add(mo)
                person_commits[c.pid][mo] += 1

    rules = parse_codeowners(model.codeowners) if model.codeowners else []
    files_by_module: dict[str, list[str]] = defaultdict(list)
    for p in model.files:
        files_by_module[model.module_of(p)].append(p)
    owner_of: dict[str, tuple[str, str, str]] = {}                # module -> (team_name, basis, rule)
    for name in mods:
        hit = module_owner(files_by_module[name], rules) if rules else None
        if hit:
            owner_of[name] = (hit[0], "codeowners", hit[1])
        else:
            s = stats[name]
            if s["commits"] >= 2 and s["top_author"]:
                owner_of[name] = (f"{s['top_author']} (top committer)", "top-committer",
                                  f"{s['top_author']} made {round(s['top_author_share'] * 100)}% of {s['commits']} commits")
    teams: dict[str, str] = {}
    for team_name, basis, _ in owner_of.values():
        teams.setdefault(team_name, f"team:{uid(team_name)}")
    for team_name, tid in teams.items():
        ds.add("Team", id=tid, name=team_name)
    for name, (team_name, basis, rule) in sorted(owner_of.items()):
        ds.link("OWNS", "Team", teams[team_name], "Service", f"svc:{name}", vf=0, vt=INF, basis=basis, rule=rule[:200])
    # membership: derived from who actually contributed to what the team owns
    team_modules: dict[str, set[str]] = defaultdict(set)
    for name, (team_name, _, _) in owner_of.items():
        team_modules[team_name].add(name)
    for team_name, ms in team_modules.items():
        scores = Counter()
        for sl, per in person_commits.items():
            n = sum(per[m] for m in ms)
            if n >= 2 or (team_name.endswith("(top committer)") and people[sl] in team_name and n >= 1):
                scores[sl] = n
        for sl, n in scores.most_common(8):
            ds.link("MEMBER_OF", "Person", f"person:{sl}", "Team", teams[team_name], vf=0, vt=INF,
                    basis="contributed-to-owned-modules", commits_last_year=n)

    # ------------------------------------------------------------------ commits (the "deploys")
    for c in humans:
        touched: dict[str, int] = defaultdict(int)
        for path, lines in c.files:
            mo = model.module_of(path)
            if mo in model.modules:
                touched[mo] += lines
        if not touched:
            continue
        did = f"dep:{c.sha[:7]}"
        ds.add("Deploy", id=did, sha=c.sha[:7], ts=c.ts, status="merged", summary=c.subject)
        ds.link("AUTHORED", "Person", f"person:{c.pid}", "Deploy", did, basis="git")
        for mo, lines in sorted(touched.items(), key=lambda kv: -kv[1])[:MAX_DEPLOY_MODULES]:
            ds.link("DEPLOYED_TO", "Deploy", did, "Service", f"svc:{mo}", lines=lines, basis="git")

    # ------------------------------------------------------------------ docs, decisions
    last_touch: dict[str, int] = {}
    for c in commits:
        for path, _ in c.files:
            last_touch.setdefault(path, c.ts)
    adr_by_num: dict[str, str] = {}
    for d in model.docs:
        did = f"doc:{d['path']}"
        ts = last_touch.get(d["path"], now)
        ds.add("Doc", id=did, kind=d["kind"], title=d["title"], body=d["body"], ts=ts,
               embedding=embed(d["title"] + " " + d["body"][:2000]))
        uri = f"{blob_base}/{d['path']}" if blob_base else f"repo://{label}/{d['path']}"
        ds.add("Source", id=f"src:{did}", kind=d["kind"], uri=uri, ts=ts)
        ds.link("DERIVED_FROM", "Doc", did, "Source", f"src:{did}")
        low = d["body"].lower()
        mentioned = [m for m in mods if len(m.rstrip("/")) >= 5 and "/" in m.rstrip("/") + "/" and m.rstrip("/").lower() in low][:15]
        for m in mentioned:
            ds.link("MENTIONS_SERVICE", "Doc", did, "Service", f"svc:{m}")
        d["_mentions"] = mentioned
        if d["kind"] == "adr":
            num = re.search(r"(\d{2,5})", d["path"].rsplit("/", 1)[-1])
            if num:
                adr_by_num[num.group(1).lstrip("0") or "0"] = d["path"]
    for d in model.docs:
        if d["kind"] != "adr":
            continue
        decid, did = f"dec:{d['path']}", f"doc:{d['path']}"
        title = re.sub(r"^(adr|rfc)?[-\s]*\d+[:.\-\s]+", "", d["title"], flags=re.I).strip() or d["title"]
        ds.add("Decision", id=decid, statement=title[:200], ts=last_touch.get(d["path"], now))
        ds.link("DECIDED_IN_DOC", "Decision", decid, "Doc", did)
        for m in d.get("_mentions", []):
            ds.link("CONSTRAINS", "Decision", decid, "Service", f"svc:{m}")
        for ref in re.findall(r"supersede[sd]?\s+(?:adr[-\s]*)?0*(\d+)", d["body"], flags=re.I):
            other = adr_by_num.get(ref)
            if other and other != d["path"]:
                ds.link("SUPERSEDES", "Decision", decid, "Decision", f"dec:{other}")

    # ------------------------------------------------------------------ ready-made investigations
    hot = sorted(mods, key=lambda m: (-stats[m]["churn_90d"] * (1 + dependents[m]), m))
    central = sorted(mods, key=lambda m: (-dependents[m], m))
    picks: list[tuple[str, str]] = []
    for m in hot[:2]:
        if stats[m]["commits"]:
            picks.append((m, "regression-after-recent-changes"))
    for m in central:
        if all(m != p for p, _ in picks) and dependents[m] > 0:
            picks.append((m, "tests-failing-downstream"))
            break
    for m in hot[2:6]:
        if len(picks) >= 4:
            break
        if stats[m]["commits"] and all(m != p for p, _ in picks):
            picks.append((m, "regression-after-recent-changes"))
    for i, (m, sig) in enumerate(picks, 1):
        aid = f"alert:LIVE-{i}"
        ds.add("Alert", id=aid, ts=now, severity=1 if tier[m] <= 1 else 2, signal=sig, summary=f"{sig} reported in {m}", live=True)
        ds.link("FIRED_ON", "Alert", aid, "Service", f"svc:{m}")

    summary = {
        "files": len(model.files), "modules": len(mods), "loc": sum(f.loc for f in model.files.values()),
        "languages": dict(Counter(f.lang for f in model.files.values()).most_common(6)),
        "module_deps": len(model.deps), "file_imports": model.file_deps, "commits": len(humans), "authors": len(people),
        "docs": len(model.docs), "decisions": sum(1 for d in model.docs if d["kind"] == "adr"),
        "has_codeowners": bool(rules), "owners_from": dict(Counter(b for _, b, _ in owner_of.values())),
        "history": bool(commits), "now": now, "module_depth": model.module_depth,
        "hotspots": [{"module": m, "churn_90d": stats[m]["churn_90d"], "dependents": dependents[m]} for m in hot[:5]],
    }
    return ds, summary
