"""Workspaces: user-submitted repositories, each in its own tenant graph (``t_repo_<id>``).

A registry file keeps metadata; graphs and files are deleted after a TTL and when too many accumulate.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import DATA_DIR, get_settings
from .graph import get_store
from .ingest.limits import INGESTS_PER_HOUR, MAX_WORKSPACES, WORKSPACE_TTL_S

WS_DIR = DATA_DIR / "workspaces"
_LOCK = threading.RLock()
_REG: dict[str, dict] = {}
_HITS: dict[str, list[float]] = {}


@dataclass
class Workspace:
    id: str
    tenant: str
    label: str
    source: str                               # "github" | "upload" | "bundle"
    created: float
    status: str = "queued"                    # queued | running | ready | error
    stage: str = "queued"
    pct: int = 0
    message: str = ""
    error: str | None = None
    now: int = 0
    mode: str = "code"
    url: str = ""
    stats: dict = field(default_factory=dict)
    byo_db: bool = False                      # graph lives in the user's own FalkorDB
    db_host: str = ""                         # host:port only, never a password

    def public(self) -> dict:
        d = asdict(self)
        d["expires_in_s"] = max(0, int(self.created + WORKSPACE_TTL_S - time.time()))
        return d


def _path() -> Path:
    WS_DIR.mkdir(parents=True, exist_ok=True)
    return WS_DIR / "registry.json"


_MTIME = 0.0


def _refresh() -> None:
    """Re-read the registry file when another process (a second worker, a CLI) changed it, so state never goes stale."""
    global _MTIME
    p = _path()
    try:
        m = p.stat().st_mtime if p.exists() else 0.0
    except OSError:
        return
    if m != _MTIME:
        try:
            data = json.loads(p.read_text()) if p.exists() else {}
        except (OSError, ValueError):
            return
        _REG.clear()
        _REG.update(data)
        _MTIME = m


def _save() -> None:
    """Atomic write (temp file + rename) so a concurrent reader never sees a half-written registry."""
    global _MTIME
    p = _path()
    tmp = p.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(_REG))
    tmp.replace(p)
    _MTIME = p.stat().st_mtime


_refresh()


def workspace_dir(wid: str) -> Path:
    d = WS_DIR / wid
    d.mkdir(parents=True, exist_ok=True)
    return d


def create(label: str, source: str, url: str = "") -> Workspace:
    with _LOCK:
        _refresh()
        cleanup()
        wid = uuid.uuid4().hex[:8]
        from .byo_db import current_target
        t = current_target()
        ws = Workspace(wid, f"repo_{wid}", label[:80], source, time.time(), url=url, byo_db=bool(t), db_host=t.label if t else "")
        _REG[wid] = asdict(ws)
        _save()
        return ws


def update(wid: str, **kw) -> None:
    with _LOCK:
        _refresh()
        if wid in _REG:
            _REG[wid].update(kw)
            _save()


def get(wid: str) -> Workspace | None:
    with _LOCK:
        _refresh()
        d = _REG.get(wid)
        return Workspace(**d) if d else None


def by_tenant(tenant: str) -> Workspace | None:
    return get(tenant[len("repo_"):]) if tenant.startswith("repo_") else None


def list_all() -> list[Workspace]:
    with _LOCK:
        _refresh()
        return sorted((Workspace(**d) for d in _REG.values()), key=lambda w: -w.created)


def delete(wid: str) -> bool:
    with _LOCK:
        _refresh()
        ws = _REG.pop(wid, None)
        _save()
    if not ws:
        return False
    # a graph in the user's own database is only touched when they are connected (header present); TTL cleanup leaves it alone
    from .graph import scoped_store
    if not ws.get("byo_db") or scoped_store() is not None:
        try:
            get_store().drop(ws["tenant"])
        except Exception:
            pass
    shutil.rmtree(WS_DIR / wid, ignore_errors=True)
    return True


def cleanup() -> int:
    """Drop expired workspaces and the oldest ones beyond the cap."""
    n, now = 0, time.time()
    with _LOCK:
        items = sorted(_REG.values(), key=lambda d: d["created"])
        stale = [d["id"] for d in items if now - d["created"] > WORKSPACE_TTL_S]
        over = [d["id"] for d in items[: max(0, len(items) - MAX_WORKSPACES + 1)]]
    for wid in dict.fromkeys(stale + over):
        n += delete(wid)
    return n


def is_workspace(tenant: str) -> bool:
    with _LOCK:
        _refresh()
    return tenant.startswith("repo_") and tenant[len("repo_"):] in _REG


def known_tenant(tenant: str) -> bool:
    return tenant in get_settings().tenants or is_workspace(tenant)


def tenant_now(tenant: str) -> int:
    from .config import NOW
    ws = by_tenant(tenant)
    return ws.now if ws and ws.now else NOW


def allow_ingest(client: str) -> bool:
    """Sliding-window rate limit per client address."""
    now = time.time()
    with _LOCK:
        hits = [t for t in _HITS.get(client, []) if now - t < 3600]
        if len(hits) >= INGESTS_PER_HOUR:
            _HITS[client] = hits
            return False
        hits.append(now)
        _HITS[client] = hits
        return True
