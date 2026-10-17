# Using TRACEBACK on real data

TRACEBACK ships with a synthetic company so the demo always works, but the same graph, tools, agents and verifier run on
real data. There are three ways in today, and one in CI.

## 1. A public GitHub repository

Paste `https://github.com/owner/repo` in **Analyze your code** (or `python -m tbk.cli analyze <url>`).

What happens, in order:

| Stage | What it does | What ends up in the graph |
|---|---|---|
| Fetch | Shallow `git clone` (last 1,500 commits), HTTPS to github.com only, no submodules, no hooks, symlinks off, empty git environment, 150 s / 250 MB limits | nothing yet |
| Parse | Walks the tree, skips `node_modules`, build output, binaries. Python via `ast`; JS/TS, Go, Java/Kotlin, C/C++ via resolvers. Only imports that resolve to files inside the repo count | `Service` per directory-level module (depth chosen so there are ≤120), `DEPENDS_ON` with the import sites (`file:line → file`) |
| History | `git log --numstat`; bots skipped; identities merged by email (hashed away afterwards) | `Person`, commits as `Deploy`, `AUTHORED`, `DEPLOYED_TO` (lines changed) |
| Ownership | CODEOWNERS (last match wins); otherwise the top committer, labelled `top-committer` | `Team`, `OWNS` (with `basis` and the rule text), inferred `MEMBER_OF` |
| Docs | README / `docs/` / ADRs as documents with source URLs; "Supersedes ADR n" becomes an edge | `Doc`, `Source`, `Decision`, `SUPERSEDES` |
| Load | Bulk load into its own graph `t_repo_<id>`, vector-index the documents | everything above |

Then you get: dependency map, hotspots (90-day churn × fan-in), bus factor, PageRank criticality, betweenness
chokepoints, change impact for any commit, Q&A, investigations, and a reproducible benchmark of your repository.

**Where the numbers come from:** every statement links to graph edges; click *Why* on any claim to see each edge's basis:
the import lines, the CODEOWNERS rule, or the git history.

## 2. A folder or zip from your machine

The browser zips only source and docs (skips `node_modules`, build output, binaries, files over 400 KB, `.git`) and uploads
one file. `.git` is deliberately never read from uploads, so you get structure, dependencies, docs and ownership from
CODEOWNERS, but not commit-based owners/experts/churn. Limit 100 MB.

## 3. Production data: the JSON bundle

For a real service catalogue, export to the bundle format and upload it in the *JSON bundle* tab (or
`POST /api/workspaces/bundle`):

```json
{
  "name": "acme-prod",
  "services":     [{"name": "checkout-api", "tier": 1, "owner": "payments"}],
  "dependencies": [{"from": "checkout-api", "to": "payments-api"}],
  "teams":        [{"name": "payments", "members": ["Ana Ruiz"]}],
  "deploys":      [{"service": "payments-api", "sha": "a1b2c3d", "author": "Ana Ruiz", "ts": 1760000000, "summary": "..."}],
  "alerts":       [{"service": "checkout-api", "signal": "high-latency", "ts": 1760003600}]
}
```

Typical mapping (you write a small exporter; live connectors are the natural next step):

| Your system | Bundle field |
|---|---|
| Backstage / OpsLevel / Cortex catalogue | `services`, `owner`, `teams` |
| Service map, OpenTelemetry traces, Istio/Linkerd topology | `dependencies` |
| GitHub Deployments, Argo CD, Spinnaker, your CD tool | `deploys` |
| PagerDuty / Opsgenie / Alertmanager | `alerts` |

Use hyphenated service names (e.g. `checkout-api`): plain English words as names can collide with ordinary words in claim text.
Everything downstream (investigation, blast radius, owners, who-knows, verification) works unchanged.

## 4. In CI: a verified comment on every PR

```yaml
# .github/workflows/pr-impact.yml
name: TRACEBACK impact
on: pull_request
jobs:
  impact:
    runs-on: ubuntu-latest
    services:
      falkordb:
        image: falkordb/falkordb:latest
        ports: ["6390:6379"]
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e path/to/traceback     # or vendor it
      - id: impact
        run: |
          python -m tbk.cli impact . --base origin/${{ github.base_ref }} --head HEAD > impact.md
      - uses: marocchino/sticky-pull-request-comment@v2
        with: { path: impact.md }
```

The comment lists the modules the PR touches, how many modules depend on them, owners, suggested reviewers,
risk factors, and a collapsed list of verified evidence.

## Keeping the data on your side

| You want | Do this |
|---|---|
| Nothing to leave your network | Self-host: `docker compose up` (needs only an optional LLM provider and cloning public URLs) |
| Our server to analyse, but your database to hold the graph | **Data** button: your FalkorDB host/port/password/TLS. New analyses are written there; our DB never receives them. The server must reach it over the public internet (private/loopback/metadata addresses are blocked on a public server). |
| To not trust our results | **Evidence bundle** + `python -m tbk.cli verify bundle.json --show-sources` on your own machine; or **Audit with my key** for a second opinion from your own LLM |

## Privacy and retention (public demo)

- Public repos only through the URL path; uploads are analysed in memory-and-disk for the duration of ingestion, then the
  working tree is deleted. The *graph* (names, edges, commit subjects, doc text) is kept 12 hours or until you delete it.
- With *your own FalkorDB* the graph is stored there; our registry keeps only the workspace id, label, stats and `host:port` (never the password). Deleting while connected drops the graph from your database; automatic expiry removes only our record.
- Each workspace is an unguessable id and its own graph; the server never lists workspaces to other browsers.
- LLM keys you supply are sent per request, used once, never stored or logged server-side.
- Run it yourself (`docker compose up`) if your code can't leave your network: nothing needs the internet except an
  optional LLM provider and cloning public URLs.

## What it cannot see

Dynamic imports, reflection, build-system or runtime-only dependencies; cross-language calls; private repositories
(by design on the public demo); anything outside the last 1,500 commits. Ownership without CODEOWNERS is an
inference and is labelled as one.
