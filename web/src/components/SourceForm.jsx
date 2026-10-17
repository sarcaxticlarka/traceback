import { useRef, useState } from 'react'
import { zipSync } from 'fflate'
import { api } from '../api'
import Icon from './ui/Icon'
import { Spinner } from './Common'

const SKIP = new Set(['node_modules', '.git', 'vendor', 'dist', 'build', 'out', 'target', '__pycache__', '.venv', 'venv', '.next', 'coverage', '.tox', 'third_party'])
const OK = /\.(py|js|jsx|ts|tsx|mjs|cjs|go|java|kt|rs|rb|php|c|h|cc|cpp|hpp|cs|swift|scala|vue|svelte|md|rst|txt|adoc)$|(^|\/)CODEOWNERS$/i
const SAMPLE_BUNDLE = `{
  "name": "acme-prod",
  "services": [
    {"name": "checkout-api", "tier": 1, "owner": "payments"},
    {"name": "payments-api", "tier": 0, "owner": "payments"},
    {"name": "ledger-store", "tier": 0, "owner": "platform"}
  ],
  "dependencies": [
    {"from": "checkout-api", "to": "payments-api"},
    {"from": "payments-api", "to": "ledger-store"}
  ],
  "teams": [{"name": "payments", "members": ["Ana Ruiz", "Lee Park"]}, {"name": "platform", "members": ["Sam Ode"]}],
  "deploys": [{"service": "ledger-store", "sha": "a1b2c3d", "author": "Sam Ode", "ts": 1760000000, "summary": "bump driver"}],
  "alerts": [{"service": "checkout-api", "signal": "high-latency", "ts": 1760003600}]
}`

async function zipFolder(files, onProgress) {
  const entries = {}
  let total = 0, kept = 0, skipped = 0
  for (const f of files) {
    const rel = f.webkitRelativePath || f.name
    if (rel.split('/').some((p) => SKIP.has(p)) || !OK.test(rel) || f.size > 400_000) { skipped++; continue }
    const buf = new Uint8Array(await f.arrayBuffer())
    total += buf.length
    if (total > 90_000_000) break
    entries[rel] = [buf, { level: 1 }]
    kept++
    if (kept % 200 === 0) onProgress?.(kept)
  }
  if (!kept) throw new Error('No source files found in that folder (supported: Python, JS/TS, Go, Java/Kotlin, C/C++, ...).')
  return { blob: new Blob([zipSync(entries)], { type: 'application/zip' }), kept, skipped, total }
}

export default function SourceForm({ initialUrl = '', onCreated }) {
  const [mode, setMode] = useState('github')
  const [url, setUrl] = useState(initialUrl)
  const [bundle, setBundle] = useState(SAMPLE_BUNDLE)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [over, setOver] = useState(false)
  const dirRef = useRef(), zipRef = useRef()

  const run = async (fn) => {
    setBusy(true); setErr('')
    try { onCreated(await fn()) } catch (e) { setErr(String(e.message || e).replace(/^\d+\s*/, '').replace(/^\{"detail":"?|"?\}$/g, '')) }
    setBusy(false); setMsg('')
  }
  const github = (e) => { e?.preventDefault(); run(() => api.wsGithub(url.trim())) }
  const folder = (fl) => run(async () => {
    setMsg('Reading files in your browser…')
    const { blob, kept } = await zipFolder(Array.from(fl), (n) => setMsg(`Packed ${n} files…`))
    setMsg(`Uploading ${kept} files (${(blob.size / 1e6).toFixed(1)} MB)…`)
    const label = (fl[0].webkitRelativePath || '').split('/')[0] || 'folder'
    return api.wsUpload(new File([blob], label + '.zip'), label)
  })
  const zip = (f) => run(() => api.wsUpload(f, f.name.replace(/\.zip$/i, '')))
  const bundleGo = () => run(async () => api.wsBundle(JSON.parse(bundle)))

  return (
    <div className="card">
      <div className="row between" style={{ marginBottom: 14 }}>
        <div className="segmented" role="tablist">
          {[['github', 'github', 'GitHub URL'], ['folder', 'folder', 'Folder / zip'], ['bundle', 'database', 'JSON bundle']].map(([k, ic, l]) => (
            <button key={k} className={mode === k ? 'active' : ''} onClick={() => setMode(k)} role="tab"><Icon name={ic} size={14} />{l}</button>))}
        </div>
        <span className="muted" style={{ fontSize: 12.5 }}>Read-only analysis · your code is never executed</span>
      </div>

      {mode === 'github' && (
        <form onSubmit={github}>
          <div className="row" style={{ flexWrap: 'nowrap' }}>
            <input type="url" required placeholder="https://github.com/owner/repo" value={url} onChange={(e) => setUrl(e.target.value)} style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }} />
            <button className="btn" disabled={busy}>{busy ? <Spinner /> : <Icon name="search" size={15} />} Analyze</button>
          </div>
          <div className="suggest">
            {['pallets/click', 'expressjs/express', 'gin-gonic/gin', 'tiangolo/fastapi'].map((r) => <button type="button" key={r} onClick={() => setUrl(`https://github.com/${r}`)}>{r}</button>)}
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>Public repositories only. Shallow clone (last 1,500 commits), no submodules, no hooks. History provides owners, experts and churn.</p>
        </form>
      )}

      {mode === 'folder' && (
        <div>
          <div className={`drop ${over ? 'over' : ''}`} onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f && /\.zip$/i.test(f.name)) zip(f) }}>
            <Icon name="upload" size={22} />
            <p style={{ margin: '8px 0 12px' }}>Choose a project folder (zipped in your browser, only source and docs are sent) or drop a <code>.zip</code></p>
            <div className="row" style={{ justifyContent: 'center' }}>
              <button className="btn" disabled={busy} onClick={() => dirRef.current.click()}><Icon name="folder" size={15} /> Choose folder</button>
              <button className="btn ghost" disabled={busy} onClick={() => zipRef.current.click()}>Choose .zip</button>
            </div>
            <input ref={dirRef} type="file" webkitdirectory="" directory="" multiple hidden onChange={(e) => e.target.files.length && folder(e.target.files)} />
            <input ref={zipRef} type="file" accept=".zip" hidden onChange={(e) => e.target.files[0] && zip(e.target.files[0])} />
          </div>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>Uploads contain no <code>.git</code> history (we never read git data from untrusted archives), so you get structure, dependencies and docs, but not owners-by-commits. Up to 100 MB. node_modules, build output and binaries are skipped.</p>
        </div>
      )}

      {mode === 'bundle' && (
        <div>
          <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>Describe services, dependencies, teams, deploys and alerts exported from your catalogue (Backstage, deploy tool, PagerDuty). Same agents, same verifier. Edit the sample:</p>
          <textarea rows={13} value={bundle} onChange={(e) => setBundle(e.target.value)} spellCheck={false} />
          <div className="row" style={{ marginTop: 10 }}><button className="btn" disabled={busy} onClick={bundleGo}><Icon name="database" size={15} /> Build graph</button></div>
        </div>
      )}
      {msg && <div className="row" style={{ marginTop: 10 }}><Spinner /> <span className="muted">{msg}</span></div>}
      {err && <div className="banner" style={{ marginTop: 12 }}>{err}</div>}
    </div>
  )
}
