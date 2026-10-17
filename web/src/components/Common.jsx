import Icon from './ui/Icon'

export const fmtTs = (ts) => (ts ? new Date(ts * 1000).toISOString().slice(0, 16).replace('T', ' ') + 'Z' : '—')
export const fmtNum = (n) => (n == null ? '—' : Number(n).toLocaleString())

export function GroundedBadge({ pct, n }) {
  const cls = pct >= 99.9 ? 'ok' : pct > 0 ? 'warn' : 'bad'
  return <span className={`chip ${cls}`} title="Share of proposed claims the verifier re-confirmed in FalkorDB">
    <Icon name={pct >= 99.9 ? 'shield' : 'alert'} size={12} /> Grounded {Number(pct).toFixed(pct % 1 ? 1 : 0)}%{n != null ? ` · ${n} claims` : ''}
  </span>
}
export function Bar({ value, max = 1, risk = false, ok = false }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100))
  return <div className={`bar ${risk ? 'risk' : ''} ${ok ? 'ok' : ''}`}><i style={{ width: `${w}%` }} /></div>
}
export function Pill({ children, kind = '', mono = false, title }) { return <span title={title} className={`chip ${kind} ${mono ? 'mono' : ''}`}>{children}</span> }
export function Empty({ icon = 'target', children }) {
  return <div className="empty"><div className="icon-wrap"><Icon name={icon} size={20} /></div><div>{children}</div></div>
}
export function Spinner() { return <span className="spinner" role="status" aria-label="Loading" /> }
export function Stat({ value, label, hint }) {
  return <div className="stat" title={hint}><div className="v">{value}</div><div className="l">{label}</div></div>
}

/** Minimal SVG line chart: series = [{name,color,points:[{x,y}]}], refs = [{y,label,color}] */
export function LineChart({ series, refs = [], xLabel = '', height = 220 }) {
  const W = 640, H = height, L = 40, R = 12, T = 30, B = 30
  const xs = series.flatMap((s) => s.points.map((p) => p.x))
  if (!xs.length) return null
  const x0 = Math.min(...xs), x1 = Math.max(...xs)
  const sx = (x) => L + ((x - x0) / Math.max(1, x1 - x0)) * (W - L - R)
  const sy = (y) => T + (1 - y) * (H - T - B)
  const t = { fill: 'var(--muted)' }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', background: 'var(--surface-2)', borderRadius: 10 }}>
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}><line x1={L} x2={W - R} y1={sy(g)} y2={sy(g)} style={{ stroke: 'var(--line)' }} />
          <text x={L - 6} y={sy(g) + 3} fontSize="10" textAnchor="end" style={t}>{Math.round(g * 100)}%</text></g>
      ))}
      {refs.map((r) => (
        <g key={r.label}><line x1={L} x2={W - R} y1={sy(r.y)} y2={sy(r.y)} strokeDasharray="5 4" style={{ stroke: r.color }} />
          <text x={W - R} y={sy(r.y) - 4} fontSize="10" textAnchor="end" style={{ fill: r.color }}>{r.label}</text></g>
      ))}
      {series.map((s) => (
        <g key={s.name}>
          <polyline fill="none" strokeWidth="2.4" strokeLinejoin="round" points={s.points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(' ')} style={{ stroke: s.color }} />
          {s.points.map((p) => <circle key={p.x} cx={sx(p.x)} cy={sy(p.y)} r="2.6" style={{ fill: s.color }} />)}
        </g>
      ))}
      <text x={(W + L) / 2} y={H - 6} fontSize="10" textAnchor="middle" style={t}>{xLabel}</text>
      {series.map((s, i) => (
        <g key={s.name} transform={`translate(${L + 8 + i * 190},9)`}>
          <rect width="10" height="10" rx="2" style={{ fill: s.color }} /><text x="15" y="9" fontSize="11" style={{ fill: 'var(--text)' }}>{s.name}</text>
        </g>
      ))}
    </svg>
  )
}

/** Grouped bars: groups = [{label, a, b}] with values 0..1 */
export function GroupedBars({ groups, aName, bName, aColor = 'var(--accent)', bColor = 'var(--faint)' }) {
  const W = 640, H = 250, L = 40, T = 38, B = 34
  const gw = (W - L - 10) / groups.length
  const sy = (v) => T + (1 - v) * (H - T - B)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', background: 'var(--surface-2)', borderRadius: 10 }}>
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}><line x1={L} x2={W - 6} y1={sy(g)} y2={sy(g)} style={{ stroke: 'var(--line)' }} />
          <text x={L - 6} y={sy(g) + 3} fontSize="10" textAnchor="end" style={{ fill: 'var(--muted)' }}>{Math.round(g * 100)}%</text></g>
      ))}
      {groups.map((g, i) => {
        const x = L + i * gw + gw * 0.15, bw = gw * 0.32
        return (
          <g key={g.label}>
            {[[g.a, aColor, 0], [g.b, bColor, 1]].map(([v, c, k]) => (
              <g key={k}>
                <rect x={x + k * (bw + 4)} y={sy(v)} width={bw} height={Math.max(1, (H - B) - sy(v))} rx="3" style={{ fill: c }} />
                <text x={x + k * (bw + 4) + bw / 2} y={sy(v) - 4} fontSize="10.5" textAnchor="middle" style={{ fill: 'var(--text)' }}>{Math.round(v * 100)}%</text>
              </g>
            ))}
            <text x={x + bw} y={H - 14} fontSize="11" textAnchor="middle" style={{ fill: 'var(--muted)' }}>{g.label}</text>
          </g>
        )
      })}
      <g transform={`translate(${L + 8},8)`}>
        <rect width="10" height="10" rx="2" style={{ fill: aColor }} /><text x="15" y="9" fontSize="11" style={{ fill: 'var(--text)' }}>{aName}</text>
        <rect x="190" width="10" height="10" rx="2" style={{ fill: bColor }} /><text x="205" y="9" fontSize="11" style={{ fill: 'var(--text)' }}>{bName}</text>
      </g>
    </svg>
  )
}
