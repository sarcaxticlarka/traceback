import { useEffect, useMemo, useRef, useState } from 'react'
import Icon from './ui/Icon'
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force'

export const LABEL_COLORS = {
  Service: '#7ba7ff', Person: '#f5c451', Team: '#b79cff', Deploy: '#ff7a6b', Incident: '#ff9f43', Alert: '#f472b6',
  Doc: '#94a3b8', Decision: '#4fd1e0', Fact: '#54d6a1', Runbook: '#a3e635', Source: '#64748b', Task: '#e879f9',
}
const W = 900, H = 520, PAD = 46

function layout(nodes, edges, ticks) {
  const ns = nodes.map((n) => ({ ...n }))
  const idx = new Map(ns.map((n) => [n.id, n]))
  const links = edges.filter((e) => idx.has(e.source) && idx.has(e.target)).map((e) => ({ ...e }))
  const big = ns.length > 40
  const sim = forceSimulation(ns)
    .force('link', forceLink(links).id((d) => d.id).distance(big ? 46 : 70).strength(big ? 0.5 : 0.9))
    .force('charge', forceManyBody().strength(big ? -120 : -220).distanceMax(big ? 200 : 260))
    .force('x', forceX(0).strength(big ? 0.12 : 0.09))
    .force('y', forceY(0).strength(big ? 0.14 : 0.11))
    .force('collide', forceCollide(big ? 14 : 24))
    .stop()
  for (let i = 0; i < ticks; i++) sim.tick()
  // isolated nodes can still drift: pull anything beyond 1.5x the 90th-percentile radius back so the main cluster fills the view
  const radii = ns.map((n) => Math.hypot(n.x, n.y)).sort((a, b) => a - b)
  const cap = Math.max(40, (radii[Math.floor(radii.length * 0.9)] || 0) * 1.5)
  ns.forEach((n) => { const d = Math.hypot(n.x, n.y); if (d > cap) { n.x *= cap / d; n.y *= cap / d } })
  const xs = ns.map((n) => n.x), ys = ns.map((n) => n.y)
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const s = Math.min((W - 2 * PAD) / Math.max(1, x1 - x0), (H - 2 * PAD) / Math.max(1, y1 - y0), big ? 5 : 2.2)
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2
  ns.forEach((n) => { n.px = W / 2 + (n.x - cx) * s; n.py = H / 2 + (n.y - cy) * s })
  return { ns, links }
}

/**
 * Evidence / dependency graph. Props:
 *  highlight: Set of edge ids to emphasise · order: Map edgeId -> traversal index (replay animation)
 *  onNode(node) makes nodes clickable · selected: node id · labels: 'all' | 'top' · sizeBy: 'dependents' to scale by importance
 */
function GraphCanvas({ nodes = [], edges = [], highlight = null, order = null, replayKey = 0, onNode, selected, labels = 'all', sizeBy, height = 520, view, setView, svgRef, fill }) {
  const { ns, links } = useMemo(() => (nodes.length ? layout(nodes, edges, nodes.length > 40 ? 420 : 320) : { ns: [], links: [] }), [nodes, edges])
  const drag = useRef(null)
  if (!ns.length) return <div className="empty">No evidence to draw yet.</div>
  const showEdgeLabels = links.length <= 22
  const firstSeen = new Map()
  links.forEach((e) => {
    const o = order?.get(e.id) ?? 0
    for (const end of [e.source.id, e.target.id]) if (!firstSeen.has(end) || firstSeen.get(end) > o) firstSeen.set(end, o)
  })
  const radius = (n) => sizeBy && n[sizeBy] != null ? 5 + Math.min(14, Math.sqrt(n[sizeBy]) * 2.2) : n.label === 'Service' ? 9 + (3 - (n.tier ?? 2)) * 1.6 : 8
  const topIds = new Set([...ns].sort((a, b) => radius(b) - radius(a)).slice(0, 14).map((n) => n.id))
  const kinds = [...new Set(ns.map((n) => n.label))]
  const neighbors = new Set()
  if (selected) links.forEach((e) => { if (e.source.id === selected) neighbors.add(e.target.id); if (e.target.id === selected) neighbors.add(e.source.id) })

  const onWheel = (e) => { e.preventDefault(); setView((v) => ({ ...v, k: Math.max(.4, Math.min(6, v.k * (e.deltaY < 0 ? 1.12 : 0.89))) })) }
  // capture the pointer only once it actually drags, otherwise node clicks would be redirected to the svg
  const onDown = (e) => { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false } }
  const onMove = (e) => {
    const d = drag.current
    if (!d) return
    if (!d.moved && Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) { d.moved = true; e.currentTarget.setPointerCapture(e.pointerId) }
    if (d.moved) setView((v) => ({ ...v, x: d.vx + (e.clientX - d.x), y: d.vy + (e.clientY - d.y) }))
  }
  const onUp = () => { drag.current = null }

  return (
    <div>
      <svg ref={svgRef} className="graph" style={{ height: fill ? "100%" : height }} viewBox={`0 0 ${W} ${H}`} key={replayKey} role="img" aria-label="Dependency graph"
        onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}>
        <defs><marker id="arrow" viewBox="0 0 10 10" refX="19" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" style={{ fill: 'var(--faint)' }} /></marker></defs>
        <g transform={`translate(${view.x} ${view.y}) scale(${view.k}) `} style={{ transformOrigin: '450px 260px' }}>
          {links.map((e) => {
            const hl = highlight?.has(e.id) || (selected && (e.source.id === selected || e.target.id === selected))
            const dim = (highlight && highlight.size > 0 && !hl) || (selected && !hl)
            const delay = order ? (order.get(e.id) ?? 0) * 70 : 0
            const mx = (e.source.px + e.target.px) / 2, my = (e.source.py + e.target.py) / 2
            return (
              <g key={e.id}>
                <line className={`edge ${hl ? 'hl' : ''} ${dim ? 'dim' : ''} ${order ? 'reveal' : ''}`} markerEnd="url(#arrow)"
                  x1={e.source.px} y1={e.source.py} x2={e.target.px} y2={e.target.py} style={{ animationDelay: `${delay}ms` }} />
                {(showEdgeLabels || (hl && highlight)) && <text x={mx} y={my - 3} fontSize="8.5" textAnchor="middle"
                  style={{ fill: hl ? 'var(--accent)' : 'var(--faint)', paintOrder: 'stroke', stroke: 'var(--bg-elev)', strokeWidth: 3 }}>{e.type}</text>}
              </g>
            )
          })}
          {ns.map((n) => {
            const r = radius(n)
            const delay = order ? (firstSeen.get(n.id) ?? 0) * 70 : 0
            const isSel = selected === n.id
            const dim = selected && !isSel && !neighbors.has(n.id)
            const showLabel = labels === 'all' || isSel || neighbors.has(n.id) || (labels === 'top' && topIds.has(n.id))
            return (
              <g key={n.id} className={`node ${order ? 'reveal' : ''} ${onNode ? 'clickable' : ''}`} transform={`translate(${n.px},${n.py})`}
                style={{ animationDelay: `${delay}ms`, opacity: dim ? .28 : undefined }} onClick={(e) => { e.stopPropagation(); onNode?.(n) }}>
                <title>{`${n.label}: ${n.name}\n${n.id}`}</title>
                <circle r={r} fill={LABEL_COLORS[n.label] || '#888'} style={{ stroke: isSel ? 'var(--accent)' : 'var(--bg-elev)', strokeWidth: isSel ? 3.5 : 2 }} />
                {showLabel && <text y={r + 11} textAnchor="middle">{String(n.name).length > 26 ? String(n.name).slice(0, 25) + '…' : n.name}</text>}
              </g>
            )
          })}
        </g>
      </svg>
      <div className="row between" style={{ marginTop: 8 }}>
        <div className="legend">{kinds.map((l) => <span key={l}><i style={{ background: LABEL_COLORS[l] || '#888' }} />{l}</span>)}</div>
        <span className="faint" style={{ fontSize: 11.5 }}>scroll to zoom · drag to pan{onNode ? ' · click a node' : ''}</span>
      </div>
    </div>
  )
}

const clampK = (k) => Math.max(0.4, Math.min(6, k))

/** Graph with a toolbar: zoom in / out / reset, full screen, save as SVG. Pass `containerRef` to let a parent grab the svg (reports). */
export default function GraphView(props) {
  const [view, setView] = useState({ k: 1, x: 0, y: 0 })
  const [full, setFull] = useState(false)
  const svgRef = useRef(null)
  const fsSvgRef = useRef(null)
  useEffect(() => {
    if (!full) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setFull(false) }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = '' }
  }, [full])
  const zoom = (f) => setView((v) => ({ ...v, k: clampK(v.k * f) }))
  const save = () => {
    const el = (full ? fsSvgRef : svgRef).current
    if (!el) return
    const clone = el.cloneNode(true)
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    const blob = new Blob([svgForExport(clone)], { type: 'image/svg+xml' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob); a.download = 'traceback-graph.svg'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  }
  const bar = (
    <div className="gtools" role="toolbar" aria-label="Graph controls">
      <button className="btn ghost icon sm" onClick={() => zoom(1.25)} title="Zoom in" aria-label="Zoom in"><Icon name="plus" size={15} /></button>
      <button className="btn ghost icon sm" onClick={() => zoom(0.8)} title="Zoom out" aria-label="Zoom out"><Icon name="minus" size={15} /></button>
      <button className="btn ghost icon sm" onClick={() => setView({ k: 1, x: 0, y: 0 })} title="Reset view" aria-label="Reset view"><Icon name="target" size={15} /></button>
      <button className="btn ghost icon sm" onClick={save} title="Save as SVG" aria-label="Save as SVG"><Icon name="download" size={15} /></button>
      <button className="btn ghost icon sm" onClick={() => setFull(!full)} title={full ? 'Exit full screen (Esc)' : 'Full screen'} aria-label="Full screen"><Icon name={full ? 'shrink' : 'expand'} size={15} /></button>
    </div>
  )
  return (
    <>
      <div className="gwrap">{bar}<GraphCanvas {...props} view={view} setView={setView} svgRef={svgRef} /></div>
      {full && (
        <div className="fs-overlay" role="dialog" aria-label="Graph, full screen">
          <div className="fs-head"><b>Graph</b><span className="muted"> · scroll to zoom, drag to pan, Esc to close</span><span className="spacer" style={{ flex: 1 }} />{bar}
            <button className="btn quiet icon sm" onClick={() => setFull(false)} aria-label="Close"><Icon name="x" size={16} /></button></div>
          <div className="fs-body"><GraphCanvas {...props} view={view} setView={setView} svgRef={fsSvgRef} fill /></div>
        </div>
      )}
    </>
  )
}

/** Make a standalone SVG: resolve CSS variables to literal colours and drop animation state. */
export function svgForExport(svg) {
  const cs = getComputedStyle(document.documentElement)
  const v = (name) => cs.getPropertyValue(name).trim()
  svg.querySelectorAll('.reveal').forEach((n) => { n.classList.remove('reveal'); n.style.animationDelay = ''; n.style.opacity = '' })
  const css = `.edge{stroke:${v('--line-2')};stroke-width:1.2;fill:none}.edge.hl{stroke:${v('--accent')};stroke-width:2.6}.edge.dim{opacity:.2}` +
    `.node text{fill:${v('--text')};font:10.5px sans-serif;paint-order:stroke;stroke:${v('--bg-elev')};stroke-width:3px}`
  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style')
  style.textContent = css
  svg.insertBefore(style, svg.firstChild)
  svg.setAttribute('style', `background:${v('--bg-elev')}`)
  const out = new XMLSerializer().serializeToString(svg)
  return out.replace(/var\((--[a-z0-9-]+)\)/g, (_, n) => v(n) || '#888')
}
