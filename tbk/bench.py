"""Concurrency benchmark: many agent crews + raw reads at once, across tenants, plus an atomic-claim race.

``python -m tbk.bench --workers 50`` writes ``data/bench_results.json`` and ``docs/BENCH.md``.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from . import memory, tasks
from .agents.orchestrator import run_incident
from .config import DATA_DIR, NOW, ROOT
from .seed.generate import get_dataset
from .tools import ToolContext, run_tool


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p * len(xs)))], 1) if xs else 0.0


def crews(workers: int, tenants: list[str]) -> dict:
    jobs = []
    for i in range(workers):
        t = tenants[i % len(tenants)]
        alerts = get_dataset(t).meta["live_alerts"]
        jobs.append((t, alerts[(i // len(tenants)) % len(alerts)]["alert"]))

    def one(job):
        t0 = time.perf_counter()
        r = run_incident(*job)
        return (time.perf_counter() - t0) * 1000, r

    t0 = time.perf_counter()
    with ThreadPoolExecutor(workers) as ex:
        out = list(ex.map(one, jobs))
    wall = time.perf_counter() - t0
    lat = [o[0] for o in out]
    ok = [o[1] for o in out if not o[1].error and o[1].grounded_pct == 100.0]
    return {"workers": workers, "tenants": tenants, "wall_s": round(wall, 2), "incidents_per_s": round(workers / wall, 2),
            "p50_ms": _pct(lat, 0.5), "p95_ms": _pct(lat, 0.95), "max_ms": round(max(lat), 1),
            "fully_grounded_runs": len(ok), "errors": sum(1 for o in out if o[1].error)}


def reads(n: int, tenants: list[str], workers: int) -> dict:
    def one(i):
        t = tenants[i % len(tenants)]
        t0 = time.perf_counter()
        run_tool(ToolContext(t, NOW), "blast_radius", {"service": "auth-service", "depth": 3})
        return (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    with ThreadPoolExecutor(workers) as ex:
        lat = list(ex.map(one, range(n)))
    wall = time.perf_counter() - t0
    return {"ops": n, "workers": workers, "ops_per_s": round(n / wall, 1), "p50_ms": _pct(lat, 0.5),
            "p95_ms": _pct(lat, 0.95)}


def claim_race(tenant: str, contenders: int = 100) -> dict:
    ctx = ToolContext(tenant, NOW)
    memory.ensure_agents(ctx)
    alert = get_dataset(tenant).meta["live_alerts"][0]["alert"]
    ctx.q("MATCH (a:Alert {id:$a}), (s:Service)<-[:FIRED_ON]-(a) "
          "MERGE (i:Incident {id:'inc:RACE'}) SET i.ts_open=$at MERGE (i)-[:TRIGGERED_BY]->(a)", {"a": alert, "at": NOW})
    task = tasks.create_task(ctx, "investigate", "inc:RACE", 0.5)

    def contender(i):
        return tasks.claim_next(ctx, "inc:RACE", f"agent:{i}", ["investigate"], retries=1)

    with ThreadPoolExecutor(contenders) as ex:
        results = list(ex.map(contender, range(contenders)))
    winners = [r for r in results if r]
    ctx.q("MATCH (i:Incident {id:'inc:RACE'}) OPTIONAL MATCH (t:Task)-[:FOR]->(i) DETACH DELETE t, i")
    return {"contenders": contenders, "winners": len(winners), "exactly_one": len(winners) == 1 and winners[0]["id"] == task}


def run(workers: int = 50, tenants: list[str] | None = None) -> dict:
    tenants = tenants or ["helix", "orbit"]
    res = {"crews": crews(workers, tenants), "reads": reads(400, tenants, 32), "claim_race": claim_race(tenants[0])}
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "bench_results.json").write_text(json.dumps(res, indent=1))
    c, r, k = res["crews"], res["reads"], res["claim_race"]
    md = ["# Concurrency benchmark", "",
          f"Local FalkorDB (single container), {len(tenants)} tenants ({', '.join(tenants)}), Python client, threads.", "",
          "| Test | Result |", "|---|---|",
          f"| {c['workers']} full agent crews at once (triage → investigator → remediator; reads+writes) | "
          f"{c['incidents_per_s']} incidents/s, p50 {c['p50_ms']} ms, p95 {c['p95_ms']} ms, "
          f"{c['fully_grounded_runs']}/{c['workers']} fully grounded, {c['errors']} errors |",
          f"| {r['ops']} concurrent graph reads ({r['workers']} threads) | {r['ops_per_s']} ops/s, p50 {r['p50_ms']} ms, p95 {r['p95_ms']} ms |",
          f"| {k['contenders']} workers racing to claim one task | {k['winners']} winner(s); exactly one: {k['exactly_one']} |"]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "BENCH.md").write_text("\n".join(md) + "\n")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=50)
    a = ap.parse_args()
    print(json.dumps(run(a.workers), indent=2))
