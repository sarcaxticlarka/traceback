"""FalkorDB access with strict tenant routing.

``GraphStore.graph(tenant)`` is the only way the rest of the code obtains a graph handle,
so a tool that receives ``tenant="orbit"`` has no way to read ``t_helix``. Tenant slugs are
validated before they become part of a graph name.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

from falkordb import FalkorDB
from redis.exceptions import ResponseError

from .config import Settings, get_settings
from .switches import GraphDisabled, graph_enabled

_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
# FalkorDB queues at most MAX_QUEUED_QUERIES (default 25) per server; admission control keeps one process below that
# and retries with backoff if several processes together still overflow it.
MAX_INFLIGHT = int(os.getenv("TBK_MAX_INFLIGHT", "16"))
RETRIES = 7


def graph_name(tenant: str) -> str:
    if not _SLUG.match(tenant):
        raise ValueError(f"invalid tenant slug: {tenant!r}")
    return f"t_{tenant}"


class GraphStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._db: FalkorDB | None = None
        self._lock = threading.Lock()
        self._gate = threading.BoundedSemaphore(MAX_INFLIGHT)

    @property
    def db(self) -> FalkorDB:
        if self._db is None:
            with self._lock:
                if self._db is None:
                    s = self.settings
                    self._db = FalkorDB(host=s.falkor_host, port=s.falkor_port, password=s.falkor_password)
        return self._db

    def graph(self, tenant: str):
        if not graph_enabled():
            raise GraphDisabled("graph layer is switched off")
        return self.db.select_graph(graph_name(tenant))

    def raw_graph(self, tenant: str):
        """Bypasses the kill switch; for seeding, tests and the control plane only."""
        return self.db.select_graph(graph_name(tenant))

    def exists(self, tenant: str) -> bool:
        return graph_name(tenant) in set(self.db.list_graphs())

    def drop(self, tenant: str) -> None:
        if self.exists(tenant):
            self.db.select_graph(graph_name(tenant)).delete()

    def query(self, tenant: str, cypher: str, params: dict | None = None, *, raw: bool = False) -> list[dict[str, Any]]:
        g = self.raw_graph(tenant) if raw else self.graph(tenant)
        res = self._run(g, cypher, params or {})
        names = [h[1] for h in res.header]
        return [dict(zip(names, row)) for row in res.result_set]

    def _run(self, g, cypher: str, params: dict):
        for attempt in range(RETRIES):
            with self._gate:
                try:
                    return g.query(cypher, params)
                except ResponseError as e:
                    if "Max pending queries" not in str(e) or attempt == RETRIES - 1:
                        raise
            time.sleep(0.01 * (2 ** attempt))               # back off outside the gate, then retry

    def explain(self, tenant: str, cypher: str) -> str:
        return str(self.raw_graph(tenant).explain(cypher))


_store: GraphStore | None = None


def get_store() -> GraphStore:
    global _store
    if _store is None:
        _store = GraphStore()
    return _store
