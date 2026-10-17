"""Bring your own FalkorDB: let a user keep their graph in a database *they* run (FalkorDB Cloud, a VM, their network).

The connection arrives per request in an ``X-FalkorDB`` header (base64 JSON: host, port, password, ssl). It lives in memory for
that request only, is never written to disk or logs, and is scrubbed from errors. Because the server connects to a host the user
names, targets are validated: on a public deployment private, loopback, link-local and metadata addresses are refused so the
feature cannot be used to probe our own network (set TBK_ALLOW_PRIVATE_DB=1 when self-hosting).
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import socket
import threading
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass, replace

from .config import get_settings
from .graph import GraphStore, scoped_store, use_store  # noqa: F401  (use_store re-exported for callers)

_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?$|^\[?[0-9a-fA-F:]+\]?$")
_target: ContextVar["DbTarget | None"] = ContextVar("tbk_byo_target", default=None)
_cache: "OrderedDict[tuple, GraphStore]" = OrderedDict()
_lock = threading.Lock()
MAX_CACHED = 16


def allow_private() -> bool:
    return os.getenv("TBK_ALLOW_PRIVATE_DB", "") == "1"


@dataclass(frozen=True)
class DbTarget:
    host: str
    port: int
    password: str = ""
    ssl: bool = False

    @property
    def label(self) -> str:                       # safe to show and store: no password
        return f"{self.host}:{self.port}"

    def scrub(self, text: str) -> str:
        return text.replace(self.password, "***") if self.password else text


def parse_header(value: str | None) -> DbTarget | None:
    if not value:
        return None
    try:
        d = json.loads(base64.b64decode(value).decode())
        host = str(d["host"]).strip()
        port = int(d.get("port") or 6379)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("invalid X-FalkorDB header") from None
    if not _HOST.match(host):
        raise ValueError("invalid host name")
    if not 1 <= port <= 65535:
        raise ValueError("invalid port")
    return DbTarget(host, port, str(d.get("password") or ""), bool(d.get("ssl")))


def resolve_public(target: DbTarget) -> str:
    """Resolve the host and make sure every address is publicly routable (unless self-hosting). Returns an IP to connect to."""
    try:
        infos = socket.getaddrinfo(target.host.strip("[]"), target.port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError(f"cannot resolve host {target.host!r}") from None
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not allow_private() and not ip.is_global:
            raise ValueError("that address is private or reserved and is not allowed on this server "
                             "(use a publicly reachable FalkorDB such as FalkorDB Cloud, or self-host TRACEBACK)")
        ips.append(str(ip))
    if not ips:
        raise ValueError("host did not resolve")
    return ips[0]


def store_for(target: DbTarget) -> GraphStore:
    """A cached GraphStore for the target (validated first). Passwords are only ever kept hashed in the cache key."""
    ip = resolve_public(target)
    key = (target.host, target.port, hashlib.sha256(target.password.encode()).hexdigest(), target.ssl)
    with _lock:
        st = _cache.get(key)
        if st is not None:
            _cache.move_to_end(key)
            return st
    # TLS needs the hostname for certificate checks; plain connections go straight to the validated IP
    settings = replace(get_settings(), falkor_host=target.host if target.ssl else ip, falkor_port=target.port,
                       falkor_password=target.password or None, falkor_ssl=target.ssl)
    st = GraphStore(settings)
    with _lock:
        _cache[key] = st
        while len(_cache) > MAX_CACHED:
            _cache.popitem(last=False)
    return st


def current_target() -> DbTarget | None:
    return _target.get()


def set_target(t: DbTarget | None):
    return _target.set(t)


def reset_target(token) -> None:
    _target.reset(token)


def active() -> bool:
    return _target.get() is not None and scoped_store() is not None


def test_connection(store: GraphStore, target: DbTarget) -> dict:
    import time
    t0 = time.perf_counter()
    try:
        graphs = store.db.list_graphs()
    except Exception as e:                        # redis errors can echo the password: scrub, never forward raw
        msg = target.scrub(str(e))[:200]
        kind = "auth" if "auth" in msg.lower() or "password" in msg.lower() else "network"
        return {"ok": False, "kind": kind, "error": msg}
    return {"ok": True, "graphs": len(graphs), "latency_ms": round((time.perf_counter() - t0) * 1000), "host": target.label,
            "tls": target.ssl}
