import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../lib/ctx'
import Icon from './ui/Icon'
import { LLMBadge } from './LLMSettings'
import { Pill, Spinner } from './Common'

const KIND = { supported: 'ok', partial: 'warn', unsupported: 'bad', unknown: '' }

function AuditDrawer({ data, claims, onClose }) {
  const c = data.counts
  const order = { unsupported: 0, partial: 1, unknown: 2, supported: 3 }
  const rows = [...data.results].sort((a, b) => order[a.verdict] - order[b.verdict])
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Independent audit">
        <div className="row between" style={{ marginBottom: 10 }}>
          <h3 style={{ fontSize: 13, textTransform: 'uppercase', letterSpacing: '.09em', color: 'var(--muted)' }}>Independent audit · your key</h3>
          <button className="btn quiet icon" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="row" style={{ marginBottom: 10 }}>
          <Pill kind="ok">{c.supported} supported</Pill>{c.partial > 0 && <Pill kind="warn">{c.partial} partial</Pill>}
          {c.unsupported > 0 && <Pill kind="bad">{c.unsupported} unsupported</Pill>}{c.unknown > 0 && <Pill>{c.unknown} unknown</Pill>}
        </div>
        <LLMBadge info={data.llm} />
        {data.disagreements > 0 && <div className="banner" style={{ marginTop: 10 }}><b>{data.disagreements} disagreement{data.disagreements > 1 ? 's' : ''}.</b> Our verifier marked these grounded but your model says the shown evidence doesn't fully support them. Open the claim's evidence to check.</div>}
        {data.error && <div className="banner" style={{ marginTop: 10 }}>Some claims could not be audited: {data.error}</div>}
        <p className="muted" style={{ fontSize: 12.5, margin: '12px 0' }}>{data.note} Claims and their evidence were sent to the provider you configured, nothing else.</p>
        {rows.map((r) => (
          <div key={r.i} className={`claim ${r.verdict === 'unsupported' ? 'withheld' : ''}`} style={{ cursor: 'default' }}>
            <div>{r.text}</div>
            <div className="meta"><Pill kind={KIND[r.verdict]}>{r.verdict}</Pill>{r.our_status && <Pill kind={r.our_status === 'grounded' ? 'ok' : 'bad'}>verifier: {r.our_status}</Pill>}</div>
            <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>{r.reason}</div>
          </div>
        ))}
      </aside>
    </div>
  )
}

/** "Audit with my key": a second opinion from the user's own model on each claim's evidence. Never uses server keys. */
export default function AuditButton({ tenant, claims, size = 'sm', label = 'Audit with my key' }) {
  const { userKeys, openLlm } = useApp()
  const [busy, setBusy] = useState(false)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const go = async () => {
    if (!userKeys.length) { openLlm(); return }
    setBusy(true); setErr('')
    try { setData(await api.audit(tenant, claims, userKeys)) } catch (e) { setErr(String(e.message || e).replace(/^\d+\s*/, '').replace(/^\{"detail":"?|"?\}$/g, '')) }
    setBusy(false)
  }
  return (
    <>
      <button className={`btn ghost ${size}`} onClick={go} disabled={busy || !claims?.length}
        title={userKeys.length ? 'Ask your own model whether the evidence supports each claim' : 'Add your own API key first'}>
        {busy ? <Spinner /> : <Icon name="scale" size={14} />} {label}
      </button>
      {err && <span className="chip bad" title={err}>audit failed</span>}
      {data && <AuditDrawer data={data} claims={claims} onClose={() => setData(null)} />}
    </>
  )
}
