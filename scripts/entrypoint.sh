#!/bin/sh
# Seed any missing tenant graphs (idempotent), precompute the evaluation, then serve API + console.
set -e
python - <<'PY'
import time
from tbk.graph import get_store
for _ in range(60):
    try:
        get_store().db.list_graphs(); break
    except Exception:
        time.sleep(1)
from tbk.seed.load import ensure_seeded
print("seeded:", ensure_seeded() or "already present")
PY
[ -f data/eval_results.json ] || python -m tbk.evalx.run >/dev/null
exec uvicorn tbk.api.app:app --host 0.0.0.0 --port "${PORT:-8765}"
