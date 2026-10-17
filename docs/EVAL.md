# Evaluation: graph agent vs docs-only baseline

Tenants: helix, orbit. Same questions, same documents, same embedder. Ground truth is computed from the generator's model, not from FalkorDB.

| Bucket | n | Graph exact | Docs-only exact | Graph F1 | Docs-only F1 | Graph grounded % |
|---|---|---|---|---|---|---|
| 1-hop | 28 | 100% | 89% | 1.00 | 0.94 | 100.0 |
| 2-hop | 14 | 100% | 29% | 1.00 | 0.44 | 100.0 |
| temporal | 14 | 100% | 86% | 1.00 | 0.86 | 100.0 |
| 3+-hop | 40 | 100% | 10% | 1.00 | 0.33 | 100.0 |
| all | 96 | 100% | 47% | 1.00 | 0.60 | 100.0 |

## By question type (exact match, correct / total)

| Intent | Graph | Docs-only |
|---|---|---|
| blast_all | 8/8 | 0/8 |
| contact_asof | 6/6 | 6/6 |
| contact_now | 6/6 | 6/6 |
| decision_chain | 6/6 | 2/6 |
| decision_current | 6/6 | 0/6 |
| dependents_2hop | 8/8 | 4/8 |
| direct_deps | 8/8 | 8/8 |
| orphaned | 2/2 | 0/2 |
| owner_asof | 8/8 | 6/8 |
| owner_members | 6/6 | 0/6 |
| owner_now | 8/8 | 7/8 |
| page_for_alert | 10/10 | 0/10 |
| teams_impacted | 8/8 | 2/8 |
| who_resolved | 6/6 | 4/6 |
