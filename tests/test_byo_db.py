"""Bring your own FalkorDB: validation, isolation between databases, and the data really lands in the user's server.

The end-to-end tests need a second FalkorDB on localhost:6391 (``docker run -p 6391:6379 falkordb/falkordb``) and skip without it.
"""
import base64
import json
import socket
import time

import pytest
from fastapi.testclient import TestClient

from tbk import byo_db, workspaces as W
from tbk.api.app import app
from tbk.graph import GraphStore, get_store, scoped_store, use_store
from tests.test_ingest import FILES, _zip


def hdr(host="127.0.0.1", port=6391, password="", ssl=False):
    return {"X-FalkorDB": base64.b64encode(json.dumps({"host": host, "port": port, "password": password, "ssl": ssl}).encode()).decode()}


def second_db_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 6391), timeout=1).close()
        return True
    except OSError:
        return False


needs_db = pytest.mark.skipif(not second_db_up(), reason="second FalkorDB on :6391 not running")


# ------------------------------------------------------------------------------------ validation and the SSRF guard
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.1.2.3", "192.168.0.5", "172.16.0.9", "169.254.169.254", "0.0.0.0", "[::1]"])
def test_private_loopback_and_metadata_addresses_are_blocked_by_default(host):
    with pytest.raises(ValueError, match="private or reserved|resolve"):
        byo_db.store_for(byo_db.DbTarget(host, 6379))


def test_public_address_passes_validation_without_connecting():
    assert byo_db.resolve_public(byo_db.DbTarget("8.8.8.8", 6379)) == "8.8.8.8"          # a literal public IP, nothing is contacted


def test_self_hosting_can_allow_private_targets(monkeypatch):
    monkeypatch.setenv("TBK_ALLOW_PRIVATE_DB", "1")
    assert byo_db.resolve_public(byo_db.DbTarget("127.0.0.1", 6391)) == "127.0.0.1"


@pytest.mark.parametrize("bad", ["", "not-base64!!", base64.b64encode(b"[]").decode(), base64.b64encode(json.dumps({"host": "a b"}).encode()).decode(),
                                 base64.b64encode(json.dumps({"host": "x.com", "port": 99999}).encode()).decode(),
                                 base64.b64encode(json.dumps({"host": "x.com;rm -rf /"}).encode()).decode()])
def test_malformed_headers_are_rejected(bad):
    if bad == "":
        assert byo_db.parse_header(bad) is None
    else:
        with pytest.raises(ValueError):
            byo_db.parse_header(bad)


def test_api_refuses_a_blocked_target_with_a_clear_message():
    r = TestClient(app).post("/api/db/test", headers=hdr("169.254.169.254", 6379))
    assert r.status_code == 400 and "not allowed" in r.json()["detail"]


def test_password_is_scrubbed_from_connection_errors(monkeypatch):
    monkeypatch.setenv("TBK_ALLOW_PRIVATE_DB", "1")
    t = byo_db.DbTarget("127.0.0.1", 6391, password="s3cret-pass")
    class Boom:
        class db:
            @staticmethod
            def list_graphs():
                raise RuntimeError("AUTH failed for password s3cret-pass")
    out = byo_db.test_connection(Boom, t)
    assert out["ok"] is False and "s3cret-pass" not in json.dumps(out) and out["kind"] == "auth"


def test_scoped_store_is_request_local():
    other = GraphStore()
    assert scoped_store() is None
    with use_store(other):
        assert get_store() is other
    assert scoped_store() is None and get_store() is not other


# ------------------------------------------------------------------------------------ end to end against a second database
@needs_db
def test_connection_test_endpoint(monkeypatch):
    monkeypatch.setenv("TBK_ALLOW_PRIVATE_DB", "1")
    r = TestClient(app).post("/api/db/test", headers=hdr()).json()
    assert r["ok"] is True and r["host"] == "127.0.0.1:6391" and "password" not in json.dumps(r)


@needs_db
def test_analysis_lands_in_the_users_database_and_never_in_ours(monkeypatch):
    monkeypatch.setenv("TBK_ALLOW_PRIVATE_DB", "1")
    c = TestClient(app)
    z = _zip({f"proj/{k}": v.encode() for k, v in FILES.items() if not k.startswith(".")})
    w = c.post("/api/workspaces/upload", files={"file": ("p.zip", z)}, data={"label": "mine"}, headers=hdr()).json()
    assert w["byo_db"] is True and w["db_host"] == "127.0.0.1:6391" and "password" not in json.dumps(w)
    for _ in range(80):
        d = c.get(f"/api/workspaces/{w['id']}").json()
        if d["status"] in ("ready", "error"):
            break
        time.sleep(0.2)
    assert d["status"] == "ready", d
    ours, theirs = GraphStore(), byo_db.store_for(byo_db.DbTarget("127.0.0.1", 6391))
    name = f"t_{w['tenant']}"
    assert name in theirs.db.list_graphs() and name not in ours.db.list_graphs()          # the data is in *their* server only

    # works through their connection ...
    out = c.post("/api/tool", json={"tenant": d["tenant"], "tool": "blast_radius", "args": {"service": "app/core/"}}, headers=hdr()).json()
    assert out["verification"]["grounded_pct"] == 100.0
    # ... and is refused (not silently created empty) without it
    r = c.post("/api/tool", json={"tenant": d["tenant"], "tool": "blast_radius", "args": {"service": "app/core/"}})
    assert r.status_code == 409 and "your own FalkorDB" in r.json()["detail"]
    assert name not in GraphStore().db.list_graphs()                                      # still nothing created on our side
    # a shared dataset must not be queried through the user's connection either
    assert c.post("/api/tool", json={"tenant": "helix", "tool": "blast_radius", "args": {"service": "auth-service"}}, headers=hdr()).status_code == 409

    # TTL cleanup (no connection) removes our record but cannot and must not reach into their database
    W.delete(w["id"])
    assert name in theirs.db.list_graphs()
    theirs.db.select_graph(name).delete()


@needs_db
def test_delete_with_connection_removes_the_graph_from_their_database(monkeypatch):
    monkeypatch.setenv("TBK_ALLOW_PRIVATE_DB", "1")
    c = TestClient(app)
    bundle = {"name": "b", "services": [{"name": "a-api"}, {"name": "b-api"}], "dependencies": [{"from": "a-api", "to": "b-api"}]}
    w = c.post("/api/workspaces/bundle", json=bundle, headers=hdr()).json()
    for _ in range(60):
        d = c.get(f"/api/workspaces/{w['id']}").json()
        if d["status"] in ("ready", "error"):
            break
        time.sleep(0.2)
    theirs = byo_db.store_for(byo_db.DbTarget("127.0.0.1", 6391))
    assert f"t_{w['tenant']}" in theirs.db.list_graphs()
    assert c.delete(f"/api/workspaces/{w['id']}", headers=hdr()).status_code == 200
    assert f"t_{w['tenant']}" not in theirs.db.list_graphs()
