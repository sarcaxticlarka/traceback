import { useMemo } from 'react'
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force'

export const LABEL_COLORS = {
  Service: '#60a5fa', Person: '#fbbf24', Team: '#a78bfa', Deploy: '#f87171', Incident: '#fb923c', Alert: '#f472b6',
  Doc: '#94a3b8', Decision: '#22d3ee', Fact: '#34d399', Runbook: '#a3e635', Source: '#64748b', Task: '#e879f9',
}
const W = 900, H = 520, PAD = 46

function layout(nodes, edges) {
  const ns = nodes.map((n) => ({ ...n }))
  const idx = new Map(ns.map((n) => [n.id, n]))
  const links = edges.filter((e) => idx.has(e.source) && idx.has(e.target)).map((e) => ({ ...e }))
  const sim = forceSimulation(ns)
    .force('link', forceLink(links).id((d) => d.id).distance(70).strength(0.9))
    .force('charge', forceManyBody().strength(-220).distanceMax(260))
    .force('x', forceX(0).strength(0.09))      // gravity keeps disconnected evidence clusters on screen together
    .force('y', forceY(0).strength(0.11))
    .force('collide', forceCollide(24))
    .stop()
  for (let i = 0; i < 320; i++) sim.tick()
  const xs = ns.map((n) => n.x), ys = ns.map((n) => n.y)
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const sx = (W - 2 * PAD) / Math.max(1, x1 - x0), sy = (H - 2 * PAD) / Math.max(1, y1 - y0)
  const s = Math.min(sx, sy, 2.2)
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2
  ns.forEach((n) => { n.px = W / 2 + (n.x - cx) * s; n.py = H / 2 + (n.y - cy) * s })
  return { ns, idx, links }
}

/** Evidence subgraph. `order` maps edge id -> traversal index (drives the replay animation). */
export default function GraphView({ nodes = [], edges = [], highlight = null, order = null, replayKey = 0 }) {
  const { ns, idx, links } = useMemo(() => (nodes.length ? layout(nodes, edges) : { ns: [], idx: new Map(), links: [] }),
    [nodes, edges])
  if (!ns.length) return <div className="empty">No evidence to draw yet.</div>
  const showEdgeLabels = links.length <= 22
  const firstSeen = new Map()
  links.forEach((e) => {
    const o = order?.get(e.id) ?? 0
    for (const end of [e.source.id, e.target.id]) if (!firstSeen.has(end) || firstSeen.get(end) > o) firstSeen.set(end, o)
  })
  const labels = [...new Set(ns.map((n) => n.label))]
  return (
    <div>
      <svg className="graph" viewBox={`0 0 ${W} ${H}`} key={replayKey} role="img" aria-label="Evidence subgraph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="19" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#5b6cb0" />
          </marker>
        </defs>
        {links.map((e) => {
          const hl = highlight?.has(e.id)
          const dim = highlight && highlight.size > 0 && !hl
          const delay = order ? (order.get(e.id) ?? 0) * 70 : 0
          const mx = (e.source.px + e.target.px) / 2, my = (e.source.py + e.target.py) / 2
          return (
            <g key={e.id}>
              <line className={`edge ${hl ? 'hl' : ''} ${dim ? 'dim' : ''} ${order ? 'reveal' : ''}`} markerEnd="url(#arrow)"
                x1={e.source.px} y1={e.source.py} x2={e.target.px} y2={e.target.py} style={{ animationDelay: `${delay}ms` }} />
              {(showEdgeLabels || hl) && (
                <text x={mx} y={my - 3} fontSize="8.5" fill={hl ? '#2dd4bf' : '#6f7fb8'} textAnchor="middle"
                  style={{ paintOrder: 'stroke', stroke: '#0b1020', strokeWidth: 3 }}>{e.type}</text>
              )}
            </g>
          )
        })}
        {ns.map((n) => {
          const r = n.label === 'Service' ? 9 + (3 - (n.tier ?? 2)) * 1.6 : 8
          const delay = order ? (firstSeen.get(n.id) ?? 0) * 70 : 0
          return (
            <g key={n.id} className={`node ${order ? 'reveal' : ''}`} transform={`translate(${n.px},${n.py})`}
              style={{ animationDelay: `${delay}ms` }}>
              <title>{`${n.label}: ${n.name}\n${n.id}`}</title>
              <circle r={r} fill={LABEL_COLORS[n.label] || '#888'} stroke="#0b1020" strokeWidth="2" />
              <text y={r + 11} textAnchor="middle">{String(n.name).length > 24 ? String(n.name).slice(0, 23) + '…' : n.name}</text>
            </g>
          )
        })}
      </svg>
      <div className="legend">
        {labels.map((l) => <span key={l}><i style={{ background: LABEL_COLORS[l] || '#888' }} />{l}</span>)}
      </div>
    </div>
  )
}
