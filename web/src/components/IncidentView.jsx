import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import GraphView from './GraphView'
import { Bar, GroundedBadge, Pill, fmtTs } from './Common'

const AGENT_COLOR = { triage: 'blue', investigator: 'ok', remediator: 'warn' }

function Claims({ claims, selected, onSelect }) {
  return (
    <div className="scroll">
      {claims.map((c, i) => (
        <div key={i} className={`claim ${c.status !== 'grounded' ? 'withheld' : ''} ${selected === i ? 'sel' : ''}`} onClick={() => onSelect(i)}>
          <div>{c.text}</div>
          <div className="meta">
            <Pill kind={AGENT_COLOR[c.agent]}>{c.agent}</Pill>
            {c.status === 'grounded'
              ? <Pill kind="ok">grounded · {(c.edge_ids?.length || 0) + (c.ended_edge_ids?.length || 0)} edge(s){c.node_ids?.length ? ` · ${c.node_ids.length} node(s)` : ''}</Pill>
              : <Pill kind="bad">withheld</Pill>}
            <span className="muted mono">{c.tool}</span>
          </div>
          {c.status !== 'grounded' && <div className="mono" style={{ color: 'var(--bad)', marginTop: 4 }}>{c.reason}</div>}
        </div>
      ))}
    </div>
  )
}

function Timeline({ agents }) {
  return (
    <div>
      {agents.map((a) => (
        <div key={a.agent} style={{ marginBottom: 14 }}>
          <div className="agent-head">
            <b style={{ textTransform: 'capitalize' }}>{a.agent}</b>
            <span className="muted mono">{a.ms ? `${a.ms} ms` : ''}</span>
          </div>
          <div className="muted" style={{ fontSize: 13, marginBottom: 4 }}>{a.headline}</div>
          {a.steps?.map((s) => (
            <div className="step" key={s.idx}>
              <span className="n mono">{s.idx + 1}</span>
              <div>
                <span className="mono" style={{ color: 'var(--accent)' }}>{s.tool}</span>{' '}
                <span className="muted mono">{JSON.stringify(s.args)}</span>
                <div className="muted" style={{ fontSize: 12 }}>{s.why} → {s.error ? <span style={{ color: 'var(--bad)' }}>{s.error}</span> : s.summary}</div>
                <div className="muted mono" style={{ fontSize: 11 }}>{s.cypher_ref}</div>
              </div>
              <span className="muted mono">{s.ms} ms</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

export default function IncidentView({ tenant, run, onApproved }) {
  const [sub, setSub] = useState({ nodes: [], edges: [] })
  const [sel, setSel] = useState(null)
  const [replayKey, setReplayKey] = useState(0)
  const [probe, setProbe] = useState(null)

  const claims = useMemo(() => (run ? run.agents.flatMap((a) => (a.verification?.claims || []).map((c) => ({ ...c, agent: a.agent }))) : []), [run])
  // draw exactly the evidence the verified claims cite, in the order the agents produced them
  const { edgeIds, nodeIds, order } = useMemo(() => {
    const order = new Map()
    const nodeIds = new Set()
    claims.filter((c) => c.status === 'grounded').forEach((c) => {
      ;[...(c.edge_ids || []), ...(c.ended_edge_ids || [])].forEach((e) => { if (!order.has(e)) order.set(e, order.size) })
      ;(c.node_ids || []).forEach((n) => nodeIds.add(n))
    })
    return { edgeIds: [...order.keys()], nodeIds: [...nodeIds], order }
  }, [claims])

  useEffect(() => {
    setSel(null); setProbe(null)
    if (!run?.graph_enabled || !edgeIds.length) { setSub({ nodes: [], edges: [] }); return }
    api.subgraph(tenant, edgeIds.slice(0, 300), nodeIds.slice(0, 60)).then(setSub).catch(() => setSub({ nodes: [], edges: [] }))
    setReplayKey((k) => k + 1)
  }, [run?.run_id])

  if (!run) return <div className="card empty">Pick an alert on the left and run the crew.<br />Every sentence the agents produce will carry the graph edges that back it.</div>
  const highlight = sel != null ? new Set([...(claims[sel].edge_ids || []), ...(claims[sel].ended_edge_ids || [])]) : null

  const inject = async () => {
    const base = claims.find((c) => c.status === 'grounded')
    if (!base) return
    const other = ['payments-api', 'ledger-store', 'auth-service'].find((s) => !base.text.includes(s) && !sub.nodes.some((n) => n.name === s))
    const fake = [
      { ...base, text: `${base.text}, and ${other} is also down` },
      { text: 'checkout-api depends on auth-service', edge_ids: [99999999], node_ids: [] },
      { text: 'The root cause was almost certainly a network blip', edge_ids: [], node_ids: [], kind: 'inference' },
    ]
    setProbe((await api.verify(tenant, fake)))
  }

  const approve = async (id) => { await api.approve(tenant, id); onApproved?.() }
  const rb = run.learned?.runbook

  return (
    <div>
      {!run.graph_enabled && <div className="banner"><b>Graph layer is OFF.</b> The product falls back to document retrieval only: no dependency scope, no ownership, no handoffs, no verifiable claims. This is rule 3 as an experiment.</div>}
      <div className="card">
        <div className="headline">{run.headline || run.error}</div>
        <div className="stats">
          <GroundedBadge pct={run.grounded_pct} n={run.n_claims} />
          {run.n_withheld > 0 && <Pill kind="bad">{run.n_withheld} withheld</Pill>}
          <Pill kind="blue">{run.planner}</Pill>
          {run.incident_id && <Pill>{run.incident_id}</Pill>}
          <Pill>{run.ms} ms</Pill>
        </div>
      </div>

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card">
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Evidence graph · replay of what the agents traversed</h3>
            <div className="row">
              <button className="btn ghost" onClick={() => setReplayKey((k) => k + 1)}>↻ Replay</button>
              <button className="btn ghost" onClick={inject} disabled={!run.graph_enabled}>Inject hallucination</button>
            </div>
          </div>
          {run.graph_enabled ? <GraphView nodes={sub.nodes} edges={sub.edges} highlight={highlight} order={order} replayKey={replayKey} />
            : <div className="empty">No graph, no evidence to draw.</div>}
          {probe && (
            <div style={{ marginTop: 10 }}>
              <b>Verifier on fabricated claims</b> <GroundedBadge pct={probe.grounded_pct} n={probe.n_claims} />
              {probe.claims.map((c, i) => (
                <div key={i} className="claim withheld"><div>{c.text}</div>
                  <div className="mono" style={{ color: 'var(--bad)' }}>{c.status}: {c.reason}</div></div>
              ))}
            </div>
          )}
        </div>
        <div className="card">
          <h3>Claims · click one to light up its edges</h3>
          {claims.length ? <Claims claims={claims} selected={sel} onSelect={(i) => setSel(sel === i ? null : i)} />
            : <div className="empty">No claims (graph disabled).</div>}
        </div>
      </div>

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card"><h3>Agent timeline · tools chosen and Cypher used</h3><Timeline agents={run.agents} /></div>
        <div>
          <div className="card">
            <h3>Handoff through graph state</h3>
            {run.tasks?.length ? (
              <table><thead><tr><th>Task</th><th>Status</th><th>Blocked by</th></tr></thead><tbody>
                {run.tasks.map((t) => (
                  <tr key={t.id}><td>{t.kind}<div className="muted mono">{t.id}</div></td>
                    <td><Pill kind={t.status === 'done' ? 'ok' : t.status === 'failed' ? 'bad' : 'warn'}>{t.status}</Pill></td>
                    <td className="mono muted">{t.blocked_by?.length ? t.blocked_by.map((b) => b.slice(0, 14)).join(', ') : '—'}</td></tr>
                ))}
              </tbody></table>
            ) : <div className="muted">No tasks (graph disabled).</div>}
          </div>
          <div className="card">
            <h3>Actions (simulated side effects)</h3>
            {run.actions?.length ? run.actions.map((a) => (
              <div key={a.id} style={{ marginBottom: 10 }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <span>{a.detail}</span>
                  <Pill kind={a.status === 'executed' ? 'ok' : 'warn'}>{a.status.replace('_', ' ')}</Pill>
                </div>
                <div className="row"><span className="muted mono">risk {a.risk}</span><Bar value={a.risk} risk /></div>
                {a.status === 'awaiting_approval' && <button className="btn warn" style={{ marginTop: 6 }} onClick={() => approve(a.id)}>Approve</button>}
              </div>
            )) : <div className="muted">None.</div>}
          </div>
          {rb && (
            <div className="card">
              <h3>What the crew learned</h3>
              <div>Runbook <b>{rb.title}</b>: outcome <Pill kind={rb.ok ? 'ok' : 'bad'}>{rb.ok ? 'success' : 'failure'}</Pill> (simulated)</div>
              <div className="muted">Now {rb.successes}/{rb.attempts} successes recorded in procedural memory.</div>
              {run.learned.fact && <div className="muted" style={{ marginTop: 6 }}>
                Semantic fact {run.learned.fact.created ? 'written' : 'already known'}{run.learned.fact.superseded?.length ? `, superseding ${run.learned.fact.superseded.length} older fact(s)` : ''}.</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
