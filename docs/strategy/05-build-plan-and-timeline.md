# 05 — Build Plan & Timeline

Deadline: **Oct 18, 11:59 PM IST.** The plan counts in **hours from now (H0)** so it works whatever time you start. Assume ≈30 working hours available, with sleep. If you have fewer, use the compressed plan at the bottom.

**Hard freeze:** no new features in the last 6 hours. **Submit** at least 3 hours before 11:59 PM IST.

## Team split (if you have 2–4 people; solo version below)

| Role | Owns |
|---|---|
| A. Graph/Backend | schema, seed generator, tools.py, verifier, tenant routing |
| B. Agents/LLM | agent loop, MCP server, memory writers, eval harness |
| C. Frontend/Demo | console, subgraph replay, grounded badge, kill switch, deploy |
| D. Docs/Video/Blog | README, QUERIES.md, video, blog, submission form |

Solo: do A → B → C in that order; D tasks are scheduled into fixed slots below. You can't skip D: rules 10 and the blog prize live there.

## Phases

### H0–H1: Foundations (do all of it before writing features)
- [ ] Register on the site; join the FalkorDB Discord (ask graph-model questions early).
- [ ] Fresh public GitHub repo `traceback`; first commit now (timestamp after start; rule 8).
- [ ] `docker run -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest`; open Browser on :3000.
- [ ] **The spike** (doc 02, UNVERIFIED table): confirm algorithm procedure names, `shortestPath`, variable-length performance, vector index, concurrent writes. Write results into `NOTES.md`.
- [ ] Deploy a hello-world (FastAPI `/health` hitting FalkorDB) to the chosen host. Prove the deploy path now, not at H28.
- [ ] Create a `AI_USAGE.md` and start logging what AI wrote/assisted from commit one (rule 11).

### H1–H5: Data and graph
- [ ] `seed/generate.py` (deterministic seed): two tenants, hub-skewed dependency graph, planted facts, ownership/time validity, docs.
- [ ] Load script with `MERGE` + indexes. Both tenants loaded in < 1 minute.
- [ ] Query Q1–Q3, Q7, Q9 working in Browser and returning the planted answers.
- [ ] Generate `eval/questions.json` with ground truth *from the generator* (not by hand).

**Checkpoint A (H5):** you can answer five hand-picked multi-hop questions by running Cypher by hand and they match ground truth. If not, fix before touching agents.

### H5–H11: Tools + verifier + agent loop
- [ ] `tools.py`: each named query wrapped as a function with a JSON schema; returns rows **plus edge ids and node ids** used (this is what makes verification possible; design returns around it).
- [ ] `verifier.py` rules 1–5 from doc 04, with unit tests (`tests/test_verifier.py`: fabricated edge id → rejected; expired edge → rejected; extra entity in text → rejected).
- [ ] Agent loop (Investigator first): tool-use loop, max steps, structured claims output.
- [ ] MCP server exposing the same `tools.py` (thin adapter). Test with an MCP client.

**Checkpoint B (H11):** from the CLI, `investigate ALERT-123` produces verified claims with edge ids for a planted incident, correct per ground truth.

### H11–H17: Memory + multi-agent + algorithms
- [ ] Episode/ToolCall logging on every run.
- [ ] Facts with `SUPPORTED_BY`; `SUPERSEDES` on contradiction; as-of queries.
- [ ] Runbook ranking (Q5) + outcome update (Q6); a simulator that replays 40 incidents so the success-rate curve exists.
- [ ] Task nodes, claim query (Q10), three agents hand off through the graph. Scheduler loop.
- [ ] PageRank + betweenness + WCC as tools; risk score function.

**Checkpoint C (H17):** one alert flows Triage → Investigator → Remediator purely via graph state, ends with an Action and an updated Runbook stat, visible in Browser.

### H17–H23: Frontend + proof of necessity
- [ ] Incident console: alert feed, run view, claim list with grounded %, click claim → highlight edges in the subgraph.
- [ ] Subgraph replay animation (traversal order).
- [ ] Tenant dropdown; kill-graph toggle.
- [ ] `eval/`: vector baseline, grader, 3 runs, chart → `eval/results.md`.
- [ ] `tests/test_isolation.py` green. `bench/bench_concurrency.py` table captured.
- [ ] Deploy frontend + API for real data; check it from a phone/another network.

**Checkpoint D (H23):** a stranger can open the live URL and run the demo scenario without you.

### H23–H27: Hardening + docs
- [ ] README per doc 06 template; QUERIES.md complete with each query and what it's used for.
- [ ] Graph data model diagram (export from Browser or draw.io) embedded in README.
- [ ] Failure handling: LLM timeouts, empty results, FalkorDB reconnect. Fixture mode (pre-recorded LLM responses) so the demo can't die to a rate limit.
- [ ] **Freeze features.**

### H27–H30: Video, blog, submit
- [ ] Record demo (script in doc 06). Two takes max. Upload (YouTube unlisted/public).
- [ ] Write and publish blog post (Dev.to / Hashnode / Medium); link in README.
- [ ] Submit on WeMakeDevs form: repo, README, video, deployment URL, tracks (all three named), project info. Submit early. Re-open the submission afterward and verify links work in an incognito window.

## Cut lines

| Level | Contents | Fallback if time is short |
|---|---|---|
| **MVP (survival)** | Seed data, Q1–Q3/Q7, tools, verifier with Grounded %, Investigator agent, subgraph view, deployed, video, README with schema + queries | Must ship |
| **STRONG (win-probable)** | + 3-layer memory with runbook learning, handoffs via Tasks, A/B eval chart, kill switch, isolation test | Ship all of this if possible |
| **STRETCH** | + bitemporal polish, approval-gated actions, concurrency benchmark charts, public GitHub data, Graphiti comparison | Only after Checkpoint D |

## Compressed plan (≤ 14 hours left)

Drop: Remediator approval gating, bitemporal as-of UI (keep `valid_*` filter in Q1/Q3), concurrency benchmark (keep isolation test), public data, MCP (keep tool schema; add MCP only if 1h is spare, since track 1 names it).
Keep: seed data, tools, verifier + Grounded %, Investigator, runbook ranking with a small simulated learning curve, subgraph view, A/B eval with 15 questions, deployed, video, README, blog (even a short one).
Target: single track primary (Track 1), other two listed as "partial" honestly or not at all. Do not claim features you didn't ship; judges will probe (rule 12).

## Test plan

| Test | Proves |
|---|---|
| `test_verifier.py` | no path, no claim is real |
| `test_isolation.py` | tenant separation; overlapping names don't leak |
| `eval/` by hop bucket | graph advantage is measurable |
| kill-switch run | graph is necessary (rule 3) |
| `bench_concurrency.py` | high-concurrency claim (T2) |
| reseed from scratch on a clean machine | README setup works (rule 10) |
| incognito check of every submitted link | nothing is private/404 |

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Variable-length queries slow at demo time | Med | Cap depth, index `id`, pre-warm, test early in the spike |
| LLM rate limit / outage during judging | Med | Fixture mode; cache tool results; small model for phrasing |
| Hosting FalkorDB for the live demo | Med | Decide at H1; FalkorDB Cloud endpoint or a single container host; verify it persists data across restarts (volume) |
| Algorithm procedure names differ from assumed | High | The H1 spike; centralise in `tools.py` |
| Scope creep | High | Cut lines above; freeze at H27 |
| "Entirely AI-generated" rejection (rule 13) | Med | You write schema, verifier, eval design; keep `AI_USAGE.md` honest and specific; be able to narrate every query |
| Sleep deprivation bugs | High | Sleep a block between H17 and H23 if the schedule allows; don't deploy at 4 AM |
| Eval embarrasses the graph | Low–Med | Still report honestly; vary data to include genuinely multi-hop planted questions; this is by design |
