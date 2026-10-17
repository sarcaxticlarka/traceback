from tbk.isolation import check_isolation


def test_tenant_isolation_canary():
    rep = check_isolation("helix", "orbit")
    failed = [c for c in rep["checks"] if not c["ok"]]
    assert rep["ok"], failed
    assert len(rep["checks"]) >= 5


def test_reverse_direction_too():
    assert check_isolation("orbit", "helix")["ok"]
