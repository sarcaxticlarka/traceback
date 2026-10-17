"""The destructive reseed endpoint must not be open on a public host."""
from fastapi.testclient import TestClient

from tbk.api.app import app


def test_reseed_closed_without_token(monkeypatch):
    monkeypatch.delenv("TBK_ADMIN_TOKEN", raising=False)
    assert TestClient(app).post("/api/admin/reseed?tenant=helix").status_code == 403    # not loopback


def test_reseed_needs_the_right_token(monkeypatch):
    monkeypatch.setenv("TBK_ADMIN_TOKEN", "s3cret")
    c = TestClient(app)
    assert c.post("/api/admin/reseed?tenant=helix").status_code == 403
    assert c.post("/api/admin/reseed?tenant=helix", headers={"x-admin-token": "wrong"}).status_code == 403
