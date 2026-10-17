import { useEffect, useState } from 'react'
import { api } from '../api'
import { Bar, LineChart, Pill, fmtTs } from './Common'

export default function MemoryView({ tenant, refreshKey }) {
  const [runbooks, setRunbooks] = useState([])
  const [facts, setFacts] = useState([])
  const [episodes, setEpisodes] = useState([])
  const [curve, setCurve] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () => {
    api.runbooks(tenant).then(setRunbooks).catch(() => {})
    api.facts(tenant).then(setFacts).catch(() => {})
    api.episodes(tenant).then(setEpisodes).catch(() => {})
  }
  useEffect(() => { load(); api.learning(tenant).then(setCurve).catch(() => setCurve(null)) }, [tenant, refreshKey])

  const simulate = async () => { setBusy(true); try { setCurve(await api.runLearning(tenant)); load() } finally { setBusy(false) } }
  const bySignal = runbooks.reduce((m, r) => ((m[r.signal] ||= []).push(r), m), {})

  return (
    <div>
      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0 }}>Procedural memory learns · runbook choice vs. incidents handled</h3>
          <button className="btn" onClick={simulate} disabled={busy}>{busy ? 'Simulating…' : 'Cold-start & re-learn (240 incidents × 5 seeds)'}</button>
        </div>
        <p className="muted">Outcomes are written back to Runbook nodes (attempts, successes) and linked to the Episode that used them. Ranking is a pure Cypher query over those counters; success is simulated from hidden per-runbook rates that never enter the graph.</p>
        {curve?.curve?.length ? (
          <LineChart xLabel="incidents handled (rolling window)"
            series={[{ name: 'picked the better runbook', color: '#2dd4bf', points: curve.curve.map((c) => ({ x: c.incidents, y: c.picked_best })) },
              { name: 'incident resolved', color: '#60a5fa', points: curve.curve.map((c) => ({ x: c.incidents, y: c.success_rate })) }]}
            refs={[{ y: curve.expected_success_best, label: 'always-best policy', color: '#34d399' }, { y: curve.expected_success_random, label: 'random policy', color: '#f87171' }]} />
        ) : <div className="empty">Run the simulation to draw the learning curve.</div>}
      </div>

      <div className="grid2" style={{ marginTop: 12 }}>
        <div className="card">
          <h3>Runbooks (procedural)</h3>
          <div className="scroll"><table><thead><tr><th>Signal / runbook</th><th>Record</th><th>Rate</th></tr></thead><tbody>
            {Object.entries(bySignal).map(([sig, rbs]) => rbs.map((r, i) => (
              <tr key={r.id}><td>{i === 0 && <b>{sig}</b>}<div className="muted mono">{r.title.replace(/^.*\(|\)$/g, '')}</div></td>
                <td className="mono">{r.successes}/{r.attempts}</td>
                <td style={{ width: 110 }}><Bar value={(r.successes + 1) / (r.attempts + 2)} /></td></tr>
            )))}
          </tbody></table></div>
        </div>
        <div>
          <div className="card">
            <h3>Semantic memory · facts with validity windows</h3>
            <div className="scroll" style={{ maxHeight: 200 }}>
              {facts.map((f) => (
                <div key={f.id} style={{ marginBottom: 8 }}>{f.text}
                  <div className="row"><Pill>{f.service}</Pill><span className="muted mono">since {fmtTs(f.since)}</span>
                    {f.supersedes > 0 && <Pill kind="warn">supersedes {f.supersedes}</Pill>}</div></div>
              ))}
              {!facts.length && <div className="muted">None yet. Run an incident.</div>}
            </div>
          </div>
          <div className="card">
            <h3>Episodic memory · recent agent runs</h3>
            <div className="scroll" style={{ maxHeight: 200 }}>
              <table><tbody>
                {episodes.map((e) => (
                  <tr key={e.id}><td><Pill kind={e.agent === 'investigator' ? 'ok' : e.agent === 'remediator' ? 'warn' : 'blue'}>{e.agent}</Pill></td>
                    <td>{e.goal}<div className="muted mono">{e.tool_calls} tool calls · {e.outcome} · {Math.round(e.latency_ms)} ms</div></td></tr>
                ))}
              </tbody></table>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
