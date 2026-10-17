"""Schema (indexes) + bulk loader. ``python -m tbk.seed.load [--tenants helix,orbit] [--reset]``."""
from __future__ import annotations

import argparse
import time
from collections import defaultdict

from ..config import get_settings
from ..graph import GraphStore, get_store
from .generate import Dataset, get_dataset

INDEXED_LABELS = ["Service", "Person", "Team", "Deploy", "Alert", "Incident", "Doc", "Decision", "Ticket",
                  "Source", "Runbook", "Signal", "Fact", "Episode", "Task", "Agent", "Finding", "Action", "ToolCall"]
EXTRA_INDEXES = [("Task", "status"), ("Deploy", "ts"), ("Alert", "live"), ("Doc", "kind"), ("Episode", "ts")]
BATCH = 400
VECTOR_LABELS = {"Doc", "Incident"}


def create_schema(store: GraphStore, tenant: str) -> None:
    g = store.raw_graph(tenant)
    dim = get_settings().embed_dim
    for label in INDEXED_LABELS:
        _try(g, f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    for label, prop in EXTRA_INDEXES:
        _try(g, f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
    for label in VECTOR_LABELS:
        _try(g, f"CREATE VECTOR INDEX FOR (n:{label}) ON (n.embedding) "
                f"OPTIONS {{dimension:{dim}, similarityFunction:'cosine'}}")


def _try(g, q: str) -> None:
    try:
        g.query(q)
    except Exception as e:                       # index already exists
        if "already" not in str(e).lower() and "exist" not in str(e).lower():
            raise


def load_dataset(store: GraphStore, ds: Dataset, reset: bool = True) -> dict[str, int]:
    tenant = ds.tenant
    if reset:
        store.drop(tenant)
    g = store.raw_graph(tenant)
    create_schema(store, tenant)
    counts: dict[str, int] = {}
    for label, rows in ds.nodes.items():
        plain = [{k: v for k, v in r.items() if k != "embedding"} for r in rows]
        vec = [{"id": r["id"], "e": r["embedding"]} for r in rows if "embedding" in r]
        for i in range(0, len(plain), BATCH):
            g.query(f"UNWIND $rows AS r CREATE (n:{label}) SET n = r", {"rows": plain[i:i + BATCH]})
        for i in range(0, len(vec), 100):
            g.query(f"UNWIND $rows AS r MATCH (n:{label} {{id: r.id}}) SET n.embedding = vecf32(r.e)",
                    {"rows": vec[i:i + 100]})
        counts[label] = len(rows)
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for e in ds.edges:
        groups[(e.type, e.src_label, e.dst_label)].append({"s": e.src_id, "d": e.dst_id, "p": e.props})
    for (etype, sl, dl), rows in groups.items():
        for i in range(0, len(rows), BATCH):
            g.query(f"UNWIND $rows AS r MATCH (a:{sl} {{id: r.s}}), (b:{dl} {{id: r.d}}) "
                    f"CREATE (a)-[e:{etype}]->(b) SET e = r.p", {"rows": rows[i:i + BATCH]})
    counts["_edges"] = len(ds.edges)
    return counts


def ensure_seeded(store: GraphStore | None = None) -> list[str]:
    """Load any configured tenant whose graph does not exist yet (used by the container entrypoint)."""
    store = store or get_store()
    loaded = []
    for tenant in get_settings().tenants:
        if not store.exists(tenant):
            load_dataset(store, get_dataset(tenant), reset=False)
            loaded.append(tenant)
    return loaded


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenants", default=",".join(get_settings().tenants))
    ap.add_argument("--no-reset", action="store_true")
    args = ap.parse_args()
    store = get_store()
    for tenant in [t for t in args.tenants.split(",") if t]:
        t0 = time.time()
        counts = load_dataset(store, get_dataset(tenant), reset=not args.no_reset)
        print(f"[{tenant}] loaded in {time.time() - t0:.1f}s: {counts}")


if __name__ == "__main__":
    main()
