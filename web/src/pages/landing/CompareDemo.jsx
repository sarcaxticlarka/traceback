import { useEffect, useState } from 'react'
import { api } from '../../api'
import { go } from '../../lib/router'
import Icon from '../../components/ui/Icon'
import { spot } from './hooks'

const QS = [
  { tenant: 'orbit', hops: '3 hops', q: 'Which teams own services that would be impacted if auth-service fails?' },
  { tenant: 'helix', hops: '3 hops', q: 'Who authored the deploy most likely responsible for alert:LIVE-3?' },
  { tenant: 'helix', hops: '3+ hops', q: 'Which services are owned by a team with no current members?' },
  { tenant: 'helix', hops: '4+ hops', q: 'What is the full blast radius if db-proxy fails?' },
]
const MAX = 9

function Chips({ items, tone, truth }) {
  const shown = items.slice(0, MAX)
  return (
    <div className="cmp-chips">
      {shown.map((a) => <span key={a} className={`cchip ${tone} ${truth && !truth.has(a) ? 'wrong' : ''}`}>{a}</span>)}
      {items.length > MAX && <span className="cchip more">+{items.length - MAX} more</span>}
      {!items.length && <span className="cmp-none">Nothing the documents state directly.</span>}
    </div>
  )
}

/** Same question, two systems, live from the API: the documents-only baseline vs the graph agent. */
export default function CompareDemo() {
  const [i, setI] = useState(0)
  const [res, setRes] = useState({})
  useEffect(() => {
    QS.forEach((x, k) => api.ask({ tenant: x.tenant, question: x.q, graph_enabled: true }).then((r) => setRes((s) => ({ ...s, [k]: r }))).catch(() => {}))
  }, [])
  const r = res[i]
  const graph = r?.answers || []
  const docs = r?.baseline_docs_only || []
  const truth = new Set(graph)
  const found = docs.filter((d) => truth.has(d)).length
  return (
    <div className="cmp glass" onMouseMove={spot}>
      <div className="cmp-tabs" role="tablist">
        {QS.map((x, k) => (
          <button key={k} role="tab" aria-selected={i === k} className={i === k ? 'on' : ''} onClick={() => setI(k)}>
            <span className="mono-label">{x.hops}</span><span>{x.q}</span></button>))}
      </div>
      <div className="cmp-grid">
        <div className="cmp-col docs">
          <div className="cmp-h"><Icon name="file" size={15} /> Documents + embeddings <span className="mono-label">retrieval · 8 chunks</span></div>
          {r ? <Chips items={docs} tone="docs" truth={truth} /> : <div className="skeleton" style={{ height: 70 }} />}
          {r && <div className="cmp-foot bad">{docs.length ? `Finds ${found} of ${graph.length}${docs.length > found ? ` and ${docs.length - found} wrong` : ''}` : `Finds 0 of ${graph.length}`}. No evidence to check.</div>}
        </div>
        <div className="cmp-col graph">
          <div className="cmp-h"><Icon name="route" size={15} /> TRACEBACK <span className="mono-label">graph agent</span></div>
          {r ? <Chips items={graph} tone="graph" /> : <div className="skeleton" style={{ height: 70 }} />}
          {r && <div className="cmp-foot ok"><Icon name="shield" size={13} /> Grounded {Math.round(r.verification?.grounded_pct ?? 0)}% · {r.verification?.n_claims ?? 0} claims, each with its edges</div>}
        </div>
      </div>
      <div className="cmp-bar"><span className="muted">Live: this just ran against the demo company's graph.</span>
        <button className="btn ghost sm" onClick={() => go('/app/ask')}>Ask your own question <Icon name="chevron" size={13} /></button></div>
    </div>
  )
}
