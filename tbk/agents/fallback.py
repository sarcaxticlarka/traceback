"""What the product can do when the graph is switched off: local document retrieval only.

Used by the "kill the graph" demo (hackathon rule 3). It has no relationships, no validity windows and no edge
ids, so it cannot scope changes by dependency, cannot hand off through shared state and cannot produce a single
verifiable claim. Documents come from the local corpus file, not from FalkorDB.
"""
from __future__ import annotations

import uuid

from ..baseline import DocIndex
from ..seed.generate import get_dataset
from .types import AgentReport, RunReport


def run_without_graph(tenant: str, alert_id: str) -> RunReport:
    ds = get_dataset(tenant)
    alert = next((a for a in ds.nodes["Alert"] if a["id"] == alert_id), None)
    text = alert["summary"] if alert else alert_id
    hits = DocIndex.for_tenant(tenant).search(text, k=3)
    claims = [{"text": f"document {h.id} ({h.kind}) looks related", "status": "withheld",
               "reason": "no graph evidence available (graph disabled)", "edge_ids": [], "node_ids": []} for h in hits]
    head = ("Graph layer is OFF. Without relationships the agent cannot tell which deploys sit in the alert's dependency "
            "scope, who owns the culprit, or what else is affected. Closest documents only: "
            + ", ".join(h.id for h in hits) + ".")
    ag = AgentReport("investigator", verification={"grounded_pct": 0.0, "n_claims": len(claims), "claims": claims},
                     headline=head)
    return RunReport(run_id=uuid.uuid4().hex[:10], tenant=tenant, alert_id=alert_id, incident_id=None,
                     graph_enabled=False, planner="docs-only", agents=[ag], headline=head, grounded_pct=0.0,
                     n_claims=len(claims), n_withheld=len(claims))
