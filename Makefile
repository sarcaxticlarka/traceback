PY := .venv/bin/python

.PHONY: setup db seed test eval bench queries web api mcp up
setup:            ## python deps + console deps
	uv venv --python 3.12 .venv || python3 -m venv .venv
	uv pip install --python $(PY) -e ".[dev]" || $(PY) -m pip install -e ".[dev]"
	cd web && npm install
db:               ## FalkorDB on :6390 (Browser UI on :3010)
	docker run -d --name traceback-falkordb -p 6390:6379 -p 3010:3000 -v traceback_fdb:/var/lib/falkordb/data falkordb/falkordb:latest || docker start traceback-falkordb
seed:             ## (re)generate and load both tenants
	$(PY) -m tbk.seed.load
test:
	$(PY) -m pytest
eval:             ## graph vs docs-only, writes docs/EVAL.md
	$(PY) -m tbk.evalx.run
bench:            ## concurrency benchmark, writes docs/BENCH.md
	$(PY) -m tbk.bench --workers 50
queries:          ## regenerate QUERIES.md from source
	$(PY) scripts/gen_queries.py
web:              ## build the console into web/dist
	cd web && npm run build
api:              ## API + console on :8765
	$(PY) -m uvicorn tbk.api.app:app --port 8765
mcp:              ## MCP server over stdio
	$(PY) -m tbk.mcp_server
up:               ## everything in containers
	docker compose up --build
