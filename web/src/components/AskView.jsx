import { useState } from 'react'
import { api } from '../api'
import { GroundedBadge, Pill } from './Common'

const SAMPLES = [
  'Which teams own services that would be impacted if auth-service fails?',
  'What is the full blast radius if db-proxy fails?',
  'Which services are owned by a team with no current members?',
  'Who authored the deploy most likely responsible for alert:LIVE-1?',
  'Which services does payments-api directly depend on?',
  'Who are the current members of the team that owns checkout-api?',
  'What is the current decision constraining ledger-store?',
]

export default function AskView({ tenant, graphOn }) {
  const [question, setQuestion] = useState(SAMPLES[0])
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const go = async (text = question) => {
    setBusy(true); setErr('')
    try { setRes(await api.ask({ tenant, question: text, graph_enabled: graphOn })) } catch (e) { setErr(String(e)) }
    setBusy(false)
  }

  return (
    <div>
      <div className="card">
        <h3>Company brain · ask anything about owners, dependencies, decisions, time</h3>
        <div className="row">
          <div style={{ flex: 1, minWidth: 260 }}>
            <input type="text" value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()} />
          </div>
          <button className="btn" onClick={() => go()} disabled={busy}>{busy ? 'Thinking…' : 'Ask'}</button>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          {SAMPLES.map((s) => <button key={s} className="chip" style={{ cursor: 'pointer', background: 'transparent' }}
            onClick={() => { setQuestion(s); go(s) }}>{s.length > 52 ? s.slice(0, 51) + '…' : s}</button>)}
        </div>
        {err && <div className="banner" style={{ marginTop: 10 }}>{err}</div>}
      </div>

      {res && (
        <div className="ask-grid" style={{ marginTop: 12 }}>
          <div className="card">
            <h3>Graph agent (FalkorDB)</h3>
            {res.graph_enabled === false ? <div className="banner">Graph is OFF. This agent has no tools to call.</div> : (
              <>
                <div className="row"><Pill kind="blue">intent: {res.intent}</Pill><GroundedBadge pct={res.verification.grounded_pct} n={res.verification.n_claims} /><span className="muted mono">{res.ms} ms</span></div>
                <div className="answer">{res.answers?.length ? res.answers.map((a) => <Pill key={a} kind="ok">{a}</Pill>) : <span className="muted">{res.text || res.error || 'No answer.'}</span>}</div>
                <h3 style={{ marginTop: 14 }}>How it got there</h3>
                {res.steps.map((s, i) => (
                  <div className="step" key={i}><span className="n mono">{i + 1}</span>
                    <div><span className="mono" style={{ color: 'var(--accent)' }}>{s.tool}</span> <span className="muted mono">{JSON.stringify(s.args)}</span>
                      <div className="muted" style={{ fontSize: 12 }}>{s.summary} · {s.cypher_ref}</div></div>
                    <span className="muted mono">{s.ms} ms</span></div>
                ))}
                <h3 style={{ marginTop: 14 }}>Evidence (verified claims)</h3>
                <div className="scroll" style={{ maxHeight: 260 }}>
                  {res.verification.claims.map((c, i) => (
                    <div key={i} className={`claim ${c.status !== 'grounded' ? 'withheld' : ''}`}>{c.text}
                      <div className="meta"><Pill kind={c.status === 'grounded' ? 'ok' : 'bad'}>{c.status}</Pill>
                        <span className="muted mono">{(c.edge_ids || []).length} edge(s)</span></div></div>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="card">
            <h3>Docs-only baseline (no graph)</h3>
            <div className="muted" style={{ marginBottom: 6 }}>Hybrid retrieval + extractive reader over the same documents.</div>
            <div className="answer">{res.baseline_docs_only?.length ? res.baseline_docs_only.map((a) => <Pill key={a} kind="warn">{a}</Pill>) : <span className="muted">Nothing the documents state directly.</span>}</div>
            {res.answers && res.baseline_docs_only && (() => {
              const g = new Set(res.answers), b = new Set(res.baseline_docs_only)
              const same = g.size === b.size && [...g].every((x) => b.has(x))
              return <div style={{ marginTop: 10 }}>{res.graph_enabled === false ? null : same
                ? <Pill kind="ok">same answer: documents were enough</Pill>
                : <Pill kind="bad">differs: documents could not compose the relationships</Pill>}</div>
            })()}
            <div className="muted" style={{ marginTop: 12, fontSize: 12 }}>No edge ids, no validity windows, no way to show a path: nothing here can be verified.</div>
          </div>
        </div>
      )}
    </div>
  )
}
