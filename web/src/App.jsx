import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, setByo } from './api'
import { AppCtx, isRepo } from './lib/ctx'
import { go, useRoute } from './lib/router'
import { useTheme } from './lib/theme'
import Landing from './pages/Landing'
import Investigate from './pages/Investigate'
import Lab from './pages/Lab'
import Method from './pages/Method'
import { AskPage, MemoryPage, ProofPage } from './pages/Simple'
import LLMSettings, { loadLLM } from './components/LLMSettings'
import DbSettings, { loadDb } from './components/DbSettings'
import Icon from './components/ui/Icon'
import Logo from './components/ui/Logo'
import { Pill } from './components/Common'

const KEY = 'traceback.ws.v1'
const readIds = () => { try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] } }

/** Workspaces this browser created: ids in localStorage, details from the server (which never lists other people's). */
function useWorkspaces() {
  const [ids, setIds] = useState(readIds)
  const [list, setList] = useState([])
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(ids)) } catch { /* ignore */ } }, [ids])
  const refresh = useCallback(() => api.wsList(ids).then((l) => { setList(l); setIds((cur) => cur.filter((i) => l.some((w) => w.id === i))) }).catch(() => {}), [ids.join(',')])
  useEffect(() => { refresh() }, [refresh])
  const busy = list.some((w) => w.status === 'queued' || w.status === 'running')
  useEffect(() => { if (!busy) return undefined; const t = setInterval(refresh, 1000); return () => clearInterval(t) }, [busy, refresh])
  return {
    workspaces: list,
    addWorkspace: (w) => { setList((l) => [w, ...l.filter((x) => x.id !== w.id)]); setIds((c) => [w.id, ...c.filter((i) => i !== w.id)]) },
    removeWorkspace: (id) => { setList((l) => l.filter((w) => w.id !== id)); setIds((c) => c.filter((i) => i !== id)) },
  }
}

const NAV = [['investigate', 'search', 'Investigate'], ['ask', 'message', 'Company brain'], ['memory', 'database', 'Agent memory'], ['lab', 'github', 'Analyze your code'], ['proof', 'chart', 'Proof'], ['method', 'book', 'Method']]
const TITLES = { investigate: 'Investigate', ask: 'Company brain', memory: 'Agent memory', lab: 'Analyze your code', proof: 'Proof', method: 'Method' }

export default function App() {
  const route = useRoute()
  const theme = useTheme()
  const [health, setHealth] = useState(null)
  const [tenant, setTenant] = useState('helix')
  const [graphOn, setGraphOn] = useState(true)
  const [llm, setLlm] = useState(loadLLM)
  const [llmOpen, setLlmOpen] = useState(false)
  const [memKey, setMemKey] = useState(0)
  const [menu, setMenu] = useState(false)
  const [db, setDb] = useState(loadDb)
  const [dbOpen, setDbOpen] = useState(false)
  const wsApi = useWorkspaces()

  useEffect(() => { api.health().then(setHealth).catch(() => setHealth({ ok: false })) }, [])
  useEffect(() => { setMenu(false) }, [route.path])
  useEffect(() => { if (isRepo(tenant) && !wsApi.workspaces.some((w) => w.tenant === tenant && w.status === 'ready') && wsApi.workspaces.length) setTenant('helix') }, [wsApi.workspaces])

  const byoReady = !!db.host
  // Tell the API layer where each dataset lives *during render*, not in an effect: child effects (e.g. the lab auto-starting an analysis
  // from ?repo=) run before this component's own effects, and a request sent too early would go to the shared server instead of the
  // user's database.
  const mine = wsApi.workspaces.filter((w) => w.byo_db)
  setByo(byoReady ? db : null, db.enabled, mine.map((w) => w.tenant), mine.map((w) => w.id))
  const userKeys = llm.configs.filter((c) => c.api_key)
  const useLlm = !llm.enabled ? false : userKeys.length ? true : null
  const ctx = useMemo(() => ({ tenant, setTenant, graphOn, useLlm, userKeys, memKey, openLlm: () => setLlmOpen(true), openDb: () => setDbOpen(true), db, byoReady, bumpMemory: () => setMemKey((k) => k + 1), ...wsApi, theme }),
    [tenant, graphOn, useLlm, llm, memKey, wsApi.workspaces, theme.dark, db])

  if (route.path === '/' || route.path === '') return <AppCtx.Provider value={ctx}><Landing theme={theme} /></AppCtx.Provider>

  const page = (route.path.split('/')[2] || 'investigate')
  const ready = wsApi.workspaces.filter((w) => w.status === 'ready')
  const llmLabel = !llm.enabled ? 'LLM off' : userKeys.length ? `${userKeys.length} key${userKeys.length > 1 ? 's' : ''}` : health?.llm ? 'server keys' : 'offline planner'

  return (
    <AppCtx.Provider value={ctx}>
      <div className="shell">
        <aside className={`sidebar ${menu ? 'open' : ''}`}>
          <a href="#/" style={{ textDecoration: 'none' }}><Logo /></a>
          <div className="ws-switch">
            <label htmlFor="ws">Dataset</label>
            <select id="ws" value={tenant} onChange={(e) => setTenant(e.target.value)}>
              <optgroup label="Demo company (synthetic)">{(health?.tenants || ['helix', 'orbit']).map((t) => <option key={t} value={t}>{t}</option>)}</optgroup>
              {ready.length > 0 && <optgroup label="Your repositories">{ready.map((w) => <option key={w.id} value={w.tenant} disabled={w.byo_db && !byoReady}>{w.label}{w.byo_db ? ' · your DB' : ''}</option>)}</optgroup>}
            </select>
          </div>
          <nav className="nav">
            {NAV.map(([k, ic, l]) => <a key={k} href={`#/app/${k}`} className={page === k ? 'active' : ''}><Icon name={ic} size={16} />{l}</a>)}
            <div className="sep" /><small>Elsewhere</small>
            <a href="#/"><Icon name="target" size={16} />Overview</a>
          </nav>
          <div className="side-foot">
            <button className="btn ghost sm" onClick={() => setDbOpen(true)} title="Where new analyses are stored"><Icon name="database" size={14} />Data: {db.enabled && db.host ? 'your FalkorDB' : 'shared server'}</button>
            <button className="btn ghost sm" onClick={() => setLlmOpen(true)}><Icon name="key" size={14} />LLM: {llmLabel}</button>
            <button className="btn quiet sm" onClick={theme.toggle}><Icon name={theme.dark ? 'sun' : 'moon'} size={14} />{theme.dark ? 'Light' : 'Dark'} theme</button>
          </div>
        </aside>
        <div className="main">
          <header className="topbar">
            <button className="btn quiet icon menu-btn" onClick={() => setMenu(!menu)} aria-label="Menu"><Icon name="menu" /></button>
            <h1>{TITLES[page] || 'Console'}</h1><span className="crumb hide-sm">· {isRepo(tenant) ? (wsApi.workspaces.find((w) => w.tenant === tenant)?.label || 'repository') : `${tenant} (synthetic)`}</span>
            <span className="spacer" />
            <button className={`switch ${graphOn ? '' : 'off'}`} onClick={() => setGraphOn(!graphOn)} title="Kill the graph: the product falls back to documents-only retrieval">
              <span className="dot" />FalkorDB graph {graphOn ? 'on' : 'off'}
            </button>
            <Pill kind={health?.ok ? 'ok' : 'bad'}>{health?.ok ? 'connected' : 'FalkorDB down'}</Pill>
          </header>
          <main className="page">
            {page === 'investigate' && <Investigate />}
            {page === 'ask' && <AskPage />}
            {page === 'memory' && <MemoryPage />}
            {page === 'lab' && <Lab query={route.query} />}
            {page === 'proof' && <ProofPage />}
            {page === 'method' && <Method />}
          </main>
        </div>
        <DbSettings open={dbOpen} onClose={() => setDbOpen(false)} db={db} setDb={setDb} privateAllowed={health?.byo_private_allowed} />
        <LLMSettings open={llmOpen} onClose={() => setLlmOpen(false)} llm={llm} setLlm={setLlm} />
      </div>
    </AppCtx.Provider>
  )
}
