import { useEffect, useState } from 'react'
import { api } from './api'
import AskView from './components/AskView'
import IncidentView from './components/IncidentView'
import MemoryView from './components/MemoryView'
import ProofView from './components/ProofView'
import { Pill, fmtTs } from './components/Common'
import LLMSettings, { loadLLM } from './components/LLMSettings'

const TABS = [['incident', 'Incident console'], ['ask', 'Company brain'], ['memory', 'Agent memory'], ['proof', 'Proof']]

export default function App() {
  const [health, setHealth] = useState(null)
  const [tenant, setTenant] = useState('helix')
  const [graphOn, setGraphOn] = useState(true)
  const [tab, setTab] = useState('incident')
  const [alerts, setAlerts] = useState([])
  const [activeAlert, setActiveAlert] = useState(null)
  const [run, setRun] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [memKey, setMemKey] = useState(0)
  const [llm, setLlm] = useState(loadLLM)
  const [llmOpen, setLlmOpen] = useState(false)
  const userKeys = llm.configs.filter((c) => c.api_key)
  // true: use my keys · null: let the server decide (its own keys, else offline) · false: never call an LLM
  const useLlm = !llm.enabled ? false : userKeys.length ? true : null

  useEffect(() => { api.health().then(setHealth).catch((e) => setErr(String(e))) }, [])
  useEffect(() => { setRun(null); api.alerts(tenant).then((a) => { setAlerts(a); setActiveAlert(a.sort((x, y) => x.id.localeCompare(y.id))[0]?.id) }).catch((e) => setErr(String(e))) }, [tenant])

  const go = async (id = activeAlert) => {
    if (!id) return
    setBusy(true); setErr(''); setActiveAlert(id)
    try { setRun(await api.run({ tenant, alert_id: id, graph_enabled: graphOn, use_llm: useLlm }, userKeys)); setMemKey((k) => k + 1) } catch (e) { setErr(String(e)) }
    setBusy(false)
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><circle cx="8" cy="24" r="4" fill="#2dd4bf" /><circle cx="24" cy="8" r="4" fill="#60a5fa" /><path d="M8 24 L24 8" stroke="#e2e8f0" strokeWidth="2" /></svg>
          TRACEBACK <small>the agent that can't say anything it can't trace</small>
        </div>
        <div className="spacer" />
        <label className="muted">Tenant&nbsp;
          <select value={tenant} onChange={(e) => setTenant(e.target.value)}>{(health?.tenants || ['helix', 'orbit']).map((t) => <option key={t}>{t}</option>)}</select>
        </label>
        <button className={`switch ${graphOn ? '' : 'off'}`} onClick={() => setGraphOn(!graphOn)} title="Kill the graph: the product falls back to docs-only retrieval">
          <span className="dot" /> FalkorDB graph: {graphOn ? 'ON' : 'OFF'}
        </button>
        <button className="switch" onClick={() => setLlmOpen(true)} title="Bring your own API keys; automatic failover between providers">
          LLM: {!llm.enabled ? 'off' : userKeys.length ? `${userKeys.length} key${userKeys.length > 1 ? 's' : ''}` : health?.llm ? 'server keys' : 'offline planner'} ⚙
        </button>
        <Pill kind={health?.ok ? 'ok' : 'bad'}>{health?.ok ? 'FalkorDB connected' : 'FalkorDB down'}</Pill>
      </header>

      <main className="layout">
        <aside>
          <div className="card">
            <h3>Live alerts · {tenant}</h3>
            {alerts.map((a) => (
              <button key={a.id} className={`alert ${activeAlert === a.id ? 'active' : ''}`} onClick={() => setActiveAlert(a.id)}>
                <b>{a.service}</b>
                <span className="muted mono">{a.id}</span>
                <div className="row" style={{ marginTop: 4 }}>
                  <Pill kind={a.severity === 1 ? 'bad' : 'warn'}>sev {a.severity}</Pill><Pill>{a.signal}</Pill><Pill>tier {a.tier}</Pill>
                </div>
              </button>
            ))}
            <button className="btn" style={{ width: '100%', marginTop: 4 }} disabled={busy || !activeAlert} onClick={() => { setTab('incident'); go() }}>
              {busy ? 'Crew working…' : 'Run the crew'}
            </button>
            {err && <div className="banner" style={{ marginTop: 10, fontSize: 12 }}>{err}</div>}
          </div>
          <div className="card muted" style={{ fontSize: 12 }}>
            <b style={{ color: 'var(--text)' }}>How to read this</b>
            <p>Every claim lists graph edge ids. A verifier re-queries FalkorDB and withholds anything it can't confirm. Flip the switch above to see the product without its graph.</p>
          </div>
        </aside>

        <section>
          <nav className="tabs">{TABS.map(([k, label]) => <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>)}</nav>
          {tab === 'incident' && <IncidentView tenant={tenant} run={run} onApproved={() => go()} />}
          {tab === 'ask' && <AskView tenant={tenant} graphOn={graphOn} useLlm={useLlm} keys={userKeys} />}
          {tab === 'memory' && <MemoryView tenant={tenant} refreshKey={memKey} />}
          {tab === 'proof' && <ProofView />}
        </section>
      </main>
      <LLMSettings open={llmOpen} onClose={() => setLlmOpen(false)} llm={llm} setLlm={setLlm} />
    </div>
  )
}
