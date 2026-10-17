import { useEffect, useState } from 'react'
import { api } from '../api'
import Icon from './ui/Icon'
import { Pill, Spinner } from './Common'

const BASIS = { import: 'static import analysis', codeowners: 'CODEOWNERS rule', 'top-committer': 'derived from git', git: 'git history', synthetic: 'synthetic data', bundle: 'uploaded bundle', 'contributed-to-owned-modules': 'inferred from contributions' }

/** "Why is this true?" — for each edge a claim cites: what it is and where it came from (import sites, rule, commit). */
export default function EvidenceDrawer({ tenant, claim, onClose }) {
  const [items, setItems] = useState(null)
  useEffect(() => {
    const ids = [...(claim.edge_ids || []), ...(claim.ended_edge_ids || [])].slice(0, 10)
    Promise.all(ids.map((id) => api.provenance(tenant, id).then((p) => ({ id, ...p })).catch(() => ({ id, error: true })))).then(setItems)
  }, [claim, tenant])
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Evidence">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h3 style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '.09em', color: 'var(--muted)' }}>Evidence</h3>
          <button className="btn quiet icon" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <p style={{ fontSize: 16, lineHeight: 1.5 }}>{claim.text}</p>
        <div className="row" style={{ margin: '8px 0 16px' }}>
          <Pill kind={claim.status === 'grounded' ? 'ok' : 'bad'}>{claim.status || 'claim'}</Pill>
          {claim.tool && <Pill mono>{claim.tool}</Pill>}
          <Pill>{(claim.edge_ids || []).length} edge(s)</Pill>
        </div>
        {claim.status !== 'grounded' && claim.reason && <div className="banner">{claim.reason}</div>}
        {!items && <div className="row"><Spinner /> Loading provenance…</div>}
        {items?.map((p) => (
          <div className="card" key={p.id} style={{ marginBottom: 10, boxShadow: 'none' }}>
            {p.error ? <span className="muted">Edge {p.id}: not available</span> : <>
              <div className="row between"><b>{p.from.name} <span className="faint">—{p.type}→</span> {p.to.name}</b><Pill mono>edge {p.id}</Pill></div>
              <div className="row" style={{ margin: '6px 0' }}><Pill kind="blue">{BASIS[p.basis] || p.basis}</Pill>{p.count ? <Pill>{p.count} import(s)</Pill> : null}{p.lines ? <Pill>{p.lines} lines changed</Pill> : null}</div>
              <div className="muted" style={{ fontSize: 13 }}>{p.why}</div>
              {p.sites?.map((s) => <div className="prov mono" key={s}>{s}</div>)}
              {p.rule && <div className="prov mono">{p.rule}</div>}
            </>}
          </div>
        ))}
        {claim.assert_props?.length > 0 && (
          <div className="card" style={{ boxShadow: 'none' }}>
            <div className="card-title">Re-checked node properties</div>
            {claim.assert_props.map((a, i) => <div key={i} className="mono" style={{ fontSize: 12 }}>{a.node_id} · {a.prop} {a.op === 'ge' ? '≥' : '='} {String(a.value)}</div>)}
          </div>
        )}
      </aside>
    </div>
  )
}
