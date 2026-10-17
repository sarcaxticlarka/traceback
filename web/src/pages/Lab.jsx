import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { useApp } from '../lib/ctx'
import { sampleQuestions } from '../lib/samples'
import SourceForm from '../components/SourceForm'
import GraphView from '../components/GraphView'
import AskView from '../components/AskView'
import EvidenceDrawer from '../components/EvidenceDrawer'
import ReportMenu from '../components/ReportMenu'
import AuditButton from '../components/AuditButton'
import { repoMarkdown, repoReport } from '../lib/report'
import Investigate from './Investigate'
import Icon from '../components/ui/Icon'
import { Bar, Empty, GroundedBadge, GroupedBars, Pill, Spinner, Stat, fmtNum } from '../components/Common'

const STAGES = [['fetch', 'Fetch'], ['analyze', 'Parse imports'], ['history', 'Read history'], ['build', 'Build graph'], ['load', 'Load FalkorDB']]

function useTool(tenant, tool, args = {}, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: '' })
  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: '' }))
    api.tool(tenant, tool, args).then((d) => live && setState({ data: d, loading: false, error: '' })).catch((e) => live && setState({ data: null, loading: false, error: String(e) }))
    return () => { live = false }
  }, [tenant, tool, JSON.stringify(args), ...deps])
  return state
}

function Progress({ ws }) {
  const idx = Math.max(0, STAGES.findIndex(([k]) => k === ws.stage))
  return (
    <div className="card">
      <div className="row between"><h3 style={{ margin: 0 }}>Analysing {ws.label}</h3><Pill kind={ws.status === 'error' ? 'bad' : 'accent'}>{ws.status}</Pill></div>
      <div className="stepper" style={{ margin: '14px 0 10px' }}>
        {STAGES.map(([k, l], i) => (<span key={k} style={{ display: 'contents' }}>
          <span className={`s ${i < idx || ws.status === 'ready' ? 'done' : i === idx ? 'now' : ''}`}>
            {i < idx || ws.status === 'ready' ? <Icon name="check" size={14} /> : i === idx && ws.status !== 'error' ? <Spinner /> : <Icon name="chevron" size={12} />}{l}</span>
          {i < STAGES.length - 1 && <span className="sep" />}</span>))}
      </div>
      <div className="bar"><i style={{ width: `${ws.pct}%` }} /></div>
      <p className="muted" style={{ marginTop: 8 }}>{ws.error || ws.message}</p>
    </div>
  )
}

function ClaimRows({ claims, onEvidence }) {
  return claims.map((c, i) => (
    <div key={i} className="claim" onClick={() => onEvidence(c)}>
      <div>{c.text}</div>
      <div className="meta"><Pill kind={c.status === 'grounded' ? 'ok' : 'bad'}>{c.status}</Pill><span className="muted mono">{(c.edge_ids || []).length} edge(s)</span>
        <button className="btn quiet sm" style={{ marginLeft: 'auto' }}><Icon name="eye" size={13} /> Why</button></div>
    </div>
  ))
}

function ToolCard({ title, tenant, tool, args, onEvidence, hint }) {
  const { data, loading, error } = useTool(tenant, tool, args)
  const claims = data?.verification?.claims || []
  return (
    <div className="card">
      <div className="row between"><h3 style={{ margin: 0 }}>{title}</h3><span className="row" style={{ gap: 6 }}>{data?.verification && <GroundedBadge pct={data.verification.grounded_pct} n={data.verification.n_claims} />}{claims.length > 0 && <AuditButton tenant={tenant} claims={claims} label="Audit" />}</span></div>
      {hint && <p className="muted" style={{ fontSize: 12.5, margin: '6px 0 10px' }}>{hint}</p>}
      {loading ? <div className="row" style={{ marginTop: 10 }}><Spinner /> Querying the graph…</div> : error ? <div className="banner">{error}</div>
        : claims.length ? <div className="scroll" style={{ maxHeight: 380, marginTop: 8 }}><ClaimRows claims={claims} onEvidence={onEvidence} /></div> : <Empty icon="check">Nothing notable found.</Empty>}
    </div>
  )
}

/** Gather everything a repository report needs (verified tool results), then render HTML + Markdown. */
async function buildRepoReport(ws, extra = {}) {
  const t = (tool, args) => api.tool(ws.tenant, tool, args).catch(() => null)
  const [hotspots, bus, crit, choke, modules, benchmark] = await Promise.all([
    t('hotspots', { top: 10 }), t('bus_factor', { top: 10 }), t('criticality', { top: 8 }), t('single_points_of_failure', { top: 8 }),
    api.wsModules(ws.id).catch(() => []), api.wsBenchmarkCached(ws.id).catch(() => null)])
  const data = { hotspots, bus, crit, choke, modules, benchmark, ...extra }
  return { html: repoReport(ws, data), md: repoMarkdown(ws, data), name: `analysis-${ws.label}` }
}

function Overview({ ws, onEvidence, onDelete }) {
  const s = ws.stats
  const langs = Object.entries(s.languages || {})
  const maxL = Math.max(1, ...langs.map(([, n]) => n))
  const left = ws.expires_in_s
  return (
    <div className="stack">
      <div className="stat-grid">
        <Stat value={fmtNum(s.files)} label="source files" /><Stat value={fmtNum(s.loc)} label="lines of code" />
        <Stat value={fmtNum(s.modules)} label="modules" hint={`directory depth ${s.module_depth}`} /><Stat value={fmtNum(s.module_deps)} label="module dependencies" hint={`${s.file_imports} file-level imports`} />
        <Stat value={fmtNum(s.commits)} label="commits read" /><Stat value={fmtNum(s.authors)} label="contributors" />
        <Stat value={fmtNum(s.graph_nodes)} label="graph nodes" /><Stat value={fmtNum(s.graph_edges)} label="graph edges" />
      </div>
      <div className="grid2">
        <div className="stack">
          <ToolCard title="Where to look first: hotspots" tenant={ws.tenant} tool="hotspots" args={{ top: 3 }} onEvidence={onEvidence} hint="Lines changed in the last 90 days × direct dependents." />
          <ToolCard title="Knowledge in one head: bus factor" tenant={ws.tenant} tool="bus_factor" args={{ top: 3 }} onEvidence={onEvidence} hint="Modules where one person wrote ≥ 70% of at least 5 commits." />
        </div>
        <div className="stack">
          <div className="card"><h3>How this graph was built</h3>
            <div className="kv" style={{ fontSize: 13 }}>
              <span>Parsed</span><span>{fmtNum(s.files)} files → {fmtNum(s.file_imports)} internal imports → {fmtNum(s.module_deps)} module dependencies</span>
              <span>History</span><span>{s.history ? `${fmtNum(s.commits)} human commits (bots skipped), identities merged by email (never stored)` : 'none (uploads carry no git data)'}</span>
              <span>Ownership</span><span>{Object.entries(s.owners_from || {}).map(([k, n]) => `${n} via ${k}`).join(', ') || 'none derived'}{s.codeowners_path ? ` (${s.codeowners_path})` : ''}</span>
              <span>Docs</span><span>{s.docs} documents, {s.decisions} decision records</span>
              <span>Ingest</span><span>{s.ingest_s}s</span>
            </div>
            {langs.length > 0 && <div style={{ marginTop: 12 }}>{langs.map(([l, n]) => (<div className="mod-bar" key={l}><span>{l}</span><Bar value={n} max={maxL} /><span className="muted mono">{n}</span></div>))}</div>}
          </div>
          <div className="card row between">
            <span className="muted"><Icon name="clock" size={14} /> Deleted automatically in {Math.floor(left / 3600)}h {Math.floor((left % 3600) / 60)}m</span>
            <button className="btn danger sm" onClick={onDelete}><Icon name="trash" size={13} /> Delete now</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function MapTab({ ws, onEvidence }) {
  const [graph, setGraph] = useState(null)
  const [mods, setMods] = useState([])
  const [sel, setSel] = useState(null)
  useEffect(() => {
    Promise.all([api.serviceMap(ws.tenant), api.wsModules(ws.id)]).then(([g, m]) => {
      const by = new Map(m.map((x) => [x.id, x]))
      setMods(m)
      setGraph({ nodes: g.nodes.map((n) => ({ ...n, label: 'Service', dependents: by.get(n.id)?.dependents || 0 })), edges: g.edges })
    })
  }, [ws.id])
  const info = mods.find((m) => m.id === sel)
  return (
    <div className="grid2">
      <div className="card"><h3>Module dependency map · bigger = more modules depend on it</h3>
        {graph ? <GraphView nodes={graph.nodes} edges={graph.edges} sizeBy="dependents" labels="top" selected={sel} onNode={(n) => setSel(n.id === sel ? null : n.id)} height={560} /> : <div className="empty"><Spinner /></div>}</div>
      <div className="stack">
        {info ? (<>
          <div className="card"><h3>{info.name}</h3>
            <div className="kv" style={{ fontSize: 13 }}><span>Files / LOC</span><span>{info.files} / {fmtNum(info.loc)}</span><span>Depended on by</span><span>{info.dependents} modules</span>
              <span>Depends on</span><span>{info.dependencies} modules</span><span>Commits</span><span>{info.commits}</span><span>90-day churn</span><span>{fmtNum(info.churn)} lines</span>
              <span>Top author</span><span>{info.top_author || '—'} {info.share ? `(${Math.round(info.share * 100)}%)` : ''}</span></div></div>
          <ToolCard title="Blast radius" tenant={ws.tenant} tool="blast_radius" args={{ service: info.name, depth: 4 }} onEvidence={onEvidence} />
          <ToolCard title="Who knows it" tenant={ws.tenant} tool="top_contributors" args={{ service: info.name, top: 3 }} onEvidence={onEvidence} />
        </>) : <div className="card"><Empty icon="target">Click a module to see who depends on it, who owns it and who knows it.</Empty></div>}
      </div>
    </div>
  )
}

function impactMarkdown(row, claims) {
  const lines = [`### TRACEBACK impact: risk ${row.risk_score}/100`, '',
    `**Touches** ${row.touched.map((m) => '`' + m + '`').join(', ')}  ·  **${row.impacted_count} modules depend on this**  ·  **owners** ${row.owners.join(', ') || 'unknown'}`]
  if (row.reviewers.length) lines.push('', `**Suggested reviewers:** ${row.reviewers.join(', ')}`)
  row.risk_factors.forEach((f) => lines.push('', `- ⚠ ${f}`))
  lines.push('', `<details><summary>Evidence (${claims.length} verified claims)</summary>`, '', ...claims.map((c) => `- ${c.text}`), '', '</details>')
  return lines.join('\n')
}

function ImpactTab({ ws, onEvidence }) {
  const [commits, setCommits] = useState([])
  const [sha, setSha] = useState('')
  const [mods, setMods] = useState('')
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  const outRef = useRef(null)
  useEffect(() => { if (res) outRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [res])
  useEffect(() => { api.wsCommits(ws.id).then((c) => { setCommits(c); setSha(c[0]?.sha || '') }).catch(() => {}) }, [ws.id])
  const analyze = async (body) => { setBusy(true); setErr(''); try { setRes(await api.impact(ws.tenant, body)) } catch (e) { setErr(String(e)) } setBusy(false) }
  const row = res?.rows?.[0]
  const claims = (res?.verification?.claims || []).filter((c) => c.status === 'grounded')
  const color = !row ? '' : row.risk_score < 35 ? 'var(--ok)' : row.risk_score < 65 ? 'var(--warn)' : 'var(--bad)'
  return (
    <div className="stack">
      <div className="card">
        <h3>What does this change touch?</h3>
        <div className="row" style={{ alignItems: 'flex-end' }}>
          {commits.length > 0 && <div style={{ flex: '1 1 320px' }}><label className="muted" style={{ fontSize: 12 }}>A recent commit</label>
            <select style={{ width: '100%' }} value={sha} onChange={(e) => setSha(e.target.value)}>{commits.map((c) => <option key={c.sha} value={c.sha}>{c.sha} · {c.author} · {c.subject.slice(0, 60)}</option>)}</select></div>}
          {commits.length > 0 && <button className="btn" disabled={busy || !sha} onClick={() => analyze({ sha })}>{busy ? <Spinner /> : <Icon name="git" size={15} />} Analyze commit</button>}
          <div style={{ flex: '1 1 260px' }}><label className="muted" style={{ fontSize: 12 }}>…or modules (comma-separated)</label>
            <input type="text" placeholder="src/api/, lib/core/" value={mods} onChange={(e) => setMods(e.target.value)} /></div>
          <button className="btn ghost" disabled={busy || !mods.trim()} onClick={() => analyze({ modules: mods })}>Analyze modules</button>
        </div>
        {err && <div className="banner" style={{ marginTop: 10 }}>{err}</div>}
      </div>
      <div ref={outRef} style={{ scrollMarginTop: 72 }} />
      {row && (
        <div className="grid2">
          <div className="card">
            <div className="row" style={{ gap: 18, flexWrap: 'nowrap' }}>
              <div className="risk-gauge" style={{ '--v': row.risk_score, '--c': color }}><div><b>{row.risk_score}</b><small>risk</small></div></div>
              <div style={{ minWidth: 0 }}>
                <div className="muted" style={{ fontSize: 12 }}>TOUCHES</div>
                <div className="row" style={{ marginBottom: 8 }}>{row.touched.map((m) => <Pill key={m} mono>{m}</Pill>)}</div>
                <div className="muted" style={{ fontSize: 12 }}>{row.impacted_count} MODULES DEPEND ON IT</div>
                <div className="row">{row.impacted.slice(0, 10).map((m) => <Pill key={m} kind="blue" mono>{m}</Pill>)}{row.impacted_count > 10 && <Pill>+{row.impacted_count - 10}</Pill>}</div>
              </div>
            </div>
            <div className="kv" style={{ marginTop: 14, fontSize: 13 }}>
              <span>Owners</span><span>{row.owners.join(', ') || 'unknown'}</span>
              <span>Suggested reviewers</span><span>{row.reviewers.length ? row.reviewers.join(', ') : 'none (author is the only expert)'}</span>
            </div>
            {row.risk_factors.map((f) => <div key={f} className="banner" style={{ borderColor: 'var(--warn)', background: 'var(--warn-soft)', marginTop: 10 }}><Icon name="alert" size={14} /> {f}</div>)}
            <div className="row" style={{ marginTop: 14 }}>
              <button className="btn ghost sm" onClick={() => { navigator.clipboard.writeText(impactMarkdown(row, claims)); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>
                <Icon name="download" size={13} /> {copied ? 'Copied' : 'Copy as PR comment'}</button>
              <ReportMenu label="Impact report" build={() => buildRepoReport(ws, { impact: { row, claims } })} />
              <span className="muted" style={{ fontSize: 12 }}>The risk score is a transparent heuristic (impacted modules, churn, single-author code); the evidence on the right is verified.</span>
            </div>
          </div>
          <div className="card"><div className="row between"><h3 style={{ margin: 0 }}>Evidence</h3><span className="row" style={{ gap: 6 }}><GroundedBadge pct={res.verification.grounded_pct} n={res.verification.n_claims} /><AuditButton tenant={ws.tenant} claims={res.verification.claims} label="Audit" /></span></div>
            <div className="scroll" style={{ marginTop: 10 }}><ClaimRows claims={res.verification.claims} onEvidence={onEvidence} /></div></div>
        </div>
      )}
      {!row && !busy && <div className="card"><Empty icon="git">Pick a commit to see its blast radius, owners and the people best placed to review it.</Empty></div>}
    </div>
  )
}

function BenchTab({ ws }) {
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api.wsBenchmarkCached(ws.id).then(setRes).catch(() => {}) }, [ws.id])
  const run = async () => { setBusy(true); setErr(''); try { setRes(await api.wsBenchmark(ws.id)) } catch (e) { setErr(String(e)) } setBusy(false) }
  const order = ['1-hop', '2-hop', '3+-hop']
  const groups = res ? order.filter((b) => res.aggregate[b]).map((b) => ({ label: `${b} (n=${res.aggregate[b].n})`, a: res.aggregate[b].graph_exact, b: res.aggregate[b].docs_exact })) : []
  return (
    <div className="stack">
      <div className="card">
        <div className="row between"><div><h3 style={{ margin: 0 }}>Benchmark this repository</h3>
          <p className="muted" style={{ margin: '6px 0 0', maxWidth: '70ch' }}>Auto-generates questions from the analyser's own model (direct dependencies, dependents, 2-hop, full blast radius, top committer), asks both the graph agent and a documents-only baseline (hybrid retrieval of 8 file chunks + an import-parsing reader), and scores exact match. Ground truth never comes from FalkorDB.</p></div>
          <button className="btn" onClick={run} disabled={busy}>{busy ? <Spinner /> : <Icon name="flask" size={15} />} Run benchmark</button></div>
        {err && <div className="banner" style={{ marginTop: 10 }}>{err}</div>}
      </div>
      {res && (<>
        <div className="stat-grid">
          <Stat value={res.aggregate.all.n} label="questions" /><Stat value={`${Math.round(res.aggregate.all.graph_exact * 100)}%`} label="graph exact-match" />
          <Stat value={`${Math.round(res.aggregate.all.docs_exact * 100)}%`} label="docs-only exact-match" /><Stat value={`${res.aggregate.all.grounded_pct}%`} label="claims grounded" />
          <Stat value={`${res.aggregate.all.graph_p50_ms} ms`} label="median graph answer" />
        </div>
        <div className="grid2">
          <div className="card"><h3>By relationships needed</h3><GroupedBars groups={groups} aName="Graph agent" bName="Docs-only" /></div>
          <div className="card"><h3>By question type (correct / total)</h3><table><thead><tr><th>Type</th><th className="num">Graph</th><th className="num">Docs</th></tr></thead><tbody>
            {Object.entries(res.by_intent).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{v.graph}/{v.n}</td><td className="num">{v.docs}/{v.n}</td></tr>)}</tbody></table></div>
        </div>
        <div className="card"><h3>Every question</h3><div className="scroll" style={{ maxHeight: 420 }}><table><thead><tr><th>Question</th><th>Truth</th><th>Graph</th><th>Docs-only</th></tr></thead><tbody>
          {res.rows.map((r) => <tr key={r.id}><td>{r.question}</td><td className="mono" style={{ fontSize: 11.5 }}>{r.truth.slice(0, 4).join(', ')}{r.truth.length > 4 ? ` +${r.truth.length - 4}` : ''}</td>
            <td><Pill kind={r.graph.exact ? 'ok' : 'bad'}>{r.graph.exact ? 'correct' : 'wrong'}</Pill></td><td><Pill kind={r.docs.exact ? 'ok' : 'bad'}>{r.docs.exact ? 'correct' : 'wrong'}</Pill></td></tr>)}</tbody></table></div></div>
      </>)}
    </div>
  )
}

function Analysis({ ws, onDelete }) {
  const { setTenant } = useApp()
  const [tab, setTab] = useState('overview')
  const [drawer, setDrawer] = useState(null)
  const [mods, setMods] = useState([])
  useEffect(() => { setTenant(ws.tenant) }, [ws.tenant])
  useEffect(() => { api.wsModules(ws.id).then(setMods).catch(() => {}) }, [ws.id])
  const tabs = [['overview', 'grid', 'Overview'], ['map', 'route', 'Dependency map'], ['risk', 'alert', 'Risk'], ['impact', 'git', 'Change impact'], ['ask', 'message', 'Ask'], ['investigate', 'search', 'Investigate'], ['bench', 'flask', 'Benchmark']]
  const samples = useMemo(() => sampleQuestions(mods), [mods])
  return (
    <div>
      {drawer && <EvidenceDrawer tenant={ws.tenant} claim={drawer} onClose={() => setDrawer(null)} />}
      <div className="row between" style={{ marginBottom: 14 }}>
        <div className="row"><h2 style={{ fontSize: 20 }}>{ws.label}</h2><Pill kind="ok">ready</Pill><Pill mono>{ws.tenant}</Pill>
          {ws.url && <a href={ws.url} target="_blank" rel="noreferrer" className="chip blue"><Icon name="external" size={12} /> GitHub</a>}</div>
        <ReportMenu label="Export report" build={() => buildRepoReport(ws)} />
      </div>
      <nav className="tabs">{tabs.map(([k, ic, l]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}><Icon name={ic} size={14} />{l}</button>)}</nav>
      {tab === 'overview' && <Overview ws={ws} onEvidence={setDrawer} onDelete={onDelete} />}
      {tab === 'map' && <MapTab ws={ws} onEvidence={setDrawer} />}
      {tab === 'risk' && <div className="grid2e" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
        <ToolCard title="Hotspots" tenant={ws.tenant} tool="hotspots" args={{ top: 10 }} onEvidence={setDrawer} hint="Churn × fan-in, the classic risk signal: files that change a lot and that many modules rely on." />
        <ToolCard title="Bus factor" tenant={ws.tenant} tool="bus_factor" args={{ top: 10 }} onEvidence={setDrawer} hint="One person wrote most of the commits: a knowledge and review risk." />
        <ToolCard title="Most relied-upon (PageRank)" tenant={ws.tenant} tool="criticality" args={{ top: 8 }} onEvidence={setDrawer} />
        <ToolCard title="Chokepoints (betweenness)" tenant={ws.tenant} tool="single_points_of_failure" args={{ top: 8 }} onEvidence={setDrawer} />
      </div>}
      {tab === 'impact' && <ImpactTab ws={ws} onEvidence={setDrawer} />}
      {tab === 'ask' && <AskView tenant={ws.tenant} graphOn useLlm={null} keys={[]} samples={samples} />}
      {tab === 'investigate' && <Investigate embedded />}
      {tab === 'bench' && <BenchTab ws={ws} />}
    </div>
  )
}

export default function Lab({ query }) {
  const { workspaces, addWorkspace, removeWorkspace } = useApp()
  const [activeId, setActiveId] = useState(query.ws || null)
  const ws = workspaces.find((w) => w.id === activeId)
  useEffect(() => { if (!activeId && workspaces.length) setActiveId(workspaces[0].id) }, [workspaces.length])
  const created = (w) => { addWorkspace(w); setActiveId(w.id) }
  const [autoErr, setAutoErr] = useState('')
  // arriving from the landing page with ?repo=<url>: start analysing straight away
  useEffect(() => {
    if (!query.repo) return
    api.wsGithub(query.repo).then((w) => { created(w); history.replaceState(null, '', '#/app/lab') }).catch((e) => setAutoErr(String(e.message || e).replace(/^\d+\s*/, '').replace(/^\{"detail":"?|"?\}$/g, '')))
  }, [query.repo])
  const del = async () => { await api.wsDelete(ws.id).catch(() => {}); removeWorkspace(ws.id); setActiveId(null) }
  return (
    <div>
      <div className="page-head"><h2>Analyze your code</h2>
        <p>Paste a public GitHub URL, upload a folder or zip, or bring a JSON bundle from your service catalogue. You get a verified dependency graph, hotspots, owners, change impact and a reproducible benchmark.</p></div>
      {workspaces.length > 0 && (
        <div className="row" style={{ marginBottom: 12 }}>{workspaces.map((w) => (
          <button key={w.id} className={`chip ${activeId === w.id ? 'accent' : ''}`} style={{ height: 28, cursor: 'pointer' }} onClick={() => setActiveId(w.id)}>
            {w.status === 'running' || w.status === 'queued' ? <Spinner /> : <Icon name={w.status === 'error' ? 'alert' : 'folder'} size={12} />} {w.label}</button>))}
          <button className="chip" style={{ height: 28, cursor: 'pointer' }} onClick={() => setActiveId(null)}>+ New</button></div>)}
      {autoErr && <div className="banner">{autoErr}</div>}
      {(!ws || !activeId) && <SourceForm initialUrl={query.repo || ''} onCreated={created} />}
      {ws && ws.status !== 'ready' && ws.status !== 'error' && <div style={{ marginTop: 12 }}><Progress ws={ws} /></div>}
      {ws && ws.status === 'error' && <div style={{ marginTop: 12 }}><div className="banner"><b>Couldn't analyse {ws.label}.</b> {ws.error}</div>
        <button className="btn ghost" onClick={() => { removeWorkspace(ws.id); setActiveId(null) }}>Try another</button></div>}
      {ws && ws.status === 'ready' && <Analysis ws={ws} onDelete={del} />}
    </div>
  )
}
