import { useEffect, useState } from 'react'
import { api } from '../api'
import { GroupedBars, Pill } from './Common'

export default function ProofView() {
  const [ev, setEv] = useState(null)
  const [iso, setIso] = useState(null)
  const [bench, setBench] = useState(null)
  const [tools, setTools] = useState([])
  const [real, setReal] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.evalResults().then(setEv).catch(() => {})
    api.bench().then(setBench).catch(() => {})
    api.tools().then(setTools).catch(() => {})
    api.benchReal().then(setReal).catch(() => {})
  }, [])

  const runIso = async () => { setBusy(true); try { setIso(await api.isolation()) } finally { setBusy(false) } }
  const order = ['1-hop', '2-hop', 'temporal', '3+-hop']
  const groups = ev ? order.filter((b) => ev.aggregate[b]).map((b) => ({ label: `${b} (n=${ev.aggregate[b].n})`, a: ev.aggregate[b].graph_exact, b: ev.aggregate[b].docs_exact })) : []

  return (
    <div>
      <div className="card">
        <h3>Does the graph earn its place? · same questions, same documents, same embedder</h3>
        {ev ? <>
          <GroupedBars groups={groups} aName="Graph agent (FalkorDB)" bName="Docs-only retrieval" />
          <p className="muted" style={{ marginTop: 10 }}>Exact-match accuracy by how many relationships the answer needs. Ground truth is computed from the generator's own model, not read back from FalkorDB.
            Overall: graph <b>{Math.round(ev.aggregate.all.graph_exact * 100)}%</b> vs docs-only <b>{Math.round(ev.aggregate.all.docs_exact * 100)}%</b>, graph answers {ev.aggregate.all.graph_grounded_pct}% grounded.</p>
          <div className="scroll" style={{ maxHeight: 260 }}><table><thead><tr><th>Question type</th><th>Graph</th><th>Docs-only</th></tr></thead><tbody>
            {Object.entries(ev.by_intent).sort().map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.graph}/{v.n}</td><td>{v.docs}/{v.n}</td></tr>)}
          </tbody></table></div>
        </> : <div className="empty">Evaluation not available.</div>}
      </div>

      {real.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <h3>Real public repositories · {real.reduce((n, r) => n + (r.aggregate?.all?.n || 0), 0)} auto-generated questions</h3>
          <div className="scroll" style={{ maxHeight: 'none' }}><table><thead><tr><th>Repository</th><th className="num">Files</th><th className="num">Modules</th><th className="num">Module deps</th><th className="num">Commits</th><th className="num">Questions</th><th className="num">Graph</th><th className="num">Docs-only</th><th className="num">Grounded</th><th className="num">Ingest</th></tr></thead><tbody>
            {real.filter((r) => r.aggregate).map((r) => <tr key={r.repo}><td><a href={`https://github.com/${r.repo}`} target="_blank" rel="noreferrer">{r.repo}</a></td>
              <td className="num">{r.stats.files}</td><td className="num">{r.stats.modules}</td><td className="num">{r.stats.module_deps}</td><td className="num">{r.stats.commits}</td>
              <td className="num">{r.aggregate.all.n}</td><td className="num">{Math.round(r.aggregate.all.graph_exact * 100)}%</td><td className="num">{Math.round(r.aggregate.all.docs_exact * 100)}%</td>
              <td className="num">{Math.round(r.aggregate.all.grounded_pct)}%</td><td className="num">{r.stats.ingest_s}s</td></tr>)}
          </tbody></table></div>
          <p className="muted" style={{ marginTop: 8, fontSize: 12.5 }}>Each repo is cloned fresh, analysed, loaded into its own graph and quizzed. Reproduce: <code>python scripts/bench_real_repos.py</code>. Ground truth comes from the static analyser and the raw commit list, not from the database under test.</p>
        </div>
      )}

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h3 style={{ margin: 0 }}>Tenant isolation · canary test</h3>
            <button className="btn" onClick={runIso} disabled={busy}>{busy ? 'Running…' : 'Run test'}</button>
          </div>
          <p className="muted">Plants a person and a deploy in tenant <b>helix</b>, then proves <b>orbit</b> (same service names) never sees them.</p>
          {iso?.checks.map((c) => <div className="check" key={c.name}><Pill kind={c.ok ? 'ok' : 'bad'}>{c.ok ? 'pass' : 'FAIL'}</Pill><div>{c.name}<div className="muted mono">{c.detail}</div></div></div>)}
        </div>
        <div className="card">
          <h3>Concurrency benchmark</h3>
          {bench ? <div className="kv">
            <span className="muted">{bench.crews.workers} full agent crews at once</span><span>{bench.crews.incidents_per_s} incidents/s · p50 {bench.crews.p50_ms} ms · p95 {bench.crews.p95_ms} ms · {bench.crews.fully_grounded_runs}/{bench.crews.workers} fully grounded · {bench.crews.errors} errors</span>
            <span className="muted">{bench.reads.ops} concurrent graph reads</span><span>{bench.reads.ops_per_s} ops/s · p95 {bench.reads.p95_ms} ms</span>
            <span className="muted">{bench.claim_race.contenders} workers racing for one task</span><span>{bench.claim_race.winners} winner {bench.claim_race.exactly_one ? '✓' : '✗'}</span>
          </div> : <div className="muted">Run <span className="mono">python -m tbk.bench</span>.</div>}
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <h3>The queries and algorithms the product depends on ({tools.length} tools, also served over MCP)</h3>
        <div className="scroll"><table><thead><tr><th>Tool</th><th>Cypher / algorithm</th><th>What it does</th></tr></thead><tbody>
          {tools.map((t) => <tr key={t.name}><td className="mono">{t.name}</td><td className="mono">{t.cypher_ref}</td><td className="muted">{t.description}</td></tr>)}
        </tbody></table></div>
      </div>
    </div>
  )
}
