import pytest

from tbk.graph import get_store
from tbk.seed.generate import get_dataset
from tbk.seed.load import load_dataset
from tbk.tools import ToolContext


@pytest.fixture(scope="session", autouse=True)
def seeded():
    """Load both tenants once per test session (deterministic seed data)."""
    store = get_store()
    for t in ("helix", "orbit"):
        load_dataset(store, get_dataset(t), reset=True)
    return store


@pytest.fixture
def ds():
    return get_dataset("helix")


@pytest.fixture
def ctx(ds):
    return ToolContext("helix", ds.meta["live_alerts"][0]["ts"])
