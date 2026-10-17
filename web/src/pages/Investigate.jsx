import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useApp, isRepo } from '../lib/ctx'
import IncidentView from '../components/IncidentView'
import Icon from '../components/ui/Icon'
import { Pill, Spinner } from '../components/Common'

export default function Investigate({ embedded = false }) {
  const { tenant, graphOn, useLlm, userKeys, bumpMemory } = useApp()
  const [alerts, setAlerts] = useState([])
  const [active, setActive] = useState(null)
  const [run, setRun] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const repo = isRepo(tenant)
  const resultsRef = useRef(null)

  useEffect(() => {
    setRun(null); setErr('')
    api.alerts(tenant).then((a) => { a.sort((x, y) => x.id.localeCompare(y.id)); setAlerts(a); setActive(a[0]?.id || null) }).catch((e) => setErr(String(e)))
  }, [tenant])

  const go = async (id = active) => {
    if (!id) return
    setBusy(true); setErr(''); setActive(id)
    // on narrow screens the results stack under the list: bring them into view straight away
    if (window.innerWidth < 1000) resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    try { setRun(await api.run({ tenant, alert_id: id, graph_enabled: graphOn, use_llm: useLlm }, userKeys)); bumpMemory() } catch (e) { setErr(String(e)) }
    setBusy(false)
  }

  return (
    <div>
      {!embedded && <div className="page-head"><h2>{repo ? 'Investigate a regression' : 'Investigate an incident'}</h2>
        <p>{repo ? 'Reported issues are generated from this repository\'s hotspots and most-depended-on modules. The crew traces each to the likely commit, its owner and the best reviewers.'
          : 'Three agents hand work to each other through the graph: triage sizes the alert, the investigator walks dependencies to the likely cause, the remediator proposes actions and learns from the outcome.'}</p></div>}
      <div className="split">
        <aside className="card rail">
          <h3>{repo ? 'Reported issues' : 'Live alerts'}</h3>
          <button className="btn rail-run" disabled={busy || !active} onClick={() => go()}>
            {busy ? <><Spinner /> Crew working…</> : <><Icon name="play" size={14} /> Run the crew</>}
          </button>
          <div className="alert-list">
            {alerts.map((a) => (
              <button key={a.id} className={`alert ${active === a.id ? 'active' : ''}`} onClick={() => setActive(a.id)} onDoubleClick={() => go(a.id)}>
                <b>{a.service}</b><span className="muted mono" style={{ fontSize: 11.5 }}>{a.id}</span>
                <div className="row" style={{ marginTop: 6, gap: 5 }}><Pill kind={a.severity === 1 ? 'bad' : 'warn'}>sev {a.severity}</Pill><Pill>{a.signal}</Pill></div>
              </button>
            ))}
            {!alerts.length && <div className="muted">No alerts for this dataset.</div>}
          </div>
          <p className="faint" style={{ fontSize: 11.5, margin: '10px 0 0' }}>Select an alert, then run. Double-click an alert to run it immediately.</p>
          {err && <div className="banner" style={{ marginTop: 10, fontSize: 12.5 }}>{err}</div>}
        </aside>
        <div ref={resultsRef} style={{ scrollMarginTop: 72 }}>
          {busy && (
            <div className="card working">
              <div className="row"><Spinner /><b>The crew is working</b></div>
              <div className="stepper" style={{ marginTop: 10 }}>
                {['Triage sizes the alert', 'Investigator walks the graph', 'Verifier checks every claim', 'Remediator proposes actions'].map((l, i) => (
                  <span key={l} style={{ display: 'contents' }}><span className="s now" style={{ animationDelay: `${i * 0.25}s` }}>{l}</span>{i < 3 && <span className="sep" />}</span>))}
              </div>
            </div>
          )}
          {!busy && <IncidentView tenant={tenant} run={run} onApproved={() => go()} />}
        </div>
      </div>
    </div>
  )
}
