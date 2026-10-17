import { useState } from 'react'
import { api } from '../api'
import { download, slug } from '../lib/report'
import Icon from './ui/Icon'
import { Spinner } from './Common'

/** Download an evidence bundle: the claims' facts in a form you can re-verify on your own machine, with no server involved. */
export default function BundleButton({ tenant, claims, name = 'evidence', size = 'sm', label = 'Evidence bundle' }) {
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const go = async () => {
    setBusy(true)
    try {
      const b = await api.evidenceBundle(tenant, claims)
      const file = `${slug(name)}-evidence.json`
      download(file, JSON.stringify(b, null, 1), 'application/json')
      setDone({ file, cmd: `python -m tbk.cli verify ${file} --show-sources` })
      setTimeout(() => setDone(null), 14000)
    } finally { setBusy(false) }
  }
  return (
    <>
      <button className={`btn ghost ${size}`} onClick={go} disabled={busy || !claims?.length} title="Download evidence you can re-verify yourself, with no server, database or LLM">
        {busy ? <Spinner /> : <Icon name="shield" size={14} />} {label}
      </button>
      {done && (
        <div className="toast" role="status">
          <b>Saved {done.file}</b>
          <div className="muted" style={{ fontSize: 12.5, margin: '4px 0 6px' }}>Re-verify it on your machine, no trust in our server needed:</div>
          <code className="mono" style={{ display: 'block', background: 'var(--bg-elev)', padding: '6px 8px', borderRadius: 6 }}>{done.cmd}</code>
          <button className="btn quiet sm" style={{ marginTop: 6 }} onClick={() => navigator.clipboard.writeText(done.cmd)}>Copy command</button>
        </div>
      )}
    </>
  )
}
