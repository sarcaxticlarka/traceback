import { useEffect, useState } from 'react'
import { api } from '../api'
import { Pill } from './Common'

export const STORAGE_KEY = 'traceback.llm.v1'

export function loadLLM() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (raw?.remember) return { enabled: raw.enabled !== false, remember: true, configs: raw.configs || [] }
  } catch { /* storage unavailable or corrupt: start empty */ }
  return { enabled: true, remember: false, configs: [] }
}

export function saveLLM(llm) {
  try {
    if (llm.remember) localStorage.setItem(STORAGE_KEY, JSON.stringify(llm))
    else localStorage.removeItem(STORAGE_KEY)
  } catch { /* ignore */ }
}

export default function LLMSettings({ open, onClose, llm, setLlm }) {
  const [presets, setPresets] = useState([])
  const [serverDefault, setServerDefault] = useState([])
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) api.llmProviders().then((p) => { setPresets(p.presets); setServerDefault(p.server_default) }).catch(() => {})
  }, [open])
  if (!open) return null

  const update = (next) => { const v = { ...llm, ...next }; setLlm(v); saveLLM(v) }
  const setRow = (i, patch) => update({ configs: llm.configs.map((c, k) => (k === i ? { ...c, ...patch } : c)) })
  const move = (i, d) => {
    const cs = [...llm.configs]; const j = i + d
    if (j < 0 || j >= cs.length) return
    ;[cs[i], cs[j]] = [cs[j], cs[i]]; update({ configs: cs })
  }
  const add = () => update({ configs: [...llm.configs, { provider: presets[0]?.id || 'anthropic', api_key: '', model: '', base_url: '' }] })
  const test = async () => {
    setBusy(true); setResults(null)
    try { setResults(await api.llmTest(llm.configs.filter((c) => c.api_key))) } catch (e) { setResults([{ ok: false, provider: 'request', error: String(e) }]) }
    setBusy(false)
  }
  const preset = (id) => presets.find((p) => p.id === id)

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal card" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="LLM providers">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0 }}>LLM providers · bring your own keys</h3>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
        <p className="muted">
          Keys are sent with each request, used for that request only, and never stored or logged on the server. Providers are
          tried <b>top to bottom</b>: if one hits a rate limit, runs out of quota, is overloaded or rejects the key, the next one
          takes over mid-investigation. Any provider with an OpenAI-compatible API works.
        </p>
        {serverDefault.length > 0 && <p className="muted">Server also has default keys for: {serverDefault.map((s) => <Pill key={s}>{s}</Pill>)} (used after yours).</p>}

        <label className="row" style={{ marginBottom: 8 }}>
          <input type="checkbox" checked={llm.enabled} onChange={(e) => update({ enabled: e.target.checked })} />
          Use an LLM to plan investigations and answer free-form questions (otherwise the offline playbook runs)
        </label>

        {llm.configs.map((c, i) => (
          <div key={i} className="llm-row">
            <span className="muted mono">{i + 1}</span>
            <select value={c.provider} onChange={(e) => setRow(i, { provider: e.target.value, model: '' })}>
              {presets.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
            <input type="text" placeholder={`model (default ${preset(c.provider)?.default_model || '—'})`} value={c.model}
              onChange={(e) => setRow(i, { model: e.target.value })} />
            <input type="password" autoComplete="off" placeholder="API key" value={c.api_key} onChange={(e) => setRow(i, { api_key: e.target.value })} />
            {preset(c.provider)?.custom_url && <input type="text" placeholder="base URL, e.g. http://localhost:11434/v1" value={c.base_url}
              onChange={(e) => setRow(i, { base_url: e.target.value })} />}
            <div className="row" style={{ gap: 4 }}>
              <button className="btn ghost" title="Higher priority" onClick={() => move(i, -1)}>↑</button>
              <button className="btn ghost" title="Lower priority" onClick={() => move(i, 1)}>↓</button>
              <button className="btn ghost" title="Remove" onClick={() => update({ configs: llm.configs.filter((_, k) => k !== i) })}>✕</button>
            </div>
          </div>
        ))}

        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn ghost" onClick={add}>+ Add provider</button>
          <button className="btn" onClick={test} disabled={busy || !llm.configs.some((c) => c.api_key)}>{busy ? 'Testing…' : 'Test keys'}</button>
        </div>
        {results && (
          <div style={{ marginTop: 10 }}>
            {results.map((r, i) => (
              <div className="check" key={i}>
                <Pill kind={r.ok ? 'ok' : 'bad'}>{r.ok ? 'works' : r.kind || 'failed'}</Pill>
                <div>{r.provider}{r.model ? ` · ${r.model}` : ''}<div className="muted mono">{r.ok ? `${r.ms} ms` : r.error}</div></div>
              </div>
            ))}
          </div>
        )}

        <label className="row" style={{ marginTop: 14 }}>
          <input type="checkbox" checked={llm.remember} onChange={(e) => update({ remember: e.target.checked })} />
          Remember my keys in this browser (localStorage)
        </label>
        {llm.remember && <div className="muted" style={{ fontSize: 12 }}>Stored unencrypted in this browser only. Don't enable on a shared computer.</div>}
      </div>
    </div>
  )
}

/** Small summary of which provider answered and any failovers that happened. */
export function LLMBadge({ info }) {
  if (!info) return null
  return (
    <span className="row" style={{ gap: 6 }}>
      {info.used ? <Pill kind="ok">LLM: {info.used}</Pill> : <Pill kind="bad">LLM unavailable</Pill>}
      {(info.failovers || []).map((f, i) => (
        <Pill key={i} kind="warn" >{f.provider}: {f.kind.replace('_', ' ')} → switched</Pill>
      ))}
    </span>
  )
}
