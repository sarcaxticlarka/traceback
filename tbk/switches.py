"""Per-request runtime switches (async/thread safe via contextvars).

``graph_enabled`` is the "kill the graph" switch: when False every FalkorDB access raises
``GraphDisabled`` so the demo can show the product failing without its graph (hackathon rule 3).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_graph_enabled: ContextVar[bool] = ContextVar("tbk_graph_enabled", default=True)


class GraphDisabled(RuntimeError):
    """Raised when the graph layer is switched off."""


def graph_enabled() -> bool:
    return _graph_enabled.get()


@contextmanager
def graph_switch(enabled: bool):
    token = _graph_enabled.set(enabled)
    try:
        yield
    finally:
        _graph_enabled.reset(token)
