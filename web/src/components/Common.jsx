export const fmtTs = (ts) => (ts ? new Date(ts * 1000).toISOString().slice(0, 16).replace('T', ' ') + 'Z' : '—')

export function GroundedBadge({ pct, n }) {
  const cls = pct >= 99.9 ? 'ok' : pct > 0 ? 'warn' : 'bad'
  return <span className={`chip ${cls}`} title="Share of proposed claims that the verifier re-confirmed in FalkorDB">
    Grounded {Number(pct).toFixed(pct % 1 ? 1 : 0)}%{n != null ? ` · ${n} claims` : ''}
  </span>
}

export function Bar({ value, max = 1, risk = false }) {
  const w = Math.max(0, Math.min(100, (value / max) * 100))
  return <div className={`bar ${risk ? 'risk' : ''}`}><i style={{ width: `${w}%` }} /></div>
}

export function Pill({ children, kind = '' }) { return <span className={`chip ${kind}`}>{children}</span> }

/** Minimal SVG line chart: series = [{name,color,points:[{x,y}]}], refs = [{y,label,color}] */
export function LineChart({ series, refs = [], xLabel = '', height = 220 }) {
  const W = 640, H = height, L = 40, R = 12, T = 12, B = 30
  const xs = series.flatMap((s) => s.points.map((p) => p.x))
  if (!xs.length) return null
  const x0 = Math.min(...xs), x1 = Math.max(...xs)
  const sx = (x) => L + ((x - x0) / Math.max(1, x1 - x0)) * (W - L - R)
  const sy = (y) => T + (1 - y) * (H - T - B)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', background: 'var(--panel-2)', borderRadius: 10 }}>
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}><line x1={L} x2={W - R} y1={sy(g)} y2={sy(g)} stroke="#243058" />
          <text x={L - 6} y={sy(g) + 3} fontSize="10" fill="#8e9acb" textAnchor="end">{Math.round(g * 100)}%</text></g>
      ))}
      {refs.map((r) => (
        <g key={r.label}><line x1={L} x2={W - R} y1={sy(r.y)} y2={sy(r.y)} stroke={r.color} strokeDasharray="5 4" />
          <text x={W - R} y={sy(r.y) - 4} fontSize="10" fill={r.color} textAnchor="end">{r.label}</text></g>
      ))}
      {series.map((s) => (
        <g key={s.name}>
          <polyline fill="none" stroke={s.color} strokeWidth="2.4"
            points={s.points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(' ')} />
          {s.points.map((p) => <circle key={p.x} cx={sx(p.x)} cy={sy(p.y)} r="2.6" fill={s.color} />)}
        </g>
      ))}
      <text x={(W + L) / 2} y={H - 6} fontSize="10" fill="#8e9acb" textAnchor="middle">{xLabel}</text>
      {series.map((s, i) => (
        <g key={s.name} transform={`translate(${L + 8 + i * 150},${T + 8})`}>
          <rect width="10" height="10" fill={s.color} rx="2" /><text x="15" y="9" fontSize="11" fill="#e6ebff">{s.name}</text>
        </g>
      ))}
    </svg>
  )
}

/** Grouped bars: groups = [{label, a, b}] with values 0..1 */
export function GroupedBars({ groups, aName, bName, aColor = '#2dd4bf', bColor = '#f87171' }) {
  const W = 640, H = 252, L = 40, T = 36, B = 34
  const gw = (W - L - 10) / groups.length
  const sy = (v) => T + (1 - v) * (H - T - B)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', background: 'var(--panel-2)', borderRadius: 10 }}>
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}><line x1={L} x2={W - 6} y1={sy(g)} y2={sy(g)} stroke="#243058" />
          <text x={L - 6} y={sy(g) + 3} fontSize="10" fill="#8e9acb" textAnchor="end">{Math.round(g * 100)}%</text></g>
      ))}
      {groups.map((g, i) => {
        const x = L + i * gw + gw * 0.15, bw = gw * 0.32
        return (
          <g key={g.label}>
            {[[g.a, aColor, 0], [g.b, bColor, 1]].map(([v, c, k]) => (
              <g key={k}>
                <rect x={x + k * (bw + 4)} y={sy(v)} width={bw} height={Math.max(1, (H - B) - sy(v))} fill={c} rx="3" />
                <text x={x + k * (bw + 4) + bw / 2} y={sy(v) - 4} fontSize="10.5" fill="#e6ebff" textAnchor="middle">{Math.round(v * 100)}%</text>
              </g>
            ))}
            <text x={x + bw} y={H - 14} fontSize="11" fill="#8e9acb" textAnchor="middle">{g.label}</text>
          </g>
        )
      })}
      <g transform={`translate(${L + 8},6)`}>
        <rect width="10" height="10" fill={aColor} rx="2" /><text x="15" y="9" fontSize="11" fill="#e6ebff">{aName}</text>
        <rect x="150" width="10" height="10" fill={bColor} rx="2" /><text x="165" y="9" fontSize="11" fill="#e6ebff">{bName}</text>
      </g>
    </svg>
  )
}
